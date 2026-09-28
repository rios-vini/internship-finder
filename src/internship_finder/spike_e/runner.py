"""Batch runner da spike (spec §14/§15) — loop injetavel para testes.

Reusa o cliente ``enrichment.llm.extract`` (3 tentativas, backoff
30/60s, sanitizacao). Sequencial, 1 chamada LLM por job; erro por job
NAO interrompe o batch. ``transport`` e ``backoff`` injetaveis (testes
offline usam FakeTransport + backoff (0,0) — sem API real).

Idempotencia: job_id ja presente no records JSONL e pulado
(``skip_done=True``) — re-execucao continua de onde parou; a analise
deduplica pela ULTIMA linha por job_id (upsert por job_id).

Aborto automatico (V4): >50% de falha nos primeiros ``ABORT_WINDOW``
jobs -> break preservando os records de erro (janela degradada conhecida
da API NVIDIA; nao insistir alem das 3 tentativas do cliente).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from internship_finder.enrichment.llm import DEFAULT_BACKOFF_S, extract
from internship_finder.spike_e import input_builder, prompt
from internship_finder.spike_e.schema import parse_llm_fields

MODEL = "z-ai/glm-5.3-flash"
HEARTBEAT_EVERY = 10
ABORT_WINDOW = 10
ABORT_FAIL_RATIO = 0.5


def load_done_ids(records_path: Path) -> set[str]:
    """job_ids ja presentes no records JSONL (para skip em re-run)."""
    done: set[str] = set()
    if not records_path.exists():
        return done
    with records_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                jid = json.loads(line).get("job_id")
            except ValueError:
                continue
            if jid:
                done.add(str(jid))
    return done


def run_batch(
    key: str,
    entries: list[dict[str, Any]],
    records_path: Path,
    *,
    transport: Any = None,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
    limit: int | None = None,
    skip_done: bool = True,
) -> dict[str, Any]:
    """Extrai os jobs SEQUENCIALMENTE (§14); retorna o summary do batch.

    ``entries``: lista de dicts da amostra com ``job_id`` + ``job`` +
    ``bucket`` + ``selection_reason`` (shape do ``sample.build_sample``).
    Records sao APPENDADOS incrementalmente no JSONL (1 linha por job,
    escrita e flush imediatos — crash no meio nao perde o que passou).
    """
    done_ids = load_done_ids(records_path) if skip_done else set()
    targets = [e for e in entries if str(e.get("job_id")) not in done_ids]
    if limit:
        targets = targets[:limit]
    log(f"batch: {len(entries)} entradas, {len(done_ids)} ja feitas, "
        f"{len(targets)} a extrair")

    n_ok = n_err = 0
    tot_in = tot_out = 0
    per_job: list[dict] = []
    latencies: list[float] = []
    aborted = False
    started = time.monotonic()

    with records_path.open("a", encoding="utf-8") as rf:
        for i, entry in enumerate(targets, 1):
            job = entry["job"]
            jid = str(entry["job_id"])
            llm_input, truncated, is_teaser = input_builder.build_input(job)
            full_prompt = prompt.SPIKE_E_PROMPT + llm_input
            parsed, usage, latency, attempts, error = extract(
                key, full_prompt, transport=transport, backoff=backoff,
                sleep=sleep)
            pin = pout = None
            if isinstance(usage, dict):
                pin = usage.get("prompt_tokens") or usage.get("input_tokens")
                pout = (usage.get("completion_tokens")
                        or usage.get("output_tokens"))
                tot_in += pin or 0
                tot_out += pout or 0

            record: dict[str, Any] = {
                "schema_version": 1,
                "job_id": jid,
                "company": job.get("company"),
                "title": job.get("title"),
                "source": job.get("source"),
                "original_url": job.get("url"),
                "bucket": entry["bucket"],
                "selection_reason": entry["selection_reason"],
                "llm_input": llm_input,
                "input_truncated": truncated,
                "model": MODEL,
                "extracted_at": datetime.now(
                    timezone.utc).isoformat(timespec="seconds"),
                "attempts": attempts,
                "latency_s": latency,
                "usage": {"prompt_tokens": pin, "completion_tokens": pout},
                "error": error,
            }
            if parsed is not None:
                fields, field_errors = parse_llm_fields(parsed)
                record.update(
                    {k: v.model_dump(mode="json") for k, v in fields.items()})
                record["field_errors"] = field_errors
                if field_errors:
                    log(f"  job {jid}: field_errors={field_errors}")
                n_ok += 1
            else:
                # record de erro: campos A-F explicitamente None (nunca
                # fallback) — schema do JSONL homogeneo por linha.
                record["field_errors"] = {}
                for fname in ("work_authorization", "german", "english",
                              "deadline", "salary", "student"):
                    record[fname] = None
                n_err += 1
                log(f"  job {jid}: ERRO LLM {error} (attempts={attempts})")
            rf.write(json.dumps(record, ensure_ascii=False) + "\n")
            rf.flush()
            per_job.append({
                "job_id": jid, "ok": parsed is not None, "error": error,
                "attempts": attempts, "latency_s": latency,
                "prompt_tokens": pin, "completion_tokens": pout,
            })
            if i % HEARTBEAT_EVERY == 0 or i == len(targets):
                log(f"progresso {i}/{len(targets)} | ok={n_ok} err={n_err} "
                    f"| tokens in={tot_in} out={tot_out}")
            if i == ABORT_WINDOW and n_err > ABORT_WINDOW * ABORT_FAIL_RATIO:
                aborted = True
                log(f"ABORTO: {n_err}/{i} falhas nos primeiros "
                    f"{ABORT_WINDOW} (>{ABORT_FAIL_RATIO:.0%}) — janela "
                    f"degradada; records de erro preservados")
                break

    return {
        "n_target": len(targets),
        "n_ok": n_ok,
        "n_error": n_err,
        "aborted": aborted,
        "duration_s": round(time.monotonic() - started, 1),
        "tokens_in_total": tot_in,
        "tokens_out_total": tot_out,
        "latency_s_per_job": [round(x, 1) for x in latencies],
        "per_job": per_job,
    }
