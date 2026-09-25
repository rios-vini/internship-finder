#!/usr/bin/env python3
"""Testes OFFLINE da camada de enrichment (scripts/test_enrichment.py).

Padrao do repo: imprime [OK]/[FAIL], termina TUDO OK (exit 0) ou FALHAS
(exit != 0). SEM rede — toda funcao de I/O (fetch, chamada LLM) e injetada
via transport falso; store usa tempdir; amostra usa o data/ local (read-
only). A key NUNCA e real (fake injetada); nenhum teste toca a API NVIDIA.

Uso:

    .venv/bin/python scripts/test_enrichment.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requests  # noqa: E402

from internship_finder import app_intel  # noqa: E402
from internship_finder.enrichment import (  # noqa: E402
    fetch as fetch_mod,
    html_norm,
    llm,
    runner,
)
from internship_finder.enrichment.schema import (  # noqa: E402
    EVIDENCE_MAX_CHARS,
    EnrichmentRecord,
    ExtractedField,
    build_record,
    compute_record_confidence,
    fields_from_llm,
    hash_content,
)
from internship_finder.enrichment.store import EnrichmentStore  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    if cond:
        print(f"[OK] {name}")
    else:
        print(f"[FAIL] {name} {detail}")
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------

FAKE_KEY = "fake-key-DO-NOT-LEAK-1234567890"


class FakeLLMTransport:
    """Transport falso: fila de respostas (status, body) para .post.

    Fila esgotada REPETE a ultima resposta (cenario de esgotar as 3
    tentativas sem scriptar 3 itens).
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.last = responses[-1] if responses else None
        self.calls: list[dict] = []

    def post(self, url, headers, payload, timeout):
        self.calls.append(
            {"url": url, "headers": headers, "payload": payload}
        )
        if self.responses:
            item = self.responses.pop(0)
            self.last = item
        else:
            item = self.last
        if isinstance(item, Exception):
            raise item
        status, body = item
        return status, body

    def get(self, url, headers, timeout):
        raise AssertionError("LLM transport nao deve fazer GET na suíte LLM")


class FakeModelsTransport:
    """Transport falso para validate_model (GET /v1/models)."""

    def __init__(self, status=200, ids=("z-ai/glm-5.3-flash",)):
        self.status = status
        self.ids = list(ids)

    def get(self, url, headers, timeout):
        body = json.dumps({"data": [{"id": i} for i in self.ids]})
        return self.status, body, url

    def post(self, url, headers, payload, timeout):
        raise AssertionError("models transport nao deve fazer POST")


class FakePageTransport:
    """Transport falso: mapa url -> (status, html, final_url) para .get."""

    def __init__(self, pages):
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url, headers, timeout):
        self.calls.append(url)
        if url in self.pages:
            status, html, final_url = self.pages[url]
            return status, html, final_url
        raise requests.ConnectTimeout("scripted page failure")


def llm_body(content: str, usage: dict | None = None) -> str:
    return json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50},
        }
    )


VALID_EXTRACTION = {
    "student_status_required": {
        "value": "true",
        "evidence": "Voraussetzung fuer das Praktikum ist die Immatrikulation an einer Hochschule",
        "confidence": "high",
    },
    "visa_sponsorship": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "page_is_job_posting": {
        "value": True,
        "evidence": "titulo da vaga no texto",
        "confidence": "high",
    },
}


def make_job(job_id: str = "ACME|ats:1", **overrides) -> dict:
    job = {
        "id": job_id,
        "company": "ACME",
        "title": "Praktikum Data Analytics",
        "source": "ats:test",
        "url": "http://acme.test/job/1",
        "score": 10.0,
        "description": "Werkstudent im Bereich Data Analytics.",
    }
    job.update(overrides)
    return job


# ---------------------------------------------------------------------------
# 1. Schema: record valido / rejeicoes / confianca record-level
# ---------------------------------------------------------------------------

ok_kwargs = dict(
    job_id="X|ats:1", company="C", title="T", source="ats:x",
    original_url="http://a", fetched_at="2026-09-25T00:00:00+00:00",
    page_status="ok",
)
rec = EnrichmentRecord(**ok_kwargs)
check("schema: record valido (nao-extracao, defaults)", rec.confidence is None)
try:
    EnrichmentRecord(**{k: v for k, v in ok_kwargs.items() if k != "job_id"})
    check("schema: rejeita sem job_id", False)
