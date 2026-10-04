#!/usr/bin/env python3
"""Testes standalone — F9: curadoria de visto, onda 1 (top empresas por volume).

Cobre, de forma DETERMINÍSTICA e offline (sem rede, sem data/):

1. **Aliases do dataset casam**: para CADA alias EXATO listado do dataset
   (Grupos A + B da onda 1), ``company_intel_for({"company": alias}, map)``
   retorna non-None — o match é EXATO por ``_norm``; sem o alias exato a
   entry nunca casa (regra F9 do orquestrador).
2. **Curadoria honesta**: toda entry nova (checked 2026-10-04) tem
   ``country`` = "de", ``sources`` não-vazio com url http(s) e quality
   válida; toda entry com ``visa_policy`` != not_verified tem
   ``sources_for.visa_policy`` não-vazio com CITAÇÃO textual + URL http(s)
   + checked + note (regra do template F9).
3. **Semântica de estados preservada**: estados só assumem valores de
   ``VISA_POLICY_STATES``; explicit_support continua ausente do arquivo
   real (não existe para estágio DE); VISA_FRIENDLY_STATES intocado;
   derivação unclear -> visa_friendly True / must_have -> False.
4. **Upgrades idempotentes**: Fraunhofer-Gesellschaft re-pesquisada sobe
   not_verified -> unclear COM sources_for (evidência nova); re-rodar o
   script não duplica entries (idempotência por casefold do canônico).
5. **Preservação F5/F7**: as 16 DE históricas continuam presentes; nenhuma
   entry foi REMOVIDA (a F9 só adiciona); counts por país não diminuem.

Padrão dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_f9.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import opportunity_intel as oi  # noqa: E402

CI = ROOT / "company_intel" / "company_intelligence.json"
CURADORIA = ROOT / "scripts" / "f9_curadoria.py"

FAILS = 0


def check(name: str, ok: bool) -> None:
    global FAILS
    mark = "[OK]" if ok else "[FAIL]"
    if not ok:
        FAILS += 1
    print(f"{mark} {name}")


# Aliases EXATOS medidos no dataset de 2.214 elegíveis (Grupos A + B).
# Cada string aqui era UNMATCHED antes da F9 e precisa casar depois.
DATASET_ALIASES = [
    # Grupo A
    "lidlstiftup2",
    "Lidl Dienstleistung GmbH & Co. KG",
    "careers.dhl.com",
    # Grupo B
    "REWE Group",
    "Mercedes-Benz Group AG",
    "Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
    "Airbus Defence and Space GmbH",
    "Fraunhofer-Gesellschaft",
    "Fraunhofer-Gesellschaft e.V. Zentrale München",
    "Vodafone Procurement Company S.a.r.l.",
    "KPMG International Cooperative",
    "Würth Group",
    "Stryker",
    "AGCO",
    "trumpf",
    "aumovio",
    "TikTok",
    "Airbus Operations GmbH Werk Bremen",
    "mllerservi",
    "Vetter Pharma-Fertigung GmbH & Co. KG",
    "MTU Aero Engines AG",
    "MTU Maintenance Hannover GmbH",
    "MAHLE International GmbH",
    "Lufthansa Technik AG",
    "Deutsche Lufthansa AG",
    "Infineon",
    "AIXTRON SE",
    "AUMOVIO SE Haupverwaltung",
    "Rheinmetall AG",
    "adidas",
    "Alfred Kärcher SE & Co. KG",
    "Endress+Hauser InfoServe GmbH+Co. KG",
    "TE Connectivity",
    "PirelliTyres",
    "Bechtle AG",
    "SMA Solar Technology AG",
    "Everllence SE",
    "simon-kucher",
    # irmãs adicionais cobertas pelas mesmas entries (alias merge)
    "REWE Markt GmbH",
    "Deloitte GmbH",
    "Airbus Logistik GmbH",
    "Vodafone GmbH",
    "Würth Industrie Service GmbH & Co. KG",
    "Mercedes-AMG GmbH",
    "MTU Maintenance Berlin-Brandenburg GmbH",
    "Endress + Hauser Wetzer GmbH & Co.KG",
    "Müller Service GmbH",
]

# Entries NOVAS esperadas da onda 1 (nome canônico -> país).
NEW_ENTRIES = {
    "Lidl": "de",
    "DHL Group": "de",
    "REWE Group": "de",
    "Deloitte (Germany)": "de",
    "Airbus": "de",
    "Vodafone": "de",
    "KPMG": "de",
    "Würth Group": "de",
    "Stryker": "de",
    "AGCO": "de",
    "TRUMPF": "de",
    "aumovio": "de",
    "TikTok": "de",
    "Müller Service GmbH": "de",
    "Vetter Pharma-Fertigung GmbH & Co. KG": "de",
    "MTU Aero Engines AG": "de",
    "Lufthansa Group": "de",
    "MAHLE": "de",
    "Infineon Technologies AG": "de",
    "AIXTRON SE": "de",
    "Rheinmetall AG": "de",
    "Kärcher": "de",
    "adidas AG": "de",
    "Endress+Hauser InfoServe GmbH+Co. KG": "de",
    "TE Connectivity": "de",
    "Pirelli Deutschland GmbH": "de",
    "Bechtle AG": "de",
    "SMA Solar Technology AG": "de",
    "Everllence SE": "de",
    "Simon-Kucher & Partners": "de",
}


def test_dataset_aliases_match() -> None:
    print("== F9.1: aliases EXATOS do dataset casam (Grupos A+B) ==")
    m = oi.load_company_intel(CI)
    check("map carregado não-vazio", len(m) > 0)
    for alias in DATASET_ALIASES:
        got = oi.company_intel_for({"company": alias}, m)
        check(f"alias casa: {alias!r} -> {got['company'] if got else None}",
              got is not None)


def test_new_entries_honest() -> None:
    print("== F9.2: curadoria honesta das entries novas ==")
    data = json.loads(CI.read_text(encoding="utf-8"))
    by_name = {e["company"]: e for e in data["companies"]}
    for name, country in NEW_ENTRIES.items():
        e = by_name.get(name)
        check(f"entry nova presente: {name}", e is not None)
        if e is None:
            continue
        check(f"{name}: country == de", e.get("country") == country)
        check(f"{name}: checked hoje (2026-10-04)", e.get("checked") == "2026-10-04")
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
                              and s.get("checked") == "2026-10-04"
                              and s.get("text") and s.get("note")
                              and s.get("quality") in oi.SOURCE_QUALITIES
                              for s in sfp))
            check(f"{name}: sources_for.visa_policy com citação+url+checked+note", ok_sfp)
        else:
            check(f"{name}: not_verified tem visa_policy_note honesta",
                  bool(e.get("visa_policy_note")))


def test_state_semantics() -> None:
    print("== F9.3: semântica de estados preservada ==")
    data = json.loads(CI.read_text(encoding="utf-8"))
    uniq = list({id(v): v for v in oi.load_company_intel(CI).values()}.values())
    check("estados todos válidos",
          all(e.get("visa_policy") in oi.VISA_POLICY_STATES for e in uniq))
    check("0 explicit_support no arquivo real (honestidade F5/F7/F9)",
          all(e.get("visa_policy") != "explicit_support" for e in uniq))
    check("VISA_FRIENDLY_STATES intocado",
          oi.VISA_FRIENDLY_STATES == ("explicit_support", "unclear"))
    # derivação viva: Lufthansa must-have -> False; REWE unclear -> True
    m = oi.load_company_intel(CI)
    lh = oi.company_intel_for({"company": "Lufthansa Technik AG"}, m)
    check("Lufthansa: candidate_must_have_authorization",
          lh is not None and lh["visa_policy"] == "candidate_must_have_authorization")
    check("Lufthansa: visa_friendly False (must-have fica FORA)",
          lh is not None and oi.visa_friendly(lh) is False)
    rw = oi.company_intel_for({"company": "REWE Group"}, m)
    check("REWE: unclear -> visa_friendly True",
          rw is not None and rw["visa_policy"] == "unclear"
          and oi.visa_friendly(rw) is True)
    sk = oi.company_intel_for({"company": "simon-kucher"}, m)
    check("Simon-Kucher: must-have (FAQ exige Aufenthaltserlaubnis) -> False",
          sk is not None and oi.visa_friendly(sk) is False)
    fr = oi.company_intel_for({"company": "Fraunhofer-Gesellschaft e.V. Zentrale München"}, m)
    check("Fraunhofer upgrade: not_verified -> unclear (evidência nova)",
          fr is not None and fr["visa_policy"] == "unclear")
    check("Fraunhofer: sources_for.visa_policy presente após upgrade",
          fr is not None and bool((fr.get("sources_for") or {}).get("visa_policy")))
    mb = oi.company_intel_for({"company": "Mercedes-Benz Group AG"}, m)
    check("Mercedes-Benz Group AG casa na entry existente (alias merge)",
          mb is not None and mb["company"] == "Mercedes-Benz Group")
    check("Mercedes: estado F5/F7 preservado (must-have)",
          mb is not None and mb["visa_policy"] == "candidate_must_have_authorization")


def test_idempotency() -> None:
    print("== F9.4: script idempotente (re-run não duplica) ==")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        repo_copy = Path(td) / "if"
        repo_copy.mkdir()
        (repo_copy / "company_intel").mkdir()
        (repo_copy / "scripts").mkdir()
        ci_dst = repo_copy / "company_intel" / "company_intelligence.json"
        # estado PRÉ-F9: reconstruído removendo as entries novas/upgrades do
        # arquivo atual — mais simples e determinístico: rodar 2x no atual.
        ci_dst.write_text(CI.read_text(encoding="utf-8"), encoding="utf-8")
        cur = Path(td) / "f9_curadoria.py"
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


def test_preservation_f5_f7() -> None:
    print("== F9.5: preservação F5/F7 (só adição; nunca remoção) ==")
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
    check(f"total entries cresceu (F9 deixou 66; agora {len(data['companies'])} >= 66)",
          len(data["companies"]) >= 66)
    # nomes F5/F7 todos ainda presentes
    historic = ["BMW AG", "SAP", "BoschGroup", "Volkswagen AG", "BASF SE",
                "Amazon EU S.à r.l.", "Nokia", "AB InBev", "Solvay", "Bekaert"]
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
    test_state_semantics()
    test_idempotency()
    test_preservation_f5_f7()
    if FAILS:
        print(f"\nFALHAS: {FAILS}")
        sys.exit(1)
    print("\nTUDO OK")


if __name__ == "__main__":
    main()
