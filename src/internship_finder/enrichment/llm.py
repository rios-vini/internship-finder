"""Cliente LLM (API NVIDIA integrate) para extracao estruturada.

Fatos medidos (historia completa, NAO reabrir sem evidencia nova):

- Endpoint ``https://integrate.api.nvidia.com/v1/chat/completions``.
- **23/10/2026 (F102 — swap de modelo POR EVIDENCIA NOVA, regra do topo)**:
  ``z-ai/glm-5.3`` recebe header ``deprecation: 2026-10-28T08:00:00Z``
  em TODA resposta (aposentadoria POR MODELO: o flash e ``/v1/models``
  NAO carregam o header; 410 Gone pos-data segundo o forum NVIDIA). A/B
  head-to-head em codigo de producao (8 vagas reais x mesmo prompt +
  ``reasoning_effort="low"``): 96% de respostas identicas, 5
  divergencias reais (nemotron 4x1), zero alucinacao/parse-error,
  latencia empate ~25-28s. Evidencia + raw:
  ``~/.hermes/handoff/nvidia-deprecao-ab/``. MODEL default =
  ``nvidia/nemotron-3-ultra-550b-a55b`` (rollback ate 28/10 08:00Z via
  env ``INTERNSHIP_FINDER_ENRICHMENT_MODEL``).
- **19/10/2026 (calibracao F50, payload real, ordem do dono)**:
  ``z-ai/glm-5.3`` (normal) + ``reasoning_effort="low"`` = PARSED OK em 1
  tentativa, 53,4s/vaga, tokens in 2.679 / out 584, ZERO burn de max_tokens
  (evidencia + script: ~/.hermes/handoff/f50-enrichment-flags/). O normal e o
  MODEL default desde entao (o flash estava murado: hang 000 / 429 desde
  18/10). Sweep de 24 vagas ~ 21min, cabe no teto 1800s.
- **spike 24/09 (SUPERSEDED pelo fix F50 ``reasoning_effort``)**: glm-5.3
  SEM reasoning_effort queimava TODO o max_tokens em raciocinio interno
  (A/B 5/5 falhas; flags de thinking da epoca ignoradas). Com o fix low o
  normal funciona — medido 19/10. Flash: parse OK, 16-290s/vaga (mais
  rapido ~23s quando saudavel — voltar a ele so se o normal voltar a
  queimar, com evidencia).
- ``temperature: 0``, ``max_tokens: 8000``, timeout ~290s.
- Parser tolerante obrigatorio: blocos de raciocinio "think" removidos,
  code fences removidos, texto antes do primeiro ``{`` descartado,
  ``raw_decode`` no resto; invalido -> erro claro (parse_error e retryavel).
- A key vem EXCLUSIVAMENTE de ``NVIDIA_API_KEY`` (env var). NUNCA default,
  nunca em arquivo, nunca em log/erro/artefato (todas as mensagens de erro
  passam por ``_sanitize``).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable

import requests

from internship_finder.enrichment.fetch import RequestsTransport, Transport

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
CHAT_COMPLETIONS_URL = f"{NVIDIA_BASE_URL}/chat/completions"
MODELS_URL = f"{NVIDIA_BASE_URL}/models"
# F50.1 (19/10, ordem do dono "troque o flash pelo normal"): default = normal
# (calibrado: +reasoning_effort=low -> 53s/vaga, zero burn). Override sem
# deploy via env (padrao REASONING_EFFORT_ENV): valor preenchido -> usado
# verbatim; vazio/ausente -> default do modulo (model e OBRIGATORIO na API —
# nao existe "nao enviar"). Flash voltar a ser default exige evidencia de
# queima do normal (docstring acima).
MODEL_ENV = "INTERNSHIP_FINDER_ENRICHMENT_MODEL"
MODEL = os.environ.get(MODEL_ENV) or "nvidia/nemotron-3-ultra-550b-a55b"

LLM_TIMEOUT_S = 290
MAX_TOKENS = 8000
TEMPERATURE = 0

# Retry: maximo 3 tentativas com backoff injetavel (default 30s/60s — o
# spike viu timeout em rajada, nao rate limit; esperar a janela abrir).
MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_S: tuple[float, ...] = (30.0, 60.0)

# Somente erros retryaveis: 429, 5xx, timeout/rede, resposta vazia e
# parse_error (JSON picado em janela degradada). Outros 4xx: registra sem
# retry (erro de request/auth nao se resolve esperando).
RETRYABLE_PREFIXES: tuple[str, ...] = (
    "http_429", "http_5", "request_error", "empty_content", "parse_error",
)


def get_api_key() -> str:
    """Lê a key do env (única fonte). Ausente -> string vazia (runner decide)."""
    return (os.environ.get("NVIDIA_API_KEY") or "").strip()


def _sanitize(message: str, key: str | None) -> str:
    """Remove a key de qualquer mensagem de erro/log (defense in depth)."""
    if key:
        message = message.replace(key, "[REDACTED]")
    return message


def parse_llm_json(content: str) -> dict:
    """Parse tolerante do content da LLM (padrao comprovado no spike).

    1. remove blocos de raciocinio delimitados por tags "think"
       (angle-bracket open/close, regex DOTALL — inclui variantes com
       atributos/whitespace);
    2. remove code fences (```json);
    3. descarta texto antes do primeiro ``{``;
    4. ``json.JSONDecoder().raw_decode`` — trailing garbage e ignorado;
    5. topo precisa ser objeto, senao erro claro (ValueError).
    """
    tag_open, tag_close = chr(60) + "think" + chr(62), chr(47) + "think" + chr(62)
    cleaned = re.sub(
        re.escape(tag_open) + r".*?" + re.escape(tag_close), "", content,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"<[a-z]*\s*think[a-z]*\s*>.*?</[a-z]*\s*think[a-z]*\s*>", "", cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(r"```(?:json)?", "", cleaned)
    cleaned = cleaned.strip()
    idx = cleaned.find("{")
    if idx < 0:
        raise ValueError("sem objeto JSON na resposta")
    obj, _ = json.JSONDecoder().raw_decode(cleaned[idx:])
    if not isinstance(obj, dict):
        raise ValueError("topo do JSON nao e objeto")
    return obj


def validate_model(
    key: str, transport: Transport | None = None
) -> tuple[bool, str | None]:
    """Confere que o MODEL esta disponivel na conta (GET /v1/models).

    Fail-fast do runner: resposta nao-200/JSON invalido/modelo ausente ->
    erro claro SEM retry (setup, nao processamento).
    """
    transport = transport or RequestsTransport()
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    try:
        status, text, _final_url = transport.get(MODELS_URL, headers, 30)
    except requests.RequestException as exc:
        return False, _sanitize(f"model_check_error:{type(exc).__name__}", key)
    if status != 200:
        return False, f"model_check_http_{status}"
    try:
        data = json.loads(text)
    except ValueError:
        return False, "model_check_invalid_json"
    models = data.get("data") if isinstance(data, dict) else None
    ids = [
        m.get("id") for m in models
        if isinstance(m, dict) and isinstance(m.get("id"), str)
    ] if isinstance(models, list) else []
    if MODEL in ids:
        return True, None
    return False, f"model_unavailable:{MODEL}"


def extract(
    key: str,
    prompt: str,
    model: str = MODEL,
    transport: Transport | None = None,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
    reasoning_effort: str | None = None,
) -> tuple[dict | None, dict | None, float | None, int, str | None]:
    """POST /chat/completions com ate 3 tentativas.

    Retorna ``(parsed | None, usage, latency_s, attempts, error)``:
    - sucesso: ``parsed`` dict + ``usage`` (tokens in/out) + ``error=None``;
    - esgotadas as tentativas: ``parsed=None`` + ``error`` curto (sanitizado —
      a key nunca aparece); erros nao-retryaveis param na 1a tentativa.

    ``backoff`` e injetavel (testes usam (0, 0)); ``sleep`` idem.
    ``max_tokens``: ``None`` = MAX_TOKENS default do modulo (8000, contrato
    historico do enrichment); callers de prompts GRANDES (apply-assist F34)
    podem passar orcamento proprio — o glm-5.3-flash queima ~7k tokens em
    reasoning_content antes de escrever o content (medido 13/10: carta com
    max_tokens=8000 -> finish_reason=length/content=None; 16000 -> stop com
    folga), entao 8000 e insuficiente para tarefas de escrita longa.
    ``timeout_s``: ``None`` = LLM_TIMEOUT_S (290s, contrato do enrichment
    spike: 16-290s/vaga); prompts grandes com orcamento maior tambem
    demoram MAIS (reasoning proporcional) — apply-assist usa 600s.
    ``reasoning_effort``: ``None`` = NAO envia o parametro (comportamento
    do endpoint NIM: default "max" — thinking budget maximo; contrato
    historico do enrichment). Callers de escrita (apply-assist F34) passam
    "low": medido 13/10 no endpoint NVIDIA NIM (docs.api.nvidia.com/nim
    z-ai-glm-5-3-flash), o thinking budget e controlado por
    ``reasoning_effort`` (low/high/max, default max) — com max, o FLASH
    queima o tempo no reasoning ate o GATEWAY cortar em ~300s (http_504,
    medido 302s com prompt real de 9.3k chars); com "low" a MESMA carta
    completa em 23s (content 2.8k chars, reasoning 226 chars).
    """
    transport = transport or RequestsTransport()
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    payload = {
        "model": model,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens if max_tokens is not None else MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    call_timeout = timeout_s if timeout_s is not None else LLM_TIMEOUT_S
    parsed: dict | None = None
    usage: dict | None = None
    latency: float | None = None
    error: str | None = None
    attempts = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        if attempt > 1:
            delay = backoff[attempt - 2] if attempt - 2 < len(backoff) else backoff[-1]
            sleep(delay)
        start = time.monotonic()
        try:
            status, text = transport.post(
                CHAT_COMPLETIONS_URL, headers, payload, call_timeout
            )
        except requests.RequestException as exc:
            latency = round(time.monotonic() - start, 2)
            error = f"request_error:{type(exc).__name__}"
        else:
            latency = round(time.monotonic() - start, 2)
            if status == 429:
                error = "http_429"
            elif status >= 500:
                error = f"http_{status}"
            elif status != 200:
                error = f"http_{status}"
            else:
                try:
                    data = json.loads(text)
                except ValueError:
                    error = "parse_error:invalid_response_json"
                else:
                    if isinstance(data.get("usage"), dict):
                        usage = data["usage"]
                    choices = data.get("choices") or []
                    content = ""
                    if choices and isinstance(choices[0], dict):
                        message = choices[0].get("message")
                        if isinstance(message, dict):
                            content = message.get("content") or ""
                    if not content:
                        error = "empty_content"
                    else:
                        try:
                            parsed = parse_llm_json(content)
                            error = None
                        except (ValueError, json.JSONDecodeError) as exc:
                            parsed = None
                            error = f"parse_error:{type(exc).__name__}"
        if parsed is not None:
            break
        if error and not error.startswith(RETRYABLE_PREFIXES):
            break

    if error:
        error = _sanitize(error, key)
    return parsed, usage, latency, attempts, error


# ---------------------------------------------------------------------------
# Prompt (constante) — conservador, com os 3 few-shots obrigatorios
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are an information extraction engine for job postings.
Extract ONLY information explicitly supported by the provided job-page text. Do not infer immigration status, sponsorship, nationality eligibility, work authorization, salary, language level, work mode, or deadlines.

Job anchor (from the feed): company="{company}", title="{title}". Use the anchor ONLY to decide whether this text is the actual posting for THIS job (page_is_job_posting) and to disambiguate references. The anchor itself is NOT evidence for any other field.

WORK AUTHORIZATION fields — these are DIFFERENT concepts, NEVER synonyms. Evaluate each one INDEPENDENTLY: evidence for one proves nothing about the others.
- student_status_required (true/false/not_mentioned/unclear): the job requires being currently enrolled at a university (Immatrikulation/enrolled at a Hochschule). Proving enrollment does NOT prove work authorization, sponsorship, or a residence permit.
- work_authorization_required: a GENERIC statement that some work authorization is necessary, without specifying which.
- existing_work_authorization_required: requires that the candidate ALREADY HOLDS a valid authorization (e.g. "must already hold a valid work permit", "vorhandene Arbeitserlaubnis").
- work_permit_required: explicit mention of Arbeitserlaubnis/work permit AS A REQUIREMENT.
- residence_permit_required: explicit mention of Aufenthaltserlaubnis/residence permit AS A REQUIREMENT.
- visa_sponsorship: the employer SPONSORS/covers/assists with visas (e.g. "we sponsor work visas", "Ubernahme der Visakosten"). Absence of visa promotion is "not_mentioned", never "false".
- international_candidates_explicitly_accepted: the JOB explicitly states international candidates are accepted/welcome for THIS position (e.g. "international applicants welcome"). Generic company-level DEI/diversity statements do NOT count.
- eu_citizenship_required: EU citizenship explicitly required.

CONDITIONAL phrasing: if an authorization/permit/requirement is stated conditionally — "ggf." (= if applicable), "falls erforderlich", "if applicable", "oder" presenting an alternative, "nach Moglichkeit", "where applicable" — the value is "unclear" with the phrase as evidence, NEVER "true".
"false" is ONLY for an explicit statement that the thing is NOT required/not offered (e.g. "No visa sponsorship available", "keine Visumsunterstutzung").

Examples (real cases — follow them exactly):
1. "sowie ggf. eine gueltige Arbeits- und Aufenthaltserlaubnis" — "ggf." = "if applicable" = conditional -> existing_work_authorization_required = "unclear" (evidence: the phrase). NOT true.
2. "Bayer begrusst Bewerbungen aller Menschen ungeachtet von ethnischer Herkunft, nationaler Herkunft..." — generic company DEI statement -> international_candidates_explicitly_accepted = "not_mentioned". NOT true.
3. "Voraussetzung fur das Praktikum ist die Immatrikulation an einer Hochschule" -> student_status_required = "true" (evidence: the phrase). This proves NOTHING about visa_sponsorship, work_authorization_required, existing_work_authorization_required, work_permit_required, or residence_permit_required — those stay "not_mentioned" unless the page says so.

Content fields (same rules; pages may be in any language, German included):
- salary: literal from the page: {"value": "2.117", "period": "hour|month|year|null", "currency": "EUR|null", "evidence": "..."} — only as stated, never converted or averaged.
- work_mode: "on_site"|"hybrid"|"remote"|"not_mentioned"|"unclear" as declared ("on-site"/"vor Ort" = on_site; "hybrid" = hybrid; "remote"/"100% Homeoffice" = remote).
- location: location explicitly stated ON THE PAGE (not the feed) or null.
- internship_compatible (true/false/not_mentioned/unclear): page confirms Praktikum/Werkstudent/internship/working student/Masterarbeit -> true; clearly a regular full-time job -> false.
- german_requirement / english_requirement: {"level": "none|conversational|fluent|business|native|not_mentioned|unclear", "evidence": "..."} — level AS DECLARED ("verhandlungssicher" -> business, "sehr gute Deutschkenntnisse" -> fluent, "fliessend" -> fluent, "native speaker" -> native, "keine Deutschkenntnisse erforderlich" -> none). The language the posting is WRITTEN in is NOT a requirement. Absence -> not_mentioned.
- employer_deadline: {"date": "YYYY-MM-DD|null", "evidence": "..."} — ONLY a deadline EXPLICITLY stated on the page (e.g. "Bewerbungsfrist: 23.10.2026" -> "2026-10-23"). NEVER infer from the posting date or any date field.
- page_is_job_posting (true/false): true only if the text is the actual job posting matching the anchor company+title; false for generic careers pages, listings, or unrelated pages.

VALUE RULES:
- "true"/"false" REQUIRE "evidence": a literal quote (<=200 chars) copied from the page text.
- Absence of information -> "not_mentioned" (NEVER "false").
- Conflicting, insufficient, or conditional evidence -> "unclear" (with evidence when a quote exists).
- "confidence" per field: "high" (explicit, unambiguous), "medium" (stated but indirect), "low" (weak/ambiguous basis).
- Never propagate a value from one field to another.

Output ONLY valid JSON, no markdown, no commentary, with EXACTLY this shape:
{
  "student_status_required": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "work_authorization_required": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "existing_work_authorization_required": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "work_permit_required": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "residence_permit_required": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "visa_sponsorship": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "international_candidates_explicitly_accepted": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "eu_citizenship_required": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "internship_compatible": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "salary": {"value": null, "period": null, "currency": null, "evidence": null, "confidence": null},
  "work_mode": {"value": "not_mentioned", "evidence": null, "confidence": null},
  "location": {"value": null, "evidence": null, "confidence": null},
  "german_requirement": {"level": "not_mentioned", "evidence": null, "confidence": null},
  "english_requirement": {"level": "not_mentioned", "evidence": null, "confidence": null},
  "employer_deadline": {"date": null, "evidence": null, "confidence": null},
  "page_is_job_posting": {"value": false, "evidence": null, "confidence": null}
}

PAGE TEXT (job: {company} | {title}):
"""


def build_prompt(company: str, title: str, content: str) -> str:
    """Monta o prompt final (ancora + conteudo normalizado ja truncado).

    Usa ``str.replace`` (nunca ``format``) para nao colidir com as chaves
    literais do schema JSON de saida embutido no prompt.
    """
    return (
        EXTRACTION_PROMPT.replace("{company}", str(company or ""))
        .replace("{title}", str(title or ""))
        + content
    )
