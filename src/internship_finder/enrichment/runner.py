"""Runner sequencial da camada de enrichment (Fase enrichment v1).

Fluxo por vaga (processamento INDEPENDENTE — excecao de uma vaga vira
record de erro e o lote segue; latencia real 16-290s/vaga torna o
sequencial a unica opcao segura contra rate limit):

  selecao deterministica -> fetch -> normalizacao -> cache (job_id +
  final_url + content_hash) -> extracao GLM-5.3-Flash -> EnrichmentRecord
  -> upsert incremental no JSONL (escrita atomica).

A LLM apenas enriquece com evidencia — NUNCA decide eligibility, score ou
ranking; nenhum modulo existente importa este pacote.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from internship_finder import app_intel
from internship_finder.enrichment import fetch as fetch_mod
from internship_finder.enrichment import html_norm
from internship_finder.enrichment import llm
from internship_finder.enrichment.schema import (
    CONTENT_LIMIT,
    EnrichmentRecord,
    build_record,
    fields_from_llm,
    hash_content,
)
from internship_finder.enrichment.store import EnrichmentStore

DEFAULT_TOP = 16
DEFAULT_EXTRA_WA = 4
DEFAULT_EXTRA_NODES = 4
DEFAULT_SLEEP_FETCH = 2.0


def now_iso() -> str:
    """Timestamp ISO UTC (segundos) — fetched_at/extracted_at."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def select_sample(
    jobs: list,
    top: int = DEFAULT_TOP,
    extra_wa: int = DEFAULT_EXTRA_WA,
    extra_nodesc: int = DEFAULT_EXTRA_NODES,
) -> list:
    """Amostra deterministica e representativa, sem rede e sem LLM.

    Ordena por ``(score desc, id desc)`` e compoe: top N + primeiras M fora
    do top com work authorization detectada no feed (detector atual, read-
    only via ``app_intel.work_authorization``) + primeiras M sem
    ``description`` no feed (a pagina oficial e a unica fonte para elas).
    Duas chamadas identicas -> mesmo resultado; ids unicos (cada vaga entra
    em no maximo um bucket). Amostra, nao corpus: nao processamos as 406
    indiscriminadamente (latencia/tokens medidos no spike).
    """
    ordered = sorted(
        jobs,
        key=lambda j: (float(j.get("score") or 0), str(j.get("id"))),
        reverse=True,
    )
    selected: list = ordered[:top]
    seen = {str(j.get("id")) for j in selected}
    rest = ordered[top:]

    wa_extras: list = []
    for job in rest:
        if len(wa_extras) >= extra_wa:
            break
        if str(job.get("id")) in seen:
            continue
        text = f"{job.get('title') or ''} {job.get('description') or ''}"
        if app_intel.work_authorization(text)["state"] != "not_mentioned":
            wa_extras.append(job)
            seen.add(str(job.get("id")))

    nodesc_extras: list = []
    for job in rest:
        if len(nodesc_extras) >= extra_nodesc:
            break
        if str(job.get("id")) in seen:
            continue
        if not (job.get("description") or "").strip():
            nodesc_extras.append(job)
            seen.add(str(job.get("id")))

    return selected + wa_extras + nodesc_extras


def should_skip(
    store: EnrichmentStore, job_id: str, final_url: str | None, content_hash: str | None
) -> bool:
    """Cache/idempotencia: record bem-sucedido com MESMO job_id + final_url
    + content_hash -> skip da LLM. Record anterior e falha -> retry permitido.
    Conteudo mudou (hash diferente) -> novo enrichment (upsert)."""
    previous = store.get(job_id)
    if previous is None or previous.get("extracted_at") is None:
        return False
    return (
        previous.get("final_url") == final_url
        and previous.get("content_hash") == content_hash
    )


