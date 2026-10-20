"""Auditoria viva do registry: batch ``verify_companies --fetch`` em TODAS as entradas.

F72 (roadmap v5) — a UNICA fase com rede permitida. Para cada empresa do
registry (``CompanyRegistry.entries``), roda o MESMO caminho do
``scripts/verify_companies.py --fetch`` (``collect_company``) e registra o
desfecho real por tenant — evidencia, nao palpite.

Guardrails (spec F72, TODOS obrigatorios):

* REDE: apenas o fetch dos scrapers publicos do pipeline (sem auth, sem
  escrita remota). O geocoding externo (Nominatim) fica OFF (flag default
  ``INTERNSHIP_FINDER_GEOCODING``); o cache de geocoding escreve sob o CWD.
* PACING: pausa serial de ``--pacing`` segundos entre empresas (default 2.0s
  = "1 req/2s por host" no pior caso: hosts compartilhados nunca recebem dois
  fetchs com menos de 2s de intervalo; hosts distintos so ganham mais folga).
* JANELA: ``--window HH:MM-HH:MM`` (UTC) define o periodo proibido (producao:
  09:00-09:15, cron do refresh). ``--window-guard`` segundos (default 60)
  ANTICIPA o bloqueio: um fetch so inicia se ``agora + custo maximo esperado``
  terminar ANTES do inicio da janela (ou se a janela ja passou). Custo maximo
  esperado = ``timeout + TIMEOUT_MARGIN`` (+5s de folga).
* RESUMIVEL: checkpoint JSONL (uma linha por empresa, append + flush). Ao
  retomar, empresas ja presentes sao puladas; linha truncada (crash no meio
  do append) e ignorada sem derrubar o lote.
* ``data/`` intocavel: nenhum artefato e escrito dentro do repo; checkpoint e
  resultado saem para paths explicitos (default: diretorio do checkpoint).

Resultado: JSON com uma entrada por empresa (resolved tenants, summary do
collect_company verbatim, tempos, classificacao). A ANALISE (drift, falhas
conhecidas, relatorio) fica fora daqui — este runner so mede.

Uso:
    .venv/bin/python scripts/audit_registry.py --checkpoint /tmp/audit.jsonl \
        --out /tmp/audit_results.json --timeout 30 --limit 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, time as dtime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.collectors.ats_scraper import (  # noqa: E402
    TIMEOUT_MARGIN,
    collect_company,
)
from internship_finder.registry import CompanyRegistry  # noqa: E402

# Classificacao de saude POR EMPRESA (tenant-agnostica: a empresa e "viva" se
# QUALQUER tenant resolveu >=1 vaga; o detalhe por tenant fica no summary).
HEALTHY = "healthy"  # algum tenant com >=1 vaga (summary["ok"] nao-vazio)
EMPTY = "empty"  # tenants responderam, todos com 0 vagas
ERROR = "error"  # timeout/falha em todos os tenants (ou not_found)


def parse_window(spec: str) -> tuple[dtime, dtime] | None:
    """Janela proibida ``HH:MM-HH:MM`` (UTC). ``none``/vazio desliga o guard."""
    spec = (spec or "").strip().lower()
    if not spec or spec == "none":
        return None
    try:
        a, b = spec.split("-")
        ha, ma = a.strip().split(":")
        hb, mb = b.strip().split(":")
        start, end = dtime(int(ha), int(ma)), dtime(int(hb), int(mb))
    except ValueError:
        raise SystemExit(f"--window invalido: {spec!r} (use HH:MM-HH:MM ou none)")
    if start >= end:
        raise SystemExit(f"--window invalido: inicio >= fim ({spec!r})")
    return start, end


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today_at(hhmm: dtime, base: datetime) -> datetime:
    """Data de ``base`` no horario ``hhmm`` (pura: sem relógio interno)."""
    return base.replace(hour=hhmm.hour, minute=hhmm.minute, second=0, microsecond=0)


def window_sleep_seconds(
    now: datetime,
    window: tuple[dtime, dtime] | None,
    expected_max_s: float,
) -> float:
    """Segundos a dormir ANTES de iniciar um fetch de custo ``expected_max_s``.

    Regra: pode iniciar se o fetch TERMINA antes do inicio da janela, ou se a
    janela de hoje ja passou. Caso contrario dorme ate o fim da janela. Com
    janela=None (ou expected_max_s<=0) nunca bloqueia.

    Pura/determinística: a janela de HOJE deriva do proprio ``now`` (sem
    relógio interno) — testável offline com datetime fixo (test_f72).
    """
    if not window or expected_max_s <= 0:
        return 0.0
    start, end = window
    start_dt, end_dt = _today_at(start, now), _today_at(end, now)
    fetch_end = now + _td(expected_max_s)
    if fetch_end <= start_dt:  # termina antes (ou exatamente no inicio): livre
        return 0.0
    if now >= end_dt:  # janela ja passou: livre
        return 0.0
    # fetch atravessaria a janela (ou estamos dentro dela): dormir ate o fim
    return (end_dt - now).total_seconds() + 1.0


def _td(seconds: float):
    from datetime import timedelta

    return timedelta(seconds=seconds)


def classify_company(summary: dict) -> str:
    """Saude da empresa a partir do summary do collect_company."""
    if summary.get("not_found"):
        return ERROR
    if summary.get("ok"):
        return HEALTHY
    if summary.get("empty"):
        return EMPTY
    return ERROR


def load_checkpoint(path: Path) -> dict[str, dict]:
    """Linhas completas do checkpoint indexadas por empresa (name).

    Linha truncada/corrompida (crash no meio do append) e ignorada — o lote
    apenas refara aquela empresa. Linha sem ``name``/``result`` idem.
    """
    done: dict[str, dict] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("name"), str) \
                and "result" in rec:
            done[rec["name"]] = rec
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="timeout por scraper/tenant (s); default 30")
    parser.add_argument("--limit", type=int, default=8,
                        help="maximo de vagas por tenant (0 = ilimitado)")
    parser.add_argument("--pacing", type=float, default=2.0,
                        help="pausa serial entre empresas (s); default 2.0")
    parser.add_argument("--window", default="09:00-09:15",
                        help="janela proibida HH:MM-HH:MM UTC (none desliga)")
    parser.add_argument("--window-guard", type=float, default=60.0,
                        help="folga extra somada ao custo maximo esperado (s)")
    parser.add_argument("--checkpoint", required=True,
                        help="JSONL resumivel (1 linha/empresa, append)")
    parser.add_argument("--out", required=True,
                        help="JSON final com o resultado de todas as empresas")
    parser.add_argument("--only", default="",
                        help="subconjunto: nomes separados por virgula (debug)")
    args = parser.parse_args(argv)

    window = parse_window(args.window)
    registry = CompanyRegistry()
    entries = registry.entries
    if args.only:
        wanted = {n.strip() for n in args.only.split(",") if n.strip()}
        entries = [e for e in entries if e.name in wanted]
    names = [e.name for e in entries]
    print(f"batch: {len(names)} empresas | timeout={args.timeout}s "
          f"limit={args.limit} pacing={args.pacing}s window={args.window} "
          f"(guard +{args.window_guard}s)", flush=True)

    ckpt_path = Path(args.checkpoint)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_checkpoint(ckpt_path)
    print(f"checkpoint: {len(done)} empresas ja auditadas "
          f"(retomando sem refaze-las)", flush=True)

    # Custo maximo esperado de um fetch: timeout + margem do subprocesso +
    # folga do guard. Usa o MESMO TIMEOUT_MARGIN do collect_company.
    expected_max = args.timeout + TIMEOUT_MARGIN + args.window_guard + 5.0

    t_batch = time.time()
    for i, entry in enumerate(entries, start=1):
        if entry.name in done:
            continue
        # Guarda de janela ANTES de cada empresa (bloqueia iniciar um fetch
        # que atravessaria a janela proibida).
        sleep_s = window_sleep_seconds(_utc_now(), window, expected_max)
        if sleep_s > 0:
            print(f"[window] aguardando {sleep_s:.0f}s "
                  f"(janela proibida {args.window} UTC)", flush=True)
            time.sleep(sleep_s)

        t0 = time.time()
        started = _utc_now().isoformat(timespec="seconds")
        print(f"[{i}/{len(names)}] {entry.name!r} "
              f"(ats={entry.ats} tenant={entry.tenant}) ...", flush=True)
        try:
            _, summary = collect_company(
                entry.name, timeout=args.timeout, limit=args.limit
            )
        except Exception as exc:  # noqa: BLE001 - auditoria nunca derruba o lote
            summary = {"ok": [], "empty": [], "timeout": [], "failed": [],
                       "skipped": [], "not_found": False, "companies": {},
                       "fatal": f"{type(exc).__name__}: {exc}"}
        elapsed = time.time() - t0
        result = {
            "name": entry.name,
            "registry_ats": entry.ats,
            "registry_tenant": entry.tenant,
            "enabled": entry.enabled,
            "started_utc": started,
            "elapsed_s": round(elapsed, 1),
            "health": classify_company(summary),
            "summary": summary,
        }
        with ckpt_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
        done[entry.name] = result
        ok_n = len(summary.get("ok", []))
        print(f"    -> {result['health']} em {elapsed:.1f}s "
              f"(ok={ok_n} empty={len(summary.get('empty', []))} "
              f"timeout={len(summary.get('timeout', []))} "
              f"failed={len(summary.get('failed', []))} "
              f"skipped={len(summary.get('skipped', []))} "
              f"not_found={summary.get('not_found')})", flush=True)
        time.sleep(max(0.0, args.pacing))

    # JSON final: TODAS as empresas (checkpoint + desta execucao).
    out = {
        "meta": {
            "finished_utc": _utc_now().isoformat(timespec="seconds"),
            "companies": len(done),
            "timeout_s": args.timeout,
            "limit": args.limit,
            "pacing_s": args.pacing,
            "window": args.window,
            "window_guard_s": args.window_guard,
            "batch_elapsed_s": round(time.time() - t_batch, 1),
        },
        "companies": [done[n] for n in names if n in done],
    }
    missing = [n for n in names if n not in done]
    if missing:
        out["meta"]["missing"] = missing
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    counts: dict[str, int] = {}
    for r in out["companies"]:
        counts[r["health"]] = counts.get(r["health"], 0) + 1
    print(f"\ndone: {len(done)}/{len(names)} empresas "
          f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))}) "
          f"em {out['meta']['batch_elapsed_s']}s -> {args.out}", flush=True)
    if missing:
        print(f"ATTENCAO: {len(missing)} empresas sem resultado: {missing}",
              flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
