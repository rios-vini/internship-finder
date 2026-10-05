"""Camada de EXIBICAO DE->EN (F12) — display-only; o original nunca sai.

Tres responsabilidades (F12, spec do dono):

1. **Titulos DE->EN deterministicos** (``title_en``): dicionario display
   aplicado por PALAVRA INTEIRA (word-boundary), case-insensitive com
   smart-case na reposicao. E OFFLINE por construcao — sem rede, sem env,
   sem LLM. O titulo DE NUNCA e substituido: a linha EN e renderizada
   ABAIXO do original pelo ``minimal_page`` e so quando a traducao difere.

2. **Cache persistente de traducoes de descricao** (``load_/save_translation_cache``):
   ``data/translation_cache.json`` mapeia ``job["id"]`` -> ``{"en": texto,
   "ts": epoch}``. Artefato de RUNTIME: escrito SOMENTE pela ferramenta
   on-demand (``scripts/translate_description.py``), NUNCA pelo cron/pipeline
   e NUNCA commitado (``data/`` e gitignored). Render le best-effort:
   ausente/corrompido -> dict vazio, pagina identica a de hoje.

3. **Traducao LLM sob demanda** (``translate_text``): reusa o PADRAO do
   ``enrichment/llm.py`` (key EXCLUSIVAMENTE da env ``NVIDIA_API_KEY``,
   transport injetavel, retry com backoff, ``_sanitize`` — a key nunca
   aparece em erro/log; GLM 5.3 flash, temperature 0). Diferenca honesta:
   aqui a saida e TEXTO traduzido (nao JSON parseado), limpo por
   ``parse_llm_text`` (think-blocks/code fences/preambulo descartados).

DECISAO DISPLAY vs DEDUP (trampa documentado da spec F12): o
``dedup.TYPE_EQUIVALENCES`` colapsa ``praktikum`` -> "working student"
porque e uma CHAVE de deduplicacao (equivalencia de tipo para fundir
mirrors DE/EN). Para EXIBICAO o dono especificou Praktikum = internship —
``title_en`` usa o dicionario DISPLAY abaixo, NUNCA TYPE_EQUIVALENCES.
Guarda: ``title_en("Pflichtpraktikum") == "Mandatory internship"`` (testado).

Honestidade do dicionario (regra): so PALAVRA INTEIRA casa (``\\b`` dos dois
lados com fallback pos-sufixo). Compostos alemaes ("Einkaufslogistik",
"Werkstudentenwerk") NAO sao traduzidos nem parcialmente — um monstro
"purchasinglogistik" seria pior que nenhum texto EN. Fora do dicionario
fica como esta: traducao parcial honesta > nenhuma. Titulo ja-EN nao muda.

Contrato F12 §3/§4: esta camada e SO de exibicao (HTML). Nenhum modulo do
pipeline (cli/ranking/dedup/filters/refresh_daily/ranking_digest) importa
este modulo; JSON/CSV/digest operam SEMPRE sobre o original.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from internship_finder.enrichment.fetch import RequestsTransport, Transport
from internship_finder.enrichment.llm import (
    CHAT_COMPLETIONS_URL,
    DEFAULT_BACKOFF_S,
    MAX_ATTEMPTS,
    MAX_TOKENS,
    MODEL,
    RETRYABLE_PREFIXES,
    TEMPERATURE,
    _sanitize,
    get_api_key,
)

__all__ = [
    "title_en",
    "CACHE_FILE_NAME",
    "load_translation_cache",
    "save_translation_cache",
    "translate_text",
    "build_translation_prompt",
    "parse_llm_text",
    "MAX_INPUT_CHARS",
]


# ---------------------------------------------------------------------------
# Tarefa 1 — dicionario DISPLAY DE->EN (offline, deterministico)
# ---------------------------------------------------------------------------

# Ordem da lista e irrelevante para corretude (todo padrao exige word-boundary
# dos dois lados, entao nenhum termo casa dentro de outro — "praktikum" NAO
# casa dentro de "pflichtpraktikum"). Mantemos familias juntas, maior primeiro,
# por legibilidade. Fonte: CONTENT_TRANSLATIONS do dedup.py (termos de
# conteudo) + termos de TIPO medidos no eligible (§1 da spec) + os 6 termos
# obrigatorios do glossario. Cada padrao e (regex, replacement); sufixos
# genitivo/plural aceitos SO quando terminam a palavra (o ``\\b`` pos-sufixo
# protege compostos: "einkauf(s)?\\b" casa "Einkaufs" solto mas NAO casa
# "Einkaufslogistik").
_DISPLAY_RULES: list[tuple[re.Pattern[str], str]] = [
    # -- tipos de vaga (DISPLAY: Praktikum = internship; NAO copiar
    #    TYPE_EQUIVALENCES, que colapsa tudo em "working student" so p/ dedup)
    (re.compile(r"\bpflichtpraktika\b", re.IGNORECASE), "mandatory internships"),
    (re.compile(r"\bpflichtpraktikum(s)?\b", re.IGNORECASE), "mandatory internship"),
    (re.compile(r"\bpraktika\b", re.IGNORECASE), "internships"),
    (re.compile(r"\bpraktikum(s)?\b", re.IGNORECASE), "internship"),
    (re.compile(r"\bpraktikantin\b", re.IGNORECASE), "intern"),
    (re.compile(r"\bpraktikanten\b", re.IGNORECASE), "interns"),
    (re.compile(r"\bpraktikant(s)?\b", re.IGNORECASE), "intern"),
    (re.compile(r"\babschlussarbeiten\b", re.IGNORECASE), "theses"),
    (re.compile(r"\babschlussarbeit(s)?\b", re.IGNORECASE), "thesis"),
    (re.compile(r"\bfacharbeiten\b", re.IGNORECASE), "thesis projects"),
    (re.compile(r"\bfacharbeit(s)?\b", re.IGNORECASE), "thesis project"),
    (re.compile(r"\bwerkstudentin\b", re.IGNORECASE), "working student"),
    (re.compile(r"\bwerkstudenten\b", re.IGNORECASE), "working students"),
    (re.compile(r"\bwerkstudent(s)?\b", re.IGNORECASE), "working student"),
    # -- conteudo (base: CONTENT_TRANSLATIONS do dedup, agora p/ exibicao)
    (re.compile(r"\blieferketten\b", re.IGNORECASE), "supply chains"),
    (re.compile(r"\blieferkette\b", re.IGNORECASE), "supply chain"),
    (re.compile(r"\blogistik\b", re.IGNORECASE), "logistics"),
    (re.compile(r"\beinkauf(s)?\b", re.IGNORECASE), "purchasing"),
    (re.compile(r"\bbeschaffung(s)?\b", re.IGNORECASE), "procurement"),
    (re.compile(r"\blager\b", re.IGNORECASE), "warehouse"),
    (re.compile(r"\bversand\b", re.IGNORECASE), "shipping"),
    (re.compile(r"\bproduktion\b", re.IGNORECASE), "production"),
    (re.compile(r"\bfertigung\b", re.IGNORECASE), "manufacturing"),
    (re.compile(r"\bdaten\b", re.IGNORECASE), "data"),
    (re.compile(r"\bdatenanalyse(n)?\b", re.IGNORECASE), "data analytics"),
    (re.compile(r"\binformatik\b", re.IGNORECASE), "computer science"),
    (re.compile(r"\bkuenstliche\b", re.IGNORECASE), "artificial"),
    (re.compile(r"\bkünstliche\b", re.IGNORECASE), "artificial"),
    (re.compile(r"\bintelligenz\b", re.IGNORECASE), "intelligence"),
    (re.compile(r"\bvertrieb(s)?\b", re.IGNORECASE), "sales"),
    (re.compile(r"\bbuchhaltung\b", re.IGNORECASE), "accounting"),
    (re.compile(r"\bfinanzen\b", re.IGNORECASE), "finance"),
    (re.compile(r"\bstrategisch(e|er|es|em|en)?\b", re.IGNORECASE), "strategic"),
]


def _smart_case(matched: str, repl: str) -> str:
    """Maiusculiza a reposicao como o termo casado comeca.

    "Werkstudent" -> "Working student"; "WERKSTUDENT" (todo caps, >1 char)
    -> "WORKING STUDENT"; "werkstudent" -> "working student".
    """
    if not repl:
        return repl
    if matched.isupper() and len(matched) > 1:
        return repl.upper()
    if matched[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def title_en(title: str | None) -> str | None:
    """Titulo DE -> EN so de EXIBICAO (deterministico, offline).

    Regras da spec F12 T1:
    - ``None``/vazio -> ``None`` (sem linha EN);
    - termo fora do dicionario fica como esta (traducao parcial honesta);
    - titulo ja-EN nao muda (nenhum padrao casa) — o chamador decide nao
      renderizar linha EN quando o retorno e IDENTICO ao original;
    - case-insensitive com smart-case (``_smart_case``);
    - o dicionario DISPLAY e independente do ``dedup.TYPE_EQUIVALENCES``
      (guarda: aqui Praktikum = internship, NUNCA "working student").
    """
    if not title:
        return None
    text = str(title)
    out = text
    for pattern, repl in _DISPLAY_RULES:
        out = pattern.sub(lambda m, r=repl: _smart_case(m.group(0), r), out)
    return out or None


# ---------------------------------------------------------------------------
# Tarefa 2 — cache persistente de traducoes (runtime; data/ gitignored)
# ---------------------------------------------------------------------------

# Nome do arquivo dentro de data/ (gitignored por construcao: nunca
# versionado, nunca publicado). A chave do mapa e o ``job["id"]`` canonico
# do pipeline: e estavel entre runs (id = <company>|<source>:<ats_id>),
# e o MESMO id usado pelo render (data-*), e sobrevive a repostagens ao
# contrario de posted_at. URL normalizada seria alternativa, mas o id e o
# que o render JA tem em maos (zero custo de recomputacao) e o que a
# ferramenta seleciona (--job-id) — sem caminho de traducao de chave.
CACHE_FILE_NAME = "translation_cache.json"

# Entradas do cache: {"<job_id>": {"en": str, "ts": epoch}}. Schema e o da
# spec (ts = time.time() na gravacao; consumo best-effort nunca o interpreta
# — e registro de frescor para auditoria do dono).


def load_translation_cache(path: Path | str | None) -> dict:
    """Le o cache best-effort: ausente/corrompido/nao-dict -> ``{}``.

    O render NUNCA quebra por causa do cache (contrato F12 §3: "ausente ou
    corrompido, nada muda, nada quebra"). Valores invalidos (entrada que nao
    e dict / sem "en") sao descartados silenciosamente — um cache sujo nao
    pode poluir a pagina.
    """
    if not path:
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(value.get("en"), str) \
                and value["en"].strip():
            out[str(key)] = {"en": value["en"], "ts": value.get("ts")}
    return out


def save_translation_cache(path: Path | str, cache: dict) -> None:
    """Grava o cache ATOMICAMENTE (padrao ``_write_atomic`` do cli.py).

    Temporario no MESMO diretorio + ``os.replace``: o cache nunca fica pela
    metade (a ferramenta pode ser interrompida entre vagas). Escrever em
    ``data/`` e permitido SOMENTE a esta funcao chamada pela ferramenta
    on-demand — testes usam tmp_path, jamais ``data/`` real.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{os.getpid()}.tmp"
    tmp.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, target)


