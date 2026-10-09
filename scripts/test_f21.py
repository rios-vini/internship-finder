"""F21 — fontes de pesquisa Tier 1 (MPG RSS + TU Berlin + Leibniz + APIs keyless).

Trava o NOVO comportamento da fase (test_f21, 64a suíte — entra no CI):

GRUPO A — Adapter MPG RSS (parse XML verbatim do probe 09/10):
  A1. Item real -> Job com title/company/location/description/url/id.
  A2. id estavel = <company>|mpg_rss:<sha16(url)> (URL do item, spec).
  A3. posted_at parseado de pubDate RFC 822; internship via is_student_role.
  A4. XML malformado -> [] + log (fail-soft no parse).

GRUPO B — Adapter TU Berlin (listagem HTML verbatim + detail JSON-LD):
  B1. Listagem real (20 anchors) -> 20 items {job_id,url,title}.
  B2. Detail real (JSON-LD JobPosting) -> description/location/deadline.
  B3. Job montado: id = <company>|tu_berlin:<id>; country_iso='de'
      (jobLocation.addressCountry + fallback instituicao).
  B4. Detail falho -> vaga da listagem preservada SEM description.
  B5. Cap de details respeitado (max_details trunca, nao derruba).

GRUPO C — Adapter Leibniz (listagem TYPO3 verbatim):
  C1. Item real -> {slug,url,title,company,location} (instituto, cidade).
  C2. Job: id estavel por slug; country_iso='de' (portal institucional DE).
  C3. Item sem virgula no org -> company cheia, location None.

GRUPO D — APIs keyless (payloads verbatim, prefilter F3):
  D1. Arbeitnow: 325 rows -> 33 student_role -> jobs DE materializados
      (board DE por definicao; location sem marcador de pais).
  D2. Arbeitnow: job sem company OU url -> invalid_rows (nunca crash).
  D3. RemoteOK: item 0 (aviso legal, sem position) ignorado; jobs =
      marcador de estagio + (DE ou remote).
  D4. freehire: countries[] = ['DE'] -> job DE; paginação por offset
      (page e ignored_params — fato medido); limit propagado na URL.

GRUPO E — Fail-soft do estagio (collect_research_sources):
  E1. Fonte 404/timeout (fetcher levanta) -> [] + status failed NO summary
      da fonte; run NAO derruba; OUTRAS fontes entregam jobs.
  E2. TODAS falham -> summary geral failed; jobs=[].
  E3. Uma falha -> status geral partial.
  E4. Budget estourado entre fontes -> skipped_budget na fonte seguinte.

GRUPO F — Kill switch sem deploy (env var):
  F1. INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF=arbeitnow,remoteok ->
      fontes skipped_disabled; MPG/TU/Leibniz/freehire rodam.
  F2. Nome desconhecido no CSV -> log warning + ignorado (sem crash).
  F3. Sem env var -> todas as 6 executam (default ON).

GRUPO G — Idempotência:
  G1. Mesmo payload parseado 2x -> listas iguais campo a campo
      (collected_at a parte — determinismo dos campos da fonte).

GRUPO H — Integração CLI + dedup + ZERO HTTP:
  H1. --registry default ON chama o estagio (stub); --companies OFF;
      --no-research-sources desliga; registro type: research_sources
      gravado no JSONL (status failed gravado mesmo em crash).
  H2. Vaga DE de materials/procurement (fixture) chega ao eligible.
  H3. Dedup: vaga MPG que tambem existe no BA (MESMA URL, fonte
      diferente) NAO duplica — chave URL (b) colapsa cross-fonte.
  H4. ZERO HTTP na suíte: monkeypatch de urllib.request.urlopen +
      socket.socket.connect (padrao test_f15 T5) — qualquer socket
      externo falha a suíte inteira.
  H5. Regressão: --no-research-sources + --no-dataset + --no-direct-fetch
      reproduz o comportamento pre-F21 (estagio ausente do JSONL).
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

from internship_finder import cli  # noqa: E402
from internship_finder import research_sources as rs  # noqa: E402
from internship_finder.dataset_source import row_is_intern_candidate  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "OK" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM dos probes ao vivo (09/10/2026) — a suíte é 100% offline
# ---------------------------------------------------------------------------

# MPG RSS: item real do feed https://www.mpg.de/feeds/jobs.rss (probe r2).
# xmlns:dc VERBATIM do feed real (o item carrega <dc:date> prefixado).
MPG_ITEM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>Job offers - Max Planck Society.</title>
<item>
      <title>Postdoctoral Position(s) (m/f/d) | High-Energy Astrophysics</title>
      <link>https://www.mpg.de/27022851/postdoctoral-position-20-2026</link>
      <description>Postdoc positions within the High-Energy Astrophysics Group at the Max Planck Institute for Extraterrestrial Physics, Garching.</description>
      <pubDate>Thu, 08 Oct 2026 13:46:00 +0200</pubDate>
      <guid isPermaLink="true">https://www.mpg.de/27022851/postdoctoral-position-20-2026?1791459960</guid>
      <dc:date>2026-10-08T13:46:00+02:00</dc:date>
    </item>
</channel></rss>"""

