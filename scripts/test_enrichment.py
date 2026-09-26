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

import argparse
import json
import os
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
# 6. Delta pos-fetch: classify_seen (cache por job_id + final_url + content_hash)
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    store = EnrichmentStore(Path(tmp) / "enrichment_results.jsonl")
    success = build_record(
        make_job(), fetched_at="2026-09-25T00:00:00+00:00", page_status="ok",
        final_url="http://a/job", http_status=200, content_hash="hash-1",
        fields=good_fields, model=llm.MODEL, extracted_at="2026-09-25T00:00:01+00:00",
    )
    store.upsert(success)
    record = store.load()[make_job()["id"]]
    check("cache: mesmo job_id+final_url+hash -> cache_hit",
          runner.classify_seen(record, "http://a/job", "hash-1") == "cache_hit")
    check("cache: content_hash diferente -> changed",
          runner.classify_seen(record, "http://a/job", "hash-2") == "changed")
    check("cache: final_url diferente -> changed_source",
          runner.classify_seen(record, "http://a/job-2", "hash-1")
          == "changed_source")
    # pendencia (D6): hash atual == pending_content_hash -> retry (a versao
    # pendente voltou); hash diferente de ambos -> changed (mudou de novo)
    pending = dict(record, pending_content_hash="hash-2")
    check("pendencia: hash atual == pending -> retry",
          runner.classify_seen(pending, "http://a/job", "hash-2") == "retry")
    check("pendencia: hash atual == sucesso MAS pendencia existe -> changed",
          runner.classify_seen(pending, "http://a/job", "hash-1") == "changed")
    check("pendencia: hash diferente de ambos -> changed",
          runner.classify_seen(pending, "http://a/job", "hash-9") == "changed")

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

    # FASE 2 (spec secao 9 / decisao D6): falha de re-extracao de conteudo
    # NOVO NAO substitui mais o sucesso — o comportamento antigo (gravar a
    # falha por cima) perdia a extracao valida por indisponibilidade da
    # API. Agora: sucesso preservado + pendencia registrada.
    failure_new = build_record(
        make_job("A|ats:1"), fetched_at="t4", page_status="ok",
        final_url="http://a/1", content_hash="h2", http_status=200,
        error="llm_error:http_429", model=llm.MODEL,
    )
    check("store: falha de conteudo novo -> preserved (spec secao 9)",
          store.upsert(failure_new) == "preserved")
    kept_new = store.load()["A|ats:1"]
    check("store: sucesso preservado com pendencia (nada apagado)",
          kept_new["extracted_at"] == "t2" and kept_new["company"] == "NOVA EMPRESA"
          and kept_new["page_status"] == "ok")
    check("store: pendencia registra o hash novo",
          kept_new.get("pending_content_hash") == "h2"
          and kept_new.get("last_error") == "llm_error:http_429"
          and kept_new.get("last_failed_at") == "t4")
    # falha de FETCH posterior (timeout, hash desconhecido): preserva o
    # sucesso E MANTENM a pendencia anterior — a pagina provavelmente
    # continua sendo a versao pendente (hash None nao prova que voltou)
    failure_gone = build_record(
        make_job("A|ats:1"), fetched_at="t4b", page_status="timeout",
        final_url="http://a/1", content_hash=None, http_status=None,
        error="timeout",
    )
    check("store: falha de fetch apos pendencia -> preserved",
          store.upsert(failure_gone) == "preserved")
    kept_gone = store.load()["A|ats:1"]
    check("store: pendencia anterior MANTIDA em fetch falho (hash None)",
          kept_gone.get("extracted_at") == "t2"
          and kept_gone.get("pending_content_hash") == "h2"
          and kept_gone.get("last_error") == "timeout"
          and kept_gone.get("last_failed_at") == "t4b")

    # REGRESSAO (fix do orquestrador): fetch falho (content_hash=None,
    # conteudo DESCONHECIDO — timeout/rede) NUNCA apaga sucesso anterior.
    success_after = build_record(
        make_job("A|ats:1"), fetched_at="t5", page_status="ok",
        final_url="http://a/1", content_hash="h3", http_status=200,
        model=llm.MODEL, extracted_at="t5",
    )
    check("store: re-sucesso apos not_found -> written",
          store.upsert(success_after) == "written")
    fetch_fail = build_record(
        make_job("A|ats:1"), fetched_at="t6", page_status="timeout",
        content_hash=None, http_status=None, error="request_error:ReadTimeout",
    )
    check("store: fetch falho (hash None) -> preserved",
          store.upsert(fetch_fail) == "preserved")
    kept = store.load()["A|ats:1"]
    check("store: extracao valida preservada apos fetch falho",
          kept["extracted_at"] == "t5" and kept["content_hash"] == "h3"
          and kept["page_status"] == "ok")
    check("store: falha de fetch fica auditavel no record (last_error)",
          kept.get("last_error") == "request_error:ReadTimeout"
          and kept.get("last_failed_at") == "t6")
    check("store: falha de fetch LLM (hash None) tambem preserva",
          store.upsert(build_record(
              make_job("A|ats:1"), fetched_at="t7", page_status="ok",
              final_url="http://a/1", content_hash=None, http_status=200,
              error="llm_error:http_429", model=llm.MODEL,
          )) == "preserved")

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
# 9. FASE 2 — planejamento incremental (plan_jobs) + sweep + cap + idempotencia
# ---------------------------------------------------------------------------

