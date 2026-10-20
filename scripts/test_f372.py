"""Testes da Fase F37.2 — exclusão Erasmus+/pool espontâneo (100% offline).

F37.2 (15/10, decisão do dono "2a. A" = EXCLUIR): postings de programa
Erasmus+ (mobilidade estudantil europeia) e de candidatura espontânea/
"pool" saem do eligible/display/digest pelo MESMO mecanismo da F37 —
flag hard_ineligible com motivo próprio (``erasmus_program``,
``spontaneous_pool``) + contadores ``aplicabilidade_excluidas_*``. Nada
de segundo mecanismo, nada de score.

Detecção TÍTULO-ONLY em ambos (decisão de design medida no universo
13/10): a menção na DESCRIÇÃO não mata — contra-casos verbatim Bosch
Tienen (desc cita Erasmus/partner), NXP ("Young Professional Talent
Pool" = perk), REWE ("Talentpool" = programa pós-candidatura), Edbz
("als eine Art Initiativbewerbung verstehen" = vaga concreta), GRIFOLS
("bewirb dich initiativ" = instrução). O FP em massa do regex largo
``\\binitiativ\\w*`` (124 estágios legítimos "initiatives/Initiativen"
no eligible 13/10) é fechado por word-boundary.

Grupos de teste:

- **T1 FIXTURE CONGELADO PRÓPRIO (auditor offline no CI)** —
  ``fixtures/audit_f372_2026-10-15.json``: 27 jobs VERBATIM dos
  snapshots congelados 13/10+14/10 (campos mínimos + trechos literais,
  NUNCA payload/raw completo; 1 contra-caso sintético DECLARADO trava o
  guard anti-nome-próprio). O auditor roda os detectores contra o
  fixture e exige 100% de acordo (exclusão E motivo).
- **T2 detector erasmus_program** (casos VERBATIM + guard
  anti-nome-próprio): e-farm #85, indiecampers #98, Tierklinik
  "Erasmus plus-Programm", clear "Erasmus Internship", artscience-node
  "Only for Erasmus/Turing". Contra-casos: "Erasmus University
  Rotterdam" (instituição), Bosch desc-erasmus (menção não é programa).
- **T3 detector spontaneous_pool** (casos VERBATIM por família de
  padrão): "Spontaneous Application", "Candidature spontanée",
  "Candidatura Espontânea", "Spontanbewerbung", "Initiativbewerbung",
  "Initiativstelle", "Initiativ" puro, "Talent Pool", "Open
  (Internship) Application", "Speculative/Unsolicited/Initiative
  Application". Contra-casos word-boundary: "initiatives", "Initiativen",
  "Initiative" pura, "ERGREIF DIE INITIATIVE".
- **T4 integração select_eligible**: contadores
  ``aplicabilidade_excluidas_erasmus_program`` /
  ``_spontaneous_pool``; first-match (indiecampers conta UMA vez como
  erasmus_program); reversibilidade (applicability=False = no-op);
  no-op byte a byte em dataset limpo (padrão T5/F18).
- **T5 herança F25** (call site b): ``_reassess_hydrated_applicability``
  devolve os motivos F37.2 — os dois call sites herdam o MESMO
  veredito por construção.
- **T6 contagem no metrics**: ``_applicability_metrics_record`` expõe
  ``flagged_erasmus_program`` / ``flagged_spontaneous_pool`` (a lista
  de razões dirige o registro).

Uso:  .venv/bin/python scripts/test_f372.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import filters as flt  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "audit_f372_2026-10-15.json"

CHECKS = 0
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    mark = "ok" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail and not ok:
        line += f" — {detail}"
    print(line)
    if not ok:
        FAILURES.append(name)


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def _job(jid: str, title: str, desc: str, company: str = "X",
         etype: str | None = "INTERN") -> dict:
    return {"id": jid, "title": title, "description": desc,
            "company": company, "employment_type": etype,
            "location": "Berlin, DE", "country_iso": "de"}


# ---------------------------------------------------------------------------
# T1 — fixture congelado próprio (auditor offline)
# ---------------------------------------------------------------------------
def t1_fixture_auditor() -> None:
    section("T1 — fixture audit_f372_2026-10-15 (auditor offline)")
    if not FIXTURE_PATH.exists():
        check("fixture existe", False, str(FIXTURE_PATH))
        return
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    jobs = fx.get("jobs") or []
    check("fixture tem jobs (>= 24)", len(jobs) >= 24, f"{len(jobs)} jobs")

    bad: list[str] = []
    for e in jobs:
        j = {
            "title": e.get("title") or "",
            "description": " ... ".join(e.get("description_snippets") or []),
            "employment_type": e.get("employment_type"),
            "company": e.get("company"),
        }
        reason = flt.applicability_exclusion_reason(j)
        ok = (reason is not None) == e["expect_excluded"]
        exp_reason = e.get("expected_reason")
        if exp_reason is not None and reason != exp_reason:
            ok = False
        if not ok:
            bad.append(f"{e['group']}/{e['id']}: reason={reason} "
                       f"(exp_excl={e['expect_excluded']}, "
                       f"exp_reason={exp_reason})")
    total = len(jobs)
    check(f"auditor: 100% dos {total} casos do fixture verificados",
          not bad, "; ".join(bad[:4]))

    groups = {e["group"] for e in jobs}
    # grupos obrigatórios: os dois FPs citados na revisão do dono
    for g in ("efarm_erasmus", "indiecampers_erasmus"):
        check(f"fixture contém grupo obrigatório '{g}'", g in groups)
    # contra-casos obrigatórios (menção NÃO mata)
    for g in ("contra_bosch_erasmus_desc", "contra_nxp_talent_pool_desc",
              "contra_rewe_talentpool_desc", "contra_edbz_initiativ_desc",
              "contra_grifols_initiativ_desc", "contra_henkel_initiatives_desc",
              "contra_erasmus_university_guard"):
        check(f"fixture contém contra-caso '{g}'", g in groups)
    # nenhuma vaga legítima do fixture morre
    survivors = [e for e in jobs if not e["expect_excluded"]]
    leaked = [e["group"] for e in survivors
              if flt.applicability_exclusion_reason({
                  "title": e.get("title") or "",
                  "description": " ... ".join(e.get("description_snippets") or []),
                  "employment_type": e.get("employment_type"),
                  "company": e.get("company")}) is not None]
    check(f"auditor: zero falsos-positivos nos {len(survivors)} contra-casos",
          not leaked, ", ".join(leaked))


# ---------------------------------------------------------------------------
# T2 — detector erasmus_program
# ---------------------------------------------------------------------------
def t2_erasmus_program() -> None:
    section("T2 — detector erasmus_program (título-only)")
    # e-farm #85 — verbatim da revisão do dono 14/10 / fixture F37
    check("erasmus: e-farm 'Paid Erasmus+ International Internship...'",
          flt.requires_erasmus_program(
              "Paid Erasmus+ International Internship in International Logistics"))
    # indiecampers #98
    check("erasmus: indiecampers 'Spontaneous Application | ... - Erasmus+'",
          flt.requires_erasmus_program(
              "Spontaneous Application | Tourism & Operations Internship - Erasmus+"))
    # Tierklinik Ismaning
    check("erasmus: 'Erasmus plus-Programm als Praktikum...'",
          flt.requires_erasmus_program(
              "Erasmus plus-Programm als Praktikum  für Student*innen und "
              "Absolvent*innen der Veterinärmedizin"))
    # clear
    check("erasmus: clear 'Erasmus Internship - Partnership Development Intern'",
          flt.requires_erasmus_program(
              "Erasmus Internship - Partnership Development Intern"))
    # artscience-node
    check("erasmus: 'Only for Erasmus/Turing Internship: AI/IT...'",
          flt.requires_erasmus_program(
              "Only for Erasmus/Turing Internship: AI/IT, Graphic Designer "
              "and/or Computer Science&Technologies on "))
    # variantes de grafia
    check("erasmus: 'ERASMUS+' maiúsculo",
          flt.requires_erasmus_program(
              "ERASMUS+ Traineeship in Logistics"))
    # GUARD anti-nome-próprio (zero casos no universo; defensivo)
    check("guard: 'Erasmus University Rotterdam' NÃO é programa",
          not flt.requires_erasmus_program(
              "Research Internship at Erasmus University Rotterdam"))
    check("guard: 'Erasmus Universität' NÃO é programa",
          not flt.requires_erasmus_program(
              "Werkstudent Erasmus Universität Rotterdam"))
    check("guard: programa + universidade no MESMO título AINDA é programa",
          flt.requires_erasmus_program(
              "Erasmus+ Internship hosted at Erasmus University Rotterdam"))
    # contra-caso central: menção na DESCRIÇÃO não mata
    check("contra: menção Erasmus na DESC não mata (Bosch Tienen)",
          not flt.requires_erasmus_program(
              "Internship Logistics",
              "Open to candidates from Erasmus partner universities."))
    check("contra: título sem erasmus NÃO dispara",
          not flt.requires_erasmus_program("Supply Chain Internship Hamburg", ""))


# ---------------------------------------------------------------------------
# T3 — detector spontaneous_pool
# ---------------------------------------------------------------------------
def t3_spontaneous_pool() -> None:
    section("T3 — detector spontaneous_pool (título-only)")
    # EN — verbatim VW/Webasto/Allianz/Barco/Swisslife/indiecampers
    check("pool: 'Spontaneous Application - Spain' (VW)",
          flt.is_spontaneous_pool_title("Spontaneous Application - Spain"))
    check("pool: 'Spontaneous Application Luxembourg (F/M/X)' (Webasto)",
          flt.is_spontaneous_pool_title(
              "Spontaneous Application Luxembourg (F/M/X)"))
    check("pool: 'Spontaneous Applications' plural (Allianz)",
          flt.is_spontaneous_pool_title("Spontaneous Applications"))
    # FR — Liebherr/NXP
    check("pool: 'Candidature spontanée' (Liebherr FR)",
          flt.is_spontaneous_pool_title(
              "Candidature spontanée - Liebherr Distribution et Services France"))
    # PT/ES — VW
    check("pool: 'Candidatura Espontânea - Portugal' (VW PT)",
          flt.is_spontaneous_pool_title("Candidatura Espontânea - Portugal"))
    check("pool: 'Candidatura Espontánea - Spain' (VW ES)",
          flt.is_spontaneous_pool_title("Candidatura Espontánea - Spain"))
    # DE — Spontanbewerbung (Festo/SONEPAR)
    check("pool: 'Spontanbewerbungen Festo...' (Festo)",
          flt.is_spontaneous_pool_title("Spontanbewerbungen Festo Gewindetriebe AG"))
    check("pool: 'Spontanbewerbung' singular (SONEPAR)",
          flt.is_spontaneous_pool_title("Spontanbewerbung"))
    # DE — Initiativbewerbung (Fraunhofer/AIXTRON/Marquardt)
    check("pool: 'Initiativbewerbung wissenschaftliche / Hilfskräfte...' (Fraunhofer)",
          flt.is_spontaneous_pool_title(
              "Initiativbewerbung wissenschaftliche / Hilfskräfte all genders"))
    check("pool: 'Praktikant ... - Initiativbewerbung' (Marquardt)",
          flt.is_spontaneous_pool_title(
              "Praktikant (m/w/d) im kaufmännischen Bereich - Initiativbewerbung"))
    check("pool: 'Initiativbewerbungen' plural (continental)",
          flt.is_spontaneous_pool_title(
              "Initiativbewerbungen BestDrive Austria GmbH"))
    # DE — Initiativstelle (Fraunhofer HHI / VW ZENDA)
    check("pool: 'Initiativstelle' (Fraunhofer HHI)",
          flt.is_spontaneous_pool_title(
              "Fraunhofer Heinrich-Hertz-Institut (HHI) - Initiativstelle"))
    # DE — Initiativ puro (Witzenmann/datev)
    check("pool: 'Praktikant (m/w/d)  (Initiativ)' (Witzenmann)",
          flt.is_spontaneous_pool_title("Praktikant (m/w/d)  (Initiativ)"))
    check("pool: 'Initiativ für IT' (datev)",
          flt.is_spontaneous_pool_title("Initiativ für IT"))
    # EN — Talent Pool (ABB)
    check("pool: 'Talent Pool - R2R - Accounting & Reporting' (ABB)",
          flt.is_spontaneous_pool_title(
              "Talent Pool - R2R - Accounting & Reporting"))
    check("pool: 'Student Internship with German Talent Pool' (ABB)",
          flt.is_spontaneous_pool_title(
              "ABB Kraków Student Internship with German Talent Pool – "
              "Share your CV with us"))
    # EN — Open Application (noxmobility/jacklinks/pareto/Enzazaden)
    check("pool: 'Internship - Open Application (f/m/d)' (noxmobility)",
          flt.is_spontaneous_pool_title("Internship - Open Application (f/m/d)"))
    check("pool: 'Open Application - Investment Banking Internship' (pareto)",
          flt.is_spontaneous_pool_title(
              "Open Application - Investment Banking Internship"))
    check("pool: 'Open Internship Application' (Enzazaden)",
          flt.is_spontaneous_pool_title("Open Internship Application"))
    # EN — Speculative/Unsolicited/Initiative Application (Fraunhofer/nxp)
    check("pool: 'SPECULATIVE APPLICATION: INTERNSHIP' (Fraunhofer)",
          flt.is_spontaneous_pool_title("SPECULATIVE APPLICATION: INTERNSHIP"))
    check("pool: 'Unsolicited application students' (Fraunhofer)",
          flt.is_spontaneous_pool_title("Unsolicited application students"))
    check("pool: 'Student Internships - Initiative Application (m/f/d)' (nxp)",
          flt.is_spontaneous_pool_title(
              "Student Internships - Initiative Application (m/f/d)"))

    # ---- word-boundary: o FP em massa do regex largo fica vivo ----
    check("wb: 'initiatives' NÃO casa (Henkel/BASF desc FP)",
          not flt.is_spontaneous_pool_title(
              "Internship in Engineering, Digitalization and Maintenance"))
    check("wb: 'Initiativen' NÃO casa (BASF/Lidl DE)",
          not flt.is_spontaneous_pool_title("unsere Initiativen"))
    check("wb: 'Initiative' pura NÃO casa (slogan)",
          not flt.is_spontaneous_pool_title("TAKE THE INITIATIVE"))
    check("wb: 'ERGREIF DIE INITIATIVE' NÃO casa (slogan)",
          not flt.is_spontaneous_pool_title("ERGREIF DIE INITIATIVE"))
    check("wb: 'Strategic Initiatives & Operations' NÃO casa (ABB US)",
          not flt.is_spontaneous_pool_title(
              "Manager, Strategic Initiatives & Operations - US"))
    # ---- menção na DESCRIÇÃO não mata ----
    check("contra: NXP 'Young Professional Talent Pool' na desc NÃO mata",
          not flt.applicability_exclusion_reason({
              "title": "Intern (f/m/d) AI-Driven Data Analysis",
              "description": "Possibility to become part of NXP's Young "
                             "Professional Talent Pool",
              "employment_type": "INTERN"}))
    # F86 (20/10): o título "Werkstudent International Tax" virou exclusão
    # job_type_non_internship (matrícula alemã) — o counter-case POOL é
    # sobre a regra título-only do spontaneous_pool e segue provado (a)
    # pelo detector direto e (b) pela full-chain com título de estágio.
    check("contra: REWE 'Werkstudent...' no título não é pool (título-only)",
          not flt.is_spontaneous_pool_title(
              "Werkstudent International Tax (m/w/d)"))
    check("contra: REWE 'Talentpool' na desc NÃO mata (título de estágio)",
          not flt.applicability_exclusion_reason({
              "title": "Praktikant/in (m/f/d) Steuer & Treasury",
              "description": "Aufnahme in das Bindungsprogramm „future steps“ "
                             "mit exklusiven Events und Talentpool.",
              "employment_type": None}))
    check("contra: Edbz 'als eine Art Initiativbewerbung' na desc NÃO mata",
          not flt.applicability_exclusion_reason({
              "title": "Praktikant/in (m/f/d) im Bereich Supply Chain",
              "description": "Deine Bewerbung kannst Du daher als eine Art "
                             "Initiativbewerbung verstehen.",
              "employment_type": None}))
    check("contra: GRIFOLS 'bewirb dich initiativ' na desc NÃO mata",
          not flt.applicability_exclusion_reason({
              "title": "Praktikum bei Haema",
              "description": "Dann bewirb dich initiativ für ein Praktikum "
                             "bei Haema.",
              "employment_type": None}))
    # ---- vaga CONCRETA com marcador de pool no título: julgamento ----
    # Barco "Internship - Spontaneous application" (Kortrijk BE): o título
    # nomeia o CANAL; não há posição concreta — documentado no relatório
    # (julgamento F37.2, decisões citadas).
    check("julgamento: Barco 'Internship - Spontaneous application' EXCLUI "
          "(canal, não vaga concreta)",
          flt.is_spontaneous_pool_title(
              "Internship - Spontaneous application"))


# ---------------------------------------------------------------------------
# T4 — integração select_eligible
# ---------------------------------------------------------------------------
def t4_select_eligible() -> None:
    section("T4 — integração: contadores, first-match, reversibilidade")
    # descrições carregam keywords de área (supply chain/procurement) para
    # que os jobs sintéticos atravessem as camadas tipo/área e cheguem ao
    # estágio de aplicabilidade — alvo dos contadores F37.2.
    jobs = [
        _job("ok-1", "Praktikum Data Analytics 1",
             "Supply chain analytics with the procurement team."),
        _job("ok-2", "Internship Supply Chain 2",
             "Support the logistics and supply chain team."),
        _job("ok-3", "Praktikum Einkauf 3",
             "Procurement and purchasing topics."),
        _job("e-erasmus", "Paid Erasmus+ International Internship",
             "Logistics and supply chain program.", "e-farm"),
        _job("e-pool", "Praktikant Supply Chain (m/w/d) - Initiativbewerbung",
             "Send us your CV for supply chain roles.", "Marquardt"),
        _job("e-both", "Spontaneous Application | Supply Chain Internship - "
             "Erasmus+", "Erasmus program in supply chain.", "indiecampers"),
    ]
    sel, counts = flt.select_eligible(jobs, country="de")
    ids = [j["id"] for j in sel]
    check("3 vagas limpas ficam", ids == ["ok-1", "ok-2", "ok-3"], str(ids))
    check("contagem erasmus_program = 2 (e-erasmus + e-both)",
          counts["aplicabilidade_excluidas_erasmus_program"] == 2,
          str(counts.get("aplicabilidade_excluidas_erasmus_program")))
    check("contagem spontaneous_pool = 1",
          counts["aplicabilidade_excluidas_spontaneous_pool"] == 1)
    check("first-match: e-both conta UMA vez, como erasmus_program "
          "(Erasmus+ vence pool)",
          flt.applicability_exclusion_reason(
              next(j for j in jobs if j["id"] == "e-both"))
          == "erasmus_program"
          and counts["aplicabilidade_excluidas_erasmus_program"]
          + counts["aplicabilidade_excluidas_spontaneous_pool"] == 3
          and counts["aplicabilidade"] == 3)
    # razões na tupla oficial (dirige contadores + registro metrics)
    check("erasmus_program/spontaneous_pool em APPLICABILITY_EXCLUSION_REASONS",
          "erasmus_program" in flt.APPLICABILITY_EXCLUSION_REASONS
          and "spontaneous_pool" in flt.APPLICABILITY_EXCLUSION_REASONS)
    # reversibilidade: applicability=False desliga (comportamento pré-F37.2)
    sel_off, counts_off = flt.select_eligible(jobs, country="de",
                                              applicability=False)
    check("reversível: applicability=False mantém as 6",
          len(sel_off) == 6)
    check("reversível: contagens F37.2 zeradas com estágio off",
          counts_off.get("aplicabilidade_excluidas_erasmus_program", 0) == 0
          and counts_off.get("aplicabilidade_excluidas_spontaneous_pool", 0) == 0)
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
# T5 — herança F25: call site (b) reusa a MESMA função
# ---------------------------------------------------------------------------
def t5_f25_inheritance() -> None:
    section("T5 — herança F25: re-avaliação pós-hidratação herda F37.2")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import refresh_daily as rd  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        check("refresh_daily importável", False, repr(exc))
        return
    check("Erasmus+ revelado pela hidratação => erasmus_program",
          rd._reassess_hydrated_applicability(_job(
              "h1", "Paid Erasmus+ International Internship",
              "Program for Erasmus students.", "e-farm")) == "erasmus_program")
    check("pool revelado pela hidratação => spontaneous_pool",
          rd._reassess_hydrated_applicability(_job(
              "h2", "Praktikant (m/w/d) - Initiativbewerbung",
              "Send us your CV.", "Marquardt")) == "spontaneous_pool")
    check("aplicável => None (contrato intacto)",
          rd._reassess_hydrated_applicability(_job(
              "h3", "Praktikum Data Analytics", "English required.",
              "Alpha")) is None)
    check("german_required segue (contrato F20/F25 intacto)",
          rd._reassess_hydrated_applicability(_job(
              "h4", "Praktikum Data",
              "Sehr gute Deutschkenntnisse erforderlich", "Beta"))
          == "german_required")


# ---------------------------------------------------------------------------
# T6 — registro metrics expõe os motivos novos
# ---------------------------------------------------------------------------
def t6_applicability_metrics() -> None:
    section("T6 — _applicability_metrics_record: flagged_* novos")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import refresh_daily as rd  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        check("refresh_daily importável", False, repr(exc))
        return
    ranking = [
        {"id": "a", "hydration_inapplicable": "erasmus_program"},
        {"id": "b", "hydration_inapplicable": "spontaneous_pool"},
        {"id": "c"},
    ]
    rec = rd._applicability_metrics_record(ranking, run_id="run-1")
    check("flagged_erasmus_program = 1",
          rec.get("flagged_erasmus_program") == 1)
    check("flagged_spontaneous_pool = 1",
          rec.get("flagged_spontaneous_pool") == 1)
    check("applicable = eligible − flagged = 1",
          rec.get("applicable") == 1)
    check("todas as razões presentes na tupla (10 F37 + 2 F37.2)",
          all(f"flagged_{r}" in rec
              for r in flt.APPLICABILITY_EXCLUSION_REASONS))
    check("motivos F37.2 na tupla oficial",
          set(flt.APPLICABILITY_EXCLUSION_REASONS) >= {
              "erasmus_program", "spontaneous_pool"})


# ---------------------------------------------------------------------------

def main() -> int:
    print("=== test_f372 — exclusão Erasmus+/pool espontâneo (F37.2) ===")
    t1_fixture_auditor()
    t2_erasmus_program()
    t3_spontaneous_pool()
    t4_select_eligible()
    t5_f25_inheritance()
    t6_applicability_metrics()
    print(f"\nF37.2: {CHECKS} checks, {len(FAILURES)} FAIL")
    if FAILURES:
        print(f"FALHAS: {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