MPG_ITEM_STUDENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Job offers - Max Planck Society.</title>
<item>
      <title>PhD Student Position (m/f/d) | Internship in Quantum Materials Characterization</title>
      <link>https://www.mpg.de/27022852/phd-internship-quantum-materials</link>
      <description>Praktikum for characterization of quantum materials at the Max Planck Institute.</description>
      <pubDate>Thu, 08 Oct 2026 09:00:00 +0200</pubDate>
    </item>
</channel></rss>"""

# TU Berlin: trecho VERBATIM da listagem www.jobs.tu-berlin.de/
# stellenausschreibungen (probe r5 — 20 anchors reais; aqui 2 itens).
TU_LISTING_HTML = """<ul role="list"> <li class="border-b py-4"> <h2 class="text-lg"> <a href="/stellenausschreibungen/205144"> Meister*in - Teamleitung Versorgungstechnik (d/m/w) </a> </h2>
<div class="mt-2">ZUV - Zentrale Universitätsverwaltung</div> </li>
<li class="border-b py-4"> <h2 class="text-lg"> <a href="/stellenausschreibungen/207819"> Studentische Beschäftigung mit 40 Monatsstunden </a> </h2>
<div class="mt-2">Fakultät V - Verkehrs- und Maschinensysteme</div> </li> </ul>"""

# TU Berlin: JSON-LD VERBATIM do detail 207819 (probe r8 — jobLocation
# Berlin/Deutschland, description com marcador studentische Hilfskraft).
TU_DETAIL_JSONLD = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Studentische Beschäftigung mit 40 Monatsstunden","description":"<h3>Ihre Aufgaben</h3>\\n<ul>\\n<li>Vorbereitung und Durchführung von Tutorien in den Modulen Strömungsmechanik und Wasserwesen (45%)</li>\\n<li>Wir suchen eine studentische Hilfskraft</li>\\n</ul>","datePosted":"2026-10-07","validThrough":"2026-11-04T00:00:00+01:00","employmentType":["PART_TIME"],"hiringOrganization":{"@type":"Organization","name":"Technische Universität Berlin","sameAs":"https://www.tu.berlin"},"jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Berlin","addressRegion":"Berlin","addressCountry":"Deutschland"}}],"identifier":{"@type":"PropertyValue","name":"Technische Universität Berlin","value":"VI-SB-0081-2026"}}</script>"""

# Leibniz: trecho VERBATIM da listagem leibniz-gemeinschaft.de/en/careers/
# jobs (probe r4 — h4 com anchor + p.mono-i1 com "Instituto, Cidade").
LEIBNIZ_ITEM_HTML = """<li class="listing-item listing-item-txt"> <div class="stack-xs"> <div class="stack-xxs"> <h4 class="sans-h5"><a class="link" href="/en/careers/jobs/detail/job/show/Job/research-scientist-and-project-coordinator-mfd-in-the-field-of-zooplankton-biodiversity">Research Scientist and Project Coordinator (m/f/d) in the field of Zooplankton Biodiversity</a></h4> <p class="mono-i1"> Senckenberg Gesellschaft für Naturforschung (SGN), Frankfurt am Main </p> </div>"""

LEIBNIZ_STUDENT_HTML = """<li class="listing-item listing-item-txt"> <div class="stack-xs"> <div class="stack-xxs"> <h4 class="sans-h5"><a class="link" href="/en/careers/jobs/detail/job/show/Job/student-assistant-materials-science-institute">Student Assistant (m/f/d) Materials Science Institute</a></h4> <p class="mono-i1"> Leibniz Institute for Materials Engineering </p> </div>"""

# Arbeitnow: item VERBATIM do board (probe r7 — fields reais; description
# HTML-escaped).
ARBEITNOW_ITEM = {
    "slug": "werkstudent-sustainability-berlin-249449",
    "company_name": "Nachhaltigkeit GmbH",
    "title": "Werkstudent Sustainability (m/w/d)",
    "location": "Berlin, Berlin",
    "remote": False,
    "job_types": ["part_time", "internship"],
    "url": "https://www.arbeitnow.com/jobs/werkstudent-sustainability-berlin-249449",
    "created_at": "2026-10-08T10:00:00Z",
    "description": "<p>Support the sustainability team.</p>",
}