def _page_for(content: str, url: str) -> tuple:
    return (200, "<html><body><h1>Praktikum Data Analytics</h1><p>"
            + content + "</p></body></html>", url)


class SweepTransport:
    """Transport falso: mapa url -> (status, html, final_url) + contador LLM."""

    def __init__(self, pages, llm_success=True):
        self.pages = pages
        self.llm_success = llm_success
        self.posts = 0

    def get(self, url, headers, timeout):
        if "integrate.api.nvidia.com" in url:  # GET /v1/models do validate_model
            return 200, json.dumps({"data": [{"id": llm.MODEL}]}), url
        return self.pages[url]

    def post(self, url, headers, payload, timeout):
        self.posts += 1
        if not self.llm_success:
            return 429, ""
        return 200, llm_body(json.dumps(VALID_EXTRACTION))


# 9a. plano deterministico: new/retry/seen na ordem (score desc, id desc)
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    ok_rec = build_record(
        make_job("B|ats:1"), fetched_at="t1", page_status="ok",
        final_url="http://b/1", http_status=200, content_hash="hb",
        fields=good_fields, model=llm.MODEL, extracted_at="t1",
    )
    fail_rec = build_record(
        make_job("C|ats:1"), fetched_at="t1", page_status="ok",
        final_url="http://c/1", http_status=200, content_hash="hc",
        error="llm_error:http_429", model=llm.MODEL,
    )
    store.upsert(ok_rec)
    store.upsert(fail_rec)
    jobs = [
        make_job("A|ats:1", score=9.0),   # new
        make_job("B|ats:1", score=8.0),   # sucesso -> seen
        make_job("C|ats:1", score=7.0),   # falha -> retry
        make_job("D|ats:1", score=6.0),   # new
        {"id": "", "company": "X", "title": "sem id", "source": "s",
         "url": "http://x/0", "score": 99.0},  # sem id -> pulada
    ]
    plan = runner.plan_jobs(jobs, store.load())
    check("plano: buckets new/retry/seen",
          [p.bucket for p in plan] == ["new", "seen", "retry", "new"])
    check("plano: ordem (score desc, id desc)",
          [str(p.job["id"]) for p in plan]
          == ["A|ats:1", "B|ats:1", "C|ats:1", "D|ats:1"])
    check("plano: vaga sem id pulada", len(plan) == 4)

