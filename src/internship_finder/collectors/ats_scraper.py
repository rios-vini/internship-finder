"""Coleta orientada a empresas: find_company (match exato) -> scraper -> Job.

O ``fetch`` de cada scraper roda em um subprocesso com teto de tempo
(``timeout`` + margem): um tenant que trava ou erra e registrado e nao
derruba o resto do pipeline. O contexto de multiprocessing e o default do
SO (fork no Linux, spawn no Windows).
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import time
from queue import Empty as _Empty

from ats_scrapers.scrapers import get_scraper

from internship_finder.adapters.ats import AtsJobAdapter
from internship_finder.collectors.company import CompanyCollector
from internship_finder.errors import (
    FETCH_STAGE,
    NORMALIZE_STAGE,
    TIMEOUT,
    UNKNOWN,
    CollectionError,
    classify_exception,
)
from internship_finder.geocoding import flush_cache
from internship_finder.models.company import Company
from internship_finder.models.job import Job

log = logging.getLogger(__name__)

# Scrapers cujo "slug" e na verdade a URL completa de careers (o slug da
# base, ex.: "jobs" p/ SAP/ZF no successfactors, nao e usavel sozinho).
URL_SLUG_ATS = {"successfactors", "workday", "taleo", "icims", "phenom"}

# Margem (segundos) somada ao ``timeout`` do scraper antes de declarar o
# subprocesso travado (ACH-07). Parametrizavel via ``fetch_with_timeout(...,
# margin=...)`` — os testes usam uma margem pequena para timeout rapido sem
# alterar o comportamento de producao (default 25).
TIMEOUT_MARGIN = 25.0

# Tempo (segundos) de cada estagio do encerramento forçado: ``terminate()``
# (SIGTERM) tem uma janela de grace para chamar a cleanup normal; se o
# processo ignorar/sobreviver, ``kill()`` (SIGKILL) e o fallback final.
TERMINATE_GRACE = 5.0
KILL_GRACE = 2.0


def scraper_slug(company: Company) -> str:
    """Slug efetivo a passar ao construtor do scraper."""
    if company.ats in URL_SLUG_ATS and company.url:
        return company.url
    return company.slug


def fetch_worker(
    company: Company, timeout: float, include_descriptions: bool, queue: mp.Queue
) -> None:
    """Roda o scraper e devolve as vagas normalizadas (dicts) pela queue.

    A normalizacao usa a ``Company`` real (source/slug corretos) e acontece
    uma unica vez — a re-adaptacao apos a queue duplicaria prefixos no ``id``.

    O payload de erro na queue e ESTRUTURADO (sem texto livre): a tupla
    ``("-error", code, detail)``, com ``code``/``detail`` vindos de
    ``classify_exception`` por estagio (fetch vs normalize).
    """
    try:
        try:
            scraper = get_scraper(
                company.ats,
                scraper_slug(company),
                timeout=timeout,
                include_descriptions=include_descriptions,
            )
            jobs = scraper.fetch()
        except Exception as exc:  # noqa: BLE001 - falha do estagio de fetch
            code, detail = classify_exception(exc, stage=FETCH_STAGE)
            queue.put(("-error", code, detail))
            return
        try:
            adapter = AtsJobAdapter()
            result = [adapter.to_job(j, company).to_dict() for j in jobs]
            # Persiste o cache de geocoding (resultados/respostas) que este
            # subprocesso possa ter gravado durante a adaptacao. O cache e
            # file-based, entao o write propaga para os demais processos.
            flush_cache()
        except Exception as exc:  # noqa: BLE001 - falha do estagio de adaptacao
            code, detail = classify_exception(exc, stage=NORMALIZE_STAGE)
            queue.put(("-error", code, detail))
            return
        queue.put(("ok", result))
    except Exception as exc:  # noqa: BLE001 - nem a classificacao pode derrubar
        queue.put(("-error", UNKNOWN, f"{type(exc).__name__}: {exc}"))


def _shutdown(proc: mp.Process, queue: mp.Queue) -> None:
    """Encerra ``proc`` e a queue de forma completa, em QUALQUER desfecho.

    Fluxo (ACH-07): ``terminate()`` (SIGTERM) -> ``join(grace)`` -> se ainda
    vivo, ``kill()`` (SIGKILL) -> ``join(2)``. A queue e drenada
    (``get_nowait`` ate ``Empty``) e depois fechada com ``close()`` +
    ``join_thread()``, sem deixar item residual nem thread de feeder viva.
    """
    proc.terminate()
    proc.join(timeout=TERMINATE_GRACE)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=KILL_GRACE)
    try:
        while True:
            queue.get_nowait()
    except _Empty:
        pass
    queue.close()
    queue.join_thread()


def _wait_worker(proc: mp.Process, queue: mp.Queue, deadline: float) -> tuple[str, object | None]:
    """Espera o primeiro item da queue, monitorando a morte do worker.

    Retorna ``(outcome, item)``:
      - ``("ok", ("ok", result))``          — item entregue/consumido;
      - ``("ok", ("-error", code, detail))``— item de erro estruturado;
      - ``("timeout", None)``               — queue vazia ate o ``deadline``;
      - ``("dead", None)``                  — worker morreu sem mensagem
        (``exitcode != 0``) detectado ANTES do deadline via ``is_alive``.
    A espera usa ``queue.get(timeout=0.2)`` como poller leve (barato, acorda a
    cada 200ms) e checa o exitcode para nao gastar a margem inteira quando o
    subprocesso ja caiu (os._exit/segfault/kill; o ``except`` nao captura).
    """
    while True:
        if not proc.is_alive():
            exitcode = proc.exitcode
            if exitcode is not None and exitcode != 0 and queue.empty():
                # Morreu sem deixar item na queue -> nao ha o que ler.
                return "dead", None
            # exitcode == 0 (terminou normal) ou ha item residual do feeder:
            # segue e tenta ler; so declara morte quando a queue esta vazia.
        try:
            item = queue.get(timeout=0.2)
            return "ok", item
        except _Empty:
            if time.monotonic() >= deadline:
                return "timeout", None


def fetch_with_timeout(
    company: Company,
    timeout: float,
    include_descriptions: bool,
    margin: float = TIMEOUT_MARGIN,
) -> list[dict]:
    """fetch() do scraper com teto de tempo; trava/erro nao derruba o fluxo.

    O ciclo de vida do subprocesso (ACH-07) distingue 4 desfechos de forma
    observavel (mensagens claras no ``detail``/log), SEM adicionar status:

    - **timeout** — a queue ficou vazia ate o ``deadline`` (``timeout`` +
      margem): ``CollectionError(TIMEOUT, ...)``.
    - **worker morto** — o subprocesso morreu sem mandar mensagem
      (``os._exit``/segfault/kill; o ``except`` do worker nao captura): detectado
      VIA ``exitcode``/``is_alive`` ANTES do deadline e reportado como
      ``CollectionError(UNKNOWN, \"worker morreu (exitcode N) sem mensagem\")`` —
      distinto de timeout, sem gastar a margem inteira.
    - **erro do worker** — payload estruturado ``("-error", code, detail)``:
      ``CollectionError(code, detail)`` do P1 #7.
    - **sucesso** — ``("ok", result)``: payload devolvido.

    Em TODOS os caminhos o processo e encerrado (terminate -> join -> kill ->
    join) e a queue drenada/fechada — sem orfaos.

    ``margin`` (opcional) parametriza a margem de timeout; default ``25``
    (``TIMEOUT_MARGIN``), inalterado em producao.
    """
    ctx = mp.get_context()
    queue = ctx.Queue()
    proc = ctx.Process(
        target=fetch_worker,
        args=(company, timeout, include_descriptions, queue),
    )
    proc.start()
    tag = f"{company.ats}/{company.slug}"
    deadline = time.monotonic() + timeout + margin
    try:
        outcome, item = _wait_worker(proc, queue, deadline)
        if outcome == "dead":
            raise CollectionError(
                UNKNOWN,
                f"worker {tag} morreu (exitcode {proc.exitcode}) sem mensagem",
            ) from None
        if outcome == "timeout":
            raise CollectionError(
                TIMEOUT,
                f"scraper {tag} nao respondeu em {timeout + margin:.0f}s (timeout)",
            ) from None
        status, payload = item[0], item[1]
        if status == "-error":
            code, detail = item[1], item[2]
            raise CollectionError(code, detail) from None
    finally:
        _shutdown(proc, queue)
    return payload


def collect_company(
    name: str,
    timeout: float = 45.0,
    include_descriptions: bool = False,
    limit: int = 0,
) -> tuple[list[Job], dict]:
    """Coleta as vagas de ``name`` (match exato na base do ats-scrapers).

    Retorna ``(jobs, summary)``; ``summary`` distingue o estado de cada
    tenant, para que "0 vagas" (EMPTY) nao seja confundido com erro:
    - ``ok``      [(source, n, tempo)]     — SUCCESS (>=1 vaga coletada)
    - ``empty``   [(source, tempo)]        — EMPTY (tenant respondeu, 0 vagas)
    - ``timeout`` [(source, code, erro)]   — TIMEOUT (nao respondeu no prazo)
    - ``failed``  [(source, code, erro)]   — ERROR (excecao de coleta)
    - ``skipped`` [source]                 — sem scraper registrado
    - ``not_found`` (bool)                 — empresa sem match exato na base

    ``code`` e o codigo estruturado de ``errors`` (ex.: ``TIMEOUT``,
    ``CONNECTION_ERROR``) e ``erro`` o detalhe legivel (``str(exc)``); os dois
    juntos (e nao texto livre sozinho) propagam da queue ate o registro JSONL.

    Erros/timeouts sao registrados e o fluxo segue para as proximas
    empresas/tenants (nenhuma excecao e engolida silenciosamente).
    """
    collector = CompanyCollector()
    companies = collector.find_company(name)
    summary: dict = {
        "ok": [],
        "empty": [],
        "timeout": [],
        "failed": [],
        "skipped": [],
        "not_found": False,
    }
    if not companies:
        log.warning("[%s] nao encontrada na base (match exato)", name)
        summary["not_found"] = True
        return [], summary

    jobs: list[Job] = []
    for company in companies:
        if not collector.has_scraper(company):
            log.warning("[%s] %s sem scraper registrado; pulando", name, company.source)
            summary["skipped"].append(company.source)
            continue
        t0 = time.time()
        try:
            raw_jobs = fetch_with_timeout(company, timeout, include_descriptions)
            if limit and len(raw_jobs) > limit:
                raw_jobs = raw_jobs[:limit]
            # Os dicts ja saem normalizados (single-pass no subprocesso).
            converted = [Job(**d) for d in raw_jobs]
            dt = time.time() - t0
            if converted:
                jobs.extend(converted)
                summary["ok"].append((company.source, len(converted), f"{dt:.1f}s"))
                log.info("[%s] %s: %d vagas em %.1fs", name, company.source, len(converted), dt)
            else:
                summary["empty"].append((company.source, f"{dt:.1f}s"))
                log.info("[%s] %s: 0 vagas (EMPTY) em %.1fs", name, company.source, dt)
        except CollectionError as exc:
            code = exc.code if exc.code else UNKNOWN
            if code == TIMEOUT:
                summary["timeout"].append((company.source, code, exc.detail))
                log.error("[%s] %s timeout: %s", name, company.source, exc)
            else:
                summary["failed"].append((company.source, code, exc.detail))
                log.error("[%s] %s falhou: %s", name, company.source, exc)
        except TimeoutError as exc:  # noqa: BLE001 - builtin str do mock/pista
            code, detail = classify_exception(exc)
            summary["timeout"].append((company.source, code, detail))
            log.error("[%s] %s timeout: %s", name, company.source, exc)
        except Exception as exc:  # noqa: BLE001 - segue para as proximas
            code, detail = classify_exception(exc)
            summary["failed"].append((company.source, code, detail))
            log.error("[%s] %s falhou: %s", name, company.source, exc)
    return jobs, summary
