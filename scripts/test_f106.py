#!/usr/bin/env python3
"""Testes da Fase F106 — local-enrollment DE/EN: matrícula em universidade
alemã (100% offline).

Origem: registro 22/10 — 3ª classe de requisito duro de MATRÍCULA LOCAL
(as 2 primeiras são NL/EN, cobertas pela F37/F99): (1) Continental Supply
Chain Intern REF99687I "Studium an einer deutschen Hochschule"; (2) DHL
Implementation Analyst 384551 "university based in Germany"; (3)
Avery Dennison "currently enrolled at a Dutch university" — já coberto
pela F99 = contra-caso de regressão. O grep pré-fase provou que o
detector F99 era CEGO à classe DE: Continental REF99687I e novemcore
14171261 estavam NO ELIGIBLE (23/10, 688 vagas) com "an einer deutschen
Hochschule" no texto.

Passo 0 MEDIDO (23/10, corpus inteiro jobs.json 118.785 vagas — decisivo
para exclusão×flag, lição F85/F90):
- "an einer deutschen": 98 spans (96 jobs) — TODOS requisitos de
  matrícula, 0 FP ("Immatrikulation an einer deutschen", "Du bist an
  einer deutschen Hochschule eingeschrieben", "Sie befinden sich in
  einem aktiven Vollzeitstudium ... an einer deutschen Hochschule").
- "in einer deutschen": 2 spans (SYNLAB, Believe) — ambos requisitos.
- "Semester einer deutschen Hochschule": 1 span (egc-fmde) — requisito.
- "Hochschule/Universität in Deutschland": 7 spans (sobi, Fraunhofer ×2,
  tanzstudio ×2 + espelhos) — todos requisitos.
- "(at|in) a German university": 27 spans — todos requisitos ("enrolled
  at/in", "enrollment/enrolment at", "studies at", "registered student
  at"); "with a German university" (menção cooperativa) = 0 spans.
- "at a university in Germany": 4 spans (Deutsche Börse Sustainability,
  lano, zentioio + espelho) — todos requisitos.
→ 2/2 hits do eligible eram requisitos reais → EXCLUSÃO na cascata
(mesma trilha F37.3 da classe NL), não flag.

Veredito: motivo NOVO na cadeia F37.3 — ``de_enrolment_required``,
irmão de ``nl_enrolment_required`` (mesma classe semântica, legenda
própria 🇩🇪 vs 🇳🇱). NÃO entra em ``APPLICABILITY_JSON_EXCLUSION_REASONS``
(padrão nl_enrolment: exclusão na cascata, flag pós-hidratação).

Contra-casos MEDIDOS que NÃO casam (guards da âncora obrigatória):
- Bosch Pflichtpraktikum gem. SPO (EURES REF285439J): "Voraussetzung für
  das Praktikum ist die Immatrikulation an einer Hochschule" — matrícula
  GENÉRICA (478 spans no corpus), estudante internacional satisfaz.
- Duales Studium (BASF/KPMG/SAP DHBW): "Duale Hochschule Baden-
  Württemberg" — classe DUAL (job_type F86), sem "an/in einer deutschen".
- KPMG: "Arbeite neben Deinem Studium an spannenden Projekten" — sem
  "einer deutschen".
- Würth: "aus einer deutschen Erfolgsgeschichte" — sem instituição.
- "based in Germany" SOLTO: BASF "Spanish Talent Acquisition team based
  in Germany", Tesla "The Internship Role is based in Germany", Bayer
  "You are based in Germany", HRW "Interns based in Germany will
  receive..." — residência/localização do CANDIDATO/TEAM/ROLE, outra
  classe (fora de escopo da F106).

Grupos de teste:

- **T1 FIXTURES VERBATIM POSITIVAS (12)** — as 2 do ELIGIBLE vivo
  (Continental REF99687I, novemcore 14171261 — a prova do buraco), a
  evidência do registro fora do dataset vivo (DHL 384551) e 9 do corpus
  (InterNations SR, Fraunhofer DE+EN, SYNLAB, egc-fmde, Deutsche Börse
  ICT+Sustainability, Nordex, Aptiv). Detector em todos; cadeia completa
  onde nenhum motivo anterior preempte (werkstudent_puro/thesis_title
  fire ANTES por desenho — re-atribuição documentada em T4).
- **T2 COUNTER-CASES OBRIGATÓRIOS (9)** — Bosch SPO (matrícula genérica),
  Duale Hochschule BASF + KPMG "neben Studium an spannenden" (classe
  DUAL/sem âncora), Würth "Erfolgsgeschichte" (sem instituição), Bayer/
  BASF/Tesla/HRW "based in Germany" (residência/role, outra classe),
  neutro sem sinal.
- **T3 REGRESSÃO F99 (classe NL intacta)** — Avery Dennison ("currently
  enrolled at a Dutch university"), YETI AUAS, Vanderlande R31, Parfumado
  HBO/WO seguem ``nl_enrolment_required``; overlap NL×DE zero (detector
  NL não casa padrões DE e vice-versa); first-match NL antes de DE.
- **T4 MECANISMO F37.3** — ``de_enrolment_required`` em
  ``APPLICABILITY_EXCLUSION_REASONS`` na posição imediatamente após
  ``nl_enrolment_required``; NÃO em ``APPLICABILITY_JSON_EXCLUSION_REASONS``
  (padrão nl_enrolment); contador ``aplicabilidade_excluidas_`` via
  ``select_eligible``; re-attribuição honesta (Fraunhofer HiWi/SYNLAB
  Werkstudent morrem em werkstudent_puro/thesis_title ANTES — o detector
  novo só muda o motivo quando alcança a posição NL/DE); legenda pt-BR
  (ptbr.APPLICABILITY_REASON_LABELS + funnel_report.DEATH_LABELS) cobre
  o motivo novo.
- **T5 INTEGRAÇÃO select_eligible** — fixture sintética com Continental
  verbatim → excluída com ``counts["aplicabilidade_excluidas_
  de_enrolment_required"] == 1``; lote com Bosch (fica) + Continental
  (sai) → contagens exatas; ``applicability=False`` desliga (reversível).
- **T6 CONTROLES NEGATIVOS** — neutros sem qualquer sinal → cadeia None.

Fixtures: VERBATIM do corpus de produção 23/10 (jobs.json/eligible.json
688 — trechos literais, campos mínimos — padrão test_f99/test_f86) +
verbatim do registro 22/10 (DHL). Zero rede, zero I/O de data/.
Uso:  .venv/bin/python scripts/test_f106.py   (ou bash scripts/test_f106.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

from internship_finder import filters as flt  # noqa: E402
from internship_finder import ptbr  # noqa: E402

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
# T1 — fixtures verbatim positivas (eligible vivo + registro + corpus)
# ---------------------------------------------------------------------------

# (1) Continental REF99687I — NO ELIGIBLE de 23/10 (688 vagas): a prova
# do buraco (o detector F99 era cego à classe DE). Verbatim do dataset:
# "Studium der Chemie, Chemieingenieurwissenschaften, Materialwissenschaften,
# Data Science, Ingenieurwissenschaften oder vergleichbar an einer deutschen
# Hochschule".
FIX_CONTINENTAL = {
    "id": "Continental AG|sf_dataset:eures:MTI3NDUtOTcyNDYzNDIzLVMgMQ",
    "title": "Praktikum – Datenvisualisierung in der Materialentwicklung - "
    "REF99687I (Entwicklung)",
    "description": (
        "- Aufbau und Strukturierung einer Benchmark-Datenbank - "
        "Datenpflege und -validierung - Visualisierung von "
        "Performance-Kennzahlen mit Power BI Qualifikationen - Studium "
        "der Chemie, Chemieingenieurwissenschaften, "
        "Materialwissenschaften, Data Science, Ingenieurwissenschaften "
        "oder vergleichbar an einer deutschen Hochschule - Interesse an "
        "Datenanalyse, Materialentwicklung oder Automobiltechnologie - "
        "Gute Microsoft Excel-Kenntnisse - Fließende "
        "Englischkenntnisse (mündlich & schriftlich), Deutschkenntnisse "
        "hilfreich"
    ),
}

# (2) novemcore 14171261 — NO ELIGIBLE de 23/10 (2º hit real). Verbatim:
# "Voraussetzung: Laufendes Bachelor- oder Master-Studium an einer
# deutschen Hochschule oder Universität".
FIX_NOVEMCORE = {
    "id": "novemcore|sf_dataset:join_com:14171261",
    "title": "Praktikum Business Analytics & Corporate Finance (m/w/d)",
    "description": (
        "Eckdaten Standort: Berlin (mit Möglichkeit für Home Office) "
        "Dauer: 8-12 Wochen Art des Praktikums: Pflicht- oder "
        "freiwilliges Praktikum (bitte in der Bewerbung angeben) "
        "Voraussetzung: Laufendes Bachelor- oder Master-Studium an "
        "einer deutschen Hochschule oder Universität Deine Rolle Du "
        "unterstützt uns in zwei zentralen Bereichen unserer Arbeit"
    ),
}

# (3) InterNations 744000145780559 — corpus vivo (smartrecruiters; twin
# personio 15053). "enrolled at a German university" — a frase da classe
# EN; o mesmo texto traz "must also be based in Germany for the entire
# duration" (residência — fora de escopo, não casa sozinha).
FIX_INTERNATIONS = {
    "id": "internations|sf_dataset:smartrecruiters:744000145780559",
    "title": "People Experience Intern",
    "description": (
        "Please note: We can only accept applications from students who "
        "must complete a mandatory internship for a minimum of 6 months "
        "as part of their degree. Candidates must be EU citizens or "
        "enrolled at a German university . The successful candidate "
        "must also be based in Germany for the entire duration of the "
        "internship."
    ),
}

# (4) DHL 384551 — evidência do registro 22/10, FORA do dataset vivo
# (vaga efêmera saiu do funil antes da fase). Frase verbatim do
# registro: "university based in Germany".
FIX_DHL = {
    "id": "DHL|384551",
    "title": "Implementation Analyst (m/f/d)",
    "description": (
        "You are currently enrolled as a student at a university based "
        "in Germany."
    ),
}

# (5) Fraunhofer 1447257833 — corpus vivo (Abschlussarbeit; morre em
# thesis_title ANTES na cadeia — detector validado em nível de função,
# re-atribuição documentada no T4). Verbatim: "Gültige Immatrikulation
# an einer deutschen Hochschule oder Universität im Masterstudium".
FIX_FRAUNHOFER_DE = {
    "id": "Fraunhofer-Gesellschaft|successfactors:fraunhofer:1447257833",
    "title": "Abschlussarbeit - Simulationsbasierte Optimierung der "
    "Regelung eines E",
    "description": (
        "Hiermit bringen Sie sich ein Gültige Immatrikulation an einer "
        "deutschen Hochschule oder Universität im Masterstudium der "
        "Kybernetik, Mechatronik, Medizintechnik"
    ),
}

# (6) SYNLAB (bamboohr:68) — corpus vivo: "in einer deutschen Hochschule
# immatrikuliert" (preposição IN; morre em werkstudent_puro antes).
FIX_SYNLAB = {
    "id": "SYNLAB Holding Deutschland GmbH|sf_dataset:bamboohr:68",
    "title": "Werkstudent (m/w/d) Bakteriologie (Humanbiologe/-b",
    "description": (
        "Darüber hinaus zeichnen Sie sich durch folgende Erfahrungen "
        "und Fähigkeiten aus: * Sie sind in einer deutschen Hochschule "
        "immatrikuliert und absolvieren derzeit erfolgreich Ihr "
        "Studium"
    ),
}

# (7) egc-fmde 14144271 — corpus vivo: "mindestens im 3. Semester einer
# deutschen Hochschule eingeschrieben" — SEM preposição an/in antes; só
# o padrão de instituição ("einer deutschen Hochschule") pega.
FIX_EGC = {
    "id": "egc-fmde|sf_dataset:join_com:14144271",
    "title": "Werkstudent Marketing und Grafikdesign (m/w/d)",
    "description": (
        "Qualifikation Du bist mindestens im 3. Semester einer "
        "deutschen Hochschule eingeschrieben im Bereich Marketing, "
        "Kommunikationsdesign"
    ),
}

# (8) Deutsche Börse 1431839233 — corpus vivo: "Ongoing studies at a
# German university in Information Technology" (morre em
# werkstudent_puro antes).
FIX_DBOERSE_ICT = {
    "id": "Deutsche Börse AG|successfactors:career:1431839233",
    "title": "Working Student (f/m/d) - ICT Security Change Services ",
    "description": (
        "We call this: the exchange mindset. Your skills: Ongoing "
        "studies at a German university in Information Technology, "
        "Business Administration, Economics, Project Management, or a "
        "related field"
    ),
}

# (9) Nordex 1448518333 — corpus vivo: "currently enrolled in a degree
# program at a German university" (o verbo fica longe do par
# at/in+German+university — a âncora de cauda pega).
FIX_NORDEX = {
    "id": "Nordex Group Career Portal|sf_dataset:successfactors:1448518333",
    "title": "Working Student (m/f/d) External Supervision Global Pro",
    "description": (
        "YOUR PROFILE You are currently enrolled in a degree program "
        "at a German university You have very good knowledge of "
        "Microsoft Office, particularly Microsoft Excel and PowerPoint"
    ),
}

# (10) Fraunhofer EN 1450230033 — corpus vivo (alcança a cadeia:
# "Enrolment at a German university" — grafia britânica ENROLment).
FIX_FRAUNHOFER_EN = {
    "id": "Fraunhofer-Gesellschaft|successfactors:fraunhofer:1450230033",
    "title": "Students: Parametric CAD & Mesh Automation for Power-El",
    "description": (
        "Run baseline simulations, perform mesh-convergence studies, "
        "and develop reusable post-processing scripts and reports. "
        "What you contribute Enrolment at a German university in "
        "Mechanical, Electrical, Computational Engineering, Computer "
        "Science, or a related Bachelor’s or Master’s program."
    ),
}

# (11) Deutsche Börse Sustainability 1448078233 — corpus vivo: "at a
# university in Germany until at least March 2028" (morre em
# werkstudent_puro antes).
FIX_DBOERSE_SUST = {
    "id": "Deutsche Börse AG|successfactors:career:1448078233",
    "title": "Working Student (f/m/d) Sustainability",
    "description": (
        "You bring along: Ongoing Bachelor or Master’s studies in "
        "environmental sciences, public policy, energy, business "
        "administration, communications, or a related field at a "
        "university in Germany until at least March 2028"
    ),
}

# (12) Aptiv J000700630 — corpus vivo: "You are enrolled at a German
# university and studying Electrical Engineering" (morre em
# werkstudent_puro antes).
FIX_APTIV = {
    "id": "Aptiv|sf_dataset:workday:J000700630",
    "title": "Working Student Interior Sensing ML",
    "description": (
        "Your Background: You are enrolled at a German university and "
        "studying Electrical Engineering, Computer Science, or a "
        "related field . You have the ability to program independently "
        "in Python ."
    ),
}

# Fixtures que ALCANÇAM a posição NL/DE da cadeia (nenhum motivo
# anterior preempte): Continental, novemcore, InterNations, DHL,
# Fraunhofer-EN.
CHAIN_POSITIVES = [
    (FIX_CONTINENTAL, "Continental REF99687I (eligible vivo)"),
    (FIX_NOVEMCORE, "novemcore (eligible vivo)"),
    (FIX_INTERNATIONS, "InterNations SR (corpus)"),
    (FIX_DHL, "DHL 384551 (registro 22/10)"),
    (FIX_FRAUNHOFER_EN, "Fraunhofer EN Enrolment (corpus)"),
]

# Fixtures que morrem em motivo ANTERIOR da cadeia (werkstudent_puro /
# thesis_title) — o detector novo é validado em nível de função e a
# re-atribuição é DOCUMENTADA no T4 (comportamento first-match da
# cadeia, não perda de exclusão: o motivo anterior também exclui).
DETECTOR_ONLY_POSITIVES = [
    (FIX_FRAUNHOFER_DE, "Fraunhofer DE Immatrikulation", "thesis_title"),
    (FIX_SYNLAB, "SYNLAB in einer deutschen", "werkstudent_puro"),
    (FIX_EGC, "egc-fmde Semester einer deutschen", "werkstudent_puro"),
    (FIX_DBOERSE_ICT, "Deutsche Börse ICT studies at a German", "werkstudent_puro"),
    (FIX_NORDEX, "Nordex degree program at a German", "werkstudent_puro"),
    (FIX_DBOERSE_SUST, "Deutsche Börse Sustainability university in Germany", "werkstudent_puro"),
    (FIX_APTIV, "Aptiv enrolled at a German", "werkstudent_puro"),
]


def t1_positives() -> None:
    section("T1 — fixtures verbatim positivas (detector + cadeia)")
    for job, name in CHAIN_POSITIVES:
        check(
            f"detector: {name}",
            flt.requires_de_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        got = flt.applicability_exclusion_reason(dict(job))
        check(
            f"cadeia: {name} → de_enrolment_required",
            got == "de_enrolment_required",
            f"cadeia={got!r}",
        )
    for job, name, earlier in DETECTOR_ONLY_POSITIVES:
        check(
            f"detector: {name}",
            flt.requires_de_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        got = flt.applicability_exclusion_reason(dict(job))
        check(
            f"cadeia first-match: {name} morre em {earlier} (antes da "
            "posição NL/DE — exclusão preservada, motivo re-atribuído)",
            got == earlier,
            f"cadeia={got!r}",
        )


# ---------------------------------------------------------------------------
# T2 — counter-cases obrigatórios (NÃO casam)
# ---------------------------------------------------------------------------

# Bosch Pflichtpraktikum gem. SPO (EURES REF285439J) — VERBATIM do
# corpus: matrícula GENÉRICA "an einer Hochschule" (sem "deutschen").
# Estudante internacional satisfaz; NÃO é requisito de matrícula local.
FIX_BOSCH_SPO = {
    "id": "Robert Bosch GmbH|sf_dataset:eures:MTU5ODYtUkVGMjg1NDM5Si1mNGQxMzQ4LVMgMQ",
    "title": "Pflichtpraktikum im Projektmanagement - Digitalisierung "
    "& Automatisier",
    "description": (
        "Beginn: ab September / Oktober 2026  Dauer: 6 Monate "
        "(ausschließlich Pflichtpraktikum gem. SPO möglich)  "
        "Voraussetzung für das Praktikum ist die Immatrikulation an "
        "einer Hochschule. Bitte füge deiner Bewerbung deinen "
        "Lebenslauf, deinen aktuellen Notenspiegel, eine aktuelle "
        "Immatrikulationsbescheinigung, deine Prüfungsordnung sowie "
        "ggf. eine gültige Arbeits- und Aufenthaltserlaubnis bei."
    ),
}

# Duales Studium BASF (DHBW Mannheim) — VERBATIM: "Duale Hochschule
# Baden-Württemberg (DHBW) in Mannheim als Kooperationspartner" — classe
# DUAL (job_type F86), sem "an/in einer deutschen".
FIX_DUAL_BASF = {
    "id": "BASF SE|successfactors:basf:1383478733",
    "title": "Duales Studium (B.Sc.) - Informatik mit Ausrichtung "
    "Künstlic",
    "description": (
        "Begeisterung für innovative Entwicklungen im IT-Umfeld hohe "
        "Zuverlässigkeit, sehr gute Kommunikationsfähigkeit DAS BIETEN "
        "WIR IN DEINEM DUALEN STUDIUM Duale Hochschule "
        "Baden-Württemberg (DHBW) in Mannheim als Kooperationspartner "
        "Individuell ausgewählte Praxisphasen"
    ),
}

# KPMG Duales Studium — VERBATIM: "Arbeite neben Deinem Studium an
# spannenden Projekten" — "Studium an" SEM "einer deutschen".
FIX_DUAL_KPMG = {
    "id": "KPMG International Cooperative|successfactors:jobs:1219523701",
    "title": "Duales Studium Steuern, Prüfungswesen, Consulting Duale "
    "Hochschule Sachsen (w/m/d)",
    "description": (
        "Du möchtest mit uns in Deine berufliche Zukunft starten? Dann "
        "komm an Bord und werde Teil unseres Teams. Arbeite neben "
        "Deinem Studium an spannenden Projekten, erhalte Einblicke in "
        "unser Tagesgeschäft und baue Dir von"
    ),
}

# Würth — VERBATIM: "Du machst aus einer deutschen Erfolgsgeschichte
# einen globalen Standard" — "einer deutschen" SEM palavra de
# instituição (o guard do padrão 2).
FIX_WUERTH = {
    "id": "Würth Group|x",
    "title": "Senior Project Manager E-Commerce (m/w/d)",
    "description": (
        "von lokalen Kundenwünschen und kulturellen Unterschieden bis "
        "hin zu technischen oder rechtlichen Rahmenbedingungen. Du "
        "machst aus einer deutschen Erfolgsgeschichte einen globalen "
        "Standard und siehst direkt"
    ),
}

# "based in Germany" SOLTO — residência/localização do CANDIDATO/TEAM/
# ROLE, outra classe (fora de escopo da F106). Verbatim do corpus:
FIX_BAYER_RESIDENCE = {
    "id": "Bayer|eightfold:bayer:891618",
    "title": "Agentic AI Internship (All Genders)",
    "description": (
        "You are a final-year student in Computer Science, Software "
        "Engineering, Artificial Intelligence, or a related field You "
        "have hands-on experience building full-stack applications You "
        "are based in Germany You communicate confidently in English"
    ),
}

FIX_BASF_TEAM = {
    "id": "BASF SE|successfactors:basf:1409352533",
    "title": "IAM Architect - Identity & Access Management (m/f/d)",
    "description": (
        "Submit your CV in English through the job posting so we can "
        "get to know each other. If your profile matches, our Spanish "
        "Talent Acquisition team based in Germany will contact you "
        "(phone prefix +49) and guide you through the process."
    ),
}

FIX_TESLA_ROLE = {
    "id": "Tesla Germany GmbH|sf_dataset:eures:MTUxNTgtMjAyNjI4MTU0Mi1TIDE",
    "title": "EHS Specialist Internship (m/w/d) (Sekretär/in)",
    "description": (
        "The ideal candidate takes pride in his or her analytical "
        "abilities. The Internship Role is based in Germany and "
        "reports to the EHS Lead."
    ),
}

FIX_HRW_STIPEND = {
    "id": "humanrightswatch|sf_dataset:greenhouse:8889167002",
    "title": "Development & Outreach Department Intern",
    "description": (
        "Applicants must possess valid work authorization in Germany "
        "for the duration of the internship. Interns based in Germany "
        "will receive a gross monthly stipend of EUR 556 per month."
    ),
}

# Neutro: vaga de Einkauf sem qualquer sinal de matrícula local.
FIX_NEUTRAL = {
    "id": "neutro|x",
    "title": "Praktikum Einkauf (m/w/d)",
    "description": (
        "Du unterstützt das Einkaufsteam bei der Beschaffung von "
        "Materialien und der Pflege von Stammdaten. Sehr gute "
        "Englischkenntnisse runden dein Profil ab."
    ),
}

COUNTER_CASES = [
    (FIX_BOSCH_SPO, "Bosch SPO: matrícula GENÉRICA an einer Hochschule"),
    (FIX_DUAL_BASF, "Duale Hochschule BASF: classe DUAL"),
    (FIX_DUAL_KPMG, "KPMG: 'Studium an spannenden' sem 'einer deutschen'"),
    (FIX_WUERTH, "Würth: 'aus einer deutschen Erfolgsgeschichte'"),
    (FIX_BAYER_RESIDENCE, "Bayer: 'You are based in Germany' (residência)"),
    (FIX_BASF_TEAM, "BASF: 'team based in Germany' (localização)"),
    (FIX_TESLA_ROLE, "Tesla: 'Role is based in Germany' (localização)"),
    (FIX_HRW_STIPEND, "HRW: 'Interns based in Germany' (estipêndio)"),
    (FIX_NEUTRAL, "neutro sem sinal"),
]


def t2_counter_cases() -> None:
    section("T2 — counter-cases obrigatórios (não casam)")
    for job, name in COUNTER_CASES:
        check(
            f"detector NÃO casa: {name}",
            not flt.requires_de_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        got = flt.applicability_exclusion_reason(dict(job))
        check(
            f"cadeia mantém (None): {name}",
            got is None,
            f"cadeia={got!r}",
        )


# ---------------------------------------------------------------------------
# T3 — regressão F99 (classe NL intacta) + overlap NL×DE zero
# ---------------------------------------------------------------------------

# Avery Dennison 744000155457544 — fixture F99: "currently enrolled at a
# Dutch university" → nl_enrolment_required (o motivo NÃO muda).
FIX_AVERY = {
    "id": "Avery Dennison|744000155457544",
    "title": "Internship",
    "description": (
        "You must be currently enrolled at a Dutch university for the "
        "entire duration of your internship."
    ),
}

# YETI JR102248 — fixture F99: AUAS por sigla no título e por extenso.
FIX_YETI = {
    "id": "YETI|sf_dataset:workday:JR102248",
    "title": "Business Operations Internship for AUAS Students",
    "description": "Currently pursuing a degree at the Amsterdam "
    "University of Applied Sciences.",
}

# Vanderlande R31 — fixture F37: "Mandatory enrolment to a Dutch
# Education System & resident of The Netherlands".
FIX_VANDERLANDE = {
    "id": "vanderlande|JR38233",
    "title": "Internship: Finance process automation & AI",
    "description": (
        "Mandatory enrolment to a Dutch Education System & resident of "
        "The Netherlands."
    ),
}

# Parfumado R12 — fixture F37: "enrolled in an HBO/WO programme".
FIX_PARFUMADO = {
    "id": "Parfumado|R12",
    "title": "Internship",
    "description": "You are enrolled in an HBO/WO programme.",
}


def t3_f99_regression() -> None:
    section("T3 — regressão F99: classe NL intacta, overlap NL×DE zero")
    nl_fixtures = [
        (FIX_AVERY, "Avery Dennison (extensão F99)"),
        (FIX_YETI, "YETI AUAS (extensão F99)"),
        (FIX_VANDERLANDE, "Vanderlande R31 (F37)"),
        (FIX_PARFUMADO, "Parfumado HBO/WO (F37)"),
    ]
    for job, name in nl_fixtures:
        check(
            f"NL intacta: {name} → requires_nl_enrolment",
            flt.requires_nl_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        check(
            f"NL intacta: {name} NÃO vira de_enrolment (detector)",
            not flt.requires_de_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        got = flt.applicability_exclusion_reason(dict(job))
        check(
            f"NL intacta: {name} → cadeia nl_enrolment_required",
            got == "nl_enrolment_required",
            f"cadeia={got!r}",
        )
    # overlap inverso: os padrões DE não ativam o detector NL
    for pos in CHAIN_POSITIVES + DETECTOR_ONLY_POSITIVES:
        job, name = pos[0], pos[1]
        check(
            f"overlap zero: {name} NÃO ativa requires_nl_enrolment",
            not flt.requires_nl_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
    # first-match: texto com AMBOS os sistemas (hipotético) → NL vence
    # (posição anterior na cadeia); nenhum caso real de overlap no
    # corpus, o teste fixa a semântica do first-match.
    check(
        "first-match NL > DE (texto híbrido hipotético)",
        flt.applicability_exclusion_reason(
            {
                "title": "Internship",
                "description": "You must be enrolled at a Dutch "
                "university. Immatrikulation an einer deutschen "
                "Hochschule ist ebenfalls willkommen.",
            }
        )
        == "nl_enrolment_required",
    )


# ---------------------------------------------------------------------------
# T4 — mecanismo F37.3 (tuplas, posição, JSON-tuple, legenda)
# ---------------------------------------------------------------------------

def _with_country(job: dict) -> dict:
    """Carimbo de país para a fixture passar pelos gates student/area/
    country da cascata e ALCANÇAR o estágio de aplicabilidade (padrão
    _job do test_f37: "país não é o alvo aqui")."""
    return {**job, "location": "Berlin, DE", "country_iso": "de"}


def t4_mechanism() -> None:
    section("T4 — tuplas F37.3 + posição + legenda pt-BR + re-atribuição")
    check(
        "de_enrolment_required em APPLICABILITY_EXCLUSION_REASONS",
        "de_enrolment_required" in flt.APPLICABILITY_EXCLUSION_REASONS,
    )
    reasons = flt.APPLICABILITY_EXCLUSION_REASONS
    check(
        "posição: imediatamente após nl_enrolment_required (irmã da classe)",
        reasons.index("de_enrolment_required")
        == reasons.index("nl_enrolment_required") + 1,
    )
    check(
        "de_enrolment_required NÃO em APPLICABILITY_JSON_EXCLUSION_"
        "REASONS (padrão nl_enrolment: cascata exclui; pós-hidratação "
        "só demove — mesma decisão da classe NL na F99)",
        "de_enrolment_required" not in flt.APPLICABILITY_JSON_EXCLUSION_REASONS
        and "nl_enrolment_required" not in flt.APPLICABILITY_JSON_EXCLUSION_REASONS,
    )
    labels = ptbr.APPLICABILITY_REASON_LABELS
    missing = [
        r for r in flt.APPLICABILITY_EXCLUSION_REASONS if r not in labels
    ]
    check(
        "legenda pt-BR cobre TODOS os motivos da cadeia",
        not missing,
        f"faltando={missing}",
    )
    check(
        "legenda nova 🇩🇪 (paralela à 🇳🇱 da classe NL)",
        "🇩🇪" in labels.get("de_enrolment_required", "")
        and "🇳🇱" in labels.get("nl_enrolment_required", ""),
    )
    # rótulo do funil de candidaturas (consumido pelo digest ✂ — best
    # effort, fallback chave crua)
    try:
        import funnel_report as _fr  # noqa: E402

        check(
            "funnel_report.DEATH_LABELS cobre de_enrolment_required",
            _fr.death_label("de_enrolment_required")
            != "de_enrolment_required",
            _fr.death_label("de_enrolment_required"),
        )
    except Exception as exc:  # noqa: BLE001 — import é best-effort
        check("funnel_report importável", False, repr(exc))
    # contagem por motivo no contrato da cascata (a chave existe mesmo
    # zerada — padrão test_f18); país carimbado p/ alcançar o estágio
    _, counts = flt.select_eligible(
        [_with_country(dict(FIX_NEUTRAL))], applicability=True
    )
    check(
        "contador da cascata existe (zerado para neutro)",
        counts.get("aplicabilidade_excluidas_de_enrolment_required") == 0
        and counts.get("aplicabilidade") == 1,
    )


# ---------------------------------------------------------------------------
# T5 — integração select_eligible (cascata real)
# ---------------------------------------------------------------------------

def t5_select_eligible() -> None:
    section("T5 — integração select_eligible (cascata real)")
    # Continental sozinha → sai com o motivo novo contado.
    sel, counts = flt.select_eligible(
        [_with_country(dict(FIX_CONTINENTAL))], applicability=True
    )
    check(
        "Continental sai da cascata (0 mantidas)",
        len(sel) == 0,
        f"kept={len(sel)}",
    )
    check(
        "contador por motivo: aplicabilidade_excluidas_"
        "de_enrolment_required == 1",
        counts.get("aplicabilidade_excluidas_de_enrolment_required") == 1,
    )
    # lote misto: Continental (sai) + neutro Einkauf (fica) + Supply
    # Chain Intern com o texto VERBATIM da InterNations (sai) → contagens
    # exatas por motivo. (A InterNations real — "People Experience
    # Intern" — morre na camada de ÁREA antes da aplicabilidade; o
    # counter-case Bosch SPO idem (Projektmanagement/Digitalisierung) e
    # é coberto no T2. A cadeia sem gates (T1) já valida os dois.)
    internations_area = {
        **FIX_INTERNATIONS,
        "title": "Supply Chain Intern (m/f/d)",
    }
    sel, counts = flt.select_eligible(
        [
            _with_country(dict(FIX_CONTINENTAL)),
            _with_country(dict(FIX_NEUTRAL)),
            _with_country(internations_area),
        ],
        applicability=True,
    )
    check(
        "lote misto: só o neutro Einkauf fica",
        len(sel) == 1 and sel[0].get("id") == FIX_NEUTRAL["id"],
        f"kept={[j.get('id') for j in sel]}",
    )
    check(
        "lote misto: de_enrolment_required == 2 (Continental+InterNations)",
        counts.get("aplicabilidade_excluidas_de_enrolment_required") == 2,
    )
    # reversibilidade: --no-applicability desliga o estágio inteiro
    # (comportamento pré-F18); as chaves por motivo NEM EXISTEM.
    sel_off, counts_off = flt.select_eligible(
        [
            _with_country(dict(FIX_CONTINENTAL)),
            _with_country(dict(FIX_NEUTRAL)),
        ],
        applicability=False,
    )
    check(
        "applicability=False mantém todas (reversível, pré-F18)",
        len(sel_off) == 2
        and "aplicabilidade_excluidas_de_enrolment_required" not in counts_off,
        f"kept={len(sel_off)}",
    )


# ---------------------------------------------------------------------------
# T6 — controles negativos (cadeia None, drift simulado)
# ---------------------------------------------------------------------------

NEGATIVES = [
    {"id": "neg|1", "title": "Praktikum Einkauf (m/w/d)",
     "description": "Du unterstützt das Einkaufsteam bei der "
     "Beschaffung von Materialien und der Pflege von Stammdaten. Sehr "
     "gute Englischkenntnisse runden dein Profil ab."},
    {"id": "neg|2", "title": "Supply Chain Intern",
     "description": "Support the planning team with daily operations, "
     "data analysis and reporting. Enrolled student for the whole "
     "duration of the internship."},
    {"id": "neg|3", "title": "Procurement Internship - 6 months",
     "description": "This is a 6-month internship focused on vendor "
     "management and procurement analytics in our Amsterdam office."},
]


def t6_negatives() -> None:
    section("T6 — controles negativos: cadeia None + drift simulado")
    for job in NEGATIVES:
        got = flt.applicability_exclusion_reason(dict(job))
        check(f"{job['id']} fica (None)", got is None, f"cadeia={got!r}")
    # variantes que NÃO devem casar (drift simulado dos padrões)
    drift = [
        ("cooperativa: 'with a German university'",
         "In cooperation with a German university, we offer this "
         "programme."),
        ("genérica: 'Immatrikulation an einer Hochschule'",
         "Voraussetzung ist die Immatrikulation an einer Hochschule."),
        ("dual: 'Duale Hochschule' solta",
         "Die Theorie absolvierst Du an der Dualen Hochschule."),
        ("sem article: 'at the German University in Cairo'",
         "You are enrolled at the German University in Cairo."),
        ("cidade: 'in einer deutschen Stadt'",
         "Unser Büro liegt in einer deutschen Stadt mit guter "
         "Anbindung."),
        ("residência: 'based in Germany' sem university",
         "You are based in Germany for the duration of the internship."),
    ]
    for name, desc in drift:
        check(
            f"drift não casa: {name}",
            not flt.requires_de_enrolment("x", desc),
        )
    # desc vazia / None não crasha (padrão test_f99)
    check(
        "desc vazia/None não crasha",
        flt.requires_de_enrolment("Praktikum", "") is False
        and flt.requires_de_enrolment("Praktikum", None) is False,
    )


def main() -> int:
    t1_positives()
    t2_counter_cases()
    t3_f99_regression()
    t4_mechanism()
    t5_select_eligible()
    t6_negatives()
    print(f"\n==== test_f106: {CHECKS} checks, {len(FAILURES)} falhas ====")
    if FAILURES:
        for f in FAILURES:
            print(f"  [FAIL] {f}")
        return 1
    print("==== test_f106 OK ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
