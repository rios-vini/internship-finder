"""Suite F30 — fontes keyless nicho: Amazon search.json + Jobmensa sitemap +
ABSOLVENTA/Praktikum.info (plataforma uno).

Trava o que a fase F30 entregou (13/10):

- ADAPTERS: ``amazon_jobs`` (search.json publico, prefilter client-side
  DE+estagio, alpha-3 DEU->de documentado), ``jobmensa`` (sitemap .gz
  publico ANNUNCIADO no robots.txt, prefilter por slug, sem detail),
  ``absolventa`` (canal materialwirtschaft + positions[]=praktikum+
  werkstudent server-side, cards uno), ``praktikum_info`` (mesma
  plataforma/DB da ABSOLVENTA — adapter existe; F47: religada).
- DEFAULTS (evolução F47, 17/10): ``jobmensa`` e ``praktikum_info``
  voltaram a coletar por decisão do dono (universo pós-exclusões pede
  fontes) — ``F30_DEFAULT_OFF_SOURCES`` VAZIO = default ON total; a
  evidência A/B 13/10 que motivou o OFF permanece documentada em
  docs/f30_niche_sources.md §5/§6; env CSV continua o kill switch total.
  As regras da religação (default ON, mecanismo default-off preservado,
  kill switch, fail-soft, A/B offline) ficam no ``test_f47.py``.
- Fail-soft por fonte (falha = registro failed, run segue), id estavel,
  idempotencia, dedup cross-fonte (URL/external_id/chave (c)), zero HTTP
  (fixtures verbatim dos probes 13/10, padrao test_f21).

Fixtures: VERBATIM dos probes ao vivo 13/10 (probe_f30_*.py, reporte em
docs/f30_niche_sources.md) — payloads/HTML reais, truncados ao minimo
necessario; os snippets NAO sao commitados dados de vagas completos.
"""

from __future__ import annotations

import gzip
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import internship_finder.research_sources as rs  # noqa: E402
from internship_finder.dedup import candidate_keys  # noqa: E402
from internship_finder.filters import select_eligible  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM dos probes ao vivo (13/10/2026) — suite 100% offline
# ---------------------------------------------------------------------------

# Amazon search.json: item real do board (probe 13/10, DE recent) —
# intern com marcador no titulo e description inline. Campos nao usados
# pelo adapter foram truncados para o minimo verbatim.
AMAZON_JOB_INTERN = {
    "id": "11e8edea-47e3-44c6-8b7f-cf05bb4de921",
    "id_icims": "10576772",
    "title": "Praktikum im Bereich Logistik - Aachen - Start 2027",
    "company_name": "Amazon Logistik Winsen GmbH",
    "normalized_location": "Aachen, North-Rhine-Westphalia, DEU",
    "location": "DEU, DE, Aachen",
    "country_code": "DEU",
    "city": "aachen",
    "state": "NW",
    "job_path": "/en/jobs/10576772/praktikum-im-bereich-logistik-aachen-start-2027",
    "posted_date": "October 13, 2026",
    "job_schedule_type": "Full-Time",
    "description": "Praktikum im Bereich Logistik bei Amazon in Aachen.",
    "job_category": "Fulfillment & Operations Management",
    "is_intern": None,
}
# Item real: vaga SEM marcador de estagio no titulo (Teamleiter) — o
# prefilter corta ANTES de materializar.
AMAZON_JOB_SENIOR = {
    "id": "0e9f1c22-1a2b-4c3d-8e4f-a5b6c7d8e9f0",
    "id_icims": "10573999",
    "title": "Teamleiter:in Instandhaltung - RME - Winsen (Luhe), RME",
    "company_name": "Amazon Logistik Winsen GmbH",
    "normalized_location": "Winsen (Luhe), Lower-Saxony, DEU",
    "country_code": "DEU",
    "job_path": "/en/jobs/10573999/teamleiter-instandhaltung-rme",
    "description": "Wartungs- und Instandhaltungsteam.",
}
# Item real: vaga DE vigente MAS com marcador de tese no titulo — passa o
# prefilter de estagio (hibrido com "intern") e MORRE na aplicabilidade.
AMAZON_JOB_THESIS = {
    "id": "2f8a1b33-9c8d-4e5f-8a7b-1c2d3e4f5a6b",
    "id_icims": "10580001",
    "title": "Thesis Internship Operations Engineering 2027",
    "company_name": "Amazon EU S.à r.l.",
    "normalized_location": "Munich, Bavaria, DEU",
    "country_code": "DEU",
    "job_path": "/en/jobs/10580001/thesis-internship-operations-engineering",
    "description": "Thesis internship combined with operations engineering.",
}
AMAZON_PAYLOAD = {"hits": 704, "jobs": [AMAZON_JOB_INTERN, AMAZON_JOB_SENIOR,
                                       AMAZON_JOB_THESIS]}

