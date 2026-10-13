#!/usr/bin/env python3
"""F31 — BME JobSource (jobsource.bme.de): adapter + gate + Crawl-delay.

Trava o NOVO comportamento da fase (test_f31, 69a suíte — entra no CI):

GRUPO A — Gate anti-bot SEM browser (probe 13/10):
  A1. 302 -> Location botchallenge.html?token=<hex> -> adapter extrai o
       token e devolve no cookie bot_verified (ECHO — o JS do desafio
       apenas copia o query para o cookie; o servidor valida o VALOR).
  A2. Location sem botchallenge/token -> failed "sem challenge
       utilizavel" (fail-soft, [] + status failed).
  A3. Sem redirect (200 direto) -> cookie None, fluxo segue.

GRUPO B — Listagem (Drupal server-rendered, VERBATIM do probe 13/10):
  B1. 20 items/pag: anchor recruiter-job-link (href absoluto), title,
       empresa (recruiter-company-profile-job-organization), cidade
       (div.location), data DD.MM.YYYY.
  B2. Dedup por slug entre paginas (offsets repetem).
  B3. Pager: href /jobs?page=N (RELATIVO — 1..7 no probe); ?page=1 =
       SEGUNDA pagina fisica (next aponta page=1); p1 = URL base.
  B4. item sem empresa -> fallback BME_COMPANY ("BME JobSource").

GRUPO C — Detail (JSON-LD JobPosting, VERBATIM do probe 13/10):
  C1. title/description(HTML->texto)/jobLocation(localidade, regiao,
       pais)/datePosted/validThrough/employmentType/hiringOrganization.
  C2. Detail falho (sem JSON-LD) -> vaga da listagem preservada SEM
       description (fail-soft TU Berlin).
  C3. Bloco ld+json sem @type JobPosting (WebSite/Organization) ->
       ignorado; nenhum JobPosting -> None.

GRUPO D — fetch_bme integração (fixtures, zero HTTP):
  D1. Fluxo completo: challenge -> echo -> listagem -> pages -> details;
      stats {rows_seen, pages, challenge, jobs, details_ok}.
  D2. Crawl-delay 10s ANTES de cada request ao dominio (robots) —
      gate incluso: n requests = n esperas (sleep injetado conta).
  D3. NENHUM prefilter de titulo na fonte: targets = PRIMEIROS
      max_details da listagem (regra da card: o funil de tipo resolve).
  D4. max_pages cap respeitado; falha de pagina individual nao derruba.
  D5. Vaga "Praktikant Einkauf - Procurement Solutions" (Dr. Oetker,
      fixture VERBATIM) -> internship=True via is_student_role; id
      estavel <company>|bme:<slug>; country_iso='de'.

GRUPO E — Fail-soft do estagio (collect_research_sources):
  E1. fetcher morto -> [] + status failed; run nao derruba; OUTRAS
      fontes entregam; summary parcial.
  E2. Kill switch: INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF=bme ->
      bme skipped_disabled; MPG roda (off-switch SEM deploy).
  E3. Nome desconhecido no CSV -> ignorado (sem crash).
  E4. bme presente em RESEARCH_SOURCE_ORDER (fonte registrada).

GRUPO F — Idempotência + parse puro:
  F1. Mesma listagem parseada 2x -> items identicos campo a campo.
  F2. parse_bme_date: 'DD.MM.YYYY' -> datetime; lixo -> None.
  F3. Listing sem <article> (pagina Bot Check / lambda) -> [] (o caso
      do run 6 do attempt 1: redirect SEGUIDO devolvia a pagina Bot
      Check; o parser novo nunca a confunde com listagem).

Uso:  .venv/bin/python scripts/test_f31.py
"""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(cond), detail))
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM dos probes ao vivo (13/10/2026) — suíte 100% offline.
# Salvos durante o recon da fase em /tmp/if-f31-recon (janela 07:04–07:47 UTC):
# jobs_cookie.html (listagem 200, 145KB), detail2.html (detail Dr. Oetker),
# h_detail.txt (302 com Location do challenge).
# Trechos reduzidos ao MINIMO que exercita cada regex (padrao test_f21).
# ---------------------------------------------------------------------------

