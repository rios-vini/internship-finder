"""CLI do internship-finder: coleta orientada a empresas + filtros de utilidade.

Dois modos:

- **Filtro (default):** le vagas coletadas (``--input``), aplica a cascata de
  filtros de utilidade, remove duplicatas, RANQUEIA por compatibilidade com o
  perfil (score + TOP 20; ``--no-rank`` desliga) e grava as ELIGIBLE em
  ``--output`` com ``score``/``score_breakdown``::

      internship-finder                                  # data/jobs.json -> data/eligible_jobs.json (ranqueado)
      internship-finder --country europe --no-area       # Europa, qualquer area
      internship-finder --all                            # copia tudo, sem filtros

- **Coleta:** com ``--companies``, coleta novas vagas (fluxo original, grava o
  bruto em ``--output``, default ``data/jobs.json``) e, em seguida, aplica a
  mesma cascata e grava o resultado em ``--filter-output``::

      internship-finder --companies "Bosch,SAP" --output data/jobs.json

Cascata de contagens (tudo ligado por padrao): total -> tipo estudante/estagio
-> area-alvo -> pais (``--country``, default ``de``). ``--all`` desliga os tres
filtros de uma vez. Exit code 0 se algo foi gravado.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

from internship_finder.collectors.ats_scraper import collect_company
from internship_finder.dedup import deduplicate
from internship_finder.filters import select_eligible
from internship_finder.models.job import Job
from internship_finder.ranking import rank_jobs

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
    "score",
]


def save_outputs(jobs: list[Job] | list[dict], output: Path) -> None:
    """Grava JSON e CSV (CSV derivado do nome do JSON). Aceita Job ou dict."""
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [j.to_dict() if hasattr(j, "to_dict") else j for j in jobs]
    with output.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    log.info("salvos: %s e %s", output, csv_path)


def print_cascade(counts: dict[str, int], country: str) -> None:
    """Imprime as contagens em cascata: total -> tipo -> area -> pais."""
    print("=== Cascata de filtros ===")
    print(f"  total            : {counts['total']}")
    print(f"  + tipo estudante : {counts['tipo']}")
    print(f"  + area-alvo      : {counts['area']}")
    print(f"  + pais           : {counts['pais']}   (--country {country})")


def print_examples(jobs: list[dict] | list[Job], limit: int = 15) -> None:
    """Exemplos da lista final (titulo, empresa, local, URL)."""
    for j in jobs[:limit]:
        d = j.to_dict() if hasattr(j, "to_dict") else j
        print(f"  - {d['title']} | {d['company']} | {d.get('location') or '-'} | {d['url']}")
    if len(jobs) > limit:
        print(f"  ... +{len(jobs) - limit} vagas (lista completa no JSON/CSV)")


def print_dedup_report(dedup_stats: dict[str, int]) -> None:
    """Linha do relatorio de dedup: quantas removidas e por qual chave."""
    total = sum(dedup_stats.values())
    if not total:
        return
    print(
        f"dedup: removidas {total} "
        f"({dedup_stats.get('external_id', 0)} por external_id, "
        f"{dedup_stats.get('url', 0)} por URL, "
        f"{dedup_stats.get('company+title+location', 0)} por company+title+location)"
    )


def print_ranking(jobs: list[dict], top: int = 20) -> None:
    """TOP N ranqueados com score e breakdown curto (area/skills/lang/tipo/loc/pen)."""
    n = min(top, len(jobs))
    print(f"\n=== TOP {n} (ranking por perfil) ===")
    for i, j in enumerate(jobs[:n], 1):
        b = j.get("score_breakdown") or {}
        parts = " ".join(f"{k} {v:+.1f}" for k, v in b.items())
        print(
            f"  {i:>2}. {j['score']:6.2f} | {j['title'][:60]} | "
            f"{j.get('company')} | {parts}"
        )
    if len(jobs) > n:
        print(f"  ... +{len(jobs) - n} vagas (score completo no JSON/CSV)")


def run_filter_pipeline(
    jobs: list[Job] | list[dict],
    *,
    student: bool,
    area: bool,
    country: str,
    output: Path,
    dedup: bool = True,
    rank: bool = True,
) -> int:
    """Aplica a cascata, remove duplicatas, ranqueia por perfil, imprime e grava.

    A deduplicacao roda sobre o conjunto ja filtrado (a saida eligible nao
    tem duplicatas); ``dedup=False`` (--no-dedup) a desliga. O ranking
    (``rank=True``, default) adiciona ``score`` + ``score_breakdown`` a cada
    vaga, ordena desc (melhores primeiro) e imprime o TOP 20; ``rank=False``
    (--no-rank) mantem a ordem original e imprime exemplos como antes.
    """
    selected, counts = select_eligible(
        [j.to_dict() if hasattr(j, "to_dict") else j for j in jobs],
        student=student,
        area=area,
        country=country,
    )
    print_cascade(counts, country)
    if dedup:
        selected, dedup_stats, _ = deduplicate(selected)
        print_dedup_report(dedup_stats)
    if rank:
        selected = rank_jobs(selected)
    print(f"\n=== {len(selected)} vagas eligible{', ranqueadas por perfil' if rank else ''} ===")
    if rank:
        print_ranking(selected)
    else:
        print_examples(selected)
    save_outputs(selected, output)
    return 0 if selected else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Coleta vagas por empresa e/ou filtra vagas candidataveis "
        "(estudante/estagio + area-alvo + pais)."
    )
    parser.add_argument(
        "--companies",
        help='Nomes separados por virgula, ex.: "Bosch,SAP" (modo coleta; sem ele, '
        "filtra --input)",
    )
    parser.add_argument(
        "--input",
        default="data/jobs.json",
        help="JSON bruto de entrada (modo filtro; default: data/jobs.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="modo filtro: saida eligible (default: data/eligible_jobs.json); "
        "modo coleta: saida bruta (default: data/jobs.json)",
    )
    parser.add_argument(
        "--filter-output",
        default="data/eligible_jobs.json",
        help="modo coleta: saida eligible (default: data/eligible_jobs.json)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Timeout por scraper (s) — modo coleta",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximo de vagas por tenant (0 = sem limite) — modo coleta",
    )
    parser.add_argument(
        "--include-descriptions",
        action="store_true",
        help="Busca descricao por vaga (mais lento em ATS que exigem chamada por vaga)",
    )
    parser.add_argument(
        "--student",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Filtra tipo estudante/estagio (default: ligado; --no-student desliga)",
    )
    parser.add_argument(
        "--area",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Filtra areas-alvo do dono (Supply Chain, Procurement, BI, Analytics, "
        "Automacao; default: ligado; --no-area desliga)",
    )
    parser.add_argument(
        "--country",
        "--countries",
        dest="country",
        default="de",
        help="Pais/localizacao: ISO alpha-2 (de,at,ch), 'europe', 'remote' ou "
        "'all' (default: de)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Desliga os tres filtros (tipo, area, pais): copia o conjunto inteiro",
    )
    parser.add_argument(
        "--dedup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove duplicatas da saida (default: ligado; --no-dedup desliga)",
    )
    parser.add_argument(
        "--rank",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rankeia as vagas por compatibilidade com o perfil (score + TOP 20; "
        "default: ligado; --no-rank desliga e mantem a ordem original)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.all:
        args.student = False
        args.area = False
        args.country = "all"

    if args.companies:
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

        if not total:
            log.error("nenhuma vaga coletada; verifique as empresas e o pacote ats-scrapers")
            return 1
        raw_output = Path(args.output or "data/jobs.json")
        save_outputs(all_jobs, raw_output)
        return run_filter_pipeline(
            all_jobs,
            student=args.student,
            area=args.area,
            country=args.country,
            output=Path(args.filter_output),
            dedup=args.dedup,
            rank=args.rank,
        )

    # Modo filtro (default): le vagas ja coletadas e filtra.
    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"--input nao encontrado: {input_path} (colete antes com --companies)")
    with input_path.open(encoding="utf-8") as fh:
        jobs = json.load(fh)
    output = Path(args.output or "data/eligible_jobs.json")
    return run_filter_pipeline(
        jobs,
        student=args.student,
        area=args.area,
        country=args.country,
        output=output,
        dedup=args.dedup,
        rank=args.rank,
    )


if __name__ == "__main__":
    raise SystemExit(main())
