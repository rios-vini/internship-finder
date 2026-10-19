#!/usr/bin/env python3
"""F64 — Benchmark desfechos ↔ score: concordância entre o score do ranking e
as decisões REAIS do dono (37 desfechos rotulados, registro 10/2026).

Medição, NÃO calibração (P2.5/disciplina do ``ranking_benchmark.py``): nenhum
peso muda aqui. A métrica é a FUNÇÃO OFICIAL ``pairwise_concordance`` do
harness F42 — o veredito positivo/negativo do dono é mapeado para os rótulos
``boa``/``ruim`` (apenas a ORDEM importa; ``boa`` > ``ruim`` em LABEL_RANK).

Dataset: ``benchmarks/outcomes_2026-10.jsonl`` (37 linhas; schema por linha:
``{job_id, source, score, rank, verdict, reason_class, date, notes}`` +
extensões F64 documentadas ``dup_of``/``linkable``). Provenance humana:
``benchmarks/REGISTRO-AVALIACOES-VAGAS-2026-10.md`` (cópia verbatim).

Regras de pares (pré-declaradas):
- POSITIVO  = verdict ∈ {enviada, preparada, ja_no_funil} (o dono agiu);
- NEGATIVO  = verdict == eliminada;
- EXCLUÍDO  = pendente (decisão em aberto), dup, linhas com ``dup_of``
  (re-listagem contábil / twin da mesma vaga) e não-ligáveis (``linkable``
  false — id fora do archive do dia; vagas LinkedIn sem counterpart).
- SCORE/RANK vêm do snapshot do DIA DA DECISÃO (archive correspondente);
  jobs com ``dup_of`` não entram nos pares (a mesma vaga conta 1×).

Três cortes de tau (business), todos com a função oficial:
1. ``same_day``  — pares apenas DENTRO do mesmo dia (escalas homogêneas:
   13-14/10 = régua v3 pré-F55; 18/10 = régua v4). Corte PRIMÁRIO.
2. ``pooled``    — todos os pares, rank = posição na ordem oficial do próprio
   dia (mistura escalas v3/v4 — limitação documentada).
3. Perfil: business (score arquivado), materials (``materials_score_job``
   re-score com ``now`` do run do dia), EU (``eu_score_job``, estrato não-DE,
   uniforme 18/10 — n diminuto, caveat).

Bandas de score PRÉ-DECLARADAS: [<6, [6,9), [9,11), [11,13), >=13) — % de
positivos por banda responde "o score prevê aceitação?".

Uso (medição real, fora do CI — CI não tem data/):
    python3 scripts/f64_outcomes.py --outcomes benchmarks/outcomes_2026-10.jsonl \
        --snapshot 2026-10-13=<caminho>/eligible_jobs_20261013_run.json \
        --snapshot 2026-10-14=<caminho>/eligible_jobs_20261014_run.json \
        --snapshot 2026-10-17=<caminho>/eligible_jobs_20261017_run.json \
        --snapshot 2026-10-18=<caminho>/eligible_jobs_20261018_run.json \
        --now 2026-10-13=2026-10-13T09:00:02.266583+00:00 \
        --now 2026-10-14=2026-10-14T09:00:02.782708+00:00 \
        --now 2026-10-18=2026-10-18T09:00:02.232332+00:00 \
        --json f64_results.json

Determinístico e offline: nenhum socket, nenhum data/ implícito — os
snapshots entram por argumento (cópias congeladas; ver relatório da fase).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.eu_ranking import eu_score_job  # noqa: E402
from internship_finder.materials_ranking import materials_score_job  # noqa: E402
from internship_finder.ranking_benchmark import (  # noqa: E402
    pairwise_concordance,
    sort_key,
)

VERDICTS = ("enviada", "preparada", "ja_no_funil", "pendente", "eliminada", "dup")
REASONS = (
    "language_block", "visa_block", "start_date_conflict", "off_axis",
    "duration", "job_type", "good_fit", "dup", "pending", "undocumented",
)
POSITIVE = ("enviada", "preparada", "ja_no_funil")
# Mapeamento para os rótulos OFICIAIS do harness (só a ordem importa).
LABEL_POS, LABEL_NEG = "boa", "ruim"
# Bandas pré-declaradas (limite inferior fechado, superior aberto).
BANDS: tuple[tuple[float, float], ...] = (
    (float("-inf"), 6.0), (6.0, 9.0), (9.0, 11.0), (11.0, 13.0), (13.0, float("inf")),
)
SIGNAL_COMPONENTS = ("area", "skills", "language", "type", "location",
                     "penalties", "registry", "decay", "fn", "core")


def load_outcomes(path: str | Path) -> list[dict[str, Any]]:
    """Carrega o jsonl validando o schema (ValueError se inválido)."""
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            for field in ("job_id", "source", "verdict", "reason_class", "date", "notes"):
                if not str(rec.get(field) or "").strip():
                    raise ValueError(f"linha {i}: campo obrigatório ausente: {field!r}")
            if rec["verdict"] not in VERDICTS:
                raise ValueError(f"linha {i}: verdict invalida {rec['verdict']!r}")
            if rec["reason_class"] not in REASONS:
                raise ValueError(f"linha {i}: reason_class invalida {rec['reason_class']!r}")
            datetime.strptime(rec["date"], "%Y-%m-%d")
            if rec.get("linkable"):
                if rec.get("score") is None or not isinstance(rec.get("rank"), int):
                    raise ValueError(f"linha {i}: linkable exige score+rank")
            rows.append(rec)
    if len(rows) < 1:
        raise ValueError("dataset vazio")
    return rows


def pair_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Linhas que entram nos pares: ligáveis, primárias (sem dup_of), não-pendentes."""
    out = []
    for r in rows:
        if not r.get("linkable"):
            continue
        if r.get("dup_of"):
            continue
        if r["verdict"] == "pendente":
            continue
        out.append(r)
    return out


