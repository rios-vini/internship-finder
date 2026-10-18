"""Testes da Fase F45 — funil com motivo de morte + parser de sazonalidade (100% offline).

F45 em uma linha: o dono quer ver ONDE as vagas morrem no pipeline (e as
candidaturas nos desfechos) e QUANDO os estágios começam (semestres
alemães + janelas de datas) — a seção 📅 do digest carrega isso, alimentada
por um relatório offline determinístico (``funnel_report.py``) e um parser
puro (``seasonality.py``).

Contratos testados:

- A (parser PURO): semestres SoSe/SS/WiSe/WS (abreviação EXIGE ano —
  "wise choice" é palavra/empresa, não semestre); inícios ab/starting/from/
  à partir de/dès + mês-ano EN/DE/FR, datas numéricas (DE pontos, ISO —
  sempre COM prefixo); extensão por duração (für 6 Monate — caso real
  Daimler Buses) e zum; ranges YMY/MMY/DMY ("1 July 2027 – June 30th
  2028" — caso real Bosch Breda; "June 30" NUNCA vira ano 30); negativos
  (AWS, sofortige, "Bewerbung bis <data>" — deadline não é sazonalidade);
  canônico: semester > range > start > imediato; determinismo.
- B (funil): escada collected→filtered→dedup→inaplicáveis→eligible com
  os MOTIVOS de morte do record ``type: run`` REAL da produção; identidade
  aritmética VERIFICADA (residual quando não fecha — nunca assert); trend
  semanal (7 runs, endpoints reais 779→871); cauda F41 via a MESMA API do
  application_log; loaders defensivos; determinismo; CLI exit codes.
- C (seção 📅): header ÚNICO carrega contagens vivas (zeradas não
  aparecem); cap 5 + "(+N outros)"; blocos ausentes quando o dado falta;
  extrator por PREFIXO EXATO; loader best-effort; pureza (sem I/O no
  formatador).
- D (compact): réplica CONGELADA da cadeia pré-F45 (fórmula do e0d75c2 —
  lição do PR #145: baseline com SHA fixo, nunca main móvel) — sem a
  seção 📅, a mensagem é IGUAL byte a byte à pré-F45 em todos os níveis
  (1/2/3); COM a seção: 📅 colapsa DEPOIS da ⏰ Intel (spec "sua seção
  semanal entra depois disso"), exibe DEPOIS da ⏰ Follow-up, header com
  contagens sobrevive em TODOS os níveis, nunca é dropada inteira,
  nenhum bloco em branco duplicado.
- E (wiring/zero-rede): o refresh chama o loader com as 3 fontes e faz o
  splice ANTES do link (ordem F44 "⏰ Intel imediatamente antes da 📌
  Follow-up" preservada); seasonality/funnel_report sem imports de rede e
  sem escrita em arquivo; sockets bloqueados em runtime -> tudo passa.

Fixtures VERBATIM: record run REAL da produção (2026-10-17, 12 motivos
medidos), eventos no schema EXATO do log F41, títulos REAIS do eligible
(TRUMPF "SS 2027", AGCO "SoSe 2027", Daimler "ab März 2027 für 6 Monate",
Amazon "von Januar bis Juli 2027", adidas "March 2027 – September 2027",
Bosch "1 July 2027 – June 30th 2028") — texto real, zero invenção.

Uso:  python scripts/test_f45.py   (CI: exit 0 = verde)
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import funnel_report as fr  # noqa: E402
import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402
import seasonality as sea  # noqa: E402

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


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (produção, lidas ao vivo em 18/10 — números reais)
# ---------------------------------------------------------------------------

# Record ``type: run`` REAL do último cron (2026-10-17 09:00 UTC): os
# contadores de morte são os medidos (12 motivos; soma 2.134).
RUN_TODAY = {
    "type": "run",
    "run_id": "2026-10-17T09:00:02.925663+00:00",
    "timestamp": "2026-10-17T09:37:39.187626+00:00",
    "total_collected": 108059,
    "filtered": 3121,
    "dedup_removed": 116,
    "eligible": 871,
    "applicability_excluded_german_required": 1189,
    "applicability_excluded_visa_blocked": 66,
    "applicability_excluded_thesis_title": 65,
    "applicability_excluded_werkstudent_puro": 705,
    "applicability_excluded_master_required": 43,
    "applicability_excluded_eu_citizenship_required": 24,
    "applicability_excluded_nl_enrolment_required": 22,
    "applicability_excluded_phd_position": 2,
    "applicability_excluded_duration_over_6m": 2,
    "applicability_excluded_full_time_permanent": 0,
    "applicability_excluded_erasmus_program": 11,
    "applicability_excluded_spontaneous_pool": 5,
}

# Série semanal: endpoints REAIS (779 no run de 7 dias atrás, 871 hoje —
# medidos no JSONL de produção); intermediários plausíveis — o trend é
# aritmética sobre records, não cópia.


def _run_day(day: str, eligible: int) -> dict:
    return {
        "type": "run",
        "run_id": f"{day}T09:00:02+00:00",
        "timestamp": f"{day}T09:38:00+00:00",
        "total_collected": 108000,
        "filtered": 3100,
        "dedup_removed": 100,
        "eligible": eligible,
        "applicability_excluded_german_required": 1100,
    }


RUNS_WEEK = [
    _run_day("2026-10-11", 779),
    _run_day("2026-10-12", 790),
    _run_day("2026-10-13", 801),
    _run_day("2026-10-14", 815),
    _run_day("2026-10-15", 830),
    _run_day("2026-10-16", 806),
    RUN_TODAY,
]

# Eventos no schema EXATO do log F41 (message_id/ts/job_id/company/
# event_type/source — ids dos exemplos do relatório da F41).
EVENTS_F41 = [
    {"message_id": "tg:501", "ts": "2026-10-15T12:34:56Z",
     "job_id": "BMW AG|successfactors:jobs:111", "company": "BMW AG",
     "event_type": "applied", "source": "telegram"},
    {"message_id": "tg:502", "ts": "2026-10-16T10:00:00Z",
     "job_id": "BMW AG|successfactors:jobs:111", "company": "BMW AG",
     "event_type": "interview", "source": "telegram"},
    {"message_id": "tg:503", "ts": "2026-10-16T14:00:00Z",
     "job_id": "SAP|successfactors:jobs:222", "company": "SAP",
     "event_type": "applied", "source": "telegram"},
    {"message_id": "cli:SAP|successfactors:jobs:222:rejected:2026-10-17",
     "ts": "2026-10-17T09:00:00Z",
     "job_id": "SAP|successfactors:jobs:222", "company": "SAP",
     "event_type": "rejected", "source": "cli"},
    {"message_id": "tg:504", "ts": "2026-10-17T11:00:00Z",
     "job_id": "STIHL|workday:STIHL_Students:R0", "company": "STIHL",
     "event_type": "applied", "source": "telegram"},
]


def _job(jid: str, title: str, company: str, desc: str = "") -> dict:
    return {"id": jid, "title": title, "company": company,
            "location": "Berlin, Deutschland", "country_iso": "de",
            "score": 10.0, "url": "https://jobs.example.com/j",
            "description": desc}


# Títulos/termos VERBATIM do eligible real (medição 18/10).
JOBS_FIXTURE = [
    _job("trumpf|workday:1",
         "Data Science / Big Data / Datenanalyse EUV (SS 2027)", "trumpf"),
    _job("agco|sf_dataset:successfactors:142480420",
         "Marketing / Big Data / Datenanalyse (SoSe 2027)", "AGCO"),
    _job("daimler|absolventa:13394473",
         "Praktikum in der After Sales Logistik (ab März 2027 für 6 Monate)",
         "Daimler Buses GmbH"),
    _job("amazon|amazon_jobs:1",
         "Praktikum Logistik — Praktikant:innen, die jederzeit von "
         "Januar bis Juli 2027 anfangen können", "Amazon"),
    _job("adidas|sf_dataset:successfactors:1442911533",
         "Internship Supply Chain — full duration from March 2027 – "
         "September 2027", "adidas"),
    _job("bosch|sf_dataset:smartrecruiters:744000153521190",
         "Working Student Breda — Details: Duration: 1 July 2027 – "
         "June 30th 2028; Level: Bachelor Student", "BoschGroup"),
    _job("aushilfe|x:2", "Studentische Aushilfe Einkauf (ab sofort)",
         "Sofort GmbH"),
    _job("prod|x:3", "Praktikum Produktion WS 2026/27 (m/w/d)",
         "Werk GmbH"),
    _job("plain|x:1", "Praktikum Einkauf (m/w/d)", "Ohne Fenster GmbH",
         "Beschaffung und supplier management."),
]


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n",
                    encoding="utf-8")
    return path


def _fixture_dir() -> tuple[Path, Path, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="f45_"))
    metrics = _write_jsonl(tmp / "collection_metrics.jsonl", RUNS_WEEK)
    events = _write_jsonl(tmp / "application_events.jsonl", EVENTS_F41)
    eligible = tmp / "eligible_jobs.json"
    eligible.write_text(json.dumps(JOBS_FIXTURE), encoding="utf-8")
    return metrics, events, eligible


# ---------------------------------------------------------------------------
# A — Parser PURO de sazonalidade
# ---------------------------------------------------------------------------


def test_semesters() -> None:
    section("A1 — semestres alemães (SoSe/SS/WiSe/WS)")
    can = sea.canonical_seasonality("Datenanalyse EUV (SS 2027)")
    check("SS 2027 -> Sommersemester 2027",
          bool(can) and can["kind"] == "semester"
          and can["semester"] == "sose" and can["start"] == "2027-04"
          and can["end"] == "2027-09" and can["year"] == 2027)
    can = sea.canonical_seasonality("Automation (SoSe 27)")
    check("SoSe 27 -> ano 2 dígitos -> 2027",
          bool(can) and can["start"] == "2027-04" and can["end"] == "2027-09")
    can = sea.canonical_seasonality("Werkstudent WiSe 2026/27")
    check("WiSe 2026/27 -> out/2026–mar/2027",
          bool(can) and can["semester"] == "wise"
          and can["start"] == "2026-10" and can["end"] == "2027-03")
    can = sea.canonical_seasonality("Praktikum im Wintersemester 2026/2027")
    check("Wintersemester 2026/2027 -> mesma janela",
          bool(can) and can["start"] == "2026-10" and can["end"] == "2027-03")
    can = sea.canonical_seasonality("WS 26/27 gesucht")
    check("WS 26/27 -> out/2026–mar/2027",
          bool(can) and can["semester"] == "wise" and can["start"] == "2026-10")
    can = sea.canonical_seasonality("zum Sommersemester")
    check("nome completo SEM ano -> semestre sem janela",
          bool(can) and can["kind"] == "semester"
          and can["start"] is None and can["year"] is None)
    check("abreviação SEM ano não casa ('a wise choice 2027' é inglês)",
          sea.canonical_seasonality("a wise choice 2027") is None)
    check("AWS 2027 (nuvem, não semestre) -> None",
          sea.canonical_seasonality("AWS 2027 cloud") is None)


def test_starts() -> None:
    section("A2 — inícios (ab/starting/from/à partir de/dès + datas)")
    cases = [
        ("ab März 2027", "2027-03"),
        ("ab dem 15. März 2027", "2027-03"),
        ("starting March 2027", "2027-03"),
        ("from June 2027", "2027-06"),
        ("à partir de mars 2027", "2027-03"),
        ("dès le 5 mars 2027", "2027-03"),
        ("ab 01.03.2027", "2027-03"),
        ("starting 2027-03-01", "2027-03"),
    ]
    for txt, start in cases:
        can = sea.canonical_seasonality(txt)
        check(f"{txt!r} -> start {start}",
              bool(can) and can["kind"] == "start" and can["start"] == start)
    check("data numérica SEM prefixo não é início (ambígua)",
          sea.canonical_seasonality("Termin war 01.03.2027") is None)
    can = sea.canonical_seasonality(
        "in der After Sales Logistik (ab März 2027 für 6 Monate)")
    check("duração 'für 6 Monate' estende o fim (caso Daimler real)",
          bool(can) and can["start"] == "2027-03" and can["end"] == "2027-08")
    can = sea.canonical_seasonality("ab März 2027 zum 30.06.2027")
    check("'zum <data>' fixa o fim",
          bool(can) and can["start"] == "2027-03" and can["end"] == "2027-06")
    can = sea.canonical_seasonality("ab sofort")
    check("'ab sofort' -> imediato (sem janela)",
          bool(can) and can["kind"] == "immediate" and can["start"] is None)


def test_ranges() -> None:
    section("A3 — janelas (ranges EN/DE/FR)")
    cases = [
        ("März 2027 bis Juni 2027", "2027-03", "2027-06"),
        ("März bis Juni 2027", "2027-03", "2027-06"),
        ("de janvier à juin 2027", "2027-01", "2027-06"),
        ("January-June 2027", "2027-01", "2027-06"),
        ("March 2027 – September 2027", "2027-03", "2027-09"),
        ("von Januar bis Juli 2027 anfangen", "2027-01", "2027-07"),
        ("Duration: 1 July 2027 – June 30th 2028; Level: Bachelor",
         "2027-07", "2028-06"),
        ("Duration: 1 July 2027 – June 30, 2028; Level: Bachelor",
         "2027-07", "2028-06"),
    ]
    for txt, start, end in cases:
        can = sea.canonical_seasonality(txt)
        check(f"{txt[:38]!r} -> {start}..{end}",
              bool(can) and can["kind"] == "range"
              and can["start"] == start and can["end"] == end)
    can = sea.canonical_seasonality("November bis Juni 2027")
    check("MMY atravessando o ano: ano no início, fim Y+1 (regra doc.)",
          bool(can) and can["start"] == "2027-11" and can["end"] == "2028-06")
    check("'June 30' (dia sem ano) NUNCA vira ano 30",
          sea.canonical_seasonality("Duration: March 2027 – June 30") is None)


def test_negatives_priority() -> None:
    section("A4 — negativos + prioridade do canônico")
    for txt in ("sofortige Einstellung", "Kraftwerksingenieur (m/w/d)",
                "Bewerbung bis 15. Januar 2027", "2026 start dates",
                "Gehalt: 2.000 € pro Monat"):
        check(f"negativo {txt[:30]!r}", sea.canonical_seasonality(txt) is None)
    can = sea.canonical_seasonality(
        "Praktikum (SoSe 2027) — Beginn ab März 2027 möglich")
    check("semestre VENCE início no mesmo texto",
          bool(can) and can["kind"] == "semester")
    can = sea.canonical_seasonality("ab März 2027 bis Juni 2027")
    check("range VENCE início (janela explícita)",
          bool(can) and can["kind"] == "range" and can["end"] == "2027-06")
    txt = "SoSe 2027 und ab sofort"
    check("determinismo: parse 2x igual",
          json.dumps(sea.parse_seasonality(txt)) ==
          json.dumps(sea.parse_seasonality(txt)))


def test_labels_calendar() -> None:
    section("A5 — rótulos e calendário")
    check("rótulo SoSe", sea.seasonality_label(
        {"kind": "semester", "semester": "sose", "year": 2027,
         "start": "2027-04", "end": "2027-09"})
        == "SoSe 2027 (abr–set/2027)")
    check("rótulo WiSe", sea.seasonality_label(
        {"kind": "semester", "semester": "wise", "year": 2026,
         "start": "2026-10", "end": "2027-03"})
        == "WiSe 2026/27 (out/26–mar/27)")
    check("rótulo range mesmo ano", sea.seasonality_label(
        {"kind": "range", "start": "2027-03", "end": "2027-06"})
        == "mar–jun/2027")
    check("rótulo range anos distintos", sea.seasonality_label(
        {"kind": "range", "start": "2026-11", "end": "2027-06"})
        == "nov/2026–jun/2027")
    check("rótulo início", sea.seasonality_label(
        {"kind": "start", "start": "2027-03", "end": None}) == "mar/2027")
    check("rótulo imediato", sea.seasonality_label(
        {"kind": "immediate"}) == "ab sofort")
    cal = sea.seasonality_calendar(
        ["(SoSe 2027)", "ab März 2027", "ab März 2027", "(WiSe 2026/27)",
         "ab sofort", ""])
    check("calendário agrega por rótulo e ordena (-count, label asc)",
          cal == [("mar/2027", 2), ("SoSe 2027 (abr–set/2027)", 1),
                  ("WiSe 2026/27 (out/26–mar/27)", 1), ("ab sofort", 1)],
          detail=str(cal))
    check("calendário: texto sem janela não conta",
          sea.seasonality_calendar(["nada", ""]) == [])


# ---------------------------------------------------------------------------
# B — funnel_report (funil + motivos de morte + trend + cauda F41)
# ---------------------------------------------------------------------------


def test_pipeline_funnel() -> None:
    section("B1 — funil do record run REAL (motivos de morte)")
    fun = fr.pipeline_funnel(RUN_TODAY)
    check("collected 108.059", fun["collected"] == 108059)
    check("filtered 3.121", fun["filtered"] == 3121)
    check("morte 'fora do recorte' = collected - filtered (104.938)",
          fun["out_of_scope"] == 104938)
    check("morte 'duplicata' 116", fun["dedup_removed"] == 116)
    check("inaplicáveis 2.134 em 12 motivos",
          fun["applicability"]["total"] == 2134
          and len(fun["applicability"]["reasons"]) == 12)
    check("german_required 1.189 (maior motivo)",
          fun["applicability"]["reasons"]["german_required"] == 1189)
    check("motivo zerado entra no total (full_time_permanent 0)",
          fun["applicability"]["reasons"].get("full_time_permanent") == 0)
    check("eligible 871", fun["eligible"] == 871)
    check("identidade aritmética FECHA -> residual ausente",
          fun["residual"] is None,
          detail=f"3121-116-2134={3121 - 116 - 2134}")
    broken = dict(RUN_TODAY)
    broken["eligible"] = 870
    fun2 = fr.pipeline_funnel(broken)
    check("identidade NÃO fecha -> residual honesto (+1, nunca assert)",
          fun2["residual"] == 1)


def test_labels_trend() -> None:
    section("B2 — rótulos de morte + trend semanal")
    check("rótulo PT german_required",
          fr.death_label("german_required") == "alemão exigido")
    check("rótulo PT erasmus_program",
          fr.death_label("erasmus_program") == "programa Erasmus+")
    check("motivo desconhecido -> chave crua (fase futura não quebra)",
          fr.death_label("future_thing") == "future_thing")
    trend = fr.weekly_trend(RUNS_WEEK)
    check("trend 871 vs 779 (+92) em janela de 7",
          trend == {"eligible_last": 871, "eligible_then": 779,
                    "delta": 92, "window": 7})
    check("menos de 7 runs -> trend ausente (nunca inventado)",
          fr.weekly_trend(RUNS_WEEK[:6]) is None)


def test_application_and_report() -> None:
    section("B3 — cauda F41 (log de candidaturas) + relatório completo")
    app = fr.application_funnel(EVENTS_F41)
    check("5 eventos em 3 vagas", app["events"] == 5 and app["jobs"] == 3)
    check("by_type: applied 3 · interview 1 · rejected 1",
          app["by_type"] == {"applied": 3, "interview": 1, "rejected": 1})
    check("status final via rebuild_status REAL (F41): "
          "applied/interview/rejected 1 cada",
          app["status_counts"] == {"applied": 1, "interview": 1,
                                   "rejected": 1})
    check("sem eventos -> cauda ausente (produção hoje)",
          fr.application_funnel([]) is None)

    metrics, events, eligible = _fixture_dir()
    report = fr.build_report(metrics, events, eligible)
    assert report is not None
    check("report: funil do último run (871)", report["funnel"]["eligible"] == 871)
    check("report: superfície/ranked = 9 vagas, best = min(30, 9)",
          report["surface"] == 9 and report["ranked"] == 9
          and report["best"] == 9)
    check("report: trend presente", bool(report["trend"]))
    check("report: cauda F41 presente", bool(report["application"]))
    sea_r = report["seasonality"]
    check("sazonalidade: 8 de 9 vagas com janela (títulos VERBATIM)",
          sea_r["scanned"] == 9 and sea_r["with_window"] == 8,
          detail=str([(c["label"], c["count"]) for c in sea_r["calendar"]]))
    labels = [c["label"] for c in sea_r["calendar"]]
    check("calendário contém os 5 rótulos esperados dos títulos reais",
          "SoSe 2027 (abr–set/2027)" in labels
          and "mar/2027" in labels and "jan–jul/2027" in labels
          and "mar–set/2027" in labels and "jul/2027–jun/2028" in labels)
    check("SoSe conta TRUMPF(SS)+AGCO(SoSe) = 2 no mesmo rótulo",
          next(c["count"] for c in sea_r["calendar"]
               if c["label"].startswith("SoSe")) == 2)

    # determinismo: mesmo report byte a byte
    report2 = fr.build_report(metrics, events, eligible)
    check("determinismo: build_report 2x -> JSON idêntico",
          json.dumps(report, sort_keys=True) == json.dumps(report2,
                                                           sort_keys=True))

    # loaders defensivos
    tmp = Path(tempfile.mkdtemp(prefix="f45b_"))
    corrupt = tmp / "metrics.jsonl"
    corrupt.write_text("{json invalido\n\n" + json.dumps(RUN_TODAY) + "\n",
                       encoding="utf-8")
    runs = fr.load_run_records(corrupt)
    check("JSONL com linha corrompida: ignora a linha, lê o record são",
          len(runs) == 1 and runs[0]["eligible"] == 871)
    check("arquivo ausente -> [] (nunca lança)",
          fr.load_run_records(tmp / "nao_existe.jsonl") == []
          and fr.load_eligible_jobs(tmp / "nao_existe.jsonl") == [])
    check("build_report sem NENHUMA fonte -> None",
          fr.build_report(tmp / "a.jsonl", tmp / "b.jsonl",
                          tmp / "c.jsonl") is None)
    only_eligible = fr.build_report(tmp / "a.jsonl", tmp / "b.jsonl",
                                    eligible)
    check("só eligible -> report existe com funil ausente (gracioso)",
          only_eligible is not None and only_eligible["funnel"] is None)


def test_cli() -> None:
    section("B4 — CLI (exit codes; stdout)")
    metrics, events, eligible = _fixture_dir()
    check("CLI com dados -> rc 0", fr.main(
        ["--metrics", str(metrics), "--events", str(events),
         "--eligible", str(eligible)]) == 0)
    check("CLI --json -> rc 0", fr.main(
        ["--metrics", str(metrics), "--eligible", str(eligible),
         "--json"]) == 0)
    check("CLI sem fontes -> rc 1", fr.main(
        ["--metrics", "/tmp/f45_nada.jsonl", "--events",
         "/tmp/f45_nada.jsonl", "--eligible", "/tmp/f45_nada.jsonl"]) == 1)


def test_format_report() -> None:
    section("B5 — format_report (ladder de texto)")
    metrics, events, eligible = _fixture_dir()
    report = fr.build_report(metrics, events, eligible)
    text = "\n".join(fr.format_report(report))
    check("escada contém as 4 etapas",
          all(k in text for k in ("collected:", "filtered:", "eligible:",
                                  "ranked:", "best:")))
    check("mortes nomeadas por etapa",
          "fora do recorte" in text and "duplicata" in text
          and "inaplicável" in text)
    check("motivo de morte com rótulo PT + chave crua",
          "alemão exigido (german_required): 1.189" in text)
    check("trend na ordem dos runs",
          "871 hoje vs 779 há 7 runs (+92)" in text)
    check("candidaturas com desfechos na ordem canônica",
          "aplicadas 3, entrevista 1, rejeitadas 1" in text)
    check("sazonalidade com contagem",
          "8 de 9 vagas com janela de início detectada" in text)
    empty = fr.format_report(None)
    check("report None -> '(sem dados)' sem lançar", empty == ["(sem dados)"])


# ---------------------------------------------------------------------------
# C — Seção 📅 do digest
# ---------------------------------------------------------------------------


def test_section_format() -> None:
    section("C1 — funnel_seasonality_lines (header carrega contagens)")
    metrics, events, eligible = _fixture_dir()
    report = fr.build_report(metrics, events, eligible)
    lines = rg.funnel_seasonality_lines(report)
    check("header único com dia do run + contagens vivas",
          lines[0] == "📅 Funil & sazonalidade (último run 17/10) — "
          "2.134 inaplicáveis; 8 vagas com janela de início",
          detail=lines[0])
    check("✂ motivos cap 5 (+N outros; motivo zerado fica fora do corpo)",
          lines[1].startswith("  ✂ alemão exigido: 1.189")
          and "(+6 outros motivos)" in lines[1], detail=lines[1])
    check("📈 trend", any(l.startswith("  📈 elegíveis: 871 hoje vs 779")
                          for l in lines))
    check("📆 calendário cap 5 + (+N outras)",
          any(l.startswith("  📆 ") and "outras janelas" in l
              for l in lines))
    check("📌 candidaturas F41", any("candidaturas (log F41): 5 eventos"
                                     in l for l in lines))

    # partes zeradas/ausentes não aparecem (padrão F44)
    zero = rg.funnel_seasonality_lines({
        "funnel": {"run_id": "2026-10-17T09:00:02Z",
                   "applicability": {"total": 0, "reasons": {}}},
        "seasonality": {"scanned": 0, "with_window": 0, "calendar": []},
        "application": None, "trend": None})
    check("sem dados vivos -> seção AUSENTE ([])", zero == [])
    only_app = rg.funnel_seasonality_lines({
        "funnel": None, "trend": None,
        "seasonality": {"scanned": 0, "with_window": 0, "calendar": []},
        "application": {"events": 3, "jobs": 2,
                         "by_type": {"applied": 3}, "status_counts": {}}})
    check("só cauda F41 viva -> header sem contagens de funil",
          len(only_app) == 2 and only_app[0] == rg.FUNNEL_SECTION_PREFIX
          and "candidaturas" in only_app[1], detail=str(only_app))
    no_cal = rg.funnel_seasonality_lines({
        "funnel": {"run_id": "2026-10-17T09:00:02Z",
                   "applicability": {"total": 10,
                                     "reasons": {"german_required": 10}}},
        "trend": None,
        "seasonality": {"scanned": 5, "with_window": 0, "calendar": []},
        "application": None})
    check("sem janelas -> sem linha 📆 e sem contagem no header",
          len(no_cal) == 2 and "📆" not in no_cal[1]
          and "janela" not in no_cal[0])
    check("report None -> []", rg.funnel_seasonality_lines(None) == [])


def test_section_extractors() -> None:
    section("C2 — extrator + prefixo + loader (contrato do compact)")
    check("prefixo == início do header emitido (padrão test_f61/F44)",
          rg.FUNNEL_SECTION_PREFIX.startswith("📅")
          and "Funil" in rg.FUNNEL_SECTION_PREFIX)
    metrics, events, eligible = _fixture_dir()
    lines = rg.funnel_seasonality_section(metrics, events, eligible)
    check("loader monta a seção (I/O só nele)", len(lines) >= 4)
    digest = ["", "⚡ Top 5 do dia (candidatura direta)", "  1. vaga"]
    digest += ["", "", ] + lines + ["", "🔗 Ranking completo: https://x"]
    check("extrator acha header+corpo até o blank",
          rg.funnel_section_lines(digest) == lines)
    check("extrator ausente -> []",
          rg.funnel_section_lines(["a", "🔗 b"]) == [])
    check("loader sem fontes -> [] (seção ausente, nunca erro)",
          rg.funnel_seasonality_section("/tmp/f45_nada.jsonl",
                                        "/tmp/f45_nada.jsonl",
                                        "/tmp/f45_nada.jsonl") == [])
    # pureza do formatador: nenhum open() no corpo da função (I/O é do loader)
    src = Path(rg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == "funnel_seasonality_lines")
    check("formatador PURO: sem open()/leitura no corpo",
          not any(isinstance(n, ast.Call) and (
              (isinstance(n.func, ast.Name) and n.func.id == "open")
              or (isinstance(n.func, ast.Attribute)
                  and n.func.attr in ("read_text", "write_text", "open")))
              for n in ast.walk(fn)))


# ---------------------------------------------------------------------------
# D — Compact do Telegram: A/B contra a fórmula pré-F45 CONGELADA (e0d75c2)
# ---------------------------------------------------------------------------


def _summary(*, eligible: int = 50, total: int = 400,
             errors: list | None = None) -> dict:
    return {"run_id": "2026-10-18T09:00:00Z",
            "ok": {"count": 10, "collected": total},
            "total_collected": total, "eligible": eligible,
            "dedup_removed": 1, "empty": 0, "skipped": 0, "not_found": 0,
            "timeout": [], "error": errors or [], "source_names": {}}


def _mk_digest(*, with_fn: bool, fat: int = 0, with_sections: bool = True,
               fn_lines: list[str] | None = None) -> list[str]:
    """Digest sintético no LAYOUT real do digest montado (ordem das seções
    = ordem de exibição; blanks separam blocos)."""
    d: list[str] = ["", "Score do run: min 3,1 · mediana 8,2 · máx 15,4"]
    if with_sections:
        d += ["", "🧪 Perfil Materials Engineering — 12 vagas",
              "  1. Firma Materials 1", "  2. Firma Materials 2"]
        d += ["", "🇪🇺 Perfil EU non-DE — 8 vagas", "  1. Firma EU 1"]
        d += ["", "🆕 Novas desde ontem: 18 vagas"]
        d += [f"  {i}. Nova vaga {i} — Empresa {i} — Berlin"
              + (" — texto gordo " + "x" * fat if fat else "")
              for i in range(1, 8)]
    d += ["", rg.TOP5_SECTION_HEADER]
    d += [f"  {i}. Título Top {i} — Empresa {i} — 14,5 — "
          f"https://jobs.example.com/apply/{i}" for i in range(1, 6)]
    if with_sections:
        d += ["", "🎯 Empresas-alvo (watchlist) — 3 nova(s)",
              "  🎯 Bosch: Werkstudent Einkauf (Stuttgart)",
              "  🎯 SAP: Praktikum Data (Walldorf)"]
        d += ["", "⏰ Intel de empresas (frescor do intel) — 12 >90d",
              "  🕰 1. Empresa Velha — checked 2026-06-10 (127d)",
              "  🕰 2. Outra Velha — checked 2026-06-11 (126d)"]
        d += ["", "⏰ Follow-up — candidaturas sem resposta — 4 pendente(s)",
              "  1. Daimler Buses GmbH — aplicada há 12 dias"]
        d += ["", "📌 3 aplicação(ões) aguardando resposta"]
    if with_fn:
        d += ["", *(fn_lines if fn_lines is not None else
                    [rg.FUNNEL_SECTION_PREFIX + " (último run 17/10) — "
                     "2.134 inaplicáveis; 6 vagas com janela",
                     "  ✂ alemão exigido: 1.189 · werkstudent puro: 705"
                     " · visto bloqueado: 66 · tese no título: 65"
                     " · mestrado exigido: 43 (+6 outros motivos)",
                     "  📈 elegíveis: 871 hoje vs 779 há 7 runs (+92)",
                     "  📆 jan–jul/2027: 48 · ab sofort: 37 · SoSe 2027: 17"
                     " · mar/2027: 5 (+2 outras janelas)"])]
    d += ["", "🔗 Ranking completo: https://example.com/ranking"]
    return d


def _base_of(summary: dict, errors: list | None) -> list[str]:
    """Base REAL da mensagem (build_message sem digest devolve a base pura)."""
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=None)
    assert msg is not None  # always_notify=True nunca devolve None
    return msg.split("\n")


def _summarized_of(base: list[str]) -> list[str]:
    """Base com o bloco de problemas colapsado em 1 contagem (fórmula F6.1
    N2 — reconstruída da base: header fica, itens viram contagem)."""
    if "⚠️ Problemas detectados:" not in base:
        return base
    start = base.index("⚠️ Problemas detectados:") + 1
    n = 0
    while start + n < len(base) and base[start + n].startswith("• "):
        n += 1
    return (base[:start] + [f"⚠️ {n} problemas (ver ranking)"]
            + base[start + n:])


def _pre_f45_compact(base: list[str], summarized: list[str],
                     digest_lines: list[str], max_len: int, *,
                     with_fn: bool) -> str:
    """Réplica CONGELADA da compactação (fórmula do e0d75c2, pré-F45).

    with_fn=False: cadeia 4-tuple original (in -> fu -> wl -> ns) — o
    gabarito A/B da regressão zero. with_fn=True: cadeia F45 (📅 colapsa
    depois da ⏰ Intel, exibe depois da ⏰ Follow-up). Nível 3 idêntico ao
    fonte. Qualquer mudança futura na cadeia quebra AQUI (a fórmula é o
    contrato, lição do PR #145: baseline congelado, nunca main móvel).
    """
    link = next((l for l in reversed(digest_lines) if l.startswith("🔗")),
                digest_lines[-1])
    top5 = rg.top5_section_lines(digest_lines)
    fallback = ("ℹ️ Resumo do ranking encurtado (mensagem longa) — "
                "ranking completo: " + link)
    # Guard do fonte real: digest que CABE inteiro é devolvido SEM
    # compactação (o bloco só roda quando estoura max_len).
    full_text = "\n".join(base + list(digest_lines))
    if len(full_text) <= max_len:
        return full_text
    if not top5:
        return "\n".join(base + ["", fallback])
    ns_full = rg.new_since_section_lines(digest_lines) or []
    wl_full = rg.watchlist_section_lines(digest_lines) or []
    prof = (rg.materials_section_lines(digest_lines)[:1]
            + rg.eu_section_lines(digest_lines)[:1])
    fu_full = rg.followup_section_lines(digest_lines) or []
    in_full = rg.intel_section_lines(digest_lines) or []
    fn_full = rg.funnel_section_lines(digest_lines) or []

    def fits(parts: list[str]) -> bool:
        return len("\n".join(parts)) <= max_len

    if with_fn:
        # cadeia F45 (5 flags: in -> fn -> fu -> wl -> ns)
        combos = ((False, False, False, False, False),
                  (True, False, False, False, False),
                  (True, True, False, False, False),
                  (True, True, True, False, False),
                  (True, True, True, True, False),
                  (True, True, True, True, True))
    else:
        # cadeia pré-F45 (4 flags in -> fu -> wl -> ns; fn sempre ausente)
        combos = ((False, False, False, False, False),
                  (True, False, False, False, False),
                  (True, False, True, False, False),
                  (True, False, True, True, False),
                  (True, False, True, True, True))
    variants: list[tuple[list[str], ...]] = []
    for in_c, fn_c, fu_c, wl_c, ns_c in combos:
        variants.append((
            [ns_full[0]] if ns_full and ns_c else ns_full,
            [wl_full[0]] if wl_full and wl_c else wl_full,
            [fu_full[0]] if fu_full and fu_c else fu_full,
            [in_full[0]] if in_full and in_c else in_full,
            [fn_full[0]] if fn_full and fn_c else fn_full))

    def assemble(head: list[str], ns_p, wl_p, fu_p, in_p, fn_p) -> list[str]:
        parts = head + [""]
        if prof:
            parts += prof + [""]
        if ns_p:
            parts += ns_p
        parts += top5
        if wl_p:
            parts += wl_p
        if in_p:
            parts += in_p
        if fu_p:
            parts += fu_p
        if fn_p:
            parts += fn_p
        parts += ["", link]
        return parts

    text = None
    for ns_p, wl_p, fu_p, in_p, fn_p in variants:
        parts = assemble(base, ns_p, wl_p, fu_p, in_p, fn_p)
        if fits(parts):
            text = "\n".join(parts)
            break
    if text is None:
        for ns_p, wl_p, fu_p, in_p, fn_p in variants:
            parts = assemble(summarized, ns_p, wl_p, fu_p, in_p, fn_p)
            if fits(parts):
                text = "\n".join(parts)
                break
    if text is None:
        ns_p = [ns_full[0]] if ns_full else []
        wl_p = [wl_full[0]] if wl_full else []
        fu_p = [fu_full[0]] if fu_full else []
        in_p = [in_full[0]] if in_full else []
        fn_p = [fn_full[0]] if fn_full else []
        prof_block = prof + [""] if prof else []
        kept = [top5[0]]
        for line in top5[1:]:
            candidate = (summarized + [""] + prof_block + ns_p + kept
                         + wl_p + in_p + fu_p + fn_p + [line] + ["", link])
            if len("\n".join(candidate)) > max_len:
                break
            kept.append(line)
        if len(kept) > 1:
            text = "\n".join(summarized + [""] + prof_block + ns_p + kept
                             + wl_p + in_p + fu_p + fn_p + ["", link])
        else:
            text = "\n".join(base + ["", fallback])
    return text


def _run_ab(digest: list[str], summary: dict, errors: list | None,
            *, with_fn: bool, max_len: int | None = None,
            label: str = "") -> tuple[str, str]:
    real_max = rd.TELEGRAM_MAX_LEN
    if max_len is not None:
        rd.TELEGRAM_MAX_LEN = max_len
    try:
        real = rd.build_message(summary, [], 0, always_notify=True,
                                digest_lines=digest)
        base = _base_of(summary, errors)
        summarized = _summarized_of(base)
        expected = _pre_f45_compact(base, summarized, digest,
                                    max_len or real_max, with_fn=with_fn)
    finally:
        rd.TELEGRAM_MAX_LEN = real_max
    assert real is not None  # always_notify=True nunca devolve None
    return real, expected


def test_compact_ab() -> None:
    section("D1 — A/B compact SEM 📅: regressão zero vs fórmula e0d75c2")
    cases = [
        ("digest médio (variant raso)", _mk_digest(with_fn=False, fat=0), None),
        ("digest gordo (colapsa in+fu)", _mk_digest(with_fn=False, fat=120), None),
        ("digest mínimo (sem seções)", _mk_digest(with_fn=False,
                                                  with_sections=False), None),
        ("aperto 900 (variantes fundas)", _mk_digest(with_fn=False), 900),
    ]
    for label, digest, max_len in cases:
        real, expected = _run_ab(digest, _summary(), None, with_fn=False,
                                 max_len=max_len, label=label)
        check(f"A/B byte a byte: {label}", real == expected,
              detail=f"real={len(real)} expected={len(expected)}")

    errors = [("registry:acme", "Acme GmbH", "TIMEOUT"),
              ("registry:beta", "Beta AG", "HTTP_ERROR")]
    digest = _mk_digest(with_fn=False, fat=200)
    real, expected = _run_ab(digest, _summary(errors=errors), errors,
                             with_fn=False, max_len=2500)
    check("A/B nível 2 (base com problemas resumida)", real == expected,
          detail=f"real={len(real)} expected={len(expected)}")
    real, expected = _run_ab(digest, _summary(errors=errors), errors,
                             with_fn=False, max_len=700)
    check("A/B nível 3 (teto defensivo do ⚡)", real == expected,
          detail=f"real={len(real)} expected={len(expected)}")


def test_compact_with_fn() -> None:
    section("D2 — compact COM 📅: fórmula F45 (colapso pós-⏰Intel, "
            "exibição pós-⏰Follow-up)")
    digest = _mk_digest(with_fn=True)
    real, expected = _run_ab(digest, _summary(), None, with_fn=True)
    check("A/B fórmula F45 (📅 inteira cabe)", real == expected,
          detail=f"real={len(real)} expected={len(expected)}")
    check("📅 presente e DEPOIS da ⏰ Follow-up na mensagem",
          all(l in real for l in (
              "⏰ Intel de empresas (frescor do intel) — 12 >90d",
              "⏰ Follow-up — candidaturas sem resposta — 4 pendente(s)",
              rg.FUNNEL_SECTION_PREFIX))
          and real.index("⏰ Follow-up — candidaturas sem resposta"
                         " — 4 pendente(s)") < real.index(
              rg.FUNNEL_SECTION_PREFIX))
    check("🔗 é a última linha", real.strip().splitlines()[-1].startswith("🔗"))
    check("sem bloco em branco duplicado", "\n\n\n" not in real)

    # aperto: 📅 colapsa ao header DEPOIS da ⏰ Intel (ordem da spec).
    # O ponto de colapso é LOCALIZADO por sonda determinística (mesmo
    # digest -> mesmo probe): descemos do default até o corpo da 📅
    # sumir com o header vivo — o primeiro probe que satisfaz isso é a
    # variante (in,fn) da cadeia, exatamente a que a spec F45 fixa.
    digest = _mk_digest(with_fn=True, fat=100)
    summary = _summary()
    real_max = rd.TELEGRAM_MAX_LEN
    found = None
    try:
        probe = real_max
        while probe > 300:
            rd.TELEGRAM_MAX_LEN = probe
            msg = rd.build_message(summary, [], 0, always_notify=True,
                                   digest_lines=digest)
            lines_p = (msg or "").splitlines()
            has_hdr = any(l.startswith(rg.FUNNEL_SECTION_PREFIX)
                          for l in lines_p)
            has_body = any(l.startswith("  ✂") for l in lines_p)
            if has_hdr and not has_body:
                found = probe
                break
            probe -= 25
    finally:
        rd.TELEGRAM_MAX_LEN = real_max
    check("sonda acha o ponto de colapso da 📅 (header vivo, corpo fora)",
          found is not None, detail=f"probe={found}")
    if found is not None:
        real, expected = _run_ab(digest, summary, None, with_fn=True,
                                 max_len=found)
        check("A/B no ponto exato: fórmula F45 com 📅 colapsada",
              real == expected)
        lines = real.splitlines()
        fn_hdr = [i for i, l in enumerate(lines)
                  if l.startswith(rg.FUNNEL_SECTION_PREFIX)]
        after = lines[fn_hdr[0] + 1:] if fn_hdr else []
        check("📅 colapsada = só header; segue direto para o 🔗",
              len(fn_hdr) == 1
              and not any(l.startswith(("  ✂", "  📈", "  📆"))
                          for l in after)
              and any(l.startswith("🔗") for l in after))
        check("⏰ Intel também colapsada antes da 📅 (cadeia in->fn)",
              any(l.startswith("⏰ Intel de empresas") for l in lines)
              and not any(l.startswith("  🕰") for l in lines))

    # aperto EXTREMO: 📅 header sobrevive ao nível 2/3 (nunca dropada)
    errors = [("registry:acme", "Acme GmbH", "TIMEOUT"),
              ("registry:beta", "Beta AG", "HTTP_ERROR")]
    digest = _mk_digest(with_fn=True, fat=300)
    real, expected = _run_ab(digest, _summary(errors=errors), errors,
                             with_fn=True, max_len=800)
    check("A/B nível 2/3 com 📅", real == expected)
    check("📅 header sobrevive ao teto defensivo",
          any(l.startswith(rg.FUNNEL_SECTION_PREFIX)
              for l in real.splitlines()))

    # sem 🎯/⏰/🆕: a 📅 colapsa sozinha sem seção fantasma
    digest = _mk_digest(with_fn=True, with_sections=False)
    real, expected = _run_ab(digest, _summary(), None, with_fn=True)
    check("digest mínimo + 📅: sem blocos fantasma, fórmula F45",
          real == expected and "\n\n\n" not in real)


# ---------------------------------------------------------------------------
# E — Wiring do refresh + zero rede
# ---------------------------------------------------------------------------


def test_wiring() -> None:
    section("E1 — wiring do refresh_daily (splice antes do link)")
    src = Path(rd.__file__).read_text(encoding="utf-8")
    check("main chama o loader com as 3 fontes",
          "ranking_digest.funnel_seasonality_section(" in src
          and "collection_metrics.jsonl" in src
          and "application_events.jsonl" in src
          and "eligible_jobs.json" in src)
    check("splice da 📅 via helper ANTES do link (blank re-criado)",
          "_splice_section_before_link(digest_lines," in src)
    # comportamento REAL do splice (helper é o código de produção):
    # caso 1: digest com blank pré-link (digest_sections puro)
    fn = ["", rg.FUNNEL_SECTION_PREFIX + " (último run 17/10) — 6 janelas",
          "  ✂ alemão exigido: 10"]
    digest1 = ["🎯 Empresas-alvo (watchlist) — 1 nova(s)", "  🎯 Bosch",
               "", "🔗 Ranking completo: https://x"]
    out1 = rd._splice_section_before_link(digest1, fn)
    check("blank pré-link consumido (nunca duplicado) + blank re-criado",
          out1 == ["🎯 Empresas-alvo (watchlist) — 1 nova(s)", "  🎯 Bosch",
                   "", rg.FUNNEL_SECTION_PREFIX + " (último run 17/10) — 6 janelas",
                   "  ✂ alemão exigido: 10", "", "🔗 Ranking completo: https://x"],
          detail=str(out1))
    check("extrator NÃO engole a 🔗 no digest montado pelo wiring",
          rg.funnel_section_lines(out1) == fn[1:]
          and out1[-1].startswith("🔗") and out1[-2] == "")
    # caso 2: digest SEM blank pré-link (pessoais splicadas antes — o
    # último bloco pessoal colado no link)
    digest2 = ["⏰ Follow-up — 1 pendente(s)", "  1. Daimler",
               "🔗 Ranking completo: https://x"]
    out2 = rd._splice_section_before_link(digest2, fn)
    check("sem blank pré-link: seção entra com o SEU blank, link separado",
          out2 == ["⏰ Follow-up — 1 pendente(s)", "  1. Daimler"]
          + fn + ["", "🔗 Ranking completo: https://x"])
    check("nenhum bloco em branco duplicado nos dois casos",
          "\n\n\n" not in "\n".join(out1) and "\n\n\n" not in "\n".join(out2))
    check("seção vazia -> digest intacto (best-effort)",
          rd._splice_section_before_link(digest1, []) == digest1)
    rg_src = Path(rg.__file__).read_text(encoding="utf-8")
    check("extrator delega ao _section_by_prefix (padrão F44)",
          "return _section_by_prefix(digest_lines, FUNNEL_SECTION_PREFIX)"
          in rg_src)


def test_no_network() -> None:
    section("E2 — zero rede + data/ somente leitura (audit AST + runtime)")
    banned = {"socket", "urllib", "http", "requests", "subprocess", "ssl",
              "smtplib", "ftplib", "telnetlib", "asyncio"}
    for mod_name, path in (("seasonality", Path(sea.__file__)),
                           ("funnel_report", Path(fr.__file__))):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        check(f"{mod_name}: nenhum import de rede",
              not (imports & banned), detail=str(imports & banned))
    # funnel_report: SOMENTE LEITURA — nenhuma chamada de escrita no AST
    tree = ast.parse(Path(fr.__file__).read_text(encoding="utf-8"))
    writes = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and (
                  (isinstance(n.func, ast.Name) and n.func.id == "open")
                  or (isinstance(n.func, ast.Attribute)
                      and n.func.attr in ("write_text", "write_bytes",
                                         "unlink", "mkdir", "rename")))]
    check("funnel_report: nenhuma chamada de escrita em arquivo",
          not writes, detail=f"{len(writes)} chamadas")
    # runtime: sockets bloqueados -> tudo passa offline
    import socket as _socket

    class _Blocked(_socket.socket):
        def __init__(self, *a, **kw):
            raise RuntimeError("rede bloqueada (teste F45)")

    _orig = _socket.socket
    _socket.socket = _Blocked
    try:
        metrics, events, eligible = _fixture_dir()
        report = fr.build_report(metrics, events, eligible)
        lines = rg.funnel_seasonality_section(metrics, events, eligible)
        cal = sea.seasonality_calendar(["ab März 2027"])
        ok = report is not None and len(lines) >= 4 and cal == [("mar/2027", 1)]
    finally:
        _socket.socket = _orig
    check("sockets bloqueados: build_report+seção+parser passam", ok)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    print("F45 — funil com motivo de morte + sazonalidade (offline)")
    test_semesters()
    test_starts()
    test_ranges()
    test_negatives_priority()
    test_labels_calendar()
    test_pipeline_funnel()
    test_labels_trend()
    test_application_and_report()
    test_cli()
    test_format_report()
    test_section_format()
    test_section_extractors()
    test_compact_ab()
    test_compact_with_fn()
    test_wiring()
    test_no_network()
    print()
    if FAILURES:
        print(f"F45: {len(FAILURES)} FALHA(S) de {CHECKS} checks")
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print(f"F45: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
