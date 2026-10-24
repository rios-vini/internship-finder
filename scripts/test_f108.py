#!/usr/bin/env python3
"""Testes da Fase F108 — CSOD redirect (Luxair/Henkel) + Fricke site-morto +
heurística EURES→Workday (offline, fixtures VERBATIM do registro 23/10).

O DELTA (registro 23/10 tarde, medidas ao vivo):

1. **CSOD: padrão geral /home/requisition/<ID> vs /job/<ID> (ADFS login wall)**
   — URLs `/job/<ID>` da Luxair/Henkel no CSOD redirecionam para ADFS/SAML
   (login wall); formato VIVO é `/home/requisition/<ID>?c=<tenant>&lang=...`
   (Luxair req5377 ALIVE medido 23/10; vale p/ henkel ×4 — reforça SAML case
   F94). Portal luxair.lu/en/careers = 404 → sempre link CSOD direto.
   Regra geral documentada: portais CSOD linkam por requisition, NUNCA por
   /job/. Guard executável em `discovery_rules.TENANT_JOB_URL_FORMATS`
   (camada F105): `luxair` e `henkel` com `current` (vivo) e `legacy` (morto
   404/ADFS) + `job_url_format_status()`.

2. **Wilhelm Fricke (13461829 absolventa): site oficial CERT EXPIRADO (morto)**
   — canal vivo é absolventa. Doutrina F96: link direto do MANUAL-CHECK
   aponta pro canal VIVO (absolventa), não pro site oficial morto.
   Metadata em `manual_check.TENANT_PORTAL_METADATA["fricke"]`:
   `site_morto` + `canal_vivo` + `note`.

3. **Heurística EURES→ATS (Workday) documentada** — TTI JR4997 rastreada
   do EURES (guid base64 opaco) ao Workday oficial. Heurística "título +
   cidade" medida funcionando. Não-escopo: rastreamento automático (é
   heurística humana documentada primeiro).

SUITE OFFLINE por contrato (o registro JÁ mediu 23/10 — nada é
re-sondado): zero rede, fixtures verbatim congeladas, tempdir para
data/. Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo
passar.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import manual_check as mc  # noqa: E402
from internship_finder import discovery_rules as dr  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def check(name: str, cond, detail: str | None = None) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"[OK] {name}" + (f" — {detail}" if detail else ""))
    else:
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (registro 23/10, congeladas)
# ---------------------------------------------------------------------------

# Luxair CSOD: URLs VIVAS medidas (formato /home/requisition/<ID>?c=luxair)
LUXAIR_CURRENT_URLS = [
    "https://luxair.csod.com/ux/ats/careersite/1/home?c=luxair&lang=en&requisitionId=5377",
    "https://luxair.csod.com/ux/ats/careersite/1/home?c=luxair&lang=en&requisitionId=5376",
]

# Luxair CSOD: formato LEGADO do registro (/job/<ID>) — redireciona p/ ADFS
LUXAIR_LEGACY_URLS = [
    "https://luxair.csod.com/ux/ats/careersite/1/job/5377",
    "https://luxair.csod.com/ux/ats/careersite/1/job/5376",
]

# Henkel CSOD: mesmo padrão (×4 no registro F96/SAML case F94)
HENKEL_CURRENT_URL = (
    "https://henkel.csod.com/ux/ats/careersite/1/home?c=henkel&lang=en&requisitionId=12345"
)
HENKEL_LEGACY_URL = (
    "https://henkel.csod.com/ux/ats/careersite/1/job/12345"
)

# Fricke: absolventa listing ATIVO (canal vivo), site oficial morto
FRICKE_ABSOLVENTA_URL = "https://www.absolventa.de/stellenangebote/13461829"


# ---------------------------------------------------------------------------
# G1 — CSOD Luxair: formato vivo x legado morto (guard, nunca segue)
# ---------------------------------------------------------------------------

def test_luxair_csod() -> None:
    section("G1 — Luxair CSOD: /home/requisition vivo; /job ADFS login wall")
    check("camada por tenant existe (TENANT_JOB_URL_FORMATS['luxair'])",
          "luxair" in dr.TENANT_JOB_URL_FORMATS)
    fmt = dr.TENANT_JOB_URL_FORMATS["luxair"]
    check("regra-mãe é cornerstone (CSOD)",
          fmt.ats == "cornerstone" and dr.rule_for("cornerstone") is not None)
    check("evidência é medição datada (registro 23/10), não opinião",
          "23/10" in fmt.evidence and "ADFS" in fmt.evidence)
    for u in LUXAIR_CURRENT_URLS:
        check(f"current (medido): …{u[-50:]}",
              dr.job_url_format_status(u) == "current")
    for u in LUXAIR_LEGACY_URLS:
        check(f"legacy (/job/<ID>) => legacy_dead (MORTO/ADFS)",
              dr.job_url_format_status(u) == "legacy_dead")
    check("legacy com barra final também é morto",
          dr.job_url_format_status(LUXAIR_LEGACY_URLS[0] + "/") == "legacy_dead")
    check("guard 'não seguido': NÃO existe reescrita legado->novo "
          "(resolve_direct_link deixa a URL intocada)",
          mc.resolve_direct_link(LUXAIR_LEGACY_URLS[0]) == LUXAIR_LEGACY_URLS[0])
    check("outro shape do MESMO host => None (silêncio honesto)",
          dr.job_url_format_status(
              "https://luxair.csod.com/ux/ats/careersite/1/home?c=luxair"
          ) is None)
    check("tenant sem medição (outro CSOD) => None",
          dr.job_url_format_status(
              "https://acme.csod.com/ux/ats/careersite/1/home?c=acme"
          ) is None)
    check("vazio => None", dr.job_url_format_status("") is None)


# ---------------------------------------------------------------------------
# G2 — CSOD Henkel: mesmo padrão (reforça SAML case F94)
# ---------------------------------------------------------------------------

def test_henkel_csod() -> None:
    section("G2 — Henkel CSOD: mesmo padrão c=henkel (×4 F96/F94)")
    check("camada por tenant existe (TENANT_JOB_URL_FORMATS['henkel'])",
          "henkel" in dr.TENANT_JOB_URL_FORMATS)
    fmt = dr.TENANT_JOB_URL_FORMATS["henkel"]
    check("regra-mãe é cornerstone (CSOD)",
          fmt.ats == "cornerstone")
    check("evidência cita SAML case F94 e ×4",
          "F94" in fmt.evidence and "×4" in fmt.evidence)
    check("current (c=henkel) => current",
          dr.job_url_format_status(HENKEL_CURRENT_URL) == "current")
    check("legacy (/job/<ID>) => legacy_dead (ADFS/SAML)",
          dr.job_url_format_status(HENKEL_LEGACY_URL) == "legacy_dead")
    check("padrão geral documentado: portais CSOD linkam por requisition",
          "requisition" in fmt.evidence.casefold())


# ---------------------------------------------------------------------------
# G3 — Fricke: site morto → canal absolventa (doutrina F96)
# ---------------------------------------------------------------------------

def test_fricke_site_morto() -> None:
    section("G3 — Fricke: site oficial morto (cert expirado) → canal absolventa")
    check("metadata fricke existe em TENANT_PORTAL_METADATA",
          "fricke" in mc.TENANT_PORTAL_METADATA)
    meta = mc.TENANT_PORTAL_METADATA["fricke"]
    check("site_morto: cert expirado 23/10 + fora do ar",
          "cert expirado" in meta["site_morto"].lower()
          and "23/10" in meta["site_morto"]
          and "fora do ar" in meta["site_morto"].lower())
    check("canal_vivo: absolventa listing 13461829 ATIVO",
          "absolventa" in meta["canal_vivo"].lower()
          and "13461829" in meta["canal_vivo"]
          and "ativo" in meta["canal_vivo"].lower())
    check("note: doutrina F96 (link direto = canal vivo)",
          "F96" in meta["note"] and "canal vivo" in meta["note"].lower())


# ---------------------------------------------------------------------------
# G4 — EURES→ATS: doc f76_1 tem a receita (TTI JR4997 exemplo medido)
# ---------------------------------------------------------------------------

def test_eures_ats_doc() -> None:
    section("G4 — Doc f76_1: heurística EURES→Workday (TTI JR4997)")
    doc_path = ROOT / "docs" / "f76_1_discovery_rules.md"
    text = doc_path.read_text(encoding="utf-8")
    check("seção 6.4 CSOD padrão geral presente",
          "6.4 CSOD" in text and "/home/requisition" in text
          and "ADFS" in text and "luxair" in text.casefold())
    check("seção 6.5 Fricke site morto presente",
          "6.5 Wilhelm Fricke" in text
          and "expirado" in text.casefold()
          and "absolventa" in text.casefold())
    check("seção 6.6 EURES→ATS heurística presente",
          "6.6 Heurística EURES" in text
          and "TTI" in text
          and "JR4997" in text
          and "título + cidade" in text)
    check("fixtures verbatim TTI citadas",
          "guid base64" in text.casefold()
          and "tti.wd5.myworkdayjobs.com" in text)
    check("não-escopo declarado: rastreamento automático NÃO implementado",
          "não-escopo" in text.casefold() or "não escopo" in text.casefold()
          or "fora de escopo" in text.casefold())


# ---------------------------------------------------------------------------
# G5 — Contratos: zero rede no discovery_rules + manual_check + membership
# ---------------------------------------------------------------------------

def test_contracts() -> None:
    section("G5 — Contratos: módulos offline + membership CI")
    import inspect
    import ci_discover_tests  # noqa: F401  (scripts/ no sys.path)

    dr_src = Path(dr.__file__).read_text(encoding="utf-8")
    mc_src = Path(mc.__file__).read_text(encoding="utf-8")

    bad_imports = [t for t in ("import urllib.request", "import requests",
                               "import httpx", "urlopen") if t in dr_src]
    check("discovery_rules SEM rede própria (contrato E1 test_f76_1 preservado)",
          not bad_imports, f"bad={bad_imports}")

    bad_mc = [t for t in ("import urllib.request", "import requests",
                          "import httpx", "urlopen") if t in mc_src]
    check("manual_check SEM rede própria (puro, tempdir nos testes)",
          not bad_mc, f"bad={bad_mc}")

    names = ci_discover_tests.discover_tests()
    check("membership: test_f108 na suíte descoberta do CI (F78)",
          "test_f108" in names, f"{len(names)} suítes")

    readme = ROOT / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    import re
    m = re.search(r"\*\*(\d+)\*\* \| CI test suites", readme_text)
    n_readme = int(m.group(1)) if m else -1
    check("README: contador 'N CI test suites' == suite descoberta (F73)",
          n_readme == len(names), f"readme={n_readme} discovery={len(names)}")


def main() -> int:
    test_luxair_csod()
    test_henkel_csod()
    test_fricke_site_morto()
    test_eures_ats_doc()
    test_contracts()
    print(f"\n==== test_f108: {CHECKS} checks, {len(FAILURES)} falha(s) ====")
    if FAILURES:
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())