# Location VERBATIM do header do 302 (h_detail.txt, probe 13/10 06:54 UTC).
BME_LOCATION_302 = (
    "https://jobsource.bme.de/botchallenge.html"
    "?token=6c0cb2078e54916f60b3389b16f70ad2"
    "&target=%2Fjob%2Fpraktikant-m-w-d-einkauf-procurement-solutions-0&referrer="
)

# Um <article> VERBATIM da listagem 200 (jobs_cookie.html, probe 07:07 UTC) —
# vaga Bereichsleiter*in Serviceprozesse und IT-Beschaffung (Deutsche
# Rentenversicherung, Würzburg, 12.10.2026). Logo/picture de 2KB cortado
# (o regex da anchor nao depende dele; caso do run 6: parser nao casava).
BME_ARTICLE_HTML = """<article id="node-4782"  about="/job/bereichsleiterin-serviceprozesse-und-it-beschaffung" typeof="sioc:Item foaf:Document" class="node node--job-per-file node-teaser no-logo node-job node--teaser node--job-per-file--teaser">
  <div class="job__logo">
          <a href="https://jobsource.bme.de/job/bereichsleiterin-serviceprozesse-und-it-beschaffung" class="recruiter-job-link" title="Bereichsleiter*in Serviceprozesse und IT-Beschaffung">
        <picture  title="Bereichsleiter*in Serviceprozesse und IT-Beschaffung">
        </picture></a>
  </div>
  <div class="job__content">
    <h3><a href="https://jobsource.bme.de/job/bereichsleiterin-serviceprozesse-und-it-beschaffung" class="recruiter-job-link" title="Bereichsleiter*in Serviceprozesse und IT-Beschaffung">Bereichsleiter*in Serviceprozesse und IT-Beschaffung</a></h3>
    <span class="recruiter-company-profile-job-organization">Deutsche Rentenversicherung</span>
    <div class="location"><span>Würzburg</span></div>
    <span class="date">12.10.2026</span>
  </div>
</article>"""

# Pager VERBATIM do rodape da listagem (jobs_cookie.html): ?page=1..7 +
# next apontando page=1 (= segunda pagina fisica; p1 = URL base).
BME_PAGER_HTML = """<nav class="pager" role="navigation" aria-labelledby="pagination-heading">
<ul class="pager__items">
  <li class="pager__item is-active"><a href="/jobs?page=0">1</a></li>
  <li class="pager__item"><a href="/jobs?page=1">2</a></li>
  <li class="pager__item"><a href="/jobs?page=2">3</a></li>
</ul>
<li class="pager__item pager__item--next"><a href="/jobs?page=1">weiter</a></li>
</nav>"""

# Detail VERBATIM: JSON-LD JobPosting do Praktikant Dr. Oetker (probe 13/10
# 07:12 UTC, detail2.html; o JobPosting e o 3o bloco ld+json da pagina —
# WebSite/Organization vêm antes e DEVEM ser ignorados).
BME_DETAIL_HTML = """<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"BME JobSource"}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"BME"}</script>
<script type="application/ld+json">{"@context":"http://schema.org","@type":"JobPosting","title":"Praktikant (m/w/d) Einkauf - Procurement Solutions","datePosted":"2026-10-07","validThrough":"2026-10-18","hiringOrganization":{"@type":"Organization","name":"Dr. Oetker"},"employmentType":["FULL_TIME"],"jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress","addressCountry":"DE","addressLocality":"Bielefeld","addressRegion":"Nordrhein-Westfalen"}}],"directApply":false,"description":"<p><strong>Int. Procurement Excellence - Solutions | Bielefeld | Startdatum: 01.01.2027 | Vollzeit | Befristet</strong></p>\\n<p>Wir suchen einen Praktikant (m/w/d) im Bereich Einkauf.</p>"}</script>"""

# Pagina "Bot Check" (jobs.html, 302 SEGUIDO pelo urllib do run 6) — o
# parser novo NUNCA deve extrair vagas daqui (F3).
BME_BOTCHECK_HTML = """<!DOCTYPE html>
<html lang="en"><head><title>Bot Check</title></head>
<body><div id="wrap"><h1>Verification Required</h1>
<button id="challengeBtn">I am human</button></div>
<script>const params = new URLSearchParams(location.search);
let token = params.get('token');
document.cookie = 'bot_verified=' + token + '; Max-Age=31536000';</script>
</body></html>"""


