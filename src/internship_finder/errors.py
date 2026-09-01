"""Codigos de erro estruturados para falhas de coleta.

Antes, uma falha virava TEXTO LIVRE (``"RuntimeError: boom"``) carregado pela
mp.Queue e depois no campo ``error`` do registro tenant — sem discriminacao
programatica entre "timeout", "erro de conexao", "falha de fetch" ou "falha de
normalizacao". Este modulo define um vocabulario fixo de codigos (constantes
``str`` simples, como o status do summary) e um **classificador** que mapeia
uma excecao (+ o estagio em que ocorreu) para ``(code, detail)``.

O classificador NUNCA levanta: qualquer excecao desconhecida cai no fallback
``UNKNOWN``. Isso torna seguro classificar no ``fetch_worker`` (subprocesso),
onde um erro de classificacao nao pode derrubar a coleta.

Formato do payload de erro estruturado (na mp.Queue): a tupla
``("-error", code, detail)`` — ``("ok", result)`` para sucesso. ``code`` e uma
das constantes abaixo e ``detail`` e o texto legivel (ex. ``"RuntimeError: boom"``).

Mapeamento excecao -> codigo (minimo, por tipo):
- ``TimeoutError``/``socket.timeout`` (alias do mesmo tipo)  -> ``TIMEOUT``
- ``requests.exceptions.ConnectionError`` e ``requests.exceptions.ConnectTimeout``,
  ``httpx.ConnectError``/``httpx.ConnectTimeout``, ``urllib3.exceptions.
  ConnectTimeoutError``/``NewConnectionError``, e subclasses do builtin
  ``ConnectionError`` -> ``CONNECTION_ERROR``
- erros de rede no estagio ``fetch`` (``ScraperError``/``CompanyNotFoundError``
  do ats-scrapers, falhas HTTP/request em geral — que nao sejam connection) -> ``FETCH_ERROR``
- falhas do estagio de adaptacao (``adapter.to_job``) -> ``NORMALIZATION_ERROR``
- qualquer outra -> ``UNKNOWN``
"""

from __future__ import annotations

import socket

TIMEOUT = "TIMEOUT"
CONNECTION_ERROR = "CONNECTION_ERROR"
FETCH_ERROR = "FETCH_ERROR"
NORMALIZATION_ERROR = "NORMALIZATION_ERROR"
UNKNOWN = "UNKNOWN"

# Estagios de coleta que o classificador entende.
FETCH_STAGE = "fetch"
NORMALIZE_STAGE = "normalize"

# Caminhos "seguros" para bibliotecas opcionais de HTTP: nunca importar no
# topo (requests/httpx/urllib3 podem nao estar instalados em ambientes enxutos).
_requests = None
_httpx = None
_urllib3 = None


def _connection_error_types() -> tuple[type, ...]:
    """Tipos de excecao de conexao (lazy; importa so quando classificar)."""
    global _requests, _httpx, _urllib3
    types = [ConnectionError]  # subtipos do builtin sao capturados via isinstance
    if _requests is None:
        try:
            import requests  # type: ignore
            _requests = requests
        except ImportError:
            _requests = False
    if _requests:
        rex = _requests.exceptions
        for t in ("ConnectionError", "ConnectTimeout"):
            if hasattr(rex, t):
                types.append(getattr(rex, t))
    if _httpx is None:
        try:
            import httpx  # type: ignore
            _httpx = httpx
        except ImportError:
            _httpx = False
    if _httpx:
        hx = _httpx
        for t in ("ConnectError", "ConnectTimeout"):
            if hasattr(hx, t):
                types.append(getattr(hx, t))
    if _urllib3 is None:
        try:
            import urllib3  # type: ignore
            _urllib3 = urllib3
        except ImportError:
            _urllib3 = False
    if _urllib3:
        ux = _urllib3.exceptions
        for t in ("ConnectTimeoutError", "NewConnectionError", "ConnectionError"):
            if hasattr(ux, t):
                types.append(getattr(ux, t))
    return tuple(types)


def is_connection_error(exc: Exception) -> bool:
    """Uma falha de conexao (network-level)? Nunca levanta."""
    if isinstance(exc, ConnectionError):
        return True
    for t in _connection_error_types():
        try:
            if isinstance(exc, t):
                return True
        except TypeError:
            continue
    return False


def _detail(exc: BaseException) -> str:
    """Texto legivel de uma excecao (``RuntimeError: boom``). Nunca levanta."""
    return f"{type(exc).__name__}: {exc}"


def classify_exception(exc: BaseException, stage: str | None = None) -> tuple[str, str]:
    """Classifica ``exc`` em ``(code, detail)``; fallback ``UNKNOWN``.

    ``stage`` (opcional) e ``"fetch"`` ou ``"normalize"``: quando fornecido,
    limita a classificacao de falhas HTTP/request ao estagio certo. Uma falha
    nao-conexao no estagio ``normalize`` (ex.: topo-valor inesperado na
    adaptacao) vira ``NORMALIZATION_ERROR``; no estagio ``fetch``, ``FETCH_ERROR``.
    Qualquer excecao desconhecida (ou tipo inesperado) cai em ``UNKNOWN``.
    """
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return TIMEOUT, _detail(exc)

    if is_connection_error(exc):
        return CONNECTION_ERROR, _detail(exc)

    # Falhas nao-conexao: o sentido do codigo depende do estagio.
    if stage == NORMALIZE_STAGE:
        return NORMALIZATION_ERROR, _detail(exc)

    if stage == FETCH_STAGE:
        return FETCH_ERROR, _detail(exc)

    return UNKNOWN, _detail(exc)


class CollectionError(Exception):
    """Excecao carregando o codigo estruturado da falha de coleta.

    Levantada por ``fetch_with_timeout`` para atravesar o limite do
    subprocesso com o ``code`` (ex.: ``TIMEOUT``) e o ``detail`` (texto
    legivel) juntos. ``__str__`` continua sendo o detalhe legivel, entao
    ``str(exc)`` segue util no log/summary — mesmo sem desempacotar o atributo.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail