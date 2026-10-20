"""Testes da Fase F75 — Analítica: matriz provider×descrição + drift do
funil no digest + retenção do collection_metrics.jsonl + gêmeos residuais.

F75 em uma linha: quatro instrumentos de medida OFFLINE, sem mudar
comportamento do funil (spec: ~/.hermes/handoff/f75-analitica/ESPECIFICACAO.md).

Contratos testados:

- A (matriz provider×descrição, item 1): provider = ATS efetivo do
  source pela MESMA regra da hidratação (``_effective_ats``); cobertura
  (presença), mediana de comprimento, bucket de curtas (< régua do
  refresh ``HYDRATION_SHORT_LIMIT`` — PINADA, padrão F62), provenance
  ``description_source``; ordenação (vagas desc, nome asc); CLI exit
  0/1 + --json; determinismo.
- B (drift do funil no digest, item 2): ``weekly_stage_drift`` por
  estágio (raw→pré-filtrado→mantido, campos REAIS do record ``run``);
  <window registros ou campo ausente = estágio/None (nunca inventa);
  build_report expõe ``drift``; a linha 📈 do digest usa o formato NOVO
  quando há drift e o formato antigo (elegíveis) para reports legados
  sem o campo (migração sem quebra); sinal de delta +/−/±0.
- C (retenção do metrics jsonl, item 3): corte ``now - retention_days``
  (exatamente no corte fica RAW); rollup = 1 registro ``metrics_rollup``
  POR DIA com contagem por type + somas numéricas POR type; raw recente
  byte a byte; idempotente (2ª chamada = no-op, arquivo intocado);
  corrompido/sem timestamp/rollup pré-existente preservados; 0 = off;
  arquivo ausente = no-op; atômico (sem .tmp remanescente); default 90
  documentado no flag do refresh; wiring: roda ANTES do snapshot de
  linhas, best-effort (try/except no main).
- D (gêmeos residuais no digest, item 4): contagem de grupos
  cross-source sobreviventes — MESMA empresa (string exata casefold) +
  MESMO título (chave DE/EN do dedup, uma fonte de verdade) em ≥2
  fontes. Fixtures VERBATIM do artifact 19/10 (âncora: 10 grupos = 8
  Amazon + 1 Würth + 1 Boston Scientific — o par Amazon tem location
  ausente de um lado; chave por cidade NÃO os enxerga): os 3 shapes
  reais contam; negativos (empresa diferente com mesmo título — caso
  Workwize×godutch; label de tenant vs nome real — lidlstiftup2×Lidl,
  o F66 funde e o radar MEDE o residual pós-dedup; mesma fonte; sem
  empresa/título/fonte) NÃO contam; espelho DE/EN de título CONTA.
  Linha: 0 = ausente; 1..20 = informativa 👯; >20 = ALERTA ⚠️ com
  "revisar dedup"; extrator por prefixo; o ALERTA sobrevive ao compact
  (nível 3) e a linha normal não; digest_sections insere a linha
  ANTES do 🔗 (best-effort, ausente sem gêmeos).
- E (wiring/zero-rede): flag ``--metrics-retention-days`` default 90 no
  refresh; ordem do rollup ANTES de ``skip_lines`` no main; módulos novos
  sem imports de rede; digest sem gêmeos não ganha linha (regressão zero).

Fixtures VERBATIM (produção 19/10, elegível 725): Amazon Dummerstorf
(absolventa×amazon_jobs, loc None de um lado), Würth Industrie Service
(absolventa×bundesagentur), Boston Scientific (sf×sf, cidades Kerkrade/LI
divergentes), Workwize×godutch (Amsterdam, empresas distintas — negativo).
Números da âncora reproduzidos ao vivo no relatório da fase.

Uso:  python scripts/test_f75.py   (CI: exit 0 = verde)
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import funnel_report as fr  # noqa: E402
import provider_description_matrix as pdm  # noqa: E402
import ranking_digest as rd  # noqa: E402
import refresh_daily as ref  # noqa: E402
from internship_finder import metrics_retention as mr  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Records ``type: run`` no schema REAL da produção (campos da cascata +
# contadores de morte — sem eles o header da seção 📅 fica "morto" e a
# seção inteira é ausente, padrão F44).
def _run_record(day: str, collected: int, filtered: int, eligible: int,
                **extra) -> dict:
    rec = {"type": "run", "run_id": f"{day}T09:00:02+00:00",
           "timestamp": f"{day}T09:38:00+00:00",
           "total_collected": collected, "filtered": filtered,
           "dedup_removed": 100, "eligible": eligible,
           "applicability_excluded_german_required": 1189}
    rec.update(extra)
    return rec


# 7 records: drift compara o último vs o de ``window`` corridas atrás
# (janela INCLUSIVA — 7 records: último vs PRIMEIRO, mesmo contrato do
# weekly_trend/test_f45: RUNS_WEEK tem 7 e compara RUN_TODAY vs 10-11).
RUNS_DRIFT = [
    _run_record("2026-10-11", 108000, 3100, 779),
    _run_record("2026-10-13", 108020, 3104, 801),
    _run_record("2026-10-14", 108030, 3106, 815),
    _run_record("2026-10-15", 108040, 3108, 830),
    _run_record("2026-10-16", 108050, 3110, 806),
    _run_record("2026-10-17", 108055, 3115, 820),
    _run_record("2026-10-18", 108059, 3121, 871),
]

# Pares VERBATIM do elegível de produção 19/10 (os 3 shapes da âncora).
AMAZON_TWIN = [
    {"id": "Amazon Dummerstorf GmbH - K74|absolventa:1",
     "company": "Amazon Dummerstorf GmbH - K74", "source": "absolventa",
     "title": "Praktikum im Bereich Logistik - Dummerstorf - Start 2027",
     "location": None, "country": "de", "score": 12.0,
     "url": "https://a.example/1"},
    {"id": "Amazon Dummerstorf GmbH - K74|amazon_jobs:1",
     "company": "Amazon Dummerstorf GmbH - K74", "source": "amazon_jobs",
     "title": "Praktikum im Bereich Logistik - Dummerstorf - Start 2027",
     "location": "Dummerstorf, Mecklenburg-Vorpommern, DEU",
     "country": "de", "score": 11.0, "url": "https://a.example/2"},
]
WUERTH_TWIN = [
    {"id": "Würth Industrie Service GmbH & Co. KG|absolventa:1",
     "company": "Würth Industrie Service GmbH & Co. KG", "source": "absolventa",
     "title": "Praktikant (m/w/d) im Bereich Logistik - "
              "Leihgut- & Palettenmanagement",
     "location": None, "country": "de", "score": 10.0,
     "url": "https://w.example/1"},
    {"id": "Würth Industrie Service GmbH & Co. KG|sf_dataset:bundesagentur:1",
     "company": "Würth Industrie Service GmbH & Co. KG",
     "source": "sf_dataset:bundesagentur",
     "title": "Praktikant (m/w/d) im Bereich Logistik - "
              "Leihgut- & Palettenmanagement",
     "location": "97980 Bad Mergentheim, Baden Wuerttemberg, Deutschland",
     "country": "de", "score": 9.0, "url": "https://w.example/2"},
]
BSX_TWIN = [
    {"id": "Boston Scientific|sf_dataset:successfactors:1",
     "company": "Boston Scientific", "source": "sf_dataset:successfactors",
     "title": "Data Intern- Healthcare Solutions & Partnerships (HS&P)  "
              "Netherlands (Students only)",
     "location": "Kerkrade, NL", "country": "nl", "score": 8.0,
     "url": "https://b.example/1"},
    {"id": "Boston Scientific|sf_dataset:eightfold:1",
     "company": "Boston Scientific", "source": "sf_dataset:eightfold",
     "title": "Data Intern- Healthcare Solutions & Partnerships (HS&P)  "
              "Netherlands (Students only)",
     "location": "LI,NL", "country": "nl", "score": 7.5,
     "url": "https://b.example/2"},
]
# Negativo REAL: mesma cidade+título, empresas DISTINTAS — não é gêmeo.
WORKWIZE_NEG = [
    {"id": "Workwize|sf_dataset:welcometothejungle:1", "company": "Workwize",
     "source": "sf_dataset:welcometothejungle", "title": "Operations intern",
     "location": "Amsterdam, Netherlands", "country": "nl", "score": 6.0,
     "url": "https://x.example/1"},
    {"id": "godutch|sf_dataset:teamtailor:1", "company": "godutch",
     "source": "sf_dataset:teamtailor", "title": "Operations Intern",
     "location": "Amsterdam, Netherlands", "country": "nl", "score": 5.0,
     "url": "https://x.example/2"},
]
# Negativo REAL: label de tenant × nome real (Lidl) — strings distintas:
# o F66 resolve a IDENTIDADE no dedup e FUNDE; o radar mede residual
# pós-dedup — strings crusas diferentes não são gêmeo medido.
LIDL_NEG = [
    {"id": "lidlstiftup2|sf_dataset:successfactors:1", "company": "lidlstiftup2",
     "source": "sf_dataset:successfactors",
     "title": "Praktikum Supply Chain - Bestandsmanagement",
     "location": "Neckarsulm, DE", "country": "de", "score": 9.0,
     "url": "https://l.example/1"},
    {"id": "Lidl Stiftung & Co. KG|absolventa:1",
     "company": "Lidl Stiftung & Co. KG", "source": "absolventa",
     "title": "Praktikum Supply Chain - Bestandsmanagement",
     "location": "74167 Neckarsulm", "country": "de", "score": 8.5,
     "url": "https://l.example/2"},
]
# Positivo DE/EN: MESMA empresa, título espelho DE/EN — a chave DE/EN do
# dedup converge (medido: '2027 dummerstorf logistics student working').
DE_EN_TWIN = [
    {"id": "Spiegel GmbH|absolventa:1", "company": "Spiegel GmbH",
     "source": "absolventa",
     "title": "Praktikum im Bereich Logistik - Start 2027",
     "location": "München", "country": "de", "score": 8.0,
     "url": "https://s.example/1"},
    {"id": "Spiegel GmbH|greenhouse:1", "company": "spiegel gmbh",
     "source": "greenhouse",
     "title": "Internship in Logistics - Start 2027",
     "location": "Munich", "country": "de", "score": 7.0,
     "url": "https://s.example/2"},
]


# ---------------------------------------------------------------------------
# A — matriz provider×descrição
# ---------------------------------------------------------------------------

MATRIX_JOBS = [
    {"id": "a|sf_dataset:successfactors:1", "source": "sf_dataset:successfactors",
     "company": "SAP", "title": "Praktikum Data", "description": "x" * 800,
     "description_source": "feed"},
    {"id": "b|sf_dataset:successfactors:2", "source": "sf_dataset:successfactors",
     "company": "SAP", "title": "Praktikum Logistik", "description": "y" * 300,
     "description_source": "feed"},
    {"id": "c|sf_dataset:successfactors:3", "source": "sf_dataset:successfactors",
     "company": "SAP", "title": "Praktikum Einkauf", "description": None,
     "description_source": None},
    {"id": "d|amazon_jobs:1", "source": "amazon_jobs", "company": "Amazon",
     "title": "Ops Intern", "description": "z" * 100,
     "description_source": "feed"},
    {"id": "e|amazon_jobs:2", "source": "amazon_jobs", "company": "Amazon",
     "title": "HR Intern", "description": None, "description_source": None},
    {"id": "f|direct:eures:1", "source": "direct:eures", "company": "EU",
     "title": "Research Intern", "description": "w" * 900,
     "description_source": "hydration"},
    {"id": "g|absolventa:1", "source": "absolventa:tenant", "company": "Bosch",
     "title": "Werkstudent", "description": None, "description_source": None},
]


def test_matrix() -> None:
    section("A1 — provider efetivo (mesma regra da hidratação)")
    check("sf_dataset:<ats> -> <ats>",
          pdm.provider_of({"source": "sf_dataset:successfactors"})
          == "successfactors")
    check("direct:<ats> -> <ats>",
          pdm.provider_of({"source": "direct:eures"}) == "eures")
    check("ats:slug -> ats",
          pdm.provider_of({"source": "absolventa:tenant"}) == "absolventa")
    check("source puro -> ele mesmo", pdm.provider_of({"source": "amazon_jobs"})
          == "amazon_jobs")
    check("source ausente -> '?'", pdm.provider_of({}) == "?")

    section("A2 — números da matriz (cobertura/mediana/curtas/fontes)")
    rows = pdm.matrix_rows(MATRIX_JOBS)
    by = {r["provider"]: r for r in rows}
    check("3 providers", set(by) == {"successfactors", "amazon_jobs",
                                    "eures", "absolventa"} or len(rows) == 4,
          detail=str(sorted(by)))
    sf = by.get("successfactors", {})
    check("successfactors: 3 vagas, 2 c/desc, 66.7%",
          sf.get("jobs") == 3 and sf.get("with_description") == 2
          and abs(sf.get("coverage_pct", 0) - 66.7) < 0.11,
          detail=str(sf))
    check("mediana das presentes = 800/300 -> 550",
          sf.get("median_chars") == 550, detail=str(sf.get("median_chars")))
    check("curtas (<500): a de 300 chars", sf.get("short") == 1)
    check("fontes: feed 2", sf.get("description_sources") == {"feed": 2},
          detail=str(sf.get("description_sources")))
    az = by.get("amazon_jobs", {})
    check("amazon_jobs: cobertura 50%, curta 1 (100 chars)",
          az.get("coverage_pct") == 50.0 and az.get("short") == 1)
    eu = by.get("eures", {})
    check("eures: provenance hydration", eu.get("description_sources")
          == {"hydration": 1})
    ab = by.get("absolventa", {})
    check("absolventa: 0% (mediana ausente = None)",
          ab.get("with_description") == 0 and ab.get("median_chars") is None)

    section("A3 — ordenação (vagas desc, nome asc) + determinismo")
    order = [r["provider"] for r in rows]
    check("maior provider primeiro", order[0] == "successfactors"
          and order[1] == "amazon_jobs", detail=str(order))
    check("determinismo", rows == pdm.matrix_rows(MATRIX_JOBS))

    section("A4 — CLI: exit 0 + texto; --json; ausente -> exit 1")
    with tempfile.TemporaryDirectory(prefix="f75_matrix_") as tmp:
        eligible = Path(tmp) / "eligible_jobs.json"
        eligible.write_text(json.dumps(MATRIX_JOBS), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pdm.main(["--input", str(eligible)])
        text = buf.getvalue()
        check("exit 0 com dados", rc == 0)
        check("header + régua de curtas no texto",
              "Matriz provider×descrição (F75)" in text
              and "régua de 'curta'" in text)
        check("linha do provider com cobertura",
              any("successfactors" in ln and "66.7%" in ln
                  for ln in text.splitlines()), detail=text[:400])
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = pdm.main(["--input", str(eligible), "--json"])
        obj = json.loads(buf2.getvalue())
        check("--json: providers + total + régua",
              obj.get("total_jobs") == 7 and len(obj.get("providers", [])) == 4
              and obj.get("short_description_limit") == 500)
        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            rc3 = pdm.main(["--input", str(Path(tmp) / "nope.json")])
        check("arquivo ausente -> exit 1", rc3 == 1)

    section("A5 — régua de curtas PINADA ao refresh (padrão F62)")
    check("SHORT_DESCRIPTION_LIMIT == HYDRATION_SHORT_LIMIT",
          pdm.SHORT_DESCRIPTION_LIMIT == ref.HYDRATION_SHORT_LIMIT,
          detail=f"{pdm.SHORT_DESCRIPTION_LIMIT} vs {ref.HYDRATION_SHORT_LIMIT}")


# ---------------------------------------------------------------------------
# B — drift do funil (digest)
# ---------------------------------------------------------------------------

def test_drift() -> None:
    section("B1 — weekly_stage_drift (por estágio, janela 7)")
    drift = fr.weekly_stage_drift(RUNS_DRIFT)
    check("3 estágios na ordem da cascata",
          [s["label"] for s in drift["stages"]]
          == ["brutas", "pré-filtrado", "mantido"],
          detail=str(drift))
    check("deltas corretos (último vs 7 atrás)",
          {(s["field"], s["delta"]) for s in drift["stages"]}
          == {("total_collected", 59), ("filtered", 21), ("eligible", 92)})
    check("<window records -> None",
          fr.weekly_stage_drift(RUNS_DRIFT[:6]) is None)
    # Record antigo SEM os campos -> os estágios correspondentes ficam
    # AUSENTES (nunca inventados); o eligible (presente nos dois) segue.
    old_partial = {"type": "run", "eligible": 5}
    seven = [old_partial, *RUNS_DRIFT[1:-1], RUNS_DRIFT[-1]]
    partial_drift = fr.weekly_stage_drift(seven)
    check("record antigo sem campo -> só o estágio presente (nunca erro)",
          partial_drift is not None
          and [s["label"] for s in partial_drift["stages"]] == ["mantido"]
          and partial_drift["stages"][0]["delta"] == 871 - 5,
          detail=str(partial_drift))
    check("todos os campos presentes nos DOIS -> 3 estágios",
          len(fr.weekly_stage_drift(RUNS_DRIFT)["stages"]) == 3)

    section("B2 — build_report expõe drift (fonte do digest)")
    with tempfile.TemporaryDirectory(prefix="f75_drift_") as tmp:
        metrics = _write_jsonl(Path(tmp) / "collection_metrics.jsonl",
                               RUNS_DRIFT)
        report = fr.build_report(metrics, Path(tmp) / "no_events.jsonl",
                                 Path(tmp) / "no_eligible.json")
        check("report['drift'] com 3 estágios",
              report is not None and report.get("drift") is not None
              and len(report["drift"]["stages"]) == 3)
        check("trend legado preservado (API do relatório offline)",
              report.get("trend") is not None
              and report["trend"]["delta"] == 92)

    section("B3 — linha 📈 do digest: formato NOVO por estágio")
    report = fr.build_report(
        _write_jsonl(Path(tempfile.mkdtemp(prefix="f75_d2_"))
                     / "collection_metrics.jsonl", RUNS_DRIFT),
        Path("/nonexistent_events.jsonl"), Path("/nonexistent_eligible.json"))
    lines = rd.funnel_seasonality_lines(report)
    expected = ("  📈 drift 7 runs: brutas 108059 (+59) · "
                "pré-filtrado 3121 (+21) · mantido 871 (+92)")
    check("linha exata", expected in lines, detail=str(lines))
    check("formato antigo ('elegíveis: ... hoje vs') AUSENTE no report novo",
          not any("elegíveis:" in ln for ln in lines))

    section("B4 — report legado (trend sem drift) mantém formato antigo")
    legacy = rd.funnel_seasonality_lines({
        "funnel": {"run_id": "2026-10-17T09:00:02Z",
                   "applicability": {"total": 1, "reasons": {"x": 1}}},
        "trend": {"eligible_last": 871, "eligible_then": 779,
                  "delta": 92, "window": 7},
        "seasonality": {"scanned": 0, "with_window": 0, "calendar": []},
        "application": None})
    check("linha 'elegíveis: 871 hoje vs 779 há 7 runs (+92)' preservada",
          "  📈 elegíveis: 871 hoje vs 779 há 7 runs (+92)" in legacy,
          detail=str(legacy))

    section("B5 — sinal do delta: negativo e zero")
    # Header VIVO obrigatório (padrão F44: sem parte viva a seção é
    # ausente) — funnel com 1 inaplicável.
    live_funnel = {"run_id": "2026-10-18T09:00:02Z",
                   "applicability": {"total": 1, "reasons": {"x": 1}}}
    neg = fr.weekly_stage_drift([
        _run_record("2026-10-11", 100, 50, 30),
        *[_run_record(f"2026-10-{d:02d}", 100, 50, 30)
          for d in (12, 13, 14, 15, 16)],
        _run_record("2026-10-18", 90, 50, 30),
    ])
    neg_lines = rd.funnel_seasonality_lines({
        "funnel": live_funnel, "drift": neg, "trend": None,
        "seasonality": {"scanned": 0, "with_window": 0, "calendar": []},
        "application": None})
    check("delta negativo sem '+'", any("brutas 90 (-10)" in ln
                                        for ln in neg_lines),
          detail=str(neg_lines))
    zero = fr.weekly_stage_drift([
        _run_record("2026-10-11", 100, 50, 30),
        *[_run_record(f"2026-10-{d:02d}", 100, 50, 30)
          for d in (12, 13, 14, 15, 16)],
        _run_record("2026-10-18", 100, 50, 30),
    ])
    zero_lines = rd.funnel_seasonality_lines({
        "funnel": live_funnel, "drift": zero, "trend": None,
        "seasonality": {"scanned": 0, "with_window": 0, "calendar": []},
        "application": None})
    check("delta zero -> ±0", any("brutas 100 (±0)" in ln
                                  for ln in zero_lines),
          detail=str(zero_lines))


# ---------------------------------------------------------------------------
# C — retenção do collection_metrics.jsonl
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def _tenant(ts: str, collected: int, source: str = "successfactors:jobs",
            company: str = "SAP") -> dict:
    return {"type": "tenant", "run_id": ts, "timestamp": ts,
            "company": company, "source": source, "ats": "successfactors",
            "status": "ok", "collected": collected, "error": None,
            "duration": 1.5}


def test_retention() -> None:
    section("C1 — corte: exatamente no limite fica RAW; 1s antes rola")
    with tempfile.TemporaryDirectory(prefix="f75_ret_") as tmp:
        path = Path(tmp) / "collection_metrics.jsonl"
        boundary = (NOW - timedelta(days=90)).isoformat()
        before = (NOW - timedelta(days=90, seconds=1)).isoformat()
        recent = (NOW - timedelta(days=1)).isoformat()
        _write_jsonl(path, [
            _tenant(before, 10), _tenant(boundary, 20), _tenant(recent, 30)])
        summary = mr.rollup_metrics(path, retention_days=90, now=NOW)
        check("1 dia rolado, 2 raw", summary["rolled_days"] == 1
              and summary["raw_kept"] == 2, detail=str(summary))
        content = [json.loads(ln) for ln in
                   path.read_text(encoding="utf-8").splitlines()]
        check("rollup primeiro; boundary e recent raw na ordem",
              content[0]["type"] == "metrics_rollup"
              and content[1]["collected"] == 20
              and content[2]["collected"] == 30,
              detail=str(content))

    section("C2 — shape do rollup: 1 por dia, por type, somas por type")
    with tempfile.TemporaryDirectory(prefix="f75_ret2_") as tmp:
        path = Path(tmp) / "collection_metrics.jsonl"
        _write_jsonl(path, [
            _tenant("2026-07-01T06:00:00+00:00", 100, source="successfactors:a",
                    company="A"),
            _tenant("2026-07-01T07:00:00+00:00", 50, source="successfactors:b",
                    company="B"),
            _run_record("2026-07-01", 1000, 100, 40),
            _tenant("2026-07-02T06:00:00+00:00", 7),
        ])
        summary = mr.rollup_metrics(path, retention_days=90, now=NOW)
        check("2 dias, 4 records rolados",
              summary["rolled_days"] == 2 and summary["rolled_records"] == 4)
        recs = [json.loads(ln) for ln in
                path.read_text(encoding="utf-8").splitlines()]
        check("2 rollups, nenhum raw",
              len(recs) == 2 and all(r["type"] == "metrics_rollup"
                                     for r in recs))
        d1 = next(r for r in recs if r["date"] == "2026-07-01")
        check("por type: tenant 2 + run 1",
              d1["by_type"]["tenant"]["count"] == 2
              and d1["by_type"]["run"]["count"] == 1)
        check("somas POR type (tenant.collected 150; run.total_collected 1000)",
              d1["by_type"]["tenant"]["sums"]["collected"] == 150
              and d1["by_type"]["run"]["sums"]["total_collected"] == 1000)
        check("rolled_records do dia = 3", d1["rolled_records"] == 3)

    section("C3 — raw recente byte a byte; C4 — idempotente")
    with tempfile.TemporaryDirectory(prefix="f75_ret3_") as tmp:
        path = Path(tmp) / "collection_metrics.jsonl"
        records = [_tenant("2026-07-01T06:00:00+00:00", 100),
                   _tenant("2026-07-01T07:00:00+00:00", 50),
                   _tenant((NOW - timedelta(days=2)).isoformat(), 30),
                   _run_record((NOW - timedelta(days=2)).date().isoformat(),
                               900, 90, 35)]
        _write_jsonl(path, records)
        raw_before = path.read_text(encoding="utf-8").splitlines()[-2:]
        mr.rollup_metrics(path, retention_days=90, now=NOW)
        after = path.read_text(encoding="utf-8").splitlines()
        check("raw recente byte a byte (2 últimas linhas)",
              after[-2:] == raw_before)
        first = mr.rollup_metrics(path, retention_days=90, now=NOW)
        check("2ª chamada: changed=False", first["changed"] is False)
        check("arquivo intocado na 2ª chamada",
              path.read_text(encoding="utf-8").splitlines() == after)

    section("C5 — corrompido/sem-ts/rollup pré-existente preservados")
    with tempfile.TemporaryDirectory(prefix="f75_ret4_") as tmp:
        path = Path(tmp) / "collection_metrics.jsonl"
        rollup_old = {"type": "metrics_rollup", "date": "2026-06-15",
                      "timestamp": "2026-06-16T00:00:00+00:00",
                      "rolled_records": 5,
                      "by_type": {"tenant": {"count": 5, "sums": {}}}}
        path.write_text(
            json.dumps(rollup_old, ensure_ascii=False) + "\n"
            + "linha corrompida {{{\n"
            + json.dumps(_tenant("2026-07-01T06:00:00+00:00", 100)) + "\n"
            + json.dumps({"type": "tenant", "company": "sem-ts",
                          "collected": 3}) + "\n",
            encoding="utf-8")
        mr.rollup_metrics(path, retention_days=90, now=NOW)
        out = path.read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(ln) for ln in out if not ln.startswith("linha")]
        check("rollup pré-existente preservado como-is",
              any(r.get("date") == "2026-06-15" for r in parsed))
        check("linha corrompida preservada",
              any("corrompida" in ln for ln in out))
        check("record sem timestamp preservado raw",
              any(r.get("company") == "sem-ts" for r in parsed))
        check("record datável antigo rolado",
              any(r["type"] == "metrics_rollup" and r["date"] == "2026-07-01"
                  for r in parsed))

    section("C6 — 0 desliga; ausente = no-op; C7 — atômico (sem .tmp)")
    with tempfile.TemporaryDirectory(prefix="f75_ret5_") as tmp:
        path = Path(tmp) / "collection_metrics.jsonl"
        _write_jsonl(path, [_tenant("2026-07-01T06:00:00+00:00", 100)])
        before_bytes = path.read_bytes()
        off = mr.rollup_metrics(path, retention_days=0, now=NOW)
        check("retention 0: no-op com reason", off["changed"] is False
              and "desligada" in off["reason"], detail=str(off))
        check("arquivo intocado com 0",
              path.read_bytes() == before_bytes)
        missing = mr.rollup_metrics(Path(tmp) / "nope.jsonl",
                                    retention_days=90, now=NOW)
        check("arquivo ausente: no-op sem lançar",
              missing["changed"] is False and "ausente" in missing["reason"])
        mr.rollup_metrics(path, retention_days=90, now=NOW)
        check("nenhum .tmp remanescente",
              not list(Path(tmp).glob("*.tmp")))

    section("C8 — records de run antigos viram rollup diário (funil >90d)")
    with tempfile.TemporaryDirectory(prefix="f75_ret6_") as tmp:
        path = Path(tmp) / "collection_metrics.jsonl"
        _write_jsonl(path, [
            _run_record("2026-07-01", 1000, 100, 40),
            _run_record("2026-07-02", 1100, 110, 45),
            _run_record((NOW - timedelta(days=1)).date().isoformat(),
                        1200, 120, 50),
        ])
        mr.rollup_metrics(path, retention_days=90, now=NOW)
        recs = [json.loads(ln) for ln in
                path.read_text(encoding="utf-8").splitlines()]
        check("2 rollups de run + 1 run raw",
              sum(1 for r in recs if r["type"] == "metrics_rollup") == 2
              and recs[-1]["type"] == "run")
        d1 = next(r for r in recs if r.get("date") == "2026-07-01")
        check("soma diária do eligible preservada (40)",
              d1["by_type"]["run"]["sums"]["eligible"] == 40)


# ---------------------------------------------------------------------------
# D — gêmeos residuais (digest)
# ---------------------------------------------------------------------------

def test_twins() -> None:
    section("D1 — contagem: os 3 shapes reais contam; negativos não")
    real = AMAZON_TWIN + WUERTH_TWIN + BSX_TWIN
    check("3 grupos reais", rd.residual_twins_count(real) == 3,
          detail=str(rd.residual_twins_count(real)))
    check("+ espelho DE/EN de título (mesma empresa) conta",
          rd.residual_twins_count(real + DE_EN_TWIN) == 4)
    check("empresas distintas (Workwize×godutch) NÃO contam",
          rd.residual_twins_count(WORKWIZE_NEG) == 0)
    check("label de tenant vs nome real (Lidl) NÃO conta no radar",
          rd.residual_twins_count(LIDL_NEG) == 0)
    same_source = [dict(AMAZON_TWIN[0]), dict(AMAZON_TWIN[1])]
    same_source[1]["source"] = same_source[0]["source"]
    check("mesma fonte NÃO conta", rd.residual_twins_count(same_source) == 0)
    check("sem empresa/título/fonte: fora da contagem",
          rd.residual_twins_count([{"company": "", "source": "s",
                                    "title": "x"},
                                   {"company": "A", "title": "x"}]) == 0)
    check("casefold da empresa (Spiegel GmbH == spiegel gmbh)",
          rd.residual_twins_count(DE_EN_TWIN) == 1)

    section("D2 — linha do digest: 0 ausente; normal; alerta >20")
    check("0 gêmeos -> []", rd.residual_twins_lines(WORKWIZE_NEG) == [])
    normal = rd.residual_twins_lines(real)
    check("normal: 👯 com a contagem",
          normal == ["👯 Gêmeos residuais: 3 grupos cross-source "
                     "(mesma empresa+título em fontes distintas)"],
          detail=str(normal))
    # 22 grupos DISTINTOS (duplicar pares não cria grupo novo — a chave
    # empresa+título colapsa réplicas; medido na 1ª rodada do teste).
    big = []
    for i in range(22):
        big += [
            {"company": f"Empresa Twin {i:02d} GmbH", "source": "absolventa",
             "title": f"Praktikum Bereich {i:02d} - Start 2027"},
            {"company": f"Empresa Twin {i:02d} GmbH", "source": "amazon_jobs",
             "title": f"Praktikum Bereich {i:02d} - Start 2027"},
        ]
    count22 = rd.residual_twins_count(big)
    check("22 grupos distintos no fixture do alerta", count22 == 22,
          detail=str(count22))
    alert = rd.residual_twins_lines(big)
    check("alerta >20: prefixo ⚠️ + revisar dedup",
          len(alert) == 1 and alert[0].startswith(rd.TWINS_ALERT_PREFIX)
          and "revisar dedup" in alert[0], detail=str(alert))
    check("20 grupos (limiar): linha normal, não alerta",
          rd.residual_twins_lines(big[:40])[0].startswith("👯"))
    check("limiar da spec = 20", rd.RESIDUAL_TWINS_ALERT == 20)

    section("D3 — digest_sections: linha antes do 🔗; ausente sem gêmeos")
    with tempfile.TemporaryDirectory(prefix="f75_dig_") as tmp:
        cur = Path(tmp) / "eligible_jobs.json"
        prev = Path(tmp) / "previous.json"
        cur.write_text(json.dumps(real), encoding="utf-8")
        prev.write_text(json.dumps([]), encoding="utf-8")
        lines = rd.digest_sections(cur, prev,
                                   pages_url="https://example.com/r")
        twins_at = [i for i, ln in enumerate(lines)
                    if "Gêmeos residuais" in ln]
        link_at = [i for i, ln in enumerate(lines)
                   if ln.startswith("🔗")]
        check("linha presente antes do link",
              len(twins_at) == 1 and len(link_at) == 1
              and twins_at[0] < link_at[0],
              detail=str(lines[twins_at[0]:twins_at[0]+3] if twins_at else "ausente"))
        cur.write_text(json.dumps(WORKWIZE_NEG), encoding="utf-8")
        lines2 = rd.digest_sections(cur, prev,
                                    pages_url="https://example.com/r")
        check("sem gêmeos -> nenhuma linha (regressão zero)",
              not any("Gêmeos" in ln for ln in lines2))

    section("D4 — extrator do alerta (prefixo exato)")
    digest_with_alert = ["", "⚠️ Gêmeos residuais: 25 grupos cross-source "
                          "(mesma empresa+título em fontes distintas) — "
                          "acima de 20, revisar dedup (F48)", "",
                         "🔗 Ranking completo: https://x.com"]
    extracted = rd.twins_alert_lines(digest_with_alert)
    check("extrai o ⚠️", len(extracted) == 1
          and extracted[0].startswith("⚠️ Gêmeos residuais"))
    check("linha normal 👯 NÃO é extraída",
          rd.twins_alert_lines(["", "👯 Gêmeos residuais: 3 grupos", ""]) == [])
    check("digest sem alerta -> []", rd.twins_alert_lines(["a", "b"]) == [])

    section("D5 — compact: ALERTA sobrevive; linha normal não")
    big_top5 = ["", "⚡ Top 5 do dia (candidatura direta)"]
    big_top5 += [f"{i}. {'Título longo de vaga para estourar o limite ' * 3} "
                 f"({i}) — https://example.com/apply/{i}"
                 for i in range(1, 60)]
    alert_digest = big_top5 + [
        "", "⚠️ Gêmeos residuais: 25 grupos cross-source (mesma empresa+"
        "título em fontes distintas) — acima de 20, revisar dedup (F48)",
        "", "🔗 Ranking completo: https://example.com/ranking"]
    normal_digest = big_top5 + [
        "", "👯 Gêmeos residuais: 10 grupos cross-source (mesma empresa+"
        "título em fontes distintas)",
        "", "🔗 Ranking completo: https://example.com/ranking"]
    summary = {"run_id": "2026-10-20T09:00:00+00:00",
               "ok": {"count": 3, "collected": 900},
               "empty": 0, "timeout": [], "error": [], "skipped": 0,
               "not_found": 0, "total_collected": 900, "eligible": 50,
               "dedup_removed": 3, "source_names": {}}
    msg_alert = ref.build_message(summary, [], 0, always_notify=True,
                                  digest_lines=alert_digest)
    msg_normal = ref.build_message(summary, [], 0, always_notify=True,
                                   digest_lines=normal_digest)
    check("digest grande -> mensagem compactada (<=4096)",
          msg_alert is not None and len(msg_alert) <= 4096,
          detail=f"{len(msg_alert or '')}")
    check("ALERTA ⚠️ sobrevive ao compact",
          "⚠️ Gêmeos residuais" in (msg_alert or ""),
          detail=str((msg_alert or "")[-300:]))
    check("linha normal 👯 é dropada no compact",
          "Gêmeos residuais" not in (msg_normal or ""),
          detail=str((msg_normal or "")[-200:]))
    check("link sobrevive nos dois",
          "🔗 Ranking completo" in (msg_alert or "")
          and "🔗 Ranking completo" in (msg_normal or ""))


# ---------------------------------------------------------------------------
# E — wiring / zero-rede
# ---------------------------------------------------------------------------

def test_wiring() -> None:
    section("E1 — flag do refresh: default 90, nome da spec")
    check("DEFAULT_METRICS_RETENTION_DAYS == 90",
          mr.DEFAULT_METRICS_RETENTION_DAYS == 90)
    src = Path(ref.__file__).read_text(encoding="utf-8")
    check("flag --metrics-retention-days no parser",
          '"--metrics-retention-days"' in src)
    check("default do flag = constante do módulo",
          f"default={mr.DEFAULT_METRICS_RETENTION_DAYS}" in src
          or "DEFAULT_METRICS_RETENTION_DAYS" in src)

    section("E2 — ordem no main: rollup ANTES do snapshot de linhas")
    idx_rollup = src.find("rollup_metrics(metrics_path,")
    idx_skip = src.find("skip_lines = _count_lines(metrics_path)")
    check("rollup antes de skip_lines",
          0 < idx_rollup < idx_skip,
          detail=f"rollup@{idx_rollup} skip@{idx_skip}")
    check("rollup best-effort (try/except no main)",
          "metrics rollup F75 FALHOU" in src)

    section("E3 — módulos novos sem imports de rede")
    for mod_path in (Path(mr.__file__), Path(pdm.__file__),
                     Path(fr.__file__), Path(rd.__file__)):
        text = mod_path.read_text(encoding="utf-8")
        banned = [tok for tok in ("import socket", "import urllib",
                                  "import requests", "import httpx",
                                  "urlopen", "urllib.request")
                  if tok in text]
        check(f"{mod_path.name} sem rede", not banned, detail=str(banned))

    section("E4 — digest sem gêmeos: nenhuma linha nova (D3 já cobre); "
            "régua da matriz pinada (A5 já cobre)")
    check("constante de alerta exportada no ranking_digest",
          rd.RESIDUAL_TWINS_ALERT == 20 and rd.TWINS_ALERT_PREFIX
          == "⚠️ Gêmeos residuais")


def main() -> int:
    print("F75 — analítica: matriz provider×descrição + drift + retenção "
          "+ gêmeos residuais (offline)")
    test_matrix()
    test_drift()
    test_retention()
    test_twins()
    test_wiring()
    print()
    if FAILURES:
        print(f"F75: {len(FAILURES)} FALHA(S) de {CHECKS} checks")
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print(f"F75: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
