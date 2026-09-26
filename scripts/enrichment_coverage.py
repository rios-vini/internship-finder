#!/usr/bin/env python3
"""Cobertura empirica do enrichment sobre o ranking (Fase 3, spec secao 11).

OFFLINE e READ-ONLY: le o store de enrichment + o ranking elegivel e imprime
a tabela de % de records UTILIZAVEIS (extracted_at + page_is_job_posting)
com cada campo, a distribuicao de valores por campo e os totais. Base para
decidir EMPIRICAMENTE quais enrichments justificam permanecer no produto.

Regras de contagem (documentadas — mesmas da medicao de 26/09):

- denominador = records com EXTRACAO (extracted_at presente), incluindo
  PIP=false — a extracao aconteceu, o gate de exibicao e outra coisa;
- campo 'presente' = valor com SIGNIFICADO: true/false para conceitos WA,
  nivel != not_mentioned p/ idiomas, valor != not_mentioned/unclear p/ work
  mode (presenca 'ampla' inclui unclear e e mostrada a parte);
- salary conta com VALUE (o schema descarta valor sem evidencia);
- deadline conta com DATE (nunca inferida);
- 'algum WA' = record com PELO MENOS 1 dos 8 conceitos em true/false/unclear.

Uso (manual; NAO entra no CI):

    .venv/bin/python scripts/enrichment_coverage.py \
        --enrichment data/enrichment/enrichment_results.jsonl \
        [--ranking data/eligible_jobs.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.enrichment import present  # noqa: E402

WA_CONCEPTS = tuple(present.WA_CONCEPT_LABELS)


def _load_ranking(path: str | Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _field(record: dict, name: str) -> dict | None:
    field = record.get(name)
    return field if isinstance(field, dict) else None


def _val(record: dict, name: str, key: str = "value") -> str | None:
    field = _field(record, name)
    if field is None:
        return None
    raw = field.get(key)
    return raw if isinstance(raw, str) and raw.strip() else None


def _has_wa_value(record: dict) -> bool:
    return any(
        _val(record, concept) in ("true", "false", "unclear")
        for concept in WA_CONCEPTS
    )


def _pct(count: int, total: int) -> str:
    return f"{100 * count / total:.0f}%" if total else "—"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cobertura empirica dos campos de enrichment (offline).",
    )
    parser.add_argument("--enrichment", required=True, metavar="PATH",
                        help="store JSONL de enrichment (key=job_id)")
    parser.add_argument("--ranking", default=None, metavar="PATH",
                        help="eligible_jobs.json (opcional: cruza os ids "
                        "do store com o ranking atual)")
    args = parser.parse_args(argv)

    records = present.load_enrichment(args.enrichment)
    if not records:
        print("store vazio ou ilegível — nada a medir")
        return 1
    extracted = [r for r in records.values() if r.get("extracted_at") is not None]
    usable = [r for r in extracted
              if (r.get("page_is_job_posting") or {}).get("value") is True]
    n = len(extracted)
    if not n:
        print("nenhum record com extração — nada a medir")
        return 0

    ranking_ids: set[str] = set()
    if args.ranking:
        ranking_ids = {str(j.get("id")) for j in _load_ranking(args.ranking)
                       if j.get("id")}
        in_ranking = sum(1 for r in extracted if str(r.get("job_id")) in ranking_ids)
        print(f"ranking: {len(ranking_ids)} vagas; records com extração que "
              f"estão no ranking: {in_ranking}/{n}")
    print()
    print(f"records no store: {len(records)}")
    print(f"records com extração (extracted_at): {n}")
    print(f"records utilizáveis (extração + page_is_job_posting=true): "
          f"{len(usable)}")
    print(f"records stale (pending_content_hash): "
          f"{sum(1 for r in usable if r.get('pending_content_hash'))}")
    print()

    def count(predicate) -> int:
        return sum(1 for r in extracted if predicate(r))

    rows = [
        ("salary (com valor)", count(lambda r: _val(r, "salary"))),
        ("work mode (valor definido)",
         count(lambda r: _val(r, "work_mode") in ("on_site", "hybrid", "remote"))),
        ("work mode (ampla, incl. unclear)",
         count(lambda r: _val(r, "work_mode") in
               ("on_site", "hybrid", "remote", "unclear"))),
        ("location enriquecida", count(lambda r: _val(r, "location"))),
        ("student status", count(lambda r: _val(r, "student_status_required")
                                 in ("true", "false"))),
        ("internship compatible",
         count(lambda r: _val(r, "internship_compatible") in ("true", "false"))),
        ("english level", count(lambda r: _val(r, "english_requirement", "level")
                                not in (None, "not_mentioned"))),
        ("german level", count(lambda r: _val(r, "german_requirement", "level")
                               not in (None, "not_mentioned"))),
        ("employer deadline (data)",
         count(lambda r: (_field(r, "employer_deadline") or {}).get("date"))),
        ("algum conceito WA com valor", count(_has_wa_value)),
    ]
    print(f"== Cobertura por campo (base: {n} records com extração) ==")
    for label, c in rows:
        print(f"  {label:<38} {c:>3}/{n}  {_pct(c, n)}")

    print()
    print("== Distribuição de valores por campo ==")
    for name, key in (("student_status_required", "value"),
                      ("internship_compatible", "value"),
                      ("work_mode", "value"),
                      ("german_requirement", "level"),
                      ("english_requirement", "level")):
        dist: dict[str, int] = {}
        for r in extracted:
            v = _val(r, name, key) or "ausente"
            dist[v] = dist.get(v, 0) + 1
        print(f"  {name}: " + " · ".join(
            f"{k} {v} ({_pct(v, n)})" for k, v in sorted(dist.items())))
    for concept in WA_CONCEPTS:
        dist = {}
        for r in extracted:
            v = _val(r, concept) or "ausente"
            dist[v] = dist.get(v, 0) + 1
        if set(dist) - {"ausente", "not_mentioned"}:
            print(f"  {concept}: " + " · ".join(
                f"{k} {v} ({_pct(v, n)})" for k, v in sorted(dist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