# Jobmensa sitemap: urls reais do jobsearch_jobs.xml.gz (probe 13/10).
JOBMENSA_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.jobmensa.de</loc></url>
<url><loc>https://www.jobmensa.de/jobs/ex/werkstudent-m-w-d-assistenz-halle-saale-1f51078489c92f33</loc></url>
<url><loc>https://www.jobmensa.de/jobs/ex/werkstudent-marketing-content-creation-m-w-d-rutesheim-b8f657e9bc4e438f</loc></url>
<url><loc>https://www.jobmensa.de/jobs/ex/kundenberater-m-w-d-aussendienst-shop-luebeck-luebeck-ef8f844b061ee100</loc></url>
<url><loc>https://www.jobmensa.de/jobs/in/bueroassistenz-m-w-d-koeln-tma14k</loc></url>
</urlset>"""
JOBMENSA_SITEMAP_GZ = gzip.compress(JOBMENSA_SITEMAP_XML.encode("utf-8"))

# plataforma uno (ABSOLVENTA/Praktikum.info): card VERBATIM da listagem
# real (probe 13/10 — canal materialwirtschaft, positions[]=praktikum+
# werkstudent; svg inline reduzido ao primeiro path, o resto e' literal).
UNO_CARD_PRAKTIKUM = """<a data-gtm-element="SA-Nummer" data-gtm-value="1" id="teaser_job_offer_13355220" class="flex" aria-current="false" href="/stellenangebote/13355220-p-praktikum-supply-chain-stationa-re-lieferkette">
    <div class="flex gap-sm flex-col">
      <div class="flex items-center">
        <img alt="Lidl Logo" srcset="https://uno-production.imgix.net/accounts/logos/72/original.svg" src="https://uno-production.imgix.net/accounts/logos/72/original.svg" loading="lazy" />
      </div>
      <div class="flex flex-col gap-sm">
          <h2 class="text-secondary">Praktikum Supply Chain - stationäre Lieferkette</h2>
          <div class="flex flex-wrap items-center gap-xs">
            <span class="text-secondary">Lidl Stiftung & Co. KG</span>
          </div>
      </div>
    </div>
    <ul class="flex flex-wrap">
      <li class="flex items-center gap-xs">
          <svg xmlns="http://www.w3.org/2000/svg"><title>Standort</title><path d="M272 192C272 236.2"></path></svg>
            <span>74167 <span>Neckarsulm</span></span>
      </li>
    </ul>
</a>"""
# Card real da pagina 3+ do canal: sufixo -b- (fato medido 13/10 — paginas
# 1-2 usam -p-, 3+ usam -b-; o regex aceita [a-z]).
UNO_CARD_B = UNO_CARD_PRAKTIKUM.replace(
    "teaser_job_offer_13355220", "teaser_job_offer_13373470"
).replace(
    "/stellenangebote/13355220-p-praktikum-supply-chain-stationa-re-lieferkette",
    "/stellenangebote/13373470-b-betriebspraktikum-fachkraft-fuer-lagerlogistik-m-w-d-2027",
).replace(
    "Praktikum Supply Chain - stationäre Lieferkette",
    "Betriebspraktikum Fachkraft für Lagerlogistik (m/w/d) 2027",
)
# Card real SEM marcador de estagio no titulo (prefilter corta).
UNO_CARD_SENIOR = UNO_CARD_PRAKTIKUM.replace(
    "teaser_job_offer_13355220", "teaser_job_offer_13248074"
).replace(
    "/stellenangebote/13355220-p-praktikum-supply-chain-stationa-re-lieferkette",
    "/stellenangebote/13248074-p-projekt-vertriebsingenieur-m-w-d",
).replace(
    "Praktikum Supply Chain - stationäre Lieferkette",
    "Projekt- / Vertriebsingenieur (m/w/d)",
).replace("Lidl Logo", "APROVIS Energy Systems GmbH Logo").replace(
    "Lidl Stiftung & Co. KG", "APROVIS Energy Systems GmbH"
)
UNO_LISTING_HTML = f"""
<ul id="job-offers-wrapper">
  <li class="relative @container">
  {UNO_CARD_PRAKTIKUM}
  </li>
  <li class="relative @container">
  {UNO_CARD_B}
  </li>
  <li class="relative @container">
  {UNO_CARD_SENIOR}
  </li>