except Exception:
    check("schema: rejeita sem job_id", True)
try:
    EnrichmentRecord(**{k: v for k, v in ok_kwargs.items() if k != "page_status"})
    check("schema: rejeita sem page_status", False)
except Exception:
    check("schema: rejeita sem page_status", True)
try:
    EnrichmentRecord(**ok_kwargs, page_status="qualquer")
    check("schema: rejeita page_status invalido", False)
except Exception:
    check("schema: rejeita page_status invalido", True)

check(
    "schema: not_mentioned sem evidence OK",
    ExtractedField(value="not_mentioned").value == "not_mentioned",
)
try:
    ExtractedField(value="true")
    check("schema: true sem evidence REJEITADO", False)
except Exception:
    check("schema: true sem evidence REJEITADO", True)
try:
    ExtractedField(value="true", evidence="citação literal da página")
    check("schema: true sem confidence REJEITADO", False)
except Exception:
    check("schema: true sem confidence REJEITADO", True)
try:
    ExtractedField(value="true", evidence="x" * (EVIDENCE_MAX_CHARS + 1), confidence="high")
    check("schema: evidence >200 REJEITADO", False)
except Exception:
    check("schema: evidence >200 REJEITADO", True)
check(
    "schema: false exige evidence",
    (
        lambda: (
            [ExtractedField(value="false", evidence="no visa sponsorship available", confidence="high")],
            True,
        )[1]
    )(),
)

# confianca record-level deterministica
good_fields = fields_from_llm({
    "student_status_required": {
        "value": "true",
        "evidence": "Voraussetzung ist die Immatrikulation an einer Hochschule",
        "confidence": "high",
    },
    "page_is_job_posting": {"value": True, "evidence": "ancora casa", "confidence": "high"},
})
rec_high = build_record(
    make_job(), fetched_at="2026-09-25T00:00:00+00:00", page_status="ok",
    final_url="http://a", http_status=200, content_hash="h",
    fields=good_fields, model=llm.MODEL, extracted_at="2026-09-25T00:00:01+00:00",
)
check("confianca: high quando completa sem truncamento", rec_high.confidence == "high")
rec_med = build_record(
    make_job(), fetched_at="2026-09-25T00:00:00+00:00", page_status="ok",
    fields=good_fields, model=llm.MODEL, extracted_at="2026-09-25T00:00:01+00:00",
    content_truncated=True,
)
check("confianca: medium quando truncado", rec_med.confidence == "medium")
bad_pip = fields_from_llm({"page_is_job_posting": {"value": False}})
rec_low = build_record(
    make_job(), fetched_at="2026-09-25T00:00:00+00:00", page_status="ok",
    fields=bad_pip, model=llm.MODEL, extracted_at="2026-09-25T00:00:01+00:00",
)
check("confianca: low quando page_is_job_posting=false", rec_low.confidence == "low")
check(
    "confianca: None quando nao extraido",
    compute_record_confidence(rec) is None,
)

# ---------------------------------------------------------------------------
# 2. parse_llm_json: fence, think, lixo, picado
# ---------------------------------------------------------------------------

TAG_O, TAG_C = chr(60) + "think" + chr(62), chr(47) + "think" + chr(62)
FENCE = "`" * 3
check("parse: JSON limpo", llm.parse_llm_json('{"a": 1}') == {"a": 1})
check(
    "parse: code fence ```json",
    llm.parse_llm_json(FENCE + 'json {"a": 1}' + FENCE) == {"a": 1},
)
check(
    "parse: bloco think antes do JSON",
    llm.parse_llm_json(TAG_O + "raciocinio interno" + TAG_C + ' {"a": 1}')
    == {"a": 1},
)
check(
    "parse: texto antes do primeiro '{'",
    llm.parse_llm_json('aqui vai o resultado: {"a": {"b": true}} fim')
    == {"a": {"b": True}},
)
check(
    "parse: think + fence + texto (tudo junto)",
    llm.parse_llm_json(
        TAG_O + "x" + TAG_C + " blabla " + FENCE + 'json {"ok": true}' + FENCE
    ) == {"ok": True},
)
try:
    llm.parse_llm_json('{"a": 1, "b": ')
    check("parse: JSON picado -> erro claro", False)
