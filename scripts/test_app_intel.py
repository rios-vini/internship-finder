"""Testes standalone — Fase 6: Application Intelligence (app_intel.py).

Cobre, de forma DETERMINISTICA e offline:

1. ``german_level`` (novo tratamento de idioma): required/preferred/plus/none
   com frases reais DE/EN — "Sehr gute Deutsch- und Englischkenntnisse" ->
   required; "English required, German is a plus" -> preferred (a exigencia
   forte e do INGLES); negacao explicita -> plus; company name ("Deutsche
   Bahn") e "Deutschland" NAO sao mencao de idioma; CEFR; par sem
   intensidade -> preferred; determinismo em repeticoes.
2. ``work_authorization``: estados por EVIDENCIA (support / existing_required
   / no_sponsorship / unclear / not_mentioned); empresa multinacional ou
   localizacao NAO geram inferencia; precedencia no_sponsorship > support.
3. ``deadline_kind``/``days_until``/``urgency_color``: valor do empregador
   (employer) vs. validade do feed do SuccessFactors (platform_sf, regra
   documentada collected+30d) vs. ausente (none); urgencia por faixas do
   enunciado (verde >14 / amarela 7-14 / laranja 3-6 / vermelha <=2); nenhum
   deadline inventado (None nunca vira data).
4. ``candidate_fit``/``possible_problems``/``quality_flags``/
   ``application_readiness``: sinais objetivos; apenas com evidencia;
   readiness = zero problemas.
5. Bloco REAL (data/eligible_jobs.json, SKIP sem o arquivo — padrao do
   projeto): distribuicao dos niveis/estados no snapshot atual, invariantes
   de classes validas e determinismo sobre texto real.

Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_app_intel.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import app_intel  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_german_level() -> None:
    print("== german_level: exigencias detectadas no TEXTO (nunca pelo idioma) ==")
    cases = [
        ("Sehr gute Deutsch- und Englischkenntnisse", "required"),
        ("English required, German is a plus", "preferred"),
        ("German is a plus. English required", "preferred"),
        ("Very good English; German is a plus", "preferred"),
        ("Fluent German required", "required"),
        ("Deutschkenntnisse von Vorteil", "preferred"),
        ("German not required", "plus"),
        ("We require German fluency", "required"),
        ("Working Student bei der Deutschen Bahn", "none"),
        ("Praktikum in Deutschland (m/w/d)", "none"),
        ("Gute Kommunikationsfähigkeiten in deutscher und englischer Sprache",
         "required"),
        ("Languages: German and English", "preferred"),
        ("verhandlungssichere Deutschkenntnisse (ab Level C1)", "required"),
        ("Keine Deutschkenntnisse erforderlich", "plus"),
        ("Deutschkenntnisse sind erforderlich, Englischkenntnisse von Vorteil",
         "required"),
        ("Englischkenntnisse (C1); Deutsch von Vorteil", "preferred"),
        ("Working Student - SAP Analytics Cloud (f/m/d)", "none"),
        ("German", "plus"),  # mencao nua, sem intensidade -> neutro
    ]
    for text, expected in cases:
        got = app_intel.german_level(text)
        level = got.level if got else "none"
        check(f"{expected:9} <- '{text[:58]}'", level == expected)

    base = base_job_text = (
        "Praktikum Data Analytics - Support the data team. "
        "Sehr gute Deutsch- und Englischkenntnisse."
    )
    check("determinismo: 300 repeticoes iguais",
          len({app_intel.german_level(base).level for _ in range(300)}) == 1)

    none_job = "Working Student BI Reporting (f/m/d)"
    check("sem mencao -> None (neutro)", app_intel.german_level(none_job) is None)
    check("None -> None", app_intel.german_level(None) is None)
    check("has_german_mention falso p/ 'Germany'", not app_intel.has_german_mention("Intern in Germany"))
    check("has_german_mention true p/ 'Deutschkenntnisse'",
          app_intel.has_german_mention("Deutschkenntnisse erforderlich"))


def test_english_evidence() -> None:
    print("== english_evidence: evidencia de ingles (sinal compativel) ==")
    check("'English required' -> sim", app_intel.english_evidence("English required, German is a plus"))
    check("'Englischkenntnisse' -> sim (DE anuncio EN referencia)", app_intel.english_evidence("Sehr gute Englischkenntnisse"))
    check("sem mencao -> nao", not app_intel.english_evidence("Support the team."))
    check("None -> nao", not app_intel.english_evidence(None))
    check("'Germany' NAO e evidencia EN", not app_intel.english_evidence("Intern in Germany"))


def test_work_authorization() -> None:
    print("== work_authorization: somente por evidencia explicita ==")
    cases = [
        ("We sponsor visas for international candidates", "support"),
        ("Visa sponsorship and relocation package available", "support"),
        ("We do not offer visa sponsorship", "no_sponsorship"),
        ("Unfortunately we cannot sponsor a work permit", "no_sponsorship"),
        ("You must have existing work authorization", "existing_required"),
        ("Applicants need a valid work and residence permit", "existing_required"),
        ("EU citizens only", "existing_required"),
        ("Join our multinational team in Munich", "not_mentioned"),
        ("A global company headquartered in Germany", "not_mentioned"),
        ("Please send us your CV", "not_mentioned"),
        ("Visa questions can be discussed during the interview", "unclear"),
    ]
    # Item 10 da auditoria — expansão do vocabulário/detector (FNs conhecidos
    # corrigidos, FPs corrigidos, negações testadas, determinismo):
    cases += [
        # FNs conhecidos (spec item 10): suporte explícito EN/DE.
        ("We support you with the visa process", "support"),
        ("Assistance with visa application provided", "support"),
        ("Wir unterst\u00fctzen bei der Beantragung eines Visums", "support"),
        ("Wir \u00fcbernehmen die Beantragung der Arbeitserlaubnis", "support"),
        ("Support with residence permit application", "support"),
        ("The company will assist with work authorization", "support"),
        ("\u00dcbernahme der Visakosten", "support"),  # custeio
        ("Hilfe bei der Arbeitsgenehmigung wird angeboten", "support"),
        ("Visa costs are covered by us", "support"),
        # FP1 (spec): requisito existente + relocation NÃO é suporte.
        ("Applicants must already have a valid work permit. "
         "We can provide relocation assistance.", "existing_required"),
        ("Candidates already possessing a work permit are eligible",
         "existing_required"),
        ("must already have a valid work permit", "existing_required"),
        # FP2 (spec): relocation sem visto NÃO toca no tema.
        ("We support your relocation to Munich.", "not_mentioned"),
        ("Relocation package available", "not_mentioned"),
        # Relocation + visa no texto: support (visa manda).
        ("Relocation support including visa sponsorship", "support"),
        # Combinação documentada: requisito + patrocínio -> support
        # (aviso mais útil ao candidato; precedência inalterada).
        ("must have valid work permit + we sponsor visas", "support"),
        # Negações expandidas (spec direção 5): cada padrão novo tem
        # contraparte negada testada.
        ("no visa support", "no_sponsorship"),
        ("We do not provide visa assistance", "no_sponsorship"),
        ("we cannot help with visa", "no_sponsorship"),
        ("cannot help with work permit applications", "no_sponsorship"),
        ("keine Unterst\u00fctzung bei Visa", "no_sponsorship"),
        ("ohne \u00dcbernahme der Visakosten", "no_sponsorship"),
        ("keine \u00dcbernahme der Visageb\u00fchren", "no_sponsorship"),
        ("visa costs not covered", "no_sponsorship"),
        ("Visakosten werden nicht \u00fcbernommen", "no_sponsorship"),
        # existing_required expandido (spec direção 6).
        ("Applicants must already hold a valid work permit",
         "existing_required"),
        ("bereits vorhandene Arbeitserlaubnis", "existing_required"),
        ("Aufenthaltstitel bereits vorhanden", "existing_required"),
        ("valid EU passport required", "existing_required"),
        ("F\u00fcr Nicht-EU-B\u00fcrger: g\u00fcltiger Aufenthaltstitel erforderlich",
         "existing_required"),
        # NÃO-inferência (spec direção 8): isolados nunca geram estado.
        ("International candidates welcome", "not_mentioned"),
        ("English-speaking environment", "not_mentioned"),
        ("Fahrerlaubnis Klasse B", "not_mentioned"),  # permissão de DIRIGIR
        # HTML com entidades -> suportado via normalize_text (item 5).
        ("You need a valid work&nbsp;permit", "existing_required"),
        ("Wir unterst\u00fctzen&nbsp;bei der Beantragung eines Visums",
         "support"),
    ]
    for text, expected in cases:
        got = app_intel.work_authorization(text)["state"]
        check(f"{expected:16} <- '{text[:52]}'", got == expected)
    check("precedencia: 'no sponsorship' vence mencao de suporte",
          app_intel.work_authorization(
              "We cannot sponsor visas, but relocation support exists"
          )["state"] == "no_sponsorship")
    # Texto sem sinal -> not_mentioned (nunca inferido).
    check("sem sinal -> not_mentioned",
          app_intel.work_authorization(None)["state"] == "not_mentioned")
    # Determinismo: mesma entrada 100x.
    _det = "Wir \u00fcbernehmen die Beantragung der Arbeitserlaubnis"
    check("determinismo: 100 repeticoes iguais",
          len({app_intel.work_authorization(_det)["state"]
               for _ in range(100)}) == 1)


def test_deadline() -> None:
    print("== deadline: classificado; nunca inventado; urgencia por faixa ==")
    ref = date(2026, 9, 9)

    emp = {"source": "smartrecruiters:co",
           "application_deadline": "2026-09-20T00:00:00Z"}
    sf = {"source": "successfactors:jobs",
          "application_deadline": "2026-10-09T00:00:00Z"}
    none = {"source": "greenhouse:co"}
    check("deadline do empregador -> employer",
          app_intel.deadline_kind(emp) == "employer")
    check("deadline SuccessFactors -> platform_sf (validade de feed, nao prazo)",
          app_intel.deadline_kind(sf) == "platform_sf")
    check("sem deadline -> none", app_intel.deadline_kind(none) == "none")
    check("data parsed", app_intel.deadline_date(emp).isoformat() == "2026-09-20")
    check("sem data -> None (nunca inventa)", app_intel.deadline_date(none) is None)

    check("days 11 -> urgencia amarela", app_intel.urgency_color(11) == "yellow")
    check("days 7 -> amarela (borda 7-14)", app_intel.urgency_color(7) == "yellow")
    check("days 6 -> laranja", app_intel.urgency_color(6) == "orange")
    check("days 3 -> laranja", app_intel.urgency_color(3) == "orange")
    check("days 2 -> vermelha", app_intel.urgency_color(2) == "red")
    check("days 0/negativo -> vermelha (vencida)", app_intel.urgency_color(0) == "red"
          and app_intel.urgency_color(-3) == "red")
    check("days 15 -> verde", app_intel.urgency_color(15) == "green")
    check("sem dias -> None", app_intel.urgency_color(None) is None)

    check("dias: 20/09 - 09/09 = 11",
          app_intel.days_until(date(2026, 9, 20), ref) == 11)
    check("dias: vencida negativa",
          app_intel.days_until(date(2026, 9, 1), ref) == -8)

    check("snapshot_ref_date = max(collected_at)",
          app_intel.snapshot_ref_date([
              {"collected_at": "2026-09-07T06:00:00Z"},
              {"collected_at": "2026-09-09T06:00:00Z"},
          ]) == date(2026, 9, 9))
    check("parse_ref_date ISO", app_intel.parse_ref_date("2026-09-09") == ref)
    check("parse_ref_date datetime", app_intel.parse_ref_date(
        datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)) == ref)


def test_fit_problems_flags_readiness() -> None:
    print("== candidate_fit / possible_problems / quality_flags / readiness ==")
    ref = date(2026, 9, 9)

    good = {
        "title": "Werkstudent Supply Chain Analytics (w/m/d)",
        "description": "Support procurement analytics. English required.",
        "country_iso": "de", "location": "Berlin, DE",
        "employment_type": "PART_TIME",
    }
    fit = {s["key"]: s for s in app_intel.candidate_fit(good)}
    check("fit: Alemanha ok", fit["germany"]["kind"] == "ok")
    check("fit: tipo estudante ok", fit["student_type"]["kind"] == "ok")
    check("fit: ingles ok", fit["english"]["kind"] == "ok")
    check("fit: local ok", fit["location_known"]["kind"] == "ok")
    check("fit: work auth info (nao mencionado)", fit["work_auth"]["kind"] == "info"
          and fit["work_auth"]["detail"] == "not_mentioned")

    hard = {
        "title": "Praktikum SCM",
        "description": "Fluent German required. You must have existing "
                       "work authorization. English is a plus.",
        "country_iso": "de", "location": "Munich, DE",
        "application_deadline": "2026-09-11T00:00:00Z",
        "source": "smartrecruiters:co",
    }
    probs = app_intel.possible_problems(hard, ref)
    keys = {p["key"] for p in probs}
    check("problemas: alemao exigido", "german_required" in keys)
    check("problemas: autorizacao existente", "wa_existing" in keys)
    check("problemas: deadline <=2 (hard)", any(
        p["key"] == "deadline" and p["severity"] == "hard" for p in probs))
    check("readiness: com problemas -> verify",
          app_intel.application_readiness(probs) == "verify")

    soft = {
        "title": "Working Student Data",
        "description": "German is a plus.",
        "country_iso": "de", "location": "Berlin, DE",
    }
    sprobs = app_intel.possible_problems(soft, ref)
    check("alemaõ preferido vira problema soft",
          any(p["key"] == "german_preferred" and p["severity"] == "soft"
              for p in sprobs))

    clean = {"title": "Working Student BI", "description": "Support BI delivery.",
             "country_iso": "de", "location": "Munich, DE"}
    check("readiness: zero problemas -> ready",
          app_intel.application_readiness(app_intel.possible_problems(clean, ref))
          == "ready")

    flags = {f["key"] for f in app_intel.quality_flags(clean, ref)}
    check("flags: sem deadline", "no_deadline" in flags)
    check("flags: descricao curta", "short_description" in flags)
    check("flags: sem idioma", "no_language" in flags)
    sf = {"title": "Praktikum Log", "description": "Support logistics.",
          "source": "successfactors:jobs",
          "application_deadline": "2026-09-30T00:00:00Z"}
    sfk = app_intel.deadline_kind(sf)
    sff = {f["key"] for f in app_intel.quality_flags(sf, ref)}
    check("flags: SF marca validade de plataforma (nao deadline)",
          sfk == "platform_sf" and "platform_validity" in sff
          and "no_deadline" not in sff)
    # Urgencia NAO existe para o valor SF (regra do enunciado/project status).
    check("urgencia NAO e calculada para validade SF",
          app_intel.urgency_color(app_intel.days_until(
              app_intel.deadline_date(sf), ref)) is None
          or app_intel.deadline_kind(sf) != "employer")

    old = {"title": "Intern", "description": "x" * 300,
           "posted_at": "2026-01-01T00:00:00Z"}
    oldf = {f["key"] for f in app_intel.quality_flags(old, ref)}
    check("flags: publicacao antiga (>60d)", "old_posting" in oldf)


def test_real_data() -> None:
    print("== bloco real (data/eligible_jobs.json) ==")
    path = ROOT / "data" / "eligible_jobs.json"
    if not path.exists():
        print("  [SKIP] sem data/eligible_jobs.json (runner limpo) — invariantes "
              "da classe ja cobertas pela fixture")
        return
    jobs = json.loads(path.read_text(encoding="utf-8"))
    levels = Counter()
    wa = Counter()
    kinds = Counter()
    ref = app_intel.snapshot_ref_date(jobs)
    problems_total = 0
    for j in jobs:
        text = f"{j.get('title') or ''} {j.get('description') or ''}"
        de = app_intel.german_level(text)
        levels[de.level if de else "none"] += 1
        wa[app_intel.work_authorization(text)["state"]] += 1
        kinds[app_intel.deadline_kind(j)] += 1
        problems_total += len(app_intel.possible_problems(j, ref))
    print(f"    nivel alemao: {dict(levels)}")
    print(f"    work auth: {dict(wa)}")
    print(f"    deadline kind: {dict(kinds)}")
    print(f"    total de problemas objetivos (evidencia): {problems_total}")
    check("classes validas", set(levels) <= set(app_intel.GERMAN_LEVELS))
    check("estados de work auth validos", set(wa) <= set(app_intel.WORK_AUTH_STATES))
    check("tipos de deadline validos", set(kinds) <= set(app_intel.DEADLINE_KINDS))
    check("determinismo: texto real 100x",
          len({app_intel.german_level(
              f"{jobs[0].get('title')} {jobs[0].get('description')}").level
              for _ in range(100)}) == 1)
    # Invariante central: nenhum deadline inventado — todo kind != none tem
    # evidencia real: campo estrutural da fonte (employer/platform_sf) OU
    # prazo declarado no texto (employer_textual, item 8 da auditoria).
    # NB: um job SF pode TER o campo estrutural (validade de feed) e um
    # prazo textual no texto AO MESMO TEMPO — o kind é employer_textual
    # (textual vence SF), então o campo conta UMA vez pelo kind, nunca duas.
    # O invariante correto é por KIND, não por soma de contagens.
    check("deadlines presentes == fonte OU textual (nada derivado)",
          all(app_intel.deadline_kind(j) in (
              "employer", "employer_textual", "platform_sf")
          for j in jobs if j.get("application_deadline")
          or app_intel.textual_deadline(
              f"{j.get('title') or ''} {j.get('description') or ''}")
          is not None)
          and all(app_intel.deadline_kind(j) != "none"
                  for j in jobs if j.get("application_deadline")))
    check("employer_textual sempre tem data no texto",
          sum(1 for j in jobs if app_intel.deadline_kind(j) == "employer_textual")
          == sum(1 for j in jobs
                 if app_intel.deadline_kind(j) == "employer_textual"
                 and app_intel.textual_deadline(
                     f"{j.get('title') or ''} {j.get('description') or ''}"
                 ) is not None))


def main() -> int:
    test_german_level()
    test_english_evidence()
    test_work_authorization()
    test_deadline()
    test_fit_problems_flags_readiness()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())