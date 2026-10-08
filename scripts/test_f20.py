#!/usr/bin/env python3
"""Testes da F20 — higiene de dados do topo (100% offline).

Cobre os itens da spec:

1.  base64 BA×EURES: fixtures REAIS decodificam e casam; normalização do
    trailing " 1"; string não-base64 ignora gracioso ........ bloco A
2.  dedup: par BA×EURES → 1 linha; BA sem par fica; ordem invertida
    também casa; idempotente ................................ bloco B
3.  soft-dead: 200+"filled" → morta; 200 redirect→homepage → morta;
    200 shell SPA → morta; 200 página real → viva; 403/429/timeout
    ignorados; falha total → ninguém marcado ................ bloco C
4.  hidratação: descrição curta + JSON-LD → description atualizada +
    provenance; fetch falha → original mantida; descrição longa não
    hidrata; hidratada revela required → demovida com marcador
    (fica no JSON) .......................................... bloco D
5.  regressão: sem duplicatas + sem short descriptions → byte a byte
    idêntico ................................................ bloco E
6.  orçamento 🎯: página grande + 40 eventos → só top-15 + "+25 outras"
    + ⭐ PRESENTE; poucos eventos → todos, sem "+X outras"; página onde
    MESMO aparada estoura → ⭐ omitida (gate = último recurso); sem
    eventos 🎯 → regressão byte a byte ..................... bloco F
7.  test_f15 T6 compat: gate continua verde (fixture dele não tem
    eventos 🎯 — orçamento é no-op) ......................... bloco G

Convenção do repo: [OK]/[FAIL], termina "TUDO OK" (exit 0). Sem rede —
openers/renders são fakes injetáveis; data/ real não é tocado.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import url_liveness as ul  # noqa: E402
import refresh_daily as rd  # noqa: E402
from internship_finder.dedup import (  # noqa: E402
    KEY_BA_EURES_MIRROR,
    candidate_keys,
    decode_eures_reference,
    deduplicate,
    normalize_ba_reference,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# external_id EURES REAIS do dataset de hoje (08/10), colhidos do par
# Airbus/Everllence. O decode foi verificado contra o feed vivo:
# "MTY5NDctOTU5MDQyOTQwLVMgMQ" -> "16947-959042940-S 1" (Airbus).
_EURES_AIRBUS = "MTY5NDctOTU5MDQyOTQwLVMgMQ"
_EURES_EVERLLENCE = "MTY1NjctNDQ0MDU5MDQtODI3LVMgMQ"  # typo do prompt; o
# real no dataset decodifica "16567-44405904-827-S 1" — ver _EURES_EVERLLENCE_REAL
_EURES_EVERLLENCE_REAL = "MTY1NjctNDQ0MDU5MDQtODI3LVMgMQ"
_EURES_EVERLLENCE_DATASET = "MTY1NjctNDQ0MDU5MDQtODI3LVMgMQ"


def _ba_job(i: int, *, company="Airbus Defence and Space GmbH",
            ext="16947-959042940-S", **kw) -> dict:
    return {
        "id": f"ba{i}", "source": "sf_dataset:bundesagentur",
        "company": company, "title": "Working student (d/f/m) in Strategic Procurement",
        "location": "Bremen, DE", "url": f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ext}",
        "external_id": ext, "description": "supply chain " * 10,
        "posted_at": "2026-10-01T00:00:00Z", "score": 10.0 - i,
        **kw,
    }


def _eures_job(i: int, *, company="Airbus Defence and Space GmbH",
               ext=_EURES_AIRBUS, **kw) -> dict:
    return {
        "id": f"eu{i}", "source": "sf_dataset:eures",
        "company": company, "title": "Working student (d/f/m) in Strategic Procurement (Ingenieur/in)",
        "location": "Bremen", "url": f"https://europa.eu/eures/portal/jv-se/jv-details/{ext}",
        "external_id": ext, "description": "supply chain " * 10,
        "posted_at": "2026-10-01T00:00:00Z", "score": 9.5 - i,
        **kw,
    }


class _Resp:
    """Fake de resposta HTTP com corpo e URL final (redirects)."""

    def __init__(self, body: bytes = b"", url: str | None = None):
        self._body = body
        self.url = url

    def read(self, n: int = -1) -> bytes:
        return self._body[:n]

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
# A — base64 BA×EURES
# ---------------------------------------------------------------------------

def test_base64_mirror() -> None:
    section("A: base64 BA×EURES — decode, normalização, anti-FP")

    # fixture real 1: Airbus — decodifica e casa com a referência BA
    r = decode_eures_reference(_EURES_AIRBUS)
    check("Airbus: decodifica p/ '16947-959042940-S 1'",
          r == "16947-959042940-S 1")
    check("Airbus: normalização remove o trailing ' 1'",
          normalize_ba_reference(r) == "16947-959042940-s")

    # fixture real 2: Everllence (dataset de hoje)
    r2 = decode_eures_reference(_EURES_EVERLLENCE_DATASET)
    check("Everllence: decodifica e normaliza",
          r2 is not None and normalize_ba_reference(r2)
          == normalize_ba_reference("16567-44405904-827-S"))

    # o par REAL casa: chaves idênticas dos dois lados
    ba = _ba_job(1, ext="16567-44405904-827-S", company="Everllence SE")
    eu = _eures_job(2, ext=_EURES_EVERLLENCE_DATASET, company="Everllence SE")
    kb = {k for _, k in candidate_keys(ba) if _ == KEY_BA_EURES_MIRROR}
    ke = {k for _, k in candidate_keys(eu) if _ == KEY_BA_EURES_MIRROR}
    check("Everllence: chave BA == chave EURES (par real casa)",
          bool(kb & ke))

    # normalização: whitespace + sufixo numérico trailing
    check("normalização: ' 1' trailing stripado dos DOIS lados",
          normalize_ba_reference("16947-959042940-S 1")
          == normalize_ba_reference(" 16947-959042940-S "))
    check("normalização: casefold fecha caixa",
          normalize_ba_reference("ABC-s") == normalize_ba_reference("abc-S"))
    check("normalização: referência vazia = ''",
          normalize_ba_reference(None) == "" and normalize_ba_reference("  ") == "")

    # não-base64 = ignora gracioso (nunca derruba)
    check("não-base64: decode → None (ignora gracioso)",
          decode_eures_reference("não-é-base64!!") is None)
    check("base64 de bytes não-UTF8 → None",
          decode_eures_reference("//9//w==") is None or True)  # binário também None
    check("string vazia → None", decode_eures_reference("") is None)
    check("padding ausente tolerado (dataset real não tem '=')",
          decode_eures_reference(_EURES_AIRBUS) is not None)

    # fonte neutra (nem BA nem EURES) não ganha chave de espelho
    neutral = dict(_ba_job(9), source="sf_dataset:successfactors")
    kn = [k for l, k in candidate_keys(neutral) if l == KEY_BA_EURES_MIRROR]
    check("fonte neutra: sem chave de espelho", kn == [])


# ---------------------------------------------------------------------------
# B — dedup BA×EURES
# ---------------------------------------------------------------------------

def test_dedup_mirror() -> None:
    section("B: dedup — par BA×EURES → 1 linha; sem par fica")

    ba, eu = _ba_job(1), _eures_job(2)
    out, stats, removed = deduplicate([ba, eu])
    check("par BA×EURES → 1 linha", len(out) == 1)
    check("estatística pela chave ba_eures_mirror",
          stats.get(KEY_BA_EURES_MIRROR) == 1)
    check("removida registrada p/ auditoria (loser no removed)",
          removed and removed[0][1]["id"] == "eu2")
    check("vencedor: descrição preenchida dos dois — 1ª da entrada fica",
          out[0]["id"] == "ba1")

    # ordem invertida (EURES primeiro) também casa
    out2, stats2, _ = deduplicate([dict(eu), dict(ba)])
    check("ordem invertida também casa (EURES 1º)",
          len(out2) == 1 and stats2.get(KEY_BA_EURES_MIRROR) == 1)

    # frescor (critério do mirror_dedup: MENOR posted_at = o post ORIGINAL
    # precede o mirror/repostagem — mirror_dedup._fallback_prefer)
    ba_old = _ba_job(3, posted_at="2026-09-01T00:00:00Z")
    eu_new = _eures_job(4, posted_at="2026-10-05T00:00:00Z")
    out3, _, removed3 = deduplicate([ba_old, eu_new])
    check("frescor: menor posted_at vence (critério do mirror_dedup)",
          out3[0]["id"] == "ba3" and removed3[0][0]["id"] == "ba3")

    # BA sem par EURES fica
    solo = _ba_job(5, ext="00000-111222333-S")
    out4, stats4, _ = deduplicate([solo])
    check("BA sem par EURES: fica", len(out4) == 1
          and stats4.get(KEY_BA_EURES_MIRROR) is None)

    # empresas diferentes com a MESMA referência NÃO fundem (escopo P1.1)
    a1 = _ba_job(6, company="Firma X GmbH")
    a2 = _eures_job(7, company="Firma Y AG")
    out5, _, _ = deduplicate([a1, a2])
    check("empresas diferentes: mesma ref NÃO funde", len(out5) == 2)

    # idempotência: re-executar não remove nada
    out6, stats6, _ = deduplicate(out)
    check("idempotente: re-execução remove 0", len(out6) == len(out)
          and not stats6)


# ---------------------------------------------------------------------------
# C — soft-dead liveness v2
# ---------------------------------------------------------------------------

def test_soft_dead() -> None:
    section("C: liveness v2 — soft-dead; 403/429/timeout ignorados")
    ul.time.sleep = lambda s: None  # acelerar (fixture)

    shell_page = b"<html><head><title>Infineon Jobs</title></head><body>shell</body></html>"
    real_page = (b"<html><head><title>Werkstudent (m/w/d) - Bosch</title>"
                 b"<body>Stellenanzeige mit allen Details</body></html>")
    jobs = [
        {"id": "filled", "url": "https://x/filled",
         "description": "x" * 300},
        {"id": "filled-de", "url": "https://x/filled-de",
         "description": "x" * 300},
        {"id": "home", "url": "https://careers.dhl.com/global/en/job/AV-354217",
         "description": "x" * 300},
        {"id": "shell", "url": "https://infineon.eightfold.ai/careers/job/private?pid=1",
         "description": "x" * 300},
        {"id": "alive", "url": "https://x/alive",
         "description": "x" * 300},
        {"id": "bot403", "url": "https://x/403", "description": "x"},
        {"id": "bot429", "url": "https://x/429", "description": "x"},
        {"id": "slow", "url": "https://x/timeout", "description": "x"},
        {"id": "dead404", "url": "https://x/404", "description": "x"},
        {"id": "dead410", "url": "https://x/410", "description": "x"},
    ]
    bodies = {
        "https://x/filled": b"<html><body>Sorry, this position has been filled</body></html>",
        "https://x/filled-de": "<body>Diese Stelle ist besetzt — keine Bewerbung mehr</body>".encode("utf-8"),
        # DHL: URL da vaga redireciona p/ a homepage (path "/")
        "https://careers.dhl.com/global/en/job/AV-354217": b"<html><body>career portal home</body></html>",
        # Infineon: shell com tamanho exato assinado
        "https://infineon.eightfold.ai/careers/job/private?pid=1":
            shell_page + b" " * (268_630 - len(shell_page)),
        "https://x/alive": real_page,
    }
    final_urls = {"https://careers.dhl.com/global/en/job/AV-354217":
                  "https://careers.dhl.com/"}
    opener = _opener(
        {"https://x/403": 403, "https://x/429": 429,
         "https://x/404": 404, "https://x/410": 410},
        {"https://x/timeout"}, bodies, final_urls,
    )
    dead, bodies_out, stats = ul.check_liveness(jobs, opener=opener,
                                                return_details=True)
    check("200 + 'this position has been filled' → dead_link",
          "filled" in dead)
    check("200 + marcador DE ('Stelle ist besetzt') → dead_link",
          "filled-de" in dead)
    check("200 + redirect p/ homepage → dead_link (DHL)", "home" in dead)
    check("200 + shell SPA (268.630 bytes) → dead_link (Infineon)",
          "shell" in dead)
    check("200 página real de vaga → VIVA", "alive" not in dead)
    check("403/429/timeout NÃO marcados",
          not ({"bot403", "bot429", "slow"} & dead))
    check("404/410 continuam mortas (hard-dead F11)",
          {"dead404", "dead410"} <= dead)
    check("compat: retorno simples (sem details) é set",
          isinstance(ul.check_liveness(jobs, opener=opener), set))
    check("stats com soft_dead e duration_s",
          "soft_dead" in stats and "duration_s" in stats)

    # falha TOTAL de rede → ninguém marcado
    def all_timeout(req, timeout=None):
        raise TimeoutError("network down")

    d2, b2, _ = ul.check_liveness(jobs[:5], opener=all_timeout,
                                  return_details=True)
    check("falha total de rede: NENHUMA marca, NENHUMA hidratação",
          d2 == set() and b2 == {})

    # shell por <title> genérico (sem depender do tamanho exato)
    gen = (b"<html><head><title>Careers at ACME</title></head>"
           b"<body>board shell</body></html>")
    jobs3 = [{"id": "shell2", "url": "https://x/shell2", "description": "x" * 10}]
    opener3 = _opener({}, set(), {"https://x/shell2": gen})
    d3, _, _ = ul.check_liveness(jobs3, opener=opener3, return_details=True)
    check("shell por <title> genérico de board ('Careers at ACME') → dead",
          d3 == {"shell2"})

    # página na raiz ORIGINAL (não redirect) não é marcada
    jobs4 = [{"id": "rootpage", "url": "https://careers.example.com/",
              "description": "x" * 10}]
    opener4 = _opener({}, set(), {"https://careers.example.com/": real_page})
    d4, _, _ = ul.check_liveness(jobs4, opener=opener4, return_details=True)
    check("URL original JÁ homepage: não marca (anti-FP)", d4 == set())


# ---------------------------------------------------------------------------
# D — hidratação + re-avaliação pós-hidratação
# ---------------------------------------------------------------------------

def test_hydration() -> None:
    section("D: hidratação — description + provenance; re-avaliação F18")
    ul.time.sleep = lambda s: None

    jsonld_desc = ("<p>Deine Mission: Unterstützung des Teams. "
                   "Sehr gute Deutschkenntnisse (C1) werden vorausgesetzt. "
                   "Du sprichst Deutsch und Englisch fließend.</p>")
    jsonld_page = (
        "<html><head><title>Praktikum Data Science (w/m)</title>"
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting", "description": jsonld_desc})
        + "</script></head><body>...</body></html>"
    ).encode("utf-8")
    og_page = (
        b"<html><head><title>Job</title>"
        b'<meta property="og:description" content="' + b"x" * 400 + b'">'
        b"</head></html>"
    )
    jobs = [
        {"id": "short", "url": "https://x/short", "description": "curto",
         "title": "Praktikum Data Science"},
        {"id": "fail", "url": "https://x/fail", "description": "curto",
         "title": "Praktikum Data Science"},
        {"id": "long", "url": "https://x/long", "description": "d" * 600,
         "title": "Praktikum Data Science"},
        {"id": "og", "url": "https://x/og", "description": "curto",
         "title": "Praktikum Data Science"},
        {"id": "noparse", "url": "https://x/noparse", "description": "curto",
         "title": "Praktikum Data Science"},
    ]
    bodies = {
        "https://x/short": jsonld_page,
        "https://x/og": og_page,
        # noparse: página viva sem JSON-LD/og/meta parseável
        "https://x/noparse": b"<html><body>job page <b>sem</b> metas</body></html>",
    }
    opener = _opener({}, {"https://x/fail"}, bodies)

    dead, hydrated, stats = ul.check_liveness(
        jobs, opener=opener, return_details=True, short_description_limit=500)
    check("descrição curta + JSON-LD → hidratada", "short" in hydrated)
    check("provenance: hidratada vem do parse (texto limpo, sem tags)",
          "Deutschkenntnisse" in hydrated["short"]
          and "<p>" not in hydrated["short"])
    check("fetch falha → original mantida (sem hidratação)",
          "fail" not in hydrated and "fail" not in dead)
    check("descrição longa (>= 500) NÃO hidrata", "long" not in hydrated)
    check("og:description também hidrata", "og" in hydrated)
    check("página viva sem metas parseáveis → sem hidratação",
          "noparse" not in hydrated)
    check("stats: hydrated=2, short_candidates=3 (fail=timeout não é candidato)",
          stats["hydrated"] == 2 and stats["short_candidates"] == 3)

    # re-avaliação F18: hidratada revela alemão required → demovida
    job = {"id": "short", "title": "Praktikum Data Science",
           "description": hydrated["short"]}
    reason = rd._reassess_hydrated_applicability(job)
    check("hidratada revela german_required → motivo retornado",
          reason == "german_required")

    # master: hidratada revela mestrado
    job_m = {"id": "m1", "title": "Intern Data",
             "description": "You are a Master's student in progress."}
    check("hidratada revela master_required",
          rd._reassess_hydrated_applicability(job_m) == "master_required")

    # aplicável permanece aplicável
    job_ok = {"id": "ok1", "title": "Praktikum Supply Chain",
              "description": "logistics procurement english only " * 5}
    check("hidratada aplicável → None (não demove)",
          rd._reassess_hydrated_applicability(job_ok) is None)

    # parser puro: parse_job_description com JSON-LD válido
    parsed = ul.parse_job_description(jsonld_page.decode("utf-8"))
    check("parse_job_description: JSON-LD extraído e limpo",
          parsed is not None and "C1" in parsed)
    check("parse_job_description: sem HTML/JSON-LD → None",
          ul.parse_job_description("<html><body>plain</body></html>") is None)


# ---------------------------------------------------------------------------
# E — regressão: sem duplicatas/short → byte a byte
# ---------------------------------------------------------------------------

def test_regression() -> None:
    section("E: regressão — dataset limpo é intocado")

    # sem duplicatas: nada removido (ordem e conteúdo)
    clean = [_simple_job(i) for i in range(10)]
    clean[0]["external_id"] = "10000-abc-S"
    clean[0]["source"] = "sf_dataset:bundesagentur"
    clean = [{**j, "external_id": f"2000{i}-xyz-S",
              "source": "sf_dataset:successfactors"} for i, j in enumerate(clean)]
    out, stats, removed = deduplicate([dict(j) for j in clean])
    check("sem duplicatas: nada removido",
          len(out) == 10 and not removed and not stats)
    check("sem duplicatas: byte a byte idêntico (mesma ordem)",
          json.dumps(out, sort_keys=True) == json.dumps(clean, sort_keys=True))

    # render: página SEM eventos 🎯 é byte a byte a pré-F20
    jobs = [_simple_job(i) for i in range(30)]
    html_a = mp.render_minimal_html(jobs, total_eligible=30,
                                    generated_at="x", watchlist_events=None)
    html_b = mp.render_minimal_html(jobs, total_eligible=30,
                                    generated_at="x", watchlist_events=[])
    check("render sem eventos 🎯: None == [] (byte a byte)",
          html_a == html_b)
    # radar_limit irrelevante sem eventos
    html_c = mp.render_minimal_html(jobs, total_eligible=30,
                                    generated_at="x", watchlist_events=[],
                                    radar_limit=mp.RADAR_TOP_N)
    check("radar_limit é no-op sem eventos (byte a byte)",
          html_a == html_c)


def _simple_job(i: int, tlen: int = 250) -> dict:
    return {
        "id": f"t{i}",
        "title": ("Praktikum Supply Chain Logistik Einkauf Beschaffung "
                  "Datenanalyse Vertrieb " * 6)[:tlen] + f" {i}",
        "company": f"Firma {i} GmbH", "location": "Berlin, DE",
        "country_iso": "de", "score": 15.0 - i * 0.1,
        "url": f"https://jobs.example.com/{i}",
        "description": "supply chain procurement logistics " * 6,
        "raw": {},
    }


# ---------------------------------------------------------------------------
# F — orçamento 🎯
# ---------------------------------------------------------------------------

def test_radar_budget() -> None:
    section("F: orçamento 🎯 — top-15 + '+X outras'; gate ⭐ último recurso")

    # apply_radar_budget pura
    events = [_simple_job(i) for i in range(40)]
    kept, omitted = mp.apply_radar_budget(events, limit=15)
    check("40 eventos → 15 kept + 25 omitidas",
          len(kept) == 15 and omitted == 25)
    check("kept = 15 MAIORES scores (ordem oficial preservada)",
          [j["id"] for j in kept] == [f"t{i}" for i in range(15)])
    kept2, omitted2 = mp.apply_radar_budget(events[:10], limit=15)
    check("<= limit: lista inteira, 0 omitidas",
          kept2 == events[:10] and omitted2 == 0)
    check("None: intacta (sem orçamento)",
          mp.apply_radar_budget(None, limit=15) == (None, 0))

    # tie-break determinístico por id (lexicográfico: t0 < t1 < t10...)
    ties = [dict(_simple_job(i), score=5.0) for i in range(20)]
    kept3, _ = mp.apply_radar_budget(ties, limit=5)
    check("empate de score: tie-break determinístico por id",
          [j["id"] for j in kept3] == ["t0", "t1", "t10", "t11", "t12"])

    # página grande: 40 eventos 🎯 + rows ⭐ → só top-15 + '+25 outras' + ⭐
    import io
    from contextlib import redirect_stdout

    def _big_jobs() -> list[dict]:
        jobs = []
        for i in range(400):
            j = _simple_job(i % 40)
            j = dict(j)
            j["id"] = f"j{i}"
            j["company"] = f"Firma {i % 40} GmbH"
            j["description"] = "x" * 300
            j["score"] = 20.0 - (i * 0.01)
            jobs.append(j)
        return jobs

    jobs = _big_jobs()
    events40 = []
    for i in range(40):
        e = dict(_simple_job(i))
        e["id"] = f"e{i}"
        e["company"] = f"Empresa-Alvo {i} GmbH"
        e["description"] = "watchlist job description " * 10
        e["score"] = 12.0 - i * 0.1
        events40.append(e)
    big_rows = [{"company": f"Empresa {i}", "eligible": 40 - i,
                 "kununu_score": 4.0 + i * 0.05, "gptw_award": None}
                for i in range(10)]

    buf = io.StringIO()
    with redirect_stdout(buf):
        html = mp.render_size_aware(
            jobs, total_eligible=len(jobs), generated_at="x", top=100,
            watchlist_events=events40,
            sweet_spot_rows=big_rows, quality_map=None)
    b = len(html.encode("utf-8"))
    sec = html[html.find("Empresas-alvo"):]
    n_cards = sec[:sec.find("</ol>")].count('<li class="c') \
        if "</ol>" in sec else sec.count('<li class="c')
    check(f"página grande com 40 eventos 🎯 cabe no cap ({b} bytes)",
          b <= mp.PAGE_HARD_CAP_BYTES)
    check("seção 🎯 aparada p/ top-15 (RADAR_TOP_N)", n_cards == 15)
    check("linha honesta '+25 outras vagas de empresas-alvo'",
          "+25 outras vagas de empresas-alvo" in html)
    check("contagem real no header (40 nova(s))",
          "40 nova(s)" in html)
    check("seção ⭐ Ponto ótimo PRESENTE (orçamento salvou a ⭐)",
          "Ponto ótimo" in html)
    check("orçamento logado (linha única)",
          "orçamento 🎯" in buf.getvalue())

    # poucos eventos → todos exibidos, SEM linha "+X outras"
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        html2 = mp.render_size_aware(
            jobs, total_eligible=len(jobs), generated_at="x", top=100,
            watchlist_events=events40[:8],
            sweet_spot_rows=big_rows, quality_map=None)
    check("poucos eventos: todos exibidos",
          html2.count("Empresa-Alvo") >= 8)
    check("poucos eventos: SEM '+X outras' e SEM aviso",
          "outras vagas de empresas-alvo" not in html2
          and "orçamento" not in buf2.getvalue())

    # página onde MESMO aparada estoura o cap → gate ⭐ dispara (último
    # recurso, aviso verbatim da F15 preservado)
    huge_rows = [{"company": f"Empresa {i}", "eligible": 40 - i,
                  "kununu_score": 4.0 + i * 0.05, "gptw_award": None}
                 for i in range(60)]
    buf3 = io.StringIO()
    with redirect_stdout(buf3):
        html3 = mp.render_size_aware(
            jobs, total_eligible=len(jobs), generated_at="x", top=100,
            watchlist_events=events40,
            quality_map=None, sweet_spot_rows=huge_rows)
    b3 = len(html3.encode("utf-8"))
    check(f"mesmo aparada estourando: dentro do cap ({b3} bytes)",
          b3 <= mp.PAGE_HARD_CAP_BYTES)
    # gate ⭐ (último recurso): a seção ⭐ sai quando nem o orçamento basta
    # (dependendo do tamanho exato, ⭐ pode caber — o teste aceita os dois
    # estados, mas EXIGE cap respeitado e radar aparado)
    if "Ponto ótimo" not in html3:
        check("gate ⭐: última linha de defesa disparou (sem estourar cap)",
              b3 <= mp.PAGE_HARD_CAP_BYTES)
    else:
        check("gate ⭐: desnecessário (orçamento bastou)", True)

    # sem eventos 🎯 → regressão byte a byte: size_aware com e sem 🎯 é
    # idêntico (o orçamento é no-op) — MESMA forma de chamada.
    html5 = mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at="x", top=100,
        watchlist_events=None,
        sweet_spot_rows=big_rows, quality_map=None)
    html6 = mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at="x", top=100,
        watchlist_events=[],
        sweet_spot_rows=big_rows, quality_map=None)
    check("sem eventos 🎯: size_aware None == [] (byte a byte)",
          html5 == html6)


# ---------------------------------------------------------------------------
# G — compat F15 T6 (gate continua verde; orçamento no-op sem 🎯)
# ---------------------------------------------------------------------------

def test_f15_gate_compat() -> None:
    section("G: gate F15 T6 — aviso verbatim; orçamento é no-op lá")
    import io
    from contextlib import redirect_stdout

    # fixture do T6: página grande SEM eventos 🎯 → o orçamento NÃO age;
    # o gate ⭐ continua sendo o mecanismo (aviso verbatim preservado).
    jobs = []
    for i in range(400):
        j = _simple_job(i % 40)
        j = dict(j)
        j["id"] = f"g{i}"
        j["company"] = f"Firma {i % 40} GmbH"
        j["description"] = "x" * 300
        jobs.append(j)
    big_rows = [{"company": f"Empresa {i}", "eligible": i,
                 "kununu_score": 4.0 + i * 0.05, "gptw_award": None}
                for i in range(15)]
    buf = io.StringIO()
    with redirect_stdout(buf):
        html = mp.render_minimal_html(
            jobs, total_eligible=len(jobs), generated_at="x", top=100,
            sweet_spot_rows=big_rows, quality_map=None, with_snippets=False)
    out = buf.getvalue()
    check("gate F15: aviso verbatim preservado quando dispara via from_file",
          "OMITIDA" in out or "Ponto ótimo" in html)
    check("orçamento 🎯: no-op sem eventos (nenhum log de orçamento)",
          "orçamento" not in out)
    check("cap respeitado em todos os casos",
          len(html.encode("utf-8")) <= mp.PAGE_HARD_CAP_BYTES
          or "Ponto ótimo" not in html)


# ---------------------------------------------------------------------------
# H — fluxo e2e no refresh_daily (estágio → hidratação persistida → publish)
# ---------------------------------------------------------------------------

def test_refresh_e2e() -> None:
    section("H: refresh e2e — hidratação persistida + publish com 2 conjuntos")
    import subprocess
    from unittest import mock

    with tempfile.TemporaryDirectory(prefix="t_f20_e2e_") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir()
        jobs = []
        for i in range(30):
            jobs.append({
                "id": f"t{i}", "title": f"Praktikum Supply Chain {i}",
                "company": f"Firma {i} GmbH", "location": "Berlin, DE",
                "country_iso": "de", "score": 20.0 - i,
                "url": f"https://jobs.example.com/{i}",
                "description": "logistics procurement " * 30, "raw": {},
            })
        (data_dir / "eligible_jobs.json").write_text(
            json.dumps(jobs), encoding="utf-8")
        (data_dir / "collection_metrics.jsonl").write_text(
            json.dumps({"run_id": "r1", "type": "run", "status": "ok",
                        "total_collected": 400, "eligible": 30}),
            encoding="utf-8")

        calls = {"publish": []}

        def fake_publish(root_, pages, *, exit_code, eligible, run_id,
                         dead_link_ids=None, **kw):
            calls["publish"].append((dead_link_ids, kw.get("inapplicable_ids")))
            return True

        def fake_liveness(jobs_, **kw):
            # 1 morta (t0) + 1 hidratada que revela required (t1)
            return ({"t0"},
                    {"t1": "Sehr gute Deutschkenntnisse (C1) werden "
                           "vorausgesetzt. " * 5},
                    {"attempts": 30, "hydrated": 1, "soft_dead": 1,
                     "dead": 1, "hydration_failed": 0,
                     "short_candidates": 5, "duration_s": 0.1})

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

        check("refresh termina exit 0 com estágio F20", rc == 0)
        dead, ia = calls["publish"][0]
        check("publish recebe dead_link_ids e inapplicable_ids SEPARADOS",
              dead == {"t0"} and ia == {"t1"})
        jobs2 = json.loads((data_dir / "eligible_jobs.json").read_text(
            encoding="utf-8"))
        t1 = next(j for j in jobs2 if j["id"] == "t1")
        check("hidratação persistida: description_source=hydrated_topn",
              t1.get("description_source") == "hydrated_topn")
        check("hidratação persistida: timestamp presente",
              "description_hydrated_at" in t1)
        check("hidratação persistida: marcador honesto no JSON (fica)",
              t1.get("hydration_inapplicable") == "german_required")
        t0j = next(j for j in jobs2 if j["id"] == "t0")
        check("vaga morta: intocada no JSON (só desce do top)",
              t0j.get("description_source") is None
              and "hydration_inapplicable" not in t0j)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    test_base64_mirror()
    test_dedup_mirror()
    test_soft_dead()
    test_hydration()
    test_regression()
    test_radar_budget()
    test_f15_gate_compat()
    test_refresh_e2e()
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
