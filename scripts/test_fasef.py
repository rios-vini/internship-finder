#!/usr/bin/env python3
"""Fase F — Deterministic Enrichment Fixes (testes offline, 100% determinísticos).

Cobre as TRÊS frentes da Fase F (spec do dono, 28/09):

P0 — Work authorization: sobre-classificação de ``existing_required`` em
      autorizações citadas CONDICIONALMENTE ("ggf.", "wenn vorliegend",
      "if applicable") corrigida de forma CONTEXTUAL (sentence-scope, nunca
      a regra simplista "ggf. => unclear"); ``existing_required`` explícito
      continua válido; precedência inalterada.

P1 — Student subtype (ENRICHMENT puro): working_student /
      mandatory_internship / voluntary_internship / internship / unclear por
      evidência explícita, com conflito title×description REGISTRADO (nunca
      arbitrado). Nunca altera eligibility/ranking/score.

P2 — Salary hourly: "Stundenlohn von X Euro", "X €/Stunde", "€X per hour"
      -> period="hour"; salários mensais/anuais existentes NÃO mudam; casos
      inválidos continuam rejeitados.

Padrão da suíte standalone do projeto: ``check(desc, cond)`` com exit 1 se
qualquer falha; roda 100% offline (dataset real é opcional e read-only).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import app_intel  # noqa: E402
from internship_finder import opportunity_intel  # noqa: E402

_student_subtype_of = app_intel._student_subtype_of  # noqa: E402 (audit anti-FP)

_FAILS: list[str] = []


def check(desc: str, cond: bool) -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {desc}")
    if not cond:
        _FAILS.append(desc)


def wa(text: str) -> str:
    return app_intel.work_authorization(text)["state"]


# ---------------------------------------------------------------------------
# P0 — Work authorization: condicionais não são exigência pre-existente
# ---------------------------------------------------------------------------

def test_wa_spike_cases() -> None:
    print("== P0.1: os 6 casos reais da spike Fase E (reproduzidos) ==")
    # Evidência literal da spike (artefatos /tmp/if-fasee-artifacts, PR #89):
    # 5x Bosch "sowie ggf. eine gültige Arbeits- und Aufenthaltserlaubnis"
    # + 1x STIHL "sowie wenn vorliegend Arbeitszeugnisse und deine gültige
    # Arbeits- und Aufenthaltserlaubnis". Todos eram existing_required.
    bosch_sentence = (
        "Bitte füge deiner Bewerbung deinen Lebenslauf, deinen aktuellen "
        "Notenspiegel, eine aktuelle Immatrikulationsbescheinigung, deine "
        "Prüfungsordnung sowie ggf. eine gültige Arbeits- und "
        "Aufenthaltserlaubnis bei."
    )
    stihl_sentence = (
        "Bitte füge deiner Bewerbung folgende Unterlagen bei: Lebenslauf, "
        "aktueller Notenspiegel und Immatrikulationsbescheinigung sowie "
        "wenn vorliegend Arbeitszeugnisse und deine gültige Arbeits- und "
        "Aufenthaltserlaubnis"
    )
    # 5x Bosch (IDs da spike) — mesmo padrão, textos com variação mínima.
    for i, tail in enumerate([
        " Dauer: 6 Monate.",
        " Dauer: 6 Monate (ausschließlich Pflichtpraktikum gem. SPO möglich).",
        " Die Studien- bzw. Prüfungsordnung mit Angabe zur Dauer des Pflichtpraktikums.",
        " Im Anschluss besteht nach Absprache die Möglichkeit einer Werkstudententätigkeit.",
        " Voraussetzung für das Praktikum ist die Immatrikulation an einer Hochschule.",
    ]):
        check(f"Bosch spike #{i+1}: ggf. + Arbeits-/Aufenthaltserlaubnis "
              f"NÃO é existing_required",
              wa(bosch_sentence + tail) != "existing_required")
    check("STIHL spike: wenn vorliegend + gültige Arbeits- und "
          "Aufenthaltserlaubnis NÃO é existing_required",
          wa(stihl_sentence) != "existing_required")
    # Os 6 caem em unclear (vocab presente, sem classificação válida).
    check("Bosch spike: estado final unclear (vocab sem classificação)",
          wa(bosch_sentence) == "unclear")
    check("STIHL spike: estado final unclear", wa(stihl_sentence) == "unclear")


def test_wa_adversarial() -> None:
    print("== P0.2: adversariais da spec §6 ==")
    # A/B: explicit existing continua válido (spec §4).
    check("A: 'gültige Arbeitserlaubnis erforderlich' -> existing_required",
          wa("gültige Arbeitserlaubnis erforderlich") == "existing_required")
    check("B: 'Sie müssen bereits über eine gültige Arbeitserlaubnis "
          "verfügen' -> existing_required",
          wa("Sie müssen bereits über eine gültige Arbeitserlaubnis "
             "verfügen") == "existing_required")
    # C/D/E: condicionais não viram existing automaticamente.
    check("C: 'ggf. gültige Arbeitserlaubnis' não é existing auto",
          wa("ggf. gültige Arbeitserlaubnis") != "existing_required")
    check("D: 'wenn vorliegend' não é existing auto",
          wa("wenn vorliegend") != "existing_required")
    check("E: 'ggf. ist eine Arbeitserlaubnis erforderlich' -> condicional",
          wa("ggf. ist eine Arbeitserlaubnis erforderlich")
          in ("unclear", "not_mentioned"))
    # F/G: suporte e não-suporte.
    check("F: 'Wir unterstützen Sie bei der Beantragung einer "
          "Arbeitserlaubnis' -> support",
          wa("Wir unterstützen Sie bei der Beantragung einer "
             "Arbeitserlaubnis") == "support")
    check("G: 'Wir unterstützen Sie bei Ihrem Umzug' -> not_mentioned",
          wa("Wir unterstützen Sie bei Ihrem Umzug") == "not_mentioned")


def test_wa_conditional_scope() -> None:
    print("== P0.3: escopo da condicional (sentença, não documento) ==")
    # A condicional em OUTRA sentença não suprime a exigência real.
    check("condicional em sentença anterior NÃO suprime exigência depois",
          wa("ggf. werden Reisen benötigt. "
             "Bewerber benötigen eine gültige Arbeitserlaubnis.")
          == "existing_required")
    check("'gegebenenfalls' qualifica na MESMA sentença",
          wa("Gegebenenfalls ist eine gültige Arbeitserlaubnis "
             "erforderlich.") != "existing_required")
    check("EN 'if applicable' na mesma sentença",
          wa("Please attach your CV and, if applicable, a valid work "
             "permit.") != "existing_required")
    check("EN exigência direta SEM condicional continua existing",
          wa("Applicants must already have a valid work permit")
          == "existing_required")
    # Não é a regra simplista "ggf. => unclear": ggf. sem TEMA de WA não
    # muda nada (não-vocab segue not_mentioned).
    check("ggf. sem tema WA -> not_mentioned (não é regra simplista)",
          wa("ggf. werden Sie gereist.") == "not_mentioned")


def test_wa_regression() -> None:
    print("== P0.4: regressão — casos existentes do test_app_intel ==")
    cases = [
        ("You must have existing work authorization", "existing_required"),
        ("Applicants need a valid work and residence permit",
         "existing_required"),
        ("EU citizens only", "existing_required"),
        ("must already have a valid work permit", "existing_required"),
        ("Applicants must already hold a valid work permit",
         "existing_required"),
        ("bereits vorhandene Arbeitserlaubnis", "existing_required"),
        ("Aufenthaltstitel bereits vorhanden", "existing_required"),
        ("valid EU passport required", "existing_required"),
        ("Für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich",
         "existing_required"),
        ("Applicants must already have a valid work permit. "
         "We can provide relocation assistance.", "existing_required"),
        ("We sponsor visas for international candidates", "support"),
        ("We do not offer visa sponsorship", "no_sponsorship"),
        ("Join our multinational team in Munich", "not_mentioned"),
        ("Visa questions can be discussed during the interview", "unclear"),
    ]
    for text, expected in cases:
        check(f"regressão: '{text[:48]}' -> {expected}",
              wa(text) == expected)
    # Precedência inalterada: no_sponsorship vence suporte.
    check("precedência: no_sponsorship vence suporte",
          wa("We cannot sponsor visas, but relocation support exists")
          == "no_sponsorship")


def test_wa_determinism() -> None:
    print("== P0.5: determinismo ==")
    det = ("Prüfungsordnung sowie ggf. eine gültige Arbeits- und "
           "Aufenthaltserlaubnis bei.")
    check("determinismo: 100 repetições iguais",
          len({wa(det) for _ in range(100)}) == 1)


# ---------------------------------------------------------------------------
# P1 — Student subtype
# ---------------------------------------------------------------------------

def _st(title: str, description: str) -> dict | None:
    return app_intel.student_type({
        "title": title, "description": description, "employment_type": "",
    })


def test_student_working() -> None:
    print("== P1.1: working_student ==")
    check("'Working Student' no title",
          (_st("Working Student (m/f/d) Power BI", "Support the team")
           or {}).get("type") == "working_student")
    check("'Werkstudent' no title (com sufixo)",
          (_st("Werkstudent Analytics & Anforderungsmanagement (m/w/d)",
               "Als Werkstudent:in unterstützt Du uns")
           or {}).get("type") == "working_student")
    check("'werkstudenten' no description",
          (_st("Praktikum IT", "Wir bieten unseren Werkstudenten "
               "unterschiedliche Arbeitszeitmodelle an.")
           or {}).get("type") == "working_student")
    check("'student worker' EN",
          (_st("Student Worker Logistics", "Help the warehouse team")
           or {}).get("type") == "working_student")


def test_student_mandatory() -> None:
    print("== P1.2: mandatory_internship ==")
    check("'Pflichtpraktikum' no title",
          (_st("Pflichtpraktikum Logistik - Schwerpunkt Data", " plain")
           or {}).get("type") == "mandatory_internship")
    check("'mandatory internship' no title",
          (_st("Mandatory Internship Supply Chain", "text")
           or {}).get("type") == "mandatory_internship")
    check("'nur Pflichtpraktika' no description (evidência real Bosch)",
          (_st("Praktikum Beschaffungsplanung",
               "mind. 20-26 Wochen, nur Pflichtpraktika – praktisches "
               "Studiensemester im Rahmen eines Bachelorstudiums.")
           or {}).get("type") == "mandatory_internship")
    check("'we can only offer mandatory internships' (evidência NXP)",
          (_st("Intern (f/m/d) AI-Driven Data Analysis",
               "Due to internal regulations, we can only offer mandatory "
               "internships. If a mandatory internship is not part of "
               "your study program, we kindly ask you to refrain from "
               "applying.")
           or {}).get("type") == "mandatory_internship")


def test_student_voluntary_and_generic() -> None:
    print("== P1.3: voluntary explícito + genérico ==")
    check("'freiwilliges Praktikum' explícito",
          (_st("Praktikum Marketing", "Wir bieten ein freiwilliges "
               "Praktikum an.") or {}).get("type")
          == "voluntary_internship")
    check("'voluntary internship' explícito",
          (_st("Voluntary Internship Sales", "text")
           or {}).get("type") == "voluntary_internship")
    check("Praktikum sem indicação -> internship genérico",
          (_st("Praktikum in der Logistikplanung",
               "Voraussetzung für das Praktikum ist die Immatrikulation")
           or {}).get("type") == "internship")
    check("NÃO inferir voluntary só pela ausência de mandatory",
          (_st("Praktikum", "Du arbeitest im Team.")
           or {}).get("type") == "internship")
    # student-role por marcador FORA do vocabulário de subtipo (tese
    # acadêmica é student-role pelo filtro, mas não é Praktikum/Werkstudent)
    # -> sem evidência de subtipo -> unclear.
    check("student-role sem evidência de subtipo -> unclear",
          (_st("Bachelorarbeit Data Analytics", "Supervision by the chair.")
           or {}).get("type") == "unclear")


def test_student_anti_fp_audits() -> None:
    print("== P1.6: anti-FP — padrões reais da audit de produção (404) ==")
    # ENUMERAÇÃO de opções (Telekom ×2, trumpf — produção 28/09): o anúncio
    # aceita AMBOS -> não classifica subtipo específico, mantém genérico.
    check("enum 'Ob Pflicht- oder freiwilliges Praktikum' -> genérico",
          _student_subtype_of(
              "Ob Pflicht- oder freiwilliges Praktikum – Als Praktikant "
              "profitierst du") == "internship")
    check("enum 'Pflichtpraktikum oder freiwilliges Praktikum' -> genérico",
          _student_subtype_of(
              "Pflichtpraktikum oder freiwilliges Praktikum (auch im Gap "
              "Year)") == "internship")
    check("enum EN 'mandatory or voluntary internships' -> genérico",
          _student_subtype_of(
              "We offer mandatory or voluntary internships.") == "internship")
    # CHECKLIST CONDICIONAL (Volkswagen AG ×3 — produção 28/09): documento
    # extra SE o Praktikum do candidato for obrigatório -> não classifica
    # a POSIÇÃO.
    check("checklist 'Bei einem Pflichtpraktikum zusätzlich...' -> "
          "não mandatory",
          _student_subtype_of(
              "Bei einem Pflichtpraktikum zusätzlich eine Bescheinigung "
              "der Hochschule") != "mandatory_internship")
    # VOLUNTÁRIO NEGADO (MAHLE ×2 — produção 28/09): Praktikum alemão é
    # binário Pflicht/freiwillig -> negar freiwillig = mandatory-only.
    check("negado 'purely voluntary internships cannot be offered' -> "
          "mandatory",
          _student_subtype_of(
              "Currently, purely voluntary internships cannot be offered")
          == "mandatory_internship")
    check("negado 'keine freiwilligen Praktika' -> mandatory",
          _student_subtype_of(
              "Derzeit können keine freiwilligen Praktika angeboten werden")
          == "mandatory_internship")


def test_student_conflict() -> None:
    print("== P1.4: conflito title x description (registro, spec §9) ==")
    out = _st("Working Student BI", "Pflichtpraktikum gem. SPO möglich")
    check("title working_student x description mandatory -> unclear",
          (out or {}).get("type") == "unclear")
    check("conflito registrado em conflict=True",
          (out or {}).get("conflict") is True)
    # Refinamento NÃO é conflito: genérico + específico compatíveis.
    check("title genérico + description mandatory -> mandatory (refina)",
          (_st("Praktikum", "Dauer: 6 Monate (ausschließlich "
               "Pflichtpraktikum gem. SPO möglich)") or {}).get("type")
          == "mandatory_internship")
    check("refinamento sem conflict flag",
          (_st("Praktikum", "Dauer: 6 Monate (ausschließlich "
               "Pflichtpraktikum gem. SPO möglich)") or {}).get("conflict")
          is False)


def test_student_scope() -> None:
    print("== P1.5: escopo — nunca reclassifica, nunca para não-student ==")
    check("não-student-role -> None (não inventa subtipo)",
          _st("Senior Manager Procurement", "Leads the team") is None)
    check("student_subtype no candidate_fit é ENRICHMENT (kind info/ok)",
          all(
              s["kind"] in ("ok", "info")
              for s in app_intel.candidate_fit({
                  "title": "Werkstudent Analytics (m/w/d)",
                  "description": "Als Werkstudent:in unterstützt Du uns",
                  "employment_type": "", "country_iso": "de",
                  "location": "Berlin",
              })
              if s["key"] == "student_subtype"
          ))
    check("student_subtype AUSENTE para genérico internship (não duplica)",
          "student_subtype" not in [
              s["key"] for s in app_intel.candidate_fit({
                  "title": "Praktikum IT", "description": " plain",
                  "employment_type": "", "country_iso": "de",
                  "location": "Berlin",
              })
          ])
    check("student_subtype ausente para não-student",
          "student_subtype" not in [
              s["key"] for s in app_intel.candidate_fit({
                  "title": "Senior Manager", "description": "Leads",
                  "employment_type": "", "country_iso": "de",
                  "location": "Berlin",
              })
          ])


# ---------------------------------------------------------------------------
# P2 — Salary hourly
# ---------------------------------------------------------------------------

def _sal(title: str, description: str) -> dict | None:
    return opportunity_intel.job_salary({
        "title": title, "description": description,
    })


def test_salary_hourly() -> None:
    print("== P2.1: hourly (evidência real Covestro, spike Fase E) ==")
    out = _sal("Werkstudent:in Supply Chain",
               "Neben unseren vielfältigen Benefits erwartet Dich ein "
               "Stundenlohn von 21 Euro plus Weihnachts- und Urlaubsgeld.")
    check("'Stundenlohn von 21 Euro' capturado (period=hour)",
          bool(out) and out["period"] == "hour")
    check("valor 21.0", bool(out) and out["min"] == 21.0 and
          out["max"] == 21.0)
    check("'13 €/Stunde' -> hour",
          (_sal("W", "Vergütung: 13 €/Stunde") or {}).get("period") == "hour")
    check("'€21 per hour' EN -> hour",
          (_sal("W", "Compensation: €21 per hour") or {}).get("period")
          == "hour")
    check("'Stundenlohn: 15 €' com dois-pontos",
          (_sal("W", "Stundenlohn: 15 €") or {}).get("period") == "hour")


def test_salary_regression() -> None:
    print("== P2.2: mensal/anual/inválidos NÃO mudam ==")
    check("mensal 'Gehalt: 2.117 €/Monat' continua month",
          (_sal("W", "Gehalt: 2.117 €/Monat") or {}).get("period")
          == "month")
    check("mensal range 'Vergütung: €1.500–€1.800' continua month",
          ((_sal("W", "Vergütung: €1.500–€1.800") or {})
           .get("period")) == "month")
    check("valor numérico sem moeda/rotulo continua rejeitado",
          _sal("W", "Der Kunde zahlt 21 Euro für die Stunde") is None)
    check("sem salario -> None",
          _sal("W", "kein Geld hier") is None)
    check("periodo 'hour' mapeado no ptbr",
          __import__("internship_finder.ptbr", fromlist=["x"])
          .SALARY_PERIOD_LABELS.get("hour") == "hora")


def test_salary_hourly_guard() -> None:
    print("== P2.3: guard de fragmento decimal (17,80 €/Stunde) ==")
    # Bug pré-existente do _MONEY_CLAUSE: decimal alemão "17,80" vira dois
    # matches ("17" e "80"). O guard impede que o FRAGMENTO seja rotulado
    # hourly (o valor seguiria errado); o comportamento pré-Fase F é
    # preservado (documentado como backlog, não alterado nesta fase).
    out = _sal("Working Student Data Analytics",
               "Vergütung: 17,80 €/Stunde")
    if out is not None:
        check("fragmento decimal NÃO é rotulado hourly (preserva "
              "comportamento pré-Fase F)", out["period"] != "hour")
    else:
        check("fragmento decimal: ausência também aceitável (nenhum "
              "retorno novo)", True)


def main() -> int:
    test_wa_spike_cases()
    test_wa_adversarial()
    test_wa_conditional_scope()
    test_wa_regression()
    test_wa_determinism()
    test_student_working()
    test_student_mandatory()
    test_student_voluntary_and_generic()
    test_student_anti_fp_audits()
    test_student_conflict()
    test_student_scope()
    test_salary_hourly()
    test_salary_regression()
    test_salary_hourly_guard()
    print()
    if _FAILS:
        print(f"TUDO OK não — {len(_FAILS)} falhas:")
        for f in _FAILS:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