def cached_translation(cache: dict | None, job_id: str | None) -> str | None:
    """Texto EN em cache para a vaga (ou ``None``). View best-effort."""
    if not cache or not job_id:
        return None
    entry = cache.get(str(job_id))
    if isinstance(entry, dict) and isinstance(entry.get("en"), str):
        text = entry["en"].strip()
        return text or None
    return None


# ---------------------------------------------------------------------------
# Tarefa 2 — traducao LLM sob demanda (padrao do enrichment/llm.py)
# ---------------------------------------------------------------------------

# Cap de entrada: mesmo criterio do spike/runner (12k chars — a mediana
# medida das descricoes hidratadas e ~3k; o cap protege o max_tokens de
# saida em anuncios gigantes). Acima disso o texto e cortado e a entrada
# marca truncated=True (a ferramenta avisa; o cache guarda o que foi
# traduzido de fato).
MAX_INPUT_CHARS = 12_000

LLM_TIMEOUT_S = 290  # mesmo padrao do enrichment/llm.py


TRANSLATION_PROMPT = """You are a professional translator. Translate the following job posting description into English. If a sentence is already in English, keep it as is. Translate faithfully: preserve every fact, requirement, number, date, salary, name and URL exactly; do not summarize, do not add, do not infer, do not invent anything. Keep the original tone and the paragraph breaks.

Output ONLY the English translation as plain text. No commentary, no markdown, no quotes around the text.

TEXT TO TRANSLATE:
"""


