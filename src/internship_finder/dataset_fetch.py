"""Camada de fetch PROPRIA do estagio dataset (F76, E1).

Porta de entrada UNICA para a rede do estadio dataset: manifest + fatias
passam por aqui (o ``dataset_source`` delega; a injecao ``http_fetch`` dos
testes continua valendo acima desta camada). Antes da F76 o urllib cru
deixava tudo implicito: HTTPError generico virava "fatia falhou (...)" sem
codigo de status, nao havia retry de NENHUMA natureza, e um 200-falso (HTML
de WAF/manutencao no lugar do CSV) so era apanhado INDIRECTAMENTE pelo
mismatch de sha256 da F80 — ou pior, processado como CSV vazio quando o
manifest injetado nao declara hash.

Equivalente proprio dos padroes do upstream ``ats_scrapers.fetch``
(medidos no clone kalil0321/ats-scrapers @ 6b44a1b, v0.3.0):

- ``MalformedJSONError`` do upstream (2xx cujo corpo nao e JSON — pagina de
  WAF/maintenance) -> aqui: :class:`MalformedJSONError` p/ o manifest e
  :class:`MalformedCSVError` p/ as fatias, com mensagem explicita do comeco
  do corpo. Ambas subclass ``ValueError`` (mesma decisao do upstream: o
  contrato F80 — ``fetch_manifest`` levanta ValueError claro em corpo
  nao-JSON — segue de pe sem edicao nos vizinhos).
- ``_BLOCKED_STATUSES = {403, 406}`` -> fail-loud NAO-retryavel
  (:class:`BlockedHTTPStatusError`): o load balancer/WAF esta bloqueando o
  cliente; retry so esconderia o bloqueio novo.
- ``_RETRYABLE_STATUSES = {408, 429} | 5xx`` -> backoff exponencial com
  ``Retry-After`` NUMERICO respeitado; esgotado ->
  :class:`RetryExhaustedError`. Formato HTTP-date do header e ignorado
  (mesma decisao do upstream — so o numerico e deterministico).
- qualquer outro 4xx -> :class:`HTTPStatusError` explicito nao-retryavel
  (o 404 “CompanyNotFoundError” do upstream nao se aplica: URLs do dataset
  vem do manifest, 404 = arquivo sumido, nao empresa inexistente).

Desvios CONSCIENTES do upstream (documentados, nao copias):

- ``Retry-After`` e respeitado ate o teto ``DEFAULT_RETRY_AFTER_CEILING``.
  O upstream espera sem teto porque e scraper por-tenant; o estagio dataset
  e um LOTE de ~63 fatias num cron diario com budget de 1800s ENTRE fatias
  — um Retry-After de horas travaria o run inteiro dentro da flock. O teto
  protege o orcamento do estagio; esgotar tentativas degrada a fatia
  (failed) como qualquer falha, e o run segue (best-effort da F3).
- Transporte e ``urllib`` stdlib sincrono (mesma dependencia-zero do
  ``dataset_source``/``direct_fetch``), nao httpx async: o estagio e um
  lote sequencial; engine cloak/escalacao de TLS nao se aplica ao R2
  (o UA custom ``internship-finder/0.1`` e aceito desde a F3 — o probe
  da investigacao 26/09 mostrou que o REJEITADO e o UA default do urllib).

Esquemas sem status HTTP (``file://`` dos testes) nao passam pelo mapa de
retry: abrem uma unica vez e seguem direto — mas o parse/sniff de corpo
continua valendo (corpo HTML via file:// levanta como 200-falso igual).

Testes (``scripts/test_f76.py``): 100% offline — opener scriptado injeta
respostas (status/headers/corpo) e um sleep coletado registra os delays
sem esperar de verdade.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (defaults so usados quando o chamador nao pinha — dataset_source
# pinha o timeout dele, DATASET_HTTP_TIMEOUT=120s, nos DOIS pontos)
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 3  # tentativas TOTAIS por request (a 1a inclusa)
# Base igual a do direct_fetch (F4) — a casa ja tinha este numero; o
# upstream usa 1.5. Teto do BACKOFF igual ao upstream (30s).
DEFAULT_RETRY_BASE_DELAY = 2.0
DEFAULT_MAX_RETRY_DELAY = 30.0
# Teto do Retry-After (desvio consciente — ver docstring do modulo).
DEFAULT_RETRY_AFTER_CEILING = 60.0

# Mapa de status — espelho do ats_scrapers.fetch (medido, v0.3.0).
RETRYABLE_STATUSES: frozenset[int] = frozenset({408, 429}) | frozenset(
    range(500, 600)
)
BLOCKED_STATUSES: frozenset[int] = frozenset({403, 406})

# 200-falso: farejamento do PRIMEIRO chunk. Gate apertado de proposito: so
# considera WAF o corpo que (a) comeca com "<" apos BOM/brancos e (b) carrega
# um marcador HTML canonico na janela. O header do CSV do dataset comeca com
# "ats_id,title,..." — falso positivo so com nome de coluna "<html...>".
_HTML_MARKERS: tuple[bytes, ...] = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<body",
    b"<script",
    b"<title",
)
_SNIFF_WINDOW = 2048
_CHUNK_BYTES = 1024 * 1024  # 1 MiB — mesmo passo da F80

# UA provado contra o R2 em producao desde a F3 (o default do urllib e 403).
_USER_AGENT = "internship-finder/0.1"

Opener = Callable[..., Any]


# ---------------------------------------------------------------------------
# Erros — SEMPRE explicitos, SEMPRE com a URL
# ---------------------------------------------------------------------------


class DatasetFetchError(Exception):
    """Base dos erros de fetch do estagio dataset (carrega a URL)."""

    def __init__(self, message: str, *, url: str) -> None:
        super().__init__(message)
        self.url = url


class MalformedJSONError(DatasetFetchError, ValueError):
    """2xx cujo corpo NAO e JSON — o 200-falso (WAF/manutencao HTML).

    Subclass de ``ValueError`` (mesma decisao do upstream ``MalformedJSONError``
    subclass ValueError): mantem o contrato F80 de ``fetch_manifest`` — corpo
    nao-JSON levanta ValueError claro com o comeco do corpo.
    """


class MalformedCSVError(DatasetFetchError, ValueError):
    """2xx cujo corpo parece HTML de WAF/manutencao onde se espera CSV.

    O 200-falso na FATIA: antes da F76 ele baixava inteiro e morria longe da
    causa (mismatch de sha256, ou pior, prefilter lendo HTML como CSV). O
    farejamento aborta no PRIMEIRO chunk, antes de escrever no disco.
    """


class BlockedHTTPStatusError(DatasetFetchError):
    """403/406 — o load balancer/WAF bloqueia o cliente; fail-loud.

    NAO-retryavel por design (mesma regra do upstream): retry esconderia um
    bloqueio novo em vez de denuncia-lo. Se o R2 comecar a bloquear o UA, o
    estagio falha claro no registro, nao lento e mudo.
    """


class HTTPStatusError(DatasetFetchError):
    """Status final explicito nao-retryavel (404, 410, 400...)."""

    def __init__(self, message: str, *, url: str, status: int) -> None:
        super().__init__(message, url=url)
        self.status = status


class RetryExhaustedError(DatasetFetchError):
    """Status retryavel (408/429/5xx) ou falha de rede esgotou as tentativas."""

    def __init__(self, message: str, *, url: str, status: int | None = None) -> None:
        super().__init__(message, url=url)
        self.status = status


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------


class _Response:
    """Resposta uniformizada: status (None = esquema sem HTTP, ex. file://),
    ``headers.get`` e ``read``. Normaliza o HTTPError do urlopen (4xx/5xx
    chegam como EXCECAO) e as respostas fake dos testes no MESMO formato."""

    __slots__ = ("status", "headers", "_stream")

    def __init__(self, stream: Any, *, status: int | None, headers: Any) -> None:
        self._stream = stream
        self.status = status
        self.headers = headers

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _open_once(url: str, *, timeout: float, opener: Opener | None) -> _Response:
    """UMA tentativa de transporte; o loop de retry decide o resto.

    ``opener`` (injecao dos testes) substitui o ``urlopen`` inteiro e recebe
    o ``Request`` montado — contratos: devolve file-like com ``.status`` ou
    levanta (HTTPError/URLError/qualquer excecao de rede). O default e o
    ``urlopen`` stdlib.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    if opener is not None:
        resp = opener(req, timeout=timeout)
    else:
        resp = urllib.request.urlopen(req, timeout=timeout)
    if isinstance(resp, urllib.error.HTTPError):
        return _Response(resp, status=int(resp.code), headers=resp.headers)
    status = getattr(resp, "status", None) or getattr(resp, "code", None)
    headers = getattr(resp, "headers", None)
    return _Response(
        resp,
        status=int(status) if status is not None else None,
        headers=headers,
    )


def _retry_delay(
    resp: _Response,
    attempt: int,
    *,
    base: float,
    max_delay: float,
    ceiling: float,
) -> float:
    """Delay da proxima tentativa: Retry-After NUMERICO (ate o teto) senao
    backoff exponencial ``base * 2**(attempt-1)`` limitado por ``max_delay``.

    So o numerico e respeitado (mesma regra do upstream); HTTP-date e
    ignorado — sem parse de datas nao deterministicas.
    """
    header: Any = None
    if resp.headers is not None:
        try:
            header = resp.headers.get("Retry-After") or resp.headers.get(
                "retry-after"
            )
        except Exception:  # noqa: BLE001 — headers exoticos nunca derrubam o fetch
            header = None
    if header is not None:
        text = str(header).strip()
        if text.isdigit():
            return min(float(text), ceiling)
    return min(base * 2 ** (attempt - 1), max_delay)


def _open_with_retries(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY,
    retry_after_ceiling: float = DEFAULT_RETRY_AFTER_CEILING,
    sleep: Callable[[float], None] = time.sleep,
    opener: Opener | None = None,
) -> _Response:
    """Abre a URL aplicando o mapa de status do upstream (docstring do modulo).

    Devolve a resposta ABERTA (2xx ou esquema sem status). Levanta
    BlockedHTTPStatusError / HTTPStatusError (imediatos) ou
    RetryExhaustedError (orcamento esgotado). Erros de rede (DNS/timeout/
    conexao) sao retryaveis como 5xx.
    """
    last_error = "sem tentativa registrada"
    for attempt in range(1, max_retries + 1):
        try:
            resp = _open_once(url, timeout=timeout, opener=opener)
        except Exception as exc:  # noqa: BLE001 — camada de transporte
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt >= max_retries:
                raise RetryExhaustedError(
                    f"{url}: falha de rede apos {max_retries} tentativas "
                    f"({last_error})",
                    url=url,
                ) from exc
            sleep(min(retry_base_delay * 2 ** (attempt - 1), max_retry_delay))
            continue
        if resp.status is None or 200 <= resp.status < 300:
            return resp
        if resp.status in BLOCKED_STATUSES:
            raise BlockedHTTPStatusError(
                f"{url}: HTTP {resp.status} — o WAF/load balancer esta "
                "bloqueando o cliente (fail-loud, NAO retryavel)",
                url=url,
            )
        if resp.status in RETRYABLE_STATUSES:
            last_error = f"HTTP {resp.status}"
            if attempt >= max_retries:
                raise RetryExhaustedError(
                    f"{url}: HTTP {resp.status} apos {max_retries} tentativas",
                    url=url,
                    status=resp.status,
                )
            sleep(
                _retry_delay(
                    resp,
                    attempt,
                    base=retry_base_delay,
                    max_delay=max_retry_delay,
                    ceiling=retry_after_ceiling,
                )
            )
            continue
        raise HTTPStatusError(
            f"{url}: HTTP {resp.status} explicito nao-retryavel",
            url=url,
            status=resp.status,
        )
    raise RetryExhaustedError(
        f"{url}: esgotado sem resposta ({last_error})", url=url
    )


# ---------------------------------------------------------------------------
# Farejamento de 200-falso (corpo HTML onde se espera CSV/JSON)
# ---------------------------------------------------------------------------


def _looks_like_html(head: bytes) -> bool:
    """``True`` quando o comeco do corpo e pagina HTML (WAF/manutencao).

    Gate duplo: (a) comeca com ``<`` apos BOM/brancos; (b) marcador HTML
    canonico dentro da janela de farejamento. CSV legitimo nunca comeca com
    ``<`` — a 1a linha e o header do schema (``ats_id,title,...``).
    """
    probe = head[:_SNIFF_WINDOW].lstrip(b"\xef\xbb\xbf \t\r\n\x0b\x0c")
    if not probe.startswith(b"<"):
        return False
    low = probe.lower()
    return any(marker in low for marker in _HTML_MARKERS)


# ---------------------------------------------------------------------------
# API publica (usada pelo dataset_source; testes injetam opener/sleep)
# ---------------------------------------------------------------------------


def fetch_json(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY,
    retry_after_ceiling: float = DEFAULT_RETRY_AFTER_CEILING,
    sleep: Callable[[float], None] = time.sleep,
    opener: Opener | None = None,
    context: str = "resposta",
) -> Any:
    """GET + parse JSON com o mapa de status/retry do modulo.

    200-falso (corpo nao-JSON) -> :class:`MalformedJSONError` com o comeco
    do corpo (~200 chars) — subclass de ``ValueError`` (contrato F80).
    ``context`` e o rotulo do erro (``fetch_manifest`` passa "manifest").
    """
    resp = _open_with_retries(
        url,
        timeout=timeout,
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
        max_retry_delay=max_retry_delay,
        retry_after_ceiling=retry_after_ceiling,
        sleep=sleep,
        opener=opener,
    )
    body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except ValueError as exc:
        snippet = body[:200]
        raise MalformedJSONError(
            f"{context}: 200-falso — corpo nao e JSON ({exc}); "
            f"corpo comeca com: {snippet!r}",
            url=url,
        ) from exc


def download_file(
    url: str,
    dest: Path | str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY,
    retry_after_ceiling: float = DEFAULT_RETRY_AFTER_CEILING,
    sleep: Callable[[float], None] = time.sleep,
    opener: Opener | None = None,
    chunk_bytes: int = _CHUNK_BYTES,
) -> tuple[int, str]:
    """Download em STREAMING para ``dest``; devolve ``(bytes, sha256)``.

    Mesmo contrato da F80: pico de disco = a fatia em download, sha256
    computado DURANTE o streaming (um ``hashlib.update`` por chunk). A
    camada NOVA (F76): status/retry/Retry-After do modulo + 200-falso
    aborta no PRIMEIRO chunk — ANTES de abrir ``dest`` e de baixar o resto
    (uma pagina de WAF de N GB nunca chega ao disco).
    """
    resp = _open_with_retries(
        url,
        timeout=timeout,
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
        max_retry_delay=max_retry_delay,
        retry_after_ceiling=retry_after_ceiling,
        sleep=sleep,
        opener=opener,
    )
    dest_path = Path(dest)
    digest = hashlib.sha256()
    total = 0
    chunk = resp.read(chunk_bytes)
    if chunk and _looks_like_html(chunk):
        snippet = chunk[:200]
        raise MalformedCSVError(
            f"{url}: 200-falso — corpo HTML (WAF/manutencao) onde se "
            f"espera CSV; corpo comeca com: {snippet!r}",
            url=url,
        )
    with dest_path.open("wb") as fh:
        while chunk:
            fh.write(chunk)
            digest.update(chunk)
            total += len(chunk)
            chunk = resp.read(chunk_bytes)
    return total, digest.hexdigest()
