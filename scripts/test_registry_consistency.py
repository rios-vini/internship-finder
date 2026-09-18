"""Testes da consistencia Registry x runtime — tenant declarado x tenant real.

Valida offline (sem rede, sem ler/gravar em ``data/``) a classificacao por
empresa entre o tenant declarado no Registry (``RegistryEntry.tenant``) e os
tenants que o runtime resolve/coleta (``ats:slug``):

1. tenant explicito e igual        -> ``consistent`` (normal);
2. tenant explicito e diferente    -> ``drift`` (divergencia detectada);
3. tenant ausente (``None``) com runtime resolvido -> ``dynamic`` (resolucao
   dinamica deliberada — NAO e drift; None nunca vira drift);
4. runtime sem resolucao          -> ``not_found`` (o comportamento existente
   de coleta continua intacto; a validacao nao mascara o erro original);
5. multiplas empresas -> comparacao POR EMPRESA: tenants compartilhados
   (ex.: ``successfactors:jobs`` em varias empresas) nao confundem a
   classificacao de uma com a de outra (identidade empresa + ATS + tenant);
6. cobertura extra (declarado presente entre N>1 resolucoes) -> ``multi``
   (informativo, nao e erro); declarado ausente entre N>1 -> ``drift``;
7. ``no_data`` (empresa sem registro de runtime) distinto de ``not_found``;
8. ``latest_run_tenants`` (extracao do run mais recente do JSONL);
9. integracao: ``--health`` expoe a secao ``registry_consistency``.

Uso:  .venv/bin/python scripts/test_registry_consistency.py
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.registry import (  # noqa: E402
    RegistryEntry,
    latest_run_tenants,
    tenant_consistency_report,
    tenant_consistency_status,
)

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def entry(name: str, tenant: str | None, ats: str | None = None) -> RegistryEntry:
    return RegistryEntry(name=name, ats=ats, tenant=tenant)


def status_of(report: list[dict], company: str) -> dict:
    return next(r for r in report if r["company"] == company)


# ---------------------------------------------------------------------------
# 1. Tenant explicito e igual
# ---------------------------------------------------------------------------
def test_explicit_equal() -> None:
    print("== [1] tenant explicito e runtime igual -> consistent ==")
    st = tenant_consistency_status("successfactors:jobs", ["successfactors:jobs"])
    check("1a. explicito igual -> consistent", st == "consistent", f"status={st}")
    report = tenant_consistency_report(
        [entry("SAP", "successfactors:jobs")],
        {"SAP": ["successfactors:jobs"]},
    )
    check("1b. relatorio: consistent com tenant/ats preservados",
          report[0]["status"] == "consistent"
          and report[0]["registry_tenant"] == "successfactors:jobs"
          and report[0]["runtime_tenants"] == ["successfactors:jobs"])
    check("1c. campos do relatorio completos",
          set(report[0]) == {"company", "ats", "registry_tenant",
                             "runtime_tenants", "status"})


# ---------------------------------------------------------------------------
# 2. Tenant explicito e diferente
# ---------------------------------------------------------------------------
def test_explicit_different() -> None:
    print("== [2] tenant explicito e runtime diferente -> drift ==")
    st = tenant_consistency_status("successfactors:jobs", ["workday:other/inc"])
    check("2a. explicito diferente -> drift", st == "drift", f"status={st}")
    report = tenant_consistency_report(
        [entry("SAP", "successfactors:jobs")],
        {"SAP": ["workday:other/inc"]},
    )
    row = report[0]
    check("2b. relatorio identifica company/ats/registry/runtime/status",
          row["company"] == "SAP" and row["registry_tenant"] == "successfactors:jobs"
          and row["runtime_tenants"] == ["workday:other/inc"]
          and row["status"] == "drift")
    # A classificacao e por EMPRESA: outra empresa no mesmo tenant nao muda a
    # de SAP (empresa resolvida em tenant compartilhado com declaracao propria
    # diferente continua drift).
    report2 = tenant_consistency_report(
        [entry("A", "successfactors:jobs"), entry("B", "workday:b")],
        {"A": ["successfactors:jobs"], "B": ["successfactors:jobs"]},
    )
    check("2c. tenant compartilhado nao confunde empresas (B continua drift)",
          status_of(report2, "B")["status"] == "drift"
          and status_of(report2, "A")["status"] == "consistent")


# ---------------------------------------------------------------------------
# 3. Tenant ausente (None) -> dynamic, nunca drift
# ---------------------------------------------------------------------------
def test_none_dynamic() -> None:
    print("== [3] tenant None com runtime resolvido -> dynamic (nao drift) ==")
    st = tenant_consistency_status(None, ["workday:datev/Datev_Careers"])
    check("3a. None + resolvido -> dynamic", st == "dynamic", f"status={st}")
    report = tenant_consistency_report(
        [entry("DATEV", None)],
        {"DATEV": ["workday:datev/Datev_Careers"]},
    )
    check("3b. relatorio marca dynamic com registry_tenant None",
          report[0]["status"] == "dynamic" and report[0]["registry_tenant"] is None)
    # None + N resolucoes tambem e dynamic (resolucao continua sendo da base).
    st2 = tenant_consistency_status(None, ["a:x", "b:y"])
    check("3c. None + multiplas resolucoes -> dynamic (nao multi/drift)",
          st2 == "dynamic", f"status={st2}")


# ---------------------------------------------------------------------------
# 4. Runtime sem resolucao -> not_found (nao mascara o erro original)
# ---------------------------------------------------------------------------
def test_not_found() -> None:
    print("== [4] runtime sem resolucao -> not_found ==")
    st = tenant_consistency_status("successfactors:jobs", [])
    check("4a. explicito + sem resolucao -> not_found", st == "not_found", f"status={st}")
    st2 = tenant_consistency_status(None, [])
    check("4b. None + sem resolucao -> not_found (nunca drift)",
          st2 == "not_found", f"status={st2}")
    st3 = tenant_consistency_status("x:y", [None, "", "  "])
    check("4c. sources invalidos/vazios contam como sem resolucao",
          st3 == "not_found", f"status={st3}")
    report = tenant_consistency_report(
        [entry("SAP", "successfactors:jobs")], {"SAP": []})
    check("4d. relatorio: not_found com lista vazia",
          report[0]["status"] == "not_found" and report[0]["runtime_tenants"] == [])
    # O registro original do JSONL (status not_found) nao e alterado por
    # nenhuma etapa — a validacao so le.
    rec = {"type": "tenant", "run_id": "2026-09-12T06:00:00+00:00", "company": "SAP",
           "source": "", "status": "not_found"}
    tenants = latest_run_tenants([rec])
    check("4e. registro not_found vira lista vazia (distinto de sem dados)",
          tenants == {"SAP": []}, f"{tenants}")


# ---------------------------------------------------------------------------
# 5. Multiplas empresas com tenants compartilhados -> por empresa
# ---------------------------------------------------------------------------
def test_shared_tenant_identity() -> None:
    print("== [5] multiplas empresas / tenants compartilhados -> por empresa ==")
    # Mesmo cenario real: successfactors:jobs cobre SAP/ZF/Kaufland e
    # phenom:nan cobre DHL/Allianz/Merck. Cada empresa so olha a propria
    # resolucao.
    entries_ = [
        entry("SAP", "successfactors:jobs"),
        entry("ZF", "successfactors:jobs"),
        entry("DHL", "phenom:nan"),
        entry("Allianz", "phenom:nan"),
    ]
    runtime = {
        "SAP": ["successfactors:jobs"],
        "ZF": ["successfactors:jobs"],
        "DHL": ["phenom:nan"],
        "Allianz": ["phenom:nan", "workday:allianz/extra"],  # cobertura extra
    }
    report = tenant_consistency_report(entries_, runtime)
    check("5a. SAP consistent", status_of(report, "SAP")["status"] == "consistent")
    check("5b. ZF consistent (mesmo tenant compartilhado)",
          status_of(report, "ZF")["status"] == "consistent")
    check("5c. DHL consistent", status_of(report, "DHL")["status"] == "consistent")
    # Allianz resolveu phenom:nan + um extra: multi, nao drift (declarado
    # presente) — e nenhum status de Allianz afeta SAP/ZF/DHL.
    check("5d. Allianz com extra -> multi (declarado presente)",
          status_of(report, "Allianz")["status"] == "multi"
          and status_of(report, "Allianz")["runtime_tenants"]
          == ["phenom:nan", "workday:allianz/extra"])
    check("5e. nenhum drift na cena compartilhada",
          all(r["status"] != "drift" for r in report))


# ---------------------------------------------------------------------------
# 6. multi x drift com N>1 resolucoes
# ---------------------------------------------------------------------------
def test_multi_vs_drift() -> None:
    print("== [6] N>1 resolucoes: declarado presente -> multi; ausente -> drift ==")
    st = tenant_consistency_status("eightfold:bayer",
                                   ["eightfold:bayer", "moka:bayer/148387"])
    check("6a. declarado presente entre extras -> multi", st == "multi", f"status={st}")
    st2 = tenant_consistency_status("eightfold:bayer",
                                    ["moka:bayer/148387", "successfactors:jobs"])
    check("6b. declarado ausente entre extras -> drift", st2 == "drift", f"status={st2}")
    # Bayer real (12/09): eightfold:bayer + moka + successfactors -> multi.
    report = tenant_consistency_report(
        [entry("Bayer", "eightfold:bayer")],
        {"Bayer": ["successfactors:jobs", "eightfold:bayer", "moka:bayer/148387"]},
    )
    check("6c. cenario Bayer real -> multi, ordenado",
          report[0]["status"] == "multi"
          and report[0]["runtime_tenants"]
          == ["eightfold:bayer", "moka:bayer/148387", "successfactors:jobs"])


# ---------------------------------------------------------------------------
# 7. no_data (empresa sem registro) distinto de not_found
# ---------------------------------------------------------------------------
def test_no_data() -> None:
    print("== [7] empresa sem informacao de runtime -> no_data ==")
    report = tenant_consistency_report(
        [entry("Bosch", "smartrecruiters:BoschGroup")], {})
    check("7a. ausente do mapeamento -> no_data",
          report[0]["status"] == "no_data" and report[0]["runtime_tenants"] == [])
    report2 = tenant_consistency_report(
        [entry("A", "x:y"), entry("B", None)],
        {"A": ["x:y"]},  # B sem registro
    )
    check("7b. mista: A consistent e B no_data",
          status_of(report2, "A")["status"] == "consistent"
          and status_of(report2, "B")["status"] == "no_data")
    # no_data NAO e drift nem not_found.
    st = tenant_consistency_status("x:y", [])
    report3 = tenant_consistency_report([entry("C", "x:y")], {"C": []})
    check("7c. no_data != not_found (presente x ausente do mapeamento)",
          report[0]["status"] == "no_data" and report3[0]["status"] == "not_found"
          and st == "not_found")


# ---------------------------------------------------------------------------
# 8. latest_run_tenants (run mais recente do JSONL)
# ---------------------------------------------------------------------------
def test_latest_run_tenants() -> None:
    print("== [8] latest_run_tenants — run mais recente, agrupado por empresa ==")

    def rec(rid: str, company: str, source: str) -> dict:
        return {"type": "tenant", "run_id": rid, "company": company,
                "source": source, "status": "ok"}

    records = [
        rec("2026-09-11T06:00:00+00:00", "SAP", "successfactors:jobs"),   # run antigo
        rec("2026-09-12T06:00:00+00:00", "SAP", "successfactors:jobs"),   # run novo
        rec("2026-09-12T06:00:00+00:00", "SAP", "bamboohr:sap"),          # 2o source
        rec("2026-09-12T06:00:00+00:00", "Bayer", "eightfold:bayer"),
        rec("2026-09-12T06:00:00+00:00", "Bayer", "eightfold:bayer"),     # duplicada
    ]
    tenants = latest_run_tenants(records)
    check("8a. so o run mais recente entra", tenants == {
        "SAP": ["successfactors:jobs", "bamboohr:sap"],
        "Bayer": ["eightfold:bayer"],
    }, f"{tenants}")
    check("8b. ordenacao de run_id ISO cronologica (11/09 < 12/09)",
          tenants["SAP"] == ["successfactors:jobs", "bamboohr:sap"])
    # Registros malformados / outros tipos nao derrubam nem entram.
    tenants2 = latest_run_tenants([
        {"type": "run", "run_id": "2026-09-12T06:00:00+00:00", "eligible": 1},
        {"type": "tenant", "run_id": "2026-09-12T06:00:00+00:00", "company": "SAP"},
        "lixo",
        None,
        {"type": "tenant", "run_id": "2026-09-12T06:00:00+00:00",
         "company": "ZF", "source": "successfactors:jobs", "status": "ok"},
    ])
    check("8c. malformados/tipos errados ignorados sem derrubar",
          tenants2 == {"ZF": ["successfactors:jobs"]}, f"{tenants2}")
    check("8d. sem registros tenant -> dict vazio",
          latest_run_tenants([]) == {}
          and latest_run_tenants([{"type": "run"}]) == {})
    # Sem run_id nenhum -> sem referencia -> vazio.
    check("8e. sem run_id nos registros -> vazio",
          latest_run_tenants([{"type": "tenant", "company": "SAP",
                               "source": "successfactors:jobs"}]) == {})


# ---------------------------------------------------------------------------
# 9. Integracao: --health expoe a secao registry_consistency
# ---------------------------------------------------------------------------
def test_cli_health_integration() -> None:
    print("== [9] CLI --health: secao registry_consistency ==")
    from internship_finder import cli

    def rec(company: str, source: str, status: str = "ok") -> dict:
        return {"type": "tenant", "run_id": "2026-09-12T06:00:00+00:00",
                "timestamp": "2026-09-12T06:01:00+00:00", "company": company,
                "source": source, "ats": (source.split(":", 1)[0] if source else ""),
                "status": status, "collected": 1 if status == "ok" else 0}

    # Fixture com o REGISTRY REAL (101 empresas): SAP consistent, Bayer multi,
    # Bosch drift (runtime resolveu so workday:zzz, declarado e BoschGroup),
    # Trumpf dynamic (None declarado), Allianz consistent, Adidas no_data.
    lines = [
        json.dumps(rec("SAP", "successfactors:jobs")),
        json.dumps(rec("Allianz", "phenom:nan")),
        json.dumps(rec("Bayer", "eightfold:bayer")),
        json.dumps(rec("Bayer", "moka:bayer/148387")),
        json.dumps(rec("Bayer", "successfactors:jobs")),
        json.dumps(rec("Bosch", "workday:zzz")),
        json.dumps(rec("Trumpf", "workday:trumpf/TRUMPF_Students")),
    ]
    tmp = tempfile.mkdtemp()
    p = Path(tmp) / "m.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["--health", str(p)])
    report = json.loads(buf.getvalue())
    section = report.get("registry_consistency")
    check("9a. exit 0 no modo health", rc == 0, f"rc={rc}")
    check("9b. secao registry_consistency presente no relatorio",
          isinstance(section, list) and len(section) == 101,
          f"n={len(section) if isinstance(section, list) else None}")
    by = {r["company"]: r for r in section}
    check("9c. SAP -> consistent", by["SAP"]["status"] == "consistent")
    check("9d. Bayer -> multi (declarado presente entre extras)",
          by["Bayer"]["status"] == "multi"
          and by["Bayer"]["runtime_tenants"]
          == ["eightfold:bayer", "moka:bayer/148387", "successfactors:jobs"])
    check("9e. Bosch -> drift (registry diz BoschGroup, runtime so workday:zzz)",
          by["Bosch"]["status"] == "drift"
          and by["Bosch"]["registry_tenant"] == "smartrecruiters:BoschGroup"
          and by["Bosch"]["runtime_tenants"] == ["workday:zzz"])
    check("9f. Trumpf (None) -> dynamic, nao drift",
          by["Trumpf"]["status"] == "dynamic" and by["Trumpf"]["registry_tenant"] is None)
    check("9g. Adidas sem registro -> no_data", by["Adidas"]["status"] == "no_data")
    check("9h. secao serializavel (json.dumps ok)",
          json.dumps(section, ensure_ascii=False) != "")


def main() -> int:
    test_explicit_equal()
    print()
    test_explicit_different()
    print()
    test_none_dynamic()
    print()
    test_not_found()
    print()
    test_shared_tenant_identity()
    print()
    test_multi_vs_drift()
    print()
    test_no_data()
    print()
    test_latest_run_tenants()
    print()
    test_cli_health_integration()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())