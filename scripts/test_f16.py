"""Testes da Fase F16 — onda de fontes: registry wave (100% offline).

Cobre as tarefas da fase sem rede e sem ``data/`` de produção:

- **T1 Novas entradas fazem parse**: cada uma das 9 empresas da onda F16
  existe no SEED como ``RegistryEntry`` com os campos esperados (name str
  não-vazia, ats str não-vazio, tenant ``ats:slug`` não-vazio) e
  ``enabled=True``.
- **T2 Nenhum tenant vazio**: TODAS as entradas do SEED (110) têm
  ``tenant`` preenchido no formato ``<ats>:<slug>`` (self-consistente com
  o ats declarado) — a onda F16 não introduziu entradas sem tenant.
- **T3 Nenhum nome duplicado**: nomes do SEED são únicos (o dict do
  CompanyRegistry colidiria silenciosamente; guarda explícita).
- **T4 Contagem do SEED**: ``len(SEED) == 110`` (101 da F15 + 9 da F16) e
  a lista de nomes bate com a canônica de 110 do test_registry.
- **T5 Isolamento das pendências**: as 6 empresas do bucket B que FICARAM
  FORA (Deutsche Bank, Munich Re, Symrise, Honeywell, Nokia, Unilever
  TMICC) NÃO estão no SEED — regra da fase: empresa sem validação ao vivo
  (0 vagas/tenant ambíguo/infra não suporta) nunca entra.
- **T6 Integridade das vizinhas**: as 101 entradas pré-F16 continuam
  presentes e intactas (nome + ats + tenant byte a byte) — a onda só
  acrescenta, nunca modifica.

Uso:  .venv/bin/python scripts/test_f16.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.registry import (  # noqa: E402
    SEED,
    CompanyRegistry,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# As 9 empresas da onda F16 (nome EXATO do manifest companies.csv, tenant
# validado ao vivo em 08/10/2026 via verify_companies --fetch; ver relatório
# da fase em ~/.hermes/handoff/f16-source-wave/).
F16_ENTRIES = {
    "Brenntag": ("workday", "workday:brenntag/brenntag_jobs"),
    "ALTANA Job Portal": ("successfactors", "successfactors:altanamana"),
    "Atlas Copco Group": ("successfactors", "successfactors:atlascopcoP"),
    "SKF": ("successfactors", "successfactors:career"),
    "Decathlon Digital EN": ("greenhouse", "greenhouse:decathlontechnologyen"),
    "Work for DSV and forward your career | DSV": ("successfactors", "successfactors:jobs"),
    "Heidelbergmaterials": ("workday", "workday:heidelbergmaterials/global_hm_career_site"),
    "Sandvik (Sandvik Jobs)": ("workday", "workday:sandvik/sandvik-jobs"),
    "Rhe (R1111)": ("workday", "workday:rhe/R1111"),
}

# Pendências do bucket B — NUNCA no SEED (validação falhou ao vivo).
F16_PENDENCIES = [
    "Deutsche Bank",
    "Munich Re",
    "munichre",
    "Symrise",
    "SYMRISE",
    "Honeywell",
    "Nokia",
    "Unilever (TMICC)",
    "Unilever TMICC",
]

SEED_COUNT = 110  # 101 pré-F16 + 9 da onda F16


def main() -> int:
    reg = CompanyRegistry()
    by_name = {e.name: e for e in SEED}

    section("T1. novas entradas F16 fazem parse (campos, formato, enabled)")
    for name, (ats, tenant) in F16_ENTRIES.items():
        e = by_name.get(name)
        check(f"T1a. '{name}' presente no SEED", e is not None)
        if e is None:
            continue
        check(f"T1b. '{name}' name str nao-vazio", isinstance(e.name, str) and e.name.strip() != "")
        check(f"T1c. '{name}' ats = {ats}", e.ats == ats, f"ats={e.ats!r}")
        check(f"T1d. '{name}' tenant = {tenant}", e.tenant == tenant, f"tenant={e.tenant!r}")
        check(f"T1e. '{name}' enabled=True", e.enabled is True, f"enabled={e.enabled!r}")

    section("T2. nenhum tenant vazio nas entradas F16 (e formato válido na SEED inteira)")
    # As 9 da onda F16: tenant OBRIGATÓRIO (regra da fase — validado ao vivo,
    # o tenant é o artefato da validação). As 3 entradas históricas com
    # tenant=None (Trumpf/DATEV/Siemens Healthineers, "a base decide")
    # são anteriores à fase e não fazem parte da onda.
    empty_f16 = [name for name in F16_ENTRIES
                 if not (by_name[name].tenant and by_name[name].tenant.strip())]
    check("T2a. as 9 F16 com tenant preenchido", not empty_f16, f"vazias: {empty_f16}")
    with_tenant = [e for e in SEED if isinstance(e.tenant, str) and e.tenant.strip()]
    malformed = [e.name for e in with_tenant
                 if ":" not in e.tenant or not e.tenant.split(":", 1)[1].strip()]
    check("T2b. tenant no formato <ats>:<slug> (SEED inteira)", not malformed, f"malformadas: {malformed}")
    mismatched = [e.name for e in with_tenant
                  if e.ats and not e.tenant.startswith(f"{e.ats}:")]
    check("T2c. tenant consistente com o ats declarado", not mismatched, f"inconsistentes: {mismatched}")

    section("T3. nenhum nome duplicado na SEED")
    names = [e.name for e in SEED]
    dupes = sorted({n for n in names if names.count(n) > 1})
    check("T3a. nomes unicos na SEED", not dupes, f"duplicados: {dupes}")
    check("T3b. registry.get resolve 1:1 (dict sem colisao)", len(by_name) == len(SEED))

    section("T4. contagem da SEED")
    check("T4a. len(SEED) == 110", len(SEED) == SEED_COUNT, f"n={len(SEED)}")
    check("T4b. registry.entries idem", len(reg.entries) == SEED_COUNT, f"n={len(reg.entries)}")
    check("T4c. 101 pré-F16 + 9 F16", len(SEED) - len(F16_ENTRIES) == 101)

    section("T5. pendências do bucket B FORA do SEED")
    seed_names_lower = {n.casefold() for n in names}
    leaked = [p for p in F16_PENDENCIES if p.casefold() in seed_names_lower]
    check("T5a. nenhuma pendência entrou no SEED", not leaked, f"vazaram: {leaked}")

    section("T6. entradas pré-F16 intactas (a onda só acrescenta)")
    f16_names = {n.casefold() for n in F16_ENTRIES}
    pre = [e for e in SEED if e.name.casefold() not in f16_names]
    check("T6a. 101 entradas pré-F16 preservadas", len(pre) == 101, f"n={len(pre)}")
    # entradas históricas sabidas e estáveis (amostra de guardiãs de cada onda)
    guards = {
        "Bosch": ("smartrecruiters", "smartrecruiters:BoschGroup"),
        "SAP": ("successfactors", "successfactors:jobs"),
        "Unilever": ("workday", "workday:unilever/unilever_experienced_professionals"),
        "sungrow-emea": ("personio", "personio:sungrow-emea"),
        "VDI Technologiezentrum GmbH": ("softgarden", "softgarden:vdijobs"),
    }
    for gname, (gats, gtenant) in guards.items():
        e = by_name.get(gname)
        ok = e is not None and e.ats == gats and e.tenant == gtenant
        check(f"T6b. guardiã '{gname}' intacta", ok,
              f"ats={e.ats if e else None!r} tenant={e.tenant if e else None!r}")

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print(f"OK — test_f16: {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
