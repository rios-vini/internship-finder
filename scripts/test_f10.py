#!/usr/bin/env python3
"""Testes standalone — F10: curadoria de visto, onda 2 (long tail) + revisão F9.

Cobre, de forma DETERMINÍSTICA e offline (sem rede, sem data/):

1. **Aliases do dataset casam**: para CADA alias novo da F10 (strings
   EXATAS medidas no dataset + aliases canônicos das entries novas),
   ``company_intel_for({{"company": alias}}, map)`` retorna non-None.
2. **Curadoria honesta**: toda entry nova (checked 2026-10-04) tem
   ``country`` = "de", ``sources`` não-vazio com url http(s) e quality
   válida; toda entry com ``visa_policy`` != not_verified tem
   ``sources_for.visa_policy`` não-vazio com CITAÇÃO textual + URL http(s)
   + checked + note (regra do template F9/F10).
3. **REGRESSION GUARD da pendência F9**: a entry Everllence SE NÃO
   contém os aliases "Daimler Truck AG"/"Daimler Truck" (factualmente
   errados) E CONTÊM "MAN Energy Solutions SE" + "MAN Energy Solutions"
   (corretos — ex-MAN Energy Solutions, grupo VW).
4. **Upgrade TE Connectivity (revisão F9, busca fraca)**: única entry
   not_verified da F9 re-pesquisada; agora unclear COM sources_for
   (working student ativo em Adelberg, BW, no portal oficial).
5. **Invariantes**: 0 explicit_support no JSON inteiro; ``country`` em
   100% das entries; estados só de VISA_POLICY_STATES;
   VISA_FRIENDLY_STATES intocado; derivação unclear -> True / must-have
   -> False (celonis é o novo caso must-have medido).
6. **Idempotência**: re-rodar f10_curadoria.py não duplica entries nem
   re-remove aliases (remoção já aplicada permanece estável).
7. **Preservação F5/F7/F9**: 66 -> 88 entries (só adição); counts por
   país não diminuem; nomes históricos presentes.

Padrão dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_f10.py
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
CURADORIA = ROOT / "scripts" / "f10_curadoria.py"
TODAY = "2026-10-04"

FAILS = 0


def check(name: str, ok: bool) -> None:
    global FAILS
    mark = "[OK]" if ok else "[FAIL]"
    if not ok:
        FAILS += 1
    print(f"{mark} {name}")


# Aliases EXATOS medidos no dataset de 2.214 elegíveis que ERAM unmatched
# antes da F10 e precisam casar depois (40 strings, 134 vagas).
DATASET_ALIASES = [
    # entries novas (22)
    "Bauhaus AG",
    "bahagag",
    "Vitesco Technologies GmbH",
    "zeissgroup",
    "Abb",
    "careers.abb",
    "ABB AG",
    "C & A (Canda)",
    "John Deere",
    "Marquardt Group",
    "isaraerospace",
    "Provinzial Versicherung",
    "Nordex Group Career Portal",
    "careers.bcg.com",
    "ebm-papst",
    "FIREVAnDerRWTHAachen",
    "B. Braun Melsungen AG",
    "Voith GmbH",
    "Voith GmbH & Co. KGaA",
    "Voith SE & Co. KG",
    "RWE",
    "ADAC SE",
    "ADAC Autovermietung GmbH",
    "ADAC Medien und Reise GmbH",
    "ADAC Versicherung AG",
    "EY Global Services",
    "EY GmbH & Co. KG WPG",
    "Ferrero International S.A",
    "www.careers.philips.com",
    "celonis",
    "MediaMarktSaturn Retail Group",
    "Media-Saturn Deutschland GmbH",
    # alias merges em entries existentes (8)
    "Knorr-Bremse Systeme für Schienenfahrzeuge GmbH",
    "Liebherr-Werk Ehingen GmbH",
    "Liebherr-Mischtechnik GmbH",
    "Liebherr-Logistics GmbH",
    "Liebherr Electronics and Drives GmbH",
    "Schaeffler Vehicle Lifetime Solutions Germany GmbH & Co. KG",
    "Bayer AG Pharmaceuticals",
    "VOLKSWAGEN GROUP Original Teil e Logistik, Vertrieb & Service s GmbH",
]

# Entries NOVAS esperadas da onda 2 (nome canônico -> país).
NEW_ENTRIES = {
    "ZEISS": "de",
    "ABB": "de",
    "C&A": "de",
    "John Deere": "de",
    "Marquardt Group": "de",
    "ISAR Aerospace": "de",
    "Provinzial Versicherung": "de",
    "Nordex Group": "de",
    "BCG": "de",
    "ebm-papst": "de",
    "FIR e.V. an der RWTH Aachen": "de",
    "Vitesco Technologies GmbH": "de",
    "B. Braun SE": "de",
    "Voith Group": "de",
    "RWE AG": "de",
    "EY (Germany)": "de",
    "Celonis SE": "de",
    "MediaMarktSaturn Retail Group": "de",
    "Philips Germany": "de",
    "Ferrero Germany": "de",
    "ADAC e.V.": "de",
    "BAUHAUS AG": "de",
}


def test_dataset_aliases_match() -> None:
    print("== F10.1: aliases EXATOS do dataset casam (entries novas + merges) ==")
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
    # colisão Philips DE x NL: strings distintas apontam para entries distintas
    de = oi.company_intel_for({"company": "www.careers.philips.com"}, m)
    nl = oi.company_intel_for({"company": "Philips"}, m)
    check("Philips Germany (DE) e Koninklijke Philips (NL) são entries distintas",
          de is not None and nl is not None and de["company"] != nl["company"]
          and de.get("country") == "de" and nl.get("country") == "nl")


def test_new_entries_honest() -> None:
    print("== F10.2: curadoria honesta das entries novas ==")
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


def test_everllence_regression_guard() -> None:
    print("== F10.3: REGRESSION GUARD — pendência F9 Everllence ==")
    m = oi.load_company_intel(CI)
    ev = oi.company_intel_for({"company": "Everllence SE"}, m)
    check("entry Everllence SE presente", ev is not None)
    if ev is None:
        return
    aliases = ev.get("aliases") or []
    check("NÃO contém alias 'Daimler Truck AG' (removido — factualmente errado)",
          "Daimler Truck AG" not in aliases)
    check("NÃO contém alias 'Daimler Truck' (removido — factualmente errado)",
          "Daimler Truck" not in aliases)
    check("contém alias 'MAN Energy Solutions SE' (correto, mantido)",
          "MAN Energy Solutions SE" in aliases)
    check("contém alias 'MAN Energy Solutions' (correto, mantido)",
          "MAN Energy Solutions" in aliases)
    check("estado unclear preservado (a remoção não mexe no visa_policy)",
          ev.get("visa_policy") == "unclear")
    # alias removido não pode casar mais: lookup direto por "Daimler Truck"
    dt = oi.company_intel_for({"company": "Daimler Truck"}, m)
    check("'Daimler Truck' NÃO casa com nenhuma entry (remoção efetiva no mapa)",
          dt is None or dt["company"] != "Everllence SE")


def test_te_upgrade() -> None:
    print("== F10.4: upgrade TE Connectivity (revisão F9, re-busca) ==")
    m = oi.load_company_intel(CI)
    te = oi.company_intel_for({"company": "TE Connectivity"}, m)
    check("entry TE Connectivity presente", te is not None)
    if te is None:
        return
    check("TE: not_verified -> unclear (working student DE documentado)",
          te.get("visa_policy") == "unclear")
    check("TE: checked atualizado hoje", te.get("checked") == TODAY)
    sfp = (te.get("sources_for") or {}).get("visa_policy") or []
    check("TE: sources_for.visa_policy com citação após upgrade",
          len(sfp) > 0 and all(s.get("url", "").startswith("http")
                               and s.get("text") and s.get("note")
                               and s.get("checked") == TODAY for s in sfp))
    check("TE: unclear -> visa_friendly True", oi.visa_friendly(te) is True)


def test_invariants() -> None:
    print("== F10.5: invariantes do arquivo curado ==")
    data = json.loads(CI.read_text(encoding="utf-8"))
    uniq = list({id(v): v for v in oi.load_company_intel(CI).values()}.values())
    check(f"estados todos válidos ({len(uniq)} entries únicas)",
          all(e.get("visa_policy") in oi.VISA_POLICY_STATES for e in uniq))
    check("0 explicit_support no arquivo real (honestidade F5/F7/F9/F10)",
          all(e.get("visa_policy") != "explicit_support" for e in uniq))
    check("country em 100% das entries",
          all(e.get("country") for e in data["companies"]))
    check("VISA_FRIENDLY_STATES intocado",
          oi.VISA_FRIENDLY_STATES == ("explicit_support", "unclear"))
    # derivação viva: celonis must-have -> False (novo caso negativo honesto)
    m = oi.load_company_intel(CI)
    ce = oi.company_intel_for({"company": "celonis"}, m)
    check("celonis: candidate_must_have_authorization (FAQ: no visa sponsorship)",
          ce is not None and ce["visa_policy"] == "candidate_must_have_authorization")
    check("celonis: visa_friendly False (must-have fica FORA)",
          ce is not None and oi.visa_friendly(ce) is False)
    zw = oi.company_intel_for({"company": "zeissgroup"}, m)
    check("zeissgroup: unclear -> visa_friendly True",
          zw is not None and zw["visa_policy"] == "unclear"
          and oi.visa_friendly(zw) is True)


def test_idempotency() -> None:
    print("== F10.6: script idempotente (re-run não duplica nem re-remove) ==")
    with tempfile.TemporaryDirectory() as td:
        repo_copy = Path(td) / "if"
        repo_copy.mkdir()
        (repo_copy / "company_intel").mkdir()
        (repo_copy / "scripts").mkdir()
        ci_dst = repo_copy / "company_intel" / "company_intelligence.json"
        ci_dst.write_text(CI.read_text(encoding="utf-8"), encoding="utf-8")
        cur = Path(td) / "f10_curadoria.py"
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
        check("re-run reporta 0 removidas (remoção já aplicada é estável)",
              "aliases REMOVIDOS (pendência F9): 0" in r2.stdout)
        # conteúdo estável: run 2 não altera nada no arquivo
        before = ci_dst.read_text(encoding="utf-8")
        r3 = subprocess.run([sys.executable, str(cur)], capture_output=True, text=True)
        check("run 3 byte-idêntico (escrita estável)",
              r3.returncode == 0 and ci_dst.read_text(encoding="utf-8") == before)


def test_preservation() -> None:
    print("== F10.7: preservação F5/F7/F9 (só adição; nunca remoção) ==")
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
    check("total entries cresceu (66 -> 88)",
          len(data["companies"]) == 88)
    historic = ["BMW AG", "SAP", "BoschGroup", "Volkswagen AG", "BASF SE",
                "Amazon EU S.à r.l.", "Nokia", "AB InBev", "Solvay", "Bekaert",
                "Lidl", "DHL Group", "REWE Group", "Airbus", "adidas AG",
                "Everllence SE", "TE Connectivity", "Simon-Kucher & Partners"]
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
    test_everllence_regression_guard()
    test_te_upgrade()
    test_invariants()
    test_idempotency()
    test_preservation()
    if FAILS:
        print(f"\nFALHAS: {FAILS}")
        sys.exit(1)
    print("\nTUDO OK")


if __name__ == "__main__":
    main()
