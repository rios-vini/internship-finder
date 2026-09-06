"""Testes do CompanyRegistry operacional (scripts/test_registry.py).

Cobre, offline e deterministicamente (sem rede, sem ler/gravar em data/):

1. seed correto: 39 empresas, nomes canonicos e campos esperados.
2. ``enabled`` default True; desabilitar remove da selecao sem remover do seed.
3. selecao de subconjunto via ``enabled(names=...)`` preservando a ordem.
4. ``registry_names`` (ponte registry -> lista do CLI) com e sem subconjunto.
5. ponte registry->coleta do CLI: ``--registry`` usa as ENABLED; o modo
   ``--companies`` puro segue funcionando como antes (mock do fetch).
6. ``company_status`` deriva o estado por empresa do JSONL (read-only).

Uso:  .venv/bin/python scripts/test_registry.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.registry import (  # noqa: E402
    CompanyRegistry,
    RegistryEntry,
    registry_names,
)

FAILURES: list[str] = []

CANONICAL_39 = [
    "Bosch", "SAP", "Continental", "ZF", "Bayer", "BASF", "Henkel", "Infineon",
    "Zalando", "Delivery Hero", "Covestro", "Evonik", "DHL", "Hellmann", "Lidl",
    "Kaufland", "VWAGLPPROD10", "Schaeffler", "Mahle", "Trumpf", "SICK AG",
    "Voith", "knorrbremsP2", "brosefahrz", "Phoenix Contact", "KraussMaffei",
    "kronesag", "bbraunprd", "Sartorius", "freseniusglobal", "Deutsche Telekom",
    "Celonis", "DATEV", "Statista", "Scout24", "Siemens Healthineers",
    "Zeiss Group", "draegerP", "Uniper",
]


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# 1. seed
# ---------------------------------------------------------------------------
def test_seed() -> None:
    print("== seed: 39 empresas canonicas ==")
    reg = CompanyRegistry()
    names = [e.name for e in reg.entries]
    check("1a. seed tem 39 empresas", len(names) == 39, f"n={len(names)}")
    check("1b. nomes canonicos identicos ao README/docs",
          names == sorted(CANONICAL_39),
          "ordem alfabetica do registry != lista canonica")
    check("1c. nomes unicos", len(set(names)) == len(names))
    missing = [n for n in CANONICAL_39 if reg.get(n) is None]
    check("1d. todas as 39 canonicas presentes", not missing, f"faltam {missing}")
    # campos esperados
    bad = [e.name for e in reg.entries
           if not isinstance(e.name, str) or not isinstance(e.enabled, bool)]
    check("1e. name/enabled com tipo esperado em todas", not bad, f"{bad}")
    # tenant e opcional; exigir pelo menos fonte parcial quando conhecida nao e
    # contrato — so garantimos que campos extras nao quebram.
    check("1f. seed determinístico (mesma ordem 2x)",
          [e.name for e in reg.entries] == [e.name for e in CompanyRegistry().entries])


# ---------------------------------------------------------------------------
# 2. enabled default
# ---------------------------------------------------------------------------
def test_enabled_default() -> None:
    print("== enabled default True ==")
    reg = CompanyRegistry()
    check("2a. todas habilitadas por default",
          all(e.enabled for e in reg.entries),
          f"{sum(1 for e in reg.entries if not e.enabled)} desabilitadas")
    check("2b. enabled() retorna as 39",
          len(reg.enabled()) == 39, f"n={len(reg.enabled())}")
    # desabilitar remove da selecao, mantendo a entrada no registry
    row = RegistryEntry(name="Zzz", enabled=False)
    reg2 = CompanyRegistry([row])
    check("2c. entrada desabilitada excluida do enabled()",
          reg2.enabled() == [] and reg2.get("Zzz") is not None)
    check("2d. entrada desabilitada excluida mesmo com names=",
          reg2.enabled(["Zzz"]) == [])


# ---------------------------------------------------------------------------
# 3. selecao de subconjunto
# ---------------------------------------------------------------------------
def test_subset() -> None:
    print("== selecao de subconjunto preserva ordem ==")
    reg = CompanyRegistry()
    sub = reg.enabled(["SAP", "Bosch", "Uniper"])
    check("3a. subset com ordem informada",
          [e.name for e in sub] == ["SAP", "Bosch", "Uniper"],
          f"{[e.name for e in sub]}")
    check("3b. nome fora do registry ignorado",
          [e.name for e in reg.enabled(["NaoExiste", "SAP"])] == ["SAP"])
    check("3c. sem names = todas habilitadas (ordem alfabetica)",
          reg.enabled(None) == reg.entries)


# ---------------------------------------------------------------------------
# 4. registry_names (ponte registry -> lista str para o CLI)
# ---------------------------------------------------------------------------
def test_registry_names() -> None:
    print("== registry_names ==")
    reg = CompanyRegistry()
    allnames = registry_names(reg)
    check("4a. sem subconjunto devolve as 39", len(allnames) == 39,
          f"n={len(allnames)}")
    subset = registry_names(reg, ["BaYer", "bosch"])
    check("4b. subset preserva ordem e ignora nao encontrados",
          subset == [], f"{subset} (nomes com casing errado)")
    subset2 = registry_names(reg, ["Bayer", "SAP"])
    check("4c. subset exato em ordem", subset2 == ["Bayer", "SAP"])
    called = registry_names(CompanyRegistry([RegistryEntry(name="A", enabled=False)]))
    check("4d. somente empresas habilitadas", called == [])


# ---------------------------------------------------------------------------
# 5. ponte registry->coleta do CLI (mock, sem rede)
# ---------------------------------------------------------------------------
def test_cli_bridge() -> None:
    print("== CLI: --registry (subset e default) e --companies compat ==")
    from internship_finder import cli

    job_dict = {
        "id": "s:1", "source": "successfactors:acme", "title": "Praktikum Einkauf",
        "company": "Acme", "url": "https://a/1", "location": "Berlin, DE",
        "collected_at": "2026-08-01T00:00:00Z",
    }

    def _collect(name, **kw):
        summary = {"ok": [("successfactors:acme", 1, "1.0s")], "empty": [],
                   "timeout": [], "failed": [], "skipped": [], "not_found": False}
        return [job_dict], summary

    # NUNCA escrever em data/: redireciona metricas e saídas para /tmp.
    tmp = tempfile.mkdtemp()
    metrics = f"{tmp}/metrics.jsonl"
    called: list[str] = []

    def _collect_track(name, **kw):
        called.append(name)
        return _collect(name, **kw)

    # (a) --registry restrita a subconjunto via --companies, na ordem informada
    with patch.object(cli, "collect_company", side_effect=_collect_track):
        rc = cli.main(["--registry", "--companies", "SAP,Bosch",
                       "--output", f"{tmp}/j1.json",
                       "--filter-output", f"{tmp}/e1.json",
                       "--metrics", metrics])
    check("5a. --registry --companies subset exit 0", rc == 0, f"rc={rc}")
    check("5b. coletou somente o subconjunto na ordem informada",
          called == ["SAP", "Bosch"], f"{called}")
    check("5c. output gravado", Path(f"{tmp}/j1.json").exists())

    # (b) --registry sem --companies usa TODAS as ENABLED (39)
    called.clear()
    with patch.object(cli, "collect_company", side_effect=_collect_track):
        rc = cli.main(["--registry", "--output", f"{tmp}/j2.json",
                       "--filter-output", f"{tmp}/e2.json",
                       "--metrics", f"{tmp}/m2.jsonl"])
    check("5d. --registry default usa as 39 ENABLED", rc == 0
          and len(called) == 39, f"rc={rc} n={len(called)}")
    check("5e. selecao ENABLED = seed alfabetico (sem duplicatas)",
          called == [e.name for e in CompanyRegistry().entries], f"{called[:5]}...")

    # (c) --companies puro (sem --registry) segue exatamente como antes
    called.clear()
    with patch.object(cli, "collect_company", side_effect=_collect_track):
        rc = cli.main(["--companies", "Bosch,SAP", "--output", f"{tmp}/j3.json",
                       "--filter-output", f"{tmp}/e3.json",
                       "--metrics", f"{tmp}/m3.jsonl"])
    check("5f. --companies puro compativel (ordem da lista)", rc == 0
          and called == ["Bosch", "SAP"], f"rc={rc} {called}")


# ---------------------------------------------------------------------------
# 6. company_status derivado do JSONL (read-only)
# ---------------------------------------------------------------------------
def test_company_status() -> None:
    print("== company_status derivado do JSONL (read-only) ==")
    reg = CompanyRegistry()
    # arquivo inexistente -> tudo None sem quebrar
    st = reg.company_status("/tmp/nao_existe_metrics_xyz.jsonl")
    check("6a. sem JSONL -> status None para todas", st["Bosch"]["status"] is None
          and len(st) == 39)

    tmp = tempfile.mkdtemp()
    p = Path(tmp) / "m.jsonl"
    p.write_text(
        json.dumps({"type": "tenant", "company": "Bosch", "status": "ok",
                    "collected": 5, "timestamp": "2026-09-01T00:00:00Z"}) + "\n" +
        json.dumps({"type": "tenant", "company": "Bosch", "status": "error",
                    "collected": 0, "timestamp": "2026-09-02T00:00:00Z"}) + "\n" +
        "lixo nao-json\n" +
        json.dumps({"type": "run", "company": "SAP", "status": "ok"}) + "\n"
    )
    st = reg.company_status(p)
    check("6b. ultima linha da empresa vence", st["Bosch"]["status"] == "error",
          f"{st['Bosch']}")
    check("6c. ultimo estado carrega data/contagem",
          st["Bosch"]["last_run"] == "2026-09-02T00:00:00Z"
          and st["Bosch"]["last_collected"] == 0)
    check("6d. registro nao-tenant ignorado (empresa sem tenant fica None)",
          st["SAP"]["status"] is None)
    check("6e. JSONL malformado nao derruba", len(st) == 39)


def main() -> int:
    test_seed()
    print()
    test_enabled_default()
    print()
    test_subset()
    print()
    test_registry_names()
    print()
    test_cli_bridge()
    print()
    test_company_status()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())