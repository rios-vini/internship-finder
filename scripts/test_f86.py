#!/usr/bin/env python3
"""Testes da Fase F86 — job_type + experiência: o detector
"não-é-estágio-pra-graduando" (100% offline).

Origem: RECUSAS-FEEDBACK-PIPELINE-2026-10.md, categoria TIPO (5 vagas) +
EXPERIENCIA (1 vaga), todas recusadas pelo dono em 20/10 — decisão literal
"TODAS as 6 foram recusadas → exclusão automática" (F37.3-style: saem do
eligible_jobs.json, badge/motivo no digest). O dono é graduando (formando
2027): essas classes são bloqueios DUROS de elegibilidade (insight do doc:
elegibilidade > tuning) — exclusão, NUNCA peso.

Grupos de teste:

- **T1 FIXTURES DO REGISTRO (verbatim)** — as 6 vagas recusadas, com
  provenance por fixture (fonte real coletada ou sinal registrado no doc
  quando a listagem não foi coletada — AA é title-only): Fraunhofer
  Hamburg (HiWi), Fraunhofer Kaiserslautern (Student assistant EN),
  Bauerfeind (Masterand), BASF Junior Controller (permanente €40–46k/ano),
  Impulsgrad (título duplo — FICA, ambíguo) e HYUNDAI MOBIS (1 ano de
  experiência).
- **T2 COUNTER-CASES OBRIGATÓRIOS (o que NÃO exclui)** — híbridos
  Pflichtpraktikum/Praktikant no título (doutrina F37), "working student
  friendly" como diferencial, desc que MENCIONA Werkstudent noutra seção,
  "keine Erfahrung erforderlich", faixa com piso zero ("0–2 years,
  entry-level" — SAP verbatim), história da empresa ("more than 180 years
  of experience" — C&A/Coface/KH verbatim) e boilerplate de background
  (BASF SF "durch Praktika, Werkstudententätigkeiten" — limitação
  consciente documentada no relatório).
- **T3 CONTROLES NEGATIVOS POR PADRÃO (drift simulado)** — cada classe e
  cada guard do detector exercitados em variantes DE/EN, incluindo o
  "N+ years" (2.371 ocorrências medidas no corpus bruto).
- **T4 MECANISMO** — tuplas F37.3 (subconjunto próprio +
  APPLICABILITY_JSON_EXCLUSION_REASONS), first-match (thesis_title >
  job_type; werkstudent_puro > job_type; full_time_permanent > job_type —
  campo estruturado > texto), contadores do select_eligible e rótulos
  pt-BR do digest (funnel_report.DEATH_LABELS).
- **T5 BADGE DE AMBIGUIDADE** — app_intel.job_type_ambiguous_title
  (classificador único compartilhado) + render pt/en do minimal_page +
  G1 da F51 (o renderer NÃO importa filters/ranking/scoring).

Fixtures: VERBATIM do registro/dados reais (trechos literais com campos
mínimos, padrão test_f373 — nunca payload completo); desc vazias são
desc vazias REAIS (AA é title-only). Zero rede, zero I/O de data/.
Uso:  .venv/bin/python scripts/test_f86.py   (ou bash scripts/test_f86.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

from internship_finder import app_intel  # noqa: E402
from internship_finder import filters as flt  # noqa: E402

CHECKS = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# T1 — as 6 fixtures do registro (verbatim, provenance por fixture)
# ---------------------------------------------------------------------------

# (1) Fraunhofer Hamburg — SF 1444227733 (recusa 18/10: DURACAO + TIPO;
# badge ⏳ pegou os 12 meses, o TIPO HiWi é o que a F86 fecha). Título e
# desc VERBATIM do dataset coletado (jobs.db 20/10). A desc cita
# "Reststudiendauer mind. 12 Monate" — requisito ao CANDIDATO, FP de
# duração já documentado na F37 (duration é título-only; aqui a classe é
# HiWi).
F1 = {
    "id": "Fraunhofer-Gesellschaft|successfactors:fraunhofer:1444227733",
    "title": "Studentische Hilfskraft Software Entwicklung für autonome "
             "unbemannte Wasserfahrzeuge (m/w/d)",
    "description": (
        "Das Fraunhofer-Center für Maritime Logistik und Dienstleistungen "
        "CML ist eine von über 80 Forschungseinrichtungen der "
        "Fraunhofer-Gesellschaft. ... Voraussetzungen: Laufendes Bachelor- "
        "oder Masterstudium in Informatik, Robotik, Elektrotechnik, "
        "Maschinenbau oder einem ähnlichen Fach (Reststudiendauer mind. "
        "12 Monate) ..."),
}

# (2) Fraunhofer Kaiserslautern — SF 1446740233 (recusa 18/10: TIPO —
# "Student assistant ≠ Pflichtpraktikum"). Título verbatim do dataset;
# trecho da desc verbatim (remuneração "standard student assistant rates").
F2 = {
    "id": "Fraunhofer-Gesellschaft|successfactors:fraunhofer:1446740233",
    "title": "STUDENT ASSISTANT (all genders) - DATA SPACE INFRASTRUCTURE "
             "DEVELOPMENT",
    "description": (
        "In the European research project CEADS (Common European "
        "Agricultural Data Space) we are building the technical "
        "infrastructure for a federated agricultural data space. ... "
        "Flexible hours, and we work around exam periods Paid at the "
        "standard student assistant rates, graded by degree held ..."),
}

# (3) Bauerfeind AG — direct:bundesagentur 13243-SDE-119610-JB-S (recusa
# 20/10: TIPO — "Masterand = tese de mestrado; dono é graduando"). Título
# e desc VERBATIM do eligible 20/10.
F3 = {
    "id": "Bauerfeind AG|direct:bundesagentur:13243-SDE-119610-JB-S",
    "title": "Masterand (m/w/d) für Kompetenzentwicklung im Kontext von KI",
    "description": (
        "Die Bauerfeind AG bietet als innovativer Hersteller von "
        "medizinischen Hilfsmitteln ein umfassendes Versorgungsprogramm "
        "in den Bereichen Bandagen, Orthesen, Kompressionsstrümpfe und "
        "orthopädische Einlagen. ... Wir suchen ab sofort am Standort "
        "Zeulenroda eine/-n ... Masterand (m/w/d) für "
        "Kompetenzentwicklung im Kontext von KI (Job-ID 4182) Ihre neuen "
        "Aufgaben Wir suchen Dich für eine praxisnahe Masterarbeit an der "
        "Schnittstelle von Künstlicher Intelligenz, Kompetenz- und "
        "Personalentwicklung. ..."),
}

# (4) BASF Junior Controller (Berlin) — AA (recusa 20/10: TIPO —
# "Job permanente full-time (€40–46k/ano, sem Praktikum/Intern no título)").
# A listagem AA NÃO foi coletada (AA é title-only); o título segue o
# registro do dono e a desc-carimbo é o trecho VERBATIM do gêmeo SF
# (successfactors:basf:1424780133 — mesma família de vaga): "Bruttojahresgehalt
# (Vollzeit): 40.000 - 46.000 €" (jahresgehalt + vollzeit + banda anual).
F4 = {
    "id": "BASF SE|sf_dataset:bundesagentur:(não coletado — registro do dono)",
    "title": "Junior Controller (m/w/d)",
    "description": (
        "WAS WIR BIETEN Bruttojahresgehalt (Vollzeit): 40.000 - 46.000 €, "
        "je nach Qualifikation und Berufserfahrung - Zusätzlich erwartet "
        "Sie ein vom Unternehmenserfolg abhängiger Bonus ..."),
    "employment_type": None,
}

# (5) Impulsgrad — sf_dataset:bundesagentur 10001-1003575313-S (recusa
# 20/10: TIPO + SEM-DADOS — "Werkstudent exige matrícula alemã; desc
# vazia"). Título e desc VAZIA verbatim do eligible 20/10. CASO DIFÍCIL
# decidido com o dono no relatório F86: título duplo NÃO exclui (a
# presença de Praktikant no título salva — doutrina F37 dos híbridos; o
# dono se qualifica a Praktikum §16e) — a vaga FICA com badge ⚠️ de tipo
# ambíguo (T5).
F5 = {
    "id": "Impulsgrad GmbH|sf_dataset:bundesagentur:10001-1003575313-S",
    "title": "Werkstudent:in / Praktikant:in Operations & Entrepreneurship "
             "(m/w/d)",
    "description": "",
    "employment_type": "FULL_TIME",
}

# (6) HYUNDAI MOBIS — absolventa 13423313 (recusa 20/10: EXPERIENCIA —
# "Minimum of 1 year of relevant professional experience"). Título
# verbatim do dataset; a frase de experiência é o sinal registrado
# VERBATIM no doc de recusas (a coleta absoluta veio com desc vazia — o
# catch em produção depende da hidratação F65 + re-avaliação F37.3).
F6 = {
    "id": "HYUNDAI MOBIS|absolventa:13423313",
    "title": "Internship in Logistics Specialist (m/f/d)",
    "description": (
        "Requirements: Minimum of 1 year of relevant professional "
        "experience. ..."),
}


def t1_fixtures() -> None:
    section("T1 — as 6 fixtures do registro (verbatim, exclusão automática)")
    # (1) Fraunhofer HH — HiWi
    check("F1 Fraunhofer HH: job_type = hiwi",
          flt.job_type_of(F1["title"], F1["description"]) == "hiwi")
    check("F1 Fraunhofer HH: exclui por job_type_non_internship",
          flt.applicability_exclusion_reason(F1) == "job_type_non_internship")
    # (2) Fraunhofer KL — Student assistant (EN)
    check("F2 Fraunhofer KL: job_type = hiwi (student assistant EN)",
          flt.job_type_of(F2["title"], F2["description"]) == "hiwi")
    check("F2 Fraunhofer KL: exclui por job_type_non_internship",
          flt.applicability_exclusion_reason(F2) == "job_type_non_internship")
    # (3) Bauerfeind — Masterand = tese
    check("F3 Bauerfeind: job_type = tese (Masterand)",
          flt.job_type_of(F3["title"], F3["description"]) == "tese")
    check("F3 Bauerfeind: exclui por job_type_non_internship",
          flt.applicability_exclusion_reason(F3) == "job_type_non_internship")
    # (4) BASF Junior Controller — permanente (jahresgehalt + vollzeit)
    check("F4 BASF JC: job_type = permanente (Bruttojahresgehalt/Vollzeit)",
          flt.job_type_of(F4["title"], F4["description"]) == "permanente")
    check("F4 BASF JC: exclui por job_type_non_internship",
          flt.applicability_exclusion_reason(F4) == "job_type_non_internship")
    # (5) Impulsgrad — título duplo FICA (decisão registrada; badge no T5)
    check("F5 Impulsgrad: NÃO exclui (título duplo — Praktikant salva)",
          flt.applicability_exclusion_reason(F5) is None)
    check("F5 Impulsgrad: job_type_of = None (guard de título)",
          flt.job_type_of(F5["title"], F5["description"]) is None)
    # (6) HYUNDAI — experiência
    check("F6 HYUNDAI: requires_experience True (1 year verbatim)",
          flt.requires_experience(F6["title"], F6["description"]))
    check("F6 HYUNDAI: exclui por experience_required",
          flt.applicability_exclusion_reason(F6) == "experience_required")


# ---------------------------------------------------------------------------
# T2 — counter-cases OBRIGATÓRIOS (o que NÃO exclui)
# ---------------------------------------------------------------------------

def t2_counter_cases() -> None:
    section("T2 — counter-cases obrigatórios (o que NÃO exclui)")
    # Híbridos com Praktikum/Praktikant no TÍTULO (doutrina F37) — casos
    # REAIS do eligible 20/10 (Werkstudent + Pflichtpraktikant composto).
    check("contra: Diehl 'Werkstudent / Pflichtpraktikant' (composto) FICA",
          flt.applicability_exclusion_reason({
              "title": "Werkstudent / Pflichtpraktikant im Bereich "
                       "HR-Analytics & Digitale Prozesse (m/w/d)",
              "description": "Unterstützung des Teams HR-Analytics.",
              "employment_type": "PART_TIME"}) is None)
    check("contra: Philips 'Werkstudent / Praktikum' FICA",
          flt.applicability_exclusion_reason({
              "title": "Werkstudent / Praktikum (all genders) – SAP Plant "
                       "Maintenance",
              "description": "Unterstützung im SAP PM Umfeld.",
              "employment_type": None}) is None)
    check("contra: Kaufland 'Praktikant / Werkstudent' FICA",
          flt.applicability_exclusion_reason({
              "title": "Praktikant / Werkstudent Verpackungsmanagement - "
                       "Nachhaltigkeit (m/w/d)",
              "description": "Analyse von Verpackungsdaten.",
              "employment_type": None}) is None)
    check("contra: Big Dutchman 'Student or voluntary internship' FICA",
          flt.applicability_exclusion_reason({
              "title": "Student or voluntary internship (m/f/d)",
              "description": "Internship in our procurement team.",
              "employment_type": "INTERNSHIP"}) is None)
    check("contra: teampicnic 'Internship - Business Analyst' FICA",
          flt.applicability_exclusion_reason({
              "title": "Internship - Business Analyst (m/w/d)",
              "description": "Support our analytics team.",
              "employment_type": None}) is None)
    # "working student friendly" como diferencial não exclui Praktikum.
    check("contra: 'working student friendly' em desc de Praktikum FICA",
          flt.applicability_exclusion_reason({
              "title": "Praktikum (m/w/d) Einkauf",
              "description": "Wir sind working student friendly und "
                             "freuen uns auf deine Bewerbung.",
              "employment_type": None}) is None)
    # Desc menciona Werkstudent noutra seção — o título de Praktikum salva.
    check("contra: desc cita 'als Werkstudent' em vaga de Praktikum FICA",
          flt.applicability_exclusion_reason({
              "title": "Praktikum im Bereich Anlagenbau (m/w/d)",
              "description": "Diese Stelle kann auch als Werkstudent:in "
                             "besetzt werden.",
              "employment_type": None}) is None)
    # Experiência: counter-cases negativos.
    check("contra: 'keine Erfahrung erforderlich' NÃO marca",
          not flt.requires_experience(
              "Praktikum Einkauf (m/w/d)",
              "Für diese Stelle ist keine Erfahrung erforderlich."))
    check("contra: '0–2 years of experience (entry-level)' NÃO marca "
          "(SAP verbatim)",
          not flt.requires_experience(
              "Contracts & Bid Support Coordinator (LiSa) (m/f/d)",
              "What you bring · Education: Bachelor's degree in "
              "Rechtspraktijk (recent graduates encouraged to apply) · "
              "Experience: 0–2 years of experience (entry-level). "
              "Relevant internships or academic experience are a plus"))
    check("contra: '0-2 Jahre' (hífen ASCII) NÃO marca",
          not flt.requires_experience(
              "Praktikum (m/w/d)", "0-2 Jahre Erfahrung ausreichend"))
    check("contra: 'Erfahrung von Vorteil' sem número NÃO marca",
          not flt.requires_experience(
              "Praktikum Controlling (m/w/d)",
              "Erste Erfahrung im Controlling von Vorteil."))
    # História da empresa (frase sobre a EMPRESA, não sobre o candidato) —
    # 3 verbatim medidos no corpus 20/10.
    check("contra: C&A 'building on more than 180 years of experience' "
          "NÃO marca",
          not flt.requires_experience(
              "Intern (m/f/d) Data Governance",
              "We are building on more than 180 years of experience in the "
              "fashion industry and continuously modernize the company."))
    check("contra: Coface 'With more than 70 years of experience ... has "
          "become' NÃO marca",
          not flt.requires_experience(
              "Marketing Internship – Coface Belgium",
              "With more than 70 years of experience and the largest "
              "international network, Coface has become a household name "
              "when it comes to credit insurance."))
    check("contra: KH 'With 30 years of experience ... has established' "
          "NÃO marca",
          not flt.requires_experience(
              "Sales Intern",
              "With 30 years of experience in chemical trading and "
              "distribution, KH Chemicals has established itself as a "
              "trusted partner in the industry."))
    check("contra: 'gegründet ... 100 Jahre Erfahrung' NÃO marca",
          not flt.requires_experience(
              "Praktikum (m/w/d)",
              "1878 gegründet, blicken wir auf über 100 Jahre Erfahrung in "
              "der Branche."))
    # Boilerplate de background (limitação consciente, documentada): o
    # gêmeo SF do BASF JC menciona Praktika/Werkstudenten como BACKGROUND
    # do candidato → a ausência de marcador falha → job_type não foga... —
    # vaga FICA (falso-negativo documentado no relatório; o gêmeo AA/desc
    # vazia é o caso do registro e SAI).
    check("contra: BASF SF boilerplate 'durch Praktika, "
          "Werkstudententätigkeiten' FICA (limitação documentada)",
          flt.applicability_exclusion_reason({
              "title": "Junior Controller Product Costing & Inventory "
                       "Valuation (m/w/d) - Hybrid Option DE",
              "description": "... erste Erfahrungen in Rechnungswesen, "
                             "Kostenrechnung ... oder in Controlling, "
                             "beispielsweise durch Praktika, "
                             "Werkstudententätigkeiten oder eine erste "
                             "Berufserfahrung ... WAS WIR BIETEN "
                             "Bruttojahresgehalt (Vollzeit): 40.000 - "
                             "46.000 € ...",
              "employment_type": None}) is None)
    check("contra: 'Intern' dentro de 'internationaler' NÃO salva "
          "(word-boundary)",
          flt.job_type_of(
              "Junior Controller (m/w/d)",
              "Die BASF Services Europe GmbH bündelt als internationaler "
              "Service Hub ... Bruttojahresgehalt (Vollzeit): 40.000 - "
              "46.000 €") == "permanente")


# ---------------------------------------------------------------------------
# T3 — controles negativos por padrão (drift simulado pega)
# ---------------------------------------------------------------------------

def t3_negative_controls() -> None:
    section("T3 — controles negativos por padrão (cada classe/guard pega)")
    # hiwi (DE + EN)
    for title in ("HiWi Data Science (m/w/d)",
                  "Wissenschaftliche Hilfskraft (m/w/d)",
                  "Studentische Hilfskraft (m/w/d)",
                  "Student Assistant (all genders)"):
        check(f"hiwi: '{title[:44]}'",
              flt.job_type_of(title, "Unterstützung unseres Teams.")
              == "hiwi")
    check("hiwi: desc-only 'als HiWi beschäftigt' pega",
          flt.job_type_of("Software Development (m/w/d)",
                          "Sie werden als HiWi an unserem Institut "
                          "beschäftigt.") == "hiwi")
    # werkstudent (título + desc definidora; formas :in e composta)
    check("werkstudent: título 'Werkstudent:in BI' pega",
          flt.job_type_of("Werkstudent:in Business Intelligence (m/w/d)",
                          "Support our BI team.") == "werkstudent")
    check("werkstudent: título 'Working Student Logistics' pega",
          flt.job_type_of("Working Student Logistics (f/m/d)",
                          "Support logistics ops.") == "werkstudent")
    check("werkstudent: desc 'als Werkstudent:in' com título limpo pega",
          flt.job_type_of("Support Einkauf (m/w/d)",
                          "Wir suchen dich als Werkstudent:in für unser "
                          "Team.") == "werkstudent")
    check("werkstudent: boilerplate 'Werkstudententätigkeiten' SEM 'als' "
          "não pega (background)",
          flt.job_type_of(
              "Junior Analyst (m/w/d)",
              "Erfahrung beispielsweise durch Praktika, "
              "Werkstudententätigkeiten.") is None)
    # tese (papel + definição na desc)
    check("tese: 'Masterand (m/w/d)' pega",
          flt.job_type_of("Masterand (m/w/d) für Datenanalyse",
                          "Praxisnahe Masterarbeit.") == "tese")
    check("tese: 'Bachelorand' pega (tese é sempre posição estudantil)",
          flt.job_type_of("Bachelorand Sensorik (m/w/d)", None) == "tese")
    check("tese: desc 'im Rahmen einer Masterarbeit' pega",
          flt.job_type_of("KI-Projekt (m/w/d)",
                          "Sie schreiben im Rahmen einer Masterarbeit "
                          "Ihre Thesis bei uns.") == "tese")
    check("tese: desc 'Master's Thesis:' pega",
          flt.job_type_of("Thesis Project",
                          "Master's Thesis: Combined Thermal Modeling.")
          == "tese")
    check("tese: 'Abschlussarbeit' solto na desc NÃO pega (doutrina — "
          "ambíguo)",
          flt.job_type_of("Praktikum Entwicklung (m/w/d)",
                          "Abschlussarbeit möglich.") is None)
    # permanente (sinais full-time + ausência de marcador)
    for desc in ("Vollzeit Stelle, unbefristet.",
                 "Festanstellung in unserem Team.",
                 "Bruttojahresgehalt (Vollzeit): 40.000 - 46.000 €",
                 "We offer a permanent position in our office.",
                 "Gehalt: 45.000 € pro Jahr.",
                 "Salary: 60,000 per year."):
        check(f"permanente: '{desc[:40]}'",
              flt.job_type_of("Junior Controller (m/w/d)", desc)
              == "permanente")
    check("permanente: Praktikum (Vollzeit) no título FICA (guard)",
          flt.job_type_of("Praktikum (Vollzeit) im Einkauf (m/w/d)",
                          "Vergütung nach IG Metall.") is None)
    # experiência (spec HYUNDAI + variantes DE + "N+ years")
    for text in ("Minimum of 1 year of relevant professional experience.",
                 "At least 2 years of professional experience.",
                 "minimum 5+ years of hands-on experience",
                 "2 + years working with Global markets",
                 "mindestens 1 Jahr Berufserfahrung",
                 "3 Jahre Praxiserfahrung im Einkauf",
                 "6 years relevant experience with BA"):
        check(f"experiência: '{text[:44]}'",
              flt.requires_experience("Analyst (m/w/d)", text))
    check("experiência: 'not required' com número NÃO marca",
          not flt.requires_experience(
              "Intern (m/f/d)",
              "3 years of experience are not required for this role."))
    check("experiência: '6 months of experience' NÃO marca (unidade "
          "jahr|year)",
          not flt.requires_experience(
              "Intern (m/f/d)", "6 months of experience in retail."))


# ---------------------------------------------------------------------------
# T4 — mecanismo (tuplas F37.3, first-match, contadores, rótulos)
# ---------------------------------------------------------------------------

def t4_mechanism() -> None:
    section("T4 — mecanismo: tuplas F37.3, first-match, contadores, rótulos")
    for reason in ("job_type_non_internship", "experience_required"):
        check(f"tupla F37: '{reason}' em APPLICABILITY_EXCLUSION_REASONS",
              reason in flt.APPLICABILITY_EXCLUSION_REASONS)
        check(f"tupla F37.3: '{reason}' em APPLICABILITY_JSON_EXCLUSION_"
              f"REASONS (exclusão pós-hidratação)",
              reason in flt.APPLICABILITY_JSON_EXCLUSION_REASONS)
        check(f"is_json_exclusion_reason('{reason}')",
              flt.is_json_exclusion_reason(reason))
    check("tupla F37.3 é subconjunto PRÓPRIO da tupla F37",
          set(flt.APPLICABILITY_JSON_EXCLUSION_REASONS)
          < set(flt.APPLICABILITY_EXCLUSION_REASONS))
    # First-match: as classes anteriores mantêm suas vagas.
    check("first-match: 'Masterarbeit Supply Chain' (título) continua "
          "thesis_title",
          flt.applicability_exclusion_reason({
              "title": "Masterarbeit Supply Chain",
              "description": "Tese no department de Logística"})
          == "thesis_title")
    check("first-match: 'Werkstudent Controlling' (puro) continua "
          "werkstudent_puro",
          flt.applicability_exclusion_reason({
              "title": "Werkstudent Controlling",
              "description": "Suporte ao time de controlling."})
          == "werkstudent_puro")
    check("first-match: FULL_TIME estruturado continua full_time_permanent "
          "(campo > texto)",
          flt.applicability_exclusion_reason({
              "title": "Associate Analyst",
              "description": "Full time permanent position in our office",
              "employment_type": "FULL_TIME"}) == "full_time_permanent")
    # Contadores do select_eligible (cascata). ``student=False``,
    # ``area=False`` e ``country="all"`` isolam o ESTÁGIO DE
    # APLICABILIDADE (as fixtures não carregam markers de área/país — os
    # estágios anteriores os derrubariam antes do que a F86 testa).
    jobs = [dict(F1), dict(F2), dict(F3), dict(F4), dict(F6),
            {"title": "Praktikum Einkauf (m/w/d)",
             "description": "Estágio em einkauf.", "id": "ok-1"}]
    kept, counts = flt.select_eligible(jobs, student=False, area=False,
                                       country="all")
    check("select_eligible: job_type_non_internship contabilizado",
          counts.get("aplicabilidade_excluidas_job_type_non_internship") == 4)
    check("select_eligible: experience_required contabilizado",
          counts.get("aplicabilidade_excluidas_experience_required") == 1)
    check("select_eligible: só o Praktikum sobrevive ao estágio",
          len(kept) == 1 and kept[0]["id"] == "ok-1")
    check("select_eligible: reversível (--no-applicability)",
          flt.select_eligible(jobs, student=False, area=False,
                              country="all",
                              applicability=False)[1].get(
              "aplicabilidade") == 6)
    # Rótulos pt-BR do digest (funnel_report.DEATH_LABELS).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import funnel_report as fr

        check("digest: rótulo job_type_non_internship",
              fr.death_label("job_type_non_internship")
              == "tipo de vaga (não-estágio: HiWi/Werkstudent/tese/"
                 "permanente)")
        check("digest: rótulo experience_required",
              fr.death_label("experience_required")
              == "experiência prévia exigida")
    except Exception as exc:  # noqa: BLE001 — import best-effort
        check("digest: funnel_report importável", False, repr(exc))


# ---------------------------------------------------------------------------
# T5 — badge de ambiguidade (app_intel + minimal_page + G1)
# ---------------------------------------------------------------------------

def t5_badge() -> None:
    section("T5 — badge de tipo ambíguo (app_intel + minimal_page + G1)")
    check("app_intel: Impulsgrad (título duplo) = ambíguo",
          app_intel.job_type_ambiguous_title(F5["title"]))
    check("app_intel: 'Werkstudent Controlling' puro NÃO é ambíguo",
          not app_intel.job_type_ambiguous_title(
              "Werkstudent Controlling (m/w/d)"))
    check("app_intel: 'Praktikum Einkauf' NÃO é ambíguo",
          not app_intel.job_type_ambiguous_title("Praktikum Einkauf (m/w/d)"))
    check("app_intel: 'Werkstudierendentätigkeit / Praktikum' NÃO é "
          "ambíguo (sem 'werkstudent' no título — híbrido fica pelo guard, "
          "sem badge; caso Liebherr medido)",
          not app_intel.job_type_ambiguous_title(
              "Werkstudierendentätigkeit / Praktikum Vertrieb"))
    try:
        import minimal_page as mp

        flag_pt = mp.job_type_ambiguous_flag(F5)
        check("minimal_page: badge pt renderiza (Impulsgrad)",
              flag_pt == mp.JOB_TYPE_AMBIGUOUS_FLAG_TEXT
              and "tipo ambíguo" in flag_pt,
              flag_pt[:60])
        flag_en = mp.job_type_ambiguous_flag(F5, lang="en")
        check("minimal_page: badge en renderiza",
              flag_en == mp.I18N["jt_ambiguous_flag"]["en"], flag_en[:60])
        check("minimal_page: vaga sem título duplo NÃO ganha badge",
              mp.job_type_ambiguous_flag(F1) == "")
        html = mp.render_minimal_html(
            [dict(F5, score=10.0)], total_eligible=1,
            generated_at="2026-10-20 12:00", top=10, lang="pt")
        check("minimal_page: card do Impulsgrad carrega o badge ⚠️",
              "⚠️ tipo ambíguo" in html)
        check("minimal_page: legenda explica o sinal F86",
              "tipo ambíguo Werkstudent/Praktikum (F86" in html)
        src = (Path(__file__).resolve().parent / "minimal_page.py"
               ).read_text(encoding="utf-8")
        check("G1/F51: renderer continua SEM import filters/ranking/scoring",
              "import filters" not in src and "import scoring" not in src
              and "import ranking" not in src.replace(
                  "import ranking_digest", ""))
    except Exception as exc:  # noqa: BLE001 — import best-effort
        check("minimal_page importável", False, repr(exc))


def main() -> int:
    print("F86 — job_type + experiência (detector não-é-estágio-pra-"
          "graduando)")
    t1_fixtures()
    t2_counter_cases()
    t3_negative_controls()
    t4_mechanism()
    t5_badge()
    print("\n" + "=" * 60)
    print(f"F86: {CHECKS} checks, {len(FAILURES)} falhas")
    if FAILURES:
        print("FALHAS:", FAILURES)
        return 1
    print("OK — F86 verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