def process_job(
    job: dict,
    key: str,
    store: EnrichmentStore,
    *,
    transport=None,
    backoff: tuple = llm.DEFAULT_BACKOFF_S,
    model: str = llm.MODEL,
) -> tuple[dict, str]:
    """Processa UMA vaga de ponta a ponta. Retorna (record dict, evento).

    Eventos: page_status da vaga / ``cache_hit`` / ``upsert:written`` /
    ``upsert:preserved``. Excecao nao capturada aqui e problema do codigo —
    ``process_batch`` isola por vaga e transforma em record de erro.
    """
    url = str(job.get("url") or "")
    company = str(job.get("company") or "")
    title = str(job.get("title") or "")
    source = str(job.get("source") or "")
    job_id = str(job.get("id") or "")

    resp = fetch_mod.fetch_page(url, transport)
    text = html_norm.normalize_html(resp.html or "") if resp.html is not None else ""
    content_hash = hash_content(text) if resp.html is not None else None
    status = fetch_mod.classify_page(resp, text, job)
    common = dict(
        job=job,
        fetched_at=now_iso(),
        page_status=status,
        final_url=resp.final_url,
        http_status=resp.http_status,
        content_hash=content_hash,
    )

    if status != "ok":
        record = build_record(
            **common,
            error=(resp.error if resp.error else None),
            model=model,
        )
        event = store.upsert(record)
        return record.model_dump(mode="json"), f"{status}:{event}"

    # So page_status=ok chega aqui — cache por (job_id, final_url, content_hash)
    if should_skip(store, job_id, resp.final_url, content_hash):
        return store.get(job_id), "cache_hit"

    truncated = len(text) > CONTENT_LIMIT
    content = text[:CONTENT_LIMIT] if truncated else text
    prompt = llm.build_prompt(company, title, content)
    parsed, usage, latency, attempts, error = llm.extract(
        key, prompt, model=model, transport=transport, backoff=backoff
    )

    if parsed is None:
        record = build_record(
            **common,
            error=f"llm_error:{error or 'unknown'}",
            model=model,
            attempts=attempts,
            latency_s=latency,
            usage=usage,
        )
        event = store.upsert(record)
        return record.model_dump(mode="json"), f"llm_error:{event}"

    record = build_record(
        **common,
        fields=fields_from_llm(parsed),
        content_truncated=truncated,
        model=model,
        extracted_at=now_iso(),
        attempts=attempts,
        latency_s=latency,
        usage=usage,
    )
    event = store.upsert(record)
    return record.model_dump(mode="json"), f"ok:{event}"


