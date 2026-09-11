"""Benchmark do ranking (P2.5) — medicao objetiva, NAO calibracao.

Funcoes puras e deterministas: mesmos dados -> mesmos numeros. Nenhuma
alteracao de pesos/formula/regras do ranking — o ranking atual continua sendo
a implementacao de referencia. A tarefa P2.5 existe para medir ANTES de
alterar: benchmark com vagas reais rotuladas por revisao manual -> metricas ->
decisao A/B/C documentada em ``docs/ranking_benchmark.md``.

O benchmark versionado vive em ``benchmarks/ranking_benchmark_v1.json``:

- rotulos humanos ``otima > boa > aceitavel > ruim > falso_positivo``
  atribuidos por leitura do conteudo real (titulo + descricao), com
  justificativa, representando "quao adequada a vaga e para o perfil do
  projeto" — nunca "quanto eu gosto do score";
- cada registro congela, do snapshot de origem: ``rank``, ``score`` e
  ``score_breakdown`` (a posicao segue a chave oficial: score desc ->
  titulo -> empresa -> id);
- ``scripts/make_ranking_benchmark.py refresh`` re-extrai score/breakdown/rank
  de um snapshot novo usando os ids como chave estavel, preservando os
  rotulos (reproducao do benchmark sem planilha desconectada).

Metricas (stdlib, sem dependencia nova; escolha justificada em
``docs/ranking_benchmark.md``):

- ``score_distribution``: quantidade de vagas por score, scores distintos,
  proporcao de vagas empatadas (o problema de baixa resolucao);
- ``mean_score_by_label`` / ``pairwise_concordance``: qualidade humana vs
  posicao. Concordancia ordinal = fracao de pares comparaveis (labels
  diferentes) em que o rotulo melhor esta acima do pior (Kendall-like,
  tau = 2*conc - 1); sem dependencia de scipy/pandas;
- ``tie_groups`` / ``tie_analysis``: grupos de MESMO score com labels
  diferentes — o ponto central da tarefa (empates escondem diferencas?);
- ``component_profiles``: media de cada componente do score_breakdown por
  rotulo (descricao simples de qual componente separa ou nao as classes);
- ``inversions`` / ``false_positives_by_score`` / ``great_jobs_low_score``:
  exemplos representativos de falha — para descobrir PADROES, nao anedotas.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

# Ordem de qualidade (melhor -> pior). O label ``falso_positivo`` e o pior:
# a vaga nem deveria estar no eligible.
LABELS_ORDER: tuple[str, ...] = ("otima", "boa", "aceitavel", "ruim", "falso_positivo")
LABEL_RANK: dict[str, int] = {
    label: idx for idx, label in enumerate(reversed(LABELS_ORDER))
}  # otima=4 ... falso_positivo=0

# Quebras de linha/acentos apenas na apresentacao; o arquivo JSON usa ascii.
LABEL_DISPLAY: dict[str, str] = {
    "otima": "otima",
    "boa": "boa",
    "aceitavel": "aceitavel",
    "ruim": "ruim",
    "falso_positivo": "falso positivo",
}

BREAKDOWN_KEYS: tuple[str, ...] = ("area", "skills", "language", "type", "location", "penalties")

# Chave de ordenacao oficial do ranking (ranking.py rank_jobs).
def sort_key(job: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -float(job["score"]),
        str(job.get("title") or "").casefold(),
        str(job.get("company") or "").casefold(),
        str(job.get("id") or ""),
    )


# ---------------------------------------------------------------------------
# Validacao do arquivo de benchmark (schema + invariantes)
# ---------------------------------------------------------------------------


def validate_benchmark(data: dict[str, Any]) -> list[str]:
    """Valida o benchmark e devolve a lista de erros (vazia = valido)."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["benchmark nao e um objeto JSON"]
    for key in ("schema_version", "labels_order", "labeling", "jobs"):
        if key not in data:
            errors.append(f"campo de cabecalho ausente: {key!r}")

    given_order = data.get("labels_order")
    if given_order is not None and list(given_order) != list(LABELS_ORDER):
        errors.append(
            f"labels_order {given_order!r} != {list(LABELS_ORDER)!r}"
        )

    jobs = data.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        errors.append("campo 'jobs' ausente/vazio (benchmark exige >= 1 vaga)")
        return errors

    seen_ranks: set[int] = set()
    for i, job in enumerate(jobs):
        prefix = f"jobs[{i}]"
        if not isinstance(job, dict):
            errors.append(f"{prefix}: registro nao e objeto")
            continue
        for field in ("rank", "id", "title", "company", "score", "score_breakdown", "label", "justification"):
            if field not in job:
                errors.append(f"{prefix}: campo obrigatorio ausente: {field!r}")
        label = job.get("label")
        if label not in LABEL_RANK:
            errors.append(f"{prefix}: label invalida {label!r} (esperada em {list(LABELS_ORDER)!r})")
        if not (job.get("justification") or "").strip():
            errors.append(f"{prefix}: justificativa obrigatoria (rotulo manual deve ser auditavel)")
        breakdown = job.get("score_breakdown")
        if not isinstance(breakdown, dict):
            errors.append(f"{prefix}: score_breakdown ausente/nao-dict")
        else:
            if set(breakdown) != set(BREAKDOWN_KEYS):
                errors.append(f"{prefix}: breakdown {sorted(breakdown)!r} != {sorted(BREAKDOWN_KEYS)!r}")
            try:
                if abs(round(sum(float(v) for v in breakdown.values()), 2) - round(float(job["score"]), 2)) > 1e-9:
                    errors.append(
                        f"{prefix}: soma do breakdown ({sum(breakdown.values()):.2f}) != score ({job['score']})"
                    )
            except (KeyError, TypeError, ValueError):
                errors.append(f"{prefix}: score/breakdown nao numericos")
        rank = job.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            errors.append(f"{prefix}: rank invalido {rank!r}")
        elif rank in seen_ranks:
            errors.append(f"{prefix}: rank duplicado {rank}")
        seen_ranks.add(rank)  # type: ignore[arg-type]
        try:
            _ = sort_key(job)
        except (TypeError, ValueError, KeyError):
            errors.append(f"{prefix}: score/titulo/empresa/id incompativeis com a chave de ranking")

    if len(jobs) > 1:
        # O rank registrado e a posicao no UNIVERSO (ex.: 1..260 do snapshot),
        # nao na amostra. O invariante e que a ordem por rank == a ordem pela
        # chave oficial de ordenacao (score desc -> titulo -> empresa -> id).
        by_rank = sorted(jobs, key=lambda j: j["rank"])
        by_key = sorted(jobs, key=sort_key)
        if [j["id"] for j in by_rank] != [j["id"] for j in by_key]:
            errors.append(
                "ordem por rank difere da chave oficial "
                "(score desc, titulo, empresa, id)"
            )
    return errors


