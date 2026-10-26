#!/usr/bin/env python3
"""Testes standalone — F129: curadoria de visto, onda 3 (~30 empresas-alvo novas).

Cobre, de forma DETERMINÍSTICA e offline (sem rede, sem data/):

1. **Aliases do dataset casam**: para CADA alias novo da F129 (strings
   EXATAS medidas no dataset + aliases canônicos das entries novas),
   ``company_intel_for({{"company": alias}}, map)`` retorna non-None.
2. **Curadoria honesta**: toda entry nova (checked 2026-10-26) tem
   ``country`` = "de", ``sources`` não-vazio com url http(s) e quality
   válida; toda entry com ``visa_policy`` != not_verified tem
   ``sources_for.visa_policy`` não-vazio com CITAÇÃO textual + URL http(s)
   + checked + note (regra do template F9/F10).
3. **REGRESSÃO MULTINACIONAIS US**: TI/ADI/Copeland — curadoria SÓ do que
   se aplica à operação DE (regra F10: registro IND por país); programas
   US não valem para entry DE.
4. **GIZ**: público federal — regime próprio de estágio (pago, período
   limitado); statement de internacionalidade explícito, ótimo p/
   visa_friendly (unclear com fonte).
5. **NÃO curar marca-filha por string match** (F66 Levio): entries
   separadas por país quando match é por string exata do dataset.
6. **Invariantes**: 0 explicit_support no JSON inteiro; ``country`` em
   100% das entries; estados só de VISA_POLICY_STATES;
   VISA_FRIENDLY_STATES intocado; derivação unclear -> True / must-have
   -> False (E.ON é o novo caso must-have medido).
7. **Idempotência**: re-rodar f129_curadoria.py não duplica entries nem
   re-adiciona aliases.
8. **Preservação F5/F7/F9/F10**: 88 -> 121 entries (só adição); counts
   por país não diminuem; nomes históricos presentes.

Padrão dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_f129_curadoria.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import opportunity_intel as oi  # noqa: E402

CI = ROOT / "company_intel" / "company_intelligence.json"
CURADORIA = ROOT / "scripts" / "f129_curadoria.py"
TODAY = "2026-10-26"

FAILS = 0


def check(name: str, ok: bool) -> None:
    global FAILS
    mark = "[OK]" if ok else "[FAIL]"
    if not ok:
        FAILS += 1
    print(f"{mark} {name}")


# Aliases EXATOS medidos no dataset de elegíveis que ERAM unmatched
# antes da F129 e precisam casar depois.
# Cada string aqui era UNMATCHED antes da F129.
DATASET_ALIASES = [
    # Aldi Süd
    "ALDI SÜD",
    "Aldi Dienstleistung SE & Co. oHG",
    "ALDI Süd Stiftung & Co. KG",
    # Aldi Nord
    "ALDI Nord",
    "Aldi-Nord",
    "ALDI Einkauf GmbH & Co. oHG",
    # E.ON
    "E.ON SE",
    "E.ON Energy",
    "E.ON Deutschland",
    # KUKA
    "KUKA AG",
    "KUKA Deutschland GmbH",
    "KUKA Robotics",
    "KUKA SE & Co. KGaA",
    # Hugo Boss (já tenant F124, mas aliases do dataset)
    "HUGO BOSS AG",
    # Mars Germany
    "Mars GmbH",
    "Mars Petcare Germany",
    "Mars Wrigley Germany",
    # Viega
    "Viega GmbH & Co. KG",
    "Viega Deutschland",
    # Siemens Energy Germany
    "Siemens Energy AG",
    "Siemens Energy Global GmbH & Co. KG",
    # TenneT Germany
    "TenneT TSO GmbH",
    "TenneT Germany",
    # Texas Instruments Germany
    "Texas Instruments Deutschland GmbH",
    "TI Germany",
    "TI Deutschland",
    # Analog Devices Germany
    "Analog Devices GmbH",
    "ADI Germany",
    "Analog Devices Deutschland",
    # Copeland Germany
    "Copeland GmbH",
    "Copeland Climate Technologies Germany",
    # DSV Germany
    "DSV Road GmbH",
    "DSV Air & Sea GmbH",
    "DSV Solutions GmbH",
    # BioNTech
    "BioNTech SE",
    # GIZ
    "Deutsche Gesellschaft für Internationale Zusammenarbeit (GIZ) GmbH",
    "GIZ GmbH",
    # INVERTO
    "Inverto GmbH",
    "Inverto, a BCG company",
    # Beiersdorf
    "Beiersdorf AG",
    "NIVEA Company",
    # Aurubis
    "Aurubis AG",
    "Aurubis Hamburg",
    # Jungheinrich
    "Jungheinrich AG",
    "Jungheinrich Deutschland",
    # Hermes Deutschland
    "Hermes Germany GmbH",
    "Hermes Fulfilment GmbH",
    # Zollner
    "Zollner Elektronik AG",
    "Zollner AG",
    # EJOT
    "EJOT GmbH & Co. KG",
    "EJOT SE & Co. KG",
    # DMK
    "DMK Deutsches Milchkontor GmbH",
    "DMK Group",
    "Milram",
    # Zentis
    "Zentis GmbH & Co. KG",
    "Zentis Fruchtwelt GmbH & Co. KG",
    # Rockwool Germany
    "DEUTSCHE ROCKWOOL GmbH & Co. KG",
    "Rockwool Deutschland",
    # Südpack
    "SÜDPACK Verpackungen SE & Co. KG",
    "Suedpack",
    # tk nucera
    "thyssenkrupp nucera AG & Co. KGaA",
    "thyssenkrupp nucera",
    # Applied Materials Germany
    "Applied Materials GmbH",
    "Applied Materials Dresden",
    # sonnen
    "sonnen GmbH",
    "sonnen Group",
    "sonnen eServices Deutschland GmbH",
    # Süss MicroTec
    "SÜSS MicroTec SE",
    "Suess MicroTec",
    # TRIMET
    "TRIMET Aluminium SE",
    "TRIMET Aluminium",
    # Schunk
    "SCHUNK GmbH & Co. KG",
    "Schunk GmbH",
    # CeramTec
    "CeramTec GmbH",
    "CeramTec Group",
]

# Entries NOVAS esperadas da onda 3 (nome canônico -> país).
NEW_ENTRIES = {
    "Aldi Süd": "de",
    "Aldi Nord": "de",
    "E.ON": "de",
    "KUKA": "de",
    "Hugo Boss": "de",
    "Mars Germany": "de",
    "Viega": "de",
    "Siemens Energy Germany": "de",
    "TenneT Germany": "de",
    "Texas Instruments Germany": "de",
    "Analog Devices Germany": "de",
    "Copeland Germany": "de",
    "DSV Germany": "de",
    "BioNTech": "de",
    "GIZ": "de",
    "INVERTO": "de",
    "Beiersdorf": "de",
    "Aurubis": "de",
    "Jungheinrich": "de",
    "Hermes Deutschland": "de",
    "Zollner": "de",
    "EJOT": "de",
    "DMK": "de",
    "Zentis": "de",
    "Rockwool Germany": "de",
    "Südpack": "de",
    "tk nucera": "de",
    "Applied Materials Germany": "de",
    "sonnen": "de",
    "Süss MicroTec": "de",
    "TRIMET": "de",
    "Schunk": "de",
    "CeramTec": "de",
}


def test_dataset_aliases_match() -> None:
    print("== F129.1: aliases EXATOS do dataset casam (entries novas) ==")
    m = oi.load_company_intel(CI)
    check("map carregado não-vazio", len(m) > 0)
    for alias in DATASET_ALIASES:
        got = oi.company_intel_for({"company": alias}, m)
        check(f"alias casa: {alias!r} -> {got['company'] if got else None}",
              got is not None)
    # aliases canônicos das entries novas também casam (map por nome)
    for name in NEW_ENTRIES:
        got = oi.company_intel_for({"company": name}, m)
        check(f"canônico casa: {name!r}", got is not None)
    # REGRESSÃO: multinacionais US — entries DE separadas da entry global
    # (se existirem entries globais no arquivo)
    # TI: entry DE existe, entry US não está no arquivo (ok)
    # ADI: entry DE existe, entry US não está no arquivo (ok)
    # Copeland: entry DE existe, entry US não está no arquivo (ok)
    # Verificar que NÃO há colisão com entry global genérica "Mars"
    de_mars = oi.company_intel_for({"company": "Mars Germany"}, m)
    check("Mars Germany entry DE existe (separada de Mars global)",
          de_mars is not None and de_mars["company"] == "Mars Germany")
    # Verificar que NÃO há colisão com entry global genérica "Texas Instruments"
    de_ti = oi.company_intel_for({"company": "Texas Instruments Germany"}, m)
    check("Texas Instruments Germany entry DE existe (separada)",
          de_ti is not None and de_ti["company"] == "Texas Instruments Germany")
    # Verificar que NÃO há colisão com entry global genérica "Analog Devices"
    de_adi = oi.company_intel_for({"company": "Analog Devices Germany"}, m)
    check("Analog Devices Germany entry DE existe (separada)",
          de_adi is not None and de_adi["company"] == "Analog Devices Germany")
    # Verificar que NÃO há colisão com entry global genérica "Copeland"
    de_cop = oi.company_intel_for({"company": "Copeland Germany"}, m)
    check("Copeland Germany entry DE existe (separada)",
          de_cop is not None and de_cop["company"] == "Copeland Germany")
    # Verificar que NÃO há colisão com entry global genérica "DSV"
    de_dsv = oi.company_intel_for({"company": "DSV Germany"}, m)
    check("DSV Germany entry DE existe (separada)",
          de_dsv is not None and de_dsv["company"] == "DSV Germany")
    # Verificar Siemens Energy Germany separada de Siemens AG
    de_se = oi.company_intel_for({"company": "Siemens Energy Germany"}, m)
    siemens_ag = oi.company_intel_for({"company": "Siemens AG"}, m)
    check("Siemens Energy Germany entry DE existe (separada de Siemens AG)",
          de_se is not None and siemens_ag is not None
          and de_se["company"] != siemens_ag["company"])


def test_new_entries_honest() -> None:
    print("== F129.2: curadoria honesta das entries novas ==")
    data = json.loads(CI.read_text(encoding="utf-8"))
    by_name = {e["company"]: e for e in data["companies"]}
    for name, country in NEW_ENTRIES.items():
        e = by_name.get(name)
        check(f"entry nova presente: {name}", e is not None)
        if e is None:
            continue
        check(f"{name}: country == de", e.get("country") == country)
        check(f"{name}: checked hoje ({TODAY})", e.get("checked") == TODAY)
        srcs = e.get("sources") or []
        ok_src = (isinstance(srcs, list) and len(srcs) > 0
                  and all(isinstance(s, dict) and s.get("url", "").startswith("http")
                          and s.get("quality") in oi.SOURCE_QUALITIES
                          and s.get("checked") for s in srcs))
        check(f"{name}: sources não-vazio c/ url http + quality válida", ok_src)
        vp = e.get("visa_policy")
        check(f"{name}: visa_policy válido", vp in oi.VISA_POLICY_STATES)
        if vp != "not_verified":
            sfp = (e.get("sources_for") or {}).get("visa_policy") or []
            ok_sfp = (len(sfp) > 0
                      and all(s.get("url", "").startswith("http")
                              and s.get("checked") == TODAY
                              and s.get("text") and s.get("note")
                              and s.get("quality") in oi.SOURCE_QUALITIES
                              for s in sfp))
            check(f"{name}: sources_for.visa_policy com citação+url+checked+note", ok_sfp)
        else:
            check(f"{name}: not_verified tem visa_policy_note honesta",
                  bool(e.get("visa_policy_note")))


def test_giz_federal_pathway() -> None:
    print("== F129.3: GIZ — pathway federal explícito ==")
    m = oi.load_company_intel(CI)
    giz = oi.company_intel_for({"company": "GIZ"}, m)
    check("entry GIZ presente", giz is not None)
    if giz is None:
        return
    check("GIZ: unclear (programa federal citado)", giz.get("visa_policy") == "unclear")
    check("GIZ: checked hoje", giz.get("checked") == TODAY)
    sfp = (giz.get("sources_for") or {}).get("visa_policy") or []
    check("GIZ: sources_for.visa_policy com citação federal",
          len(sfp) > 0 and all("statutory health insurance" in s.get("text", "")
                               or "Berlin, Bonn or Eschborn" in s.get("text", "")
                               for s in sfp))
    check("GIZ: unclear -> visa_friendly True", oi.visa_friendly(giz) is True)


def test_eon_must_have() -> None:
    print("== F129.4: E.ON — candidate_must_have_authorization ==")
    m = oi.load_company_intel(CI)
    eon = oi.company_intel_for({"company": "E.ON"}, m)
    check("entry E.ON presente", eon is not None)
    if eon is None:
        return
    check("E.ON: candidate_must_have_authorization",
          eon.get("visa_policy") == "candidate_must_have_authorization")
    check("E.ON: checked hoje", eon.get("checked") == TODAY)
    sfp = (eon.get("sources_for") or {}).get("visa_policy") or []
    check("E.ON: sources_for.visa_policy com citação de Aufenthaltstitel",
          len(sfp) > 0 and any("Aufenthaltstitel" in s.get("text", "")
                               or "residence permit" in s.get("text", "")
                               for s in sfp))
    check("E.ON: must-have -> visa_friendly False", oi.visa_friendly(eon) is False)


def test_multinational_us_entries_separate() -> None:
    print("== F129.5: REGRESSÃO — multinacionais US têm entries DE separadas ==")
    m = oi.load_company_intel(CI)
    # Texas Instruments
    de_ti = oi.company_intel_for({"company": "Texas Instruments Germany"}, m)
    check("Texas Instruments Germany: entry DE existe",
          de_ti is not None and de_ti.get("country") == "de")
    check("Texas Instruments Germany: visa_policy not_verified (US não vale)",
          de_ti is not None and de_ti.get("visa_policy") == "not_verified")
    check("Texas Instruments Germany: nota menciona regra F10",
          de_ti is not None and "regra F10" in (de_ti.get("visa_policy_note") or ""))
    # Analog Devices
    de_adi = oi.company_intel_for({"company": "Analog Devices Germany"}, m)
    check("Analog Devices Germany: entry DE existe",
          de_adi is not None and de_adi.get("country") == "de")
    check("Analog Devices Germany: visa_policy not_verified (US não vale)",
          de_adi is not None and de_adi.get("visa_policy") == "not_verified")
    check("Analog Devices Germany: nota menciona regra F10",
          de_adi is not None and "regra F10" in (de_adi.get("visa_policy_note") or ""))
    # Copeland
    de_cop = oi.company_intel_for({"company": "Copeland Germany"}, m)
    check("Copeland Germany: entry DE existe",
          de_cop is not None and de_cop.get("country") == "de")
    check("Copeland Germany: visa_policy not_verified (US não vale)",
          de_cop is not None and de_cop.get("visa_policy") == "not_verified")
    check("Copeland Germany: nota menciona regra F10",
          de_cop is not None and "regra F10" in (de_cop.get("visa_policy_note") or ""))
    # DSV
    de_dsv = oi.company_intel_for({"company": "DSV Germany"}, m)
    check("DSV Germany: entry DE existe",
          de_dsv is not None and de_dsv.get("country") == "de")
    check("DSV Germany: visa_policy not_verified",
          de_dsv is not None and de_dsv.get("visa_policy") == "not_verified")


def test_invariants() -> None:
    print("== F129.6: invariantes do arquivo curado ==")
    data = json.loads(CI.read_text(encoding="utf-8"))
    uniq = list({id(v): v for v in oi.load_company_intel(CI).values()}.values())
    check(f"estados todos válidos ({len(uniq)} entries únicas)",
          all(e.get("visa_policy") in oi.VISA_POLICY_STATES for e in uniq))
    check("0 explicit_support no arquivo real (honestidade F5/F7/F9/F10/F129)",
          all(e.get("visa_policy") != "explicit_support" for e in uniq))
    check("country em 100% das entries",
          all(e.get("country") for e in data["companies"]))
    check("VISA_FRIENDLY_STATES intocado",
          oi.VISA_FRIENDLY_STATES == ("explicit_support", "unclear"))
    # derivação viva: E.ON must-have -> False (novo caso negativo honesto)
    m = oi.load_company_intel(CI)
    eon = oi.company_intel_for({"company": "E.ON"}, m)
    check("E.ON: candidate_must_have_authorization -> visa_friendly False",
          eon is not None and eon["visa_policy"] == "candidate_must_have_authorization"
          and oi.visa_friendly(eon) is False)
    # GIZ unclear -> True
    giz = oi.company_intel_for({"company": "GIZ"}, m)
    check("GIZ: unclear -> visa_friendly True",
          giz is not None and giz["visa_policy"] == "unclear"
          and oi.visa_friendly(giz) is True)
    # KUKA unclear -> True
    kuka = oi.company_intel_for({"company": "KUKA"}, m)
    check("KUKA: unclear -> visa_friendly True",
          kuka is not None and kuka["visa_policy"] == "unclear"
          and oi.visa_friendly(kuka) is True)


def test_idempotency() -> None:
    print("== F129.7: script idempotente (re-run não duplica) ==")
    with tempfile.TemporaryDirectory() as td:
        repo_copy = Path(td) / "if"
        repo_copy.mkdir()
        (repo_copy / "company_intel").mkdir()
        (repo_copy / "scripts").mkdir()
        ci_dst = repo_copy / "company_intel" / "company_intelligence.json"
        ci_dst.write_text(CI.read_text(encoding="utf-8"), encoding="utf-8")
        cur = Path(td) / "f129_curadoria.py"
        cur.write_text(CURADORIA.read_text(encoding="utf-8"), encoding="utf-8")
        script = cur.read_text(encoding="utf-8").replace(
            'Path(__file__).resolve().parent.parent / "company_intel" / "company_intelligence.json"',
            f"Path({str(ci_dst)!r})")
        cur.write_text(script, encoding="utf-8")
        r1 = subprocess.run([sys.executable, str(cur)], capture_output=True, text=True)
        check("run 1 exit 0", r1.returncode == 0)
        n1 = len(json.loads(ci_dst.read_text(encoding="utf-8"))["companies"])
        r2 = subprocess.run([sys.executable, str(cur)], capture_output=True, text=True)
        check("run 2 exit 0", r2.returncode == 0)
        n2 = len(json.loads(ci_dst.read_text(encoding="utf-8"))["companies"])
        check(f"re-run não duplica entries ({n1} == {n2})", n1 == n2)
        check("re-run reporta 0 adicionadas", "entries adicionadas: 0" in r2.stdout)
        # conteúdo estável: run 2 não altera nada no arquivo
        before = ci_dst.read_text(encoding="utf-8")
        r3 = subprocess.run([sys.executable, str(cur)], capture_output=True, text=True)
        check("run 3 byte-idêntico (escrita estável)",
              r3.returncode == 0 and ci_dst.read_text(encoding="utf-8") == before)


def test_preservation() -> None:
    print("== F129.8: preservação F5/F7/F9/F10 (só adição; nunca remoção) ==")
    data = json.loads(CI.read_text(encoding="utf-8"))
    by_country: dict[str, int] = {}
    uniq = list({id(v): v for v in oi.load_company_intel(CI).values()}.values())
    for e in uniq:
        by_country[e["country"]] = by_country.get(e["country"], 0) + 1
    check(f"16 DE históricas preservadas (agora {by_country.get('de', 0)} >= 16)",
          by_country.get("de", 0) >= 16)
    for iso, before in (("lu", 5), ("nl", 5), ("fi", 3), ("be", 7)):
        check(f"{iso.upper()} não diminuiu (antes {before}, agora {by_country.get(iso, 0)})",
              by_country.get(iso, 0) >= before)
    check("total entries cresceu (88 -> 121)",
          len(data["companies"]) == 121)
    historic = ["BMW AG", "SAP", "BoschGroup", "Volkswagen AG", "BASF SE",
                "Amazon EU S.à r.l.", "Nokia", "AB InBev", "Solvay", "Bekaert",
                "Lidl", "DHL Group", "REWE Group", "Airbus", "adidas AG",
                "Everllence SE", "TE Connectivity", "Simon-Kucher & Partners",
                "ZEISS", "ABB", "C&A", "John Deere", "Celonis SE",
                "MediaMarktSaturn Retail Group", "Philips Germany", "Ferrero Germany",
                "ADAC e.V.", "BAUHAUS AG", "MAHLE"]
    names = {e["company"] for e in data["companies"]}
    for h in historic:
        check(f"entry histórica preservada: {h}", h in names)


def main() -> None:
    if not CI.exists():
        check("arquivo curado presente", False)
        print(f"\nFALHAS: {FAILS}")
        sys.exit(1)
    test_dataset_aliases_match()
    test_new_entries_honest()
    test_giz_federal_pathway()
    test_eon_must_have()
    test_multinational_us_entries_separate()
    test_invariants()
    test_idempotency()
    test_preservation()
    if FAILS:
        print(f"\nFALHAS: {FAILS}")
        sys.exit(1)
    print("\nTUDO OK")


if __name__ == "__main__":
    main()