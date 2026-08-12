"""Cobertura do pipeline (offline, deterministico, exit 0).

Le ``data/jobs.json`` (bruto), ``data/eligible_jobs.json`` (eligible, pos-dedup
e ranking) e ``data/ranked_jobs.json`` e imprime, em texto legivel:

- **Funil**: raw -> tipo estudante -> area-alvo -> pais -> eligible -> dedup
  (removidas) -> ranked. Os passos intermediarios sao RECOMPUTADOS com a
  cascata real de filtros (``filters.select_eligible``) sobre o bruto, para a
  saida nunca divergir do CLI. ``dedup removidas`` = ``pais - eligible``
  (assumindo que eligible_jobs.json foi gerado do jobs.json com o pipeline
  padrao, com dedup ligado).
- **Empresas**: empresas distintas (campo ``company``) e tenants (campo
  ``source``) no conjunto eligible, vagas por empresa (desc), contribuicao das
  maiores (top 1/3/5 e a maior em %).
- **ATS**: vagas por ATS (prefixo do ``source`` ate ``:``).
- **Paises**: vagas por ``country_iso`` (ordenado) e % de
  None/localizacao desconhecida.

Uso:
    .venv/bin/python scripts/coverage.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.filters import select_eligible  # noqa: E402


def load(name: str) -> list[dict]:
    path = ROOT / "data" / name
    if not path.exists():
        raise SystemExit(f"ERRO: {path} nao existe — rode a coleta/filtro antes")
    return json.loads(path.read_text(encoding="utf-8"))


def pct(part: int, total: int) -> str:
    return f"{100.0 * part / total:.1f}%" if total else "-"


def main() -> int:
    jobs = load("jobs.json")
    eligible = load("eligible_jobs.json")
    ranked = load("ranked_jobs.json")

    # --- Funil (recomputado com a cascata real; sem rede) ---
    _, c_tipo = select_eligible(jobs, student=True, area=False, country="all")
    _, c_area = select_eligible(jobs, student=True, area=True, country="all")
    _, c_pais = select_eligible(jobs, student=True, area=True, country="de")
    raw, tipo, area, pais = c_tipo["total"], c_tipo["tipo"], c_area["area"], c_pais["pais"]
    eligible_n = len(eligible)
    dedup_removed = pais - eligible_n
    ranked_n = len(ranked)

    print("=== Funil (--country de) ===")
    print(f"  raw coletadas        : {raw}")
    print(f"  + tipo estudante     : {tipo}")
    print(f"  + area-alvo          : {area}")
    print(f"  + pais (DE)          : {pais}")
    print(f"  eligible (pos-dedup) : {eligible_n}")
    print(f"  dedup removidas      : {dedup_removed}")
    print(f"  ranked               : {ranked_n}")

    # --- Empresas (eligible) ---
    n_companies = len({j["company"] for j in eligible})
    n_tenants = len({j["source"] for j in eligible})
    by_company = Counter(j["company"] for j in eligible)
    print("\n=== Empresas (eligible) ===")
    print(f"  {n_companies} empresas distintas | {n_tenants} tenants (source)")
    print(f"  bruto: {len({j['company'] for j in jobs})} empresas | "
          f"{len({j['source'] for j in jobs})} tenants com dados (12 operacionais)")
    for company, n in by_company.most_common():
        print(f"    {n:>4}  {company}")
    top1 = by_company.most_common(1)[0][1]
    top3 = sum(n for _, n in by_company.most_common(3))
    top5 = sum(n for _, n in by_company.most_common(5))
    print(f"  contribuicao das maiores: top1 {pct(top1, eligible_n)} | "
          f"top3 {pct(top3, eligible_n)} | top5 {pct(top5, eligible_n)}")

    # --- ATS (eligible, prefixo do source) ---
    by_ats = Counter(j["source"].split(":", 1)[0] for j in eligible)
    print("\n=== ATS (eligible) ===")
    for ats, n in sorted(by_ats.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"    {n:>4}  {ats}")

    # --- Paises (eligible) ---
    by_country = Counter(j.get("country_iso") for j in eligible)
    none_n = by_country.get(None, 0)
    print("\n=== Paises (eligible) ===")
    for code, n in sorted(by_country.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        print(f"    {n:>4}  {code if code is not None else 'None (desconhecido)'}")
    print(f"  None/localizacao desconhecida: {none_n} ({pct(none_n, eligible_n)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
