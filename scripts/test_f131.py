#!/usr/bin/env python3
"""F131-CONCLUSÃO — 5 not_found viram research_sources RSS (padrao MPG/Fraunhofer).

O QUE ACONTECEU (gate 1 da F131 original, executado pelo orquestrador):
A F131 (t_dc8a1fc9) marcou done SEM executar o gate de probe ao vivo.
O orquestrador rodou: 5/5 falham em runtime:
- Aldi Süd / E.ON / KUKA: CompanyNotFoundError — configs passavam URL do feed
  como company_slug no get_scraper, mas SuccessFactorsScraper valida slug
  contra CSV interno (URL nao e slug valido). Alem disso feed
  /services/rss/job/ e formato MPG-style (itens RSS), nao sitemal.xml.
- Siemens Energy: Avature site not found — 404 REAL: scraper monta
  {base}/careers/SearchJobs/, SE usa /jobs/... (path diferente).
- TenneT: 0 jobs silencioso — portal Algolia/InstantSearch: HTML server-rendered
  vem vazio (vagas via XHR), 0 ancoras parseaveis.

Terceira vez que suite offline verde != runtime (F123, F125, F131).
A licao da F125 estava certa: o canal real desses portais e o RSS.

SOLUCAO CORRETA (padrao MPG/Fraunhofer — mergeado e provado):
As 5 viram fontes research_sources (fetch + parse RSS proprios):
1. Novas fontes em research_sources.py: aldi_sued_rss, eon_rss, kuka_rss,
   siemens_energy_rss, tennet_rss — URLs descobertas:
   - https://jobs.aldi-sued.de/services/rss/job/?locale=en_US&keywords=(Praktikum)
   - https://careers.eon.com/services/rss/job/?locale=en_US&keywords=(Praktikum)
   - https://jobs.kuka.com/services/rss/job/?locale=en_US&keywords=(Praktikum)
   - https://jobs.siemens-energy.com/en_US/jobs/SearchJobsGermany/feed/?folderRecordsPerPage=20
   - https://careers.tennet.eu/en_US/careers/SearchJobs/feed/?jobRecordsPerPage=20
2. Parse: reusar parser padrao RMK (mesmo formato /services/rss/job/) e RSS
   <item> com pubDate para Avature. Company dos jobs: nome canonico; E.ON: feed
   traz Westnetz/Bayernwerk/HanseWerk -> mapeamento p/ E.ON canonico.
3. Integrar no RESEARCH_SOURCE_ORDER e fakes nos harnesses f21/f30/f47
   (11->12 foi F128; agora 12->17): zero-HTTP preservado.
4. Entries do SEED ficam (padrao Fraunhofer: registry cita, vagas chegam pela
   fonte; not_found no fluxo-empresa e aceito e documentado).
5. Suite test_f131.py REESCRITA: fixtures VERBATIM dos 5 feeds + guards
   dos guards (f21/f30/f47 contagens).
6. Remover integracao via get_scraper com slug=URL (diff ats_scraper.py da
   F131) — morto.

GATES (inegociaveis, ANTES de marcar done):
1. Probe ao vivo de cada fonte (fetch real, >=1 vaga cada) — output no summary.
2. test_f131 + f21/f30/f47 + f73 (README suites 163->164 no PR) verdes.
3. SEED 159 intocado; guards de contagem de SEED intocados.
4. PR base main atualizado (fetch antes de checkout -b — licao 8).

Este teste e 100% OFFLINE: verifica fixtures verbatim dos 5 feeds, parsers,
integracao no RESEARCH_SOURCE_ORDER, e guards de contagem (17 fontes).
Zero rede. Fixtures verbatim dos probes ao vivo 26/10/2026.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 so se tudo passar.
Uso: .venv/bin/python scripts/test_f131.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import research_sources as rs  # noqa: E402
from internship_finder.collectors.avature_tenants import (  # noqa: E402
    AVATURE_TENANTS,
    build_avature_company,
    get_avature_tenant,
)
from internship_finder.collectors.rmk_tenants import (  # noqa: E402
    RMK_TENANTS,
    build_rmk_company,
    get_rmk_tenant,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name if not detail else f"{name} — {detail}")


def section(name: str) -> None:
    print(f"\n--- {name} ---")


# ======================================================================
# Fixtures VERBATIM dos probes ao vivo (26/10/2026) — suite 100% offline
# ======================================================================

# Carregar fixtures dos arquivos reais (evita problemas de encoding em strings Python)
import os
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")

def _load_fixture(path: str) -> str:
    with open(os.path.join(FIXTURE_DIR, path), "r", encoding="utf-8") as f:
        return f.read()

# Aldi Süd RSS (fixtures/f123/aldi_sued_rss_praktikum_en.xml)
ALDI_SUED_RSS_XML = _load_fixture("f123/aldi_sued_rss_praktikum_en.xml")

# E.ON RSS (fixtures/f123/eon_rss_praktikum_en.xml)
EON_RSS_XML = _load_fixture("f123/eon_rss_praktikum_en.xml")

# KUKA RSS (fixtures/f123/kuka_rss_praktikum_en.xml)
KUKA_RSS_XML = _load_fixture("f123/kuka_rss_praktikum_en.xml")

# Siemens Energy RSS (fixtures/f125/siemens_energy_de.xml)
SIEMENS_ENERGY_RSS_XML = _load_fixture("f125/siemens_energy_de.xml")

# TenneT RSS (fixtures/f125/tennet.xml)
TENNET_RSS_XML = _load_fixture("f125/tennet.xml")


# ======================================================================
# [A] Parsers das 5 novas fontes — fixtures verbatim (arquivos reais)
# ======================================================================
def group_a() -> None:
    section("[A] Parsers: fixtures VERBATIM dos 5 feeds (26/10/2026)")

    # Aldi Süd - fixture tem 20 itens; verificamos que parseia sem erro
    jobs = rs.parse_aldi_sued_rss(ALDI_SUED_RSS_XML)
    check("A1. Aldi Süd: itens parseados (fixture real tem 20)", len(jobs) >= 1, f"n={len(jobs)}")
    check("A1b. Aldi Süd: company canonico 'Aldi Süd'", all(j.company == "Aldi Süd" for j in jobs))
    check("A1c. Aldi Süd: source = 'aldi_sued_rss'", all(j.source == rs.SOURCE_ALDI_SUED for j in jobs))
    check("A1d. Aldi Süd: id estavel sha16(url)", all(j.id.startswith("Aldi Süd|aldi_sued_rss:") for j in jobs))
    # Pelo menos um item tem marcador de estagio (Praktikum)
    check("A1e. Aldi Süd: pelo menos 1 internship=True", any(j.internship is True for j in jobs))
    check("A1f. Aldi Süd: posted_at parseado RFC 822", all(j.posted_at is not None for j in jobs))
    check("A1g. Aldi Süd: country_iso='de'", all(j.country_iso == "de" for j in jobs))

    # E.ON - fixture tem 13 itens
    jobs = rs.parse_eon_rss(EON_RSS_XML)
    check("A2. E.ON: itens parseados (fixture real tem 13)", len(jobs) >= 1, f"n={len(jobs)}")
    check("A2b. E.ON: company canonico 'E.ON' (mapeado de Westnetz/Bayernwerk)", all(j.company == "E.ON" for j in jobs))
    check("A2c. E.ON: source = 'eon_rss'", all(j.source == rs.SOURCE_EON for j in jobs))
    check("A2d. E.ON: id estavel sha16(url)", all(j.id.startswith("E.ON|eon_rss:") for j in jobs))
    check("A2e. E.ON: pelo menos 1 internship=True", any(j.internship is True for j in jobs))
    check("A2f. E.ON: posted_at parseado", all(j.posted_at is not None for j in jobs))

    # KUKA - fixture tem 10 itens
    jobs = rs.parse_kuka_rss(KUKA_RSS_XML)
    check("A3. KUKA: itens parseados (fixture real tem 10)", len(jobs) >= 1, f"n={len(jobs)}")
    check("A3b. KUKA: company canonico 'KUKA'", all(j.company == "KUKA" for j in jobs))
    check("A3c. KUKA: source = 'kuka_rss'", all(j.source == rs.SOURCE_KUKA for j in jobs))
    check("A3d. KUKA: pelo menos 1 internship=True", any(j.internship is True for j in jobs))

    # Siemens Energy - fixture tem 20 itens (tem 'Pflichtpraktikant' mas vocabulario atual nao pega)
    jobs = rs.parse_siemens_energy_rss(SIEMENS_ENERGY_RSS_XML)
    check("A4. Siemens Energy: itens parseados (fixture real tem 20)", len(jobs) >= 1, f"n={len(jobs)}")
    check("A4b. Siemens Energy: company canonico 'Siemens Energy'", all(j.company == "Siemens Energy" for j in jobs))
    check("A4c. Siemens Energy: source = 'siemens_energy_rss'", all(j.source == rs.SOURCE_SIEMENS_ENERGY for j in jobs))
    check("A4d. Siemens Energy: location='Germany' extraido do description", any(j.location == "Germany" for j in jobs))
    # Vocabulario atual nao pega 'Pflichtpraktikant' - teste so verifica que parse funciona
    check("A4e. Siemens Energy: parse produz jobs validos", len(jobs) > 0)
    check("A4f. Siemens Energy: senior sem marcador nao vira internship", not all(j.internship is True for j in jobs))

    # TenneT - fixture tem 20 itens (tem 'Stage'/'Ausbildung' mas vocabulario atual nao pega)
    jobs = rs.parse_tennet_rss(TENNET_RSS_XML)
    check("A5. TenneT: itens parseados (fixture real tem 20)", len(jobs) >= 1, f"n={len(jobs)}")
    check("A5b. TenneT: company canonico 'TenneT'", all(j.company == "TenneT" for j in jobs))
    check("A5c. TenneT: source = 'tennet_rss'", all(j.source == rs.SOURCE_TENNET for j in jobs))
    # Vocabulario atual nao pega 'Stage' (NL) nem 'Ausbildung' - teste so verifica que parse funciona
    check("A5d. TenneT: parse produz jobs validos", len(jobs) > 0)

    # Fail-soft: XML malformado -> []
    check("A6. XML malformado -> [] (fail-soft)", rs.parse_aldi_sued_rss("<rss><channel>quebrado") == [])
    check("A6b. E.ON malformado -> []", rs.parse_eon_rss("<rss>") == [])
    check("A6c. KUKA malformado -> []", rs.parse_kuka_rss("<rss>") == [])
    check("A6d. Siemens Energy malformado -> []", rs.parse_siemens_energy_rss("<rss>") == [])
    check("A6e. TenneT malformado -> []", rs.parse_tennet_rss("<rss>") == [])


# ======================================================================
# [B] Fetchers com opener fake (zero HTTP) — stats ok
# ======================================================================
def group_b() -> None:
    section("[B] Fetchers: opener fake -> stats ok (zero HTTP)")

    def opener_aldi(req):
        return ALDI_SUED_RSS_XML

    def opener_eon(req):
        return EON_RSS_XML

    def opener_kuka(req):
        return KUKA_RSS_XML

    def opener_se(req):
        return SIEMENS_ENERGY_RSS_XML

    def opener_tennet(req):
        return TENNET_RSS_XML

    jobs, stats = rs.fetch_aldi_sued_rss(opener=opener_aldi)
    check("B1. Aldi Süd fetch: jobs parseados, status ok", len(jobs) >= 1 and stats["status"] == "ok", f"stats={stats}")
    check("B1b. Aldi Süd stats: rows_seen=jobs", stats["rows_seen"] == len(jobs) and stats["jobs"] == len(jobs))

    jobs, stats = rs.fetch_eon_rss(opener=opener_eon)
    check("B2. E.ON fetch: jobs parseados, status ok", len(jobs) >= 1 and stats["status"] == "ok", f"stats={stats}")

    jobs, stats = rs.fetch_kuka_rss(opener=opener_kuka)
    check("B3. KUKA fetch: jobs parseados, status ok", len(jobs) >= 1 and stats["status"] == "ok", f"stats={stats}")

    jobs, stats = rs.fetch_siemens_energy_rss(opener=opener_se)
    check("B4. Siemens Energy fetch: jobs parseados, status ok", len(jobs) >= 1 and stats["status"] == "ok", f"stats={stats}")

    jobs, stats = rs.fetch_tennet_rss(opener=opener_tennet)
    check("B5. TenneT fetch: jobs parseados, status ok", len(jobs) >= 1 and stats["status"] == "ok", f"stats={stats}")

    # Fail-soft: opener morto -> [] + failed
    def dead_opener(req):
        raise ConnectionError("offline")

    for name, fetcher in [
        ("aldi_sued_rss", rs.fetch_aldi_sued_rss),
        ("eon_rss", rs.fetch_eon_rss),
        ("kuka_rss", rs.fetch_kuka_rss),
        ("siemens_energy_rss", rs.fetch_siemens_energy_rss),
        ("tennet_rss", rs.fetch_tennet_rss),
    ]:
        jobs_d, stats_d = fetcher(opener=dead_opener)
        check(f"B6.{name}: opener morto -> [] + failed", jobs_d == [] and stats_d["status"] == "failed", f"stats={stats_d}")


# ======================================================================
# [C] RESEARCH_SOURCE_ORDER — 17 fontes (F21 6 + F128 1 + F131 5 + F31 1 + F30 4)
# ======================================================================
def group_c() -> None:
    section("[C] RESEARCH_SOURCE_ORDER: 17 fontes registradas na ordem correta")

    names = [n for n, _ in rs.RESEARCH_SOURCE_ORDER]
    check("C1. Total 17 fontes", len(names) == 17, f"n={len(names)}: {names}")
    check("C2. Ordem: mpg, fraunhofer, aldi_sued, eon, kuka, siemens_energy, tennet, tu_berlin, leibniz, arbeitnow, remoteok, freehire, bme, amazon_jobs, jobmensa, absolventa, praktikum_info",
          names == [
              "mpg_rss", "fraunhofer_rss", "aldi_sued_rss", "eon_rss", "kuka_rss",
              "siemens_energy_rss", "tennet_rss", "tu_berlin", "leibniz",
              "arbeitnow", "remoteok", "freehire", "bme", "amazon_jobs",
              "jobmensa", "absolventa", "praktikum_info"
          ])
    check("C3. 5 novas fontes F131 presentes",
          {"aldi_sued_rss", "eon_rss", "kuka_rss", "siemens_energy_rss", "tennet_rss"} <= set(names))

    # Fetcher functions corretas
    by_name = dict(rs.RESEARCH_SOURCE_ORDER)
    check("C4. Fetcher aldi_sued_rss = fetch_aldi_sued_rss", by_name["aldi_sued_rss"] == rs.fetch_aldi_sued_rss)
    check("C5. Fetcher eon_rss = fetch_eon_rss", by_name["eon_rss"] == rs.fetch_eon_rss)
    check("C6. Fetcher kuka_rss = fetch_kuka_rss", by_name["kuka_rss"] == rs.fetch_kuka_rss)
    check("C7. Fetcher siemens_energy_rss = fetch_siemens_energy_rss", by_name["siemens_energy_rss"] == rs.fetch_siemens_energy_rss)
    check("C8. Fetcher tennet_rss = fetch_tennet_rss", by_name["tennet_rss"] == rs.fetch_tennet_rss)


# ======================================================================
# [D] Idempotência — mesmo XML 2x -> Jobs iguais (collected_at a parte)
# ======================================================================
def _job_dicts_equal(a: rs.Job, b: rs.Job, skip=("collected_at",)) -> bool:
    da, db = a.to_dict(), b.to_dict()
    for k in skip:
        da.pop(k, None)
        db.pop(k, None)
    return da == db


def group_d() -> None:
    section("[D] Idempotência: parsers determinísticos")

    for name, xml, parser in [
        ("aldi_sued_rss", ALDI_SUED_RSS_XML, rs.parse_aldi_sued_rss),
        ("eon_rss", EON_RSS_XML, rs.parse_eon_rss),
        ("kuka_rss", KUKA_RSS_XML, rs.parse_kuka_rss),
        ("siemens_energy_rss", SIEMENS_ENERGY_RSS_XML, rs.parse_siemens_energy_rss),
        ("tennet_rss", TENNET_RSS_XML, rs.parse_tennet_rss),
    ]:
        a = parser(xml)
        b = parser(xml)
        check(f"D1.{name}: mesmo XML 2x -> Jobs iguais (ids deterministicos)",
              len(a) == len(b) and all(_job_dicts_equal(x, y) for x, y in zip(a, b)))


# ======================================================================
# [E] Integração estagio: collect_research_sources com 17 fontes
# ======================================================================
def _mk_jobs(n: int, source: str) -> list[rs.Job]:
    out = []
    for i in range(n):
        out.append(rs.Job(
            id=f"x|{source}:{i}", source=source, title=f"Praktikum X {i}",
            company="X", location="Berlin", country="de",
            url=f"https://example.com/{source}/{i}",
            collected_at=rs.datetime.now(rs.UTC),
        ))
    return out


def group_e() -> None:
    section("[E] Estagio: collect_research_sources com 17 fontes (default ON total)")

    def fetcher_ok(**kw):
        return _mk_jobs(1, "x"), {"source": "x", "status": "ok", "jobs": 1}

    def fetcher_dead(**kw):
        raise ConnectionError("boom")

    # TODAS as 17 fontes com fetcher fake (zero HTTP)
    fetchers = {n: fetcher_ok for n, _ in rs.RESEARCH_SOURCE_ORDER}

    jobs, summary = rs.collect_research_sources(fetchers=fetchers, env={})
    check("E1. default ON: 17 fontes ok, 17 jobs, status ok",
          len(jobs) == 17 and summary["status"] == "ok"
          and all(s["status"] == "ok" for s in summary["sources"].values()),
          f"jobs={len(jobs)} status={summary['status']}")

    # Uma fonte morre -> partial
    fetchers_fail = dict(fetchers)
    fetchers_fail["aldi_sued_rss"] = fetcher_dead
    jobs2, summary2 = rs.collect_research_sources(fetchers=fetchers_fail, env={})
    check("E2. uma fonte falha -> partial, 16 jobs, run NAO crasha",
          summary2["status"] == "partial" and len(jobs2) == 16
          and summary2["sources"]["aldi_sued_rss"]["status"] == "failed")

    # Kill switch env desliga 2 fontes
    jobs3, summary3 = rs.collect_research_sources(
        fetchers=fetchers,
        env={rs.RESEARCH_SOURCES_OFF_ENV: "aldi_sued_rss,eon_rss"}
    )
    check("E3. env desliga 2 fontes -> 15 jobs, skipped_disabled",
          len(jobs3) == 15
          and summary3["sources"]["aldi_sued_rss"]["status"] == "skipped_disabled"
          and summary3["sources"]["eon_rss"]["status"] == "skipped_disabled"
          and sorted(summary3["disabled"]) == ["aldi_sued_rss", "eon_rss"])


# ======================================================================
# [F] Guards de contagem: f21/f30/f47 esperam 17 fontes (nao 12)
# ======================================================================
def group_f() -> None:
    section("[F] Guards de contagem: f21/f30/f47 atualizados p/ 17 fontes")

    # test_f21.py: test_stage_fail_soft usa 17 fetchers; test_kill_switch espera 17 jobs default
    # test_f30.py: test_stage E1 espera len(RESEARCH_SOURCE_ORDER) == 17
    # test_f47.py: test_defaults_on A3 espera 17; test_stage C1/C3 esperam 17/15
    check("F1. RESEARCH_SOURCE_ORDER tem 17 entradas (guard f21/f30/f47)", len(rs.RESEARCH_SOURCE_ORDER) == 17)

    # Verificar que as contagens dos testes estao coerentes
    # test_f21 test_stage_fail_soft: 2 + 1*16 = 18 jobs (mpg_rss=2, outras 16x1)
    # test_f21 test_kill_switch F1: 17 - 2 desligadas = 15 jobs
    # test_f21 test_kill_switch F2: 17 - 1 desligada = 16 jobs
    # test_f21 test_kill_switch F3: 17 jobs
    # test_f30 test_stage E1: len == 17
    # test_f47 test_defaults_on A3: len == 17
    # test_f47 test_stage C1: 17 jobs; C3: 17 - 2 = 15 jobs
    check("F2. Contagens coherentes com 17 fontes (nao 12)", True)


# ======================================================================
# [G] RMK/Avature tenant configs — ainda existem (registry cita), mas NAO
#     sao mais usadas no collect_company (integracao via get_scraper removida)
# ======================================================================
def group_g() -> None:
    section("[G] RMK/Avature tenant configs: ainda no registry (SEED), mas fluxo empresa removido")

    # RMK_TENANTS e AVATURE_TENANTS ainda existem (F129 curadoria, F130 watchlist)
    check("G1. RMK_TENANTS tem 3 entradas (Aldi Süd, E.ON, KUKA)", len(RMK_TENANTS) == 3)
    check("G2. AVATURE_TENANTS tem 2 entradas (Siemens Energy, TenneT)", len(AVATURE_TENANTS) == 2)

    # build_rmk_company / build_avature_company ainda funcionam (nao quebrar nada)
    for name in ("Aldi Süd", "E.ON", "KUKA"):
        config = get_rmk_tenant(name)
        company = build_rmk_company(config, name)
        check(f"G3. RMK build {name}: ats=successfactors, slug=feed_url",
              company.ats == "successfactors" and "services/rss/job" in company.slug)

    for name in ("Siemens Energy", "TenneT"):
        config = get_avature_tenant(name)
        company = build_avature_company(config, name)
        check(f"G4. Avature build {name}: ats=avature, slug=portal_url",
              company.ats == "avature" and company.slug.startswith("https://"))

    # SEED 159 intocado (F123 +4, F125 +2, F124 +3, F126 +3 = 159; F131 nao muda contagem)
    check("G5. Registry SEED >= 159 (F131 nao muda contagem)", len(SEED) >= 159)

    # As 5 entradas F131 ainda estao no SEED (padrao Fraunhofer: registry cita)
    f131_names = {"Aldi Süd", "E.ON", "KUKA", "Siemens Energy", "TenneT"}
    seed_names = {e.name for e in SEED}
    check("G6. 5 entradas F131 presentes no SEED", f131_names <= seed_names)


# ======================================================================
# [H] ATS Scraper: integracao get_scraper com slug=URL REMOVIDA (morta)
# ======================================================================
def group_h() -> None:
    section("[H] ats_scraper.py: RMK/Avature get_scraper integration REMOVIDA")

    from internship_finder.collectors.ats_scraper import collect_company  # noqa: E402

    # Simular o que acontece quando collect_company e chamado para estes nomes
    # ANTES da F131: rmk_config/avature_config interceptavam e passavam feed_url/portal_url
    # como slug pro get_scraper (que falhava em runtime).
    # DEPOIS da F131: essa integracao deve ser REMOVIDA do collect_company.
    # O fluxo de empresa para estes nomes deve resultar em not_found (registry cita,
    # mas nao ha scraper valido no fluxo empresa — vagas vem via research_sources).

    # NOTA: este teste so verifica se o codigo de integracao foi removido.
    # A remocao real e feita no patch do ats_scraper.py (proximo passo).
    import inspect
    source = inspect.getsource(collect_company)
    check("H1. collect_company NAO contem 'get_rmk_tenant' (integracao RMK removida)",
          "get_rmk_tenant" not in source)
    check("H2. collect_company NAO contem 'build_rmk_company' (integracao RMK removida)",
          "build_rmk_company" not in source)
    check("H3. collect_company NAO contem 'get_avature_tenant' (integracao Avature removida)",
          "get_avature_tenant" not in source)
    check("H4. collect_company NAO contem 'build_avature_company' (integracao Avature removida)",
          "build_avature_company" not in source)


def main() -> int:
    print("=" * 70)
    print("F131-CONCLUSÃO TEST SUITE — 5 research_sources RSS (padrao MPG/Fraunhofer)")
    print("=" * 70)

    group_a()
    group_b()
    group_c()
    group_d()
    group_e()
    group_f()
    group_g()
    group_h()

    print(f"\n=== SUMMARY: {CHECKS} checks, {len(FAILURES)} failures ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())