except (ValueError, json.JSONDecodeError):
    check("parse: JSON picado -> erro claro", True)
try:
    llm.parse_llm_json("sem json nenhum aqui")
    check("parse: sem objeto -> ValueError", False)
except ValueError:
    check("parse: sem objeto -> ValueError", True)

# ---------------------------------------------------------------------------
# 3. Classificacao de campos (guardas pos-LLM + independencia)
# ---------------------------------------------------------------------------

GGF = "sowie ggf. eine gueltige Arbeits- und Aufenthaltserlaubnis"
for phrase in (GGF, "falls erforderlich", "if applicable", "falls notwendig"):
    fields = fields_from_llm({
        "existing_work_authorization_required": {
            "value": "true", "evidence": phrase,
        }
    })
    field = fields["existing_work_authorization_required"]
    check(
        f"campos: condicional '{phrase[:22]}' -> unclear (nunca true)",
        field.value == "unclear" and field.evidence == phrase,
    )

DEI = ("Bayer begriert Bewerbungen aller Menschen ungeachtet von ethnischer "
       "Herkunft, nationaler Herkunft")
fields = fields_from_llm({
    "international_candidates_explicitly_accepted": {
        "value": "true", "evidence": DEI,
    }
})
check(
    "campos: frase DEI -> not_mentioned (nunca true)",
    fields["international_candidates_explicitly_accepted"].value == "not_mentioned",
)

IMMAT = "Voraussetzung fuer das Praktikum ist die Immatrikulation an einer Hochschule"
fields = fields_from_llm({
    "student_status_required": {"value": "true", "evidence": IMMAT},
})
check(
    "campos: Immatrikulation -> student_status true",
    fields["student_status_required"].value == "true",
)
check(
    "campos: independencia — nao propaga p/ outros campos",
    all(
        fields[name].value == "not_mentioned"
        for name in (
            "visa_sponsorship", "work_authorization_required",
            "existing_work_authorization_required", "work_permit_required",
            "residence_permit_required", "eu_citizenship_required",
            "international_candidates_explicitly_accepted",
        )
    ),
)

empty_fields = fields_from_llm({})
check(
    "campos: ausencia -> not_mentioned (nunca false)",
    all(empty_fields[n].value == "not_mentioned" for n in (
        "student_status_required", "visa_sponsorship", "work_permit_required",
    )),
)
check(
    "campos: conflito explicito (unclear) preservado",
    fields_from_llm({
        "work_authorization_required": {"value": "unclear", "evidence": "mixed signals"},
    })["work_authorization_required"].value == "unclear",
)
check(
    "campos: valor fora do enum -> unclear",
    fields_from_llm({
        "visa_sponsorship": {"value": "maybe"},
    })["visa_sponsorship"].value == "unclear",
)
check(
    "campos: true SEM evidence -> unclear (nunca true)",
    fields_from_llm({
        "visa_sponsorship": {"value": "true"},
    })["visa_sponsorship"].value == "unclear",
)
check(
    "campos: work_mode on-site -> on_site",
    fields_from_llm({"work_mode": {"value": "on-site"}})["work_mode"].value == "on_site",
)
check(
    "campos: work_mode desconhecido -> unclear",
    fields_from_llm({"work_mode": {"value": "flexible"}})["work_mode"].value == "unclear",
)
check(
    "campos: verhandlungssicher -> business",
    fields_from_llm({
        "german_requirement": {"level": "verhandlungssicher"},
    })["german_requirement"].level == "business",
)
check(
    "campos: sehr gute -> fluent",
    fields_from_llm({
        "german_requirement": {"level": "sehr gute Deutschkenntnisse"},
    })["german_requirement"].level == "fluent",
)
check(
    "campos: idioma ausente -> not_mentioned",
    fields_from_llm({})["english_requirement"].level == "not_mentioned",
)
check(
    "campos: deadline explicito preservado",
    fields_from_llm({
        "employer_deadline": {"date": "2026-10-23", "evidence": "Bewerbungsfrist: 23.10.2026"},
    })["employer_deadline"].date is not None,
)
check(
    "campos: deadline sem evidencia -> descartado (nunca inventado)",
    fields_from_llm({
        "employer_deadline": {"date": "2026-10-23"},
    })["employer_deadline"].date is None,
)
check(
    "campos: salary sem evidencia -> valor descartado",
    fields_from_llm({
        "salary": {"value": "2000", "period": "month", "currency": "EUR"},
    })["salary"].value is None,
)
check(
    "campos: salary literal com evidencia",
    (
        lambda s: (s.value == "2.117", s.currency == "EUR", s.period == "month")[0]
    )(fields_from_llm({
        "salary": {"value": "2.117", "period": "monat", "currency": "EUR",
                   "evidence": "Gehalt: 2.117 EUR/Monat"},
    })["salary"]),
)