def _label_of(row: dict[str, Any]) -> str | None:
    if row["verdict"] in POSITIVE:
        return LABEL_POS
    if row["verdict"] == "eliminada":
        return LABEL_NEG
    return None


def measure_tau(records: list[dict[str, Any]]) -> dict[str, Any]:
    """tau com a FUNÇÃO OFICIAL sobre ``records`` ({label, rank} por entrada)."""
    return pairwise_concordance(records)


def tau_same_day(rows: list[dict[str, Any]], *, rank_field: str = "rank") -> dict[str, Any]:
    """Corte PRIMÁRIO: pares só dentro do mesmo dia (escalas homogêneas).

    Soma os pares comparáveis/concordantes da função oficial POR DIA —
    comparar rank 9/777 (13/10) com rank 2/736 (18/10) não é ordinal.
    """
    comparable = concordant = 0
    per_day: dict[str, dict] = {}
    by_day: dict[str, list] = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    for day, day_rows in sorted(by_day.items()):
        labels = {_label_of(r) for r in day_rows}
        if len(labels) < 2:
            per_day[day] = {"comparable_pairs": 0, "concordant_pairs": 0}
            continue
        recs = [{"label": _label_of(r), "rank": r[rank_field]} for r in day_rows]
        m = measure_tau(recs)
        comparable += m["comparable_pairs"]
        concordant += m["concordant_pairs"]
        per_day[day] = m
    pct = 100.0 * concordant / comparable if comparable else 0.0
    return {
        "comparable_pairs": comparable,
        "concordant_pairs": concordant,
        "concordant_pct": round(pct, 2),
        "tau": round(2.0 * pct / 100.0 - 1.0, 3),
        "per_day": per_day,
    }


def tau_pooled(rows: list[dict[str, Any]], *, score_field: str = "score",
               rank_field: str = "rank") -> dict[str, Any]:
    """Corte secundário: todos os pares; ordem pela chave oficial sobre o
    subconjunto ({score desc, titulo, empresa, id}) — limitação: mistura as
    escalas v3 (13-14/10) e v4 (18/10)."""
    ordered = sorted(rows, key=lambda r: (
        -float(r[score_field]), str(r.get("title") or "").casefold(),
        str(r.get("company") or "").casefold(), str(r["job_id"])))
    pooled_rank = {r["job_id"]: i for i, r in enumerate(ordered, 1)}
    recs = [{"label": _label_of(r), "rank": pooled_rank[r["job_id"]]} for r in rows]
    return measure_tau(recs)


def rescore_profile(rows: list[dict[str, Any]], snapshots: dict[str, dict[str, dict]],
                    scorer: Callable[[dict[str, Any]], float], *,
                    field: str) -> list[dict[str, Any]]:
    """(helper de reuso) Re-scorea cada linha ligável com ``scorer`` e devolve
    cópias com ``<field>`` (score) e ``<field>_rank`` (posição oficial no dia)."""
    out = []
    by_day: dict[str, list] = {}
    for r in rows:
        job = snapshots[r["date"]][r["job_id"]]
        nr = dict(r)
        nr[field] = scorer(job)
        nr["title"] = job.get("title")
        nr["company"] = job.get("company")
        by_day.setdefault(r["date"], []).append(nr)
    for day, day_rows in by_day.items():
        ordered = sorted(day_rows, key=lambda r: (
            -float(r[field]), str(r.get("title") or "").casefold(),
            str(r.get("company") or "").casefold(), str(r["job_id"])))
        for i, r in enumerate(ordered, 1):
            r[field + "_rank"] = i
        out.extend(ordered)
    return out


