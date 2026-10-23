#!/usr/bin/env python3
"""Testes da Fase F99 — requisitos duros de elegibilidade (100% offline).

Origem: verificação independente do Brainstorm_Visto (21/10, erratas
E1/E4/E5/E6/E8) — 6 classes de requisito DURO escaparam de TODA a triagem
e chegaram ao documento de estratégia como vagas "aplicáveis" quando NÃO
são, para o perfil do dono (aluno de graduação não-UE, UFSCar, início
≥ jan/2027, nativo PT-BR): native-language (ISS JR_10434, score 13.0 — a
maior do dataset), EU-national-only (AWS ESC 10571716), local-enrollment
NL (Avery Dennison, YETI), completed-master (ISS DACH JR_10438, AGFA,
Oliver Wyman), recent-graduate (auto1), 1-year-conflict (Delivery Hero).

Grupos de teste:

- **T1 FIXTURES VERBATIM (9)** — as 8 do archive 20261021T090001Z
  (descrição real coletada) + Delivery Hero 744000155973854 (frase
  verbatim da página viva, confirmada 22/10 — a descrição do DATASET não
  carrega a frase: gap de captura upstream documentado no relatório).
  Cada fixture → motivo esperado (novo OU estendido).
- **T2 COUNTER-CASES OBRIGATÓRIOS (4)** — OR-semantics NÃO exclui: DB
  Controlling LU ("enrolled ... or have graduated ... no more than 6
  months"), Wellington ("current enrolment in, or recent completion
  of"), Nestlé ("obtained or are currently pursuing"), JDE ("mandatory
  part of your studies").
- **T3 SEVERIDADE F85** — requisito DURO exclui; "advantage/preferred/
  ideally" NÃO exclui (Kraft Heinz "Ideally native Dutch speaker";
  "German would be an advantage"; "native speaker preferred").
- **T4 GUARDS DOS DETECTORES NOVOS (FPs medidos no A/B)** — faixa com
  piso ≤6 ("6 to 12 months", "6 – 12 Monate Praktikum"), frase-de-data
  ("within 12 months" — Kinaxis), duração de formatura ("graduated in
  the last 12 months"), experiência prévia ("2 years before the
  internship"), pathway ("12-month contract after the internship"),
  OR com estudante ("a student or recent graduate", "nearing the end
  of your studies", "studying in, or recently graduated from"),Bachelor
  aceito ("Bachelor's final year or Master's", "undergraduate or
  master's degree student" — neutralizador F99).
- **T5 FIX CURLY U+2019** — root cause das 3 fixtures de mestrado:
  "Master’s" tipográfico == "Master's" (requires_master + cadeia);
  counter-case Wellington em curly segue FICANDO (neutralizador roda
  pós-normalização); 187/704 vagas do archive carregam U+2019.
- **T6 MECANISMO F37.3** — tuplas (APPLICABILITY_EXCLUSION_REASONS com
  os 3 motivos novos; APPLICABILITY_JSON_EXCLUSION_REASONS com o padrão
  F86), first-match (german_required > native_language; título >
  duração-desc), extensões dos motivos existentes (AWS/Avery/YETI via
  eu_citizenship_required/nl_enrolment_required) e legenda pt-BR
  (ptbr.APPLICABILITY_REASON_LABELS cobre TODOS os motivos).
- **T7 CONTROLES NEGATIVOS** — vagas sem qualquer sinal: cadeia None
  para as 13 fixtures do corpus sem sinal + payload sintético neutro.

Fixtures: VERBATIM do archive de produção 20261021T090001Z (trechos
literais, campos mínimos — padrão test_f86/test_f373). Zero rede, zero
I/O de data/.
Uso:  .venv/bin/python scripts/test_f99.py   (ou bash scripts/test_f99.py)
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
# T1 — fixtures verbatim (archive 20261021T090001Z + página viva)
# ---------------------------------------------------------------------------

# (1) ISS STOXX JR_10434 — native_language (a vaga de MAIOR score do
# dataset 21/10). Verbatim do archive: a lista de línguas derrota o
# german_level (classifica ``plus``).
FIX_NATIVE = {
    "id": "Issgovernance|sf_dataset:workday:JR_10434",
    "title": "Internship - Corporate Governance Data Procurement (m/w/d)",
    "description": (
        "Excellent analytical and communication skills (verbal and "
        "written). A minimum one of the following languages to a native "
        "standard: Russian, Polish, German, Turkish, Danish, Swedish, "
        "Norwegian. A relevant field of study is required."
    ),
}

# (2) AWS ESC 10571716 — eu_citizenship_required (EXTENSÃO F99: o padrão
# literal F37 não cobria "national of an EU member state").
FIX_EU = {
    "id": "AWS European Sovereign Cloud Development Center GmbH - M94|amazon_jobs:10571716",
    "title": "System Engineer internship 2027 (6 months), ESC Managed Operations",
    "description": (
        "Written and spoken English is required. Candidate must be a "
        "national of an EU member state and residing in the EU to operate "
        "the AWS European Sovereign Cloud."
    ),
}

# (3) Avery Dennison — nl_enrolment_required (EXTENSÃO F99: "enrolled at
# a Dutch university" não casava os padrões F37).
FIX_AVERY = {
    "id": "averydennison|sf_dataset:smartrecruiters:744000155457544",
    "title": "Internship: Business Intelligence and Finance Excellence",
    "description": (
        "Language: We only consider applications submitted in English. "
        "Enrollment: You must be currently enrolled at a Dutch university "
        "for the entire duration of your internship. Direct Applicants "
        "Only: We do not accept applications from Recruitment Agencies."
    ),
}

# (4) YETI JR102248 — nl_enrolment_required (EXTENSÃO F99: instituição
# específica NL — título "for AUAS Students" + AUAS por extenso na desc).
FIX_YETI = {
    "id": "YETI|sf_dataset:workday:JR102248",
    "title": "Business Operations Internship for AUAS Students",
    "description": (
        "Currently pursuing a degree in Business Management, Supply "
        "Chain, Logistics, or a related field at the Amsterdam University "
        "of Applied Sciences. Strong organizational, analytical, and "
        "communication skills."
    ),
}

# (5) ISS DACH JR_10438 — master_required (FIX CURLY: "Master’s degree
# or in the process of obtaining such a degree" com U+2019 escapava do
# regex ASCII). A frase "considered an advantage, but not a requirement"
# refere-se a OUTRO item da lista (skills) — o requisito de mestrado vem
# como item próprio e é DURO.
FIX_ISS_DACH = {
    "id": "Issgovernance|sf_dataset:workday:JR_10438",
    "title": "Internship - Corporate Governance Research - DACH Market (m/w/d)",
    "description": (
        "Other skills are considered an advantage, but not a requirement. "
        "A Master\u2019s degree or in the process of obtaining such a degree. "
        "Prior experience in a relevant field is a plus."
    ),
}

# (6) AGFA 454965801 — master_required (FIX CURLY + "studying for" que os
# padrões de estado não tinham — pego pelo "Master’s degree" normalizado).
FIX_AGFA = {
    "id": "AGFA NV|sf_dataset:successfactors:454965801",
    "title": "Internship : DISCOVERY project Advanced Materials Design",
    "description": (
        "Your Profile If you are a student who\u2026. is studying for a "
        "Master\u2019s degree in the following disciplines of Material, "
        "Polymer Science and Technology, Chemistry or Chemical Engineering"
    ),
}

# (7) Oliver Wyman R_364450 — master_required (FIX CURLY + plural
# "students?" — "Ideal for master’s students" é público-alvo, decisão do
# dono via verificação independente).
FIX_OW = {
    "id": "careers.marsh.com|sf_dataset:phenom:R_364450",
    "title": "Oliver Wyman - Data & Analytics Intern Analyst -  Amsterdam",
    "description": (
        "You will work with the latest analytical tools, and apply your "
        "quantitative expertise. Ideal for master\u2019s students in "
        "quantitative disciplines with strong programming skills and a "
        "passion for problem solving."
    ),
}

# (8) auto1 — recent_graduate (classe NOVA; sem alternativa de matrícula
# na janela ±100 do match).
FIX_AUTO1 = {
    "id": "auto1|sf_dataset:smartrecruiters:744000154701234",
    "title": "Intern Financial Planning & Analytics (f/m/x)",
    "description": (
        "Prepare periodic and tactical reports for key stakeholders You "
        "are recent graduate from University, preferably in Business, "
        "Economics, Finance, or in another relevant field of study."
    ),
}

# (9) Delivery Hero — duration_conflict (classe NOVA). FRASE VERBATIM da
# página viva (confirmada 22/10): a descrição do DATASET para esta vaga
# NÃO carrega a frase (gap de captura upstream documentado no relatório
# da fase) — a fixture é o texto do anúncio, não do dataset.
FIX_DELIVERY_HERO = {
    "id": "deliveryhero|sf_dataset:smartrecruiters:744000155973854",
    "title": "Intern, Product GTM & Impact Analytics - Marketplace, Quick Commerce",
    "description": (
        "This is a 1 Year full time Internship and will require full time "
        "work authorization. What You'll Do Support the product team in "
        "shaping and prioritizing features based on user and business needs."
    ),
}

FIXTURES = [
    (FIX_NATIVE, "native_language", "ISS JR_10434"),
    (FIX_EU, "eu_citizenship_required", "AWS ESC 10571716 (extensão)"),
    (FIX_AVERY, "nl_enrolment_required", "Avery Dennison (extensão)"),
    (FIX_YETI, "nl_enrolment_required", "YETI AUAS (extensão)"),
    (FIX_ISS_DACH, "master_required", "ISS DACH JR_10438 (fix curly)"),
    (FIX_AGFA, "master_required", "AGFA (fix curly)"),
    (FIX_OW, "master_required", "Oliver Wyman (fix curly + students?)"),
    (FIX_AUTO1, "recent_graduate", "auto1 (classe nova)"),
    (FIX_DELIVERY_HERO, "duration_conflict", "Delivery Hero (classe nova, verbatim vivo)"),
]


def t1_fixtures() -> None:
    section("T1 — fixtures verbatim: 8 archive + 1 página viva → motivo")
    for job, want, label in FIXTURES:
        got = flt.applicability_exclusion_reason(dict(job))
        check(f"{label} → {want}", got == want, f"cadeia={got!r}")
    # detectores individuais (contrato da função pura)
    check(
        "requires_native_language(JR_10434) True",
        flt.requires_native_language(
            FIX_NATIVE["title"], FIX_NATIVE["description"]
        ),
    )
    check(
        "duration_conflict_description(DeliveryHero) True",
        flt.duration_conflict_description(
            FIX_DELIVERY_HERO["title"], FIX_DELIVERY_HERO["description"]
        ),
    )
    check(
        "targets_recent_graduates(auto1) True",
        flt.targets_recent_graduates(
            FIX_AUTO1["title"], FIX_AUTO1["description"]
        ),
    )


# ---------------------------------------------------------------------------
# T2 — counter-cases OBRIGATÓRIOS (OR-semantics: matriculado qualifica)
# ---------------------------------------------------------------------------

COUNTERS = [
    # DB Controlling LU 1445042933 — "enrolled ... OR have graduated ≤6m"
    {
        "id": "Deutsche Börse AG|sf_dataset:successfactors:1445042933",
        "title": "Intern - Controlling (f/m/d)",
        "description": (
            "Your profile: You are enrolled in a Bachelor's or Master's "
            "Degree program with a recognized institution and can provide "
            "an internship agreement, or have graduated with a Bachelor's "
            "degree or similar for no more than 6 months."
        ),
    },
    # Wellington R94939 — "current enrolment in, or recent completion of"
    {
        "id": "Wellington|sf_dataset:workday:R94939",
        "title": "Compliance Internship - Luxembourg",
        "description": (
            "The candidate is likely to have: Current enrolment in, or "
            "recent completion of, a bachelor's or master's degree in "
            "data science, information systems, business analytics, "
            "finance, economics or a related field."
        ),
    },
    # Nestlé 1441411733 — "obtained or are currently pursuing a degree"
    {
        "id": "nestleHRprdRMK|successfactors:jobdetails:1441411733",
        "title": "Supply Chain (DSP) Intern - Nestlé Waters",
        "description": (
            "Dutch and or French are a plus You have obtained or are "
            "currently pursuing a degree in Economics Business "
            "Administration, Engineering or a related field, ideally with "
            "a specialization in supply chain."
        ),
    },
    # JDE 744000150326658 — "mandatory part of your studies" (estudante)
    {
        "id": "JACOBSDOUWEEGBERTS|sf_dataset:smartrecruiters:744000150326658",
        "title": "Internship / Stage Planning Operations (Supply Chain)",
        "description": (
            "Starting January/February 2027 Your internship is a "
            "mandatory part of your studies. You are a team player with "
            "strong communication and analytical skills."
        ),
    },
]


def t2_counter_cases() -> None:
    section("T2 — counter-cases OR-semantics: NENHUM é excluído")
    for job in COUNTERS:
        got = flt.applicability_exclusion_reason(dict(job))
        label = str(job["id"]).split("|")[-1]
        check(f"{label} fica (None)", got is None, f"cadeia={got!r}")
    # guards individuais
    check(
        "targets_recent_graduates(DB enrolled-or-grad) False",
        not flt.targets_recent_graduates(
            COUNTERS[0]["title"], COUNTERS[0]["description"]
        ),
    )
    check(
        "targets_recent_graduates(Wellington) False",
        not flt.targets_recent_graduates(
            COUNTERS[1]["title"], COUNTERS[1]["description"]
        ),
    )
    check(
        "targets_recent_graduates(Nestlé) False",
        not flt.targets_recent_graduates(
            COUNTERS[2]["title"], COUNTERS[2]["description"]
        ),
    )
    check(
        "requires_master(counter-cases) False (Bachelor's or Master's "
        "neutralizado mesmo em curly)",
        not flt.requires_master(
            COUNTERS[1]["title"], COUNTERS[1]["description"]
        )
        and not flt.requires_master(
            COUNTERS[2]["title"], COUNTERS[2]["description"]
        ),
    )


# ---------------------------------------------------------------------------
# T3 — severidade F85: soft NÃO exclui
# ---------------------------------------------------------------------------

def t3_severity() -> None:
    section("T3 — severidade F85: requisito DURO exclui, soft fica")
    check(
        '"Ideally native Dutch speaker" (Kraft Heinz) fica',
        not flt.requires_native_language(
            "Legal Intern",
            "- Ideally native Dutch speaker or at least, advanced Dutch "
            "language (B2-C1).",
        ),
    )
    check(
        '"native speaker preferred" fica',
        not flt.requires_native_language(
            "x", "A native speaker of German is preferred for this role."
        ),
    )
    check(
        '"native German would be an advantage" fica',
        not flt.requires_native_language(
            "x", "Native German would be an advantage, English is required."
        ),
    )
    check(
        '"native speaker required" EXCLUI',
        flt.requires_native_language(
            "x", "You are a native speaker of Dutch with excellent English."
        ),
    )
    check(
        '"native level English" EXCLUI',
        flt.requires_native_language(
            "x", "English at native level and strong communication skills."
        ),
    )
    check(
        '"mother tongue" EXCLUI',
        flt.requires_native_language(
            "x", "German as mother tongue, written and spoken."
        ),
    )
    check(
        "única língua nativa = português fica (dono é nativo)",
        not flt.requires_native_language(
            "x", "Portuguese to a native standard is required for this role."
        ),
    )


# ---------------------------------------------------------------------------
# T4 — guards dos detectores novos (FPs medidos no A/B do archive)
# ---------------------------------------------------------------------------

def t4_guards() -> None:
    section("T4 — guards duration/recent-grad/master (FPs do A/B)")
    # duration: faixa com piso ≤6 fica (semântica F29/F37)
    check(
        '"6 to 12 months" faixa fica (OMA)',
        not flt.duration_conflict_description(
            "Internship Business Development",
            "- A full-time internship for a period of 6 to 12 months.",
        ),
    )
    check(
        '"6 – 12 Monate Praktikum" faixa fica (Edbz)',
        not flt.duration_conflict_description(
            "Praktikant/in (m/f/d)",
            "- 6 \u2013 12 Monate Praktikum an unserem europäischen "
            "Hauptstandort in Freising",
        ),
    )
    check(
        '"within 12 months" frase-de-data fica (Kinaxis)',
        not flt.duration_conflict_description(
            "Intern Software Developer Quality Assurance",
            "To be eligible for an Internship position at Kinaxis, you "
            "must either be currently enrolled in full-time education or, "
            "if you are a recent/upcoming graduate, your graduation date "
            "must be within 12 months.",
        ),
    )
    check(
        '"graduated in the last 12 months" fica (FP F37 medido)',
        not flt.duration_conflict_description(
            "x",
            "You graduated in the last 12 months and are looking for an "
            "internship.",
        ),
    )
    check(
        '"2 years ... before the internship" fica (experiência prévia)',
        not flt.duration_conflict_description(
            "x",
            "You need at least 2 years of experience before the "
            "internship starts.",
        ),
    )
    check(
        '"12-month contract after the internship" fica (pathway)',
        not flt.duration_conflict_description(
            "x",
            "The internship may lead to a 12-month contract afterwards.",
        ),
    )
    check(
        '"6-month internship" fica (dentro do teto)',
        not flt.duration_conflict_description(
            "x", "This is a 6-month internship in Berlin."
        ),
    )
    check(
        '"an internship of at least 12 months" EXCLUI',
        flt.duration_conflict_description(
            "x", "It is an internship of at least 12 months in Berlin."
        ),
    )
    # recent_graduate: OR com estudante fica
    check(
        '"a student or recent graduate" fica (indiecampers)',
        not flt.targets_recent_graduates(
            "Tourism & Operations Internship",
            "- You are a student or recent graduate in Hospitality, "
            "Tourism, International Studies, Business Administration or a "
            "related field looking for an internship;",
        ),
    )
    check(
        '"recent graduate or nearing the end of your studies" fica (bunch)',
        not flt.targets_recent_graduates(
            "Operations & Strategy Internship",
            "- You are a recent graduate or nearing the end of your "
            "studies",
        ),
    )
    check(
        '"studying in, or recently graduated from" fica (OMA)',
        not flt.targets_recent_graduates(
            "Internship Business Development",
            "- Currently studying in, or recently graduated from, "
            "Architecture school.",
        ),
    )
    # master: Bachelor/undergraduate aceito fica (neutralizador estendido)
    check(
        '"Bachelor\'s final year or Master\'s programme" fica (Resmed)',
        not flt.requires_master(
            "Supply Chain Planning Internship (6 months)",
            "What You Bring Currently enrolled in a Bachelor's final year "
            "or Master's programme in Supply Chain Management, Logistics, "
            "Business Analytics.",
        ),
    )
    check(
        '"undergraduate or master\'s degree student" fica (Tencent)',
        not flt.requires_master(
            "Global Talent Sourcing Intern",
            "Who We Look For Qualifications Currently an undergraduate or "
            "master's degree student in Human Resources or its equivalent.",
        ),
    )
    check(
        '"Bachelor\'s or Master\'s student" fica (Clariant perfil)',
        not flt.requires_master(
            "Intern (m/f/d)",
            "Requirements Bachelor's or Master's student in Industrial "
            "Engineering, Mechanical Engineering.",
        ),
    )
    check(
        '"enrolled in a Master\'s program" EXCLUI (teampicnic — classe F99 '
        "capturada pela normalização)",
        flt.requires_master(
            "Internship - Business Analyst (m/w/d)",
            "<li>Enrolled in a <strong>Master's program</strong> in a "
            "quantitative field.</li>",
        ),
    )


# ---------------------------------------------------------------------------
# T5 — fix curly U+2019 (root cause das 3 fixtures de mestrado)
# ---------------------------------------------------------------------------

def t5_curly() -> None:
    section("T5 — apóstrofo tipográfico U+2019 == ASCII")
    check(
        "requires_master('A Master\u2019s degree...') True (era False pré-F99)",
        flt.requires_master(
            None,
            "A Master\u2019s degree or in the process of obtaining such a "
            "degree.",
        ),
    )
    check(
        "requires_master('A Master's degree...') True (ASCII, regressão zero)",
        flt.requires_master(
            None, "A Master's degree or in the process of obtaining such a degree."
        ),
    )
    check(
        "Wellington counter em curly fica (neutralizador pós-normalização)",
        not flt.requires_master(
            None,
            "Current enrolment in, or recent completion of, a "
            "bachelor\u2019s or master\u2019s degree in data science.",
        ),
    )
    check(
        "normalize_apostrophes é idempotente",
        flt.normalize_apostrophes("Master\u2019s \u2018x\u2019") == "Master's 'x'"
        and flt.normalize_apostrophes(flt.normalize_apostrophes("Master\u2019s"))
        == "Master's",
    )
    check(
        "normalize_apostrophes(None) == ''",
        flt.normalize_apostrophes(None) == "",
    )
    job = {"title": "x", "description": "A Master\u2019s degree is required."}
    check(
        "CADEIA aplica a normalização (curly → master_required)",
        flt.applicability_exclusion_reason(job) == "master_required",
    )


# ---------------------------------------------------------------------------
# T6 — mecanismo F37.3 (tuplas, first-match, extensões, legenda)
# ---------------------------------------------------------------------------

def t6_mechanism() -> None:
    section("T6 — tuplas F37.3 + first-match + extensões + legenda")
    for reason in ("native_language", "duration_conflict", "recent_graduate"):
        check(
            f"APPLICABILITY_EXCLUSION_REASONS contém {reason}",
            reason in flt.APPLICABILITY_EXCLUSION_REASONS,
        )
        check(
            f"APPLICABILITY_JSON_EXCLUSION_REASONS contém {reason} (padrão F86)",
            reason in flt.APPLICABILITY_JSON_EXCLUSION_REASONS,
        )
        check(
            f"is_json_exclusion_reason({reason}) True",
            flt.is_json_exclusion_reason(reason),
        )
    check(
        "german_required > native_language (first-match: alemão verhandlungs-"
        "sicher exigido ganha; 'Muttersprachliches' puro é plus no F18)",
        flt.applicability_exclusion_reason(
            {
                "title": "Praktikum Einkauf (m/w/d)",
                "description": "Verhandlungssichere Deutschkenntnisse sind "
                "erforderlich. A minimum one of the following languages to "
                "a native standard: Russian, Polish.",
            }
        )
        == "german_required",
    )
    check(
        "duration_over_6m (título) > duration_conflict (first-match)",
        flt.applicability_exclusion_reason(
            {
                "title": "Internship - 12 months",
                "description": "This is a 1 Year full time Internship.",
            }
        )
        == "duration_over_6m",
    )
    check(
        "extensão EU: 'national of an EU member state' → eu_citizenship_required",
        flt.requires_eu_citizenship(
            "x",
            "Candidate must be a national of an EU member state and "
            "residing in the EU.",
        ),
    )
    check(
        "guard EU: 'non-EU nationals welcome' NÃO casa",
        not flt.requires_eu_citizenship(
            "x", "Non-EU nationals are welcome to apply with a valid permit."
        ),
    )
    check(
        "extensão NL: 'enrolled at a Dutch university' → nl_enrolment_required",
        flt.requires_nl_enrolment(
            "x",
            "You must be currently enrolled at a Dutch university for the "
            "entire duration of your internship.",
        ),
    )
    check(
        "extensão NL: AUAS (título e por extenso) → nl_enrolment_required",
        flt.requires_nl_enrolment(
            "Business Operations Internship for AUAS Students",
            "Currently pursuing a degree at the Amsterdam University of "
            "Applied Sciences.",
        ),
    )
    check(
        "AUAS solto sem contexto at/in não casa (guard de contexto)",
        not flt.requires_nl_enrolment(
            "x", "The AUAS building is next to our office."
        ),
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
        "badges F99 na legenda (native-language/EU-national-only/"
        "local-enrollment/master/recent-graduate/1-year-conflict)",
        all(
            k in labels
            for k in (
                "native_language",
                "eu_citizenship_required",
                "nl_enrolment_required",
                "master_required",
                "recent_graduate",
                "duration_conflict",
            )
        ),
    )


# ---------------------------------------------------------------------------
# T7 — controles negativos (sem qualquer sinal)
# ---------------------------------------------------------------------------

NEGATIVES = [
    {"id": "neg|1", "title": "Praktikum Einkauf (m/w/d)",
     "description": "Du unterstützt das Einkaufsteam bei der Beschaffung "
     "von Materialien und der Pflege von Stammdaten. Sehr gute "
     "Englischkenntnisse runden dein Profil ab."},
    {"id": "neg|2", "title": "Supply Chain Intern",
     "description": "Support the planning team with daily operations, "
     "data analysis and reporting. Enrolled student for the whole "
     "duration of the internship."},
    {"id": "neg|3", "title": "Procurement Internship - 6 months",
     "description": "This is a 6-month internship focused on vendor "
     "management and procurement analytics in our Amsterdam office."},
]


def t7_negatives() -> None:
    section("T7 — controles negativos: cadeia None")
    for job in NEGATIVES:
        got = flt.applicability_exclusion_reason(dict(job))
        check(f"{job['id']} fica (None)", got is None, f"cadeia={got!r}")
    # drift simulado: variantes dos padrões que NÃO devem casar
    check(
        "desc vazia não crasha (todos os detectores)",
        flt.applicability_exclusion_reason(
            {"id": "neg|4", "title": "Intern", "description": None}
        )
        is None,
    )
    check(
        "título None não crasha",
        flt.duration_conflict_description(None, None) is False
        and flt.targets_recent_graduates(None, None) is False
        and flt.requires_native_language(None, None) is False,
    )


def main() -> int:
    print("F99 — requisitos duros de elegibilidade (native-language/"
          "EU-national/local-enrollment/completed-master/recent-grad/"
          "1-year)")
    t1_fixtures()
    t2_counter_cases()
    t3_severity()
    t4_guards()
    t5_curly()
    t6_mechanism()
    t7_negatives()
    print("\n" + "=" * 60)
    print(f"F99: {CHECKS} checks, {len(FAILURES)} falhas")
    if FAILURES:
        print("FALHAS:", FAILURES)
        return 1
    print("OK — F99 verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