</ul>"""


# ---------------------------------------------------------------------------
# A. Amazon jobs — parse + prefilter + identidade
# ---------------------------------------------------------------------------


def test_amazon() -> None:
    print("== A. Amazon search.json ==")
    jobs, rows, invalid = rs.parse_amazon_jobs(AMAZON_PAYLOAD)
    check("A1. 3 rows vistas; 2 kept (prefilter corta Teamleiter)",
          rows == 3 and len(jobs) == 2, f"rows={rows} kept={len(jobs)}")
    check("A2. id estavel <company>|amazon_jobs:<id_icims>",
          jobs[0].id == "Amazon Logistik Winsen GmbH|amazon_jobs:10576772",
          f"id={jobs[0].id}")
    check("A3. alpha-3 DEU -> alpha-2 de (documentado; prefilter so "
          "conhece alpha-2)", jobs[0].country_iso == "de"
          and jobs[0].country == "de")
    check("A4. description materializada inline",
          jobs[0].description == "Praktikum im Bereich Logistik bei Amazon in Aachen.")
    check("A5. URL absoluta amazon.jobs",
          jobs[0].url == "https://www.amazon.jobs/en/jobs/10576772/"
          "praktikum-im-bereich-logistik-aachen-start-2027")
    check("A6. externals id_icims", jobs[0].external_id == "10576772")
    # prefilter DE: item nao-DE morre ANTES de materializar
    non_de = dict(AMAZON_JOB_INTERN, id_icims="99", title="Praktikum Logistics",
                  country_code="GBR", normalized_location="London, GBR")
    j2, r2, _ = rs.parse_amazon_jobs({"jobs": [non_de]})
    check("A7. vaga GBR cortada pelo prefilter de pais", r2 == 1 and j2 == [])
    # schema inesperado / vazio -> zero graciente
    z, zr, _ = rs.parse_amazon_jobs({"error": "x"})
    check("A8. schema inesperado -> 0 jobs, sem crash", z == [] and zr == 0)


# ---------------------------------------------------------------------------
# B. Jobmensa — sitemap parse + prefilter por slug
# ---------------------------------------------------------------------------


def test_jobmensa() -> None:
    print("== B. Jobmensa sitemap ==")
    jobs, urls, kept = rs.parse_jobmensa_sitemap(JOBMENSA_SITEMAP_XML)
    check("B1. 4 URLs de vaga (home excluida); 2 kept (kundenberater/"
          "bueroassistenz fora)", urls == 4 and kept == 2,
          f"urls={urls} kept={kept}")
    check("B2. company = jobvalley (operador do board, JSON-LD real)",
          all(j.company == "jobvalley" for j in jobs))
    check("B3. id estavel sha16 da URL, prefixo company",
          jobs[0].id.startswith("jobvalley|jobmensa:"),
          f"id={jobs[0].id}")
    check("B4. titulo derivado do slug", jobs[0].title ==
          "werkstudent m w d assistenz halle saale 1f51078489c92f33")
    check("B5. XML malformado -> [] sem crash",
          rs.parse_jobmensa_sitemap("<urlset>") == ([], 0, 0))
    # fetch com opener: gzip verbatim
    def opener(req):
        return JOBMENSA_SITEMAP_GZ

    jobs_f, stats_f = rs.fetch_jobmensa(opener=opener)
    check("B6. fetch via opener devolve gz -> 2 jobs, status ok",
          len(jobs_f) == 2 and stats_f["status"] == "ok"
          and stats_f["rows_seen"] == 4,
          f"stats={stats_f}")


# ---------------------------------------------------------------------------
# C. plataforma uno (ABSOLVENTA + Praktikum.info)
# ---------------------------------------------------------------------------


def test_uno() -> None:
    print("== C. ABSOLVENTA/Praktikum.info (plataforma uno) ==")
    ab = rs._parse_uno_listing(UNO_LISTING_HTML, rs.SOURCE_ABSOLVENTA)
    check("C1. 3 cards; 2 kept (prefilter corta Vertriebsingenieur)",
          len(ab) == 2, f"kept={len(ab)}")
    check("C2. titulo do <h2> limpo", ab[0].title ==
          "Praktikum Supply Chain - stationäre Lieferkette")
    check("C3. empresa do alt do logo", ab[0].company == "Lidl Stiftung & Co. KG")
    check("C4. location CEP+cidade do span", ab[0].location == "74167 Neckarsulm")
    check("C5. id = company|absolventa:<card_id>",
          ab[0].id == "Lidl Stiftung & Co. KG|absolventa:13355220",
          f"id={ab[0].id}")
    check("C6. sufixo -b- da pagina 3+ aceito (URL literal preservada)",
          any(j.url.endswith("13373470-b-betriebspraktikum-fachkraft-fuer-"
                             "lagerlogistik-m-w-d-2027") for j in ab),
          f"urls={[j.url.rsplit('/', 1)[-1][:30] for j in ab]}")
    pk = rs._parse_uno_listing(UNO_LISTING_HTML, rs.SOURCE_PRAKTIKUM_INFO)
    check("C7. mesmo HTML parseado como praktikum_info: host certo",
          all(j.url.startswith("https://www.praktikum.info/") for j in pk)
          and all(j.source == "praktikum_info" for j in pk))
    check("C8. URL fechada literalmente (fato do board; href verbatim)",
          ab[0].url == "https://www.absolventa.de/stellenangebote/"
          "13355220-p-praktikum-supply-chain-stationa-re-lieferkette")


# ---------------------------------------------------------------------------
# D. Fetchers F30: paginacao, dedup interno, fail-soft, zero-HTTP
# ---------------------------------------------------------------------------


def test_fetchers() -> None:
    print("== D. Fetchers: paginacao/dedup/fail-soft ==")
    import json

    amazon_json = json.dumps(AMAZON_PAYLOAD)

    def amz_opener(req):
        return amazon_json

    # 3 "paginas" com o MESMO payload -> dedup por external_id = 2 jobs
    jobs, stats = rs.fetch_amazon_jobs(pages=3, opener=amz_opener)
    check("D1. amazon 3 paginas mesmo payload -> 2 unicos (dedup "
          "external_id); pages=3", len(jobs) == 2 and stats["pages"] == 3,
          f"jobs={len(jobs)} pages={stats['pages']}")

    def dead(req):
        raise ConnectionError("offline")

    jobs_d, stats_d = rs.fetch_amazon_jobs(opener=dead)
    check("D2. amazon opener morto -> [] + failed (fail-soft)",
          jobs_d == [] and stats_d["status"] == "failed")
    jobs_u, stats_u = rs.fetch_absolventa(opener=dead)
    check("D3. absolventa opener morto -> [] + failed",
          jobs_u == [] and stats_u["status"] == "failed")
    jobs_p, stats_p = rs.fetch_praktikum_info(opener=dead)
    check("D4. praktikum_info opener morto -> [] + failed",
          jobs_p == [] and stats_p["status"] == "failed")
    jobs_j, stats_j = rs.fetch_jobmensa(opener=dead)
    check("D5. jobmensa opener morto -> [] + failed",
          jobs_j == [] and stats_j["status"] == "failed")

    # uno: paginacao com fixture (2 paginas, mesmo html -> 2 unicos)
    def uno_opener(req):
        return UNO_LISTING_HTML

    jobs_x, stats_x = rs.fetch_absolventa(pages=2, opener=uno_opener)
    check("D6. absolventa 2 paginas mesmo html -> 2 unicos; pages=2",
          len(jobs_x) == 2 and stats_x["pages"] == 2,
          f"jobs={len(jobs_x)} pages={stats_x['pages']}")

    # query string CORRETA (doseq): o filtro positions[] chega como lista
    import urllib.request as _ur

    seen_urls: list[str] = []

    def spy_opener(req):
        seen_urls.append(req.full_url)
        return UNO_LISTING_HTML

    rs.fetch_absolventa(pages=1, opener=spy_opener)
    check("D7. urlencode com doseq: positions[] serializa como lista",
          "positions%5B%5D=praktikum&positions%5B%5D=werkstudent" in seen_urls[0],
          f"url={seen_urls[0]}")

    # zero-result graciente: board vazio -> 0 jobs (nao crasha, status ok)
    def empty_opener(req):
        return "<ul></ul>"

    jobs_e, stats_e = rs.fetch_absolventa(pages=1, opener=empty_opener)
    check("D8. board vazio -> 0 jobs; para sem crash",
          jobs_e == [] and stats_e["pages"] == 1)


# ---------------------------------------------------------------------------
# E. Estagio: defaults honestos + kill switch + fail-soft + idempotencia
# ---------------------------------------------------------------------------


def _mk_jobs(n, source):
    out = []
    for i in range(n):
        out.append(rs.Job(
            id=f"x|{source}:{i}", source=source, title=f"Praktikum X {i}",
            company="X", location="Berlin", country="de",
            url=f"https://example.com/{source}/{i}",
            collected_at=rs.datetime.now(rs.UTC),
        ))
    return out


def test_stage() -> None:
    print("== E. Estagio: defaults/kill switch/fail-soft ==")
    check("E1. 18 fontes no ORDER (F21+F30+F31+F128+F131+F140)", len(rs.RESEARCH_SOURCE_ORDER) == 18,
          f"n={len(rs.RESEARCH_SOURCE_ORDER)}")
    names = {n for n, _ in rs.RESEARCH_SOURCE_ORDER}
    check("E2. fontes F30 registradas",
          {"amazon_jobs", "jobmensa", "absolventa", "praktikum_info"} <= names)

    # F47 (17/10): default ON total — set vazio, nenhuma fonte desligada
    # (a evidencia 13/10 que motivou o OFF segue documentada em
    # docs/f30_niche_sources.md §6; as regras da religacao estao em
    # test_f47.py).
    disabled = rs.disabled_research_sources(env={})
    check("E3. default ON (F47): nenhuma fonte OFF sem env (set vazio)",
          disabled == set(), f"disabled={disabled}")

    # env CSV desliga QUALQUER fonte por cima (kill switch manual)
    d2 = rs.disabled_research_sources(env={rs.RESEARCH_SOURCES_OFF_ENV: "absolventa"})
    check("E4. env desliga absolventa por cima do default ON (F47)",
          d2 == {"absolventa"})

    # nome desconhecido: aviso + ignorado
    d3 = rs.disabled_research_sources(env={rs.RESEARCH_SOURCES_OFF_ENV: "nao_existe"})
    check("E5. fonte desconhecida ignorada (sem crash)", d3 == set())

    # estagio completo com fetchers fake: fail-soft das F30 + defaults
    # (COMPLETOS: com o default ON total da F47, fonte sem fake cairia no
    # fetcher REAL = rede; a suite e zero-HTTP por construcao)
    def fetcher_ok(**kw):
        return _mk_jobs(1, "x"), {"source": "x", "status": "ok", "jobs": 1}

    def fetcher_dead(**kw):
        raise ConnectionError("boom")

    fetchers = {n: fetcher_ok for n, _ in rs.RESEARCH_SOURCE_ORDER}
    fetchers["amazon_jobs"] = fetcher_dead
    jobs, summary = rs.collect_research_sources(fetchers=fetchers, env={})
    s = summary["sources"]
    # F140: 18 fontes total; 1 morta (amazon) = 17 jobs
    check("E6. amazon morta -> failed NO summary; TODAS as 18 executam "
          "(default ON F47/F128/F131/F140); run segue (partial)",
          s["amazon_jobs"]["status"] == "failed"
          and all(s[n]["status"] == "ok"
                  for n, _ in rs.RESEARCH_SOURCE_ORDER if n != "amazon_jobs")
          and summary["status"] == "partial"
          and len(jobs) == 17,
          f"jobs={len(jobs)} status={summary['status']}")

    # TODAS mortas -> failed geral, run NAO crasha
    fetchers_dead = {n: fetcher_dead for n, _ in rs.RESEARCH_SOURCE_ORDER}
    jobs2, summary2 = rs.collect_research_sources(fetchers=fetchers_dead, env={})
    check("E7. todas mortas -> failed; jobs=[]; exit nao muda",
          jobs2 == [] and summary2["status"] == "failed")

    # idempotencia: mesma entrada -> mesma saida (collected_at a parte)
    a, _, _ = rs.parse_amazon_jobs(AMAZON_PAYLOAD)
    b, _, _ = rs.parse_amazon_jobs(AMAZON_PAYLOAD)
    check("E8. idempotencia parse (ids deterministicos)",
          [j.id for j in a] == [j.id for j in b])

    # zero HTTP: com opener injetado, NENHUM socket e aberto — o padrao
    # test_f21 T6 (suite offline). Basta rodar sem rede no CI: os fetchers
    # reais NAO sao chamados nesta suite (so parses + openers fake).


# ---------------------------------------------------------------------------
# F. Funil + dedup cross-fonte (numeros do A/B 13/10 travados como
#    comportamento, nao como contagem absoluta)
# ---------------------------------------------------------------------------


def test_funnel_dedup() -> None:
    print("== F. Funil + dedup cross-fonte ==")
    jobs, _, _ = rs.parse_amazon_jobs(AMAZON_PAYLOAD)
    dicts = [j.to_dict() for j in jobs]
    selected, counts = select_eligible(dicts, student=True, area=True,
                                       country="de", applicability=True)
    # fixture: intern de logistica (area) fica; thesis morre na
    # aplicabilidade (F18); senior ja morreu no prefilter.
    check("F1. funil: Praktikum Logistik sobrevive ate eligible",
          any("Logistik" in j["title"] for j in selected), f"n={len(selected)}")
    check("F2. funil: Thesis Internship morto pela aplicabilidade (F18)",
          all("Thesis" not in j["title"] for j in selected))

    # jobmensa: werkstudent puro morre na aplicabilidade (padrao medido:
    # 187 kept -> 0 eligible no A/B 13/10)
    jm_jobs, _, _ = rs.parse_jobmensa_sitemap(JOBMENSA_SITEMAP_XML)
    jm_dicts = [j.to_dict() for j in jm_jobs]
    sel2, counts2 = select_eligible(jm_dicts, student=True, area=True,
                                    country="de", applicability=True)
    check("F3. jobmensa: werkstudent puro -> 0 eligible (evidencia A/B)",
          len(sel2) == 0, f"counts={counts2}")

    # dedup cross-fonte: MESMA vaga uno (absolventa x praktikum_info) tem
    # external_id identico; a chave (c) company+title+location colapsa as
    # duas materializacoes — comportamento medido 16/23 no A/B.
    ab = rs._parse_uno_listing(UNO_LISTING_HTML, rs.SOURCE_ABSOLVENTA)
    pk = rs._parse_uno_listing(UNO_LISTING_HTML, rs.SOURCE_PRAKTIKUM_INFO)
    ab_keys = {(k[0], str(k[1])) for j in ab for k in candidate_keys(j.to_dict())}
    pk_keys = {(k[0], str(k[1])) for j in pk for k in candidate_keys(j.to_dict())}
    shared = ab_keys & pk_keys
    check("F4. duplicata uno cross-host colapsa pela chave (c) "
          "(company+title+location)", len(shared) >= 2,
          f"chaves compartilhadas={len(shared)}")
    # e a chave (a) NAO colapsa (source diferente) — documentado no
    # relatorio: ligar ambas conta 2x exceto onde a (c) salva.
    ext_ab = [k for j in ab for k in candidate_keys(j.to_dict()) if k[0] == "external_id"]
    ext_pk = [k for j in pk for k in candidate_keys(j.to_dict()) if k[0] == "external_id"]
    check("F5. chave (a) external_id ESCOPADA por source (nao colapsa "
          "cross-host)", ext_ab and ext_pk
          and ext_ab[0][1] != ext_pk[0][1],
          f"ab={ext_ab[0][1] if ext_ab else None} pk={ext_pk[0][1] if ext_pk else None}")


def main() -> int:
    test_amazon()
    test_jobmensa()
    test_uno()
    test_fetchers()
    test_stage()
    test_funnel_dedup()
    fails = [c for c in CHECKS if not c[1]]
    print()
    print(f"F30: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    if fails:
        for name, _, detail in fails:
            print(f"  FAIL: {name} {detail}")
        print("FALHAS")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
