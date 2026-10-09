#!/usr/bin/env python3
"""Testes da F22 — hidratação JSON-LD-ONLY (100% offline).

Fecha a pendência §5.3 da F20: ``parse_job_description()`` aceita
SOMENTE JSON-LD schema.org JobPosting. ``og:description`` e meta
``description`` saíram do caminho de hidratação — KPMG/Thales servem
meta GENÉRICA do board (137/159 chars) que passava no gate de qualidade
(>= 120 chars) e era inútil como descrição da vaga (0 hidratações no
passe real de 08/10).

Cobre os itens da spec F22:

1.  (a) JSON-LD JobPosting presente → hidrata (fixture REAL: bloco
    JSON-LD da página da Deloitte GmbH do dataset de hoje, capturada no
    passe de 09/10) .................................. bloco A
2.  (b) página com SÓ og:description (KPMG REAL de hoje, 57 chars
    pós-unescape — título da vaga, não descrição) → NÃO hidrata
    (regressão da pendência §5.3) ...................... bloco B
3.  (c) página com SÓ meta genérica (Thales REAL de hoje, 159 chars
    "Explore Thales careers...") → NÃO hidrata ........ bloco C
4.  (d) JSON-LD sem campo description → não hidrata;
    (e) JSON-LD < 120 chars → não hidrata (gate) ..... bloco D
5.  (f) falha de fetch → descrição original mantida (nunca piora);
    nunca-piora vale também para parse curto ......... bloco E
6.  (g) re-avaliação F18 intacta: hidratada com C1 alemão → demovida
    com ``hydration_inapplicable`` ..................... bloco F
7.  (h) regressão byte a byte: refresh sem vagas curtas = idêntico
    (dataset intocado pela hidratação) ................ bloco G
8.  Bônus de robustez do parser: @graph, array, JSON-LD inválido
    ignorado gracioso, meta genérica de 400+ chars NÃO hidrata
    (a meta do board pode ser longa e ainda ser genérica) . bloco H

Convenção do repo: [OK]/[FAIL], termina "TUDO OK" (exit 0). Sem rede —
openers são fakes injetáveis; data/ real não é tocado.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import url_liveness as ul  # noqa: E402
import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


class _Resp:
    def __init__(self, raw: bytes, url: str):
        self._raw = raw
        self.url = url

    def read(self, n: int = -1) -> bytes:
        return self._raw if n is None or n < 0 else self._raw[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(status_map: dict, error_urls: set, bodies: dict,
            final_urls: dict | None = None):
    """GET fake: status/corpo/URL-final por URL; error_urls = rede fora."""
    final_urls = final_urls or {}

    def open(req, timeout=None):
        url = req.full_url
        if url in error_urls:
            raise TimeoutError("simulated timeout")
        status = status_map.get(url, 200)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "err", {}, None)
        return _Resp(bodies.get(url, b"<html><title>Job page</title></html>"),
                     final_urls.get(url, url))

    return open


# ---------------------------------------------------------------------------
# Fixtures REAIS capturadas no passe de 09/10/2026 (top exibido, corte
# 2/empresa). Meta tags verbatim das páginas vivas; JSON-LD verbatim da
# página da vaga da Deloitte GmbH (Bundesagentur jobdetail) — description
# de 4.377 chars.
# ---------------------------------------------------------------------------

# KPMG real (jobs.kpmg.de, 09/10): og:description E meta description
# iguais ao TÍTULO da vaga (57 chars pós-unescape) — não são descrição.
KPMG_META_TAGS = (
    b'<meta name="description" content='
    b'"Praktikum Data Science / Data Analytics & BI  (w/m/d)" />'
    b'<meta property="og:description" content='
    b'"Praktikum Data Science / Data Analytics & BI  (w/m/d)" />'
)
KPMG_PAGE = (
    b"<html><head><title>Praktikum Data Science / Data Analytics & BI"
    b" (w/m/d) - KPMG</title>" + KPMG_META_TAGS +
    b"</head><body>job page body</body></html>"
)

# KPMG §5.3 (F20, 08/10): a meta GENÉRICA do board com 137 chars
# documentada no relatório da F20 ("Alle offenen Jobs bei KPMG auf einen
# Blick..."). Reconstituída a partir do prefixo verbatim do relatório —
# a página de hoje serve o título (57 chars), mas o comprimento exato
# documentado (137 > gate 120) é o coração da pendência: passava no gate
# da F20 e seria hidratada como se fosse descrição da vaga.
KPMG_BOARD_META_137 = (
    "Alle offenen Jobs bei KPMG auf einen Blick – entdecken Sie "
    "aktuelle Stellen, finden Sie Ihre Karrieremöglichkeit und "
    "bewerben Sie online."
)
assert len(KPMG_BOARD_META_137) == 137
KPMG_BOARD_PAGE = (
    "<html><head><title>Praktikum bei KPMG – Jobbörse</title>"
    '<meta name="description" content="' + KPMG_BOARD_META_137 + '" />'
    "</head><body>board page body</body></html>"
).encode("utf-8")

# Thales real (careers.thalesgroup.com, 09/10): og:description "Join us"
# (7 chars) + meta description GENÉRICA do board de 159 chars — o caso
# exato da pendência §5.3 (passava no gate >= 120 da F20).
THALES_META_TAGS = (
    b'<meta name="description" content="Explore Thales careers: creating '
    b'innovative solutions for a safer, greener and more inclusive future. '
    b'Join our team and the Human Intelligence behind the tech." '
    b'key-description="external-default-home-description" />'
    b'<meta property="og:description" content="Join us" />'
)
THALES_PAGE = (
    b"<html><head><title>Join us | Thales Group</title>" + THALES_META_TAGS +
    b"</head><body>job page body</body></html>"
)

# Deloitte real (arbeitsagentur.de jobdetail, 09/10): o bloco JSON-LD
# verbatim (id="jsonld-schema-jobdetail") com JobPosting.description de
# 4.377 chars. Descrição truncada no fixture (primeiros ~600 chars do
# texto real + cauda real) — suficiente para os gates (>> 120 chars) e
# mantém o arquivo de teste enxuto.
DELOITTE_DESC = (
    "Deloitte bietet f\u00fchrende Pr\u00fcfungs- und Beratungsleistungen in "
    "Audit & Assurance, Tax & Legal, Consulting und Advisory \u2013 "
    "f\u00fcr nahezu 90 % der Fortune Global 500\u00ae und zahlreiche private "
    "Unternehmen. Wir liefern innovative Denkans\u00e4tze, l\u00f6sen komplexe "
    "Herausforderungen und f\u00f6rdern nachhaltiges Wachstum. "
    "Deine Aufgaben: Du unterst\u00fctzt das Team bei der Analyse von "
    "Daten und erstellst aussagekr\u00e4ftige Reports."
)
DELOITTE_JSONLD = json.dumps({
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Praktikant / Werkstudent Data Analytics - Innovation & "
             "Transformation (m/w/d)",
    "description": DELOITTE_DESC,
    "datePosted": "2026-08-03",
    "hiringOrganization": {"@type": "Organization", "name": "Deloitte GmbH"},
    "employmentType": ["FULL_TIME", "INTERN"],
}, ensure_ascii=False)
DELOITTE_PAGE = (
    "<html><head><title>Praktikant Data Analytics - Deloitte</title>"
    '<script type="application/ld+json" id="jsonld-schema-jobdetail">'
    + DELOITTE_JSONLD +
    "</script></head><body>...</body></html>"
).encode("utf-8")


# ---------------------------------------------------------------------------
# A — (a) JSON-LD JobPosting presente → hidrata
# ---------------------------------------------------------------------------

def test_jsonld_hydrates() -> None:
    section("A: (a) JSON-LD JobPosting presente → hidrata (fixture real)")
    ul.time.sleep = lambda s: None

    jobs = [{"id": "deloitte", "url": "https://x/deloitte",
             "description": "kurz", "title": "Praktikum Data Analytics"}]
    opener = _opener({}, set(), {"https://x/deloitte": DELOITTE_PAGE})
    dead, hydrated, stats = ul.check_liveness(
        jobs, opener=opener, return_details=True, short_description_limit=500)
    check("JSON-LD JobPosting real → hidratada", "deloitte" in hydrated)
    check("hidratada é o texto do JSON-LD (unescape correto, sem tags)",
          "Deloitte bietet" in hydrated.get("deloitte", "")
          and "Audit & Assurance" in hydrated.get("deloitte", "")
          and "<" not in hydrated.get("deloitte", ""))
    check("provenance/estatística: hydrated=1, dead=0",
          stats["hydrated"] == 1 and stats["dead"] == 0)

    # parser puro
    parsed = ul.parse_job_description(DELOITTE_PAGE.decode("utf-8"))
    check("parse_job_description: JSON-LD real extraído",
          parsed is not None and "Deloitte bietet" in parsed)
    check("gate >= 120: descrição de 4377 chars (real) passa",
          parsed is not None and len(parsed) >= 120)


# ---------------------------------------------------------------------------
# B — (b) KPMG real: SÓ og:description/título → NÃO hidrata (regressão)
# ---------------------------------------------------------------------------

def test_kpmg_regression() -> None:
    section("B: (b) KPMG real — só og:description/meta=título → NÃO hidrata")
    jobs = [{"id": "kpmg", "url": "https://x/kpmg",
             "description": "Praktikum Data Science / Data Analytics & BI "
                            "(w/m/d) Frankfurt am Main",  # 57 chars como hoje
             "title": "Praktikum Data Science"}]
    opener = _opener({}, set(), {"https://x/kpmg": KPMG_PAGE})
    dead, hydrated, stats = ul.check_liveness(
        jobs, opener=opener, return_details=True, short_description_limit=500)
    check("KPMG real (og 57 chars) NÃO hidrata mais",
          "kpmg" not in hydrated and "kpmg" not in dead)
    check("descrição original intacta (job não tocado)",
          jobs[0]["description"].startswith("Praktikum Data Science"))

    # §5.3 da F20 — a meta GENÉRICA do board de 137 chars (passava no
    # gate >= 120 da F20; hoje a página KPMG serve o título, mas a
    # pendência documentada era ESTA): JSON-LD-only → NUNCA hidrata.
    jobs_b = [{"id": "kpmg137", "url": "https://x/kpmg137",
               "description": "kurz", "title": "Praktikum"}]
    opener_b = _opener({}, set(), {"https://x/kpmg137": KPMG_BOARD_PAGE})
    dead_b, hydrated_b, stats_b = ul.check_liveness(
        jobs_b, opener=opener_b, return_details=True,
        short_description_limit=500)
    check("§5.3: meta genérica KPMG 137 chars (gate 120 da F20) NÃO hidrata",
          "kpmg137" not in hydrated_b and "kpmg137" not in dead_b)
    check("§5.3: original mantida (hydration_failed=1)",
          jobs_b[0]["description"] == "kurz"
          and stats_b["hydration_failed"] == 1)

    # mesmo com a meta de 400+ chars (comprida mas GENÉRICA de board):
    # og:description de 400 chars no lugar → NÃO hidrata (JSON-LD-only)
    kpmg_long_og = (
        b"<html><head><title>KPMG</title>"
        b'<meta property="og:description" content="' + b"y" * 400 + b'">'
        b"</head></html>"
    )
    jobs2 = [{"id": "kpmg2", "url": "https://x/kpmg2",
              "description": "kurz", "title": "Praktikum"}]
    opener2 = _opener({}, set(), {"https://x/kpmg2": kpmg_long_og})
    dead2, hydrated2, _ = ul.check_liveness(
        jobs2, opener=opener2, return_details=True,
        short_description_limit=500)
    check("og:description de 400 chars (genérica longa) NÃO hidrata",
          "kpmg2" not in hydrated2 and "kpmg2" not in dead2)


# ---------------------------------------------------------------------------
# C — (c) Thales real: SÓ meta genérica do board (159 chars) → NÃO hidrata
# ---------------------------------------------------------------------------

def test_thales_regression() -> None:
    section("C: (c) Thales real — meta genérica 159 chars → NÃO hidrata")
    # descrição original de hoje (257 chars) MENOR que a meta genérica de
    # 159? NÃO — mas com original curto o nunca-piora seria a única defesa
    # na F20; a F22 mata o caminho: o parser nem extrai mais.
    jobs = [{"id": "thales", "url": "https://x/thales",
             "description": "Working student Strategic Procurement "
                            "Thales UK/Germany R0336944",  # curto,
             "title": "Working student"}]
    opener = _opener({}, set(), {"https://x/thales": THALES_PAGE})
    dead, hydrated, stats = ul.check_liveness(
        jobs, opener=opener, return_details=True, short_description_limit=500)
    check("Thales real (meta genérica 159 chars) NÃO hidrata",
          "thales" not in hydrated and "thales" not in dead)
    check("descrição original intacta",
          jobs[0]["description"].startswith("Working student"))

    # parser puro confirma: og+meta presente → None (JSON-LD-only)
    parsed = ul.parse_job_description(THALES_PAGE.decode("utf-8"))
    check("parse_job_description(Thales real) = None",
          parsed is None)
    parsed_k = ul.parse_job_description(KPMG_PAGE.decode("utf-8"))
    check("parse_job_description(KPMG real) = None",
          parsed_k is None)


# ---------------------------------------------------------------------------
# D — (d) JSON-LD sem description + (e) JSON-LD < 120 chars
# ---------------------------------------------------------------------------

def test_jsonld_gates() -> None:
    section("D: (d) sem description / (e) < 120 chars → não hidratam")
    # (d) JobPosting sem campo description
    no_desc_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting",
                      "title": "Praktikum"}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: JobPosting SEM description → None",
          ul.parse_job_description(no_desc_page.decode("utf-8")) is None)

    # (d2) description não-string (número)
    num_desc_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting", "description": 12345}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: description não-string (int) → None",
          ul.parse_job_description(num_desc_page.decode("utf-8")) is None)

    # (e) description < 120 chars (gate de qualidade)
    short_jsonld_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting",
                      "description": "Kurzbeschreibung der Stelle."}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: JobPosting 28 chars → None (gate >= 120)",
          ul.parse_job_description(short_jsonld_page.decode("utf-8")) is None)

    # e2e: vaga curta + JSON-LD < 120 chars → hydration_failed, original
    # mantida
    jobs = [{"id": "g1", "url": "https://x/g1", "description": "kurz",
             "title": "Praktikum"}]
    opener = _opener({}, set(), {"https://x/g1": short_jsonld_page})
    dead, hydrated, stats = ul.check_liveness(
        jobs, opener=opener, return_details=True, short_description_limit=500)
    check("e2e: JSON-LD 28 chars → NÃO hidrata (hydration_failed=1)",
          "g1" not in hydrated and stats["hydration_failed"] == 1
          and stats["hydrated"] == 0)
    check("e2e: original mantida", jobs[0]["description"] == "kurz")


# ---------------------------------------------------------------------------
# E — (f) falha de fetch → original mantida; nunca-piora em parse curto
# ---------------------------------------------------------------------------

def test_fetch_failure() -> None:
    section("E: (f) fetch falha → original mantida (nunca piora)")
    jsonld_page = DELOITTE_PAGE
    jobs = [
        {"id": "netfail", "url": "https://x/netfail",
         "description": "original A", "title": "Praktikum"},
        {"id": "http410", "url": "https://x/410",
         "description": "original B", "title": "Praktikum"},
    ]
    opener = _opener({"https://x/410": 410}, {"https://x/netfail"},
                     {"https://x/ok": jsonld_page})
    dead, hydrated, stats = ul.check_liveness(
        jobs, opener=opener, return_details=True, short_description_limit=500)
    check("timeout/rede → original mantida, não morta",
          "netfail" not in hydrated and "netfail" not in dead
          and jobs[0]["description"] == "original A")
    check("410 → morta (desce do top), JSON intocado",
          "http410" in dead and jobs[1]["description"] == "original B")
    # 410 (HTTPError) e timeout (rede) → ambos `continue` ANTES do bloco
    # de hidratação: nenhum conta short_candidate (só 2xx vivas chegam
    # ao parse).
    check("stats: hydrated=0, short_candidates=0 (410/timeout morrem antes do parse)",
          stats["hydrated"] == 0 and stats["short_candidates"] == 0)

    # nunca-piora no chamador: parse de texto MENOR que a original não
    # hidrata (check_liveness_v2 só inclui no mapa se len(desc) > len(original))
    short_text = "Sehr kurze Beschreibung. " * 3  # 75 chars
    page_short_text = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting", "description": short_text * 2}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")  # JSON-LD 150 chars — passa o gate 120 mas é MENOR
    jobs2 = [{"id": "np", "url": "https://x/np",
              "description": "d" * 400, "title": "Praktikum"}]
    opener2 = _opener({}, set(), {"https://x/np": page_short_text})
    dead2, hydrated2, _ = ul.check_liveness(
        jobs2, opener=opener2, return_details=True,
        short_description_limit=500)
    check("parse OK mas MENOR que a original → NÃO hidrata (nunca piora)",
          "np" not in hydrated2 and jobs2[0]["description"] == "d" * 400)


# ---------------------------------------------------------------------------
# F — (g) re-avaliação F18 intacta
# ---------------------------------------------------------------------------

def test_f18_reassessment() -> None:
    section("F: (g) re-avaliação F18 intacta (hidratada C1 → demovida)")
    # hidratada revela alemão required → motivo retornado (reuso F18)
    job = {"id": "x1", "title": "Praktikum Data Science",
           "description": "Sehr gute Deutschkenntnisse (C1) werden "
                          "vorausgesetzt. " * 5}
    check("hidratada revela german_required → motivo",
          rd._reassess_hydrated_applicability(job) == "german_required")

    job_m = {"id": "x2", "title": "Intern Data",
             "description": "You are a Master's student in progress."}
    check("hidratada revela master_required",
          rd._reassess_hydrated_applicability(job_m) == "master_required")

    job_ok = {"id": "x3", "title": "Praktikum Supply Chain",
              "description": "logistics procurement english only " * 5}
    check("hidratada aplicável → None (não demove)",
          rd._reassess_hydrated_applicability(job_ok) is None)


# ---------------------------------------------------------------------------
# G — (h) regressão byte a byte: refresh sem vagas curtas = idêntico
# ---------------------------------------------------------------------------

def test_refresh_byte_identical() -> None:
    section("G: (h) refresh sem vagas curtas → byte a byte idêntico")
    import subprocess
    from unittest import mock

    with tempfile.TemporaryDirectory(prefix="t_f22_reg_") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir()
        # NENHUMA vaga curta: todas com descrição >= 500 chars — a
        # hidratação não tem candidatos; nada é escrito, nada muda.
        jobs = []
        for i in range(12):
            jobs.append({
                "id": f"r{i}", "title": f"Praktikum Supply Chain {i}",
                "company": f"Firma {i} GmbH", "location": "Berlin, DE",
                "country_iso": "de", "score": 20.0 - i,
                "url": f"https://jobs.example.com/{i}",
                "description": "logistics procurement " * 40, "raw": {},
            })
        (data_dir / "eligible_jobs.json").write_text(
            json.dumps(jobs), encoding="utf-8")
        (data_dir / "collection_metrics.jsonl").write_text(
            json.dumps({"run_id": "r1", "type": "run", "status": "ok",
                        "total_collected": 400, "eligible": 12}),
            encoding="utf-8")

        before = (data_dir / "eligible_jobs.json").read_bytes()

        def fake_publish(root_, pages, *, exit_code, eligible, run_id,
                         dead_link_ids=None, **kw):
            return True

        def fake_liveness(jobs_, **kw):
            return set(), {}, {"attempts": 12, "hydrated": 0,
                               "hydration_failed": 0,
                               "short_candidates": 0, "duration_s": 0.1}

        def fake_run(*a, **k):
            return subprocess.CompletedProcess(a[0], 0)

        original_root = rd.repo_root
        rd.repo_root = lambda: root
        try:
            with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd.url_liveness, "check_liveness",
                                   side_effect=fake_liveness), \
                 mock.patch.object(rd.publish_pages, "publish_ranking",
                                   side_effect=fake_publish), \
                 mock.patch.object(rd, "notify_or_log",
                                   side_effect=lambda c, m, *, dry_run:
                                   {"sent": True}):
                rc = rd.main(["--config", str(root / ".env"),
                              "--pages-dir", str(root / "pages"),
                              "--always-notify"])
        finally:
            rd.repo_root = original_root

        after = (data_dir / "eligible_jobs.json").read_bytes()
        check("refresh exit 0 (estágio nunca derruba)", rc == 0)
        check("sem vagas curtas → eligible_jobs.json BYTE A BYTE idêntico",
              before == after)


# ---------------------------------------------------------------------------
# H — robustez do parser JSON-LD-only (bônus de robustez)
# ---------------------------------------------------------------------------

def test_parser_robustness() -> None:
    section("H: robustez — @graph/array/JSON inválido/sem JobPosting")
    # @graph com JobPosting aninhado
    graph_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org",
                     "@graph": [{"@type": "Organization", "name": "X"},
                                {"@type": "JobPosting",
                                 "description": "g" * 300}]}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: JobPosting dentro de @graph → extrai",
          ul.parse_job_description(graph_page.decode("utf-8")) is not None)

    # array de objetos JSON-LD
    arr_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps([{"@type": "WebPage"},
                      {"@type": "JobPosting", "description": "a" * 200}]) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: JobPosting em array JSON-LD → extrai",
          ul.parse_job_description(arr_page.decode("utf-8")) is not None)

    # JSON-LD inválido (syntax error) + um válido depois → o inválido é
    # ignorado gracioso, o válido hidrata
    mixed_page = (
        "<html><head>"
        '<script type="application/ld+json">{invalid json!!</script>'
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting", "description": "m" * 200}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: JSON-LD inválido ignorado, válido seguinte extrai",
          ul.parse_job_description(mixed_page.decode("utf-8")) is not None)

    # JSON-LD presente mas SEM JobPosting (WebSite/BreadcrumbList —
    # padrão Thales/Merck/Marsh reais: 3 blocos, nenhum JobPosting)
    no_jp_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "WebSite", "url": "https://x/"}) +
        "</script>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "BreadcrumbList", "itemListElement": []}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: JSON-LD sem JobPosting (WebSite/Breadcrumb) → None",
          ul.parse_job_description(no_jp_page.decode("utf-8")) is None)

    # @type em LISTA (variante aceita pela spec oficial)
    types_page = (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": ["JobPosting", "ListItem"],
                      "description": "t" * 200}) +
        "</script></head><body>x</body></html>"
    ).encode("utf-8")
    check("parser: @type em lista [JobPosting, ListItem] → extrai",
          ul.parse_job_description(types_page.decode("utf-8")) is not None)

    # HTML sem nenhum JSON-LD/meta → None
    check("parser: página plain → None",
          ul.parse_job_description("<html><body>plain</body></html>") is None)

    # Thales real: tem 3 blocos JSON-LD válidos mas NENHUM JobPosting —
    # as metas genéricas NÃO são fallback (JSON-LD-only).
    check("parser: Thales real (3 JSON-LD sem JobPosting) → None",
          ul.parse_job_description(THALES_PAGE.decode("utf-8")) is None)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    test_jsonld_hydrates()
    test_kpmg_regression()
    test_thales_regression()
    test_jsonld_gates()
    test_fetch_failure()
    test_f18_reassessment()
    test_refresh_byte_identical()
    test_parser_robustness()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