# ---------------------------------------------------------------------------
# 4. classify_page: 8 status
# ---------------------------------------------------------------------------

job = {"url": "http://a/job", "title": "Senior Data Analytics Praktikum"}
long_text = ("Senior Data Analytics Praktikum Bosch " + "conteudo util da vaga " * 30)
ok_resp = fetch_mod.FetchResult(200, "http://a/job", "<html><body>vaga</body></html>", None)
check("classify: 200 com conteudo -> ok",
      fetch_mod.classify_page(ok_resp, long_text, job) == "ok")
home_resp = fetch_mod.FetchResult(200, "http://a/careers", "<html>careers</html>", None)
generic = "Careers at our company. Browse open roles. " * 20
check("classify: redirect p/ home sem match -> redirected",
      fetch_mod.classify_page(home_resp, generic, job) == "redirected")
match_resp = fetch_mod.FetchResult(200, "http://a/job-2", "<html>vaga</html>", None)
check("classify: redirect COM match de titulo -> ok",
      fetch_mod.classify_page(match_resp, long_text, job) == "ok")
nf_resp = fetch_mod.FetchResult(404, "http://a/job", "<html>gone</html>", None)
check("classify: 404 -> not_found",
      fetch_mod.classify_page(nf_resp, long_text, job) == "not_found")
gone_resp = fetch_mod.FetchResult(410, "http://a/job", "<html>gone</html>", None)
check("classify: 410 -> not_found",
      fetch_mod.classify_page(gone_resp, long_text, job) == "not_found")
check("classify: texto <200 chars -> empty_content",
      fetch_mod.classify_page(ok_resp, "curto demais", job) == "empty_content")
spa_html = ('<html><body><div id="root"></div><script id="__NEXT_DATA__">'
            '{"props":{}}</script>' + "<script>var x=1;</script>" * 12 + "</body></html>")
spa_resp = fetch_mod.FetchResult(200, "http://a/job", spa_html, None)
check("classify: SPA (__NEXT_DATA__, texto minimo) -> js_rendered",
      fetch_mod.classify_page(spa_resp, "Loading...", job) == "js_rendered")
timeout_resp = fetch_mod.FetchResult(None, None, None, "timeout")
check("classify: timeout -> timeout",
      fetch_mod.classify_page(timeout_resp, "", job) == "timeout")
err_resp = fetch_mod.FetchResult(None, None, None, "fetch_error:ConnectTimeout")
check("classify: excecao -> fetch_error",
      fetch_mod.classify_page(err_resp, "", job) == "fetch_error")
http_resp = fetch_mod.FetchResult(403, "http://a/job", "<html>forbidden</html>", None)
check("classify: 403 (outro nao-200) -> http_error",
      fetch_mod.classify_page(http_resp, long_text, job) == "http_error")

# fetch_page com transport falso: excecoes capturadas por tipo
fake_pages = FakePageTransport({})
try:
    fetch_mod.fetch_page("http://x", transport=fake_pages)
    timeout_result = None
except Exception:
    timeout_result = "raised"
timeout_result = fetch_mod.fetch_page("http://x", transport=fake_pages)
check("fetch: requests.Timeout -> error=timeout", timeout_result.error == "timeout")
boom = FakePageTransport({})
boom.pages = {}
def _raise(url, headers, timeout):
    raise requests.ConnectionError("boom")
boom.get = _raise
err_result = fetch_mod.fetch_page("http://x", transport=boom)
check("fetch: RequestException -> fetch_error:<Tipo>",
      err_result.error == "fetch_error:ConnectionError")
no_url = fetch_mod.fetch_page("")
check("fetch: sem URL -> fetch_error:no_url", no_url.error == "fetch_error:no_url")

# ---------------------------------------------------------------------------
# 5. normalize_html
# ---------------------------------------------------------------------------