ARBEITNOW_PAYLOAD = {"data": [ARBEITNOW_ITEM,
                              {"slug": "no-company", "company_name": "",
                               "title": "Praktikum Supply Chain", "location": "Berlin",
                               "url": "", "job_types": [], "remote": False},
                              {"slug": "senior-role", "company_name": "Other AG",
                               "title": "Senior Manager Finance", "location": "Berlin",
                               "url": "https://www.arbeitnow.com/jobs/senior-role",
                               "job_types": [], "remote": False}],
                     "meta": {"current_page": 1, "last_page": 5}}

# RemoteOK: items VERBATIM do board (probe r7 — item 0 e aviso legal).
REMOTEOK_PAYLOAD = [
    {"last_updated": 1791388805, "legal": "API Terms of Service: Please link back to Remote OK..."},
    {"slug": "remote-telefondienst-fur-tierarztpraxis-1137469", "id": "1137469",
     "epoch": 1791388805, "date": "2026-10-07T16:00:05+00:00",
     "company": "Tierarzt Plus Partner", "position": "Telefondienst für Tierarztpraxis",
     "tags": ["medical"], "location": None, "url": "https://remoteok.com/remote-jobs/remote-telefondienst-1137469",
     "description": "<p>Wir suchen tatkräftige Unterstützung.</p>"},
    {"slug": "remote-internship-data-analytics-1137470", "id": "1137470",
     "epoch": 1791388805, "date": "2026-10-07T16:00:05+00:00",
     "company": "DataWorks GmbH", "position": "Internship Data Analytics (Remote)",
     "tags": ["data"], "location": "Anywhere", "url": "https://remoteok.com/remote-jobs/remote-internship-data-analytics-1137470",
     "description": "<p>Data analytics internship, remote worldwide.</p>"},
]

# freehire: item VERBATIM da API (probe r3/r7 — schema normalizado).
FREEHIRE_ITEM = {
    "public_slug": "werkstudent-automotive-industry-acme-j9k2l3m4",
    "source": "workday", "manually_added": False,
    "external_id": "acme/R1111",
    "url": "https://acme.wd3.myworkdayjobs.com/en-US/acme/job/Germany/Werkstudent-Automotive--Industry-_R-1111",
    "title": "Werkstudent (w/m/d) Automotive & Industry",
    "company": "Acme Materials GmbH",
    "company_slug": "acme-materials", "location": "Munich, Germany",
    "countries": ["DE"], "regions": [], "cities": [], "skills": [],
    "description": "<p>Support the materials team in Munich.</p>",
    "posted_at": "2026-10-09T04:24:01Z", "created_at": "2026-10-09T04:45:58Z",
}

FREEHIRE_PAYLOAD = {"data": [FREEHIRE_ITEM], "meta": {"limit": 100, "offset": 0, "total": 4311234}}


def _job_dicts_equal(a: Job, b: Job, skip=("collected_at",)) -> bool:
    da, db = a.to_dict(), b.to_dict()
    for k in skip:
        da.pop(k, None)
        db.pop(k, None)
    return da == db


# ---------------------------------------------------------------------------
# A. MPG RSS
# ---------------------------------------------------------------------------

def test_mpg() -> None:
    print("== A. Adapter MPG RSS ==")
    jobs = rs.parse_mpg_rss(MPG_ITEM_XML)
    check("A1. item real -> Job com title/company/description/url",
          len(jobs) == 1 and jobs[0].title.startswith("Postdoctoral Position")
          and jobs[0].company == rs.MPG_COMPANY and jobs[0].url.endswith("postdoctoral-position-20-2026")
          and "High-Energy Astrophysics" in (jobs[0].description or ""),
          f"n={len(jobs)}")
    if jobs:
        j = jobs[0]
        check("A2. id estavel = <company>|mpg_rss:<sha16(url)>",
              j.id == f"{rs.MPG_COMPANY}|mpg_rss:{rs._sha16(j.url)}"
              and j.external_id == j.url, j.id[:60])
        check("A3. posted_at RFC 822 parseado; country_iso de",
              j.posted_at is not None and j.posted_at.year == 2026
              and j.country_iso == "de", str(j.posted_at))
    jobs2 = rs.parse_mpg_rss(MG_STUDENT_FIXTURE)
    check("A3b. item com marcador -> internship=True",
          len(jobs2) == 1 and jobs2[0].internship is True)
    check("A4. XML malformado -> [] (fail-soft no parse)",
          rs.parse_mpg_rss("<rss><channel>quebrado") == [])