# 9b. vaga nova -> enrichment (D8.1); ja enriquecida + hash igual ->
#     cache_hit com ZERO chamadas LLM (D8.2); idempotencia (D8.12)
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    url = "http://acme.test/job/1"
    pages = {url: _page_for("conteudo util " * 50, url)}
    tr = SweepTransport(pages)
    jobs = [make_job("ACME|ats:1", url=url)]
    plan = runner.plan_jobs(jobs, store.load())
    s1 = runner.run_incremental(plan, FAKE_KEY, store, transport=tr,
                                backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    check("fase2: vaga nova -> 1 extracao LLM",
          s1["llm_calls"] == 1 and s1["extractions_ok"] == 1 and tr.posts == 1)
    check("fase2: vaga nova gravada com extracted_at",
          store.load()["ACME|ats:1"]["extracted_at"] is not None)

    tr2 = SweepTransport(pages)
    plan2 = runner.plan_jobs(jobs, store.load())
    s2 = runner.run_incremental(plan2, FAKE_KEY, store, transport=tr2,
                                backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    check("fase2: idempotencia — 2a run zero LLM, tudo cache_hit",
          s2["llm_calls"] == 0 and s2["cache_hits"] == 1 and tr2.posts == 0)

# 9c. conteudo alterado (hash diferente) -> novo enrichment (D8.3);
#     URL final alterada -> changed_source (D8.4)
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    url = "http://acme.test/job/1"
    tr = SweepTransport({url: _page_for("versao A " * 50, url)})
    jobs = [make_job("ACME|ats:1", url=url)]
    s1 = runner.run_incremental(runner.plan_jobs(jobs, {}), FAKE_KEY, store,
                                transport=tr, backoff=(0, 0), sleep_fetch=0,
                                log=lambda *_: None)
    # conteudo muda
    tr_changed = SweepTransport({url: _page_for("versao B " * 50, url)})
    s2 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, transport=tr_changed, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    check("fase2: conteudo alterado -> novo enrichment",
          s2["llm_calls"] == 1 and s2["changed"] == 1)
    check("fase2: novo sucesso substitui (regra da Fase 1)",
          store.load()["ACME|ats:1"]["extracted_at"] is not None)
    # URL final muda (redirect), conteudo IGUAL ao do sucesso — prova que
    # changed_source dispara pela URL, independentemente do hash
    tr_src = SweepTransport(
        {url: (200, _page_for("versao B " * 50, url)[1],
               "http://acme.test/job/1-new")})
    s3 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, transport=tr_src, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    check("fase2: URL final alterada -> changed_source + LLM",
          s3["llm_calls"] == 1 and s3["changed_source"] == 1)

# 9d. falha temporaria -> retry no run seguinte (D8.5); falha NAO apaga
#     sucesso anterior; pendencia reprocessada no run seguinte (D8.7)
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    url = "http://acme.test/job/1"
    tr = SweepTransport({url: _page_for("conteudo util " * 50, url)})
    jobs = [make_job("ACME|ats:1", url=url)]
    runner.run_incremental(runner.plan_jobs(jobs, {}), FAKE_KEY, store,
                           transport=tr, backoff=(0, 0), sleep_fetch=0,
                           log=lambda *_: None)
    success_before = dict(store.load()["ACME|ats:1"])

    # conteudo NOVO + LLM falha (429 em rajada)
    tr_fail = SweepTransport({url: _page_for("conteudo novo " * 50, url)},
                             llm_success=False)
    s2 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, transport=tr_fail, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    kept = store.load()["ACME|ats:1"]
    check("fase2: falha de hash novo preserva sucesso + pendencia",
          kept["extracted_at"] == success_before["extracted_at"]
          and kept.get("pending_content_hash") is not None
          and kept.get("last_error") is not None)
    check("fase2: falha individual conta e o lote segue",
          s2["extractions_fail"] == 1 and s2["llm_calls"] == 1)

    # run seguinte: MESMO conteudo novo, LLM OK -> pendencia reprocessada
    tr_ok = SweepTransport({url: _page_for("conteudo novo " * 50, url)})
    s3 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, transport=tr_ok, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    after = store.load()["ACME|ats:1"]
    check("fase2: pendencia reprocessada no run seguinte",
          s3["llm_calls"] == 1 and s3["retry"] == 1
          and "pending_content_hash" not in after
          and after["extracted_at"] is not None
          and after["content_hash"] == hash_content(html_norm.normalize_html(
              _page_for("conteudo novo " * 50, url)[1])))

    # fetch falho (timeout) sobre sucesso com pendencia ja resolvida:
    # preserva sem pendencia nova (hash None = desconhecido)
    class TimeoutTransport(SweepTransport):
        def get(self, url, headers, timeout):
            raise requests.ConnectTimeout("scripted timeout")

    s4 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, transport=TimeoutTransport({}),
                                backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    kept4 = store.load()["ACME|ats:1"]
    check("fase2: fetch falho preserva o ultimo sucesso",
          kept4["extracted_at"] == after["extracted_at"]
          and kept4.get("last_error") == "timeout"
          and s4["fetch_failures"] == 1 and s4["timeouts"] == 1)

# 9e. falha permanente (4xx nao-retryavel) -> registrado, sem retry
#     infinito (D8.6) — testado na camada LLM (secao 7); aqui o comportamento
#     integrado: extracao falha 1x, record de falha gravado, lote segue
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    url = "http://acme.test/job/1"

    class PermanentFailTransport(SweepTransport):
        def post(self, url, headers, payload, timeout):
            self.posts += 1
            return 400, "bad request"

    tr = PermanentFailTransport({url: _page_for("conteudo util " * 50, url)})
    jobs = [make_job("ACME|ats:1", url=url)]
    s1 = runner.run_incremental(runner.plan_jobs(jobs, {}), FAKE_KEY, store,
                                transport=tr, backoff=(0, 0), sleep_fetch=0,
                                log=lambda *_: None)
    check("fase2: 4xx permanente -> 1 tentativa, sem retry infinito",
          tr.posts == 1 and s1["llm_calls"] == 1
          and s1["extractions_fail"] == 1)
    check("fase2: record de falha gravado e retryavel",
          store.load()["ACME|ats:1"]["error"] == "llm_error:http_400"
          and store.load()["ACME|ats:1"]["attempts"] == 1)

# 9f. backlog limitado: pool > cap -> LLM calls == cap, excedente pending
#     (D8.8); prioridade do pool: retry -> new -> changed (D2)
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    pages = {}
    jobs = []
    for i in range(5):
        url = f"http://acme.test/job/{i}"
        pages[url] = _page_for(f"conteudo {i} " * 50, url)
        jobs.append(make_job(f"ACME|ats:{i}", url=url, score=float(10 - i)))
    tr = SweepTransport(pages)
    s1 = runner.run_incremental(runner.plan_jobs(jobs, {}), FAKE_KEY, store,
                                limit=2, transport=tr, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    check("fase2: backlog — LLM calls == cap",
          s1["llm_calls"] == 2 and s1["extractions_ok"] == 2)
    check("fase2: excedente fica pending_backlog",
          s1["pending_backlog"] == 3)
    # run 2: backlog continua (2 do cap + 1 que sobrou)
    tr2 = SweepTransport(pages)
    s2 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, limit=2, transport=tr2, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    check("fase2: backlog processado naturalmente no run seguinte",
          s2["llm_calls"] == 2 and s2["pending_backlog"] == 1)
    tr3 = SweepTransport(pages)
    s3 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, limit=2, transport=tr3, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    check("fase2: backlog esgotado — 3 runs processam as 5 vagas",
          s3["llm_calls"] == 1 and s3["pending_backlog"] == 0
          and len(store.load()) == 5)
    tr4 = SweepTransport(pages)
    s4 = runner.run_incremental(runner.plan_jobs(jobs, store.load()), FAKE_KEY,
                                store, limit=2, transport=tr4, backoff=(0, 0),
                                sleep_fetch=0, log=lambda *_: None)
    check("fase2: backlog esgotado -> run 100% cache_hit",
          s4["llm_calls"] == 0 and s4["cache_hits"] == 5
          and s4["pending_backlog"] == 0)

    # prioridade do pool: retry primeiro, depois new (score desc dentro do
    # bloco) — vaga de falha com score MENOR entra na frente de new maior
    store2 = EnrichmentStore(Path(tmp) / "prio.jsonl")
    fail_low = build_record(
        make_job("LOW|ats:1", score=1.0), fetched_at="t1", page_status="ok",
        final_url="http://acme.test/job/low", http_status=200,
        content_hash="x", error="llm_error:http_429", model=llm.MODEL,
    )
    store2.upsert(fail_low)
    pages2 = dict(pages)
    pages2["http://acme.test/job/low"] = _page_for("baixa prioridade " * 50,
                                                   "http://acme.test/job/low")
    jobs2 = jobs + [make_job("LOW|ats:1", url="http://acme.test/job/low",
                             score=1.0)]
    trp = SweepTransport(pages2)
    sp = runner.run_incremental(runner.plan_jobs(jobs2, store2.load()),
                                FAKE_KEY, store2, limit=3, transport=trp,
                                backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    check("fase2: pool prioriza retry sobre new (D2)",
          sp["llm_calls"] == 3 and sp["retry"] >= 1)

# 9g. métricas do resumo + status file batem com o cenário (D8.10)
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out.jsonl"
    store = EnrichmentStore(out)
    url = "http://acme.test/job/1"
    tr = SweepTransport({url: _page_for("conteudo util " * 50, url)})
    jobs = [make_job("ACME|ats:1", url=url)]
    plan = runner.plan_jobs(jobs, {})
    s1 = runner.run_incremental(plan, FAKE_KEY, store, transport=tr,
                                backoff=(0, 0), sleep_fetch=0, log=lambda *_: None)
    text = runner.format_summary(s1)
    check("fase2: resumo cobre todos os campos da secao 4",
          all(field in text for field in (
              "vagas elegiveis", "cache hits", "pool:", "selecionadas",
              "backlog pendente", "LLM:", "fetch:", "preservados", "tokens:",
              "tempos")))
    check("fase2: resumo com valores do cenario",
          "vagas elegiveis: 1" in text and "chamadas 1" in text)
    runner._write_run_status(out, 0, s1, s1["duration_s"], s1.get("last_error"))
    status = json.loads(runner.status_path_for(out).read_text(encoding="utf-8"))
    check("fase2: status file com health da secao 12",
          status["last_exit_code"] == 0 and status["model"] == "z-ai/glm-5.3-flash"
          and status["last_success_at"] is not None
          and status["counts"]["llm_calls"] == 1)
    # falha de setup: last_success_at preservado
    runner._write_run_status(out, 1, None, 0.0, "setup: sem key")
    status2 = json.loads(runner.status_path_for(out).read_text(encoding="utf-8"))
    check("fase2: run falho preserva last_success_at anterior",
          status2["last_exit_code"] == 1
          and status2["last_success_at"] == status["last_success_at"]
          and status2["last_error"] == "setup: sem key")
    # escrita atomica: sem temporarios residuais
    residue = [p.name for p in out.parent.iterdir()
               if p.name not in (out.name, runner.STATUS_FILE_NAME,
                                 runner.LOCK_FILE_NAME)]
    check("fase2: status/store sem temporarios residuais", residue == [])

# ---------------------------------------------------------------------------
# 10. FASE 2 — concorrencia (flock) + run() exit codes
# ---------------------------------------------------------------------------

# 10a. duas execucoes concorrentes: a segunda detecta lock e sai 3 sem
# tocar o store (D8.9). A key precisa estar no env — o exit 1 de "key
# ausente" vem ANTES da aquisicao do lock.
with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    out = base / "out.jsonl"
    eligible = base / "eligible_jobs.json"
    eligible.write_text(json.dumps(
        [make_job("X|ats:1", url="http://x/1")], ensure_ascii=False),
        encoding="utf-8")
    EnrichmentStore(out).upsert(build_record(
        make_job("X|ats:1"), fetched_at="t1", page_status="ok",
        final_url="http://x/1", http_status=200, content_hash="hx",
        fields=good_fields, model=llm.MODEL, extracted_at="t1",
    ))
    before = out.read_bytes()
    fd = runner.acquire_lock(out)
    check("lock: primeiro adquire", fd is not None)
    assert fd is not None
    old_key = os.environ.get("NVIDIA_API_KEY")
    os.environ["NVIDIA_API_KEY"] = FAKE_KEY
    try:
        rc = runner.run(argparse.Namespace(
            input=str(eligible), output=str(out),
            limit=1, sleep_fetch=0, dry_run=False,
        ), transport=SweepTransport({}), backoff=(0, 0), log=lambda *_: None)
        check("concorrencia: run com lock ocupado -> exit 3",
              rc == 3)
        check("concorrencia: store intocado pela run recusada",
              out.read_bytes() == before)
        os.close(fd)
        # lock liberado: run volta a passar (com transport vazio o fetch
        # da vaga falha como fetch_error — exit 0, dado do cenario)
        rc = runner.run(argparse.Namespace(
            input=str(eligible), output=str(out),
            limit=1, sleep_fetch=0, dry_run=False,
        ), transport=SweepTransport({}), backoff=(0, 0), log=lambda *_: None)
        check("lock: liberado apos close (run nao sai mais 3)",
              rc == 0)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass  # ja fechado no bloco try
        if old_key is None:
            os.environ.pop("NVIDIA_API_KEY", None)
        else:
            os.environ["NVIDIA_API_KEY"] = old_key

# 10b. exit codes do run() com input real (D5)
class _Args:
    def __init__(self, input, output, limit, dry_run=False, sleep_fetch=0):
        self.input = input
        self.output = output
        self.limit = limit
        self.dry_run = dry_run
        self.sleep_fetch = sleep_fetch


with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    eligible = base / "eligible_jobs.json"
    eligible.write_text(json.dumps(
        [make_job("ACME|ats:1", url="http://acme.test/job/1")],
        ensure_ascii=False), encoding="utf-8")
    out = base / "enrichment" / "enrichment_results.jsonl"

    # --dry-run: plano pre-fetch, sem rede, sem lock, exit 0
    rc = runner.run(_Args(str(eligible), str(out), 24, dry_run=True),
                    transport=SweepTransport({}), backoff=(0, 0),
                    log=lambda *_: None)
    check("run: --dry-run exit 0 e nao cria lock",
          rc == 0 and not (out.parent / runner.LOCK_FILE_NAME).exists())

    # key ausente -> exit 1 + status file registrado
    old_key = os.environ.pop("NVIDIA_API_KEY", None)
    try:
        rc = runner.run(_Args(str(eligible), str(out), 24),
                        transport=SweepTransport({}), backoff=(0, 0),
                        log=lambda *_: None)
        check("run: key ausente -> exit 1", rc == 1)
        status = json.loads(runner.status_path_for(out).read_text(encoding="utf-8"))
        check("run: key ausente registrada no status",
              status["last_exit_code"] == 1
              and "NVIDIA_API_KEY" in (status["last_error"] or ""))
    finally:
        if old_key is not None:
            os.environ["NVIDIA_API_KEY"] = old_key

    # run real com transport valido: exit 0 + status + store escritos
    os.environ["NVIDIA_API_KEY"] = FAKE_KEY
    try:
        url = "http://acme.test/job/1"
        tr = SweepTransport({url: _page_for("conteudo util " * 50, url)})
        rc = runner.run(_Args(str(eligible), str(out), 24),
                        transport=tr, backoff=(0, 0), log=lambda *_: None)
        check("run: run real exit 0", rc == 0)
        check("run: store gravado com 1 record",
              len(EnrichmentStore(out).load()) == 1)
        status = json.loads(runner.status_path_for(out).read_text(encoding="utf-8"))
        check("run: status file exit 0 + counts",
              status["last_exit_code"] == 0
              and status["counts"]["extractions_ok"] == 1)

        # idempotencia: 2a run exit 0, zero LLM, tudo cache_hit
        tr2 = SweepTransport({url: _page_for("conteudo util " * 50, url)})
        rc2 = runner.run(_Args(str(eligible), str(out), 24),
                         transport=tr2, backoff=(0, 0), log=lambda *_: None)
        status2 = json.loads(runner.status_path_for(out).read_text(encoding="utf-8"))
        check("run: idempotente — 2a run 100% cache_hit (exit 0)",
              rc2 == 0 and status2["counts"]["llm_calls"] == 0
              and status2["counts"]["cache_hits"] == 1)

        # --limit 0 com pool pendente -> exit 2 (nada processado)
        eligible2 = base / "eligible2.json"
        eligible2.write_text(json.dumps(
            [make_job("ACME|ats:9", url="http://acme.test/job/9")],
            ensure_ascii=False), encoding="utf-8")
        tr3 = SweepTransport(
            {"http://acme.test/job/9": _page_for("outra vaga " * 50,
                                                "http://acme.test/job/9")})
        rc3 = runner.run(_Args(str(eligible2), str(out), 0),
                         transport=tr3, backoff=(0, 0), log=lambda *_: None)
        status3 = json.loads(runner.status_path_for(out).read_text(encoding="utf-8"))
        check("run: --limit 0 com pool pendente -> exit 2",
              rc3 == 2 and status3["counts"].get("pending_backlog") == 1)

        # input ilegivel -> exit 1
        rc4 = runner.run(_Args(str(base / "nao_existe.json"), str(out), 24),
                         transport=SweepTransport({}), backoff=(0, 0),
                         log=lambda *_: None)
        check("run: input ilegivel -> exit 1", rc4 == 1)
        bad = base / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        rc5 = runner.run(_Args(str(bad), str(out), 24),
                         transport=SweepTransport({}), backoff=(0, 0),
                         log=lambda *_: None)
        check("run: input malformado -> exit 1", rc5 == 1)
        empty = base / "empty.json"
        empty.write_text("[]", encoding="utf-8")
        rc6 = runner.run(_Args(str(empty), str(out), 24),
                         transport=SweepTransport({}), backoff=(0, 0),
                         log=lambda *_: None)
        check("run: eligible vazio -> exit 1", rc6 == 1)
    finally:
        if old_key is not None:
            os.environ["NVIDIA_API_KEY"] = old_key
        else:
            os.environ.pop("NVIDIA_API_KEY", None)

# ---------------------------------------------------------------------------
# 11. Isolamento por vaga (heranca da Fase 1 — mesma garantia, novo fluxo)
# ---------------------------------------------------------------------------

class BoomTransport(SweepTransport):
    """LLM OK, mas fetch da vaga 2 explode com excecao nao-request."""

    def __init__(self, boom_url):
        super().__init__({})
        self.boom_url = boom_url
        self.pages = {
            "http://acme.test/job/1": _page_for("x" * 400, "http://acme.test/job/1"),
            "http://acme.test/job/3": _page_for("y" * 400, "http://acme.test/job/3"),
        }

    def get(self, url, headers, timeout):
        if url == self.boom_url:
            raise RuntimeError("boom na vaga 2")
        status, html, final_url = self.pages[url]
        return status, html, final_url


with tempfile.TemporaryDirectory() as tmp:
    store = EnrichmentStore(Path(tmp) / "out.jsonl")
    jobs = [
        make_job("ACME|ats:1", url="http://acme.test/job/1"),
        make_job("ACME|ats:2", url="http://acme.test/job/2"),
        make_job("ACME|ats:3", url="http://acme.test/job/3"),
    ]
    boom = BoomTransport("http://acme.test/job/2")
    s = runner.run_incremental(runner.plan_jobs(jobs, {}), FAKE_KEY, store,
                                transport=boom, backoff=(0, 0), sleep_fetch=0,
                                log=lambda *_: None)
    records = store.load()
    check("lote: vaga 2 -> record de erro, lote segue",
          records["ACME|ats:2"]["error"] == "runner_error:RuntimeError")
    check("lote: vagas 1 e 3 extraidas",
          records["ACME|ats:1"]["extracted_at"] is not None
          and records["ACME|ats:3"]["extracted_at"] is not None)
    check("lote: resumo consistente",
          s["extractions_ok"] == 2 and s["extractions_fail"] == 0)

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
