"""Runner incremental da camada de enrichment (Fase 2 — enrichment LLM v2).

Fluxo do run (spec da fase 2):

  planejamento deterministico sobre eligible_jobs.json
    (ordem (score desc, id desc); bucket por record existente:
     sem record -> new; record de falha -> retry; sucesso -> seen)
  -> fetch sweep: TODAS as vagas do plano -> fetch + normalize + SHA-256
     (delta = job_id + final_url + content_hash, infra da Fase 1)
  -> seen + identico ao record de sucesso e SEM pendencia -> cache_hit
     (zero LLM, zero escrita)
  -> pool p/ LLM: retry -> new -> changed/changed_source (cada bloco por
     score desc), cap ``--limit`` sobre CHAMADAS LLM; excedente fica
     ``pending_backlog`` p/ o proximo run
  -> extracao GLM-5.3-Flash sequencial (3 tentativas, backoff 30/60s,
     isolamento por vaga — uma vaga nunca bloqueia as demais)
  -> EnrichmentRecord -> upsert (escrita atomica; falha nova NUNCA apaga
     sucesso anterior — conteudo novo com falha vira PENDENCIA no record
     preservado, spec secao 9)
  -> resumo operacional + status file de health (enrichment_status.json)

A LLM apenas enriquece com evidencia — NUNCA decide eligibility, score ou
ranking; nenhum modulo existente importa este pacote.

Exit codes (spec fase 2 / decisao D5):

- 0: run concluido (falha individual de vaga e dado, nao e erro);
- 1: erro de setup (input ilegivel, eligible vazio, key ausente, modelo
  indisponivel);
- 2: nenhuma vaga processada (ex.: ``--limit 0`` com pool pendente);
- 3: execucao concorrente detectada (lock ocupado).
"""

from __future__ import annotations

import fcntl
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from internship_finder.enrichment import fetch as fetch_mod
from internship_finder.enrichment import html_norm
from internship_finder.enrichment import llm
from internship_finder.enrichment.schema import (
    CONTENT_LIMIT,
    build_record,
    fields_from_llm,
    hash_content,
)
from internship_finder.enrichment.store import EnrichmentStore

# Cap default de chamadas LLM por run (decisao D2/D15: backlog e processado
# naturalmente em execucoes futuras; 24 extracoes x 16-290s medidos).
DEFAULT_LIMIT = 24
DEFAULT_SLEEP_FETCH = 2.0

# Lock de concorrencia (spec secao 14): flock do SO no diretorio do store —
# processo morto libera sozinho, sem stale lock, sem cleanup manual.
LOCK_FILE_NAME = ".enrichment.lock"

# Health da camada (spec secao 12): um JSON ao lado do store, escrita atomica.
STATUS_FILE_NAME = "enrichment_status.json"


