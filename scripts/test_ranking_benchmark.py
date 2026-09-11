"""Testes do benchmark do ranking (P2.5) — infraestrutura de medição.

Cobre ``src/internship_finder/ranking_benchmark.py`` (funções puras) +
``benchmarks/ranking_benchmark_v1.json`` (arquivo versionado) + o fluxo de
refresh via ``refresh_benchmark``:

- validacao de schema/invariantes (labels validas, soma do breakdown == score,
  ordem por rank == chave oficial, justificativa obrigatoria, rank unico);
- metricas: distribuicao de scores, concordancia ordinal (pares comparaveis,
  formula Kendall-like), grupos de empate mistos, perfis de componente,
  inversoes (melhor-pior com maior impacto primeiro);
- determinismo: mesmos dados -> mesmos numeros;
- refresh: re-extrai score/breakdown/rank de snapshot novo preservando
  rotulos/justificativas e valida o resultado;
- bloco real: o benchmark versionado carrega valido, tem 59 vagas, as 5
  labels presentes, justificativa em toda vaga e snapshot registrado.

NAO depende de ``data/`` (o benchmark e versionado; em runner limpo o bloco
real roda normal). NAO altera ranking/pesos — medicao apenas.

Uso:  .venv/bin/python scripts/test_ranking_benchmark.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.ranking_benchmark import (  # noqa: E402
    LABELS_ORDER,
    component_profiles,
    false_positives_by_score,
    great_jobs_low_score,
    inversions,
    load_benchmark,
    mean_score_by_label,
    pairwise_concordance,
    refresh_benchmark,
    score_distribution,
    tie_analysis,
    validate_benchmark,
)

BENCHMARK_FILE = ROOT / "benchmarks" / "ranking_benchmark_v1.json"

FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        FAILURES.append(name)


def rec(rank: int, title: str, score: float, label: str, *, job_id: str | None = None,
        just: str = "fixture") -> dict:
    """Registro de benchmark com breakdown que SEMPRE soma ao score."""
    area = round(score - 4.0, 2)  # area + (0.75+1.0+1.0+1.0+0.25) == score
    return {
        "rank": rank,
        "id": job_id or f"A|x:{rank}",
        "title": title,
        "company": "A",
        "location": "Stuttgart, de",
        "employment_type": None,
        "url": f"https://example.com/{rank}",
        "score": score,
        "score_breakdown": {"area": area, "skills": 0.75, "language": 1.0,
                            "type": 1.0, "location": 1.0, "penalties": 0.25},
        "label": label,
        "justification": just,
    }


def make_bench(*records) -> dict:
    return {
        "schema_version": 1,
        "snapshot": {"source_file": "test", "run_date": "2026-01-01",
                     "note": "fixture de teste"},
        "labels_order": list(LABELS_ORDER),
        "labeling": {"date": "2026-01-01", "by": "teste",
                     "rubric": {"otima": "x", "boa": "x", "aceitavel": "x",
                                "ruim": "x", "falso_positivo": "x"}},
        "jobs": list(records),
    }


# ---------------------------------------------------------------------------
# 1. Validacao
# ---------------------------------------------------------------------------


def test_validation() -> None:
    print("== validacao ==")
    good = [rec(1, "Werkstudent Analytics", 13.75, "otima"), rec(2, "Intern SCM", 8.0, "boa")]
    check("fixture valida nao gera erros", validate_benchmark(make_bench(*good)) == [],
          str(validate_benchmark(make_bench(*good))))

    rec2 = rec(2, "Outra vaga", 6.0, "aceitavel", job_id="A|x:9")
    cases = [
        ("label invalida", dict(rec2, label="excelente"), "label invalida"),
        ("justificativa vazia", dict(rec2, justification=""), "justificativa"),
        ("breakdown soma != score", dict(rec2, score=5.0), "soma do breakdown"),
        ("rank duplicado", dict(rec2, rank=1), "rank duplicado"),
        ("rank nao-int", dict(rec2, rank=1.5), "rank invalido"),
    ]
    for name, mutant, needle in cases:
        errs = validate_benchmark(make_bench(rec(1, "Intern SCM", 8.0, "boa"), mutant))
        check(name, any(needle in e for e in errs), f"erros={errs}")

    # ordem por rank != chave oficial -> erro (score 9 no rank 2 vs 7 no rank 1)
    swapped = [rec(2, "Zeta Job", 9.0, "boa"), rec(1, "Alpha Job", 7.0, "ruim")]
    errs = validate_benchmark(make_bench(*swapped))
    check("ordem por rank difere da chave -> erro", any("chave oficial" in e for e in errs),
          f"erros={errs}")

    # ordem consistente (ranks na ordem da chave) -> valido
    ok_swap = [rec(1, "Alpha Job", 8.0, "boa"), rec(2, "Beta Job", 8.0, "boa"),
               rec(3, "Zeta Job", 8.0, "boa")]
    check("ordem por rank == chave oficial -> valido", validate_benchmark(make_bench(*ok_swap)) == [],
          str(validate_benchmark(make_bench(*ok_swap))))

    empty = dict(make_bench())
    empty["jobs"] = []
    check("jobs vazio -> erro", bool(validate_benchmark(empty)))

    no_order = dict(make_bench(*good))
    no_order["labels_order"] = ["otima", "boa"]
    check("labels_order divergente -> erro", bool(validate_benchmark(no_order)))


# ---------------------------------------------------------------------------
# 2. Metricas (fixtures pequenas com valores conhecidos)
# ---------------------------------------------------------------------------


def test_metrics() -> None:
    print("== metricas ==")
    # 3 vagas: otima no topo, boa no meio, ruim embaixo -> 3 pares comparaveis,
    # todos concordes -> tau = +1
    good = [rec(1, "Intern SCM", 10.0, "otima"), rec(2, "Werkstudent Logistik", 6.0, "boa"),
            rec(3, "Praktikum HR", 4.0, "ruim")]
    c = pairwise_concordance(good)
    check("concordancia perfeita -> 3/3 pares, tau=+1.0",
          c["comparable_pairs"] == 3 and c["concordant_pairs"] == 3 and c["tau"] == 1.0,
          str(c))

    # 2 pares concordes, 1 discordante (ruim acima de boa) -> 66.67%, tau=+1/3
    mixed = [rec(1, "Intern SCM", 10.0, "otima"), rec(2, "Praktikum HR", 4.0, "ruim"),
             rec(3, "Werkstudent Logistik", 6.0, "boa")]
    c2 = pairwise_concordance(mixed)
    check("1 inversao -> 2/3 concordes, tau=+0.333",
          c2["concordant_pairs"] == 2 and round(c2["tau"], 3) == 0.333, str(c2))

    # distribuicao: 3 vagas iguais sem empate -> 0 empatadas
    dist = score_distribution(good)
    check("distribuicao: 3 scores distintos, 0 empatadas", dist["distinct_scores"] == 3
          and dist["tied_jobs"] == 0 and dist["num_tie_groups"] == 0, str(dist))

    dup = [rec(1, "Intern SCM", 8.0, "boa"), rec(2, "Intern SCM 2", 8.0, "boa"),
           rec(3, "Werkstudent", 6.0, "boa")]
    d2 = score_distribution(dup)
    check("distribuicao com empate: 2/3 empatadas, 1 grupo",
          d2["tied_jobs"] == 2 and round(d2["tied_pct"], 3) == round(2 / 3 * 100, 3)
          and d2["largest_groups"][0] == (8.0, 2), str(d2))

    # grupos de empate mistos
    ties = tie_analysis(dup)
    check("grupo de empate com labels iguais NAO e misto", ties["mixed_groups"] == 0
          and ties["max_label_spread"] == 0, str(ties))
    dup[0]["label"] = "otima"
    t2 = tie_analysis(dup)
    check("mesmo score, labels diferentes -> grupo misto",
          t2["mixed_groups"] == 1 and t2["mixed_pct_of_tied"] == 100.0, str(t2))

    # score medio por rotulo na ordem de qualidade (otima, boa, aceitavel, ruim, falso)
    means = mean_score_by_label(good)
    check("mean_score_by_label: ordem completa e medias corretas",
          [m["label"] for m in means] == list(LABELS_ORDER)
          and means[0]["mean"] == 10.0 and means[1]["mean"] == 6.0
          and means[3]["mean"] == 4.0 and means[2]["mean"] is None, str(means))

    # inversoes: encontra o par ruim-acima-de-boa
    inv = inversions(mixed)
    check("inversoes encontram o par ruim-acima-de-boa",
          len(inv) == 1 and inv[0]["worse"]["label"] == "ruim"
          and inv[0]["better"]["label"] == "boa", str(inv))

    fpx = [rec(1, "Intern SCM", 10.0, "otima"), rec(2, "AI Dev", 4.0, "falso_positivo")]
    fp = false_positives_by_score(fpx)
    check("falsos positivos por score desc", len(fp) == 1 and fp[0]["title"] == "AI Dev")
    check("otimas mais baixas primeiro", [j["title"] for j in great_jobs_low_score(fpx)] == ["Intern SCM"])

    # perfis de componente: estrutura + area otima > area ruim
    prof = component_profiles(good)
    check("perfis tem as 6 componentes", set(prof) == {"area", "skills", "language",
          "type", "location", "penalties"})
    area_rows = {r["label"]: r["mean"] for r in prof["area"]["by_label"]}
    check("media de area: otima > ruim", area_rows["otima"] == 6.0 and area_rows["ruim"] == 0.0,
          str(area_rows))


# ---------------------------------------------------------------------------
# 3. Determinismo
# ---------------------------------------------------------------------------


def test_determinism() -> None:
    print("== determinismo ==")
    data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    records = load_benchmark(data)
    a = (score_distribution(records), pairwise_concordance(records),
         tie_analysis(records), component_profiles(records), inversions(records))
    b = (score_distribution(records), pairwise_concordance(records),
         tie_analysis(records), component_profiles(records), inversions(records))
    check("metricas deterministicas (mesmos dados -> mesmos numeros)", a == b)
    check("configuracao do benchmark estavel (antes==depois)", len(records) == 59)


# ---------------------------------------------------------------------------
# 4. Fluxo de refresh (reproducao do benchmark)
# ---------------------------------------------------------------------------


def test_refresh_flow() -> None:
    print("== refresh (re-extrair do snapshot preservando rotulos) ==")
    bench = make_bench(
        rec(1, "Intern SCM", 10.0, "otima"),
        rec(2, "Werkstudent Logistik", 6.0, "boa", just="just-2"),
    )
    snap = [
        {"id": "A|x:1", "title": "Intern SCM", "company": "A", "location": "Munich",
         "employment_type": "INTERN", "url": "u1", "score": 12.0,
         "score_breakdown": {"area": 7.25, "skills": 1.5, "language": 1.5,
                             "type": 1.0, "location": 1.0, "penalties": -0.25}},
        {"id": "A|x:new", "title": "Praktikum Neu", "company": "A", "location": "Berlin",
         "employment_type": None, "url": "u3", "score": 7.0,
         "score_breakdown": {"area": 3.0, "skills": 0.75, "language": 1.0,
                             "type": 1.0, "location": 1.0, "penalties": 0.25}},
    ]
    new, dropped, kept = refresh_benchmark(bench, snap, run_date="2026-02-01", source_file="snap.json")
    check("vaga sumida -> dropped; nova nao entra sozinha",
          dropped == ["A|x:2"] and kept == ["A|x:1"], f"dropped={dropped} kept={kept}")
    check("score/breakdown regravados do snapshot", new["jobs"][0]["score"] == 12.0
          and new["jobs"][0]["score_breakdown"]["skills"] == 1.5)
    check("rotulo e justificativa preservados", new["jobs"][0]["label"] == "otima"
          and new["jobs"][0]["justification"] == "fixture")
    check("rank recomputado e snapshot atualizado", new["jobs"][0]["rank"] == 1
          and new["snapshot"]["run_date"] == "2026-02-01")
    check("resultado do refresh e valido", validate_benchmark(new) == [])

    # snapshot com registro sem id -> recusa (nunca grava benchmark torto)
    bad = [{"title": "sem id", "score": 1.0, "score_breakdown": {"area": 1.0, "skills": 0.0,
            "language": 0.0, "type": 0.0, "location": 0.0, "penalties": 0.0}}]
    try:
        refresh_benchmark(bench, bad, run_date="2026-02-01", source_file="snap.json")
        check("snapshot com registro sem id -> erro", False)
    except ValueError:
        check("snapshot com registro sem id -> erro", True)


# ---------------------------------------------------------------------------
# 5. Benchmark real (versionado, disponivel no CI sem data/)
# ---------------------------------------------------------------------------


def test_real_benchmark() -> None:
    print("== benchmark versionado (real) ==")
    if not BENCHMARK_FILE.exists():
        print("  [SKIP] benchmarks/ranking_benchmark_v1.json ausente")
        return
    data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    errs = validate_benchmark(data)
    check("v1 valido (0 erros de schema)", errs == [], str(errs[:3]))
    records = load_benchmark(data)
    check("59 vagas rotuladas", len(records) == 59, f"n={len(records)}")
    check("as 5 labels presentes", set(r["label"] for r in records) >= set(LABELS_ORDER))
    check("toda vaga tem justificativa", all((r["justification"] or "").strip() for r in records))
    check("toda vaga tem url (revisao do rotulo possivel)", all(r.get("url") for r in records))
    check("snapshot registrado (run 2026-09-11)", data["snapshot"]["run_date"] == "2026-09-11")
    check("labels_order == LABELS_ORDER", list(data["labels_order"]) == list(LABELS_ORDER))

    ok_sum = all(
        abs(round(sum(r["score_breakdown"].values()), 2) - r["score"]) < 1e-9
        for r in records
    )
    check("score == soma(breakdown) em todas as 59", ok_sum)

    # cobertura de empates no arquivo real (deve ter grupos mistos — a tese da tarefa)
    t = tie_analysis(records)
    check("amostra real tem grupos de empate mistos", t["mixed_groups"] >= 8,
          f"mixed={t['mixed_groups']}")


def main() -> int:
    test_validation()
    test_metrics()
    test_determinism()
    test_refresh_flow()
    test_real_benchmark()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())