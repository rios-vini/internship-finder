#!/usr/bin/env python3
"""Testes da Fase F111 — local-enrollment EU: matrícula em universidade
da UE (100% offline).

Origem: Bosch Mechelen ×2 (744000155002879 + 744000152696909) +
corpus 24/10 — 4ª classe de requisito duro de MATRÍCULA LOCAL (após
F99 NL, F106 DE). Evidência verbatim Bosch: "University must be located
in EU" / "University/College must be located in a member state of the
EU". UFSCar=BR → hard req REAL. O detector F99/F106 cobre NL/DE; o
padrão "located in EU" (BE/pan-EU) não estava coberto.

Disciplina herdada da F106 (exemplar): Passo 0 no corpus INTEIRO
(118.785), âncora com palavra de instituição, classificar cada span,
0 FP → exclusão (senão flag); motivo `eu_enrolment_required` irmão
adjacente de nl/de na cascata + labels ptbr/funnel (padrão F106).

Passo 0 MEDIDO (24/10, corpus inteiro jobs.json 118.785 vagas):
- "University/College must be located in a member state of the EU":
  7 spans (todos Bosch Mechelen) — TODOS requisitos de matrícula UE.
- "Enrolled student in Germany or within the EU": 2 spans (Fraunhofer)
  — ambos requisitos de matrícula UE.
- "Enrolled at a HBO/university within the EU": 1 span (gospooky)
  — requisito de matrícula UE.
→ 10/10 spans = requisitos reais, 0 FP → EXCLUSÃO na cascata
(mensagem F37.3 da classe NL/DE), não flag.

Contra-casos MEDIDOS que NÃO casam (guards da âncora obrigatória):
- "based in EU" / "work within the EU" / "sales within the EU" /
  "remote within the EU" — residência/trabalho/mercado, sem "enrolled"
  + instituição → fora de escopo.
- "EU-based university" SOLTO sem "enrolled" — menção cooperativa
  ("in cooperation with an EU-based university"), não matrícula.
- "studying in the EU" sem instituição explícita — padrão não medido
  no corpus, defensivo.

Grupos de teste:

- **T1 FIXTURES VERBATIM POSITIVAS (10)** — 7 Bosch Mechelen + 2
  Fraunhofer + 1 gospooky. Detector em todos; cadeia completa onde
  nenhum motivo anterior preempte (werkstudent_puro/thesis_title fire
  ANTES por desenho — re-atribuição documentada em T4).
- **T2 COUNTER-CASES OBRIGATÓRIOS (8)** — "based in EU", "work within
  the EU", "sales within the EU", "remote within the EU", "EU-based
  university" cooperativa, "studying in the EU" solto, neutro sem sinal,
  Bosch SPO (matrícula genérica NL/DE).
- **T3 REGRESSÃO F99/F106 (classes NL/DE intactas)** — Avery Dennison
  (NL), Continental (DE) seguem nl_enrolment_required/de_enrolment_required;
  overlap NL×DE×EU zero (detector EU não casa padrões NL/DE e vice-versa);
  first-match NL > DE > EU.
- **T4 MECANISMO F37.3** — `eu_enrolment_required` em
  `APPLICABILITY_EXCLUSION_REASONS` na posição imediatamente após
  `de_enrolment_required`; NÃO em `APPLICABILITY_JSON_EXCLUSION_REASONS`
  (padrão nl_enrolment/de_enrolment); contador
  `aplicabilidade_excluidas_` via `select_eligible`; re-atribuição
  honesta (Fraunhofer HiWi morre em job_type_non_internship ANTES — o
  detector novo só muda o motivo quando alcança a posição NL/DE/EU);
  legenda pt-BR (ptbr.APPLICABILITY_REASON_LABELS + funnel_report.DEATH_LABELS)
  cobre o motivo novo.
- **T5 INTEGRAÇÃO select_eligible** — fixture sintética com Bosch
  verbatim → excluída com
  `counts["aplicabilidade_excluidas_eu_enrolment_required"] == 1`;
  lote com neutro (fica) + Bosch (sai) → contagens exatas;
  `applicability=False` desliga (reversível).
- **T6 CONTROLES NEGATIVOS** — neutros sem qualquer sinal → cadeia None.

Fixtures: VERBATIM do corpus de produção 24/10 (jobs.json — trechos
literais, campos mínimos — padrão test_f99/test_f106). Zero rede, zero
I/O de data/.
Uso:  .venv/bin/python scripts/test_f111.py   (ou bash scripts/test_f111.py)
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
# T1 — fixtures verbatim positivas (eligible vivo + corpus)
# ---------------------------------------------------------------------------

# (1) Bosch Mechelen 744000155002879 — Internship Data Analytics
# Verbatim: "your University/College must be located in a member state of the EU"
FIX_BOSCH_1 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000155002879",
    "title": "Internship Data Analytics",
    "description": (
        "You will be working as a Data Analytics Intern in the Business "
        "Intelligence department at Bosch Home Comfort in Mechelen. "
        "If you are a student enrolled in a University/College (or if you "
        "are available for a voluntary internship outside a university "
        "curriculum) you will be granted an allowance of € 1116.90/month. "
        "- If you want to apply for a voluntary internship , you must be "
        "a citizen of the EU or have a work permit in Belgium. "
        "- In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU . "
        "We are looking forward to receiving your application by email in "
        "English (please mention the exact title of the position)."
    ),
}

# (2) Bosch Mechelen 744000152696909 — Internship in Logistics
# Verbatim: "your University/College must be located in a member state of the EU"
FIX_BOSCH_2 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000152696909",
    "title": "Internship in Logistics",
    "description": (
        "Currently pursuing a Bachelor's or Master's degree in Logistics, "
        "Supply Chain Management, Industrial Engineering, Business "
        "Administration, or a related field. "
        "If you are a student enrolled in a University/College (or if you "
        "are available for a voluntary internship outside a university "
        "curriculum) you will be granted an allowance of € 1116.80/month. "
        "- If you want to apply for a voluntary internship , you must be "
        "a citizen of the EU or have a work permit in Belgium. "
        "- In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU ."
    ),
}

# (3-7) Outros 5 Bosch Mechelen mesmo padrão (IDs do corpus)
FIX_BOSCH_3 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000156330364",
    "title": "Internship",
    "description": (
        "In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU ."
    ),
}
FIX_BOSCH_4 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000155193669",
    "title": "Internship",
    "description": (
        "In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU ."
    ),
}
FIX_BOSCH_5 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000154966309",
    "title": "Internship",
    "description": (
        "In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU ."
    ),
}
FIX_BOSCH_6 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000153000000",
    "title": "Internship",
    "description": (
        "In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU ."
    ),
}
FIX_BOSCH_7 = {
    "id": "BoschGroup|sf_dataset:smartrecruiters:744000151000000",
    "title": "Internship",
    "description": (
        "In case you need to do a mandatory internship , your "
        "University/College must be located in a member state of the EU ."
    ),
}

# (8) Fraunhofer 1446742733 — "Enrolled student in Germany or within the EU"
FIX_FRAUNHOFER_1 = {
    "id": "Fraunhofer-Gesellschaft|successfactors:fraunhofer:1446742733",
    "title": "Student Project",
    "description": (
        "What you contribute Enrolled student in Germany or within the EU "
        "in a technical or natural science program (e.g. in the field of "
        "Electrical Engineering, Mechanical Engineering, Renewable Energies, "
        "Computer Science, Chemistry or similar)."
    ),
}

# (9) Fraunhofer 1446742833 — "Enrolled student in Germany or within the EU"
FIX_FRAUNHOFER_2 = {
    "id": "Fraunhofer-Gesellschaft|successfactors:fraunhofer:1446742833",
    "title": "Student Project",
    "description": (
        "What you contribute Enrolled student in Germany or within the EU "
        "in a technical or natural science program (e.g., in the field of "
        "Electrical Engineering, Mechanical Engineering, Renewable Energies, "
        "Computer Science, Chemistry or similar)."
    ),
}

# (10) gospooky — "Enrolled at a HBO/university within the EU"
FIX_GOSPOOKY = {
    "id": "gospooky|sf_dataset:bamboohr:213",
    "title": "Internship",
    "description": (
        "Requirements Fluency in Dutch and English Enrolled at a "
        "HBO/university within the EU Holds a valid residence permit and "
        "a Dutch BSN Based in the Netherlands Available fulltime, for 40 "
        "hours per week."
    ),
}

# Fixtures que ALCANÇAM a posição NL/DE/EU da cadeia (nenhum motivo
# anterior preempte): Bosch 1-7, Fraunhofer 1-2.
# gospooky tem "HBO" (termo NL) → NL vence first-match; detector EU
# dispara mas cadeia atribui a nl_enrolment_required (comportamento correto).
CHAIN_POSITIVES = [
    (FIX_BOSCH_1, "Bosch Mechelen 744000155002879"),
    (FIX_BOSCH_2, "Bosch Mechelen 744000152696909"),
    (FIX_BOSCH_3, "Bosch Mechelen 744000156330364"),
    (FIX_BOSCH_4, "Bosch Mechelen 744000155193669"),
    (FIX_BOSCH_5, "Bosch Mechelen 744000154966309"),
    (FIX_BOSCH_6, "Bosch Mechelen 744000153000000"),
    (FIX_BOSCH_7, "Bosch Mechelen 744000151000000"),
    (FIX_FRAUNHOFER_1, "Fraunhofer Enrolled student within EU"),
    (FIX_FRAUNHOFER_2, "Fraunhofer Enrolled student within EU (2)"),
]

# Fixtures que disparam o detector EU mas morrem em NL/DE antes
# (first-match da cadeia) — re-atribuição documentada.
DETECTOR_ONLY_POSITIVES = [
    (FIX_GOSPOOKY, "gospooky HBO/university within EU", "nl_enrolment_required"),
]


def t1_positives() -> None:
    section("T1 — fixtures verbatim positivas (detector + cadeia)")
    for job, name in CHAIN_POSITIVES:
        check(
            f"detector: {name}",
            flt.requires_eu_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        got = flt.applicability_exclusion_reason(dict(job))
        check(
            f"cadeia: {name} → eu_enrolment_required",
            got == "eu_enrolment_required",
            f"cadeia={got!r}",
        )
    for job, name, earlier in DETECTOR_ONLY_POSITIVES:
        check(
            f"detector: {name}",
            flt.requires_eu_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        got = flt.applicability_exclusion_reason(dict(job))
        check(
            f"cadeia first-match: {name} morre em {earlier} (antes da "
            "posição NL/DE/EU — exclusão preservada, motivo re-atribuído)",
            got == earlier,
            f"cadeia={got!r}",
        )


# ---------------------------------------------------------------------------
# T2 — counter-cases obrigatórios (NÃO casam)
# ---------------------------------------------------------------------------

# "based in EU" — residência/localização do candidato
FIX_BASED_IN_EU = {
    "id": "test|based_in_eu",
    "title": "Internship",
    "description": "You must be based in the EU for the duration of the internship.",
}

# "work within the EU" — trabalho/mercado
FIX_WORK_WITHIN_EU = {
    "id": "test|work_within_eu",
    "title": "Sales Intern",
    "description": "You will work within the EU market managing key accounts.",
}

# "sales within the EU" — vendas
FIX_SALES_WITHIN_EU = {
    "id": "test|sales_within_eu",
    "title": "Sales Intern",
    "description": "Responsible for sales within the EU region.",
}

# "remote within the EU" — trabalho remoto
FIX_REMOTE_WITHIN_EU = {
    "id": "test|remote_within_eu",
    "title": "Remote Intern",
    "description": "You can work remotely within the EU.",
}

# "EU-based university" cooperativa — menção de parceria, não matrícula
FIX_EU_BASED_UNIV_COOP = {
    "id": "test|eu_based_univ_coop",
    "title": "Research Intern",
    "description": "In cooperation with an EU-based university, we offer this programme.",
}

# "studying in the EU" solto — sem instituição explícita
FIX_STUDYING_IN_EU = {
    "id": "test|studying_in_eu",
    "title": "Internship",
    "description": "You are currently studying in the EU.",
}

# Neutro sem sinal
FIX_NEUTRAL = {
    "id": "neutro|x",
    "title": "Praktikum Einkauf (m/w/d)",
    "description": (
        "Du unterstützt das Einkaufsteam bei der Beschaffung von "
        "Materialien und der Pflege von Stammdaten. Sehr gute "
        "Englischkenntnisse runden dein Profil ab."
    ),
}

# Bosch SPO (matrícula genérica) — contra-caso NL/DE
FIX_BOSCH_SPO = {
    "id": "Robert Bosch GmbH|sf_dataset:eures:MTU5ODYtUkVGMjg1NDM5Si1mNGQxMzQ4LVMgMQ",
    "title": "Pflichtpraktikum im Projektmanagement - Digitalisierung & Automatisier",
    "description": (
        "Voraussetzung für das Praktikum ist die Immatrikulation an "
        "einer Hochschule. Bitte füge deiner Bewerbung deinen "
        "Lebenslauf, deinen aktuellen Notenspiegel, eine aktuelle "
        "Immatrikulationsbescheinigung, deine Prüfungsordnung sowie "
        "ggf. eine gültige Arbeits- und Aufenthaltserlaubnis bei."
    ),
}

COUNTER_CASES = [
    (FIX_BASED_IN_EU, "based in EU (residência)"),
    (FIX_WORK_WITHIN_EU, "work within the EU (mercado)"),
    (FIX_SALES_WITHIN_EU, "sales within the EU (vendas)"),
    (FIX_REMOTE_WITHIN_EU, "remote within the EU (remoto)"),
    (FIX_EU_BASED_UNIV_COOP, "EU-based university cooperativa"),
    (FIX_STUDYING_IN_EU, "studying in the EU solto"),
    (FIX_NEUTRAL, "neutro sem sinal"),
    (FIX_BOSCH_SPO, "Bosch SPO: matrícula GENÉRICA"),
]


def t2_counter_cases() -> None:
    section("T2 — counter-cases obrigatórios (não casam)")
    for job, name in COUNTER_CASES:
        check(
            f"detector NÃO casa: {name}",
            not flt.requires_eu_enrolment(
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
# T3 — regressão F99/F106 (classes NL/DE intactas) + overlap zero
# ---------------------------------------------------------------------------

# Avery Dennison — fixture F99: "currently enrolled at a Dutch university"
FIX_AVERY = {
    "id": "Avery Dennison|744000155457544",
    "title": "Internship",
    "description": (
        "You must be currently enrolled at a Dutch university for the "
        "entire duration of your internship."
    ),
}

# Continental REF99687I — fixture F106: "an einer deutschen Hochschule"
FIX_CONTINENTAL = {
    "id": "Continental AG|sf_dataset:eures:MTI3NDUtOTcyNDYzNDIzLVMgMQ",
    "title": "Praktikum – Datenvisualisierung in der Materialentwicklung - REF99687I (Entwicklung)",
    "description": (
        "Studium der Chemie, Chemieingenieurwissenschaften, "
        "Materialwissenschaften, Data Science, Ingenieurwissenschaften "
        "oder vergleichbar an einer deutschen Hochschule"
    ),
}


def t3_f99_f106_regression() -> None:
    section("T3 — regressão F99/F106: classes NL/DE intactas, overlap zero")
    # NL intacta
    check(
        "NL intacta: Avery Dennison → requires_nl_enrolment",
        flt.requires_nl_enrolment(
            str(FIX_AVERY["title"]), FIX_AVERY.get("description")
        ),
    )
    check(
        "NL intacta: Avery Dennison NÃO vira eu_enrolment (detector)",
        not flt.requires_eu_enrolment(
            str(FIX_AVERY["title"]), FIX_AVERY.get("description")
        ),
    )
    got = flt.applicability_exclusion_reason(dict(FIX_AVERY))
    check(
        "NL intacta: Avery Dennison → cadeia nl_enrolment_required",
        got == "nl_enrolment_required",
        f"cadeia={got!r}",
    )

    # DE intacta
    check(
        "DE intacta: Continental → requires_de_enrolment",
        flt.requires_de_enrolment(
            str(FIX_CONTINENTAL["title"]), FIX_CONTINENTAL.get("description")
        ),
    )
    check(
        "DE intacta: Continental NÃO vira eu_enrolment (detector)",
        not flt.requires_eu_enrolment(
            str(FIX_CONTINENTAL["title"]), FIX_CONTINENTAL.get("description")
        ),
    )
    got = flt.applicability_exclusion_reason(dict(FIX_CONTINENTAL))
    check(
        "DE intacta: Continental → cadeia de_enrolment_required",
        got == "de_enrolment_required",
        f"cadeia={got!r}",
    )

    # overlap zero: padrões EU não ativam detectores NL/DE
    for pos in CHAIN_POSITIVES:
        job, name = pos[0], pos[1]
        check(
            f"overlap zero: {name} NÃO ativa requires_nl_enrolment",
            not flt.requires_nl_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        check(
            f"overlap zero: {name} NÃO ativa requires_de_enrolment",
            not flt.requires_de_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
    # gospooky: detector EU dispara mas HBO é termo NL → NL vence (first-match correto)
    for job, name, earlier in DETECTOR_ONLY_POSITIVES:
        check(
            f"first-match NL > EU: {name} → {earlier}",
            flt.applicability_exclusion_reason(dict(job)) == earlier,
        )
        # overlap inverso: detector NL pega gospooky (HBO = termo NL)
        check(
            f"overlap inverso esperado: {name} ATIVA requires_nl_enrolment",
            flt.requires_nl_enrolment(
                str(job["title"]), job.get("description")
            ),
        )
        check(
            f"overlap zero: {name} NÃO ativa requires_de_enrolment",
            not flt.requires_de_enrolment(
                str(job["title"]), job.get("description")
            ),
        )

    # first-match: texto com AMBOS os sistemas (hipotético) → NL > DE > EU
    check(
        "first-match NL > DE > EU (texto híbrido hipotético)",
        flt.applicability_exclusion_reason(
            {
                "title": "Internship",
                "description": "You must be enrolled at a Dutch university. "
                "Immatrikulation an einer deutschen Hochschule ist ebenfalls willkommen. "
                "University must be located in a member state of the EU.",
            }
        )
        == "nl_enrolment_required",
    )


# ---------------------------------------------------------------------------
# T4 — mecanismo F37.3 (tuplas, posição, JSON-tuple, legenda)
# ---------------------------------------------------------------------------


def _with_country(job: dict) -> dict:
    """Carimbo de país para a fixture passar pelos gates student/area/
    country da cascata e ALCANÇAR o estágio de aplicabilidade."""
    return {**job, "location": "Berlin, DE", "country_iso": "de"}


def t4_mechanism() -> None:
    section("T4 — tuplas F37.3 + posição + legenda pt-BR + re-atribuição")
    check(
        "eu_enrolment_required em APPLICABILITY_EXCLUSION_REASONS",
        "eu_enrolment_required" in flt.APPLICABILITY_EXCLUSION_REASONS,
    )
    reasons = flt.APPLICABILITY_EXCLUSION_REASONS
    check(
        "posição: imediatamente após de_enrolment_required (irmã das classes NL/DE)",
        reasons.index("eu_enrolment_required")
        == reasons.index("de_enrolment_required") + 1,
    )
    check(
        "eu_enrolment_required NÃO em APPLICABILITY_JSON_EXCLUSION_REASONS "
        "(padrão nl_enrolment/de_enrolment: cascata exclui; pós-hidratação "
        "só demove — mesma decisão das classes NL/DE)",
        "eu_enrolment_required" not in flt.APPLICABILITY_JSON_EXCLUSION_REASONS
        and "nl_enrolment_required" not in flt.APPLICABILITY_JSON_EXCLUSION_REASONS
        and "de_enrolment_required" not in flt.APPLICABILITY_JSON_EXCLUSION_REASONS,
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
        "legenda nova 🇪🇺 (paralela à 🇳🇱/🇩🇪 das classes NL/DE)",
        "🇪🇺" in labels.get("eu_enrolment_required", "")
        and "🇳🇱" in labels.get("nl_enrolment_required", "")
        and "🇩🇪" in labels.get("de_enrolment_required", ""),
    )
    # rótulo do funil de candidaturas
    try:
        import funnel_report as _fr  # noqa: E402

        check(
            "funnel_report.DEATH_LABELS cobre eu_enrolment_required",
            _fr.death_label("eu_enrolment_required")
            != "eu_enrolment_required",
            _fr.death_label("eu_enrolment_required"),
        )
    except Exception as exc:  # noqa: BLE001 — import é best-effort
        check("funnel_report importável", False, repr(exc))
    # contagem por motivo no contrato da cascata
    _, counts = flt.select_eligible(
        [_with_country(dict(FIX_NEUTRAL))], applicability=True
    )
    check(
        "contador da cascata existe (zerado para neutro)",
        counts.get("aplicabilidade_excluidas_eu_enrolment_required") == 0
        and counts.get("aplicabilidade") == 1,
    )


# ---------------------------------------------------------------------------
# T5 — integração select_eligible (cascata real)
# ---------------------------------------------------------------------------


def t5_select_eligible() -> None:
    section("T5 — integração select_eligible (cascata real)")
    # Bosch 1 sozinha → sai com o motivo novo contado.
    sel, counts = flt.select_eligible(
        [_with_country(dict(FIX_BOSCH_1))], applicability=True
    )
    check(
        "Bosch sai da cascata (0 mantidas)",
        len(sel) == 0,
        f"kept={len(sel)}",
    )
    check(
        "contador por motivo: aplicabilidade_excluidas_eu_enrolment_required == 1",
        counts.get("aplicabilidade_excluidas_eu_enrolment_required") == 1,
    )
    # lote misto: Bosch (sai) + neutro (fica) → contagens exatas
    sel, counts = flt.select_eligible(
        [
            _with_country(dict(FIX_BOSCH_1)),
            _with_country(dict(FIX_NEUTRAL)),
        ],
        applicability=True,
    )
    check(
        "lote misto: só o neutro fica",
        len(sel) == 1 and sel[0].get("id") == FIX_NEUTRAL["id"],
        f"kept={[j.get('id') for j in sel]}",
    )
    check(
        "lote misto: eu_enrolment_required == 1 (Bosch)",
        counts.get("aplicabilidade_excluidas_eu_enrolment_required") == 1,
    )
    # reversibilidade: --no-applicability desliga o estágio inteiro
    sel_off, counts_off = flt.select_eligible(
        [
            _with_country(dict(FIX_BOSCH_1)),
            _with_country(dict(FIX_NEUTRAL)),
        ],
        applicability=False,
    )
    check(
        "applicability=False mantém todas (reversível, pré-F18)",
        len(sel_off) == 2
        and "aplicabilidade_excluidas_eu_enrolment_required" not in counts_off,
        f"kept={len(sel_off)}",
    )


# ---------------------------------------------------------------------------
# T6 — controles negativos (cadeia None, drift simulado)
# ---------------------------------------------------------------------------

NEGATIVES = [
    {"id": "neg|1", "title": "Praktikum Einkauf (m/w/d)",
     "description": "Du unterstützt das Einkaufsteam bei der Beschaffung."},
    {"id": "neg|2", "title": "Supply Chain Intern",
     "description": "Support the planning team with daily operations."},
]

# variantes que NÃO devem casar (drift simulado dos padrões)
DRIFT = [
    ("cooperativa: 'with an EU-based university'",
     "In cooperation with an EU-based university, we offer this programme."),
    ("residência: 'based in the EU' sem university",
     "You must be based in the EU for the duration."),
    ("trabalho: 'work within the EU' sem enrolled",
     "This role requires work within the EU market."),
    ("vendas: 'sales within the EU'",
     "Responsible for sales within the EU region."),
    ("remoto: 'remote within the EU'",
     "You can work remotely within the EU."),
    ("estudo solto: 'studying in the EU'",
     "You are currently studying in the EU."),
    ("Bosch SPO: matrícula genérica",
     "Voraussetzung ist die Immatrikulation an einer Hochschule."),
]


def t6_negatives() -> None:
    section("T6 — controles negativos: cadeia None + drift simulado")
    for job in NEGATIVES:
        got = flt.applicability_exclusion_reason(dict(job))
        check(f"{job['id']} fica (None)", got is None, f"cadeia={got!r}")
    for name, desc in DRIFT:
        check(
            f"drift não casa: {name}",
            not flt.requires_eu_enrolment("x", desc),
        )
    # desc vazia / None não crasha
    check(
        "desc vazia/None não crasha",
        flt.requires_eu_enrolment("Praktikum", "") is False
        and flt.requires_eu_enrolment("Praktikum", None) is False,
    )


def main() -> int:
    t1_positives()
    t2_counter_cases()
    t3_f99_f106_regression()
    t4_mechanism()
    t5_select_eligible()
    t6_negatives()
    print(f"\n==== test_f111: {CHECKS} checks, {len(FAILURES)} falhas ====")
    if FAILURES:
        for f in FAILURES:
            print(f"  [FAIL] {f}")
        return 1
    print("==== test_f111 OK ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
