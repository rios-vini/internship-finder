#!/usr/bin/env python3
"""Refresh diario da coleta + alertas (Telegram) — P2 #17.

Rotina standalone de producao: faz a COLETA REAL do registry (subprocesso do
CLI), avalia o health sobre o JSONL atualizado (reusa ``build_health_report``
de ``src/internship_finder/health.py`` — sem camada nova) e envia alerta via
Telegram SOMENTE em anomalia (anti-spam). Uso:

    .venv/bin/python scripts/refresh_daily.py                 # producao
    .venv/bin/python scripts/refresh_daily.py --dry-run       # demonstrativo, sem rede/data
    .venv/bin/python scripts/refresh_daily.py --always-notify # digest diario (documentado, nao default)

Fluxo:

1. **Backup/rotacao** — copia os arquivos reais de ``data/``
   (``jobs.json``/``.csv``, ``eligible_jobs.json``/``.csv`` e
   ``collection_metrics.jsonl``) para ``data/archive/<timestamp>/`` ANTES de
   rodar. Preserva o snapshot anterior (rollback = copiar de volta; o
   ``run_info.json`` gravado no archive registra o run que o substituiu).
   Copia, nao move: a origem fica intacta ate o CLI gravar por cima.
2. **Coleta real** — subprocesso ``python -m internship_finder.cli
   --registry --timeout <T>`` (cwd = raiz do repo; PYTHONPATH=src; stdout/
   stderr herdados — caem no log do cron). Exit 0 = ok; 1 = nada
   eligible/coletado; 2 = parcial com falhas reais (dados salvos).
3. **Health** — ``build_health_report`` sobre o conteudo COMPLETO do JSONL
   apos o run (defensivo: malformados nunca derrubam). Os registros do run
   atual sao isolados por snapshot de linhas (antes x depois), sem adivinhar
   run_id.
4. **Alerta** — 1 mensagem por run, alertas deduplicados por fonte.
   Dispara quando: exit != 0 (run falhou/parcial), OU o relatorio tem alertas
   (queda brusca / erro recorrente), OU ``--always-notify`` (digest diario,
   nao default). Sem anomalia -> sem envio. Credenciais em ``.env``
   (gitignored): ``TELEGRAM_BOT_TOKEN`` e ``TELEGRAM_CHAT_ID``; sem token ->
   aviso no log e NAO envia (nunca crasha).

Flags:

- ``--dry-run``: sem rede, sem escrever em ``data/`` — usa um tempdir com
  dados sinteticos (rotacao + health + mensagem validados; a mensagem e
  impressa, nada e enviado). Exit 0.
- ``--config PATH``: arquivo de configuracao (default ``.env`` na raiz;
  formato ``CHAVE=VALOR``, ``#`` comenta).
- ``--always-notify``: envia o resumo mesmo sem anomalia (digest; documentado,
  nao e o default).
- ``--timeout N``: timeout por scraper passado ao CLI (default 60).
- ``--max-collection-secs N``: teto total do subprocesso de coleta (default
  5400 = 90 min; a coleta completa de 39 empresas e ~10-30 min). Estourado:
  mensagem "run falhou (timeout do subprocesso)".

Concorrencia: o cron usa ``flock -n`` (ver README) para nunca sobrepor runs;
este script nao reimplementa lock.

Limitação conhecida (documentada em MASTER_PLAN/README): o arquivo JSONL
acumula lixo historico de validacao (registros ``type: tenant`` de mocks, sem
run_id de coleta real; ex.: ``smartrecruiters:other`` 70x ``error``). O health
e defensivo (malformados pulados) mas o lixo VALIDO entra nas contagens por
fonte — uma fonte que so tem lixo emitira "erro recorrente" em TODO run ate o
JSONL ser limpo (1 alerta por fonte por run; nao ha dedup entre runs).
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from internship_finder.health import build_health_report  # reuso — sem camada nova

log = logging.getLogger("refresh_daily")

# Arquivos de data/ rotacionados a cada run (fonte de dados + metricas).
ROTATE_FILES = [
    "jobs.json",
    "jobs.csv",
    "eligible_jobs.json",
    "eligible_jobs.csv",
    "collection_metrics.jsonl",
]

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Nomes das chaves aceitas no .env.
ENV_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT = "TELEGRAM_CHAT_ID"


def utcnow_iso() -> str:
    """Timestamp UTC atual em ISO 8601 (mesmo formato das metricas)."""
    return datetime.now(UTC).isoformat()


def repo_root() -> Path:
    """Raiz do repositorio (este script vive em ``scripts/``)."""
    return Path(__file__).resolve().parents[1]


# --- config ----------------------------------------------------------------

def load_env_config(path: Path | str) -> dict:
    """Le ``CHAVE=VALOR`` de um arquivo .env simples (``#`` comenta, linhas
    em branco puladas). Arquivo inexistente/ilegivel -> dict vazio (o envio
    vira aviso, nunca crasha)."""
    config: dict = {}
    path = Path(path)
    if not path.exists():
        log.warning("config %s nao encontrado; sem credenciais de Telegram", path)
        return config
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("config %s ilegivel (%s); sem credenciais de Telegram", path, exc)
        return config
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        config[key.strip()] = value.strip().strip('"').strip("'")
    return config


# --- rotacao ---------------------------------------------------------------

def rotate(data_dir: Path, archive_root: Path, ts: str) -> Path:
    """Copia os arquivos reais de ``data_dir`` para ``archive_root/<ts>/``.

    Copia (nao move): a origem fica intacta ate o CLI da coleta gravar por
    cima. Arquivos ausentes sao pulados com aviso. Devolve o diretorio do
    archive. Rollback = copiar de volta o conteudo de ``archive_root/<ts>/``.
    """
    archive_dir = archive_root / ts
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in ROTATE_FILES:
        src = data_dir / name
        if not src.exists():
            log.warning("rotacao: %s ausente (primeiro run?); pulado", src)
            continue
        dst = archive_dir / name
        shutil.copy2(src, dst)
        copied += 1
        log.info("rotacao: backup %s -> %s", src, dst)
    log.info("rotacao: %d arquivos arquivados em %s", copied, archive_dir)
    return archive_dir


# --- coleta via subprocesso ------------------------------------------------

def collection_command(timeout: float) -> list[str]:
    """Linha de comando da coleta real (subprocesso, cwd = raiz do repo)."""
    return [
        sys.executable, "-m", "internship_finder.cli",
        "--registry",
        "--timeout", str(timeout),
    ]


def run_collection(command: list[str], cwd: Path, max_secs: float) -> subprocess.CompletedProcess:
    """Roda a coleta como subprocesso, herdando stdout/stderr (cai no log do
    cron). Erro/estouro do teto vira ``timeout`` no processo retornado."""
    env = {"PYTHONPATH": str(cwd / "src"), "PATH": "/usr/bin:/bin"}
    log.info("coleta: subprocesso %s (cwd=%s)", " ".join(command), cwd)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            timeout=max_secs,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.error("coleta: subprocesso estourou o teto de %.0fs", max_secs)
        return subprocess.CompletedProcess(command, 124)  # 124 = timeout (convencao)


# --- metricas do run -------------------------------------------------------

def _count_lines(path: Path) -> int:
    """Numero de linhas de um arquivo (0 se ausente)."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def read_new_records(path: Path, skip_lines: int) -> list[dict]:
    """Le as linhas de ``path`` a partir de ``skip_lines`` (snapshot antes x
    depois do run). Linhas malformadas sao puladas com aviso — nunca derrubam.
    """
    records: list[dict] = []
    if skip_lines < 0:
        skip_lines = 0
    with path.open(encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            if idx < skip_lines:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                log.warning("registro %d inparseavel; pulado", idx)
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


def summarize_run(records: list[dict]) -> dict:
    """Resumo do run atual (registros novos do JSONL) para a mensagem.

    ``type: run`` -> totais do funil (total_collected/filtered/dedup_removed/
    eligible + run_id/timestamp). ``type: tenant`` -> contagem por status,
    com ``(source, error_code)`` para timeout/error (``UNKNOWN`` quando o
    registro antigo nao tem codigo).
    """
    summary: dict = {
        "run_id": None,
        "timestamp": None,
        "total_collected": None,
        "filtered": None,
        "dedup_removed": None,
        "eligible": None,
        "ok": {"count": 0, "collected": 0},
        "empty": 0,
        "skipped": 0,
        "not_found": 0,
        "timeout": [],
        "error": [],
    }
    for rec in records:
        rtype = rec.get("type")
        if rtype == "run":
            summary["run_id"] = rec.get("run_id") or summary["run_id"]
            summary["timestamp"] = rec.get("timestamp") or summary["timestamp"]
            for key in ("total_collected", "filtered", "dedup_removed", "eligible"):
                value = rec.get(key)
                if isinstance(value, (int, float)):
                    summary[key] = int(value)
        elif rtype == "tenant":
            status = rec.get("status")
            source = rec.get("source") or "?"
            code = rec.get("error_code")
            if status == "ok":
                summary["ok"]["count"] += 1
                collected = rec.get("collected")
                if isinstance(collected, (int, float)):
                    summary["ok"]["collected"] += int(collected)
            elif status == "empty":
                summary["empty"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
            elif status == "not_found":
                summary["not_found"] += 1
            elif status == "timeout":
                summary["timeout"].append((source, code or "UNKNOWN"))
            elif status == "error":
                summary["error"].append((source, code or "UNKNOWN"))
    return summary


def _fmt(n: int) -> str:
    """Numero no formato pt-BR (37.373), legivel no Telegram."""
    return f"{n:,}".replace(",", ".")


# --- mensagem --------------------------------------------------------------

def build_message(
    summary: dict,
    report_alerts: list[dict],
    exit_code: int,
    *,
    always_notify: bool = False,
) -> str | None:
    """Monta a mensagem de alerta/digest; ``None`` = nada a enviar (anti-spam:
    sem anomalia, sem falha e sem ``--always-notify``, nao envia).
    Alertas deduplicados por fonte (1 por fonte por run)."""
    alerts = sorted(report_alerts, key=lambda a: (a.get("source", ""), a.get("type", "")))
    if not (always_notify or exit_code != 0 or alerts):
        return None

    lines: list[str] = ["📊 internship-finder · refresh diário"]
    lines.append(f"run {summary.get('run_id') or '-'} · exit {exit_code}")
    lines.append("")

    total = summary.get("total_collected")
    if total is not None:
        eligible = summary.get("eligible")
        dedup = summary.get("dedup_removed") or 0
        lines.append(
            f"Brutas: {_fmt(total)} → eligible {_fmt(eligible or 0)}"
            + (f" (dedup −{_fmt(dedup)})" if dedup else "")
        )
    ok = summary.get("ok", {})
    n_fail = len(summary.get("timeout", [])) + len(summary.get("error", []))
    lines.append(
        f"Tenants: ok {ok.get('count', 0)} ({_fmt(ok.get('collected', 0))} vagas)"
        f" · empty {summary.get('empty', 0)} · timeout {len(summary.get('timeout', []))}"
        f" · error {len(summary.get('error', []))}"
        f" · skip {summary.get('skipped', 0)} · not_found {summary.get('not_found', 0)}"
    )

    if exit_code == 1:
        lines.append("⚠️ Nenhuma vaga eligible / nada coletado (exit 1)")
    elif exit_code == 2:
        lines.append("⚠️ Coleta parcial com falhas reais (exit 2)")
    elif exit_code not in (0, 124):
        lines.append(f"⚠️ Run falhou (exit {exit_code})")
    elif exit_code == 124:
        lines.append("⚠️ Run falhou: subprocesso estourou o teto de tempo (exit 124)")

    if alerts:
        lines.append("")
        lines.append("⚠️ Alertas (health):")
        for a in alerts:
            src = a.get("source", "?")
            if a.get("type") == "drop":
                lines.append(
                    f"• {src} — queda brusca (collected {a.get('collected_atual')} "
                    f"< 50% da mediana {a.get('mediana_anterior')} · {a.get('pct')})"
                )
            elif a.get("type") == "zero_return":
                lines.append(
                    f"• {src} — voltou a zero (empty) após {a.get('ok_history')} "
                    f"runs com vagas (último ok: {a.get('last_ok_collected')})"
                )
            else:
                lines.append(
                    f"• {src} — erro recorrente ({a.get('runs_seq')} runs consecutivos)"
                )

    # Fontes ja sinalizadas nos alertas nao se repetem em "Falhas"
    # (1 alerta por fonte por run — anti-spam).
    alert_sources = {a.get("source") for a in alerts}
    failures = [f for f in dict.fromkeys(summary.get("timeout", []) + summary.get("error", []))
                if f[0] not in alert_sources]
    if failures:
        lines.append("")
        lines.append("Falhas: " + " · ".join(f"{s} [{c}]" for s, c in failures))
    return "\n".join(lines)


# --- telegram --------------------------------------------------------------

def telegram_url(token: str) -> str:
    """URL do sendMessage para um token (testavel sem rede)."""
    return TELEGRAM_API.format(token=token)


def send_telegram(token: str, chat_id: str, text: str, timeout: float = 30.0) -> dict:
    """Envia ``text`` via Bot API sendMessage; devolve o JSON da resposta.

    Qualquer falha de rede/HTTP levanta excecao (o chamador trata e loga —
    o refresh nunca crasha por causa do envio).
    """
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        telegram_url(token), data=payload, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def notify_or_log(config: dict, message: str, *, dry_run: bool) -> dict:
    """Envia OU loga a decisao; nunca levanta. Devolve o resultado do envio.

    - ``dry_run``: imprime a mensagem e nao envia (``sent=False``).
    - sem token/chat no config: aviso e nao envia (``sent=False``).
    - senao: chama ``send_telegram``; falha de rede -> erro logado e
      ``sent=False`` (o refresh nao pode cair por causa da notificacao).
    """
    if dry_run:
        print("\n===== MENSAGEM (DRY-RUN — nada enviado) =====")
        print(message)
        print("==============================================")
        return {"sent": False, "dry_run": True}
    token = config.get(ENV_TOKEN)
    chat_id = config.get(ENV_CHAT)
    if not token or not chat_id:
        log.warning(
            "alerta nao enviado: %s/%s ausentes no config (defina em .env)",
            ENV_TOKEN if not token else "ok",
            ENV_CHAT if not chat_id else "ok",
        )
        return {"sent": False, "reason": "no_credentials"}
    try:
        response = send_telegram(token, chat_id, message)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        log.error("alerta nao enviado: falha no sendMessage (%s)", exc)
        return {"sent": False, "reason": "send_error", "error": str(exc)}
    log.info("telegram response: %s", json.dumps(response, ensure_ascii=False))
    return {"sent": bool(response.get("ok")), "response": response}


# --- dry-run (dados sinteticos, sem rede/data) -----------------------------

def _seed_dry_run(data_dir: Path) -> tuple[int, int]:
    """Cria data_dir com arquivos falsos + JSONL sintetico com historia e um
    run novo com anomalia (padrao ``smartrecruiters:other`` do JSONL real).
    Devolve ``(linhas_de_historia, linhas_novas)`` para o snapshot.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "jobs.json").write_text(
        json.dumps([{"id": "sf:1", "title": "Working Student Supply Chain",
                     "company": "SAP", "country_iso": "de"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "jobs.csv").write_text("id,title\nsf:1,Working Student Supply Chain\n", encoding="utf-8")
    (data_dir / "eligible_jobs.json").write_text(
        json.dumps([{"id": "sf:1", "title": "Working Student Supply Chain",
                     "company": "SAP", "country_iso": "de", "score": 6.0}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "eligible_jobs.csv").write_text(
        "id,title,score\nsf:1,Working Student Supply Chain,6.0\n", encoding="utf-8")

    def tenant(rid: str, source: str, status: str, collected: int,
               company: str = "Acme", error_code: str | None = None) -> dict:
        return {
            "type": "tenant", "run_id": rid, "timestamp": rid,
            "company": company, "source": source,
            "ats": source.split(":", 1)[0], "status": status,
            "collected": collected,
            "error": None if status not in ("timeout", "error") else "boom",
            "error_code": error_code, "duration": 1.5,
        }

    history = [
        tenant("2026-08-30T06:00:00+00:00", "successfactors:jobs", "ok", 400, "SAP"),
        tenant("2026-08-31T06:00:00+00:00", "successfactors:jobs", "ok", 380, "SAP"),
        tenant("2026-09-01T06:00:00+00:00", "successfactors:jobs", "ok", 410, "SAP"),
        tenant("2026-09-02T06:00:00+00:00", "successfactors:jobs", "ok", 395, "SAP"),
        tenant("2026-09-03T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        tenant("2026-09-04T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        tenant("2026-09-04T12:00:00+00:00", "smartrecruiters:other", "error", 0),
    ]
    new = [
        tenant("2026-09-05T06:00:00+00:00", "successfactors:jobs", "ok", 390, "SAP"),
        tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:other", "error", 0, "Bosch", "UNKNOWN"),
        tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:continental", "timeout", 0, "Continental", "TIMEOUT"),
        {
            "type": "run", "run_id": "2026-09-05T06:00:00+00:00",
            "timestamp": "2026-09-05T06:01:00+00:00",
            "total_collected": 391, "filtered": 44, "dedup_removed": 1, "eligible": 43,
        },
    ]
    with (data_dir / "collection_metrics.jsonl").open("a", encoding="utf-8") as fh:
        for rec in history + new:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(history), len(new)


def _run_dry_run() -> int:
    """Fluxo dry-run: tempdir com dados sinteticos; valida rotacao, snapshot
    de linhas, health, resumo e mensagem. Nunca toca ``data/`` nem a rede."""
    with tempfile.TemporaryDirectory(prefix="refresh_dryrun_") as tmp:
        base = Path(tmp)
        data_dir = base / "data"
        archive_root = base / "data" / "archive"
        hist, new = _seed_dry_run(data_dir)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        print(f"== DRY-RUN (tempdir {base}) ==")
        archive_dir = rotate(data_dir, archive_root, ts)
        metrics = data_dir / "collection_metrics.jsonl"
        new_records = read_new_records(metrics, hist)
        print(f"linhas novas lidas: {len(new_records)} (esperado {new})")
        summary = summarize_run(new_records)
        print("resumo:", json.dumps(summary, ensure_ascii=False, default=str))
        records = read_new_records(metrics, 0)
        report = build_health_report(records)
        print("alertas health:", json.dumps(report["alerts"], ensure_ascii=False))
        message = build_message(summary, report["alerts"], exit_code=0)
        notify_or_log({}, message, dry_run=True)
        print(f"archive criado: {archive_dir} ({len(list(archive_dir.iterdir()))} arquivos)")
        print("DRY-RUN OK: data/ real intocada, sem rede, sem envio.")
        return 0


# --- fluxo de producao -----------------------------------------------------

def _archive_run_info(archive_dir: Path, summary: dict, alert_count: int) -> None:
    """Registra no archive o run que substituiu o snapshot (best-effort)."""
    info = {
        "rotated_at": utcnow_iso(),
        "run_id": summary.get("run_id"),
        "exit_code": summary.get("_exit_code"),
        "total_collected": summary.get("total_collected"),
        "eligible": summary.get("eligible"),
        "alerts": alert_count,
    }
    try:
        (archive_dir / "run_info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("run_info.json nao gravado: %s", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh diario da coleta (rotacao + coleta real + health"
        " + alerta Telegram em anomalia).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="sem rede e sem escrever em data/ (tempdir com dados sinteticos)")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="arquivo .env com TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID (default: .env na raiz)")
    parser.add_argument("--always-notify", action="store_true",
                        help="envia o resumo mesmo sem anomalia (digest diario; nao e o default)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="timeout por scraper passado ao CLI (default 60)")
    parser.add_argument("--max-collection-secs", type=float, default=5400.0,
                        help="teto total do subprocesso de coleta em segundos (default 5400)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.dry_run:
        return _run_dry_run()

    root = repo_root()
    data_dir = root / "data"
    metrics_path = data_dir / "collection_metrics.jsonl"
    archive_root = data_dir / "archive"
    config_path = Path(args.config) if args.config else root / ".env"

    log.info("refresh: rotacao antiga -> archive (config=%s)", config_path)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = rotate(data_dir, archive_root, ts)

    skip_lines = _count_lines(metrics_path)
    proc = run_collection(collection_command(args.timeout), root, args.max_collection_secs)
    exit_code = proc.returncode

    new_records = read_new_records(metrics_path, skip_lines)
    summary = summarize_run(new_records)
    summary["_exit_code"] = exit_code
    log.info("run %s: exit %d, %d registros novos (bruto %s, eligible %s)",
             summary.get("run_id"), exit_code, len(new_records),
             summary.get("total_collected"), summary.get("eligible"))

    records = read_new_records(metrics_path, 0)  # JSONL completo (defensivo)
    report = build_health_report(records)
    log.info("health: %d alertas", len(report["alerts"]))

    message = build_message(summary, report["alerts"], exit_code,
                            always_notify=args.always_notify)
    if message is None:
        print("Sem anomalia — nenhum envio (anti-spam).")
    else:
        print("\n===== MENSAGEM =====")
        print(message)
        print("=====================")
        result = notify_or_log(load_env_config(config_path), message, dry_run=False)
        if result.get("dry_run"):
            pass
        elif not result.get("sent"):
            log.warning("envio nao confirmado: %s",
                        result.get("reason") or result.get("error") or "desconhecido")

    _archive_run_info(archive_dir, summary, len(report["alerts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())