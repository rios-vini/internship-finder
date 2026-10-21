"""F90 — fixture de contrato: suspicious_zero no digest do run (C3).

Passo 0 desta fase (21/10/2026) verificou no código E no JSONL de produção
que o pipeline JÁ cobre o objetivo C3 end-to-end — a fase encolheu para
verificação + fixture de contrato (regressão) + relatório, SEM mudança em
código de produção:

- ``internship_finder.health._detect_zero_return``: série ``(source,
  company)`` cujo run MAIS RECENTE respondeu ``empty`` depois de
  ``MIN_OK_HISTORY_FOR_ZERO_RETURN`` (=3) runs ``ok`` anteriores com
  vagas — a mesma conservadoridade que a spec F90 pede (mediana>0,
  collected=0, >=3 runs de história ok).
- ``refresh_daily`` avalia ``build_health_report`` sobre o JSONL COMPLETO
  após a coleta e ``build_message`` renderiza a linha
  "voltou a zero (empty) após N runs com vagas" no bloco
  "Problemas detectados" do digest diário — display-only: nunca exclui
  vaga, nunca derruba run, nunca vira alarme de falha.
- Guards exigidos pela spec já vivos no código: timeout/erro NÃO contam
  como zero (status estritamente ``empty``; falhas têm linhas próprias);
  fonte legítima de zero (nunca teve ok>0) fica só no contador
  "N sem vagas"; história curta (<3) não alerta; série aposentada (F58,
  36h sem registro) não alerta para sempre.
- Evidência real (50 runs): 31 dias-suspeito (Siemens Healthineers
  avature desde 29/09; BCG bamboohr 08-18/10) com disparo 1:1 (32
  zero_return, 0 falso-negativo). Os helpers privados de ``health`` são
  importados de propósito no bloco real: o invariante deve compartilhar
  a SEMÂNTICA exata de ordenação/aposentadoria, não uma cópia.

Esta suíte TRAVA o contrato (regressão): se alguém mexer no health ou no
digest e o digest deixar de DIZER quando uma fonte que normalmente
retorna vagas retorna zero, ela fica vermelha. Os 4 casos da spec:
mediana>0 + zero hoje -> flag; mediana=0 -> sem flag; <3 runs de
história -> sem flag; timeout -> sem flag zero (linha própria).

Standalone e OFFLINE (sem rede, sem escrever em data/): fixtures JSONL
em tmpdir + bloco real SOMENTE LEITURA sobre data/collection_metrics.jsonl
(SKIP sem o arquivo — padrão CI, mesmo que test_zero_return). Uso:

    .venv/bin/python scripts/test_f90.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))  # importa refresh_daily
sys.path.insert(0, str(SCRIPTS.parent / "src"))

import refresh_daily as rd  # noqa: E402
import internship_finder.health as health  # noqa: E402
from internship_finder.health import (  # noqa: E402
    MIN_OK_HISTORY_FOR_ZERO_RETURN,
    SERIES_STALE_HOURS,
    build_health_report,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


# --- fixtures ---------------------------------------------------------------

HIST = ["2026-10-15T09:00:00Z", "2026-10-16T09:00:00Z",
        "2026-10-17T09:00:00Z", "2026-10-18T09:00:00Z"]
TODAY = "2026-10-19T09:00:00Z"


def _tenant(rid: str, source: str, company: str, status: str,
            collected: int, error_code: str | None = None) -> dict:
    """Registro tenant minimo e valido (mesmo schema do cli._tenant_record)."""
    return {
        "type": "tenant", "run_id": rid, "timestamp": rid,
        "company": company, "source": source,
        "ats": source.split(":", 1)[0], "status": status,
        "collected": collected,
        "error": "boom" if status in ("timeout", "error") else None,
        "error_code": error_code, "duration": 1.5,
    }


def _run_record(rid: str, total: int, eligible: int, dedup: int = 1) -> dict:
    return {"type": "run", "run_id": rid, "timestamp": rid,
            "total_collected": total, "filtered": total,
            "dedup_removed": dedup, "eligible": eligible}


def _serie(source: str, company: str,
           hist: list[tuple[str, int]], today_status: str,
           today_collected: int = 0,
           error_code: str | None = None) -> list[dict]:
    """Série (source, company): HIST runs de história + 1 registro hoje.

    ``hist`` são pares ``(status, collected)`` — produção grava ``empty``
    para resposta com 0 vagas (nunca ``ok`` com 0), e o fixture espelha
    isso para não forjar alertas de queda que não existem na realidade.
    """
    rows = [_tenant(r, source, company, st, v)
            for r, (st, v) in zip(HIST, hist)]
    rows.append(_tenant(TODAY, source, company, today_status,
                        today_collected, error_code))
    return rows


def _write_fixture(tmp: Path, name: str, series: list[list[dict]],
                   run_total: int = 37, run_eligible: int = 12) -> Path:
    """JSONL: bloco de história (4 runs) ANTES do bloco de hoje.

    Espelha a produção (append pós-run): o resumo do run vem de
    ``read_new_records(path, skip_lines)`` e o health do arquivo COMPLETO.
    """
    hist_lines = []
    for i, rid in enumerate(HIST):
        hist_lines.append(_run_record(rid, 30 + i, 10 + i))
        for rows in series:
            hist_lines.append(rows[i])
    today_lines = [_run_record(TODAY, run_total, run_eligible)]
    today_lines += [rows[-1] for rows in series]
    path = tmp / f"metrics_{name}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for rec in hist_lines + today_lines:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def _digest(path: Path) -> tuple[dict, list[dict], str | None]:
    """Caminho de produção: resumo do run novo + health do arquivo todo."""
    skip = _history_len(path)
    summary = rd.summarize_run(rd.read_new_records(path, skip))
    report = build_health_report(rd.read_new_records(path, 0))
    msg = rd.build_message(summary, report["alerts"], 0)
    return summary, report["alerts"], msg


def _history_len(path: Path) -> int:
    """Linhas antes do bloco de hoje (run record de TODAY delimita)."""
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if TODAY in line and '"type": "run"' in line:
                break
            count += 1
    return count


def _zero_alerts(alerts: list[dict]) -> list[dict]:
    return [a for a in alerts if a.get("type") == "zero_return"]


# --- G1: detector (fixture JSONL -> build_health_report) --------------------

def test_g1_detector() -> None:
    print("== G1: detector zero_return sobre fixture JSONL ==")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_fixture(Path(tmpdir), "g1", [
            # mediana de [10, 8, 12, 10] = 10 > 0; empty hoje -> SUSPEITO
            _serie("sf:alfa", "Alfa",
                   [("ok", 10), ("ok", 8), ("ok", 12), ("ok", 10)], "empty"),
            # nunca teve ok>0 (mediana=0): zero legítimo/sazonal
            _serie("sf:beta", "Beta",
                   [("empty", 0)] * 4, "empty"),
            # só 2 runs ok>0: história curta, gate conservador
            _serie("sf:gamma", "Gamma",
                   [("ok", 5), ("ok", 7), ("empty", 0), ("empty", 0)],
                   "empty"),
            # timeout hoje: tem linha PRÓPRIA, não é zero
            _serie("sf:delta", "Delta",
                   [("ok", 20), ("ok", 22), ("ok", 21), ("ok", 20)],
                   "timeout", error_code="TIMEOUT"),
            # error hoje: idem timeout
            _serie("sf:eps", "Eps",
                   [("ok", 3), ("ok", 4), ("ok", 2), ("ok", 4)],
                   "error", error_code="FETCH_ERROR"),
            # saudável: ok hoje
            _serie("sf:zeta", "Zeta",
                   [("ok", 6), ("ok", 9), ("ok", 8), ("ok", 7)], "ok",
                   today_collected=7),
        ])
        alerts = build_health_report(rd.read_new_records(path, 0))["alerts"]
        zeros = _zero_alerts(alerts)

        check("G1.1 mediana>0 + zero hoje -> flag (exatamente 1)",
              len(zeros) == 1)
        if zeros:
            a = zeros[0]
            check("G1.1a fonte correta", a["source"] == "sf:alfa")
            check("G1.1b empresa correta", a["company"] == "Alfa")
            check("G1.1c ok_history conta os ok>0 anteriores",
                  a["ok_history"] == 4)
            check("G1.1d last_ok_collected = último ok",
                  a["last_ok_collected"] == 10)
        check("G1.2 mediana=0 (nunca teve vagas) -> SEM flag",
              not any(z["source"] == "sf:beta" for z in zeros))
        check("G1.3 <3 runs de história -> SEM flag",
              not any(z["source"] == "sf:gamma" for z in zeros))
        check("G1.4 timeout hoje -> SEM flag zero (linha própria de falha)",
              not any(z["source"] == "sf:delta" for z in zeros))
        check("G1.5 error hoje -> SEM flag zero (linha própria de falha)",
              not any(z["source"] == "sf:eps" for z in zeros))
        check(f"G1.6 gate de conservadoridade = {MIN_OK_HISTORY_FOR_ZERO_RETURN}",
              MIN_OK_HISTORY_FOR_ZERO_RETURN == 3)


# --- G2: digest end-to-end, zero suspeito SEM falhas (flag informativa) -----

def test_g2_digest_zero_puro() -> None:
    print("== G2: digest com zero suspeito e SEM falhas (flag informativa) ==")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_fixture(Path(tmpdir), "g2", [
            _serie("sf:alfa", "Alfa",
                   [("ok", 10), ("ok", 8), ("ok", 12), ("ok", 10)], "empty"),
            _serie("sf:beta", "Beta", [("empty", 0)] * 4, "empty"),
            _serie("sf:zeta", "Zeta",
                   [("ok", 6), ("ok", 9), ("ok", 8), ("ok", 7)], "ok",
                   today_collected=7),
        ])
        summary, alerts, msg = _digest(path)
        zeros = _zero_alerts(alerts)

        check("G2.1 health dispara zero_return no fixture",
              len(zeros) == 1 and zeros[0]["source"] == "sf:alfa")
        check("G2.2 mensagem construída SEM always_notify (alerta é o gatilho)",
              msg is not None)
        if msg is None:
            return
        check("G2.3 header continua 'Coleta concluída' (zero NÃO é alarme "
              "de falha)", "✅ Coleta concluída" in msg)
        check("G2.4 bloco 'Problemas detectados' presente",
              "⚠️ Problemas detectados:" in msg)
        check("G2.5 linha do zero suspeito renderiza exata",
              "• Alfa (sf:alfa) — voltou a zero (empty) após 4 runs com "
              "vagas (último ok: 10)" in msg)
        check("G2.6 zero legítimo (Beta) SEM linha própria — só no contador",
              "Beta" not in msg)
        check("G2.7 contador informativo '2 sem vagas' (Alfa+Beta)",
              "2 sem vagas" in msg)
        check("G2.8 resumo do run intacto (display-only)",
              "Vagas: 37 brutas → 12 elegíveis (1 duplicata removida)" in msg
              and "Fontes: 1 ok (7 vagas)" in msg)
        check("G2.9 summary não contaminado pelo alerta (counts do run)",
              summary["empty"] == 2 and summary["ok"]["count"] == 1
              and summary["timeout"] == [] and summary["error"] == [])
# --- G3: digest com guards coexistindo (timeout/erro/curto + 1 suspeito) ----

def test_g3_digest_guards() -> None:
    print("== G3: digest com timeout/erro/história curta + zero suspeito ==")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_fixture(Path(tmpdir), "g3", [
            _serie("sf:alfa", "Alfa",
                   [("ok", 10), ("ok", 8), ("ok", 12), ("ok", 10)], "empty"),
            _serie("sf:beta", "Beta", [("empty", 0)] * 4, "empty"),
            _serie("sf:gamma", "Gamma",
                   [("ok", 5), ("ok", 7), ("empty", 0), ("empty", 0)],
                   "empty"),
            _serie("sf:delta", "Delta",
                   [("ok", 20), ("ok", 22), ("ok", 21), ("ok", 20)],
                   "timeout", error_code="TIMEOUT"),
            _serie("sf:eps", "Eps",
                   [("ok", 3), ("ok", 4), ("ok", 2), ("ok", 4)],
                   "error", error_code="FETCH_ERROR"),
            _serie("sf:zeta", "Zeta",
                   [("ok", 6), ("ok", 9), ("ok", 8), ("ok", 7)], "ok",
                   today_collected=7),
        ])
        summary, alerts, msg = _digest(path)

        check("G3.0 digest construído (falhas + zero suspeito)",
              msg is not None)
        if msg is None:
            return
        check("G3.1 falhas mudam o header (são alarme; zero não era)",
              "⚠️ Coleta parcial: 2 de 6 fontes falharam" in msg)
        check("G3.2 zero suspeito continua presente entre as falhas",
              "• Alfa (sf:alfa) — voltou a zero (empty) após 4 runs com "
              "vagas (último ok: 10)" in msg)
        check("G3.3 exatamente 1 linha de zero no digest",
              msg.count("voltou a zero") == 1)
        check("G3.4 timeout tem linha própria (sem flag zero)",
              "• Delta (sf:delta) — sem resposta a tempo (timeout)" in msg)
        check("G3.5 error tem linha própria (sem flag zero)",
              "• Eps (sf:eps) — erro ao buscar vagas" in msg)
        check("G3.6 história curta (Gamma) e zero legítimo (Beta) SEM linha",
              "Gamma" not in msg and "Beta" not in msg)
        check("G3.7 contador agrega os 3 empties (Alfa+Beta+Gamma)",
              "3 sem vagas" in msg)
        check("G3.8 falhas no resumo contam como falha (não como zero)",
              len(summary["timeout"]) == 1 and len(summary["error"]) == 1
              and summary["empty"] == 3)


# --- G4: invariantes display-only -------------------------------------------

def test_g4_invariantes() -> None:
    print("== G4: invariantes display-only do contrato ==")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_fixture(Path(tmpdir), "g4", [
            _serie("sf:alfa", "Alfa",
                   [("ok", 10), ("ok", 8), ("ok", 12), ("ok", 10)], "empty"),
            _serie("sf:zeta", "Zeta",
                   [("ok", 6), ("ok", 9), ("ok", 8), ("ok", 7)], "ok",
                   today_collected=7),
        ])
        records = rd.read_new_records(path, 0)
        snapshot = json.dumps(records, sort_keys=True)
        size_before = path.stat().st_size

        build_health_report(records)  # exerce a função sob a lista snapshotted
        _, alerts, msg = _digest(path)

        check("G4.0 digest construído (zero suspeito isolado)",
              msg is not None)
        if msg is None:
            return
        check("G4.1 health não muta os registros de entrada (read-only)",
              json.dumps(records, sort_keys=True) == snapshot)
        check("G4.2 arquivo JSONL inalterado pelo fluxo inteiro",
              path.stat().st_size == size_before)
        check("G4.3 zero_return não altera exit nem gera falha no resumo",
              "Coleta concluída" in msg and "timeout 0" in msg)
        check(f"G4.4 guarda F58 de aposentadoria = {SERIES_STALE_HOURS}h",
              SERIES_STALE_HOURS == 36)


# --- G5: bloco real (SOMENTE LEITURA; SKIP sem data/ — padrão CI) ------------

def _expected_suspicious(records: list[dict]) -> set[tuple[str, str]]:
    """Séries suspeitas segundo a DEFINIÇÃO F90 (spec), caminhando o JSONL.

    Último registro da série = ``empty`` + >=3 runs ``ok`` anteriores com
    vagas + série não-aposentada (F58). Usa os helpers PRIVADOS de health
    de propósito: o invariante deve compartilhar a semântica exata de
    validação/ordenação/aposentadoria do módulo, não uma cópia que drifte.
    """
    tenants = health._tenant_records(records, [])
    by_series: dict[tuple[str, str], list[dict]] = {}
    for rec in tenants:
        by_series.setdefault((rec["source"], rec.get("company", "")),
                             []).append(rec)
    latest_dt = None
    for rec in tenants:
        rec_dt = health._parse_sort_dt(health._sort_key(rec)[1])
        if rec_dt is not None and (latest_dt is None or rec_dt > latest_dt):
            latest_dt = rec_dt
    expected: set[tuple[str, str]] = set()
    for key, rows in by_series.items():
        rows.sort(key=health._sort_key)
        if health._series_is_stale(rows, latest_dt):
            continue  # aposentada (F58): estado final não é observável
        last = rows[-1]
        if last["status"] != "empty":
            continue
        prior_ok = [r for r in rows[:-1]
                    if r["status"] == "ok" and r["collected"] > 0]
        if len(prior_ok) >= MIN_OK_HISTORY_FOR_ZERO_RETURN:
            expected.add(key)
    return expected


def test_g5_real_data() -> None:
    print("== G5: dados reais (read-only; SKIP sem data/) ==")
    path = SCRIPTS.parent / "data" / "collection_metrics.jsonl"
    if not path.exists():
        print(f"  [SKIP] {path} ausente (padrão CI — bloco real é VPS-only)")
        return
    size_before = path.stat().st_size
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                records.append(rec)

    alerts = build_health_report(records)["alerts"]
    zeros = _zero_alerts(alerts)

    check("G5.1 somente leitura (tamanho inalterado)",
          path.stat().st_size == size_before)
    check(f"G5.2 {len(zeros)} zero_return(is) no arquivo real — schema válido",
          all(z.get("source") and z.get("company") is not None
              and z.get("ok_history", 0) >= MIN_OK_HISTORY_FOR_ZERO_RETURN
              and z.get("last_ok_collected", 0) > 0 for z in zeros))
    expected = _expected_suspicious(records)
    actual = {(z["source"], z["company"]) for z in zeros}
    check(f"G5.3 INVARIÁRIO F90: alertas == séries suspeitas "
          f"(esperado {len(expected)}, disparado {len(actual)}) "
          "— sem falso negativo E sem falso positivo",
          expected == actual)


def main() -> int:
    test_g1_detector()
    test_g2_digest_zero_puro()
    test_g3_digest_guards()
    test_g4_invariantes()
    test_g5_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
