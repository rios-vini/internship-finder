"""Verifica a presenca de empresas na base do ats-scrapers e o estado dos tenants.

Uso (runbook "Como adicionar empresas"):
    .venv/bin/python scripts/verify_companies.py "ZF,Bayer,BASF"          # so matching
    .venv/bin/python scripts/verify_companies.py "ZF,Bayer,BASF" --fetch  # + testa scraper

Sem ``--fetch``: tabela de matching exato (tenant ``ats:slug``, URL quando o
ATS exige URL como slug, e se ha scraper registrado para o ATS).
Com ``--fetch``: roda o scraper de cada tenant (com timeout) e reporta o
status real: ``OK`` com N vagas, ``FAIL`` (tenant inativo/erro), ``SKIP``
(sem scraper no pacote) ou ``NONE`` (sem match exato na base).
"""

from __future__ import annotations

import argparse
import sys

from internship_finder.collectors.ats_scraper import collect_company, scraper_slug
from internship_finder.collectors.company import CompanyCollector


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("companies", help="Nomes separados por virgula, ex.: ZF,Bayer,BASF")
    parser.add_argument("--fetch", action="store_true", help="testa o scraper de cada tenant")
    parser.add_argument("--timeout", type=float, default=60.0, help="timeout por scraper (s)")
    parser.add_argument("--limit", type=int, default=0, help="maximo de vagas por tenant")
    args = parser.parse_args(argv)

    collector = CompanyCollector()
    for name in [n.strip() for n in args.companies.split(",") if n.strip()]:
        companies = collector.find_company(name)
        print(f"\n== {name} -> {len(companies)} match(es)")
        for c in companies:
            print(
                f"   {c.source:32s} ats={c.ats:15s} slug={scraper_slug(c)!r:50s} "
                f"url={c.url!r:35s} scraper={collector.has_scraper(c)}"
            )
        if not companies:
            print("   NONE: sem match exato na base")
        if args.fetch:
            _, summary = collect_company(name, timeout=args.timeout, limit=args.limit)
            for source, n, dt in summary["ok"]:
                print(f"   OK   {source}: {n} vagas ({dt})")
            for source, err in summary["failed"]:
                print(f"   FAIL {source}: {err}")
            for source in summary["skipped"]:
                print(f"   SKIP {source}: sem scraper no pacote")
            if summary["not_found"]:
                print("   NONE: sem match exato na base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