def score_bands(rows: list[dict[str, Any]], *, score_field: str = "score") -> list[dict[str, Any]]:
    """% de positivos por banda pré-declarada — "o score prevê aceitação?"."""
    out = []
    for lo, hi in BANDS:
        sel = [r for r in rows if lo <= float(r[score_field]) < hi]
        n_pos = sum(1 for r in sel if _label_of(r) == LABEL_POS)
        n_neg = sum(1 for r in sel if _label_of(r) == LABEL_NEG)
        out.append({
            "band": f"{lo:g}..{hi:g}" if hi != float("inf") else f">={lo:g}",
            "n": n_pos + n_neg, "positivos": n_pos, "negativos": n_neg,
            "pct_positivos": round(100.0 * n_pos / (n_pos + n_neg), 1) if (n_pos + n_neg) else None,
        })
    return out


def topk_precision(rows: list[dict[str, Any]], *, k: int,
                   score_field: str = "score") -> dict[str, Any]:
    """Precisão@k na ordem oficial do subconjunto (pooled)."""
    ordered = sorted(rows, key=lambda r: (
        -float(r[score_field]), str(r.get("title") or "").casefold(),
        str(r.get("company") or "").casefold(), str(r["job_id"])))
    top = ordered[:k]
    n_pos = sum(1 for r in top if _label_of(r) == LABEL_POS)
    return {"k": k, "n": len(top), "positivos": n_pos,
            "pct_positivos": round(100.0 * n_pos / len(top), 1) if top else None}


def signals_table(rows: list[dict[str, Any]],
                  snapshots: dict[str, dict[str, dict]]) -> dict[str, Any]:
    """Tabela fato×veredito: cada componente do score_breakdown discriminou?

    Por componente: média entre positivos/negativos + tabela 2×2
    (presença do sinal × veredito). Componentes só-18/10 (fn/core/decay)
    são medidos apenas nas linhas que os carregam (n documentado).
    """
    per_comp: dict[str, dict[str, Any]] = {}
    for comp in SIGNAL_COMPONENTS:
        pos_vals, neg_vals, pos_with, pos_without, neg_with, neg_without = [], [], 0, 0, 0, 0
        for r in rows:
            job = snapshots[r["date"]][r["job_id"]]
            bd = job.get("score_breakdown") or {}
            if comp not in bd:
                continue
            v = float(bd[comp])
            lab = _label_of(r)
            if lab == LABEL_POS:
                pos_vals.append(v)
                pos_with, pos_without = (pos_with + 1, pos_without) if v > 0 else (pos_with, pos_without + 1)
            elif lab == LABEL_NEG:
                neg_vals.append(v)
                neg_with, neg_without = (neg_with + 1, neg_without) if v > 0 else (neg_with, neg_without + 1)
        if not pos_vals and not neg_vals:
            continue
        mean_pos = sum(pos_vals) / len(pos_vals) if pos_vals else None
        mean_neg = sum(neg_vals) / len(neg_vals) if neg_vals else None
        sep = (mean_pos - mean_neg) if (mean_pos is not None and mean_neg is not None) else None
        per_comp[comp] = {
            "n_pos": len(pos_vals), "n_neg": len(neg_vals),
            "media_pos": round(mean_pos, 3) if mean_pos is not None else None,
            "media_neg": round(mean_neg, 3) if mean_neg is not None else None,
            "separacao": round(sep, 3) if sep is not None else None,
            "pos_com_sinal": pos_with, "pos_sem_sinal": pos_without,
            "neg_com_sinal": neg_with, "neg_sem_sinal": neg_without,
        }
    ranked = sorted(
        ((c, v) for c, v in per_comp.items() if v["separacao"] is not None),
        key=lambda kv: -abs(kv[1]["separacao"]))
    return {"componentes": per_comp, "ordenado_por_abs_separacao": [c for c, _ in ranked]}


