#!/usr/bin/env python3
"""Benchmark v3 do perfil EU non-DE (F36) — medição, não calibração.

Compara, SOBRE O MESMO ESTRATO não-DE rotulado do benchmark v2
(``benchmarks/ranking_benchmark_v2.json``, 35 vagas com rótulo), a
concordância ordinal do ranking ATUAL (perfil business; baseline v2
não-DE) contra o NOVO perfil EU (``eu_ranking``).

Metodologia — MESMA do v2 (``pairwise_concordance`` do
``ranking_benchmark.py``: pares comparáveis = labels diferentes;
concordante = rótulo melhor ACIMA do pior; tau = 2*pct − 1). A única
diferença: as posições (``rank``) são derivadas DENTRO do estrato
(ordenar o subconjunto pelas chaves oficiais de cada perfil), porque o
perfil EU é exibido como ranking próprio — o que o dono vê é a ordem
interna do estrato, não a mistura com a DE.

Critério de aceite F36 (veredito do dono 13/10): tau do perfil EU ≥
tau v2-não-DE + 0,10 = +0,628.

Determinístico sobre arquivos versionados; nenhuma rede; nenhum
``data/`` de produção (o snapshot é passado via ``--snapshot``, cópia
local). Não altera nada — o ranking business segue sendo a
implementação de referência.

Uso:
    .venv/bin/python scripts/ranking_benchmark_v3.py \
        --snapshot /tmp/if-f36-universe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.eu_ranking import eu_score_job  # noqa: E402
from internship_finder.ranking_benchmark import (  # noqa: E402
    LABELS_ORDER,
    LABEL_RANK,
)

DEFAULT_BENCHMARK = ROOT / "benchmarks" / "ranking_benchmark_v2.json"


def _stratum_records(benchmark: dict, universe: dict[str, dict]) -> list[dict]:
    """Registros do estrato não-DE (country != 'de') ligados ao universo."""
    out = []
    for j in benchmark["jobs"]:
        if str(j.get("country") or "de").lower() == "de":
            continue
        u = universe.get(j["id"])
        if u is None:
            continue
        out.append({"id": j["id"], "label": j["label"], "job": u,
                   "title": u.get("title") or "", "company": u.get("company") or ""})
    return out


def _ranks_by(records: list[dict], *, business: bool) -> dict[str, int]:
    """Posições dentro do estrato sob a chave oficial de cada perfil.

    business: score congelado do snapshot (ordem oficial do pipeline).
    EU: ``eu_score_job`` sobre o MESMO snapshot.
    Desempate idêntico ao ``rank_jobs``/``rank_eu_jobs`` (título
    casefold → empresa casefold → id) — posições únicas por construção.
    """
    def key(rec):
        score = (float(rec["job"]["score"]) if business
                 else float(eu_score_job(rec["job"]).total))
        return (-score, rec["title"].casefold(), rec["company"].casefold(), rec["id"])
    ordered = sorted(records, key=key)
    return {rec["id"]: i + 1 for i, rec in enumerate(ordered)}


def _tau(records: list[dict], ranks: dict[str, int]) -> dict:
    comparable = concordant = 0
    for i in range(len(records)):
        for k in range(i + 1, len(records)):
            a, b = records[i], records[k]
            if a["label"] == b["label"]:
                continue
            comparable += 1
            better, worse = (
                (a, b) if LABEL_RANK[a["label"]] > LABEL_RANK[b["label"]] else (b, a)
            )
            if ranks[better["id"]] < ranks[worse["id"]]:
                concordant += 1
    pct = 100.0 * concordant / comparable if comparable else 0.0
    return {
        "comparable_pairs": comparable,
        "concordant_pairs": concordant,
        "concordant_pct": round(pct, 2),
        "tau": round(2.0 * pct / 100.0 - 1.0, 3),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK),
                    help="benchmark v2 (fonte dos rótulos)")
    ap.add_argument("--snapshot", required=True,
                    help="cópia local do eligible_jobs.json (medição; "
                         "produção data/ intocável)")
    args = ap.parse_args(argv)

    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    universe_list = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    universe = {j["id"]: j for j in universe_list}

    records = _stratum_records(benchmark, universe)
    if not records:
        print("benchmark v3: nenhuma vaga não-DE rotulada ligada ao snapshot")
        return 1
    missing = [j["id"] for j in benchmark["jobs"]
               if str(j.get("country") or "de").lower() != "de"
               and j["id"] not in universe]
    if missing:
        print(f"benchmark v3: AVISO — {len(missing)} rotuladas ausentes do "
              f"snapshot (medição nas {len(records)} presentes)")

    biz_ranks = _ranks_by(records, business=True)
    eu_ranks = _ranks_by(records, business=False)
    biz = _tau(records, biz_ranks)
    eu = _tau(records, eu_ranks)

    labels_count: dict[str, int] = {}
    for rec in records:
        labels_count[rec["label"]] = labels_count.get(rec["label"], 0) + 1

    print("=== Benchmark v3 (F36) — perfil EU non-DE vs ranking atual ===")
    print(f"  estrato: {len(records)} vagas não-DE rotuladas (v2) sobre o snapshot")
    print(f"  rótulos: " + " · ".join(
        f"{lab} {labels_count.get(lab, 0)}" for lab in LABELS_ORDER))
    print()
    print(f"  ranking ATUAL (business) no estrato: conc {biz['concordant_pct']}% "
          f"({biz['concordant_pairs']}/{biz['comparable_pairs']} pares) "
          f"tau {biz['tau']:+.3f}")
    print(f"  perfil EU (novo):                  conc {eu['concordant_pct']}% "
          f"({eu['concordant_pairs']}/{eu['comparable_pairs']} pares) "
          f"tau {eu['tau']:+.3f}")
    delta = round(eu["tau"] - biz["tau"], 3)
    target = round(biz["tau"] + 0.10, 3)
    ok = eu["tau"] >= target
    print()
    print(f"  delta tau: {delta:+.3f} | critério de aceite: "
          f"tau EU ≥ {target:+.3f} (v2-não-DE {biz['tau']:+.3f} + 0,10)")
    print(f"  RESULTADO: {'ATINGE' if ok else 'NÃO ATINGE'} o critério")
    print()
    # Top/bottom do estrato sob o perfil novo (inspeção rápida)
    top = sorted(records, key=lambda r: eu_ranks[r["id"]])[:5]
    bot = sorted(records, key=lambda r: eu_ranks[r["id"]])[-3:]
    print("  top 5 (perfil EU):")
    for rec in top:
        s = eu_score_job(rec["job"]).total
        print(f"    {eu_ranks[rec['id']]:>2}. [{rec['label']:<15}] eu {s:>5} "
              f"{rec['title'][:52]!r}")
    print("  bottom 3:")
    for rec in bot:
        s = eu_score_job(rec["job"]).total
        print(f"    {eu_ranks[rec['id']]:>2}. [{rec['label']:<15}] eu {s:>5} "
              f"{rec['title'][:52]!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
