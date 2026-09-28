#!/usr/bin/env python3
"""Fase E — LLM Enrichment Spike: CLI dos artefatos (§5/§6/§14/§15).

MODOS:

- ``--plan``    : amostra + input montados + baseline deterministico; ZERO
                  LLM. Grava sample.json + baseline_deterministic.json +
                  plan_inputs.jsonl.
- ``--skip-llm`` : plan + analysis/comparison de records JA existentes
                  (re-analise sem gastar tokens).
- ``--run``     : execucao real — batch sequencial (spike_e.runner.run_batch:
                  1 chamada LLM por job, erro por job nao interrompe,
                  aborto >50% nos primeiros 10, records JSONL incremental
                  com skip-if-done para resume) + run_manifest.json.
- ``--analyze`` : APOS o batch — relations por campo + tabelas §16 +
                  flags evidence_not_found em analysis/.

Artefatos em /tmp/if-fasee-artifacts/ (FORA do repo; contem dados de
vagas — nunca commitados). A API key NUNCA entra em codigo/log/artefato
(carregada de /tmp/if-fasee-data/env para o env do processo; o cliente
existente sanitiza erros via _sanitize).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_PATH = Path("/tmp/if-fasee-data/eligible_jobs.json")
ENV_PATH = Path("/tmp/if-fasee-data/env")
ARTIFACTS = Path("/tmp/if-fasee-artifacts")
RECORDS_DIR = ARTIFACTS / "records"
ANALYSIS_DIR = ARTIFACTS / "analysis"
MANUAL_DIR = ARTIFACTS / "manual_review"

MODEL = "z-ai/glm-5.3-flash"


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}",
          flush=True)


def load_env() -> str:
    """dotenv manual: le ENV_PATH -> os.environ; retorna a key (nunca loga)."""
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()
    return (os.environ.get("NVIDIA_API_KEY") or "").strip()


def load_jobs() -> list[dict]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("eligible_jobs.json: topo nao e lista")
    return data


def do_plan(jobs: list[dict]) -> list[dict]:
    """V1: amostra + sample.json + baseline + plan_inputs (zero LLM)."""
    from internship_finder.spike_e import input_builder, sample
    from internship_finder.spike_e.compare import deterministic_baseline

    sample_list = sample.build_sample(jobs)
    comp = sample.sample_composition(sample_list)
    _log(f"dataset {len(jobs)} jobs; amostra {len(sample_list)} "
         f"({json.dumps(comp)})")
    deviations = {b: {"planned": n, "actual": comp.get(b, 0)}
                  for b, n in sample.PLAN.items() if comp.get(b, 0) != n}
    if deviations:
        _log(f"DESVIO de composicao vs planejado: {json.dumps(deviations)}")

    sample_out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": sample.SAMPLE_SEED,
        "dataset_size": len(jobs),
        "planned_composition": sample.PLAN,
        "actual_composition": comp,
        "composition_deviations": deviations,
        "jobs": [{k: v for k, v in e.items() if k != "job"}
                 for e in sample_list],
    }
    (ARTIFACTS / "sample.json").write_text(
        json.dumps(sample_out, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"sample.json gravado ({len(sample_list)} jobs)")

    baseline_out = {}
    inputs_out = []
    for entry in sample_list:
        job = entry["job"]
        baseline_out[entry["job_id"]] = deterministic_baseline(job)
        llm_input, truncated, is_teaser = input_builder.build_input(job)
        inputs_out.append({
            "job_id": entry["job_id"],
            "bucket": entry["bucket"],
            "llm_input": llm_input,
            "input_truncated": truncated,
            "input_chars": len(llm_input),
            "input_is_teaser": is_teaser,
        })
    (ARTIFACTS / "baseline_deterministic.json").write_text(
        json.dumps(baseline_out, ensure_ascii=False, indent=2),
        encoding="utf-8")
    with (RECORDS_DIR / "plan_inputs.jsonl").open("w", encoding="utf-8") as f:
        for row in inputs_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _log("baseline_deterministic.json + plan_inputs.jsonl gravados")
    return sample_list


def do_run(jobs: list[dict], *, limit: int | None = None,
           only_job: str | None = None) -> None:
    """V4: batch real sequencial via spike_e.runner (injetavel p/ testes)."""
    from internship_finder.enrichment.llm import validate_model
    from internship_finder.spike_e import sample
    from internship_finder.spike_e.runner import run_batch

    key = load_env()
    if not key:
        raise SystemExit("NVIDIA_API_KEY ausente")
    ok, err = validate_model(key)
    if not ok:
        raise SystemExit(f"modelo indisponivel: {err}")

    sample_list = sample.build_sample(jobs)
    if only_job:
        targets = [e for e in sample_list if e["job_id"] == only_job]
        if not targets:
            raise SystemExit(f"job_id nao esta na amostra: {only_job}")
    else:
        targets = sample_list

    records_path = RECORDS_DIR / "spike_records.jsonl"
    summary = run_batch(
        key, targets, records_path, log=_log,
        limit=limit, skip_done=only_job is None)
    manifest = {
        "run_finished_at": datetime.now(
            timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL,
        "mode": "run",
        "n_target": summary["n_target"],
        "n_ok": summary["n_ok"],
        "n_error": summary["n_error"],
        "aborted": summary["aborted"],
        "duration_s": summary["duration_s"],
        "tokens_in_total": summary["tokens_in_total"],
        "tokens_out_total": summary["tokens_out_total"],
        "latency_s_per_job": summary["latency_s_per_job"],
        "per_job": summary["per_job"],
    }
    (ARTIFACTS / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"run_manifest.json gravado: ok={summary['n_ok']} "
         f"err={summary['n_error']} abortado={summary['aborted']} "
         f"duracao={summary['duration_s']}s tokens in/out="
         f"{summary['tokens_in_total']}/{summary['tokens_out_total']}")


def _revalidated_fields(rec: dict) -> dict:
    """Revalida os campos A-F do record cru (mesma semantica do run).

    Um record gravado antes de uma mudanca de guarda pode ter campo que
    hoje rejeitaria — a analise reproduca o comportamento do
    ``parse_llm_fields`` (campo invalido vira None + erro registrado),
    em vez de derrubar o record inteiro.
    """
    from internship_finder.spike_e.schema import parse_llm_fields
    fields, errors = parse_llm_fields(rec)
    out = dict(fields)
    for name in ("work_authorization", "german", "english", "deadline",
                 "salary", "student"):
        if name not in out:
            out[name] = None
    merged_errors = dict(rec.get("field_errors") or {})
    merged_errors.update(errors)
    out["field_errors"] = merged_errors
    return out


def do_analyze() -> None:
    """V5: relations por campo + tabelas §16 (records + baseline)."""
    from collections import Counter

    from internship_finder.spike_e import input_builder
    from internship_finder.spike_e.compare import compare_record
    from internship_finder.spike_e.schema import SpikeERecord

    records: dict[str, dict] = {}
    with (RECORDS_DIR / "spike_records.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                records[str(row.get("job_id"))] = row  # upsert: ultima vence
    baseline = json.loads(
        (ARTIFACTS / "baseline_deterministic.json").read_text(encoding="utf-8"))

    per_field_counts: dict[str, Counter] = {}
    rows: list[dict] = []
    evidence_not_found: list[dict] = []
    record_errors: list[dict] = []
    for jid, rec in records.items():
        # Validacao POR CAMPO (mesma semantica do run: parse_llm_fields
        # valida cada campo isolado; record com field_errors mantem os
        # campos validos). O record cru e reconstruido campo a campo
        # para a analise — erro em um campo NAO nulifica os outros.
        rec = dict(rec)
        rec.update(_revalidated_fields(rec))
        try:
            model_rec = SpikeERecord(**rec)
        except Exception as exc:
            rows.append({"job_id": jid, "record_invalid": str(exc)[:200]})
            record_errors.append({"job_id": jid, "error": str(exc)[:200]})
            continue
        if model_rec.error is not None:
            rows.append({"job_id": jid, "llm_error": model_rec.error})
            continue
        b = baseline.get(jid, {})
        cmp_row = compare_record(b, model_rec)
        rows.append(cmp_row)
        for field in ("work_authorization", "german", "english",
                      "deadline", "salary", "student"):
            info = cmp_row[field]
            per_field_counts.setdefault(field, Counter())[
                (str(info["deterministic"]), str(info["llm"]),
                 info["relation"])] += 1
        # flag evidence_not_found (§16: alucinacao-aparente automatica;
        # o manual review decide FP vs alucinacao)
        for field in ("work_authorization", "german", "english",
                      "deadline", "salary", "student"):
            fobj = getattr(model_rec, field)
            if fobj is None:
                continue
            ev = getattr(fobj, "evidence", None)
            state = getattr(fobj, "state", None)
            if ev and state not in (None, "not_mentioned", "unclear"):
                if not input_builder.evidence_in_input(ev, model_rec.llm_input):
                    evidence_not_found.append({
                        "job_id": jid, "field": field,
                        "state": str(state), "evidence": ev,
                    })

    tables = {
        field: [
            {"deterministic": det, "llm": llm, "relation": rel, "count": n}
            for (det, llm, rel), n in sorted(
                counter.items(), key=lambda kv: -kv[1])
        ]
        for field, counter in per_field_counts.items()
    }
    out = {
        "n_records": len(records),
        "n_compared": sum(1 for r in rows if "work_authorization" in r),
        "record_errors": record_errors,
        "per_field_tables": tables,
        "evidence_not_found": evidence_not_found,
        "rows": rows,
    }
    (ANALYSIS_DIR / "comparison.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# Spike E — comparison deterministic × LLM", ""]
    for field, tbl in tables.items():
        md.append(f"## {field}")
        md.append("| deterministic | LLM | relation | qtd |")
        md.append("|---|---|---|---|")
        for r in tbl:
            md.append(f"| {r['deterministic']} | {r['llm']} | "
                      f"{r['relation']} | {r['count']} |")
        md.append("")
    (ANALYSIS_DIR / "comparison.md").write_text("\n".join(md), encoding="utf-8")
    _log(f"analysis gravada: {len(records)} records, "
         f"{len(evidence_not_found)} evidences not-found, "
         f"{len(record_errors)} record errors")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase E spike runner")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only-job", type=str, default=None)
    args = ap.parse_args()
    if not (args.plan or args.skip_llm or args.run or args.analyze):
        ap.error("escolha --plan, --skip-llm, --run ou --analyze")

    for d in (RECORDS_DIR, ANALYSIS_DIR, MANUAL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if args.analyze:
        do_analyze()
        return 0

    jobs = load_jobs()
    if args.plan or args.skip_llm:
        do_plan(jobs)
    if args.run:
        do_run(jobs, limit=args.limit, only_job=args.only_job)
    elif args.skip_llm and (RECORDS_DIR / "spike_records.jsonl").exists():
        do_analyze()
    return 0


if __name__ == "__main__":
    sys.exit(main())