def measure(outcomes_path: str | Path, snapshot_args: list[str], now_args: list[str]) -> dict[str, Any]:
    rows = load_outcomes(outcomes_path)
    snapshots: dict[str, dict[str, dict]] = {}
    for spec in snapshot_args:
        day, path = spec.split("=", 1)
        jobs = json.loads(Path(path).read_text(encoding="utf-8"))
        snapshots[day] = {j["id"]: j for j in jobs}
    nows = {}
    for spec in now_args:
        day, iso = spec.split("=", 1)
        nows[day] = datetime.fromisoformat(iso)

    pairs = pair_rows(rows)
    verdicts = Counter(r["verdict"] for r in pairs)

    biz_same = tau_same_day(pairs)
    biz_pooled = tau_pooled(pairs)

    # materials: re-score linha a linha com o now do DIA da decisão
    mat_rows = []
    by_day: dict[str, list] = {}
    for r in pairs:
        job = snapshots[r["date"]][r["job_id"]]
        nr = dict(r)
        nr["mat_score"] = float(materials_score_job(job, now=nows.get(r["date"])).total)
        nr["title"] = job.get("title")
        nr["company"] = job.get("company")
        by_day.setdefault(r["date"], []).append(nr)
    for day, day_rows in by_day.items():
        ordered = sorted(day_rows, key=lambda r: (
            -r["mat_score"], str(r.get("title") or "").casefold(),
            str(r.get("company") or "").casefold(), str(r["job_id"])))
        for i, r in enumerate(ordered, 1):
            r["mat_rank"] = i
        mat_rows.extend(ordered)
    mat_same = tau_same_day(mat_rows, rank_field="mat_rank")
    mat_pooled = tau_pooled(mat_rows, score_field="mat_score")

    # EU: estrato não-DE, uniforme 18/10 (n diminuto — caveat no relatório)
    day18 = "2026-10-18" if "2026-10-18" in snapshots else sorted(snapshots)[-1]
    eu_rows = []
    for r in pairs:
        job = snapshots[day18].get(r["job_id"])
        if job is None:
            continue
        if str(job.get("country") or "de").lower() == "de":
            continue
        nr = dict(r)
        nr["eu_score"] = float(eu_score_job(job, now=nows.get(day18)).total)
        nr["title"] = job.get("title")
        nr["company"] = job.get("company")
        eu_rows.append(nr)
    if eu_rows:
        ordered = sorted(eu_rows, key=lambda r: (
            -r["eu_score"], str(r.get("title") or "").casefold(),
            str(r.get("company") or "").casefold(), str(r["job_id"])))
        for i, r in enumerate(ordered, 1):
            r["eu_rank"] = i
        eu_tau = measure_tau([{"label": _label_of(r), "rank": r["eu_rank"]} for r in eu_rows])
    else:
        eu_tau = {"comparable_pairs": 0, "concordant_pairs": 0, "concordant_pct": 0.0, "tau": None}

    bands = score_bands(pairs)
    topk = [topk_precision(pairs, k=k) for k in (5, 10, 14)]
    signals = signals_table(pairs, snapshots)

    return {
        "meta": {
            "n_linhas": len(rows), "n_ligaveis": sum(1 for r in rows if r.get("linkable")),
            "n_pares_eligiveis": len(pairs), "verdicts_nos_pares": dict(verdicts),
            "criterio_pares": "positivo={enviada,preparada,ja_no_funil}; negativo=eliminada; "
                              "exclui pendente/dup/re-listagens(dup_of)/nao-ligaveis",
            "bandas_pre_declaradas": [f"{lo:g}..{hi:g}" if hi != float('inf') else f">={lo:g}"
                                      for lo, hi in BANDS],
        },
        "business": {"same_day": biz_same, "pooled": biz_pooled},
        "materials": {"same_day": mat_same, "pooled": mat_pooled},
        "eu_uniform_18_10": {"n": len(eu_rows), **eu_tau},
        "bandas_score": bands,
        "precisao_topk": topk,
        "sinais_fato_veredito": signals,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="F64 — benchmark desfechos vs score (medição, não calibração)")
    ap.add_argument("--outcomes", required=True)
    ap.add_argument("--snapshot", action="append", default=[], metavar="DATE=PATH",
                    help="snapshot congelado do run daquele dia (eligible_jobs.json)")
    ap.add_argument("--now", action="append", default=[], metavar="DATE=ISO",
                    help="ts do run (decay) por dia")
    ap.add_argument("--json", help="grava o resultado em JSON neste caminho")
    args = ap.parse_args(argv)
    result = measure(args.outcomes, args.snapshot, args.now)
    text = json.dumps(result, indent=1, ensure_ascii=False, default=str)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