def now_iso() -> str:
    """Timestamp ISO UTC (segundos) — fetched_at/extracted_at/last_run_at."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Planejamento (pre-fetch, deterministico, sem rede)
# ---------------------------------------------------------------------------


@dataclass
class PlanItem:
    """Uma vaga do plano: job do ranking + bucket + record atual do store."""

    job: dict
    bucket: str  # new | retry | seen
    record: dict | None


def job_sort_key(job: dict) -> tuple:
    """Ordem deterministica do plano: (score desc, id desc)."""
    return (float(job.get("score") or 0), str(job.get("id")))


def plan_jobs(jobs: list, records: dict) -> list:
    """Plano deterministico sobre TODAS as vagas elegiveis.

    Bucket por record existente no store: sem record -> ``new``; record de
    falha (``extracted_at=None``) -> ``retry``; record de sucesso ->
    ``seen`` (indeciso ate o fetch — o delta so e conhecido apos o hash).
    Vagas sem ``id`` sao puladas (input malformado; o schema exige job_id).
    """
    ordered = sorted(jobs, key=job_sort_key, reverse=True)
    items: list = []
    for job in ordered:
        job_id = str(job.get("id") or "")
        if not job_id:
            continue
        record = records.get(job_id)
        if record is None:
            bucket = "new"
        elif record.get("extracted_at") is None:
            bucket = "retry"
        else:
            bucket = "seen"
        items.append(PlanItem(job=job, bucket=bucket, record=record))
    return items


def classify_seen(record: dict, final_url: str | None, content_hash: str | None) -> str:
    """Classifica pos-fetch uma vaga com record de sucesso (delta, D2/D6).

    - ``final_url`` diferente -> ``changed_source`` (a origem mudou;
      reprocessar — a chave de cache inclui a URL);
    - hash igual ao do sucesso E sem pendencia -> ``cache_hit``;
    - hash igual ao ``pending_content_hash`` -> ``retry`` (a versao pendente
      voltou; reprocessar);
    - demais casos -> ``changed`` (mudou de novo, ou reverteu ao conteudo do
      sucesso com pendencia registrada — conservador: reprocessa).

    Conservador por design (dados preservados > performance): quando ha
    pendencia o cache_hit so acontece se o hash casar E a pendencia nao
    existir — uma pendencia nunca e silenciada por um cache.
    """
    if final_url != record.get("final_url"):
        return "changed_source"
    if (
        content_hash is not None
        and content_hash == record.get("content_hash")
        and not record.get("pending_content_hash")
    ):
        return "cache_hit"
    if (
        content_hash is not None
        and content_hash == record.get("pending_content_hash")
    ):
        return "retry"
    return "changed"


# ---------------------------------------------------------------------------
# Concorrencia (spec secao 14)
# ---------------------------------------------------------------------------


def acquire_lock(output_path: Path):
    """flock exclusivo nao-bloqueante em ``<dir do --output>/.enrichment.lock``.

    Retorna o fd aberto (o chamador segura ate o fim do run e fecha no
    finally) ou ``None`` quando outra execucao detem o lock. flock do SO:
    processo morto libera sozinho — sem stale lock, sem cleanup manual.
    ``--dry-run`` nao passa por aqui (read-only).
    """
    lock_path = output_path.parent / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


# ---------------------------------------------------------------------------
# Execucao incremental (sweep + pool + LLM)
# ---------------------------------------------------------------------------


def run_incremental(
    plan: list,
    key: str,
    store: EnrichmentStore,
    *,
    limit: int = DEFAULT_LIMIT,
    transport=None,
    backoff: tuple = llm.DEFAULT_BACKOFF_S,
    sleep_fetch: float = DEFAULT_SLEEP_FETCH,
    log=print,
) -> dict:
    """Sweep completo + pool com cap + extracao sequencial. Retorna o resumo.

    Isolamento por vaga em TODAS as fases: excecao vira record de erro
    (``runner_error:<Tipo>``) e o lote segue (spec secao 8 — uma vaga nao
    bloqueia permanentemente as demais). Fetch de UMA tentativa por URL
    (retry na camada LLM; martelar servidor de carreira nao e aceitavel).
    """
    counts: Counter = Counter()
    page_status_counts: Counter = Counter()
    fetch_secs: list[float] = []
    llm_secs: list[float] = []
    tokens_in = tokens_out = 0
    last_error: str | None = None
    total = len(plan)
    started = time.monotonic()

    def _upsert_failure(job: dict, common: dict, error: str | None) -> str:
        """Record de nao-extracao + upsert (preserva sucesso anterior)."""
        record = build_record(**common, error=error, model=llm.MODEL)
        return store.upsert(record)

    # --- fetch sweep: TODAS as vagas do plano (fetch + normalize + hash) ---
    pool: list[dict] = []
    for index, item in enumerate(plan, 1):
        job = item.job
        company = str(job.get("company") or "")
        title = str(job.get("title") or "")
        try:
            t0 = time.monotonic()
            resp = fetch_mod.fetch_page(str(job.get("url") or ""), transport)
            fetch_secs.append(round(time.monotonic() - t0, 2))
            text = (
                html_norm.normalize_html(resp.html or "")
                if resp.html is not None
                else ""
            )
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
                # Fetch falho: conta nas metricas e segue pelo caminho normal
                # de falha (upsert preserva sucesso anterior com last_error).
                page_status_counts[status] += 1
                error = resp.error or f"page_status:{status}"
                event = _upsert_failure(job, common, error)
                if event == "preserved":
                    counts["preserved"] += 1
                last_error = f"{job.get('id')}: {error}"
                log(
                    f"[{index}/{total}] {status:<14} {company[:20]:<22} "
                    f"{title[:40]} upsert:{event}"
                )
            else:
                if item.bucket == "seen":
                    bucket = classify_seen(
                        item.record or {}, resp.final_url, content_hash
                    )
                else:
                    bucket = item.bucket
                if bucket == "cache_hit":
                    counts["cache_hits"] += 1
                    log(
                        f"[{index}/{total}] cache_hit      {company[:20]:<22} "
                        f"{title[:40]}"
                    )
                else:
                    counts[f"bucket_{bucket}"] += 1
                    pool.append(
                        dict(
                            job=job,
                            bucket=bucket,
                            text=text,
                            content_hash=content_hash,
                            final_url=resp.final_url,
                            http_status=resp.http_status,
                            fetched_at=common["fetched_at"],
                        )
                    )
                    log(
                        f"[{index}/{total}] pool:{bucket:<11} {company[:20]:<22} "
                        f"{title[:40]}"
                    )
        except Exception as exc:  # isolamento por vaga — o lote segue
            page_status_counts["fetch_error"] += 1
            try:
                record = build_record(
                    job=job,
                    fetched_at=now_iso(),
                    page_status="fetch_error",
                    error=f"runner_error:{type(exc).__name__}",
                )
                event = store.upsert(record)
                if event == "preserved":
                    counts["preserved"] += 1
            except Exception:
                event = "runner_error:lost"  # persistencia falhou
            last_error = f"{job.get('id')}: runner_error:{type(exc).__name__}"
            log(f"[{index}/{total}] runner_error  {company[:20]:<22} {event}")
        if sleep_fetch > 0 and index < total:
            time.sleep(sleep_fetch)

    # --- pool p/ LLM: retry -> new -> changed/changed_source (score desc) ---
    cap = max(0, int(limit))
    ordered_pool = (
        [p for p in pool if p["bucket"] == "retry"]
        + [p for p in pool if p["bucket"] == "new"]
        + [p for p in pool if p["bucket"] in ("changed", "changed_source")]
    )
    selected = ordered_pool[:cap]
    counts["pending_backlog"] = len(ordered_pool) - len(selected)

    for index, pool_item in enumerate(selected, 1):
        job = pool_item["job"]
        company = str(job.get("company") or "")
        title = str(job.get("title") or "")
        text = pool_item["text"]
        truncated = len(text) > CONTENT_LIMIT
        content = text[:CONTENT_LIMIT] if truncated else text
        common = dict(
            job=job,
            fetched_at=pool_item["fetched_at"],
            page_status="ok",
            final_url=pool_item["final_url"],
            http_status=pool_item["http_status"],
            content_hash=pool_item["content_hash"],
        )
        try:
            prompt = llm.build_prompt(company, title, content)
            parsed, usage, latency, attempts, error = llm.extract(
                key, prompt, transport=transport, backoff=backoff
            )
            counts["llm_calls"] += 1
            counts["llm_retries"] += max(0, attempts - 1)
            if latency is not None:
                llm_secs.append(float(latency))
            usage = usage or {}
            tokens_in += usage.get("prompt_tokens") or 0
            tokens_out += usage.get("completion_tokens") or 0
            if parsed is None:
                record = build_record(
                    **common,
                    error=f"llm_error:{error or 'unknown'}",
                    model=llm.MODEL,
                    attempts=attempts,
                    latency_s=latency,
                    usage=usage,
                )
                event = store.upsert(record)
                if event == "preserved":
                    counts["preserved"] += 1
                counts["extractions_fail"] += 1
                last_error = f"{job.get('id')}: llm_error:{error}"
                log(
                    f"[LLM {index}/{len(selected)}] falha  {company[:20]:<22} "
                    f"{title[:40]} {error} upsert:{event}"
                )
            else:
                record = build_record(
                    **common,
                    fields=fields_from_llm(parsed),
                    content_truncated=truncated,
                    model=llm.MODEL,
                    extracted_at=now_iso(),
                    attempts=attempts,
                    latency_s=latency,
                    usage=usage,
                )
                event = store.upsert(record)
                counts["extractions_ok"] += 1
                log(
                    f"[LLM {index}/{len(selected)}] ok     {company[:20]:<22} "
                    f"{title[:40]} upsert:{event}"
                )
        except Exception as exc:  # isolamento por vaga — o lote segue
            try:
                record = build_record(
                    job=job,
                    fetched_at=now_iso(),
                    page_status="fetch_error",
                    error=f"runner_error:{type(exc).__name__}",
                )
                event = store.upsert(record)
                if event == "preserved":
                    counts["preserved"] += 1
            except Exception:
                event = "runner_error:lost"
            counts["extractions_fail"] += 1
            last_error = f"{job.get('id')}: runner_error:{type(exc).__name__}"
            log(f"[LLM {index}/{len(selected)}] runner_error {company[:20]:<22} {event}")

    page = page_status_counts
    duration = round(time.monotonic() - started, 1)
    return {
        "total_eligible": total,
        "cache_hits": counts["cache_hits"],
        "new": counts["bucket_new"],
        "retry": counts["bucket_retry"],
        "changed": counts["bucket_changed"],
        "changed_source": counts["bucket_changed_source"],
        "selected": len(pool),
        "cap": cap,
        "llm_calls": counts["llm_calls"],
        "llm_retries": counts["llm_retries"],
        "extractions_ok": counts["extractions_ok"],
        "extractions_fail": counts["extractions_fail"],
        "fetch_failures": page["timeout"] + page["fetch_error"],
        "timeouts": page["timeout"],
        "http_errors": page["http_error"] + page["not_found"],
        "js_rendered": page["js_rendered"],
        "skipped": page["js_rendered"] + page["empty_content"] + page["redirected"],
        "preserved": counts["preserved"],
        "pending_backlog": counts["pending_backlog"],
        "page_status": dict(page),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "duration_s": duration,
        "fetch_avg_s": round(statistics.mean(fetch_secs), 2) if fetch_secs else None,
        "llm_avg_s": round(statistics.mean(llm_secs), 2) if llm_secs else None,
        "last_error": last_error,
    }


def format_summary(summary: dict) -> str:
    """Resumo operacional do run (spec secao 4 — TODOS os campos)."""
    fetch_avg = summary.get("fetch_avg_s")
    llm_avg = summary.get("llm_avg_s")
    lines = [
        "== Resumo do enrichment (fase 2) ==",
        f"vagas elegiveis: {summary.get('total_eligible', 0)}",
        f"cache hits: {summary.get('cache_hits', 0)}",
        "pool: "
        f"new {summary.get('new', 0)} | retry {summary.get('retry', 0)} | "
        f"changed {summary.get('changed', 0)} | "
        f"changed_source {summary.get('changed_source', 0)}",
        f"selecionadas p/ LLM: {summary.get('selected', 0)} "
        f"(cap {summary.get('cap', 0)}) | "
        f"backlog pendente: {summary.get('pending_backlog', 0)}",
        f"LLM: chamadas {summary.get('llm_calls', 0)} | "
        f"retries {summary.get('llm_retries', 0)} | "
        f"ok {summary.get('extractions_ok', 0)} | "
        f"falha {summary.get('extractions_fail', 0)}",
        f"fetch: falhas {summary.get('fetch_failures', 0)} "
        f"(timeouts {summary.get('timeouts', 0)}) | "
        f"HTTP errors {summary.get('http_errors', 0)} | "
        f"js_rendered {summary.get('js_rendered', 0)} | "
        f"skipped {summary.get('skipped', 0)}",
        f"preservados (falha nao apagou sucesso): {summary.get('preserved', 0)}",
        f"tokens: in {summary.get('tokens_in', 0)} out {summary.get('tokens_out', 0)}",
        "tempos (s): "
        f"total {summary.get('duration_s', 0)} | "
        f"fetch medio {fetch_avg if fetch_avg is not None else '-'} | "
        f"LLM medio {llm_avg if llm_avg is not None else '-'}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Status file (health — spec secao 12)
# ---------------------------------------------------------------------------


def status_path_for(output_path: Path) -> Path:
    """Caminho do status file (ao lado do store)."""
    return output_path.parent / STATUS_FILE_NAME


def _read_status(path: Path) -> dict:
    """Status anterior (tolerante: ausente/malformado -> {})."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_status_json(path: Path, payload: dict) -> None:
    """Escrita atomica (tmp no mesmo diretorio + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=path.parent,
            prefix=".status-",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.replace(tmp_name, path)
    except BaseException:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _write_run_status(
    output_path: Path,
    exit_code: int,
    summary: dict | None,
    duration_s: float,
    last_error: str | None,
) -> None:
    """Health do run (spec secao 12). Best-effort: falha nunca derruba o run.

    ``last_success_at`` so avanca em exit 0 (run concluido) — um run de
    setup falho preserva o ultimo sucesso, que e exatamente o sinal de
    \"o enrichment parou de funcionar\" quando parado no tempo.
    """
    path = status_path_for(output_path)
    previous = _read_status(path)
    success_at = now_iso() if exit_code == 0 else previous.get("last_success_at")
    counts = {
        k: v
        for k, v in (summary or {}).items()
        if isinstance(v, int) and not isinstance(v, bool)
    }
    payload = {
        "last_run_at": now_iso(),
        "last_success_at": success_at,
        "last_exit_code": exit_code,
        "model": llm.MODEL,
        "counts": counts,
        "last_error": last_error,
        "duration_s": round(duration_s or 0.0, 1),
    }
    try:
        _write_status_json(path, payload)
    except OSError as exc:
        print(f"[aviso] status de enrichment nao gravado: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point (scripts/enrichment_run.py)
# ---------------------------------------------------------------------------


def run(args, *, transport=None, backoff: tuple = llm.DEFAULT_BACKOFF_S, log=print) -> int:
    """Entry point do runner (scripts/enrichment_run.py). Exit codes:

    - 0: run concluido (falha individual de vaga e dado, nao e erro);
    - 1: erro de setup (input ilegivel, eligible vazio, key ausente,
      modelo indisponivel);
    - 2: nenhuma vaga processada (ex.: ``--limit 0`` com pool pendente);
    - 3: execucao concorrente detectada (lock ocupado).

    Ordem: input -> plano -> ``--dry-run`` (read-only, sai 0) -> key ->
    lock -> validacao do modelo (fail fast, sem disperdiciar sweep) ->
    sweep + LLM -> resumo -> status file.
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
    if not jobs:
        print("ERRO: nenhuma vaga elegivel no input", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    store = EnrichmentStore(output_path)
    records = store.load()
    plan = plan_jobs(jobs, records)

    if args.dry_run:
        buckets = Counter(item.bucket for item in plan)
        print(
            f"--dry-run: {len(plan)} vagas no sweep (sem rede, sem LLM, sem lock)"
        )
        print(
            f"plano pre-fetch: new={buckets['new']} retry={buckets['retry']} "
            f"seen={buckets['seen']}"
        )
        print(
            f"cap de extracoes LLM: {max(0, int(args.limit))} | "
            f"store: {len(records)} records"
        )
        return 0

    key = llm.get_api_key()
    if not key:
        print(
            "ERRO: NVIDIA_API_KEY ausente no env — export antes de rodar "
            "(a key NUNCA vai em arquivo)",
            file=sys.stderr,
        )
        _write_run_status(
            output_path, 1, None, 0.0, "setup: NVIDIA_API_KEY ausente"
        )
        return 1

    lock_fd = acquire_lock(output_path)
    if lock_fd is None:
        print("execucao concorrente detectada — saindo", file=sys.stderr)
        return 3

    try:
        ok, model_error = llm.validate_model(key, transport)
        if not ok:
            print(
                f"ERRO: modelo indisponivel/key invalida: {model_error}",
                file=sys.stderr,
            )
            _write_run_status(output_path, 1, None, 0.0, f"setup: {model_error}")
            return 1

        summary = run_incremental(
            plan,
            key,
            store,
            limit=args.limit,
            transport=transport,
            backoff=backoff,
            sleep_fetch=args.sleep_fetch,
            log=log,
        )
        print(format_summary(summary))

        exit_code = 0
        touched = (
            summary["cache_hits"]
            + summary["llm_calls"]
            + summary["fetch_failures"]
            + summary["http_errors"]
            + summary["skipped"]
        )
        if summary["llm_calls"] == 0 and summary["selected"] > 0:
            # havia trabalho no pool e nenhuma extracao foi feita
            # (ex.: --limit 0 com backlog pendente) — sinal operacional,
            # nao e erro de setup.
            exit_code = 2
        elif not touched:
            exit_code = 2  # defensivo: nada foi processado (impossivel com sweep)
        _write_run_status(
            output_path,
            exit_code,
            summary,
            summary["duration_s"],
            summary.get("last_error"),
        )
        return exit_code
    finally:
        os.close(lock_fd)
