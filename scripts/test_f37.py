"""Testes da Fase F37 — saneamento hard-eligibility (100% offline).

F37 (14/10, decisão literal do dono): vagas que o dono NÃO PODE aplicar
SAEM do eligible/display/digest — EXCLUSÃO, nunca rebaixamento de score.
Mecanismo ÚNICO: os detectores vivem na função de aplicabilidade de
``filters.py`` (``applicability_exclusion_reason``, razões com contadores
``aplicabilidade_excluidas_*``); os 2 call sites herdam o MESMO veredito:
(a) filtros do pipeline (``select_eligible``); (b) re-avaliação pós-
hidratação do ``refresh_daily`` (``_reassess_hydrated_applicability``,
padrão F25 — reusa a função verbatim). A flag F25 ``german_required``
PERMANECE flag+descida (decisão pendente do dono; contagem só).

Grupos de teste:

- **T1 FIXTURE CONGELADO (auditor offline no CI)** —
  ``fixtures/audit_2026-10-14.json``: jobs VERBATIM dos snapshots
  congelados 13/10+14/10 (campos mínimos + trechos literais, NUNCA
  payload/raw completo). O auditor roda os detectores contra o fixture e
  reporta precisão por grupo. A partir daqui o CI NUNCA mais audita
  contra dado vivo (lição test_f29). Os 8 grupos de FP da revisão
  (GALERIA, AVISON, OTTOFUCHSKG, SAP, Amazon, ArcelorMittal, e-farm,
  indiecampers) têm presença OBRIGATÓRIA no fixture.
- **T2 detectores novos** (regex determinístico, trechos LITERAIS em
  constantes nomeadas — anti-invenção): eu_citizenship_required
  (teampicnic R6 + Kraft Heinz R8 + variante literal), nl_enrolment
  (Vanderlande R31 + Parfumado R12 HBO/WO), phd_position (SAP).
- **T3 fixes de detector** (cada fix com caso VERBATIM + contra-caso):
  "intern." abreviação (AVISON "intern. Chemiehandel" morre; "intern.
  you will work" em desc de estágio legítimo não exclui sozinho),
  "placement" composto (Amazon "Inventory Placement Operations" morre;
  Citi "Placement Analyst" programa UK de 6 meses FICA), Aushilfe/
  Schnupper na exclusão de tipo (GALERIA + Champignon morrem; contra-
  caso: Praktikum legítimo FULL_TIME — 268/272 do FULL_TIME 13/10 —
  fica), tese estendida (Bachelorarbeit/Masterarbeit puros morrem;
  "Bachelor's or Master's" não é mestrado), FULL_TIME efetivo (Amazon
  BA sem marcador morre; "Praktikum" no título fica), duração >6m
  título-only (ArcelorMittal "12 months" morre; faixa "6 – 12 Monate"
  com piso dentro do teto fica — mesma semântica F29), word-boundary
  em TODOS os regexes novos (precedente F28: \\bteams\\b era MS Teams).
- **T4 integração select_eligible**: contadores por motivo (incluindo os
  5 novos), first-match (uma vaga, um motivo), reversibilidade
  (applicability=False), no-op byte a byte em dataset limpo (padrão T5
  do F18).
- **T5 herança F25** (call site b): ``_reassess_hydrated_applicability``
  devolve os NOVOS motivos (herda o veredito completo da cascata) e
  continua devolvendo german/master (contrato F20/F25 intacto).
- **T6 contagem derivada no metrics**: ``_applicability_metrics_record``
  = {eligible, flagged, applicable, flagged_*} puro e correto.

Uso:  .venv/bin/python scripts/test_f37.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import filters as flt  # noqa: E402

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


FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "audit_2026-10-14.json"


# ---------------------------------------------------------------------------
# Fixtures sintéticas (texto real só onde citado literalmente da revisão)
# ---------------------------------------------------------------------------

def _job(id_: str, title: str, description: str = "Support the team in English.",
         company: str = "Acme", employment_type: str | None = None) -> dict:
    return {
        "id": id_, "title": title, "description": description,
        "company": company, "employment_type": employment_type,
        "location": "Berlin, DE", "country_iso": "de",  # país não é o alvo aqui
    }


# ---------------------------------------------------------------------------
# T1 — FIXTURE CONGELADO: auditor offline (precisão por grupo)
# ---------------------------------------------------------------------------

def t1_fixture_auditor() -> None:
    section("T1 — fixture congelado audit_2026-10-14 (auditor offline)")
    if not FIXTURE_PATH.exists():
        check("fixture existe", False, str(FIXTURE_PATH))
        return
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    jobs = fx.get("jobs") or []
    check("fixture tem jobs", len(jobs) >= 30, f"{len(jobs)} jobs")

    # precisão por grupo (auditor: roda os detectores contra o fixture)
    by_group: dict[str, dict[str, int]] = {}
    bad: list[str] = []
    for e in jobs:
        j = {
            "title": e.get("title") or "",
            "description": " ... ".join(e.get("description_snippets") or []),
            "employment_type": e.get("employment_type"),
            "company": e.get("company"),
        }
        reason = flt.applicability_exclusion_reason(j)
        student = flt.is_student_role(j["title"], j["description"], j.get("employment_type"))
        excluded = reason is not None or not student
        g = by_group.setdefault(e["group"], {"total": 0, "ok": 0})
        g["total"] += 1
        ok = excluded == e["expect_excluded"]
        exp_reason = e.get("expected_reason")
        if exp_reason is not None and reason != exp_reason:
            ok = False
        g["ok"] += 1 if ok else 0
        if not ok:
            bad.append(f"{e['group']}/{e['id']}: excl={excluded} "
                       f"(exp {e['expect_excluded']}) reason={reason} "
                       f"(exp {exp_reason})")
    total_ok = sum(g["ok"] for g in by_group.values())
    total = sum(g["total"] for g in by_group.values())
    check("auditor: 100% dos 32 casos do fixture verificados", total_ok == total,
          f"{total_ok}/{total}")
    check("auditor: zero discordâncias", not bad, "; ".join(bad[:4]))

    # os 8 grupos de FP da revisão do dono têm presença OBRIGATÓRIA
    groups = {e["group"] for e in jobs}
    for g in ("galeria_aushilfe", "avison_intern_abbrev", "ottfuchs_bachelorarbeit",
              "sap_phd", "amazon_fulltime_placement", "arcelormittal_duration",
              "efarm_erasmus", "indiecampers_spontaneous"):
        check(f"fixture contém grupo obrigatório '{g}'", g in groups)

    # contra-casos do topo (Bayer/Nestlé/TRUMPF) e Praktikum-FULL_TIME
    for g in ("contra_bayer_top", "contra_nestle_top", "contra_trumpf_top",
              "contra_praktikum_fulltime"):
        check(f"fixture contém contra-caso '{g}'", g in groups)

    # F37.2 (15/10): a decisão pendente VIROU decisão — dono respondeu "2a. A"
    # (EXCLUIR); os detectores F37.2 agora excluem esses grupos com motivo
    # próprio. Auditoria atualizada: expect_excluded=true, motivo
    # erasmus_program (Erasmus+ vence first-match sobre pool).
    for e in jobs:
        if e["group"] in ("efarm_erasmus", "indiecampers_spontaneous"):
            j = {
                "title": e.get("title") or "",
                "description": " ... ".join(e.get("description_snippets") or []),
                "employment_type": e.get("employment_type"),
                "company": e.get("company"),
            }
            check(f"decisão implementada (F37.2): {e['group']} exclui",
                  flt.applicability_exclusion_reason(j) == "erasmus_program")


# ---------------------------------------------------------------------------
# T2 — detectores novos (trechos literais; anti-invenção)
# ---------------------------------------------------------------------------

def t2_new_detectors() -> None:
    section("T2 — detectores novos: EU-citizenship, NL-enrolment, PhD")
    # teampicnic R6 — trecho literal confirmado na revisão 14/10
    check("eu_cit: 'Staatsbürgerschaft eines EU-Mitgliedstaates'",
          flt.requires_eu_citizenship(
              "Praktikum Business Analytics",
              "Du besitzt die Staatsbürgerschaft eines EU-Mitgliedstaates."))
    check("eu_cit: variante 'ue' (transliteração)",
          flt.requires_eu_citizenship(
              "Praktikum", "Staatsbuergerschaft eines EU-Mitgliedstaates"))
    # Kraft Heinz R8
    check("eu_cit: 'EU working rights are required'",
          flt.requires_eu_citizenship(
              "Supply chain Intern", "EU working rights are required."))
    check("eu_cit: variante literal Kraft Heinz",
          flt.requires_eu_citizenship(
              "Intern", "Either you have an EU Citizenship, or you are "
                         "studying in the Netherlands"))
    # contra-casos: sem trecho, NÃO dispara
    check("eu_cit: vaga comum NÃO dispara (Bayer R4 'Enrolled student')",
          not flt.requires_eu_citizenship(
              "Internship Analytics",
              "Enrolled student in economics or a comparable field"))
    check("eu_cit: 'EU' solto não dispara (word-boundary)",
          not flt.requires_eu_citizenship("EU Analyst Intern", "work across the EU"))

    # Vanderlande R31
    check("nl_enrol: 'Mandatory enrolment to a Dutch Education System'",
          flt.requires_nl_enrolment(
              "Internship: Finance process automation",
              "Mandatory enrolment to a Dutch Education System & resident "
              "of The Netherlands"))
    # Parfumado R12
    check("nl_enrol: 'HBO/WO programme'",
          flt.requires_nl_enrolment(
              "Operations & Supply Chain Intern",
              "You are enrolled in an HBO/WO programme. €450 per month."))
    check("nl_enrol: 'HBO' puro (medido no universo: Levio, Frenckengroup)",
          flt.requires_nl_enrolment("Internship Account Management",
                                    "You are enrolled in an HBO programme."))
    check("nl_enrol: vaga DE comum NÃO dispara",
          not flt.requires_nl_enrolment("Praktikum Einkauf",
                                        "Hochschulpraktikum im Einkauf"))

    # SAP #79
    check("phd: 'PhD Internship' no título",
          flt.requires_phd("PhD Internship (f/m/d) - AI Research", ""))
    check("phd: 'doctoral' / 'Doktorand'",
          flt.requires_phd("Internship", "doctoral candidate position")
          and flt.requires_phd("Abschlussarbeit", "Wir suchen einen Doktoranden"))
    check("phd: vaga bachelor NÃO dispara",
          not flt.requires_phd("Internship", "bachelor student in engineering"))


# ---------------------------------------------------------------------------
# T3 — fixes de detector (caso verbatim + contra-caso)
# ---------------------------------------------------------------------------

def t3_detector_fixes() -> None:
    section("T3 — fixes: intern., placement, Aushilfe/Schnupper, tese, "
            "FULL_TIME, duração")

    # (a) "intern." abreviação de 'internationaler' (AVISON ×4, 13/10)
    check("intern.: 'intern. Chemiehandel' NÃO é marcador",
          not flt.is_student_role(
              "Vetriebsmitarbeiter m/w/d - (Supply Chain Manager) - intern. "
              "Chemiehandel (Kaufmann/-frau - Groß- und Außenhandel)",
              "AVISON Chemical GmbH - Berlin Vertriebsmitarbeiter (Supply "
              "Chain Manager / Sales Manager) internationaler Chemiehandel "
              "Wir suchen eine/n Kaufmann/-frau in Vollzeit.",
              "FULL_TIME"))
    check("intern.: 'intern.' em desc de estágio legítimo continua OK "
          "(contra-caso: frase 'rockstar intern.' real do 13/10)",
          flt.is_student_role(
              "GTM Automation / Operations Internship",
              "We are looking for a rockstar intern. you will work directly "
              "with our co-founder.", None))
    check("intern.: 'Internship' normal continua marcador",
          flt.is_student_role("Supply Chain Intern", "support", None))

    # (b) "placement" só em compostos (Amazon #88 FP; Citi contra-caso)
    check("placement: 'Inventory Placement Operations' NÃO é marcador (FP #88)",
          not flt.is_student_role(
              "Business Analyst, EU Inbound & Inventory Placement Operations (m/f)",
              "Business Analyst Job ID: 10475360. The Amazon University Talent "
              "Aquisition Team (AUTA) is looking for ambitious Graduates.",
              "FULL_TIME"))
    check("placement: 'Placement Analyst' programa UK FICA (contra-caso Citi)",
          flt.is_student_role(
              "Banking, Investment Banking, Placement Analyst, Amsterdam – "
              "Netherlands",
              "Citi is actively seeking highly motivated placement analysts "
              "to join its esteemed investment banking team. This placement "
              "offers an immersive experience of up to 6 months.", None))
    check("placement: 'placement year/scheme' compostos UK continuam marcadores",
          flt.is_student_role("Placement Year - Procurement", "", None)
          and flt.is_student_role("Internship placement", "", None))

    # (c) Aushilfe/Schnupper: exclusão de TIPO (título vence desc)
    check("tipo: GALERIA 'Aushilfe (w/m/d)' + desc 'Werkstudenten' morre "
          "(FP ×8 do 13/10)",
          not flt.is_student_role(
              "Aushilfe (w/m/d)",
              "Du bist Student, Schüler oder Quereinsteiger und suchst einen "
              "Nebenjob oder Minijob? Wir suchen studentische Aushilfen, "
              "Verkaufshilfen, Werkstudenten in Teilzeit.", "FULL_TIME"))
    check("tipo: 'Schnupperpraktikum Kaufmann' morre (Champignon 13/10)",
          not flt.is_student_role(
              "Schnupperpraktikum Kaufmann für Spedition und "
              "Logistikdienstleistung (m/w/d)",
              "Das Schnupperpraktikum ist die ideale Vorbereitung für deine "
              "späteren beruflichen Pläne.", None))
    check("tipo: Aushilfe só na DESC não exclui estágio legítimo "
          "(contra-caso: título é marcador forte)",
          flt.is_student_role(
              "Praktikum Logistik", "Wir suchen Aushilfen für die Filiale.",
              None))

    # (d) tese estendida: Bachelorarbeit/Masterarbeit PUROS no título
    check("tese: 'Bachelorarbeit Data Science' (OTTOFUCHSKG #57) sai",
          flt.applicability_exclusion_reason(
              _job("otto", "Bachelorarbeit Data Science",
                   "Wir bieten die Möglichkeit, Ihre Abschlussarbeit zu "
                   "verfassen.", "OTTOFUCHSKG", "FULL_TIME"))
          == "thesis_title")
    check("tese: 'Masterarbeit' no título também (antes: só master_required)",
          flt.is_thesis_title_strict("Masterarbeit im Einkauf"))
    check("tese: 'Bachelor's or Master's' NÃO é exigência de mestrado "
          "(contra-caso real Amazon)",
          not flt.requires_master(
              "Business Analyst",
              "In final year of study for Bachelor's or Master's degree, or "
              "graduated in the last 12 months"))
    check("tese: Abschlussarbeit/Thesis continuam (contrato F18 intacto)",
          flt.is_thesis_title_strict("Abschlussarbeit Einkauf")
          and flt.is_thesis_title_strict("Thesis Internship Audit"))

    # (e) FULL_TIME efetivo SEM marcador de estágio (Amazon #88)
    check("full_time: FULL_TIME sem marcador nenhum morre",
          flt.is_full_time_permanent(_job(
              "ft", "Business Analyst, EU Inbound & Inventory Placement "
              "Operations (m/f)", "Looking for ambitious Graduates.",
              "Amazon EU Sàrl", "FULL_TIME")))
    check("full_time: Praktikum legítimo FULL_TIME FICA (CONTRA-CASO "
          "OBRIGATÓRIO — 268/272 do FULL_TIME 13/10)",
          not flt.is_full_time_permanent(_job(
              "bosch", "Praktikum in der Logistik - Data & Analytics",
              "Aufgaben im Bereich Logistik.", "BoschGroup", "FULL_TIME")))
    check("full_time: et ausente não dispara (defensivo)",
          not flt.is_full_time_permanent(_job("none", "Business Analyst")))
    check("full_time: reason aplica no pipeline",
          flt.applicability_exclusion_reason(_job(
              "ft2", "Business Analyst, EU Inbound & Inventory Placement "
              "Operations (m/f)", "Looking for ambitious Graduates.",
              "Amazon", "FULL_TIME")) == "full_time_permanent")

    # (f) duração >6m — TÍTULO only (desc é frágil: 5/14 FPs de contexto)
    check("duracao: 'IT Procurement Internship - 12 months' (ArcelorMittal #38)",
          flt.duration_over_6m_title("IT Procurement Internship - 12 months"))
    check("duracao: 'for up to 12 months' no título (Deutsche Börse)",
          flt.duration_over_6m_title(
              "Internship Commodity ETD Clearing and Risk Operations for up "
              "to 12 months (part-/full-time)"))
    check("duracao: '6 months' no título FICA (exatamente o teto)",
          not flt.duration_over_6m_title(
              "Business Analyst Intern (6 months) - 2027"))
    check("duracao: faixa '6 – 12 Monate' FICA (piso dentro do teto; "
          "semântica F29 D3)",
          not flt.duration_over_6m_title(
              "Praktikant/in (m/f/d) im Bereich Supply Chain"))
    check("duracao: desc com '12 Monate' NÃO exclui (FP de contexto medido: "
          "'within the last 12 months', 'Reststudiendauer mind. 12 Monate')",
          flt.applicability_exclusion_reason(_job(
              "grad", "Engineering Intern (m/w/d)",
              "Du hast dein Studium innerhalb der letzten 12 Monate "
              "abgeschlossen.", "Amazon FC Graben", None)) is None)
    check("duracao: reason aplica no pipeline",
          flt.applicability_exclusion_reason(_job(
              "arc", "IT Procurement Internship - 12 months",
              "The IT & Telco sub-category is part of the European "
              "Procurement Organisation.", "ArcelorMittal", None))
          == "duration_over_6m")

    # (g) word-boundary em TODOS os regexes novos (precedente F28)
    check("word-boundary: 'HBO' não casa dentro de outra palavra",
          not flt.requires_nl_enrolment("Internship", "SEPHORA STORES GMBH"))
    check("word-boundary: 'phd' não casa substring",
          not flt.requires_phd("Internship", "the uphomd process"))


# ---------------------------------------------------------------------------
# T4 — integração select_eligible: contadores, first-match, reversibilidade
# ---------------------------------------------------------------------------

def t4_select_eligible() -> None:
    section("T4 — select_eligible: 10 razões, first-match, reversibilidade")
    jobs = [
        _job("ok-1", "Praktikum Data Analytics", "English required.", "Alpha"),
        _job("out-ger", "Praktikum Data Analytics", "Sehr gute "
             "Deutschkenntnisse erforderlich", "Beta"),
        _job("out-eu", "Praktikum Data Analytics", "Du besitzt die "
             "Staatsbürgerschaft eines EU-Mitgliedstaates.", "Teampicnic"),
        _job("out-nl", "Operations & Supply Chain Intern", "You are enrolled "
             "in an HBO/WO programme.", "Parfumado"),
        _job("out-phd", "PhD Internship Data Analytics",
             "Research position in procurement.", "SAP"),
        _job("out-dur", "IT Procurement Internship - 12 months",
             "Procurement team support.", "ArcelorMittal"),
        # full_time: título SEM marcador morre ANTES (camada tipo — barreira
        # anterior); a razão full_time_permanent fica como defesa nas
        # chamadas diretas (fixture auditor) e no legacy do backlog F25.
        _job("out-ft", "Business Analyst, EU Inbound & Inventory Placement "
             "Operations (m/f)", "Looking for Graduates.", "Amazon",
             "FULL_TIME"),
        _job("out-thesis", "Bachelorarbeit Data Science", "Abschlussarbeit "
             "verfassen.", "OTTOFUCHSKG", "FULL_TIME"),
    ]
    sel, counts = flt.select_eligible(jobs, country="de")
    ids = [j["id"] for j in sel]
    check("eligible só com aplicáveis", ids == ["ok-1"], str(ids))
    check("full_time SEM marcador morre na camada tipo (barreira anterior)",
          flt.is_student_role(
              "Business Analyst, EU Inbound & Inventory Placement "
              "Operations (m/f)", "Looking for Graduates.", "FULL_TIME")
          is False)
    for reason in ("eu_citizenship_required", "nl_enrolment_required",
                   "phd_position", "duration_over_6m",
                   "thesis_title", "german_required"):
        check(f"contagem por motivo: {reason} 1",
              counts.get(f"aplicabilidade_excluidas_{reason}") == 1,
              str({k: v for k, v in counts.items()
                   if k.startswith("aplicabilidade_excluidas_")}))
    check("counts['aplicabilidade'] == len(sel) == 1",
          counts["aplicabilidade"] == len(sel) == 1)

    # first-match: EU-cit + PhD juntos => um só motivo (o primeiro)
    both = _job("both", "PhD Internship", "Du besitzt die Staatsbürgerschaft "
                "eines EU-Mitgliedstaates.", "X")
    check("first-match: uma vaga, um motivo (eu_cit antes de phd)",
          flt.applicability_exclusion_reason(both) == "eu_citizenship_required")

    # reversibilidade (applicability=False = comportamento pré-F18/F37):
    # os 6 excluídos pela camada de APLICABILIDADE voltam; o out-ft (Amazon)
    # permanece fora pois agora morre ANTES, na camada de TIPO (sem marcador
    # de estágio — o fix placement/intern. da F37 é intencional e não é
    # coberto por --no-applicability, que só desliga o estágio F18+).
    sel_off, counts_off = flt.select_eligible(jobs, country="de",
                                              applicability=False)
    off_ids = {j["id"] for j in sel_off}
    check("applicability=False: TODOS os excluídos pela aplicabilidade voltam",
          {"out-ger", "out-eu", "out-nl", "out-phd", "out-dur",
           "out-thesis"} <= off_ids
          and all(v == 0 for k, v in counts_off.items()
                  if k.startswith("aplicabilidade_excluidas_")))
    check("applicability=False: out-ft segue fora (morto na camada tipo)",
          "out-ft" not in off_ids)

    # no-op: dataset limpo => saída byte a byte idêntica (padrão T5/F18)
    clean = [_job(f"ok-{i}", f"Praktikum Data Analytics {i}",
                  "English required. Support the team.")
             for i in range(6)]
    sel_on, counts_on = flt.select_eligible(clean, country="de")
    sel_clean, _ = flt.select_eligible(clean, country="de",
                                       applicability=False)
    check("no-op: dataset limpo => saída byte a byte idêntica",
          json.dumps(sel_on, sort_keys=True)
          == json.dumps(sel_clean, sort_keys=True))
    check("no-op: contagens novas zeradas",
          all(counts_on[f"aplicabilidade_excluidas_{r}"] == 0
              for r in flt.APPLICABILITY_EXCLUSION_REASONS))


# ---------------------------------------------------------------------------
# T5 — herança F25: re-avaliação pós-hidratação usa a MESMA função
# ---------------------------------------------------------------------------

def t5_f25_inheritance() -> None:
    section("T5 — herança F25: call site (b) herda o veredito completo")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import refresh_daily as rd  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        check("refresh_daily importável", False, repr(exc))
        return

    check("EU-cit revelada pela hidratação => flagged com o motivo novo",
          rd._reassess_hydrated_applicability(_job(
              "h1", "Praktikum Business Analytics",
              "Du besitzt die Staatsbürgerschaft eines EU-Mitgliedstaates.",
              "Teampicnic")) == "eu_citizenship_required")
    check("HBO/WO revelado pela hidratação => nl_enrolment_required",
          rd._reassess_hydrated_applicability(_job(
              "h2", "Operations Intern",
              "You are enrolled in an HBO/WO programme.", "Parfumado"))
          == "nl_enrolment_required")
    check("german_required segue (contrato F20/F25 intacto)",
          rd._reassess_hydrated_applicability(_job(
              "h3", "Praktikum Data",
              "Sehr gute Deutschkenntnisse erforderlich", "Beta"))
          == "german_required")
    check("master_required segue (contrato F20/F25 intacto)",
          rd._reassess_hydrated_applicability(_job(
              "h4", "Praktikum Data",
              "Currently enrolled in a Master's program", "SAP"))
          == "master_required")
    check("aplicável => None",
          rd._reassess_hydrated_applicability(_job(
              "h5", "Praktikum Data Analytics", "English required.", "Alpha"))
          is None)


# ---------------------------------------------------------------------------
# T6 — contagem derivada "aplicável" no metrics (header de universo)
# ---------------------------------------------------------------------------

def t6_applicability_metrics() -> None:
    section("T6 — _applicability_metrics_record (eligible − flagged)")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import refresh_daily as rd  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        check("refresh_daily importável", False, repr(exc))
        return

    ranking = [
        {"id": "a", "hydration_inapplicable": "german_required"},
        {"id": "b", "hydration_inapplicable": "eu_citizenship_required"},
        {"id": "c", "hydration_inapplicable": "eu_citizenship_required"},
        {"id": "d"},  # aplicável
        {"id": "e"},
    ]
    rec = rd._applicability_metrics_record(ranking, run_id="run-1")
    check("type applicability", rec["type"] == "applicability")
    check("eligible = 5", rec["eligible"] == 5)
    check("flagged = 3", rec["flagged"] == 3)
    check("applicable = eligible − flagged = 2", rec["applicable"] == 2)
    check("flagged_por_motivo (german 1, eu 2)",
          rec["flagged_german_required"] == 1
          and rec["flagged_eu_citizenship_required"] == 2)
    check("run_id preservado", rec["run_id"] == "run-1")
    check("todas as razões presentes (5 velhas + 5 novas)",
          all(f"flagged_{r}" in rec
              for r in flt.APPLICABILITY_EXCLUSION_REASONS))


# ---------------------------------------------------------------------------

def main() -> int:
    print("=== test_f37 — saneamento hard-eligibility (EXCLUSÃO, nunca score) ===")
    t1_fixture_auditor()
    t2_new_detectors()
    t3_detector_fixes()
    t4_select_eligible()
    t5_f25_inheritance()
    t6_applicability_metrics()
    print(f"\nF37: {CHECKS} checks, {len(FAILURES)} FAIL")
    if FAILURES:
        print(f"FALHAS: {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