# Segundo <article> VERBATIM-esquecido: vaga REAL do board (probe 13/10) —
# Praktikant Dr. Oetker (slug real, mesmo JSON-LD do detail fixture abaixo).
BME_ARTICLE2_HTML = """<article id="node-4783"  about="/job/praktikant-m-w-d-einkauf-procurement-solutions-0" typeof="sioc:Item foaf:Document" class="node node--job-per-file node-teaser no-logo node-job node--teaser node--job-per-file--teaser">
  <div class="job__content">
    <h3><a href="https://jobsource.bme.de/job/praktikant-m-w-d-einkauf-procurement-solutions-0" class="recruiter-job-link" title="Praktikant (m/w/d) Einkauf - Procurement Solutions">Praktikant (m/w/d) Einkauf - Procurement Solutions</a></h3>
    <span class="recruiter-company-profile-job-organization">Dr. Oetker</span>
    <div class="location"><span>Bielefeld</span></div>
    <span class="date">07.10.2026</span>
  </div>
</article>"""


def _fetcher_dead(**kw):  # noqa: ARG001
    raise RuntimeError("fonte fora do ar")


def test_gate() -> None:
    print("== A. Gate anti-bot SEM browser ==")
    import sys
    sys.path.insert(0, "src")
    from internship_finder.research_sources import _bme_extract_gate_token

    # A1: Location do 302 real -> token extraido.
    tok = _bme_extract_gate_token(BME_LOCATION_302)
    check("A1. Location botchallenge?token= -> token hex extraido",
          tok == "6c0cb2078e54916f60b3389b16f70ad2", f"tok={tok}")
    # A2: Location sem botchallenge/token -> None.
    check("A2. Location sem challenge -> None (fail-soft)",
          _bme_extract_gate_token("https://jobsource.bme.de/other?x=1") is None
          and _bme_extract_gate_token(None) is None)
    # A3: gate de 1 round-trip: 302 -> cookie -> 200 (opener injetado).
    jobs, stats = _run_bme(challenge=True, max_details=0, max_pages=1)
    check("A3. challenge -> echo do token no cookie -> 200 listagem",
          stats["challenge"] is True and stats["rows_seen"] == 2
          and stats["status"] == "ok", f"stats={stats}")
    # A4: challenge sem token -> failed SEM crash.
    jobs, stats = _run_bme(challenge="no_token", max_details=0, max_pages=1)
    check("A4. challenge sem token -> failed 'sem challenge utilizavel'",
          stats["status"] == "failed" and jobs == []
          and "utili" in (stats["error"] or ""), f"stats={stats}")


def _run_bme(*, challenge: bool | str = False, max_details: int = 0,
             max_pages: int = 1, fail_pages: bool = False,
             fail_details: bool = False, sleep_fn=None):
    """fetch_bme com opener que simula o site real (fixtures VERBATIM).

    Listagem = 2 articles reais (Bereichsleiter + Praktikant Dr. Oetker) +
    pager. Detail por-slug: o slug do Praktikant devolve o JSON-LD VERBATIM;
    qualquer outro slug devolve pagina 404 sem JSON-LD (detail falho ->
    vaga preservada — mesmo fail-soft do TU Berlin).
    """
    import sys
    sys.path.insert(0, "src")
    from internship_finder import research_sources as rs

    listing = (BME_ARTICLE_HTML + "\n" + BME_ARTICLE2_HTML + "\n"
               + BME_PAGER_HTML)

    def opener(req):
        url = req.full_url
        cookie = req.get_header("Cookie")
        if cookie is None and challenge:
            if challenge == "no_token":
                raise urllib.error.HTTPError(
                    url, 302, "Found",
                    {"Location": "https://jobsource.bme.de/botchallenge.html"}, None)
            raise urllib.error.HTTPError(
                url, 302, "Found", {"Location": BME_LOCATION_302}, None)
        if fail_pages and "page=" in url:
            raise RuntimeError("pagina fora do ar")
        if "/job/" in url:
            if fail_details:
                raise RuntimeError("detail fora do ar")
            if url.rstrip("/").endswith("praktikant-m-w-d-einkauf-procurement-solutions-0"):
                return BME_DETAIL_HTML
            return "<html><body>404</body></html>"
        return listing

    kw = {}
    if sleep_fn is not None:
        kw["sleep"] = sleep_fn
    return rs.fetch_bme(opener=opener, sleep=kw.pop("sleep", lambda s: None),
                        max_details=max_details, max_pages=max_pages)