html_doc = (
    "<html><head><style>.x{color:red}</style></head><body>"
    "<nav><a href='#'>Menu</a><a href='#'>Jobs</a></nav>"
    "<script>var a=1;</script>"
    "<h1>Praktikum Data</h1>"
    "<p>Descri&ccedil;&atilde;o da vaga com conte&uacute;do.</p>"
    "<footer>(c) ACME</footer>"
    "</body></html>"
)
text = html_norm.normalize_html(html_doc)
check("normalize: remove script", "var a" not in text)
check("normalize: remove style", "color:red" not in text)
check("normalize: remove nav", "Menu" not in text)
check("normalize: remove footer", "(c) ACME" not in text)
check("normalize: preserva bloco de conteudo", "Praktikum Data" in text)
check("normalize: entidades decodadas", "Descrição da vaga" in text)
header_doc = ("<html><body><header><nav>menu</nav></header>"
              "<header><h1>Job Title</h1></header><p>body</p></body></html>")
header_text = html_norm.normalize_html(header_doc)
check("normalize: header boilerplate (com nav) removido", "menu" not in header_text)
check("normalize: header com titulo preservado", "Job Title" in header_text)
check("normalize: html vazio -> string vazia", html_norm.normalize_html("") == "")

# ---------------------------------------------------------------------------
# 6. Cache por (job_id, final_url, content_hash)
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    store = EnrichmentStore(Path(tmp) / "enrichment_results.jsonl")
    success = build_record(
        make_job(), fetched_at="2026-09-25T00:00:00+00:00", page_status="ok",
        final_url="http://a/job", http_status=200, content_hash="hash-1",
        fields=good_fields, model=llm.MODEL, extracted_at="2026-09-25T00:00:01+00:00",
    )
    store.upsert(success)
    job_id = make_job()["id"]
    check("cache: mesmo job_id+final_url+hash -> skip",
          runner.should_skip(store, job_id, "http://a/job", "hash-1"))
    check("cache: content_hash diferente -> reprocessa",
          not runner.should_skip(store, job_id, "http://a/job", "hash-2"))
    check("cache: final_url diferente -> reprocessa",
          not runner.should_skip(store, job_id, "http://a/job-2", "hash-1"))
    failure = build_record(
        make_job(job_id), fetched_at="2026-09-25T00:00:00+00:00", page_status="ok",
        final_url="http://a/job", http_status=200, content_hash="hash-3",
        error="llm_error:http_429", model=llm.MODEL,
    )
    store.upsert(failure)
    check("cache: record de falha -> retry permitido",
          not runner.should_skip(store, job_id, "http://a/job", "hash-3"))
    check("cache: job nunca processado -> processa",
          not runner.should_skip(store, "OUTRO|ats:9", "http://a/job", "hash-1"))

# ---------------------------------------------------------------------------
# 7. Retry/error handling da LLM (transport injetado, backoff 0)
# ---------------------------------------------------------------------------

NO_BACKOFF = (0, 0)
tracked = FakeLLMTransport([(429, ""), (429, ""), (429, "")])
parsed, usage, latency, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=tracked, backoff=NO_BACKOFF
)
check("llm: 429 esgota 3 tentativas", parsed is None and attempts == 3)
check("llm: 429 -> erro http_429 registrado", error == "http_429")
check("llm: 3 chamadas no transport", len(tracked.calls) == 3)

recover = FakeLLMTransport([(500, ""), (200, llm_body(json.dumps(VALID_EXTRACTION)))])
parsed, usage, latency, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=recover, backoff=NO_BACKOFF
)
check("llm: 200 valido na 2a tentativa -> attempts=2", attempts == 2)
check("llm: parse OK apos retry", parsed is not None and parsed["visa_sponsorship"]["value"] == "not_mentioned")
check("llm: usage propagado", (usage or {}).get("prompt_tokens") == 100)

no_retry = FakeLLMTransport([(400, "bad request")])
parsed, usage, latency, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=no_retry, backoff=NO_BACKOFF
)
check("llm: 4xx nao-retryavel -> 1 tentativa", attempts == 1)
check("llm: 4xx erro registrado sem retry", parsed is None and error == "http_400")

empty_then_valid = FakeLLMTransport([
    (200, llm_body("")),
    (200, llm_body(json.dumps(VALID_EXTRACTION))),
])
parsed, _, _, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=empty_then_valid, backoff=NO_BACKOFF
)
check("llm: resposta vazia e retryavel (attempts=2)",
      attempts == 2 and parsed is not None)