def process_batch(
    jobs: list,
    key: str,
    store: EnrichmentStore,
    *,
    transport=None,
    backoff: tuple = llm.DEFAULT_BACKOFF_S,
    sleep_fetch: float = DEFAULT_SLEEP_FETCH,
    log=print,
) -> dict:
    """Lote sequencial com isolamento por vaga + resumo agregado.

    Cada vaga: try/except completo — excecao vira record de erro
    (``runner_error:<Tipo>``) e o lote segue. Resumo: counts por
    page_status, extracoes ok/falha, cache_hits, latencias min/med/max e
    tokens totais do run.
    """
    records: list[dict] = []
    stats: Counter = Counter()
    latencies: list[float] = []
    tokens_in = tokens_out = 0
    total = len(jobs)
    for index, job in enumerate(jobs, 1):
        try:
            record, event = process_job(
                job, key, store, transport=transport, backoff=backoff
            )
        except Exception as exc:  # isolamento por vaga — o lote segue
            record = build_record(
                job=job,
                fetched_at=now_iso(),
                page_status="fetch_error",
                error=f"runner_error:{type(exc).__name__}",
            ).model_dump(mode="json")
            event = "runner_error:written"
            try:
                store.upsert(record)
            except Exception:
                pass  # persistencia falhou: registro fica so no resumo
        records.append(record)
        stats[str(record.get("page_status"))] += 1
        if event.startswith("cache_hit"):
            stats["cache_hits"] += 1
        usage = record.get("usage") or {}
        tokens_in += usage.get("prompt_tokens") or 0
        tokens_out += usage.get("completion_tokens") or 0
        if record.get("extracted_at") is not None:
            stats["extractions_ok"] += 1
            if record.get("latency_s") is not None:
                latencies.append(float(record["latency_s"]))
        else:
            stats["extractions_fail"] += 1
        log(
            f"[{index}/{total}] {str(record.get('page_status')):<14} "
            f"{str(record.get('company'))[:20]:<22} "
            f"{str(record.get('title'))[:40]} {event}"
        )
        if sleep_fetch > 0:
            time.sleep(sleep_fetch)
    summary = {
        "page_status": dict(stats),
        "processed": total,
        "cache_hits": stats["cache_hits"],
        "extractions_ok": stats["extractions_ok"],
        "extractions_fail": stats["extractions_fail"],
        "latencies": latencies,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
    return {"records": records, "summary": summary}


def format_summary(summary: dict) -> str:
    """Resumo final do run (counts por status, latencias, tokens)."""
    status_counts = {
        k: v
        for k, v in sorted(summary.get("page_status", {}).items())
        if k not in ("cache_hits", "extractions_ok", "extractions_fail")
    }
    latencies = summary.get("latencies") or []
    lines = [
        "== Resumo do run ==",
        f"vagas processadas: {summary.get('processed', 0)}",
        "page_status: " + (
            " ".join(f"{k}={v}" for k, v in status_counts.items()) or "nenhuma"
        ),
        f"extracoes: ok={summary.get('extractions_ok', 0)} "
        f"falha={summary.get('extractions_fail', 0)}",
        f"cache_hits: {summary.get('cache_hits', 0)}",
    ]
    if latencies:
        lines.append(
            "latencia LLM (s): "
            f"min={min(latencies):.1f} med={statistics.median(latencies):.1f} "
            f"max={max(latencies):.1f}"
        )
    lines.append(
        f"tokens: in={summary.get('tokens_in', 0)} "
        f"out={summary.get('tokens_out', 0)}"
    )
    return "\n".join(lines)


def run(args) -> int:
    """Entry point do runner (scripts/enrichment_run.py). Exit codes:

    - 0: run concluido (falha individual de vaga e dado, nao e erro);
    - 1: erro de setup (input ilegivel, amostra vazia, key ausente, modelo
      indisponivel);
    - 2: nada processado (sample vazia apos --limit 0).
    """
    input_path = Path(args.input)
    try:
        jobs = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERRO: input nao encontrado: {input_path}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERRO: input ilegivel ({input_path}): {exc}", file=sys.stderr)
        return 1
    if not isinstance(jobs, list):
        print("ERRO: input nao e lista de vagas", file=sys.stderr)
        return 1

    sample = select_sample(
        jobs, top=args.top, extra_wa=args.extra_wa, extra_nodesc=args.extra_nodesc
    )
    if args.limit is not None:
        sample = sample[: max(0, args.limit)]

    store = EnrichmentStore(args.output)

    if args.dry_run:
        if not sample:
            print("ERRO: amostra vazia", file=sys.stderr)
            return 1
        print(f"--dry-run: {len(sample)} vagas selecionadas (sem rede, sem LLM)")
        for index, job in enumerate(sample, 1):
            print(
                f"[{index}/{len(sample)}] {job.get('id')} | "
                f"{str(job.get('company'))[:24]} | "
                f"{str(job.get('title'))[:48]} | ats={job.get('source')} | "
                f"score={job.get('score')}"
            )
        sources = {str(j.get("source")) for j in sample}
        print(f"ATS distintos na amostra: {len(sources)}")
        print(f"store: {args.output} ({len(store.load())} records existentes)")
        return 0

    if not sample:
        print("ERRO: amostra vazia", file=sys.stderr)
        return 1

    key = llm.get_api_key()
    if not key:
        print(
            "ERRO: NVIDIA_API_KEY ausente no env — export antes de rodar "
            "(a key NUNCA vai em arquivo)",
            file=sys.stderr,
        )
        return 1

    ok, model_error = llm.validate_model(key)
    if not ok:
        print(f"ERRO: modelo indisponivel/key invalida: {model_error}", file=sys.stderr)
        return 1

    result = process_batch(
        sample,
        key,
        store,
        sleep_fetch=args.sleep_fetch,
    )
    print(format_summary(result["summary"]))
    if result["summary"]["processed"] == 0:
        print("ERRO: nenhuma vaga foi processada", file=sys.stderr)
        return 2
    return 0
