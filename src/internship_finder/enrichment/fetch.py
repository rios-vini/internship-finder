"""Fetch da pagina oficial da vaga (camada isolada de enrichment).

UMA tentativa por URL (retry fica na camada LLM — martelar servidores de
carreira nao e aceitavel); redirects seguidos; timeout curto de conexao e
longo de leitura; User-Agent identificavel (o mesmo do spike 24/09, ja
aceito pelos ATS visitados). Transport injetavel para testes offline —
nenhum teste toca a rede.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import requests

# User-Agent do spike (identificavel, ja medido contra os ATS do dataset).
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)
FETCH_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"}
FETCH_TIMEOUT = (10, 30)  # (conexao, leitura) — mesmo padrao do spike

# Texto util minimo para extracao (abaixo disso a pagina nao vale LLM).
MIN_USEFUL_TEXT = 200

# Marcadores de app JS client-side (shell de SPA sem conteudo de vaga).
_JS_MARKERS = (
    "__NEXT_DATA__",
    'id="root"',
    'id="app"',
    "window.__INITIAL_STATE__",
    "data-reactroot",
    "ng-app",
)


@dataclass
class FetchResult:
    """Saida do fetch: status/final_url/html quando ha resposta; senao erro.

    ``error`` usa marcadores curtos por tipo: ``timeout`` para
    requests.Timeout e ``fetch_error:<ExceptionName>`` para as demais —
    a chave de API nunca passa por aqui (fetch nao a conhece).
    """

    http_status: int | None
    final_url: str | None
    html: str | None
    error: str | None


class Transport(Protocol):
    """Contrato do transporte HTTP injetavel (testes injetam fakes)."""

    def get(self, url, headers, timeout) -> tuple[int, str, str]: ...

    def post(self, url, headers, payload, timeout) -> tuple[int, str]: ...


class RequestsTransport(Transport):
    """Transport real (requests). Interface estavel para injecao em testes:

    - ``get(url, headers, timeout)`` -> ``(status, text, final_url)``
    - ``post(url, headers, payload, timeout)`` -> ``(status, text)``
    """

    def get(self, url, headers, timeout):
        resp = requests.get(
            url, headers=headers, timeout=timeout, allow_redirects=True
        )
        return resp.status_code, resp.text, resp.url

    def post(self, url, headers, payload, timeout):
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        return resp.status_code, resp.text


def fetch_page(url: str, transport: Transport | None = None) -> FetchResult:
    """GET de UMA pagina: uma unica tentativa, excecoes capturadas por tipo.

    Timeout de rede -> ``timeout``; qualquer outra ``RequestException`` ->
    ``fetch_error:<nome>``. Sem URL -> ``fetch_error:no_url``. O runner
    nunca deixa uma URL problematica abortar o lote.
    """
    transport = transport or RequestsTransport()
    if not url or not str(url).strip():
        return FetchResult(None, None, None, "fetch_error:no_url")
    try:
        status, html, final_url = transport.get(
            str(url), FETCH_HEADERS, FETCH_TIMEOUT
        )
    except requests.Timeout:
        return FetchResult(None, None, None, "timeout")
    except requests.RequestException as exc:
        return FetchResult(None, None, None, f"fetch_error:{type(exc).__name__}")
    return FetchResult(status, final_url, html, None)


def title_match(title: str | None, text: str) -> float:
    """Fracao dos tokens significativos (>=4 chars) do titulo na pagina.

    Reuso fiel do spike 24/09 (threshold 0.5 no classify_page): caso
    simples, sem dependencia, medido contra o dataset real.
    """
    if not title:
        return 0.0
    tokens = [t.casefold() for t in re.split(r"\W+", title) if len(t) >= 4]
    if not tokens:
        return 0.0
    low = text.casefold()
    return sum(1 for t in tokens if t in low) / len(tokens)


def looks_js_rendered(html: str, text: str) -> bool:
    """Heuristica do spike: shell de app JS sem conteudo de vaga.

    Marco de SPA presente + pouco texto util (app client-side renderiza
    depois e o fetch plain nunca ve a vaga), OU pagina crivada de
    scripts com texto minimo. Paginas server-side renderizadas com
    ``__NEXT_DATA__`` E texto real passam (o gate de texto decide).
    """
    if not html:
        return False
    head = html[:50000]
    marker = any(m in head for m in _JS_MARKERS)
    if marker and len(text) < 2000:
        return True
    return html.count("<script") >= 10 and len(text) < MIN_USEFUL_TEXT


def classify_page(resp: FetchResult, text: str, job: dict) -> str:
    """Classifica o fetch em page_status (spec da fase, por precedencia):

    - excecao de timeout -> ``timeout``; outra excecao -> ``fetch_error``;
    - 404/410 -> ``not_found``; outro nao-200 -> ``http_error``;
    - assinatura de app JS sem conteudo de vaga -> ``js_rendered``;
    - texto util < ~200 chars -> ``empty_content``;
    - redirect ocorreu E o texto nao casa com o titulo da vaga
      (title_match < 0.5) -> ``redirected``;
    - redirect ocorreu mas o conteudo casa com a vaga -> ``ok``
      (o redirect fica auditavel em ``final_url``);
    - sem redirect e conteudo presente -> ``ok``.

    Retorna o valor do enum ``PageStatus`` como str (StrEnum). So ``ok``
    prossegue para a LLM.
    """
    if resp.error:
        if resp.error == "timeout" or resp.error.startswith("timeout"):
            return "timeout"
        return "fetch_error"
    status = resp.http_status
    if status in (404, 410):
        return "not_found"
    if status != 200:
        return "http_error"
    if looks_js_rendered(resp.html or "", text or ""):
        return "js_rendered"
    if len(text or "") < MIN_USEFUL_TEXT:
        return "empty_content"
    original = str(job.get("url") or "")
    if resp.final_url and original and resp.final_url != original:
        if title_match(job.get("title"), text) < 0.5:
            return "redirected"
    return "ok"