def build_translation_prompt(text: str) -> str:
    """Prompt final (constante + texto ja normalizado/cortado)."""
    return TRANSLATION_PROMPT + text


def parse_llm_text(content: str) -> str:
    """Limpa a saida da LLM (adaptacao honesta do ``parse_llm_json``).

    Aqui a saida e TEXTO, nao JSON — entao nao ha ``raw_decode``: descarta
    think-blocks, code fences, e um preambulo de 1 linha tipo "Here is the
    translation:"; o resto e texto traduzido. Nao inventa conteudo: se a
    resposta vier vazia, o chamador trata como ``empty_content`` (retryable).
    """
    tag_open = chr(60) + "think" + chr(62)
    tag_close = chr(47) + "think" + chr(62)
    cleaned = re.sub(
        re.escape(tag_open) + r".*?" + re.escape(tag_close), "", content,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r"<[a-z]*\s*think[a-z]*\s*>.*?</[a-z]*\s*think[a-z]*\s*>", "", cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(r"```[a-z]*\n?", "", cleaned)
    lines = cleaned.strip().splitlines()
    # Preambulo de 1 linha (deterministico, so a primeira): "Here is the
    # translation:" e variantes. O corpo vive nas linhas seguintes.
    if len(lines) > 1 and re.fullmatch(
        r"(?:here(?: i|')?s?(?: the)? ?(?:english )?translation|translation)"
        r" ?(?:text)?\s*:?",
        lines[0].strip().lower(),
    ):
        lines = lines[1:]
    return "\n".join(lines).strip()


def translate_text(
    key: str,
    text: str,
    *,
    transport: Transport | None = None,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str | None, dict | None, float | None, int, str | None, bool]:
    """POST /chat/completions p/ traducao livre (ate 3 tentativas).

    Retorna ``(en_text | None, usage, latency_s, attempts, error, truncated)``.
    Mesma mecanica do ``enrichment/llm.extract`` (retry 429/5xx/rede/vazio,
    backoff injetavel, ``_sanitize`` — a key nunca aparece no erro); a
    diferenca e que o sucesso devolve TEXTO limpo (``parse_llm_text``), nao
    um dict parseado. ``truncated`` = True quando a ENTRADA foi cortada no
    ``MAX_INPUT_CHARS`` (aviso honesto, nao erro).
    """
    transport = transport or RequestsTransport()
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    body = text[:MAX_INPUT_CHARS]
    truncated = len(text) > MAX_INPUT_CHARS
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "user", "content": build_translation_prompt(body)},
        ],
    }
    result: str | None = None
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
            status, resp_text = transport.post(
                CHAT_COMPLETIONS_URL, headers, payload, LLM_TIMEOUT_S
            )
        except Exception as exc:  # requests.RequestException e afins
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
                    data = json.loads(resp_text)
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
                        cleaned = parse_llm_text(content)
                        if not cleaned:
                            error = "empty_content"
                        else:
                            result = cleaned
                            error = None
        if result is not None:
            break
        if error and not error.startswith(RETRYABLE_PREFIXES):
            break

    if error:
        error = _sanitize(error, key)
    return result, usage, latency, attempts, error, truncated
