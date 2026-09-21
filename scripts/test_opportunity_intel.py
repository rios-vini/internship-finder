"""Testes standalone — Fase 7: Opportunity Intelligence (opportunity_intel.py
+ integracao com a interface).

Cobre, de forma DETERMINISTICA e offline (sem rede):

1. ``job_salary``: salario citado NO anuncio (Gehalt/Vergütung/Salary +
   valor/faixa); ausencia nunca vira valor; frase sem numero nao casa.
2. ``work_mode``: remote/hybrid/on_site por evidencia no texto; raw.is_remote
   decide remote; sem evidencia -> not_mentioned (nunca inferido).
3. ``city_and_region``: cidade/regiao da string real; rua+CEP captura a
   cidade; "Germany"/"Deutschland" nao viram cidade; vazio -> None.
4. ``load_company_intel``/``company_intel_for``: ausente/malformado -> {};
   alias; reuso da MESMA entrada para varias vagas da mesma empresa.
5. ``cost_of_living``: cidade conhecida -> dado com fonte/checked; desconhecida
   -> None.
6. ``pathway_state``/``pathway_percentage``/``turnover_summary``: estados
   validos; invalido -> unknown; percentual so como dado factual; turnover
   somente com fonte.
7. ``job_duration``: valor unico/faixa; ausencia -> None.
8. Integracao com a interface (render_html): secoes Company/Benefits/Career/
   Pathway/Location/Salary/Sources presentes; dados de comparacao nos
   data-attributes; score das vagas NAO alterado (ranking intocado);
   arquivos ausentes nao quebram a pagina.
9. Bloco REAL (data/eligible_jobs.json, SKIP sem o arquivo — padrao do
   projeto): distribuicao de salario citado/modalidade/cidades.

Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_opportunity_intel.py
"""

from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import interface  # noqa: E402  (mesmo script de renderizacao da pagina)
from internship_finder import opportunity_intel as oi  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _job(**overrides) -> dict:
    base = {
        "id": "t:1", "source": "test:source", "title": "Vaga", "company": "TestCo",
        "location": "Berlin, DE", "country_iso": "de", "url": "https://example.org/j",
        "description": "", "collected_at": "2026-09-20T06:00:00Z",
    }
    base.update(overrides)
    return base


def test_salary() -> None:
    print("== job_salary: evidencia no anuncio (nunca inventa) ==")
    cases = [
        (_job(description="Gehalt: 2.117 €/Monat"), (2117.0, 2117.0, "month")),
        (_job(description="Vergütung: 1.500 € - 1.800 € im Monat"), (1500.0, 1800.0, "month")),
        (_job(description="Salary: EUR 2,000 per month"), (2000.0, 2000.0, "month")),
        (_job(description="compensation: €3,000 – €3,500 / month"), (3000.0, 3500.0, "month")),
        (_job(description="Gehalt ca. 2.100 €/Monat"), (2100.0, 2100.0, "month")),
        (_job(description="6 Monate Dauer; keine Angaben"), None),  # sem valor
        (_job(description=""), None),
        (_job(description="wir bieten keine Vergütung"), None),  # palavra sem numero
        (_job(description="Salary: not disclosed"), None),
    ]
    for job, expected in cases:
        got = oi.job_salary(job)
        if expected is None:
            check(f"sem salario -> None ({job['description'][:40]!r})", got is None)
        else:
            ok = got is not None and (got["min"], got["max"], got["period"]) == expected
            check(f"salario {expected[0]}..{expected[1]} ({job['description'][:40]!r})", ok)
    # determinismo
    j = _job(description="Gehalt: 1.900 €/Monat")
    check("determinismo", oi.job_salary(j) == oi.job_salary(j))


def test_work_mode() -> None:
    print("== work_mode: evidencia no texto / raw.is_remote ==")
    checks = [
        (_job(description="Hybrid work model"), "hybrid"),
        (_job(description="fully remote position"), "remote"),
        (_job(description="Arbeit vor Ort in unserem Büro"), "on_site"),
        (_job(description="work from anywhere"), "remote"),
        (_job(description="Join our team."), "not_mentioned"),
        (_job(description="", raw={"is_remote": True}), "remote"),
    ]
    for job, expected in checks:
        check(f"work_mode -> {expected}", oi.work_mode(job) == expected)