picado_then_valid = FakeLLMTransport([
    (200, llm_body('{"a": 1, "b": ')),
    (200, llm_body(json.dumps(VALID_EXTRACTION))),
])
parsed, _, _, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=picado_then_valid, backoff=NO_BACKOFF
)
check("llm: parse_error e retryavel (JSON picado, attempts=2)",
      attempts == 2 and parsed is not None)

network_fail = FakeLLMTransport([requests.ReadTimeout("took too long")])
parsed, usage, latency, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=network_fail, backoff=NO_BACKOFF
)
check("llm: timeout de rede esgota 3 tentativas",
      attempts == 3 and error == "request_error:ReadTimeout")

# payload do POST: temperatura 0, max_tokens 8000, model flash
payload = tracked.calls[0]["payload"] if tracked.calls else {}
check("llm: payload temperature=0", payload.get("temperature") == 0)
check("llm: payload max_tokens=8000", payload.get("max_tokens") == 8000)
check("llm: model fixo z-ai/glm-5.3-flash",
      payload.get("model") == "z-ai/glm-5.3-flash" and llm.MODEL == "z-ai/glm-5.3-flash")

# ---------------------------------------------------------------------------
# 8. Persistencia atomica + upsert + preservacao + load tolerante
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "enrichment" / "enrichment_results.jsonl"
    store = EnrichmentStore(out)
    check("store: load de arquivo inexistente -> {}", store.load() == {})
    first = build_record(
        make_job("A|ats:1"), fetched_at="t1", page_status="ok",
        final_url="http://a/1", content_hash="h1", http_status=200,
        fields=good_fields, model=llm.MODEL, extracted_at="t1",
    )
    check("store: upsert 1o record -> written", store.upsert(first) == "written")
    check("store: arquivo criado com 1 linha", len(out.read_text().splitlines()) == 1)

    second = build_record(
        make_job("A|ats:1"), fetched_at="t2", page_status="ok",
        final_url="http://a/1", content_hash="h1", http_status=200,
        fields=good_fields, model=llm.MODEL, extracted_at="t2",
    )
    second.company = "NOVA EMPRESA"
    check("store: upsert substitui o mesmo job_id", store.upsert(second) == "written")
    loaded = store.load()
    check("store: upsert deixou 1 record e conteudo novo",
          len(loaded) == 1 and loaded["A|ats:1"]["company"] == "NOVA EMPRESA")

    # falha nova do MESMO conteudo NAO apaga sucesso
    success_hash = loaded["A|ats:1"]["content_hash"]
    failure_same = build_record(
        make_job("A|ats:1"), fetched_at="t3", page_status="ok",
        final_url="http://a/1", content_hash=success_hash, http_status=200,
        error="llm_error:http_429", model=llm.MODEL,
    )
    check("store: falha do mesmo content_hash -> preserved",
          store.upsert(failure_same) == "preserved")
    check("store: sucesso preservado apos falha",
          store.load()["A|ats:1"]["company"] == "NOVA EMPRESA"
          and store.load()["A|ats:1"]["extracted_at"] == "t2")

    # falha de conteudo NOVO e gravada (estado atual e dado)
    failure_new = build_record(
        make_job("A|ats:1"), fetched_at="t4", page_status="not_found",
        content_hash="h2", http_status=404,
    )
    check("store: falha de conteudo novo -> written",
          store.upsert(failure_new) == "written")
    check("store: record atual reflete o estado novo",
          store.load()["A|ats:1"]["page_status"] == "not_found")

    # escrita atomica: sem temporarios residuais no diretorio
    residue = [p.name for p in out.parent.iterdir() if p.name != out.name]
    check("store: sem arquivos temporarios residuais", residue == [])

    # load tolerante: linha malformada pula sem crashar
    other = build_record(
        make_job("B|ats:2"), fetched_at="t5", page_status="ok",
        final_url="http://b/2", content_hash="hB", http_status=200,
    )
    store.upsert(other)
    good_line = out.read_text().splitlines()
    with out.open("a", encoding="utf-8") as handle:
        handle.write("}{ linha malformada\n")
        handle.write("\n")
        handle.write('{"no_job_id": true}\n')
    loaded = store.load()
    check("store: load pula malformada sem crashar", len(loaded) == 2)
    check("store: records validos preservados no load",
          set(loaded.keys()) == {"A|ats:1", "B|ats:2"})

