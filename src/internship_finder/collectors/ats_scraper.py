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


def fetch_with_timeout(
    company: Company, timeout: float, include_descriptions: bool
) -> list[dict]:
    """fetch() do scraper com teto de tempo; trava/erro nao derruba o fluxo.

    A excecao levantada carrega o codigo estruturado: timeout do subprocesso
    vira ``CollectionError(TIMEOUT, ...)``; erro vindo do worker, um
    ``CollectionError(code, detail)`` com o codigo do payload estruturado.
    """
    ctx = mp.get_context()
    queue = ctx.Queue()
    proc = ctx.Process(
        target=fetch_worker,
        args=(company, timeout, include_descriptions, queue),
    )
    proc.start()
    deadline = timeout + 25
    try:
        status, payload = queue.get(timeout=deadline)
    except Exception:
        proc.terminate()
        proc.join(timeout=5)
        raise CollectionError(
            TIMEOUT,
            f"scraper {company.ats}/{company.slug} nao respondeu em {deadline:.0f}s (timeout)",
        ) from None
    proc.join(timeout=5)
    if status == "-error":
        code, detail = payload
        raise CollectionError(code, detail) from None
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
