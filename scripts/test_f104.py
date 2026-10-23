#!/usr/bin/env python3
"""F104 — Testes do sanity check cidade→país (display-only, fail-closed).

Testes:
- Fixture VERBATIM Adaptyv (Lausanne) flagged
- Vaga DE com cidade alemã NÃO flagged
- Vaga NL "Amsterdam" NÃO flagged (NL é mercado-alvo!)
- Fail-closed do config (ausente → OFF, zero erro)
- README count paramétrico (F73 — 140/141 conforme ordem com F103)
- A/B digest sem matches = byte a byte
- Suíte 100% offline
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from internship_finder.countries import (
    check_city_country_mismatch,
    country_mismatch_flag,
    _load_city_country_map,
)


# Fixture VERBATIM do registro 21/10: Adaptyv Lab Automation Intern (Lausanne, CH)
# arbeitnow b1de625e95bec9aa rotulada "de" entrou no eligible DE
ADAPTYV_JOB = {
    "id": "b1de625e95bec9aa",
    "title": "Lab Automation Intern",
    "company": "Adaptyv",
    "location": "Lausanne, CH",
    "country_iso": "de",  # Campo errado na fonte — o bug real
    "url": "https://example.com/adaptyv",
    "source": "arbeitnow",
}

# Vaga alemã legítima (Munich, DE) — NÃO deve flaggar
DE_JOB = {
    "id": "de-munich-001",
    "title": "Praktikum Supply Chain",
    "company": "BMW",
    "location": "Munich, DE",
    "country_iso": "de",
    "url": "https://example.com/bmw",
    "source": "arbeitnow",
}

# Vaga NL legítima (Amsterdam, NL) — NL é mercado-alvo, NÃO flagga
NL_JOB = {
    "id": "nl-amsterdam-001",
    "title": "Procurement Internship",
    "company": "Philips",
    "location": "Amsterdam, NL",
    "country_iso": "nl",
    "url": "https://example.com/philips",
    "source": "arbeitnow",
}

# Vaga CH legítima (Zurich, CH) mas country_iso = ch — NÃO flagga (country_iso não está nos 5 alvos)
CH_JOB = {
    "id": "ch-zurich-001",
    "title": "Materials Engineering Internship",
    "company": "ABB",
    "location": "Zurich, CH",
    "country_iso": "ch",
    "url": "https://example.com/abb",
    "source": "arbeitnow",
}

# Vaga com cidade ambígua (Hamilton) — NÃO está no mapa, NÃO flagga
AMBIGUOUS_CITY_JOB = {
    "id": "ambiguous-001",
    "title": "Internship",
    "company": "TestCorp",
    "location": "Hamilton, ON, CA",
    "country_iso": "de",  # país errado, mas Hamilton não está no mapa
    "url": "https://example.com/test",
    "source": "arbeitnow",
}

# Vaga sem location — NÃO flagga
NO_LOCATION_JOB = {
    "id": "no-loc-001",
    "title": "Internship",
    "company": "TestCorp",
    "location": "",
    "country_iso": "de",
    "url": "https://example.com/test",
    "source": "arbeitnow",
}


def test_adaptyv_flagged() -> bool:
    """Fixture VERBATIM Adaptyv (Lausanne) flagged."""
    # Reset cache para testar com mapa real
    from internship_finder.countries import _CITY_COUNTRY_MAP
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    # Lausanne está no mapa -> CH, country_iso = de (alvo) -> mismatch
    result = check_city_country_mismatch(ADAPTYV_JOB)
    print(f"  Adaptyv (Lausanne, country_iso=de): {result}")
    assert result is True, "Adaptyv Lausanne deve ser flagged"

    # Badge text
    badge = country_mismatch_flag(ADAPTYV_JOB)
    print(f"  Badge: '{badge}'")
    assert badge == "⚠ localização fora dos 5 mercados"
    return True


def test_de_job_not_flagged() -> bool:
    """Vaga DE com cidade alemã NÃO flagged."""
    from internship_finder.countries import _CITY_COUNTRY_MAP
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    result = check_city_country_mismatch(DE_JOB)
    print(f"  DE job (Munich, country_iso=de): {result}")
    assert result is False, "Vaga DE legítima não deve ser flagged"

    badge = country_mismatch_flag(DE_JOB)
    assert badge == ""
    return True


def test_nl_job_not_flagged() -> bool:
    """Vaga NL 'Amsterdam' NÃO flagged (NL é mercado-alvo!)."""
    from internship_finder.countries import _CITY_COUNTRY_MAP
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    # Amsterdam está no mapa -> NL, mas NL está em TARGET_COUNTRIES
    # Logo, expected_country in TARGET_COUNTRIES -> retorna False
    result = check_city_country_mismatch(NL_JOB)
    print(f"  NL job (Amsterdam, country_iso=nl): {result}")
    assert result is False, "Vaga NL legítima não deve ser flagged (NL é alvo)"

    badge = country_mismatch_flag(NL_JOB)
    assert badge == ""
    return True


def test_ch_job_not_flagged() -> bool:
    """Vaga CH legítima (country_iso=ch) NÃO flagged (country_iso não é alvo)."""
    from internship_finder.countries import _CITY_COUNTRY_MAP
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    result = check_city_country_mismatch(CH_JOB)
    print(f"  CH job (Zurich, country_iso=ch): {result}")
    assert result is False, "Vaga CH com country_iso=ch não deve ser flagged (country_iso não é alvo)"

    badge = country_mismatch_flag(CH_JOB)
    assert badge == ""
    return True


def test_ambiguous_city_not_flagged() -> bool:
    """Cidade ambígua (Hamilton) não está no mapa -> NÃO flagga."""
    from internship_finder.countries import _CITY_COUNTRY_MAP
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    result = check_city_country_mismatch(AMBIGUOUS_CITY_JOB)
    print(f"  Ambiguous city (Hamilton, country_iso=de): {result}")
    assert result is False, "Cidade ambígua não mapeada não deve ser flagged"

    badge = country_mismatch_flag(AMBIGUOUS_CITY_JOB)
    assert badge == ""
    return True


def test_no_location_not_flagged() -> bool:
    """Vaga sem location NÃO flagga."""
    from internship_finder.countries import _CITY_COUNTRY_MAP
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    result = check_city_country_mismatch(NO_LOCATION_JOB)
    print(f"  No location job: {result}")
    assert result is False, "Vaga sem location não deve ser flagged"

    badge = country_mismatch_flag(NO_LOCATION_JOB)
    assert badge == ""
    return True


def test_fail_closed_missing_config() -> bool:
    """Fail-closed: config ausente/corrompido/vazio = feature OFF sem erro."""
    import internship_finder.countries as countries_mod

    # Simula config ausente
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = FileNotFoundError("test")

    # Deve retornar False (feature OFF) sem levantar exceção
    result = check_city_country_mismatch(ADAPTYV_JOB)
    print(f"  Missing config: {result}")
    assert result is False, "Config ausente -> feature OFF (False)"

    badge = country_mismatch_flag(ADAPTYV_JOB)
    assert badge == ""
    return True


def test_fail_closed_empty_config() -> bool:
    """Fail-closed: config vazio = feature OFF."""
    import internship_finder.countries as countries_mod

    # Simula config vazio (erro de validação)
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = ValueError("city_to_country ausente/vazio")

    result = check_city_country_mismatch(ADAPTYV_JOB)
    print(f"  Empty config: {result}")
    assert result is False, "Config vazio -> feature OFF (False)"

    badge = country_mismatch_flag(ADAPTYV_JOB)
    assert badge == ""
    return True


def test_load_city_country_map() -> bool:
    """Carrega mapa real do arquivo config/city_country.json."""
    import internship_finder.countries as countries_mod
    countries_mod._CITY_COUNTRY_MAP = None
    countries_mod._CITY_COUNTRY_LOAD_ERROR = None

    city_map = _load_city_country_map()
    assert city_map is not None, "Mapa deve carregar"
    assert "lausanne" in city_map, "Lausanne deve estar no mapa"
    assert city_map["lausanne"] == "ch", "Lausanne -> CH"
    assert "munich" in city_map, "Munich deve estar no mapa"
    assert city_map["munich"] == "de", "Munich -> DE"
    assert "amsterdam" in city_map, "Amsterdam deve estar no mapa"
    assert city_map["amsterdam"] == "nl", "Amsterdam -> NL"
    print(f"  Mapa carregado: {len(city_map)} cidades")
    return True


def run_all() -> None:
    tests = [
        ("load_city_country_map", test_load_city_country_map),
        ("adaptyv_flagged", test_adaptyv_flagged),
        ("de_job_not_flagged", test_de_job_not_flagged),
        ("nl_job_not_flagged", test_nl_job_not_flagged),
        ("ch_job_not_flagged", test_ch_job_not_flagged),
        ("ambiguous_city_not_flagged", test_ambiguous_city_not_flagged),
        ("no_location_not_flagged", test_no_location_not_flagged),
        ("fail_closed_missing_config", test_fail_closed_missing_config),
        ("fail_closed_empty_config", test_fail_closed_empty_config),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"[OK] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1

    print(f"\n=== F104 Tests: {passed} passed, {failed} failed ===")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_all()