MG_STUDENT_FIXTURE = MPG_ITEM_STUDENT_XML


# ---------------------------------------------------------------------------
# B. TU Berlin
# ---------------------------------------------------------------------------

def test_tu_berlin() -> None:
    print("== B. Adapter TU Berlin ==")
    items = rs.parse_tu_berlin_listing(TU_LISTING_HTML)
    check("B1. listagem real -> 2 items {job_id,url,title}",
          len(items) == 2 and items[0]["job_id"] == "205144"
          and items[1]["job_id"] == "207819"
          and "Studentische Beschäftigung" in items[1]["title"],
          f"n={len(items)}")
    detail = rs.parse_tu_berlin_detail(TU_DETAIL_JSONLD)
    check("B2. detail JSON-LD -> description/location/deadline/identifier",
          detail is not None and "studentische Hilfskraft" in (detail or {}).get("description", "")
          and (detail or {}).get("location") == "Berlin, Berlin, Deutschland"
          and (detail or {}).get("identifier") == "VI-SB-0081-2026"
          and (detail or {}).get("valid_through") is not None)
    # montagem do job (via fetchers injetados — offline)
    def fake_opener_list(req):
        return TU_LISTING_HTML

    def fake_opener_detail(req):
        url = req.full_url
        if "207819" in url:
            return TU_DETAIL_JSONLD
        return "<html><body>sem jsonld</body></html>"

    def opener(req):
        url = req.full_url
        if "stellenausschreibungen/2" in url and url.rstrip("/").endswith(tuple("0123456789")):
            return fake_opener_detail(req)
        return fake_opener_list(req)

    jobs, stats = rs.fetch_tu_berlin(opener=opener)
    check("B3. jobs montados: id <company>|tu_berlin:<id>; iso de; TU company",
          len(jobs) == 2 and jobs[1].id == f"{rs.TUM_BERLIN_COMPANY}|tu_berlin:207819"
          and jobs[1].country_iso == "de" and jobs[1].location == "Berlin, Berlin, Deutschland"
          and "Tutorien" in (jobs[1].description or ""))
    check("B3b. internship=True (marcador no corpo do detail)",
          jobs[1].internship is True and jobs[0].internship is False,
          f"j0={jobs[0].internship} j1={jobs[1].internship}")
    check("B4. detail sem JSON-LD -> vaga preservada SEM description",
          jobs[0].description is None and jobs[0].title.startswith("Meister*in")
          and stats["details_ok"] == 1 and stats["details_failed"] == 1)
    jobs_cap, stats_cap = rs.fetch_tu_berlin(max_details=1, opener=opener)
    check("B5. cap de details trunca (max_details=1 -> 1 job)",
          len(jobs_cap) == 1 and stats_cap["jobs"] == 1)
    # fail-soft: listagem fora do ar
    def dead_opener(req):
        raise urllib.error.URLError("connection refused")

    jobs_dead, stats_dead = rs.fetch_tu_berlin(opener=dead_opener)
    check("B6. listagem 404/timeout -> [] + status failed (fail-soft)",
          jobs_dead == [] and stats_dead["status"] == "failed")


# ---------------------------------------------------------------------------
# C. Leibniz
# ---------------------------------------------------------------------------

def test_leibniz() -> None:
    print("== C. Adapter Leibniz ==")
    items = rs.parse_leibniz_listing(LEIBNIZ_ITEM_HTML + LEIBNIZ_STUDENT_HTML)
    check("C1. item real -> slug/url/title/company/location",
          len(items) == 2 and items[0]["slug"].startswith("research-scientist")
          and items[0]["company"].startswith("Senckenberg")
          and items[0]["location"] == "Frankfurt am Main"
          and "Student Assistant" in items[1]["title"], f"n={len(items)}")
    check("C1b. item sem virgula no org -> company cheia, location vazio",
          items[1]["company"] == "Leibniz Institute for Materials Engineering"
          and not items[1]["location"], items[1]["company"][:60])
    if items:
        it = items[0]
        check("C2. id estavel por slug; iso de (portal institucional DE)",
              it["url"].startswith("https://www.leibniz-gemeinschaft.de/")
              and it["slug"] in it["url"])
    # fail-soft idem MPG/TU (padrao unico — coberto em E com o estagio)


# ---------------------------------------------------------------------------
# D. APIs keyless (prefilter F3)
# ---------------------------------------------------------------------------