def test_listing() -> None:
    print("== B. Listagem Drupal server-rendered ==")
    import sys
    sys.path.insert(0, "src")
    from internship_finder.research_sources import (
        parse_bme_listing, parse_bme_pager, BME_COMPANY,
    )

    # B1: article VERBATIM -> item completo.
    items = parse_bme_listing(BME_ARTICLE_HTML)
    check("B1. article verbatim -> item {job_id,url,title,company,location,date}",
          len(items) == 1 and items[0]["job_id"] == "bereichsleiterin-serviceprozesse-und-it-beschaffung"
          and items[0]["company"] == "Deutsche Rentenversicherung"
          and items[0]["location"] == "Würzburg"
          and items[0]["date_str"] == "12.10.2026"
          and items[0]["title"] == "Bereichsleiter*in Serviceprozesse und IT-Beschaffung",
          f"items={items}")
    # B2: dedup por slug (mesma vaga em 2 paginas -> 1).
    dup = parse_bme_listing(BME_ARTICLE_HTML + BME_ARTICLE_HTML)
    check("B2. dedup por slug entre paginas", len(dup) == 1)
    # B3: pager relativo ?page=N -> [0,1,2]; next=page=1 é 2a física.
    pages = parse_bme_pager(BME_PAGER_HTML)
    check("B3. pager href RELATIVO /jobs?page=N parseado", pages == [0, 1, 2], f"pages={pages}")
    # B4: item sem org -> fallback BME_COMPANY.
    no_org = parse_bme_listing(
        BME_ARTICLE_HTML.replace(
            '<span class="recruiter-company-profile-job-organization">Deutsche Rentenversicherung</span>', ""))
    check("B4. item sem organizacao -> fallback BME JobSource",
          no_org and no_org[0]["company"] == BME_COMPANY, f"no_org={no_org}")
    # F3 (aqui, mesmo grupo): pagina Bot Check NUNCA produz vagas —
    # o bug do run 6 do attempt 1 (redirect seguido -> Bot Check page).
    check("B5. pagina Bot Check -> [] (nunca vaga; bug do attempt 1)",
          parse_bme_listing(BME_BOTCHECK_HTML) == [])


def test_detail() -> None:
    print("== C. Detail JSON-LD JobPosting ==")
    import sys
    sys.path.insert(0, "src")
    from internship_finder.research_sources import parse_bme_detail

    d = parse_bme_detail(BME_DETAIL_HTML, fallback_title="fallback")
    check("C1. JobPosting: title/org/loc/dates/employmentType/description",
          d is not None and d["title"] == "Praktikant (m/w/d) Einkauf - Procurement Solutions"
          and d["company"] == "Dr. Oetker"
          and d["location"] == "Bielefeld, Nordrhein-Westfalen, DE"
          and d["country_name"] == "DE"
          and d["employment_type"] == "FULL_TIME"
          and d["date_posted"] == datetime(2026, 10, 7)
          and d["valid_through"] == datetime(2026, 10, 18)
          and "Einkauf" in (d["description"] or ""),
          f"d={d}")
    # C2: sem JobPosting (so WebSite/Organization) -> None.
    check("C2. ld+json sem JobPosting -> None",
          parse_bme_detail(BME_DETAIL_HTML.split('<script type="application/ld+json">{"@context":"http://schema.org","@type":"JobPosting"')[0]) is None)
    # C3: HTML de detail sem JSON-LD (404/lambda) -> None (fail-soft).
    check("C3. detail sem ld+json -> None", parse_bme_detail("<html>404</html>") is None)