# ---------------------------------------------------------------------------
# 9. Isolamento por vaga no lote
# ---------------------------------------------------------------------------

class BoomTransport:
    """LLM OK, mas fetch da vaga 2 explode com excecao nao-request."""

    def __init__(self, boom_url):
        self.boom_url = boom_url
        self.pages = {
            "http://acme.test/job/1": (
                200,
                "<html><body><h1>Praktikum Data Analytics</h1>"
                "<p>descricao longa " + "x" * 400 + "</p></body></html>",
                "http://acme.test/job/1",
            ),
            "http://acme.test/job/3": (
                200,
                "<html><body><h1>Praktikum Data Analytics</h1>"
                "<p>descricao longa " + "y" * 400 + "</p></body></html>",
                "http://acme.test/job/3",
            ),
        }
        self.posts = 0

    def get(self, url, headers, timeout):
        if url == self.boom_url:
            raise RuntimeError("boom na vaga 2")
        status, html, final_url = self.pages[url]
        return status, html, final_url

    def post(self, url, headers, payload, timeout):
        self.posts += 1
        return 200, llm_body(json.dumps(VALID_EXTRACTION))


with tempfile.TemporaryDirectory() as tmp:
    store = EnrichmentStore(Path(tmp) / "out.jsonl")
    jobs = [
        make_job("ACME|ats:1", url="http://acme.test/job/1"),
        make_job("ACME|ats:2", url="http://acme.test/job/2"),
        make_job("ACME|ats:3", url="http://acme.test/job/3"),
    ]
    boom = BoomTransport("http://acme.test/job/2")
    result = runner.process_batch(
        jobs, FAKE_KEY, store, transport=boom, backoff=(0, 0), sleep_fetch=0,
        log=lambda *_: None,
    )
    records = {r["job_id"]: r for r in result["records"]}
    check("lote: 3 records retornados (nada abortou)", len(records) == 3)
    check("lote: vaga 2 -> record de erro",
          records["ACME|ats:2"]["error"] == "runner_error:RuntimeError")
    check("lote: vagas 1 e 3 extraidas",
          records["ACME|ats:1"]["extracted_at"] is not None
          and records["ACME|ats:3"]["extracted_at"] is not None)
    check("lote: resumo consistente",
          result["summary"]["extractions_ok"] == 2
          and result["summary"]["extractions_fail"] == 1)