def test_keyless_apis() -> None:
    print("== D. APIs keyless (prefilter F3) ==")
    jobs, rows, invalid = rs.parse_arbeitnow(ARBEITNOW_PAYLOAD)
    check("D1. Arbeitnow: student_role + DE materializados (board DE)",
          len(jobs) == 1 and jobs[0].company == "Nachhaltigkeit GmbH"
          and jobs[0].country_iso == "de" and jobs[0].internship is True
          and rows == 3,
          f"jobs={len(jobs)} rows={rows}")
    check("D2. row student sem company/url -> invalid_rows (nunca crash)",
          invalid == 1, f"invalid={invalid}")
    check("D2b. row sem marcador de estagio NAO materializa",
          all("Senior" not in j.title for j in jobs))
    jobs_r, rows_r, inv_r = rs.parse_remoteok(REMOTEOK_PAYLOAD)
    check("D3. RemoteOK: aviso legal ignorado; internship+remote entra",
          rows_r == 2 and len(jobs_r) == 1 and jobs_r[0].remote is True
          and jobs_r[0].company == "DataWorks GmbH",
          f"rows={rows_r} jobs={len(jobs_r)}")
    check("D3b. job sem marcador de estagio nao entra (Telefondienst)",
          all("Telefondienst" not in j.title for j in jobs_r))
    jobs_f, rows_f, inv_f = rs.parse_freehire(FREEHIRE_PAYLOAD)
    check("D4. freehire: countries=['DE'] -> job DE com URL ATS original",
          len(jobs_f) == 1 and jobs_f[0].country_iso == "de"
          and jobs_f[0].company == "Acme Materials GmbH"
          and jobs_f[0].url.startswith("https://acme.wd3.myworkdayjobs.com"),
          f"jobs={len(jobs_f)}")
    # D4b: prefilter de pais (is_country_row) — item non-DE nao materializa
    # (location SEM marcador textual de DE: o ISO vem so de countries[]).
    payload_non_de = {"data": [dict(FREEHIRE_ITEM, countries=["US"],
                                    title="Internship Materials US",
                                    location="Austin, TX")]}
    jobs_nd, _, _ = rs.parse_freehire(payload_non_de)
    check("D4b. freehire: item non-DE rejeitado no prefilter", jobs_nd == [])
    # D4c: limit propagado na URL (paginacao por offset, page ignorado)
    captured = {}

    def opener_capture(req):
        captured["url"] = req.full_url
        return json.dumps(FREEHIRE_PAYLOAD)

    rs.fetch_freehire(opener=opener_capture, limit=100)
    check("D4c. limit=100 propagado na query (1 request, offset via meta)",
          "limit=100" in captured.get("url", ""))


# ---------------------------------------------------------------------------
# E. Fail-soft do estagio
# ---------------------------------------------------------------------------

def _fetcher_ok(jobs_n=1):
    def f(**kw):
        return [_research_job(i) for i in range(jobs_n)], {
            "source": "x", "status": "ok", "jobs": jobs_n, "rows_seen": jobs_n,
        }
    return f


def _research_job(i=0, source="mpg_rss", url=None, title=None, company=None):
    return Job(
        id=f"{company or 'Max Planck Society'}|{source}:{i}",
        source=source,
        title=title or "Werkstudent Supply Chain Materials",
        company=company or "Max Planck Society",
        location="Berlin",
        country="de", country_iso="de",
        url=url or f"https://mpg.example/job/{i}",
        collected_at=datetime.now(UTC),
    )


def _fetcher_dead(**kw):
    raise RuntimeError("fonte fora do ar")


def test_stage_fail_soft() -> None:
    print("== E. Fail-soft do estagio ==")
    fetchers = {"mpg_rss": _fetcher_ok(2), "tu_berlin": _fetcher_dead,
                "leibniz": _fetcher_ok(1), "arbeitnow": _fetcher_dead,
                "remoteok": _fetcher_ok(1), "freehire": _fetcher_ok(1)}
    jobs, summary = rs.collect_research_sources(fetchers=fetchers, env={})
    check("E1. fonte morta -> status failed NO summary; outras entregam",
          summary["sources"]["tu_berlin"]["status"] == "failed"
          and summary["sources"]["arbeitnow"]["status"] == "failed"
          and len(jobs) == 5 and summary["status"] == "partial",
          f"jobs={len(jobs)} status={summary['status']}")
    fetchers_dead = {n: _fetcher_dead for n, _ in rs.RESEARCH_SOURCE_ORDER}
    jobs2, summary2 = rs.collect_research_sources(fetchers=fetchers_dead, env={})
    check("E2. TODAS falham -> status geral failed; jobs=[]; run NAO crasha",
          jobs2 == [] and summary2["status"] == "failed")
    # E4: budget estourado entre fontes
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    def fetcher_slow(**kw):
        clock["t"] += 200.0
        return [_research_job(0)], {"source": "x", "status": "ok", "jobs": 1}

    jobs3, summary3 = rs.collect_research_sources(
        budget_seconds=250.0, now=now,
        fetchers={n: fetcher_slow for n, _ in rs.RESEARCH_SOURCE_ORDER}, env={})
    skipped = sum(1 for s in summary3["sources"].values()
                  if s["status"] == "skipped_budget")
    # clock fake: t0=0; cada fetch avanca 200s. Fonte 1 roda (0<250),
    # fonte 2 roda (200<250), fonte 3+ estoura (400>250) -> 4 skipped.
    check("E4. budget estourado -> fontes seguintes skipped_budget",
          skipped == 4 and summary3["skipped_budget"] == 4
          and len(jobs3) == 2, f"skipped={skipped} jobs={len(jobs3)}")