def test_fetch() -> None:
    print("== D. fetch_bme integração (fixtures, zero HTTP) ==")
    import sys
    sys.path.insert(0, "src")
    from internship_finder import research_sources as rs

    # D1: fluxo completo: TODA a listagem materializada (2 vagas), 1 detail
    # (o Praktikant intern-first escolhido; Bereichsleiter fica SEM detail).
    jobs, stats = _run_bme(challenge=True, max_details=1, max_pages=1)
    check("D1. TODA listagem materializada; detail vai pro intern-first",
          stats["status"] == "ok" and stats["rows_seen"] == 2
          and stats["challenge"] is True and stats["jobs"] == 2
          and stats["details_ok"] == 1 and stats["details_failed"] == 0
          and stats["error"] is None,
          f"stats={stats}")
    # D5: vaga Dr. Oetker VERBATIM -> internship True, id estavel, DE.
    oetker = [j for j in jobs if j.company == "Dr. Oetker"]
    bereich = [j for j in jobs if j.company == "Deutsche Rentenversicherung"]
    check("D5. Praktikant Dr. Oetker -> internship=True, id=<company>|bme:<slug>, iso=de",
          len(oetker) == 1 and oetker[0].internship is True
          and oetker[0].id == "Dr. Oetker|bme:praktikant-m-w-d-einkauf-procurement-solutions-0"
          and oetker[0].country_iso == "de"
          and oetker[0].url == "https://jobsource.bme.de/job/praktikant-m-w-d-einkauf-procurement-solutions-0"
          and oetker[0].description is not None,
          f"jobs={[(j.id, j.internship, bool(j.description)) for j in jobs]}")
    check("D7. nao-estagio materializado SEM detail (sem prefilter na fonte)",
          len(bereich) == 1 and bereich[0].description is None
          and bereich[0].internship is False,
          f"bereich={[(j.id, j.internship, bool(j.description)) for j in bereich]}")
    # D2: Crawl-delay ANTES de cada request ao dominio (gate incluso) —
    # fluxo com challenge, 2 paginas, 2 details (intern-first: Praktikant
    # primeiro + Bereichsleiter): [challenge, listagem, page=1, d, d]
    # = 5 requests = 5 esperas de 10s (robots Crawl-delay: 10).
    sleeps: list[float] = []

    def counting_sleep(s: float) -> None:
        sleeps.append(s)

    jobs, stats = _run_bme(challenge=True, max_details=2, max_pages=2,
                           sleep_fn=counting_sleep)
    check("D2. Crawl-delay 10s antes de CADA request (robots; gate incluso)",
          len(sleeps) == 5 and all(s == 10.0 for s in sleeps),
          f"sleeps={sleeps}")
    # D3: SEM prefilter que descarte na fonte: max_details=0 -> NENHUM
    # detail, mas TODA a listagem (2 vagas) continua materializada.
    jobs, stats = _run_bme(challenge=True, max_details=0, max_pages=1)
    check("D3. max_details=0 -> 0 details, listagem inteira materializada",
          stats["jobs"] == 2 and stats["details_ok"] == 0
          and {j.title.split()[0] for j in jobs} == {"Bereichsleiter*in", "Praktikant"},
          f"stats={stats}")
    # D4: pagina fora do ar nao derruba (fail-soft por pagina).
    jobs, stats = _run_bme(challenge=True, max_details=0, max_pages=2,
                           fail_pages=True)
    check("D4. falha de pagina individual -> run segue (fail-soft)",
          stats["status"] == "ok" and stats["rows_seen"] == 2
          and stats["pages"] == 2,
          f"stats={stats}")
    # D6: detail fora do ar -> vaga preservada sem description (fail-soft;
    # listagem inteira continua entrando).
    jobs, stats = _run_bme(challenge=True, max_details=1, max_pages=1,
                           fail_details=True)
    check("D6. detail falho -> vaga preservada SEM description",
          stats["details_failed"] == 1 and len(jobs) == 2
          and all(j.description is None for j in jobs),
          f"stats={stats} desc={[bool(j.description) for j in jobs]}")


