#!/usr/bin/env python3
"""Testes da Fase F95 — elegibilidade temporal + work-auth v2 (ITENS 2-6).

Deltas (spec ~/.hermes/handoff/f95-elegibilidade-temporal/ESPECIFICACAO.md):
  ITEM 2 — ``work_auth_requirement`` 3-níveis (none_mentioned |
           right_to_work_required | sponsorship_offered) + frases novas
           ("EU/EEA citizenship", "EU only", "right to work by start
           date") — DISPLAY-ONLY: a exclusão F61 fica INTACTA (blast
           radius medido da exclusão: 77 vagas Amazon, decisão do dono).
  ITEM 3 — ``start_date`` + ``start_conflict`` TOO_EARLY | IMMEDIATE |
           TOO_LATE — FLAG obrigatória, NÃO exclusão (doutrina F62).
  ITEM 4 — ``salary_period`` monthly | annual | null (nunca estimar;
           LexisNexis NÃO declara período no verbatim medido — spec dizia
           "/ano" e a medição F63/F95 refutou).
  ITEM 5 — eixo NL como SINAL (espelho FR F60/F85; Mondelez R-176327).
  ITEM 6 — dual-track Pflicht × freiwillig (flag informativo de
           remuneração; NÃO elegibilidade — F86: Praktikum presente = OK).

Fixtures VERBATIM de records reais (dataset 21/10, data/ intocável):
Amazon Bad Oldesloe 10544252 (amazon_jobs), Mondelez R-160904 + R-176327
(workday), keplercheuvreux 8570849 (teamtailor), LexisNexis R119275
(workday), Lidl SAP BI 1436050633 (successfactors). Uso:
  .venv/bin/python scripts/test_f95.py   (ou bash scripts/test_f95.py)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "src"))

import seasonality  # noqa: E402
import minimal_page as mp  # noqa: E402
import ranking_digest as rg  # noqa: E402
import funnel_report as fr  # noqa: E402
from internship_finder import app_intel as ai  # noqa: E402
from internship_finder import opportunity_intel as oi  # noqa: E402
from internship_finder import filters  # noqa: E402

N = 0
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def section(name: str) -> None:
    print(f"\n== {name} ==")


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (dataset de produção 21/10 — round-trip por frase-chave)
# ---------------------------------------------------------------------------

# Amazon Bad Oldesloe 10544252 (amazon_jobs) — o caso do lote 21/10. O
# verbatim integral não contém exigência de idioma (medição F95: "German
# C1" do ITENS NÃO está no texto — o bloqueio textual é o work-auth).
AMAZON_10544252 = (
    "Praktikum im Bereich Logistik - Bad Oldesloe - Start 2027",
    "Das Team ist stolz darauf, den Qualitätsservice zu liefern, für den "
    "Amazon weltweit bekannt ist.\n\nHinweis: Du musst zum Starttermin die "
    "Arbeitsberechtigung für das Beschäftigungsland haben.\n\n\nKey job "
    "responsibilities\nAls Amazon Operations-Praktikant:in hast du die "
    "Möglichkeit, deine analytischen Fähigkeiten in wirkungsvollen "
    "Projekten anzuwenden.",
)
AMAZON_10544252_EN = (
    "Praktikum im Bereich Logistik",
    "Note: You must have the right to work in the country of employment "
    "by the start date.",
)
# Mondelez R-160904 (workday) — início Aug 2026 (TOO_EARLY).
MONDELEZ_R160904 = (
    "Internship Mondelez (Lu, Oreo, Côte d'Or, Milka,...) - Consumer & "
    "Shopper Insights (M/F/X) - 6 months - August 2026 - Mechelen",
    "• Place of work : Mechelen (30 min from Brussels by train) • "
    "Beginning : August 2026 • Duration : 6 months • Compensation : "
    "According to profile",
)
# Mondelez R-176327 (workday) — "fluent French OR Dutch" (eixo NL).
MONDELEZ_R176327 = (
    "Taste The Future Mondelēz Internship (Lu, Oreo, Milka…) Consumer & "
    "Shopper Insights (M/F/X) – 6 months – Start Jan 2027 - Mechelen "
    "(Belgium)",
    "Passion for consumers, shoppers and brands. Fluency in English and "
    "fluent in one of the 2 languages, French or Dutch",
)
# keplercheuvreux 8570849 (teamtailor) — "Start Date: January 2026" (stale)
# + "Fluent spoken and written Dutch and English (French is a plus)".
KEPLER_8570849 = (
    "INTERNSHIP - MERGERS AND ACQUISITIONS ANALYST - BRUSSELS",
    "DETAILS : Role: Mergers and Acquisitions Analyst Intern Department: "
    "Kepler Corporate Finance Duration: 6 months Start Date: January 2026 "
    "Location: Brussels Salary: Unpaid",
)
# LexisNexis R119275 (workday) — "€17,200 - €28,700" SEM marcador de
# período no verbatim (medição F63 §A4 + F95: '/year', 'per year', 'p.a.',
# 'jährlich', 'annual', 'yearly', 'pro jahr' ausentes).
LEXISNEXIS_R119275 = (
    "Intern Data Engineering",
    "Primary Location Base Pay Range: Germany - Karlsruhe €17,200 - "
    "€28,700. We know your well-being and happiness are key to a long "
    "and successful career.",
)
# Lidl SAP BI 1436050633 (successfactors) — ab sofort + dual-track com
# remuneração distinta por trilha.
LIDL_1436050633 = (
    "Praktikum Controlling International - SAP BI Reporting",
    "Unterstütze uns bei der Digitalisierung und Weiterentwicklung des "
    "Reportings mit SAP und der SAP Analytics Cloud. Ab sofort für 6 "
    "Monate. … Lidl legt Wert darauf, dass sich deine Zeit bei uns "
    "lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen "
    "aufbessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges "
    "Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle "
    "Praxiseinblicke.",
)
MAHLE_1373497333 = (
    "Praktikum Lead-Buying Mechatronics",
    "Für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich. Ab "
    "sofort.",
)
# Contra-casos verbatim (corpus 21/10).
HELLA_EEA_FP = (
    "Praktikum Radar-Algorithmen",
    "Especially you will work with internal experts e.g., EEA engineer "
    "and V2X engineer, to evaluate influence of new calculation platform.",
)
BMW_CHECKS_FP = (
    "Intern Finance",
    "These checks include references, right to work, IT system "
    "Compliance Integrity Check (COIN), CV, and relevant qualifications.",
)
TRUMPF_DUAL = (
    "Praktikum Einkauf",
    "Das bieten wir Ihnen Pflichtpraktikum oder freiwilliges Praktikum "
    "(auch im Gap Year zwischen Bachelor und Master) Attraktive "
    "Vergütung.",
)
MAHLE_NEGATED_VOLUNTARY = (
    "Praktikum",
    "Bestätigung der Schule über die Teilnahme an einem "
    "Pflichtpraktikum. Purely voluntary internships cannot be offered.",
)
LIEBHERR_SEMESTER = (
    "Praktikant Einkauf",
    "suchen wir ab sofort oder für das Sommersemester 2027.",
)
GFO_ASAP = (
    "Praktikum Kaufmann/frau",
    "**Praktikumsvoraussetzungen:** Beginn zum nächstmöglichen Zeitpunkt",
)
HORNBACH_ASAP = (
    "Praktikum Verkauf Logistik",
    "Eintrittstermin: Zum nächstmöglichen Zeitpunkt",
)
GSK_ASAP = (
    "Internship",
    "Start date: As soon as possible Duration: Minimum 6 months",
)
ADAPTYV_ASAP = (
    "Intern",
    "Start date: ASAP Application deadline: rolling",
)
LIDL_SLOGAN_FP = (
    "Praktikum Verkauf",
    "Du steigst sofort in die Arbeitswelt ein und lernst unser Team "
    "kennen.",
)
BASF_ANNUAL = (
    "Praktikum Controlling",
    "Gross annual salary: 40.000 - 46.000 €",
)
NOVEMCORE_YEAR_RAW = {
    "title": "Praktikum", "description": "",
    "raw": {"salary_min": "900.0", "salary_max": "1200.0",
            "salary_period": "YEAR", "salary_currency": "EUR"},
}


def _job(title_desc: tuple[str, str], **extra) -> dict:
    return {"title": title_desc[0], "description": title_desc[1], **extra}


def _wa(job_or_text) -> dict:
    text = (job_or_text.get("title", "") + " " +
            job_or_text.get("description", "")) \
        if isinstance(job_or_text, dict) else job_or_text
    return ai.work_auth_requirement(text)


def main() -> int:
    # ---------------------------------------------------------------- A
    section("A: work_auth_requirement 3-níveis (ITEM 2 — display-only)")
    sc = _wa(_job(AMAZON_10544252))
    check("A1 Amazon 10544252 DE verbatim: right_to_work_required "
          "(zum Starttermin + Arbeitsberechtigung — frase nova)",
          sc["level"] == "right_to_work_required"
          and sc["detected"] == "new_forms", str(sc))
    sc = _wa(_job(AMAZON_10544252_EN))
    check("A2 Amazon EN verbatim: right_to_work_required ('right to "
          "work ... by the start date' — também existing do 5-estados)",
          sc["level"] == "right_to_work_required", str(sc))
    sc = _wa(_job(MAHLE_1373497333))
    check("A3 MAHLE verbatim: right_to_work_required via existing "
          "(F61/intel path preservado)",
          sc["level"] == "right_to_work_required"
          and sc["detected"] == "existing", str(sc))
    sc = _wa("The position includes visa sponsorship where applicable.")
    check("A4 sponsorship verbatim (the-exploration-company): "
          "sponsorship_offered (flag positiva)",
          sc["level"] == "sponsorship_offered", str(sc))
    sc = _wa("Great team, modern office in central Karlsruhe, exciting "
             "projects in procurement.")
    check("A5 sem vocab -> none_mentioned", sc["level"] == "none_mentioned")
    sc = _wa("We do not offer visa sponsorship for this position.")
    check("A6 dobra no_sponsorship -> none_mentioned (o dono nunca "
          "contou com patrocínio; §16e é a aposta)",
          sc["level"] == "none_mentioned"
          and sc["detected"] == "no_sponsorship", str(sc))
    sc = _wa("Visa requirements apply. Candidates must comply with "
             "immigration regulations.")
    check("A7 dobra unclear -> none_mentioned (5-estados segue vivo "
          "para quem quiser o nível fino)",
          sc["level"] == "none_mentioned", str(sc))
    check("A8 'Applicants must hold EU/EEA citizenship' -> "
          "right_to_work_required (frase nova do ITENS)",
          _wa("Applicants must hold EU/EEA citizenship."
              )["level"] == "right_to_work_required")
    check("A9 'EU only' bare + 'EU citizens only' -> right_to_work_required",
          _wa("Open to EU only.")["level"] == "right_to_work_required"
          and _wa("EU citizens only may apply."
                  )["level"] == "right_to_work_required")
    check("A10 FP hella 'EEA engineer': NÃO é citizenship -> "
          "none_mentioned",
          _wa(_job(HELLA_EEA_FP))["level"] == "none_mentioned")
    check("A11 FP BMW checklist ('checks include references, right to "
          "work, ...'): menção sem exigência -> none_mentioned",
          _wa(_job(BMW_CHECKS_FP))["level"] == "none_mentioned")
    check("A12 precedência: blocker vence suporte (existing + visa "
          "sponsorship juntos -> right_to_work_required)",
          _wa("Gültiger Aufenthaltstitel erforderlich. We offer visa "
              "sponsorship.")["level"] == "right_to_work_required")
    j = _job(AMAZON_10544252)
    first = _wa(j)
    check("A13 determinismo ×50 (Amazon verbatim)",
          all(_wa(j) == first for _ in range(50)))
    check("A14 DISPLAY-ONLY: a cascata de exclusão NÃO consome o campo "
          "— Amazon 10544252 continua APLICÁVEL (a exclusão das frases "
          "novas é decisão do dono; blast radius medido: 77 vagas)",
          filters.applicability_exclusion_reason(
              _job(AMAZON_10544252)) is None)
    check("A15 F61 intacta: MAHLE segue EXCLUÍDA pelo padrão "
          "endereçado-a-não-UE (hard blocker §16e mantém)",
          filters.applicability_exclusion_reason(
              _job(MAHLE_1373497333)) == "visa_blocked")

    # ---------------------------------------------------------------- B
    section("B: start_date + start_conflict (ITEM 3 — flag, não exclusão)")
    sc = seasonality.start_conflict_of(_job(LIDL_1436050633))
    check("B1 Lidl SAP BI verbatim: IMMEDIATE ('Ab sofort für 6 "
          "Monate' com contexto — F62/F67)",
          sc and sc["conflict"] == "IMMEDIATE"
          and sc["start"] is None and sc["label"] == "ab sofort", str(sc))
    sc = seasonality.start_conflict_of(_job(MONDELEZ_R160904))
    check("B2 Mondelez R-160904: TOO_EARLY ago/2026 ('Beginning : "
          "August 2026' — o ' : ' quebrava o parser)",
          sc and sc["conflict"] == "TOO_EARLY"
          and sc["start"] == "2026-08" and sc["label"] == "ago/2026",
          str(sc))
    sc = seasonality.start_conflict_of(_job(KEPLER_8570849))
    check("B3 keplercheuvreux: TOO_EARLY jan/2026 ('Start Date: "
          "January 2026' — rótulo novo)",
          sc and sc["conflict"] == "TOO_EARLY"
          and sc["start"] == "2026-01", str(sc))
    check("B4 BMW 'Startdatum: ab 09/01/2027' (DD/MM/YYYY alemão): "
          "jan/2027 DENTRO da janela -> sem flag",
          seasonality.start_conflict_of(
              {"title": "Ausbildung",
               "description": "Startdatum: ab 09/01/2027"}) is None)
    check("B5 'ab 08/2026' (MM/YYYY da spec): TOO_EARLY",
          (seasonality.start_conflict_of(
              {"title": "P", "description": "Beginn: ab 08/2026"})
           or {}).get("conflict") == "TOO_EARLY")
    check("B6 'Starting March 2028': TOO_LATE",
          (seasonality.start_conflict_of(
              {"title": "P", "description": "Starting March 2028"})
           or {}).get("conflict") == "TOO_LATE")
    check("B7 boundary: set/2027 NÃO flaga; out/2027 flaga (janela boa "
          "= jan..set/2027)",
          seasonality.start_conflict_of(
              {"title": "P", "description": "starting September 2027"})
          is None
          and (seasonality.start_conflict_of(
              {"title": "P", "description": "starting October 2027"})
              or {}).get("conflict") == "TOO_LATE")
    check("B8 Liebherr: semestre vence o 'ab sofort' em prosa -> "
          "positiva, sem flag (doutrina F62)",
          seasonality.start_conflict_of(_job(LIEBHERR_SEMESTER)) is None)
    check("B9 fórmula ASAP DE (GFO/HORNBACH verbatim 'zum "
          "nächstmöglichen Zeitpunkt'): IMMEDIATE sem data",
          (seasonality.start_conflict_of(_job(GFO_ASAP))
           or {}).get("conflict") == "IMMEDIATE"
          and (seasonality.start_conflict_of(_job(HORNBACH_ASAP))
               or {}).get("label") == "zum nächstmöglichen Zeitpunkt")
    check("B10 ASAP pós-rótulo EN (Gsk 'As soon as possible'/Adaptyv "
          "'ASAP'): IMMEDIATE; prosa solta NÃO casa",
          (seasonality.start_conflict_of(_job(GSK_ASAP))
           or {}).get("conflict") == "IMMEDIATE"
          and (seasonality.start_conflict_of(_job(ADAPTYV_ASAP))
               or {}).get("conflict") == "IMMEDIATE"
          and seasonality.start_conflict_of(
              {"title": "P",
               "description": "Apply as soon as possible for this role."})
          is None)
    check("B11 prosa 'steigt sofort in die Arbeitswelt' (slogan Lidl): "
          "sem contexto F67 -> sem flag",
          seasonality.start_conflict_of(_job(LIDL_SLOGAN_FP)) is None)
    check("B12 janela futura em jan/2027: sem flag",
          seasonality.start_conflict_of(
              {"title": "P",
               "description": "Beginn: ab März 2027 für 6 Monate"}) is None)
    hits = seasonality._start_hits("Startdatum: ab März 2027 für 6 Monate")
    check("B13 dedupe: rótulo novo + 'ab März 2027' antigo = 1 start hit",
          len([h for h in hits if h["kind"] == "start"]) == 1, str(len(hits)))
    j2 = _job(MONDELEZ_R160904)
    check("B14 determinismo ×50 (Mondelez)",
          all(seasonality.start_conflict_of(j2)
              == seasonality.start_conflict_of(j2) for _ in range(50))
          and seasonality.start_conflict_of(j2)
          == seasonality.start_conflict_of(dict(j2)))
    check("B15 FLAG NÃO exclusão (doutrina F62): Mondelez e Lidl seguem "
          "APLICÁVEIS na cascata",
          filters.applicability_exclusion_reason(
              _job(MONDELEZ_R160904)) is None
          and filters.applicability_exclusion_reason(
              _job(LIDL_1436050633)) is None)

    # ---------------------------------------------------------------- C
    section("C: salary_period (ITEM 4 — verbatim, nunca estimar)")
    sal = oi.job_salary(_job(LEXISNEXIS_R119275))
    check("C1 LexisNexis R119275: NÃO declara período no verbatim (A4 "
          "da F63 re-medido) -> salary_period None; display segue "
          "'(unidade não confirmada)' F63",
          oi.salary_period_of(_job(LEXISNEXIS_R119275)) is None
          and sal["period"] is None
          and sal.get("provenance") == "unidade não confirmada")
    sal = oi.job_salary(_job(BASF_ANNUAL))
    check("C2 BASF 'Gross annual salary': period_declared='year' -> "
          "annual; display F63 converte p/ mensal com provenance "
          "(intocado)",
          oi.salary_period_of(_job(BASF_ANNUAL)) == "annual"
          and sal["period"] == "month"
          and sal["period_declared"] == "year"
          and sal.get("provenance") == "anual convertido p/ mensal")
    check("C3 Lidl '1.300 €/Monat': a barra quebra o período (Fase J "
          "J2.1, design consciente) -> period_declared None; valor "
          "verbatim preservado",
          oi.salary_period_of({"title": "",
                               "description": "Faires "
                               "Praktikantengehalt 1.300 €/Monat "
                               "(beim Pflichtpraktikum)"}) is None
          and oi.job_salary({"title": "",
                             "description": "Faires "
                             "Praktikantengehalt 1.300 €/Monat"})["text"]
          == "1.300 €")
    check("C4 horário (18,33 €/h): fora do enum -> None (nunca estimar)",
          oi.salary_period_of({"title": "",
                               "description": "Vergütung: 18,33 €/h"})
          is None)
    check("C5 novemcore structured salary_period=YEAR -> annual (sem "
          "conversão — anomalia de fonte documentada na F63)",
          oi.salary_period_of(dict(NOVEMCORE_YEAR_RAW)) == "annual")
    check("C6 recruitee MONTH declarado (16.480–21.203, magnitude "
          "implausível): field honesto = monthly (a fonte DECLARA; o "
          "display F63 segue recusando a unidade)",
          oi.salary_period_of(
              {"title": "", "description": "",
               "raw": {"salary_min": "16480", "salary_max": "21203",
                       "salary_period": "MONTH",
                       "salary_currency": "EUR"}}) == "monthly")
    check("C7 sem salário -> None", oi.salary_period_of(
        {"title": "x", "description": "sem remuneração citada"}) is None)
    check("C8 period_declared congelado ANTES da plausibilidade "
          "(conversão year->month do display NÃO vaza no campo)",
          "period_declared" in sal)
    check("C9 Nestlé '$240,000.00 to $260,000.00 per year' -> annual",
          oi.salary_period_of(
              {"title": "",
               "description": "Salary: $240,000.00 to $260,000.00 "
               "per year"}) == "annual")

    # ---------------------------------------------------------------- D
    section("D: eixo NL como SINAL (ITEM 5 — espelho FR F60/F85)")
    dl = ai.dutch_level(f"{MONDELEZ_R176327[0]} {MONDELEZ_R176327[1]}")
    check("D1 Mondelez R-176327 'fluent in one of the 2 languages, "
          "French or Dutch': required (gap 40 — a forma-fixture mede 38)",
          dl is not None and dl.level == "required", str(dl))
    djk = f"{KEPLER_8570849[0]} Fluent spoken and written Dutch and " \
          "English (French is a plus)"
    check("D2 kepler: Dutch required + FR preferred no MESMO texto "
          "(os eixos não se contaminam)",
          ai.dutch_level(djk).level == "required"
          and ai.french_level(djk).level == "preferred")
    check("D3 SAP 'Fluency in Dutch and English is required': required",
          ai.dutch_level(
              "Languages: Fluency in Dutch and English is required "
              "French is a strong asset").level == "required")
    check("D4 Citi 'Fluency in both English and Dutch is essential': "
          "required",
          ai.dutch_level(
              "Fluency in both English and Dutch is essential"
              ).level == "required")
    check("D5 Peripass 'You are fluent in Dutch': required (qual)",
          ai.dutch_level(
              "You are fluent in Dutch and have a good working "
              "proficiency of English").level == "required")
    check("D6 soft 'Dutch is a plus': preferred",
          ai.dutch_level("Knowledge of Dutch is a plus").level
          == "preferred")
    check("D7 negação 'no Dutch required': plus (SINAL — nunca exclusão)",
          ai.dutch_level("no Dutch required").level == "plus")
    check("D8 menção nua 'Dutch market': plus",
          ai.dutch_level("Exposure to the Dutch market").level == "plus")
    check("D9 sem menção -> None", ai.dutch_level("Praktikum Einkauf "
                                                  "Logistik") is None)
    check("D10 REGRESSÃO FR (motor extraído): CANAL+ preferred/soft, "
          "courant required, 'French is a plus' preferred",
          ai.french_level("Fluent in English (written and spoken) "
                          "required; French strongly valued").level
          == "preferred"
          and ai.french_level("un français et un anglais courants").level
          == "required"
          and ai.french_level("Fluent in English (French is a plus)"
                              ).level == "preferred")
    check("D11 determinismo ×50 (Mondelez)",
          all(ai.dutch_level(f"{MONDELEZ_R176327[0]} {MONDELEZ_R176327[1]}")
              == dl for _ in range(50)))
    check("D12 SINAL nunca exclusão: Mondelez (Dutch required) segue "
          "APLICÁVEL",
          filters.applicability_exclusion_reason(
              _job(MONDELEZ_R176327)) is None)

    # ---------------------------------------------------------------- E
    section("E: dual-track Pflicht × freiwillig (ITEM 6 — informativo)")
    check("E1 Lidl SAP BI verbatim (Pflichtpraktikum: 1.300 € p.M. / "
          "freiwilliges Praktikum: Mindestlohn): flag",
          mp.dual_track_flag_text(_job(LIDL_1436050633))
          == mp.DUAL_TRACK_FLAG_TEXT)
    check("E2 trumpf enum 'Pflichtpraktikum oder freiwilliges "
          "Praktikum': flag",
          mp.dual_track_flag_text(_job(TRUMPF_DUAL))
          == mp.DUAL_TRACK_FLAG_TEXT)
    check("E3 MAHLE 'voluntary internships cannot be offered': SEM "
          "flag (não há duas trilhas)",
          mp.dual_track_flag_text(_job(MAHLE_NEGATED_VOLUNTARY)) == "")
    check("E4 só Pflicht: sem flag",
          mp.dual_track_flag_text(
              {"title": "P", "description": "Pflichtpraktikum: 900 €"})
          == "")
    check("E5 NÃO elegibilidade: Lidl e trumpf seguem APLICÁVEIS (F86: "
          "Praktikum presente = OK)",
          filters.applicability_exclusion_reason(
              _job(LIDL_1436050633)) is None
          and filters.applicability_exclusion_reason(
              _job(TRUMPF_DUAL)) is None)

    # ---------------------------------------------------------------- F
    section("F: card render pt/en (badges, I18N, legenda)")
    # companies distintas — o cap F93 (2/empresa) derrubaria cards de
    # fixtures sem company (todas cairiam no bucket None).
    html = mp.render_minimal_html(
        [_job(AMAZON_10544252, company="Amazon"),
         _job(MONDELEZ_R160904, company="Mdlz"),
         _job(MONDELEZ_R176327, company="Mdlz 2"),
         _job(LIDL_1436050633, company="Lidl")],
        total_eligible=4, generated_at="2026-10-22T00:00:00Z",
        top=10, lang="pt")
    check("F1 Amazon: badge 🔒 work-auth (pt VERBATIM)",
          f"🔒 {mp.WORK_AUTH_FLAG_TEXT}" in html)
    check("F2 Mondelez R-160904: ⚠ 'início ago/2026 — antes da "
          "disponibilidade (jan/2027)'",
          "⚠️ início ago/2026 — antes da disponibilidade (jan/2027)"
          in html)
    check("F2b Mondelez R-176327 ('fluent ... French or Dutch'): badge "
          "🇳🇱 (required)",
          '<span class="nl"><span aria-hidden="true">🇳🇱</span>'
          '</span>' in html)
    check("F3 Lidl: ⚠ VERBATIM F62 (imediato) + 🎓 dual-track",
          f"⚠️ {mp.AB_SOFORT_FLAG_TEXT}" in html
          and f"🎓 {mp.DUAL_TRACK_FLAG_TEXT}" in html)
    html_en = mp.render_minimal_html(
        [_job(AMAZON_10544252)], total_eligible=1,
        generated_at="2026-10-22T00:00:00Z", top=10, lang="en")
    m = re.search(r'data-i18n-pt="([^"]*🔒[^"]*)"', html_en)
    check("F4 EN: texto en + attr do toggle carrega o emoji + pt "
          "(padrão F62)",
          m is not None and "requires work authorization already at "
          "start" in html_en and "🔒" in (m.group(1) or ""))
    check("F5 legenda: item 🇳🇱 holandês (sinal) presente pt/en",
          "holandês (sinal)" in mp._legend_html("pt")
          and "Dutch (signal)" in mp._legend_html("en"))
    clean = mp.render_minimal_html(
        [_job(("Praktikum Einkauf", "Beginn: ab März 2027 für 6 Monate"))],
        total_eligible=1, generated_at="2026-10-22T00:00:00Z",
        top=10, lang="pt")
    check("F6 card sem sinais F95: nenhum byte de badge novo",
          "🔒" not in clean and "🤝" not in clean and "🎓" not in clean
          and "⚠️ " not in clean)
    card = mp._card(
        1, _job(AMAZON_10544252), visa=False, salary="", snippet="",
        apply_href=None, job_href="https://x", de_level="none",
        fr_level="none", age="", dead=False, is_new=False,
        duration_flag="", enrollment_red_flag="", jt_ambiguous_flag_txt="",
        start_conflict_flag="", na_flag="", lang="pt")
    check("F7 retrocompat: _card sem os params novos = nenhum badge F95 "
          "(data-nl é atributo incondicional, padrão data-fr da F60)",
          "🔒" not in card and "🤝" not in card and "🎓" not in card)
    sc_pt = mp.start_conflict_flag_text(_job(MONDELEZ_R160904), "pt")
    sc_en = mp.start_conflict_flag_text(_job(MONDELEZ_R160904), "en")
    check("F8 I18N paridade TOO_EARLY pt/en (mesmo label do parser)",
          sc_pt == "início ago/2026 — antes da disponibilidade (jan/2027)"
          and sc_en == "start ago/2026 — before your availability "
                       "(Jan/2027)")

    # ---------------------------------------------------------------- G
    section("G: digest (linhas condicionais — never-worsens)")
    sea = fr.seasonality_summary([_job(MONDELEZ_R160904),
                                  _job(KEPLER_8570849)])
    lines = rg.funnel_seasonality_lines(
        {"funnel": None, "trend": None, "application": None,
         "seasonality": sea})
    check("G1 linha ⚠ fora da janela: '2 vagas (2 antes de jan/2027)'",
          any(l.startswith("  ⚠ início fora da janela (jan–set/2027): "
                           "2 vagas (2 antes de jan/2027)")
              for l in lines), detail=" | ".join(lines))
    sea = fr.seasonality_summary([_job(AMAZON_10544252)])
    lines = rg.funnel_seasonality_lines(
        # fun stub — sem janelas a seção 📅 some (contrato F45: header
        # sem partes + sem app = []); em produção o funnel SEMPRE existe.
        {"funnel": {"run_id": "2026-10-22T09:00:00Z",
                    "applicability": {"total": 3}},
         "trend": None, "application": None, "seasonality": sea})
    check("G2 linha 🚫 work-auth: '1 vaga com exigência de autorização "
          "no início'",
          any(l == "  🚫 work-auth: 1 vaga com exigência de autorização "
                  "no início — display-only, o dono decide"
              for l in lines), detail=" | ".join(lines))
    sea = fr.seasonality_summary([_job(LIDL_SLOGAN_FP)])
    lines = rg.funnel_seasonality_lines(
        {"funnel": None, "trend": None, "application": None,
         "seasonality": sea})
    check("G3 sem sinais: NENHUMA linha nova (digest byte a byte o de "
          "antes)",
          not any(l.startswith("  ⚠ início fora")
                  or l.startswith("  🚫 work-auth") for l in lines))
    # Report pré-F95 (sem os campos novos) — best-effort honesto: sem
    # campo = sem linha (nunca volta a inventar contagem).
    lines_pre = rg.funnel_seasonality_lines(
        {"funnel": None, "trend": None, "application": None,
         "seasonality": {"scanned": 1, "with_window": 0, "calendar": []}})
    check("G4 report pré-F95 (sem os campos): linhas ausentes",
          isinstance(lines_pre, list)
          and not any(l.startswith("  🚫 work-auth")
                      or l.startswith("  ⚠ início fora")
                      for l in lines_pre))

    # ---------------------------------------------------------------- H
    section("H: never-worsens + F61 intacta")
    hits = []
    for f in (ROOT / "src" / "internship_finder").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        if ("🔒" in t or "🤝" in t or "🎓" in t
                or WORK_AUTH_TXT_MARK in t or DUAL_TXT_MARK in t):
            hits.append(str(f))
    check("H1 src/ (pipeline) ZERO menções aos textos de badge F95 "
          "(display-only; o CAMPO work_auth_requirement é a única "
          "superfície src/)",
          hits == [], detail=str(hits))
    check("H2 F61 viva: teampicnic 'sponsor your Visa' NÃO bloqueia "
          "(contra-caso da F61) e continua sponsorship_offered no campo",
          filters.applicability_exclusion_reason(
              _job(("Intern", "we would love to sponsor your Visa for "
                             "this role"))) is None
          and _wa("we would love to sponsor your Visa for this role"
                  )["level"] == "sponsorship_offered")
    check("H3 F37 viva: 'EU working rights are required' segue "
          "eu_citizenship_required",
          filters.applicability_exclusion_reason(
              _job(("Intern", "EU working rights are required")))
          == "eu_citizenship_required")
    check("H4 F37 viva: 'Either you have an EU Citizenship, or you are "
          "studying in the Netherlands' segue eu_citizenship_required",
          filters.applicability_exclusion_reason(
              _job(("Intern", "Either you have an EU Citizenship, or "
                              "you are studying in the Netherlands")))
          == "eu_citizenship_required")
    j3 = _job(MONDELEZ_R160904)
    check("H5 determinismo do summary ×20 (too_early/work_auth)",
          all(fr.seasonality_summary([j3])["too_early"] == 1
              for _ in range(20)))

    print(f"\nF95: {N} checks, {len(FAILURES)} falhas")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print("F95: TUDO OK")
    return 0


# Marcas de texto (evita duplicar as constantes do render aqui — o H1
# confere que NENHUMA delas vazou p/ src/).
WORK_AUTH_TXT_MARK = "exige autorização de trabalho já no início"
DUAL_TXT_MARK = "remuneração distinta por trilha"


if __name__ == "__main__":
    sys.exit(main())