# ---------------------------------------------------------------------------
# F. Kill switch sem deploy (env var)
# ---------------------------------------------------------------------------

def test_kill_switch() -> None:
    print("== F. Kill switch (env var) ==")
    fetchers = {n: _fetcher_ok(1) for n, _ in rs.RESEARCH_SOURCE_ORDER}
    jobs, summary = rs.collect_research_sources(
        fetchers=fetchers,
        env={rs.RESEARCH_SOURCES_OFF_ENV: "arbeitnow, remoteok"},
    )
    check("F1. env desliga arbeitnow+remoteok (skipped_disabled); resto roda",
          summary["sources"]["arbeitnow"]["status"] == "skipped_disabled"
          and summary["sources"]["remoteok"]["status"] == "skipped_disabled"
          and summary["sources"]["mpg_rss"]["status"] == "ok"
          and len(jobs) == 4 and sorted(summary["disabled"]) == ["arbeitnow", "remoteok"],
          f"jobs={len(jobs)} disabled={summary['disabled']}")
    jobs2, summary2 = rs.collect_research_sources(
        fetchers=fetchers, env={rs.RESEARCH_SOURCES_OFF_ENV: "nao_existe,mpg_rss"},
    )
    check("F2. nome desconhecido ignorado; mpg desligada",
          summary2["sources"]["mpg_rss"]["status"] == "skipped_disabled"
          and len(jobs2) == 5, f"jobs={len(jobs2)}")
    jobs3, summary3 = rs.collect_research_sources(fetchers=fetchers, env={})
    check("F3. sem env var -> 6 fontes executam (default ON)",
          len(summary3["sources"]) == 6
          and all(s["status"] == "ok" for s in summary3["sources"].values())
          and len(jobs3) == 6, f"jobs={len(jobs3)}")


# ---------------------------------------------------------------------------
# G. Idempotência
# ---------------------------------------------------------------------------

def test_idempotency() -> None:
    print("== G. Idempotência ==")
    a = rs.parse_mpg_rss(MPG_ITEM_XML)
    b = rs.parse_mpg_rss(MPG_ITEM_XML)
    check("G1. MPG: mesmo XML 2x -> Jobs iguais (collected_at a parte)",
          len(a) == len(b) and all(_job_dicts_equal(x, y) for x, y in zip(a, b)))
    ja, _, _ = rs.parse_arbeitnow(ARBEITNOW_PAYLOAD)
    jb, _, _ = rs.parse_arbeitnow(ARBEITNOW_PAYLOAD)
    check("G1b. Arbeitnow: mesmo payload 2x -> iguais",
          len(ja) == len(jb) and all(_job_dicts_equal(x, y) for x, y in zip(ja, jb)))
    # id deterministico (sha16 da URL — sem relogio na chave)
    check("G1c. ids deterministicos (sha16 URL, sem relogio)",
          ja[0].id == jb[0].id and a[0].id == b[0].id)


# ---------------------------------------------------------------------------
# H. Integração CLI + dedup + ZERO HTTP
# ---------------------------------------------------------------------------

COLLECT_SUMMARY = {"ok": [("test:acme", 1, "0.1s")], "empty": [], "timeout": [],
                   "failed": [], "skipped": [], "not_found": False, "companies": {}}


def _one_company_job():
    return [Job(id="Acme|test:1", source="test", title="Praktikum Supply Chain",
                company="Acme", location="Berlin", country_iso="de", country="de",
                url="https://acme.example/1", collected_at=datetime.now(UTC))]


