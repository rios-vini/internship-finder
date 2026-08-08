"""CLI do internship-finder: coleta orientada a empresas.

Uso:
    internship-finder --companies "Bosch,SAP" --output data/jobs.json
    python scripts/collect_jobs.py --companies "Siemens,Bosch" --limit 50

Fluxo por empresa: find_company (selecao exata) -> scraper do ATS -> fetch
(com timeout defensivo via subprocesso) -> adapter -> Job -> print + save
(JSON e CSV).

Exit code: 0 se ao menos uma vaga foi coletada e os arquivos gravados.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

from internship_finder.collectors.ats_scraper import collect_company
from internship_finder.models.job import Job

log = logging.getLogger("internship_finder")

CSV_COLUMNS = [
    "id",
    "title",
    "company",
    "location",
    "country",
    "country_iso",
    "url",
    "source",
    "external_id",
    "employment_type",
    "internship",
    "posted_at",
    "collected_at",
]


def save_outputs(jobs: list[Job], output: Path) -> None:
    """Grava JSON e CSV (CSV derivado do nome do JSON)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        json.dump([j.to_dict() for j in jobs], fh, ensure_ascii=False, indent=2)
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for j in jobs:
            writer.writerow(j.to_dict())
    log.info("salvos: %s e %s", output, csv_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta vagas de estagio por empresa.")
    parser.add_argument(
        "--companies",
        required=True,
        help='Nomes separados por virgula, ex.: "Bosch,SAP"',
    )
    parser.add_argument(
        "--output",
        default="data/jobs.json",
        help="Arquivo JSON de saida (CSV derivado)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Timeout por scraper (s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximo de vagas por tenant (0 = sem limite)",
    )
    parser.add_argument(
        "--include-descriptions",
        action="store_true",
        help="Busca descricao por vaga (mais lento em ATS que exigem chamada por vaga)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    names = [n.strip() for n in args.companies.split(",") if n.strip()]
    if not names:
        parser.error("--companies vazio")

    all_jobs: list[Job] = []
    summaries: list[tuple[str, dict]] = []

    for name in names:
        jobs, summary = collect_company(
            name,
            timeout=args.timeout,
            include_descriptions=args.include_descriptions,
            limit=args.limit,
        )
        summaries.append((name, summary))
        all_jobs.extend(jobs)
        print(f"Found {len(jobs)} jobs for {name}")
        for j in jobs[:15]:
            print(f"  - {j}")
        if len(jobs) > 15:
            print(f"  ... +{len(jobs) - 15} vagas (lista completa no JSON/CSV)")

    total = len(all_jobs)
    print(f"\n=== TOTAL: {total} vagas ===")
    for name, summary in summaries:
        for source, n, dt in summary["ok"]:
            print(f"  OK   {source}: {n} vagas ({dt})")
        for source, err in summary["failed"]:
            print(f"  FAIL {source}: {err}")
        for source in summary["skipped"]:
            print(f"  SKIP {source}: sem scraper no pacote")
        if summary["not_found"]:
            print(f"  NONE {name}: sem match exato na base")

    if total:
        save_outputs(all_jobs, Path(args.output))
        return 0
    log.error("nenhuma vaga coletada; verifique as empresas e o pacote ats-scrapers")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
