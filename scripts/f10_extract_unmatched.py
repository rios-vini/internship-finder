#!/usr/bin/env python3
"""F10 Tarefa 1: extrai empresas SEM match no intel_map (data-driven).

Lê o snapshot read-only de elegíveis (NUNCA data/ de produção), agrupa por
``company`` e lista as empresas cujo ``company_intel_for`` retorna None
(match EXATO por ``_norm`` — casefold + NFD + ß->ss + colapso de espaços),
ordenadas por contagem desc.

Serve para ANTES e DEPOIS da curadoria: o intel_map vem SEMPRE do repo
(company_intel/company_intelligence.json) e o snapshot é argumento —
assim a cobertura é medida no MESMO snapshot com dois estados do mapa.

Uso:
    .venv/bin/python scripts/f10_extract_unmatched.py [snapshot.json]

Sem argumento: /tmp/f10-baseline/eligible_jobs.json (cópia read-only).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import opportunity_intel as oi  # noqa: E402

CI = ROOT / "company_intel" / "company_intelligence.json"
DEFAULT_SNAPSHOT = Path("/tmp/f10-baseline/eligible_jobs.json")


def main() -> None:
    snapshot = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SNAPSHOT
    jobs = json.loads(snapshot.read_text(encoding="utf-8"))
    intel = oi.load_company_intel(CI)

    matched: Counter[str] = Counter()
    unmatched: Counter[str] = Counter()
    visa_friendly_jobs = 0
    titles: dict[str, list[str]] = defaultdict(list)
    countries: dict[str, set] = defaultdict(set)
    sources: dict[str, set] = defaultdict(set)

    for job in jobs:
        company = (job.get("company") or "").strip()
        if not company:
            company = "(sem company)"
        entry = oi.company_intel_for(job, intel)
        if entry is not None:
            matched[company] += 1
            if oi.visa_friendly(entry):
                visa_friendly_jobs += 1
        else:
            unmatched[company] += 1
            if len(titles[company]) < 6:
                titles[company].append(job.get("title", ""))
            if job.get("country_iso"):
                countries[company].add(job["country_iso"])
            if job.get("source"):
                sources[company].add(job["source"].split(":")[0])

    total = len(jobs)
    m = sum(matched.values())
    u = sum(unmatched.values())
    print(f"snapshot: {snapshot}")
    print(f"total de vagas: {total}")
    print(f"vagas matched:   {m} ({m / total:.1%})" if total else "sem vagas")
    print(f"vagas visa_friendly: {visa_friendly_jobs} "
          f"({visa_friendly_jobs / total:.1%})" if total else "")
    print(f"vagas unmatched: {u} ({u / total:.1%})" if total else "")
    print(f"empresas distintas unmatched: {len(unmatched)}")
    print()
    print("UNMATCHED por contagem desc:")
    for company, count in unmatched.most_common():
        isos = ",".join(sorted(countries.get(company, {"?"})))
        src = ",".join(sorted(sources.get(company, {"?"})))
        print(f"{count:4d}  {company}  [{isos}|{src}]")

    out = {
        "snapshot": str(snapshot),
        "total_jobs": total,
        "matched_jobs": m,
        "visa_friendly_jobs": visa_friendly_jobs,
        "unmatched_jobs": u,
        "unmatched_companies": len(unmatched),
        "companies": [
            {
                "company": company,
                "count": count,
                "country_isos": sorted(countries.get(company, [])),
                "sources": sorted(sources.get(company, [])),
                "titles": titles.get(company, []),
            }
            for company, count in unmatched.most_common()
        ],
    }
    out_path = Path("/tmp/f10-unmatched.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\ndetalhes (counts, ISOs, sources, títulos amostra): {out_path}")


if __name__ == "__main__":
    main()