def test_city_region() -> None:
    print("== city_and_region: string real, sem inferencia ==")
    checks = [
        (_job(location="Fellbach, BW, DE, 70736"), ("Fellbach", "BW")),
        (_job(location="München, BY, DE, 80809"), ("München", "BY")),
        (_job(location="Dornkaulstraße 2, 52134 Herzogenrath, Nordrhein-Westfalen, Deutschland"),
         ("Herzogenrath", "Nordrhein-Westfalen")),
        (_job(location="Germany"), (None, None)),
        (_job(location="", country_iso="de"), (None, None)),
    ]
    for job, expected in checks:
        got = oi.city_and_region(job)
        check(f"city/region {expected} (loc={job.get('location')!r})",
              (got["city"], got["region"]) == expected)
    got = oi.city_and_region(_job(location="Bonn, DE"))
    check("pais preservado de country_iso", got["country"] == "de")


def test_loaders() -> None:
    print("== load_company_intel / company_intel_for: tolerante e reutilizavel ==")
    check("arquivo ausente -> {}", oi.load_company_intel(Path("/nonexistent/x.json")) == {})
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{quebrado")
        check("arquivo malformado -> {}", oi.load_company_intel(bad) == {})
        p = Path(td) / "ci.json"
        p.write_text(json.dumps({"companies": [
            {"company": "SAP SE", "aliases": ["SAP"], "industry": "Software", "benefits": ["x"],
             "internship_pathway": "evidence_available", "checked": "2026-09-20"},
            {"company": "Bosch", "internship_pathway": "explicitly_supported"},
        ]}), encoding="utf-8")
        m = oi.load_company_intel(p)
        check("2 empresas carregadas", len(m) >= 2)
        check("canonico via nome exato", oi.company_intel_for(_job(company="SAP SE"), m) is not None)
        check("canonico via alias", oi.company_intel_for(_job(company="SAP"), m) is not None)
        check("empresa sem entrada -> None",
              oi.company_intel_for(_job(company="Nope GmbH"), m) is None)
        a = oi.company_intel_for(_job(company="SAP"), m)
        b = oi.company_intel_for(_job(company="SAP SE"), m)
        check("MESMA entrada reutilizada (mesma empresa, 2 vagas)", a is b)


def test_cost_of_living() -> None:
    print("== cost_of_living: so cidade conhecida, com fonte ==")
    loc = {"munchen": {"estimate_monthly": "€1,400", "source": {"name": "Numbeo"},
                       "checked": "2026-09-20", "period": "2026"}}
    check("cidade conhecida (normalizada)", oi.cost_of_living("München", loc) is not None)
    check("cidade desconhecida -> None", oi.cost_of_living("Fellbach", loc) is None)
    check("sem cidade -> None", oi.cost_of_living(None, loc) is None)
    check("mapa vazio", oi.cost_of_living("Berlin", {}) is None)


def test_pathway() -> None:
    print("== pathway_state / percentage / turnover: dados, nunca opiniao ==")
    entry = {"internship_pathway": "explicitly_supported",
             "pathway_percentage": {"value": "40%", "text": "interns receive offers"},
             "turnover": {"kind": "workforce", "detail": "-10k headcount",
                          "source": "Press release", "period": "2024"}}
    check("explicitly_supported", oi.pathway_state(entry) == "explicitly_supported")
    check("unknown sem entrada", oi.pathway_state(None) == "unknown")
    check("invalido -> unknown", oi.pathway_state({"internship_pathway": "80%"}) == "unknown")
    pct = oi.pathway_percentage(entry)
    check("percentual oficial como dado", pct is not None and pct["value"] == "40%")
    check("sem percentual -> None", oi.pathway_percentage({"internship_pathway": "x"}) is None)
    t = oi.turnover_summary(entry)
    check("turnover com fonte", t is not None and t["period"] == "2024")
    check("turnover sem fonte -> None",
          oi.turnover_summary({"turnover": {"detail": "x"}}) is None)


def test_duration() -> None:
    print("== job_duration: evidencia explicita ==")
    check("unico", oi.job_duration(_job(description="6 Monate")) == {"min": 6, "max": 6})
    check("faixa", oi.job_duration(_job(description="6–12 months")) == {"min": 6, "max": 12})
    check("sem duracao", oi.job_duration(_job(description="go go")) is None)


FIXTURE = [
    {"id": "sap:1", "title": "Working Student Supply Chain Analytics (f/m/d)",
     "company": "SAP", "location": "Walldorf, DE, 69190", "country_iso": "de",
     "url": "https://example.org/sap-1", "score": 9.5,
     "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "description": "Hybrid working. Salary: EUR 1,900 per month. Duration 6 months.",
     "collected_at": "2026-09-20T06:00:02Z", "internship": True},
    {"id": "sap:2", "title": "Praktikum BI & Analytics (f/m/d)", "company": "SAP",
     "location": "Berlin, DE", "country_iso": "de",
     "url": "https://example.org/sap-2", "score": 9.0,
     "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "description": "Dashboards and data pipelines.",
     "collected_at": "2026-09-20T06:00:02Z", "internship": True},
    {"id": "bosch:1", "title": "Werkstudent Logistik (m/w/d)", "company": "Bosch",
     "location": "Stuttgart, DE", "country_iso": "de",
     "url": "https://example.org/bosch-1", "score": 7.2,
     "score_breakdown": {"area": 4.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 1.0, "penalties": -0.3},
     "description": "Support the logistics team. Vor Ort.",
     "collected_at": "2026-09-20T06:00:02Z", "internship": True},
    {"id": "zf:1", "title": "Working Student Automation", "company": "ZF",
     "location": "Germany", "country_iso": "de", "remote": True,
     "url": "https://example.org/zf-1", "score": 5.4,
     "score_breakdown": {"area": 2.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 0.0, "penalties": 0.0},
     "description": "RPA bots.",
     "collected_at": "2026-09-20T06:00:02Z", "internship": True},
]

COMPANY_INTEL_FIXTURE = {
    "companies": [
        {"company": "SAP", "industry": "Software empresarial", "size": "~108.000 (global)",
         "hq": "Walldorf, Alemanha", "website": "https://example.org/sap-site",
         "careers_url": "https://example.org/sap-careers",
         "benefits": ["Assistência médica", "Working Student benefits"],
         "career_development": [{"text": "Programa de Working Student com mentoria"}],
         "internship_pathway": "evidence_available",
         "checked": "2026-09-20",
         "sources": [{"text": "SAP Careers — Benefits", "url": "https://example.org/sap-careers",
                      "quality": "primary", "checked": "2026-09-20"}]},
        {"company": "Bosch", "industry": "Tecnologia e engenharia",
         "internship_pathway": "explicitly_supported",
         "checked": "2026-09-20",
         "sources": [{"text": "Bosch Careers", "url": "https://example.org/bosch-careers",
                      "quality": "primary", "checked": "2026-09-20"}]},
    ]
}
LOCATION_INTEL_FIXTURE = {
    "cities": {"walldorf": {"estimate_monthly": "€1.150", "rent_1br_center": "€1.050",
                            "transport_monthly": "€49",
                            "source": {"name": "Fonte de teste", "url": "https://example.org/col"},
                            "checked": "2026-09-20", "period": "2026"}}
}


def test_interface_integration() -> None:
    print("== integracao: render_html com Company/Location Intelligence ==")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ci_path = Path(td) / "ci.json"
        loc_path = Path(td) / "loc.json"
        ci_path.write_text(json.dumps(COMPANY_INTEL_FIXTURE), encoding="utf-8")
        loc_path.write_text(json.dumps(LOCATION_INTEL_FIXTURE), encoding="utf-8")
        ci = oi.load_company_intel(ci_path)
        loc = oi.load_location_intel(loc_path)
        before = copy.deepcopy(FIXTURE)
        page = interface.render_html(
            FIXTURE, total=4, source_label="fixture", filters_desc=[],
            generated_at="2026-09-20T06:00:00Z", stats=None, top_n=30,
            company_intel_map=ci, loc_map=loc,
        )
        check("secao Oportunidade por vaga", page.count("Oportunidade — empresa, localização") == 4)
        check("secao Empresa (industry)", "Software empresarial" in page)
        check("secao Beneficios", "Assistência médica" in page)
        check("secao Carreira", "Programa de Working Student" in page)
        check("pathway evidence_available", "Evidence available" in page)
        check("secao Localização (Walldorf)", "Walldorf" in page and "Híbrido" in page)
        check("custo de vida context (fonte)", "€1.150" in page)
        check("salario citado no anuncio", "€1.900 / mês" in page)
        check("salary source = job posting", "Source: job posting" in page)
        check("beneficios ausentes -> Not mentioned", "Not mentioned" in page)
        check("data attrs de comparacao", 'data-salary="1900"' in page and 'data-mode="hybrid"' in page)
        check("Compare opportunities presente", "Compare opportunities" in page)
        check("JS de comparacao (fatores)", "Internship → Full-time" in page)
        # Ranking NAO alterado: os data-score coincidem com o fixture de origem.
        scores = re.findall(r'data-score="([0-9.]+)"', page)
        check("score intocado no HTML", sorted(float(s) for s in scores) ==
              sorted(float(j["score"]) for j in FIXTURE))
        check("dados de origem nao mutados", before == FIXTURE)
    # Pagina sem arquivos curados: arquivos ausentes nao quebram nada.
    page2 = interface.render_html(
        FIXTURE, total=4, source_label="fixture", filters_desc=[],
        generated_at="2026-09-20T06:00:00Z", stats=None, top_n=30,
        company_intel_map={}, loc_map={},
    )
    check("sem dados curados -> pagina continua (4 vagas)",
          page2.count("Oportunidade — empresa, localização") == 4
          and "Not disclosed" in page2)


def test_curated_files() -> None:
    print("== arquivos curados do repo (company_intel/*.json) ==")
    ci = ROOT / "company_intel" / "company_intelligence.json"
    loc = ROOT / "company_intel" / "location_intel.json"
    if not ci.exists() or not loc.exists():
        check("arquivos curados presentes no repo", ci.exists() and loc.exists())
        return
    m = oi.load_company_intel(ci)
    check(">= 10 empresas curadas", len(m) >= 10)
    entries = [v for v in m.values() if isinstance(v, dict)]
    check("empresas com checked + fontes",
          all("checked" in e and isinstance(e.get("sources"), list) and e["sources"]
              for e in entries))
    for key, entry in list(m.items())[:200]:
        for s in entry.get("sources") or []:
            check(f"fonte {key} tem url+qualidade", bool(s.get("url")) and s.get("quality") in oi.SOURCE_QUALITIES)
    lm = oi.load_location_intel(loc)
    check(">= 8 cidades com custo de vida", len(lm) >= 8)
    for city, data in lm.items():
        check(f"cidade {city} com fonte/checked/periodo",
              data.get("estimate_monthly") and data.get("rent_1br_center")
              and data.get("checked") and data.get("period") and data.get("source", {}).get("url"))
    # Empresas do topo do ranking real cobertas (aliases casam com display names).
    import json as _json
    rp = ROOT / "data" / "eligible_jobs.json"
    if rp.exists():
        jobs = _json.loads(rp.read_text(encoding="utf-8"))
        from collections import Counter
        top = [c for c, _ in Counter(str(j.get("company") or "") for j in jobs).most_common(10)]
        covered = sum(1 for c in top if m.get(oi._norm(c)))
        check(f"{covered}/10 maiores empresas com Company Intelligence", covered >= 5)
        print(f"  top real: {top}")


def test_real_snapshot() -> None:
    print("== bloco real (data/eligible_jobs.json; SKIP sem o arquivo) ==")
    path = ROOT / "data" / "eligible_jobs.json"
    if not path.exists():
        print("  [SKIP] sem data/eligible_jobs.json (CI limpo)")
        return
    jobs = json.loads(path.read_text(encoding="utf-8"))
    sal = sum(1 for j in jobs if oi.job_salary(j))
    modes = Counter(oi.work_mode(j) for j in jobs)
    cities = {c for j in jobs for c in [oi.city_and_region(j)["city"]] if c}
    check("salario citado em >= 1 vaga real", sal >= 1)
    check("modalidades dentro das classes validas", set(modes) <= set(oi.WORK_MODES))
    check("cidades reais extraidas", len(cities) >= 10)
    print(f"  real: salario citado {sal} · modalidades {dict(modes)} · cidades {len(cities)}")


def main() -> None:
    test_salary()
    test_work_mode()
    test_city_region()
    test_loaders()
    test_cost_of_living()
    test_pathway()
    test_duration()
    test_interface_integration()
    test_curated_files()
    test_real_snapshot()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        raise SystemExit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()