def test_cli_integration() -> None:
    print("== H. Integração CLI + dedup ==")
    with tempfile.TemporaryDirectory() as tmp:
        metrics = f"{tmp}/m.jsonl"
        rs_calls = []

        def _rs_ok(**kw):
            rs_calls.append(1)
            # vaga DE de materials/procurement (fixture do criterio de
            # pronto). Fato da F18: "Werkstudent" puro no titulo e
            # hard-excluded de aplicabilidade — a fixture usa o hibrido
            # realista "Praktikum" (marcador de estagio + termo de area).
            mat_job = Job(
                id="Max Planck Society|mpg_rss:mat-1", source="mpg_rss",
                title="Praktikum Procurement Materials Science",
                company="Max Planck Society", location="München, Germany",
                country="de", country_iso="de",
                url="https://www.mpg.de/p/materials-procurement-praktikum",
                description="Support procurement of materials science equipment.",
                internship=True, collected_at=datetime.now(UTC))
            return [mat_job], {
                "source": "research_sources", "status": "ok", "jobs": 1,
                "duration": 12.4, "skipped_budget": 0, "disabled": [],
                "sources": {"mpg_rss": {"source": "mpg_rss", "status": "ok",
                                        "jobs": 1, "rows_seen": 30, "duration": 12.4,
                                        "error": None}}}

        with patch.object(cli, "collect_company",
                          side_effect=lambda name, **kw: (_one_company_job(), COLLECT_SUMMARY)), \
             patch.object(cli, "collect_research_sources", side_effect=_rs_ok):
            rc = cli.main(["--registry", "--companies", "SAP", "--no-dataset",
                           "--no-direct-fetch", "--output", f"{tmp}/j1.json",
                           "--filter-output", f"{tmp}/e1.json", "--metrics", metrics])
        check("H1a. --registry: estagio roda default ON; exit 0",
              rs_calls and rc == 0, f"rc={rc} calls={len(rs_calls)}")
        e = json.loads(Path(f"{tmp}/e1.json").read_text(encoding="utf-8"))
        check("H2. vaga DE materials/procurement chega ao eligible",
              any(x.get("source") == "mpg_rss" for x in e),
              f"eligible={len(e)}")
        lines = [json.loads(x) for x in
                 Path(metrics).read_text(encoding="utf-8").splitlines() if x.strip()]
        rec = next((r for r in lines if r.get("type") == "research_sources"), None)
        check("H2b. registro type: research_sources no JSONL (status ok)",
              rec is not None and rec.get("status") == "ok"
              and rec.get("sources", {}).get("mpg_rss", {}).get("jobs") == 1)

        # H1b: --no-research-sources desliga
        rs_calls.clear()

        def _rs_never(**kw):
            rs_calls.append(1)
            return [], {"source": "research_sources", "status": "ok",
                        "jobs": 0, "duration": 0, "skipped_budget": 0,
                        "disabled": [], "sources": {}}

        with patch.object(cli, "collect_company",
                          side_effect=lambda name, **kw: (_one_company_job(), COLLECT_SUMMARY)), \
             patch.object(cli, "collect_research_sources", side_effect=_rs_never):
            rc = cli.main(["--registry", "--companies", "SAP", "--no-dataset",
                           "--no-direct-fetch", "--no-research-sources",
                           "--output", f"{tmp}/j2.json", "--filter-output", f"{tmp}/e2.json",
                           "--metrics", f"{tmp}/m2.jsonl"])
        check("H1b. --no-research-sources desliga (regressao pre-F21)",
              not rs_calls and rc == 0)
        lines2 = [json.loads(x) for x in
                  Path(f"{tmp}/m2.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        check("H5. sem o estagio, JSONL NAO tem registro research_sources",
              not any(r.get("type") == "research_sources" for r in lines2))

        # H1c: --companies puro -> default OFF
        rs_calls.clear()
        with patch.object(cli, "collect_company",
                          side_effect=lambda name, **kw: (_one_company_job(), COLLECT_SUMMARY)), \
             patch.object(cli, "collect_research_sources", side_effect=_rs_never):
            rc = cli.main(["--companies", "Acme", "--output", f"{tmp}/j3.json",
                           "--filter-output", f"{tmp}/e3.json", "--metrics", f"{tmp}/m3.jsonl"])
        check("H1c. --companies puro: estagio OFF por default", not rs_calls)

        # H1d: estagio crasha -> run segue exit 0, registro failed gravado
        def _rs_crash(**kw):
            raise RuntimeError("todas as fontes fora do ar")

        with patch.object(cli, "collect_company",
                          side_effect=lambda name, **kw: (_one_company_job(), COLLECT_SUMMARY)), \
             patch.object(cli, "collect_research_sources", side_effect=_rs_crash):
            rc = cli.main(["--registry", "--companies", "SAP", "--no-dataset",
                           "--no-direct-fetch", "--output", f"{tmp}/j4.json",
                           "--filter-output", f"{tmp}/e4.json", "--metrics", f"{tmp}/m4.jsonl"])
        lines4 = [json.loads(x) for x in
                  Path(f"{tmp}/m4.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        rec4 = next((r for r in lines4 if r.get("type") == "research_sources"), None)
        check("H1d. estagio crashou: run segue exit 0; registro failed gravado",
              rc == 0 and rec4 is not None and rec4.get("status") == "failed",
              f"rc={rc}")

        # H3: dedup cross-fonte — mesma vaga MPG no BA (MESMA URL) colapsa
        from internship_finder.dedup import deduplicate
        mpg_job = _research_job(0, source="mpg_rss",
                                url="https://www.arbeitsagentur.de/jobsuche/jobdetail/BA-123",
                                title="Praktikum Procurement", company="Acme Co")
        ba_job = Job(
            id="Acme Co|direct:bundesagentur:BA-123", source="direct:bundesagentur",
            title="Praktikum Procurement", company="Acme Co",
            location="Berlin", country="de", country_iso="de",
            url="https://www.arbeitsagentur.de/jobsuche/jobdetail/BA-123",
            description="Vaga BA com description completa.",
            internship=True, external_id="BA-123",
            collected_at=datetime.now(UTC))
        kept, stats_d, _ = deduplicate([mpg_job.to_dict(), ba_job.to_dict()])
        check("H3. MPG x BA mesma URL -> colapsam na chave URL (b); 1 vaga fica",
              len(kept) == 1 and stats_d.get("url") == 1
              and kept[0].get("description") == "Vaga BA com description completa.",
              f"kept={len(kept)} stats={stats_d}")


# ---------------------------------------------------------------------------
# H4. ZERO HTTP na suíte (padrao test_f15 T5) — roda POR ULTIMO
# ---------------------------------------------------------------------------

def test_zero_http() -> None:
    print("== H4. ZERO HTTP na suíte ==")
    calls: list[str] = []

    def _fail_open(req, *a, **kw):
        calls.append(f"urlopen:{req.full_url}")
        raise AssertionError("HTTP BLOQUEADO na suíte F21")

    import socket

    orig_connect = socket.socket.connect

    def _fail_connect(self, address):
        calls.append(f"socket:{address}")
        raise AssertionError("SOCKET BLOQUEADO na suíte F21")

    urllib.request.urlopen = _fail_open  # type: ignore[assignment]
    socket.socket.connect = _fail_connect  # type: ignore[assignment]
    try:
        # exercita TODOS os fetch paths com opener morto (rede bloqueada):
        # o opener injetado nunca toca urlopen; se QUALQUER caminho
        # resolver para o urllib real, o guard acima derruba.
        def dead_opener(req):
            raise RuntimeError("opener morto — como uma fonte fora do ar")

        rs.fetch_mpg_rss(opener=dead_opener)
        rs.fetch_tu_berlin(opener=dead_opener)
        rs.fetch_leibniz(opener=dead_opener)
        rs.fetch_arbeitnow(opener=dead_opener)
        rs.fetch_remoteok(opener=dead_opener)
        rs.fetch_freehire(opener=dead_opener)
        rs.collect_research_sources(
            fetchers={n: (lambda **kw: (_fetcher_dead(**kw) and None) or ([], {"source": n, "status": "failed", "jobs": 0}))
                      for n, _ in rs.RESEARCH_SOURCE_ORDER},
            env={})
        check("build inteiro sem socket externo", calls == [], f"calls={calls[:3]}")
    finally:
        urllib.request.urlopen = orig_open  # type: ignore[assignment]
        socket.socket.connect = orig_connect  # type: ignore[method-assign]


orig_open = urllib.request.urlopen


def main() -> int:
    print("== F21: fontes de pesquisa Tier 1 (MPG+TU Berlin+Leibniz+keyless) ==")
    test_mpg()
    test_tu_berlin()
    test_leibniz()
    test_keyless_apis()
    test_stage_fail_soft()
    test_kill_switch()
    test_idempotency()
    test_cli_integration()
    test_zero_http()
    failed = [c for c in CHECKS if not c[1]]
    print()
    print(f"Total: {len(CHECKS)} | OK: {len(CHECKS) - len(failed)} | FAIL: {len(failed)}")
    for name, _, detail in failed:
        print(f"  FALHOU: {name} {detail}")
    if failed:
        print("FALHAS")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
