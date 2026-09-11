"""Relatorio do benchmark do ranking (P2.5) — medicao, NAO calibracao.

Le ``benchmarks/ranking_benchmark_v1.json`` (rotulos humanos versionados) e
imprime um relatorio objetivo: distribuicao de scores (amostra + universo se
``--snapshot`` apontar para o ``data/eligible_jobs.json`` vivo), qualidade vs
posicao (score medio por rotulo + concordancia ordinal Kendall-like),
analise de empates (mesmo score -> labels diferentes), perfis de componente
do score_breakdown por rotulo e exemplos de falha (padroes, nao anedotas).

Deterministico sobre os mesmos arquivos (nenhum timestamp na saida). Nao
altera nada — o ranking atual segue sendo a implementacao de referencia.

Uso:
    .venv/bin/python scripts/ranking_benchmark.py
    .venv/bin/python scripts/ranking_benchmark.py --benchmark benchmarks/ranking_benchmark_v1.json --snapshot data/eligible_jobs.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.ranking_benchmark import (  # noqa: E402
    LABEL_DISPLAY,
    LABEL_RANK,
    LABELS_ORDER,
    component_profiles,
    false_positives_by_score,
    great_jobs_low_score,
    inversions,
    load_benchmark,
    mean_score_by_label,
    pairwise_concordance,
    score_distribution,
    tie_analysis,
    tie_groups,
    validate_benchmark,
)

DEFAULT_BENCHMARK = ROOT / "benchmarks" / "ranking_benchmark_v1.json"
DEFAULT_SNAPSHOT = ROOT / "data" / "eligible_jobs.json"


def fmt_score(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def print_header(data: dict) -> None:
    print("=== Benchmark do ranking — P2.5 (medicao; sem alteracao do ranking) ===")
    snap = data.get("snapshot", {})
    print(f"  snapshot: {snap.get('source_file')} | run {snap.get('run_date')} | {snap.get('note', '')}")
    lab = data.get("labeling", {})
    print(f"  rotulagem: {lab.get('date')} — {lab.get('by')}")
    print()


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def report_distribution(records, universe: list[dict] | None) -> None:
    section("1. Distribuicao dos scores")
    d = score_distribution(records)
    print(f"  amostra ({d['total']} vagas): {d['distinct_scores']} scores distintos | "
          f"{d['tied_jobs']} empatadas ({d['tied_pct']:.1f}%) | {d['num_tie_groups']} grupos de empate")
    print("  maiores grupos de empate (amostra): "
          + ", ".join(f"{s:.2f} x{c}" for s, c in d["largest_groups"]))
    if universe:
        u = score_distribution(universe)
        print(f"  UNIVERSO ({u['total']} vagas do snapshot vivo): {u['distinct_scores']} scores " 
              f"distintos | {u['tied_jobs']} empatadas ({u['tied_pct']:.1f}%) | "
              f"{u['num_tie_groups']} grupos | maiores: "
              + ", ".join(f"{s:.2f} x{c}" for s, c in u["largest_groups"][:6]))
        print("  histograma do universo (top 15):")
        for s, c in u["per_score"][:15]:
            bar = "#" * min(c, 40)
            print(f"    {s:6.2f} x{c:<4} {bar}")


def report_quality(records) -> None:
    section("2. Qualidade humana vs posicao")
    print("  score medio por rotulo (ordem de qualidade):")
    for r in mean_score_by_label(records):
        print(f"    {LABEL_DISPLAY[r['label']]:<16} n={r['n']:<3} media={fmt_score(r['mean'])} "
              f"min={fmt_score(r['min'])} max={fmt_score(r['max'])}")
    c = pairwise_concordance(records)
    print(f"  concordancia ordinal (pares comparaveis {c['comparable_pairs']}): "
          f"{c['concordant_pairs']} concordes = {c['concordant_pct']}% | tau={c['tau']:+.3f}")


def report_ties(records) -> None:
    section("3. Empates: mesmo score esconde diferencas reais?")
    t = tie_analysis(records)
    print(f"  {t['num_tie_groups']} grupos de empate na amostra | {t['mixed_groups']} com labels "
          f"DIFERENTES | {t['jobs_in_mixed_groups']} vagas ({t['mixed_pct_of_tied']:.0f}% das empatadas) "
          f"em grupos mistos | maior dispersao de qualidade: {t['max_label_spread']} niveis")
    if t["worst_group"]:
        w = t["worst_group"]
        print(f"  pior grupo: score {w['score']:.2f} x{w['size']} -> {w['labels']} (ranks {w['ranks']})")
    print("  grupos mistos (score x composicao):")
    for g in tie_groups(records):
        if g["mixed"]:
            print(f"    {g['score']:6.2f} x{g['size']:<3} {g['labels']}")


def report_components(records) -> None:
    section("4. Componentes do score_breakdown por rotulo (descritivo)")
    prof = component_profiles(records)
    header = "  " + " | ".join(f"{LABEL_DISPLAY[l]:<14}" for l in LABELS_ORDER)
    print(header)
    for comp, info in prof.items():
        row = "  " + " | ".join(
            f"{fmt_score(r['mean']):<14}" for r in info["by_label"]
        )
        mono = ("monotono" if info["monotonic_with_quality"] is True
                else ("nao monotono" if info["monotonic_with_quality"] is False else "sem gradiente"))
        print(f"{comp:<11}{row}   [{mono}]")


def report_failures(records) -> None:
    section("5. Exemplos representativos de falha")
    print("  5.1 inversoes (vaga PIOR acima de uma MELHOR):")
    for p in inversions(records):
        b, w = p["better"], p["worse"]
        print(f"    #{w['rank']} {LABEL_DISPLAY[w['label']]:<14} score {w['score']:5.2f} | {w['title'][:58]}")
        print(f"        acima de #{b['rank']} {LABEL_DISPLAY[b['label']]:<14} score {b['score']:5.2f} | {b['title'][:58]}")
    print("  5.2 mesmo score, qualidade claramente diferente (amostra de grupos mistos):")
    shown = 0
    for g in tie_groups(records):
        if not g["mixed"]:
            continue
        labels = sorted(g["labels"], key=lambda l: -LABEL_RANK[l])
        best = next((m for m in records if m["score"] == g["score"] and m["label"] == labels[0]), None)
        worst = next((m for m in records if m["score"] == g["score"] and m["label"] == labels[-1]), None)
        if best and worst:
            print(f"    score {g['score']:5.2f}: {LABEL_DISPLAY[best['label']]:<14} '{best['title'][:44]}'"
                  f"  vs  {LABEL_DISPLAY[worst['label']]:<14} '{worst['title'][:44]}'")
            shown += 1
        if shown >= 6:
            break
    print("  5.3 falsos positivos com score relativamente alto:")
    for j in false_positives_by_score(records):
        print(f"    #{j['rank']:<3} score {j['score']:5.2f} | {j['title'][:72]}")
    print("  5.4 vagas otimas com score inesperadamente baixo:")
    for j in great_jobs_low_score(records):
        print(f"    #{j['rank']:<3} score {j['score']:5.2f} | {j['title'][:72]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK), help="arquivo do benchmark versionado")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT),
                        help="eligible_jobs.json vivo para estatisticas do universo (opcional)")
    args = parser.parse_args(argv)

    bench_path = Path(args.benchmark)
    if not bench_path.exists():
        print(f"ERRO: benchmark nao encontrado: {bench_path}")
        return 1
    data = json.loads(bench_path.read_text(encoding="utf-8"))
    errors = validate_benchmark(data)
    if errors:
        print(f"ERRO: benchmark invalido ({len(errors)} problemas):")
        for e in errors[:15]:
            print(f"  - {e}")
        return 1
    records = load_benchmark(data)

    universe = None
    snap_path = Path(args.snapshot)
    if snap_path.exists():
        universe = json.loads(snap_path.read_text(encoding="utf-8"))
        if not universe or not isinstance(universe, list) or not isinstance(universe[0], dict) or "score" not in universe[0]:
            print(f"AVISO: {snap_path} nao parece um eligible ranqueado — ignorado", file=sys.stderr)
            universe = None

    print_header(data)
    report_distribution(records, universe)
    report_quality(records)
    report_ties(records)
    report_components(records)
    report_failures(records)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())