def load_benchmark(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Retorna os registros do benchmark, validando antes (ValueError)."""
    errors = validate_benchmark(data)
    if errors:
        raise ValueError("benchmark invalido: " + "; ".join(errors[:8]))
    return list(data["jobs"])


def refresh_benchmark(
    data: dict[str, Any],
    snapshot_jobs: list[dict[str, Any]],
    *,
    run_date: str,
    source_file: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Re-extrai score/breakdown/rank de um snapshot novo, preservando rotulos.

    Os ids das vagas sao a chave estavel (P1.1: ``<company>|<source>:<external_id>``):
    para cada registro do benchmark cujo id existe no snapshot, score/breakdown/
    titulo/empresa/local/url sao REGRAVADOS do snapshot e as posicoes sao
    recomputadas com a chave oficial (score desc -> titulo -> empresa -> id).
    Rotulos e justificativas sao HUMANOS e ficam intactos. Vagas que sumiram
    do snapshot sao REMOVIDAS (alertadas em ``dropped``); ids novos do
    snapshot nao entram sozinhos (adicionar exige rotulagem manual).

    Retorna ``(benchmark_novo, dropped_ids, kept_ids)``. O resultado e
    validado (ValueError se invalido) — nunca grava benchmark quebrado.
    """
    snapshot = {j["id"]: j for j in snapshot_jobs if isinstance(j, dict) and j.get("id")}
    missing = [j for j in snapshot_jobs if not isinstance(j, dict) or not j.get("id")]
    if missing:
        raise ValueError(f"snapshot com {len(missing)} registros sem id")

    kept, dropped = [], []
    for rec in data.get("jobs", []):
        src = snapshot.get(rec.get("id"))
        if src is None:
            dropped.append(rec.get("id"))
            continue
        rec = dict(rec)
        rec["score"] = src["score"]
        rec["score_breakdown"] = dict(src["score_breakdown"])
        for field in ("title", "company", "location", "employment_type", "url"):
            if field in src:
                rec[field] = src[field]
        kept.append(rec)

    kept.sort(key=sort_key)
    for i, rec in enumerate(kept, start=1):
        rec["rank"] = i

    new_data = dict(data)
    new_data["jobs"] = kept
    new_data["snapshot"] = {
        "source_file": source_file,
        "run_date": run_date,
        "note": "Regravao via make_ranking_benchmark.py refresh; rotulos humanos preservados por id.",
    }
    errors = validate_benchmark(new_data)
    if errors:
        raise ValueError("refresh produziria benchmark invalido: " + "; ".join(errors[:8]))
    return new_data, dropped, [r["id"] for r in kept]


# ---------------------------------------------------------------------------
# Metricas
# ---------------------------------------------------------------------------


def score_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Distribuicao de scores: por valor, distintos, empatados, maiores grupos."""
    counts = Counter(float(j["score"]) for j in records)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[0], kv[1]))
    distinct = len(counts)
    total = len(records)
    tied_jobs = sum(c for s, c in ordered if c > 1)
    groups = [(s, c) for s, c in ordered if c > 1]
    return {
        "per_score": ordered,
        "distinct_scores": distinct,
        "total": total,
        "tied_jobs": tied_jobs,
        "tied_pct": 100.0 * tied_jobs / total if total else 0.0,
        "num_tie_groups": len(groups),
        "largest_groups": sorted(groups, key=lambda kv: -kv[1])[:8],
    }


def mean_score_by_label(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score medio por rotulo (ordem de qualidade descrescente)."""
    sums: dict[str, list[float]] = {}
    for j in records:
        sums.setdefault(j["label"], []).append(float(j["score"]))
    out = []
    for label in LABELS_ORDER:  # melhor -> pior
        vals = sums.get(label, [])
        out.append({
            "label": label,
            "n": len(vals),
            "mean": sum(vals) / len(vals) if vals else None,
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
        })
    return out


def pairwise_concordance(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Concordancia ordinal entre rotulo humano e posicao (Kendall-like).

    Pares comparaveis: todas as duplas com labels DIFERENTES. Concorde =
    o rotulo melhor esta ACIMA do pior (rank menor). ``tau = 2*pct - 1``
    (equivalente ao Kendall tau quando nao ha empate de posicao; as
    posicoes sao unicas por construcao). Nenhuma biblioteca necessaria.
    """
    comparable = concordant = 0
    for i in range(len(records)):
        for k in range(i + 1, len(records)):
            a, b = records[i], records[k]
            la, lb = a["label"], b["label"]
            if la == lb:
                continue
            comparable += 1
            better, worse = (a, b) if LABEL_RANK[la] > LABEL_RANK[lb] else (b, a)
            if better["rank"] < worse["rank"]:
                concordant += 1
    pct = 100.0 * concordant / comparable if comparable else 0.0
    return {
        "comparable_pairs": comparable,
        "concordant_pairs": concordant,
        "concordant_pct": round(pct, 2),
        "tau": round(2.0 * pct / 100.0 - 1.0, 3),
    }


def tie_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grupos de MESMO score (tamanho > 1) com composicao de labels/ranks."""
    by_score: dict[float, list[dict[str, Any]]] = {}
    for j in records:
        by_score.setdefault(float(j["score"]), []).append(j)
    groups = []
    for score, members in by_score.items():
        if len(members) < 2:
            continue
        labels = Counter(m["label"] for m in members)
        groups.append({
            "score": score,
            "size": len(members),
            "labels": dict(sorted(labels.items(), key=lambda kv: -LABEL_RANK[kv[0]])),
            "distinct_labels": len(labels),
            "mixed": len(labels) > 1,
            "ranks": sorted(m["rank"] for m in members),
        })
    groups.sort(key=lambda g: (-g["size"], -g["score"]))
    return groups


def tie_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    """O ponto central: empates de score escondem diferencas de qualidade?"""
    groups = tie_groups(records)
    mixed = [g for g in groups if g["mixed"]]
    tied_jobs = sum(g["size"] for g in groups)
    max_spread = 0
    worst: dict[str, Any] | None = None
    for g in mixed:
        spread = max(LABEL_RANK[l] for l in g["labels"]) - min(LABEL_RANK[l] for l in g["labels"])
        if spread > max_spread:
            max_spread, worst = spread, g
    return {
        "num_tie_groups": len(groups),
        "mixed_groups": len(mixed),
        "tied_jobs": tied_jobs,
        "jobs_in_mixed_groups": sum(g["size"] for g in mixed),
        "mixed_pct_of_tied": 100.0 * sum(g["size"] for g in mixed) / tied_jobs if tied_jobs else 0.0,
        "max_label_spread": max_spread,
        "worst_group": worst,
    }


def component_profiles(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Media por componente do breakdown por rotulo (descricao simples).

    Para cada componente, qual classe ele separa? Um componente com media
    semelhante entre ``otima`` e ``falso_positivo`` nao e discriminativo no
    nivel humano; um com gradiente monotono acompanha a qualidade. Medida
    descritiva (nao e uma nova formula — o benchmark nao altera o ranking).
    """
    comps: dict[str, dict[str, list[float]]] = {c: {} for c in BREAKDOWN_KEYS}
    for j in records:
        b = j["score_breakdown"]
        for c in BREAKDOWN_KEYS:
            comps[c].setdefault(j["label"], []).append(float(b[c]))
    out = {}
    for c in BREAKDOWN_KEYS:
        rows = []
        for label in LABELS_ORDER:
            vals = comps[c].get(label, [])
            rows.append({
                "label": label,
                "n": len(vals),
                "mean": round(sum(vals) / len(vals), 3) if vals else None,
            })
        means = [r["mean"] for r in rows if r["mean"] is not None]
        monotonic = all(
            (means[i] - means[i + 1]) * (means[0] - means[-1]) >= -1e-9
            for i in range(len(means) - 1)
        ) if len(means) >= 2 and means[0] != means[-1] else None
        out[c] = {"by_label": rows, "monotonic_with_quality": monotonic}
    return out


def inversions(records: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Pares em que uma vaga PIOR ficou ACIMA de uma melhor.

    Ordenados pelo impacto: (diferenca de label, distancia de rank).
    """
    pairs = []
    for i in range(len(records)):
        for k in range(i + 1, len(records)):
            a, b = records[i], records[k]
            la, lb = a["label"], b["label"]
            if la == lb:
                continue
            better, worse = (a, b) if LABEL_RANK[la] > LABEL_RANK[lb] else (b, a)
            if better["rank"] > worse["rank"]:  # o melhor esta ABAIXO
                pairs.append({
                    "better": better,
                    "worse": worse,
                    "label_gap": LABEL_RANK[better["label"]] - LABEL_RANK[worse["label"]],
                    "rank_gap": worse["rank"] - better["rank"],
                })
    pairs.sort(key=lambda p: (-p["label_gap"], -p["rank_gap"]))
    return pairs[:limit]


def false_positives_by_score(records: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Falsos positivos ordenados por score desc (os mais bem ranqueados)."""
    f = [j for j in records if j["label"] == "falso_positivo"]
    f.sort(key=lambda j: (-j["score"], j["rank"]))
    return f[:limit]


def great_jobs_low_score(records: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Vagas otimas com score mais baixo (candidatas a subestimadas)."""
    f = [j for j in records if j["label"] == "otima"]
    f.sort(key=lambda j: (j["score"], j["rank"]))
    return f[:limit]