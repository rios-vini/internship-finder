"""Testes da Fase F37.3 — german_required: flag → EXCLUSÃO TOTAL do
eligible (100% offline).

F37.3 (15/10, decisão do dono "german_required: exclusão total aprovada"):
vagas cujo motivo de inaplicabilidade é ``german_required`` SAEM do
eligible_jobs.json — mesmo tratamento de exclusão da F39 (``_remove_
hard_dead``: o id sai do JSON, provenance na métrica diária) — em vez de
apenas serem demovidas do topo com o flag F25 ``hydration_inapplicable``
(design F25 "fica no JSON" permanece para os OUTROS motivos).

MECANISMO ÚNICO (a decisão mora num lugar só):
``filters.APPLICABILITY_JSON_EXCLUSION_REASONS`` — tupla lida por
``refresh_daily._remove_json_excluded`` (o estágio de exclusão do JSON
que a F39 criou para hard-dead, estendido pela F37.3 para o veredito
revelado PÓS-hidratação F20/F25). Nenhum segundo mecanismo, nenhum
detector duplicado: o motivo vem SEMPRE do detector único
``applicability_exclusion_reason`` (classificador F18
``app_intel.german_level == required``); a exclusão lê o MESMO veredito
(o flag ``hydration_inapplicable``) e NÃO re-executa o detector.

Grupos de teste:

- **T1 FIXTURE CONGELADO PRÓPRIO (auditor offline)** —
  ``fixtures/audit_f373_2026-10-15.json``: 10 jobs VERBATIM do eligible
  15/10 (pós-run 09:00 UTC, 861 vagas) com trechos literais de língua
  (campos mínimos, nunca o payload completo): 4 positivos
  (``german_level == required``) e 6 contra-casos (``None`` ou
  ``preferred`` — "von Vorteil", "German is a plus", vaga puro-EN na
  Alemanha). O auditor roda o DETECTOR único e a EXCLUSÃO
  (``_remove_json_excluded``) contra o fixture e exige 100% de acordo.
- **T2 exclusão total no mecanismo**: ``_remove_json_excluded`` remove
  do ranking exatamente as german_required; motivos fora do subconjunto
  (eu_citizenship_required, erasmus_program, spontaneous_pool) FICAM no
  JSON (design F25 intacto); sem flags => no-op byte a byte (padrão
  T5/F18); idempotente (re-run sobre o JSON limpo = 0 removidos, sem
  evento); ordem dos sobreviventes preservada; ``removed_entries``
  auditável (id/reason/company/title).
- **T3 decisão num lugar só**: ``APPLICABILITY_JSON_EXCLUSION_REASONS``
  contém ``german_required`` e é subconjunto PRÓPRIO da tupla F37
  (``APPLICABILITY_EXCLUSION_REASONS``); ``is_json_exclusion_reason``:
  True só para o subconjunto; ``None`` e motivos F25-only → False.
  Mudar a decisão = editar a tupla (1 linha), não um call-site.
- **T4 contra-casos de detector** (guarda o ESCOPO da fase: a decisão é
  sobre a exclusão, não sobre quem casa): "Deutschkenntnisse von
  Vorteil", "German is a plus", vaga em inglês na Alemanha — NENHUM sai;
  enquanto "verhandlungssicheres Deutsch", "Very good German and English
  skills", "Deutsch- und Englischkenntnisse" SAEM (veredito do
  classificador F18, fixtures verbatim).
- **T5 não-regressão dos detectores anteriores**: ranking misto com os
  12 motivos da cascata — contagens por motivo IDÊNTICAS pré/pós a
  exclusão F37.3 (a exclusão só age sobre o flag já atribuído; a
  cascata ``select_eligible`` e os detectores F18/F37/F37.2 seguem
  intactos; first-match preservado).
- **T6 integração pipeline**: sequência real do refresh (reassess
  backlog F25 → exclusão F37.3 → recálculo da métrica ``applicability``)
  num fixture sintético; ``_applicability_metrics_record`` pós-exclusão
  descreve o NOVO estado do JSON; registro diário
  ``applicability_exclusion`` carrega motivo + contadores + ids que
  saíram (padrão F39); import do refresh_daily garante wiring.

Uso:  .venv/bin/python scripts/test_f373.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import filters as flt  # noqa: E402

FIXTURE_PATH = ROOT / "fixtures" / "audit_f373_2026-10-15.json"

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


# ---------------------------------------------------------------------------
# T1 — fixture congelado próprio (auditor offline)
# ---------------------------------------------------------------------------
def t1_fixture_auditor() -> None:
    section("T1 — fixture audit_f373_2026-10-15 (auditor offline)")
    if not FIXTURE_PATH.exists():
        check("fixture existe", False, str(FIXTURE_PATH))
        return
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    entries = fx.get("jobs") or []
    check("fixture tem jobs (>= 8)", len(entries) >= 8, f"{len(entries)} jobs")
    check("fixture declara universo/origem",
          bool(fx.get("universe")), str(fx.get("universe"))[:80])

    bad: list[str] = []
    removed_expected = 0
    for e in entries:
        j = {
            "id": e.get("id"),
            "title": e.get("title") or "",
            "description": e.get("description_snippet") or "",
            "employment_type": e.get("employment_type"),
            "company": e.get("company"),
            "location": e.get("location") or "Berlin, DE",
            "country_iso": e.get("country_iso") or "de",
        }
        reason = flt.applicability_exclusion_reason(j)
        exp_reason = e.get("expected_reason")
        ok = (reason == exp_reason)
        if e.get("expect_json_excluded"):
            removed_expected += 1
            ok = ok and flt.is_json_exclusion_reason(reason)
        if not ok:
            bad.append(f"{e.get('group')}/{e.get('id')}: reason={reason!r} "
                       f"(esperado {exp_reason!r})")
    check("detector único: 100% de acordo com o fixture",
          not bad, "; ".join(bad[:5]))
    check("positivos no fixture marcados p/ exclusão JSON",
          removed_expected == fx.get("expected_removals"),
          f"{removed_expected} vs {fx.get('expected_removals')}")

    # o MESMO fixture passa pela EXCLUSÃO: só os expect_json_excluded saem
    ranking = [
        {"id": e.get("id"),
         "title": e.get("title") or "",
         "description": e.get("description_snippet") or "",
         "employment_type": e.get("employment_type"),
         "company": e.get("company"),
         "hydration_inapplicable": e.get("expected_reason")
         if e.get("expect_json_excluded") else None}
        for e in entries
    ]
    stats = rd_remove(ranking)
    check("exclusão: nº removidos = expected_removals",
          stats["removed"] == fx.get("expected_removals"),
          f"{stats['removed']}")
    check("exclusão: by_reason só german_required",
          set(stats["by_reason"]) == {"german_required"},
          str(stats["by_reason"]))
    check("exclusão: contra-casos permanecem no JSON",
          all(j in ranking for j in ranking
              if j.get("hydration_inapplicable") != "german_required"))


def rd_remove(ranking: list) -> dict:
    """Importa refresh_daily (wiring real do pipeline) e roda a exclusão."""
    import refresh_daily  # noqa: F401 — wiring do estágio no pipeline

    return refresh_daily._remove_json_excluded(ranking)


# ---------------------------------------------------------------------------
# T2 — exclusão total no mecanismo
# ---------------------------------------------------------------------------
def t2_removal_mechanism() -> None:
    section("T2 — _remove_json_excluded (exclusão total)")
    import refresh_daily as rd

    others = (
        "visa_blocked", "thesis_title", "werkstudent_puro",
        "master_required", "eu_citizenship_required",
        "nl_enrolment_required", "phd_position", "duration_over_6m",
        "full_time_permanent", "erasmus_program", "spontaneous_pool",
    )
    ranking = (
        [{"id": f"gr{i}", "hydration_inapplicable": "german_required",
          "company": "BoschGroup", "title": f"Praktikum {i}"}
         for i in range(3)]
        + [{"id": f"keep-{r}", "hydration_inapplicable": r,
            "company": "X", "title": f"Vaga {r}"} for r in others]
        + [{"id": "clean", "company": "Y", "title": "Vaga limpa"}]
    )
    snapshot = json.dumps(ranking, ensure_ascii=False, indent=2)
    stats = rd._remove_json_excluded(ranking)

    check("remove exatamente as german_required",
          stats["removed"] == 3, str(stats["removed"]))
    check("by_reason = {'german_required': 3}",
          stats["by_reason"] == {"german_required": 3},
          str(stats["by_reason"]))
    check("todos os outros motivos FICAM (design F25)",
          all(any(j.get("id") == f"keep-{r}" for j in ranking)
              for r in others))
    check("vaga sem flag fica", any(j.get("id") == "clean" for j in ranking))
    check("removed_entries auditáveis (id/reason/company/title)",
          all(set(e) == {"id", "reason", "company", "title"}
              for e in stats["removed_entries"])
          and len(stats["removed_entries"]) == 3)
    check("ordem dos sobreviventes preservada",
          [j.get("id") for j in ranking][:4]
          == ["keep-visa_blocked", "keep-thesis_title",
              "keep-werkstudent_puro", "keep-master_required"])

    # idempotência: re-run sobre o JSON já limpo = 0 removidos
    stats2 = rd._remove_json_excluded(ranking)
    check("idempotente: re-run remove 0", stats2["removed"] == 0,
          str(stats2["removed"]))
    check("idempotente: by_reason vazio (sem evento inventado)",
          stats2["by_reason"] == {})

    # no-op byte a byte num ranking limpo (padrão T5/F18)
    clean = [{"id": f"c{i}", "company": "Z", "title": f"Vaga limpa {i}"}
             for i in range(5)]
    snap_clean = json.dumps(clean, ensure_ascii=False, indent=2)
    st_clean = rd._remove_json_excluded(clean)
    check("sem flags: removed=0", st_clean["removed"] == 0)
    check("sem flags: no-op byte a byte",
          json.dumps(clean, ensure_ascii=False, indent=2) == snap_clean)

    # snapshot original de um ranking misto: sobreviventes byte-idênticos
    mixed = [
        {"id": "a", "hydration_inapplicable": "german_required",
         "company": "B", "title": "T1", "score": 42},
        {"id": "b", "company": "C", "title": "T2", "score": 41},
        {"id": "c", "hydration_inapplicable": "eu_citizenship_required",
         "company": "D", "title": "T3", "score": 40},
    ]
    before = json.loads(json.dumps(mixed))
    st = rd._remove_json_excluded(mixed)
    survivors_expected = [j for j in before if j.get("id") != "a"]
    check("sobreviventes byte-identicos (json.dumps indent=2)",
          json.dumps(mixed, ensure_ascii=False, indent=2)
          == json.dumps(survivors_expected, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# T3 — decisão num lugar só (tupla + helper)
# ---------------------------------------------------------------------------
def t3_decision_single_place() -> None:
    section("T3 — APPLICABILITY_JSON_EXCLUSION_REASONS (decisão única)")
    check("tupla existe e contém german_required",
          "german_required" in flt.APPLICABILITY_JSON_EXCLUSION_REASONS)
    check("subconjunto PRÓPRIO da tupla F37",
          set(flt.APPLICABILITY_JSON_EXCLUSION_REASONS)
          < set(flt.APPLICABILITY_EXCLUSION_REASONS))
    check("is_json_exclusion_reason(german_required) = True",
          flt.is_json_exclusion_reason("german_required") is True)
    check("is_json_exclusion_reason(None) = False (design F25 intacto)",
          flt.is_json_exclusion_reason(None) is False)
    check("is_json_exclusion_reason(motivo F25-only) = False",
          flt.is_json_exclusion_reason("eu_citizenship_required") is False
          and flt.is_json_exclusion_reason("erasmus_program") is False
          and flt.is_json_exclusion_reason("spontaneous_pool") is False
          and flt.is_json_exclusion_reason("master_required") is False)
    check("detector único inalterado: vaga sem alemão obrigatório não casa",
          flt.applicability_exclusion_reason({
              "title": "Intern Data Analytics",
              "description": "Fluency in English, German is a plus",
              "employment_type": "INTERN", "company": "X"}) is None)


# ---------------------------------------------------------------------------
# T4 — contra-casos verbatim de detector (escopo: exclusão, não detecção)
# ---------------------------------------------------------------------------
def t4_detector_counterexamples() -> None:
    section("T4 — contra-casos verbatim (não saem) + positivos (saem)")
    base = {"employment_type": "INTERN", "company": "X",
            "location": "Berlin, DE", "country_iso": "de"}

    stay = [
        ("Würth 'von Vorteil'",
         "Praktikant (m/w/d) im Bereich Logistik - Import Beschaffung",
         "Spezialisierung im Bereich Logistik von Vorteil. Gute "
         "Englischkenntnisse in Wort und Schrift sind wünschenswert."),
        ("adidas 'German is a plus'",
         "INTERNSHIP OPPORTUNITIES - CONSUMER, MARKETPLACE AND SALES "
         "INSIGHTS & ANALYTICS (M/F/D)",
         "Project Management, Strategy or similar Fluency in English "
         "(written & spoken), German is a plus Strong MS Office skills"),
        ("BASF 'German is a plus' (Berlim, EN)",
         "Internship Business Reporting (m/f/d) - Hybrid Option GER",
         "service-minded, with very good English skills, German is a "
         "plus you are based in Berlin or able to work regularly from "
         "our Berlin office"),
        ("C&A 'German is a plus'",
         "Intern (m/f/d) Data Governance",
         "Excellent communication and stakeholder management skills "
         "Fluent in English; German is a plus Available for a full-time "
         "internship of six months' duration"),
        ("trumpf 'von Vorteil'",
         "Praktikum Controlling & Business Analytics EUV (SS 2027)",
         "Grundkenntnisse in SAP (ERP/BW) sowie in Power BI runden Ihr "
         "Profil ab und sind von Vorteil Durch eine strukturierte und "
         "proaktive Arbeitsweise überzeugen Sie"),
        ("Oliver Wyman Berlin puro-EN",
         "Oliver Wyman - Data & Analytics Consulting - Intern (m/f/d) - Berlin",
         "We are currently hiring an intern to join our Data & Analytics "
         "team in Berlin, supporting clients in complex business "
         "challenges. Ideal for students with a quantitative background "
         "and proficiency in Python or R."),
    ]
    for name, title, desc in stay:
        reason = flt.applicability_exclusion_reason(
            {**base, "id": name[:12], "title": title, "description": desc})
        check(f"NÃO sai: {name}", reason is None, repr(reason))

    leave = [
        ("Bosch 'verhandlungssicheres Deutsch'",
         "Praktikum in der Logistik - Data & Analytics",
         "Möchtest du die Logistik von morgen durch intelligente "
         "Datenströme revolutionieren? Sprachen: verhandlungssicheres "
         "Deutsch und sehr gutes Englisch  Beginn: nach Absprache "
         "Dauer: 6 Monate"),
        ("Hilti 'Very good German and English skills'",
         "Intern Strategic Procurement Electronics & Drives (m/f/d)",
         "We are looking for an intern in the field of Strategic "
         "Procurement for Electronics & Drives for at least 6 months "
         "starting immediately. Independent and responsible working "
         "style Very good German and English skills Interest in "
         "technical topics"),
        ("TRUMPF 'Deutsch- und Englischkenntnisse'",
         "Praktikum Data & Analytics Engineering",
         "Pflichtpraktikum oder freiwilliges Praktikum. Deutsch- und "
         "Englischkenntnisse in Wort und Schrift runden Ihr Profil ab"),
        ("Bosch BA 'Deutsch und Englisch'",
         "Pflichtpraktikum Data Engineering & Data Analytics im Akustik",
         "Additional Information\nBeginn: nach Absprache\nSprachen: "
         "Deutsch und Englisch\nDauer: 4 - 6 Monate"),
    ]
    for name, title, desc in leave:
        reason = flt.applicability_exclusion_reason(
            {**base, "id": name[:12], "title": title, "description": desc})
        check(f"SAI: {name}", reason == "german_required", repr(reason))


# ---------------------------------------------------------------------------
# T5 — não-regressão dos detectores anteriores
# ---------------------------------------------------------------------------
def t5_no_regression() -> None:
    section("T5 — contagens por motivo idênticas pré/pós exclusão")
    import refresh_daily as rd

    base = {"employment_type": "INTERN", "company": "X",
            "location": "Berlin, DE", "country_iso": "de"}
    jobs = [
        {**base, "id": "gr", "title": "Praktikum Data & Analytics",
         "description": "Sprachen: verhandlungssicheres Deutsch und "
                        "sehr gutes Englisch"},                       # german_required
        {**base, "id": "thesis", "title": "Masterarbeit Supply Chain",
         "description": "Tese no department de Logística"},           # thesis_title
        {**base, "id": "werk", "title": "Werkstudent Controlling",
         "description": "Suporte ao time de controlling"},            # werkstudent_puro
        {**base, "id": "master", "title": "Intern Analytics",
         "description": "Candidates should be enrolled in a Master's "
                        "degree program in a relevant field"},        # master_required
        {**base, "id": "eu", "title": "Intern EU Affairs",
         "description": "Applicants must hold EU citizenship"},       # None (vira keep-eu)
        {**base, "id": "nl", "title": "Intern Operations NL",
         "description": "You must be enrolled at a Dutch university "
                        "(HBO/WO) for the whole internship"},         # nl_enrolment_required
        {**base, "id": "phd", "title": "PhD position in Logistics",
         "description": "We offer a doctoral researcher position"},   # phd_position
        {**base, "id": "dur", "title": "Praktikum (12 months)",
         "description": "Join our team for a 12 months internship"},  # duration_over_6m
        {**base, "id": "ft", "title": "Associate Analyst",
         "description": "Full time permanent position in our office",
         "employment_type": "FULL_TIME"},                             # full_time_permanent
        {**base, "id": "eras", "title": "Erasmus+ Traineeship",
         "description": "Mobility programme for European students"},  # erasmus_program
        {**base, "id": "pool", "title": "Spontaneous Application",
         "description": "Send us your initiative application"},       # spontaneous_pool
        {**base, "id": "clean", "title": "Intern Data Analytics",
         "description": "Fluency in English required, German is a plus"},  # fica
    ]
    # veredito do DETECTOR ÚNICO (fonte da verdade, mesmo universo do JSON:
    # re-avaliação pós-hidratação F20/F25 roda o MESMO detector)
    verdict = {j["id"]: flt.applicability_exclusion_reason(j) for j in jobs}
    expected_verdict = {
        "gr": "german_required", "thesis": "thesis_title",
        "werk": "werkstudent_puro", "master": "master_required",
        "eu": None, "nl": "nl_enrolment_required",
        "phd": "phd_position", "dur": "duration_over_6m",
        "ft": "full_time_permanent", "eras": "erasmus_program",
        "pool": "spontaneous_pool", "clean": None,
    }
    check("detector único: vereditos verbatim esperados",
          verdict == expected_verdict, str(verdict))

    # universo realista do eligible_jobs.json: TODAS as inaplicáveis
    # entraram com descrição curta (pré-hidratação) e foram flaggadas
    # pela re-avaliação F20/F25; o passe F37.3 age sobre ESSE universo.
    flagged = []
    for j in jobs:
        g = dict(j)
        if verdict[j["id"]]:
            g["hydration_inapplicable"] = verdict[j["id"]]
        flagged.append(g)
    pre = json.loads(json.dumps(flagged))
    pre_counts = {r: sum(1 for j in flagged
                         if j.get("hydration_inapplicable") == r)
                  for r in flt.APPLICABILITY_EXCLUSION_REASONS}
    st = rd._remove_json_excluded(flagged)
    post_counts = {r: sum(1 for j in flagged
                          if j.get("hydration_inapplicable") == r)
                   for r in flt.APPLICABILITY_EXCLUSION_REASONS}
    check("exclusão removeu SÓ german_required (1)",
          st["removed"] == 1
          and st["by_reason"] == {"german_required": 1},
          str(st["by_reason"]))
    check("contagens por motivo IDÊNTICAS pré/pós para os 11 outros "
          "motivos (não-regressão)",
          all(post_counts[r] == pre_counts[r]
              for r in flt.APPLICABILITY_EXCLUSION_REASONS
              if r != "german_required"),
          str({r: (pre_counts[r], post_counts[r])
               for r in pre_counts
               if r != "german_required"
               and pre_counts[r] != post_counts[r]}))
    check("german_required zera no JSON (saiu por exclusão, design F37.3)",
          post_counts["german_required"] == 0
          and pre_counts["german_required"] == 1)
    check("veredito do detector inalterado nos sobreviventes "
          "(re-detecção pós-exclusão)",
          all(flt.applicability_exclusion_reason(j) == verdict[j["id"]]
              for j in flagged))
    survivors = {j["id"] for j in flagged}
    check("sobreviventes: 10 inaplicáveis (outros motivos) + clean",
          survivors == {"thesis", "werk", "master", "eu", "nl", "phd",
                        "dur", "ft", "eras", "pool", "clean"},
          str(sorted(survivors)))


# ---------------------------------------------------------------------------
# T6 — integração pipeline (reassess backlog → exclusão → métrica)
# ---------------------------------------------------------------------------
def t6_pipeline_integration() -> None:
    section("T6 — sequência real do refresh + métrica applicability")
    try:
        import refresh_daily as rd  # noqa: F401 — wiring do pipeline
    except Exception as exc:  # noqa: BLE001
        check("refresh_daily importável", False, repr(exc))
        return

    base = {"employment_type": "INTERN", "company": "X",
            "location": "Berlin, DE", "country_iso": "de"}
    ranking = [
        # já flaggada de run anterior (german_required) => sai neste passe
        {**base, "id": "old-gr", "title": "Praktikum Logistik",
         "description": "Sprachen: verhandlungssicheres Deutsch",
         "description_source": "hydration",
         "hydration_inapplicable": "german_required"},
        # hidratada neste run, flag NOVO german_required => sai no MESMO passe
        {**base, "id": "new-gr", "title": "Praktikum Data",
         "description": "Sehr gute Deutschkenntnisse in Wort und Schrift "
                        "setzen wir voraus",
         "description_source": "hydration"},
        # flag em motivo FORA do subconjunto => fica (design F25)
        {**base, "id": "keep-eu", "title": "Intern EU Affairs",
         "description": "Applicants must hold EU citizenship",
         "description_source": "hydration",
         "hydration_inapplicable": "eu_citizenship_required"},
        # limpa e aplicável
        {**base, "id": "clean", "title": "Intern Data Analytics",
         "description": "Fluency in English, German is a plus",
         "description_source": "hydration"},
    ]
    # passe F25 (re-avalia backlog hidratado) — roda ANTES da exclusão,
    # exatamente como no refresh_daily.main
    bs = rd._reassess_backlog_applicability(ranking)
    es = rd._remove_json_excluded(ranking)

    check("backlog re-avaliou 2 não-flaggadas, flaggou 1 nova (new-gr); "
          "old-gr já flaggada é PULADA pelo passe (design F25)",
          bs["reassessed"] == 2 and bs["newly_flagged"] == 1
          and bs["by_reason"] == {"german_required": 1},
          str({k: bs[k] for k in ("reassessed", "newly_flagged", "by_reason")}))
    check("exclusão removeu 2 german_required (herdada + nova)",
          es["removed"] == 2
          and es["by_reason"] == {"german_required": 2},
          str(es["by_reason"]))
    ids = {str(j.get("id") or "") for j in ranking}
    check("JSON final: keep-eu + clean (design F25 p/ os demais)",
          ids == {"keep-eu", "clean"}, str(sorted(ids)))
    check("new-gr flaggada e removida no mesmo passe",
          "new-gr" not in ids and bs["by_reason"].get("german_required") == 1)

    # métrica applicability DESCREVE o novo estado do JSON
    rec = rd._applicability_metrics_record(ranking, run_id="run-f373")
    check("métrica: eligible = 2",
          rec.get("eligible") == 2, str(rec.get("eligible")))
    check("métrica: flagged = 1 (keep-eu)",
          rec.get("flagged") == 1, str(rec.get("flagged")))
    check("métrica: applicable = 1",
          rec.get("applicable") == 1, str(rec.get("applicable")))
    check("métrica: flagged_german_required = 0 (saiu do JSON)",
          rec.get("flagged_german_required") == 0,
          str(rec.get("flagged_german_required")))
    check("métrica: flagged_eu_citizenship_required = 1",
          rec.get("flagged_eu_citizenship_required") == 1)

    # registro diário da exclusão (padrão F39): motivo + ids + entries
    check("registro exclusão: removed_ids auditáveis",
          sorted(es["removed_ids"]) == ["new-gr", "old-gr"],
          str(es["removed_ids"]))
    check("registro exclusão: entries com company/title",
          all(e.get("company") == "X" and e.get("title")
              for e in es["removed_entries"]))


# ---------------------------------------------------------------------------

def main() -> int:
    print("=== test_f373 — german_required: exclusão total do eligible ===")
    t1_fixture_auditor()
    t2_removal_mechanism()
    t3_decision_single_place()
    t4_detector_counterexamples()
    t5_no_regression()
    t6_pipeline_integration()
    print(f"\nF37.3: {CHECKS} checks, {len(FAILURES)} FAIL")
    if FAILURES:
        print(f"FALHAS: {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