def test_stage() -> None:
    print("== E. Estágio collect_research_sources ==")
    import sys
    sys.path.insert(0, "src")
    from internship_finder import research_sources as rs

    # E1: fetcher morto -> failed no summary; run segue.
    jobs, summary = rs.collect_research_sources(
        fetchers={
            "mpg_rss": lambda **kw: ([], {"source": "mpg_rss", "status": "ok", "jobs": 0}),
            "bme": lambda **kw: _fetcher_dead(),
        },
        env={},
    )
    bme_entry = summary["sources"]["bme"]
    check("E1. fetcher morto -> failed; run NAO derruba",
          bme_entry["status"] == "failed" and summary["status"] == "partial",
          f"summary={summary['status']} bme={bme_entry}")
    # E2: kill switch SEM deploy: bme desligada, mpg roda.
    jobs, summary = rs.collect_research_sources(
        fetchers={
            "mpg_rss": lambda **kw: ([], {"source": "mpg_rss", "status": "ok", "jobs": 3}),
            "bme": lambda **kw: ([], {"source": "bme", "status": "ok", "jobs": 0}),
        },
        env={"INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF": "bme"},
    )
    check("E2. off-switch env: bme skipped_disabled, mpg_rss roda",
          summary["sources"]["bme"]["status"] == "skipped_disabled"
          and summary["sources"]["mpg_rss"]["status"] == "ok",
          f"sources={summary['sources']}")
    # E3: nome desconhecido -> ignorado sem crash.
    jobs, summary = rs.collect_research_sources(
        fetchers={"bme": lambda **kw: ([], {"source": "bme", "status": "ok", "jobs": 1})},
        env={"INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF": "fonte_inexistente"},
    )
    check("E3. nome desconhecido no CSV -> ignorado (sem crash)",
          summary["sources"]["bme"]["status"] == "ok"
          and summary["sources"]["bme"]["jobs"] == 1,
          f"sources={summary['sources']}")
    # E4: bme registrada na ordem do estagio.
    check("E4. bme em RESEARCH_SOURCE_ORDER (7a fonte)",
          any(n == "bme" for n, _ in rs.RESEARCH_SOURCE_ORDER))


def test_idempotency() -> None:
    print("== F. Idempotência + parse puro ==")
    import sys
    sys.path.insert(0, "src")
    from internship_finder.research_sources import (
        parse_bme_date, parse_bme_listing,
    )

    a = parse_bme_listing(BME_ARTICLE_HTML + BME_PAGER_HTML)
    b = parse_bme_listing(BME_ARTICLE_HTML + BME_PAGER_HTML)
    check("F1. listagem parseada 2x -> identica campo a campo", a == b)
    check("F2. parse_bme_date: DD.MM.YYYY -> datetime; lixo -> None",
          parse_bme_date("07.10.2026") == datetime(2026, 10, 7)
          and parse_bme_date("lixo") is None
          and parse_bme_date("") is None)


def test_zero_http() -> None:
    print("== G. ZERO HTTP na suíte (padrão test_f15 T5 / F21 H4) ==")
    calls: list[str] = []

    def _fail_open(req, *a, **kw):
        calls.append(f"urlopen:{req.full_url}")
        raise AssertionError("HTTP BLOQUEADO na suíte F31")

    import socket

    orig_connect = socket.socket.connect

    def _fail_connect(self, address):
        calls.append(f"socket:{address}")
        raise AssertionError("SOCKET BLOQUEADO na suíte F31")

    urllib.request.urlopen = _fail_open  # type: ignore[assignment]
    socket.socket.connect = _fail_connect  # type: ignore[method-assign]
    try:
        import sys
        sys.path.insert(0, "src")
        from internship_finder import research_sources as rs

        def dead_opener(req):
            raise RuntimeError("opener morto — fonte fora do ar")

        # O opener injetado nunca toca urlopen; se QUALQUER caminho do
        # fetch_bme resolver para urllib real, o guard derruba.
        rs.fetch_bme(opener=dead_opener, sleep=lambda s: None)
        check("G1. fetch_bme inteiro sem socket externo", calls == [],
              f"calls={calls[:3]}")
    finally:
        urllib.request.urlopen = orig_open  # type: ignore[assignment]
        socket.socket.connect = orig_connect  # type: ignore[method-assign]


orig_open = urllib.request.urlopen


def main() -> int:
    print("== F31: BME JobSource — adapter + gate sem browser + Crawl-delay ==")
    test_gate()
    test_listing()
    test_detail()
    test_fetch()
    test_stage()
    test_idempotency()
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