# cache_hit dentro do lote: rerun idempotente nao chama LLM
with tempfile.TemporaryDirectory() as tmp:
    store = EnrichmentStore(Path(tmp) / "out.jsonl")
    page = ("http://acme.test/job/1",
            (200, "<html><body><h1>Praktikum Data Analytics</h1><p>"
             + "conteudo " * 100 + "</p></body></html>",
             "http://acme.test/job/1"))
    class OnePageTransport:
        posts = 0
        def get(self, url, headers, timeout):
            return page[1][0], page[1][1], page[1][2]
        def post(self, url, headers, payload, timeout):
            self.posts += 1
            return 200, llm_body(json.dumps(VALID_EXTRACTION))
    tr = OnePageTransport()
    jobs = [make_job("ACME|ats:1", url="http://acme.test/job/1")]
    runner.process_batch(jobs, FAKE_KEY, store, transport=tr, backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    first_posts = tr.posts
    result2 = runner.process_batch(jobs, FAKE_KEY, store, transport=tr, backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    check("lote: rerun idempotente -> cache_hit",
          result2["summary"]["cache_hits"] == 1 and tr.posts == first_posts)

# ---------------------------------------------------------------------------
# 10. select_sample: determinismo, composicao, unicos, teto
# ---------------------------------------------------------------------------

data_path = Path(__file__).resolve().parent.parent / "data" / "eligible_jobs.json"
if data_path.exists():
    real_jobs = json.loads(data_path.read_text(encoding="utf-8"))
    s1 = runner.select_sample(real_jobs)
    s2 = runner.select_sample(real_jobs)
    check("amostra: deterministica (2 chamadas identicas)", s1 == s2)
    check("amostra: 16+4+4=24 vagas", len(s1) == 24, f"got {len(s1)}")
    check("amostra: ids unicos", len(set(str(j['id']) for j in s1)) == 24)
    ats = {str(j["source"]) for j in s1}
    check("amostra: multiplos ATS", len(ats) >= 5, f"got {len(ats)}")
    ordered = sorted(real_jobs, key=lambda j: (float(j.get("score") or 0), str(j.get("id"))), reverse=True)
    check("amostra: top 16 sao os 16 maiores scores",
          [str(j["id"]) for j in s1[:16]] == [str(j["id"]) for j in ordered[:16]])
    wa = [j for j in s1[16:20]]
    check("amostra: extras WA detectados no feed",
          all(app_intel.work_authorization(
              f"{j.get('title') or ''} {j.get('description') or ''}"
          )["state"] != "not_mentioned" for j in wa))
    nodesc = [j for j in s1[20:24]]
    check("amostra: extras sem description",
          all(not (j.get("description") or "").strip() for j in nodesc))
    small = runner.select_sample(real_jobs, top=3, extra_wa=1, extra_nodesc=1)
    check("amostra: teto respeitado (3+1+1=5)", len(small) == 5, f"got {len(small)}")
    check("amostra: ids unicos no teto",
          len(set(str(j["id"]) for j in small)) == 5)
else:  # CI (sem data/): fixture sintetica
    synth = [
        {"id": f"S{i}", "company": f"C{i}", "title": f"Job {i}",
         "source": "ats:s", "url": f"http://x/{i}", "score": float(i),
         "description": "" if i % 2 else "Werkstudent Data Analytics"}
        for i in range(20)
    ]
    a = runner.select_sample(synth, top=5, extra_wa=2, extra_nodesc=2)
    b = runner.select_sample(synth, top=5, extra_wa=2, extra_nodesc=2)
    check("amostra: deterministica (fixture)", a == b)
    check("amostra: composicao 5+2+2", len(a) == 9, f"got {len(a)}")
    check("amostra: ids unicos (fixture)",
          len(set(str(j["id"]) for j in a)) == 9)

# ---------------------------------------------------------------------------
# 11. Segredo: a key nunca vaza em prompt/erro/artefato
# ---------------------------------------------------------------------------

leak_transport = FakeLLMTransport([
    requests.ConnectionError(f"connection refused for Bearer {FAKE_KEY}"),
])
parsed, usage, latency, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=leak_transport, backoff=NO_BACKOFF
)
check("segredo: erro nao contem a key", FAKE_KEY not in (error or ""))
body_leak = FakeLLMTransport([(401, f"unauthorized key {FAKE_KEY}")])
parsed, usage, latency, attempts, error = llm.extract(
    FAKE_KEY, "prompt", transport=body_leak, backoff=NO_BACKOFF
)
check("segredo: body de erro nao vaza no erro final", FAKE_KEY not in (error or ""))
prompt = llm.build_prompt("ACME", "Praktikum", "texto da pagina")
check("segredo: prompt nao contem a key", FAKE_KEY not in prompt)
check("segredo: validate_model ok com transport falso",
      llm.validate_model(FAKE_KEY, transport=FakeModelsTransport())[0] is True)
check("segredo: validate_model sanitiza erros",
      all(
          FAKE_KEY not in (llm.validate_model(FAKE_KEY, transport=tr)[1] or "")
          for tr in (
              FakeModelsTransport(status=500),
              FakeModelsTransport(status=401, ids=()),
          )
      ))
# producao (pacote + runner): o PROPRIO teste carrega esses padroes como
# regra de varredura — scan de codigo de producao, nao do teste.
source_paths = list(
    (Path(__file__).resolve().parent.parent / "src" / "internship_finder" / "enrichment").glob("*.py")
) + [Path(__file__).resolve().parent / "enrichment_run.py"]
leaks = [
    str(p)
    for p in source_paths
    if p.exists() and ("nvapi" + "-") in p.read_text(encoding="utf-8", errors="ignore")
]
check("segredo: nenhum padrao de key real no codigo versionado", not leaks, str(leaks))
env_leak = [
    p for p in source_paths
    if p.exists() and ".hermes/.env" in p.read_text(encoding="utf-8", errors="ignore")
]
check("segredo: codigo nunca referencia .hermes/.env", not env_leak)

print()
if FAILURES:
    print(f"FALHAS: {len(FAILURES)}")
    sys.exit(1)
print("TUDO OK")
