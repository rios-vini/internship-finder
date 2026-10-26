#!/usr/bin/env python3
"""Test offline para F124 — Onda Phenom: Hugo Boss + Mars + Viega.

Valida que os fixtures do feed Phenom (title/company/location/url) produzem
objetos Job corretos apos o adapter. Nao requer rede.
"""

from __future__ import annotations

import json
from pathlib import Path

from internship_finder.adapters.ats import AtsJobAdapter
from internship_finder.collectors.phenom_tenants import PHENOM_TENANTS, build_phenom_company
from internship_finder.models.job import Job


# Fixtures extraidos de chamadas reais ao endpoint /widgets (2026-10-25)
# URLs ja absolutas (o scraper Phenom normaliza URLs relativas)
# Location ja composto pelo scraper (_format_location: city, state, country)
# employment_type ja mapeado pelo scraper (_EMPLOYMENT_TYPE_PATTERNS)
# country usa nomes completos (infer_country_iso mapeia nomes -> ISO alpha-2)
FIXTURES: list[dict] = [
    # Hugo Boss (en_global/global)
    {
        "jobId": "141146",
        "title": "Full Time Key Holder - BOSS Store - Clearfolk",
        "jobUrl": "https://careers.hugoboss.com/job/141146",
        "location": "Fort Worth, TX, United States",
        "city": "Fort Worth",
        "state": "TX",
        "country": "United States",
        "jobType": "Full Time",
        "employment_type": "FULL_TIME",
        "descriptionTeaser": "Join our team as a Key Holder...",
        "description": "<p>Full description here...</p>",
        "postedDate": "2026-10-20T00:00:00Z",
        "category": "Retail",
        "department": "Store Operations",
    },
    # Mars (en_global/global)
    {
        "jobId": "R161848",
        "title": "Warehouse Operator Nights",
        "jobUrl": "https://careers.mars.com/job/R161848",
        "location": "Salt Lake City, Utah, United States",
        "city": "Salt Lake City",
        "state": "Utah",
        "country": "United States",
        "jobType": "Full Time",
        "employment_type": "FULL_TIME",
        "descriptionTeaser": "Warehouse operator position...",
        "description": "<p>Full description here...</p>",
        "postedDate": "2026-10-22T00:00:00Z",
        "category": "Supply Chain",
        "department": "Manufacturing",
    },
    # Viega (en_eu/eu) - German locations
    {
        "jobId": "17328",
        "title": "Ausbildung zum Zerspanungsmechaniker (all genders) - Start 08/2027 Standort Lennestadt-Elspe",
        "jobUrl": "https://careers.viega.com/job/17328",
        "location": "Lennestadt-Elspe, Nordrhein-Westfalen, Germany",
        "city": "Lennestadt-Elspe",
        "state": "Nordrhein-Westfalen",
        "country": "Germany",
        "jobType": "Ausbildung",
        "employment_type": "INTERN",
        "descriptionTeaser": "Ausbildung zum Zerspanungsmechaniker...",
        "description": "<p>Full description here...</p>",
        "postedDate": "2026-10-15T00:00:00Z",
        "category": "Production",
        "department": "Manufacturing",
    },
    # Viega - Switzerland
    {
        "jobId": "17424",
        "title": "Teamleiter*in Verification & Validation (m/w/d)",
        "jobUrl": "https://careers.viega.com/job/17424",
        "location": "Chur, Graubünden, Switzerland",
        "city": "Chur",
        "state": "Graubünden",
        "country": "Switzerland",
        "jobType": "Full Time",
        "employment_type": "FULL_TIME",
        "descriptionTeaser": "Teamleiter Verification & Validation...",
        "description": "<p>Full description here...</p>",
        "postedDate": "2026-10-18T00:00:00Z",
        "category": "Quality",
        "department": "Engineering",
    },
]


def test_adapter_normalization() -> None:
    """Testa que o adapter normaliza corretamente os fixtures Phenom."""
    adapter = AtsJobAdapter()
    errors: list[str] = []

    for i, (fixture, tenant_name) in enumerate(zip(FIXTURES, ["Hugo Boss", "Mars", "Viega", "Viega"])):
        config = PHENOM_TENANTS[tenant_name]
        company = build_phenom_company(config, tenant_name)
        
        job = adapter.to_job(fixture, company)
        
        # Verificações básicas
        assert job.title == fixture["title"], f"Fixture {i}: title mismatch"
        assert job.url == fixture["jobUrl"], f"Fixture {i}: url mismatch"
        assert job.company == config.display_name, f"Fixture {i}: company mismatch"
        assert job.external_id == fixture["jobId"], f"Fixture {i}: external_id mismatch"
        assert job.source == f"phenom:{config.base_url}", f"Fixture {i}: source mismatch"
        
        # Location deve ser o campo composto pelo scraper
        expected_location = fixture["location"]
        assert job.location == expected_location, f"Fixture {i}: location mismatch (got {job.location!r}, expected {expected_location!r})"
        
        # Country ISO deve ser inferido corretamente
        if fixture["country"] == "Germany":
            assert job.country_iso == "de", f"Fixture {i}: country_iso should be 'de' for Germany"
        elif fixture["country"] == "Switzerland":
            assert job.country_iso == "ch", f"Fixture {i}: country_iso should be 'ch' for Switzerland"
        elif fixture["country"] == "United States":
            assert job.country_iso == "us", f"Fixture {i}: country_iso should be 'us' for US"
        
        # Employment type deve vir mapeado do scraper
        assert job.employment_type == fixture["employment_type"], f"Fixture {i}: employment_type mismatch (got {job.employment_type!r}, expected {fixture['employment_type']!r})"
        
        # Description deve ser passada (o adapter nao limpa HTML; o scraper faz isso)
        assert job.description is not None, f"Fixture {i}: description should not be None"
        assert "Full description here..." in job.description, f"Fixture {i}: description should contain text"
        
        print(f"  ✓ Fixture {i} ({tenant_name}): {job.title[:50]}... | {job.location} | {job.country_iso} | {job.employment_type}")

    print(f"\n✅ All {len(FIXTURES)} fixtures passed normalization checks")


def test_company_building() -> None:
    """Testa que build_phenom_company cria Company com locale/country corretos."""
    for name, config in PHENOM_TENANTS.items():
        company = build_phenom_company(config, name)
        
        assert company.ats == "phenom"
        assert company.slug == config.base_url
        assert company.url == config.base_url
        assert company.locale == config.locale
        assert company.country == config.country
        assert company.match_kind == "exact"
        
        print(f"  ✓ {name}: locale={company.locale}, country={company.country}")

    print("✅ All company builds correct")


def test_fixture_count() -> None:
    """Verifica contagem de fixtures por empresa."""
    from collections import Counter
    counts = Counter()
    for fixture, tenant_name in zip(FIXTURES, ["Hugo Boss", "Mars", "Viega", "Viega"]):
        counts[tenant_name] += 1
    
    assert counts["Hugo Boss"] == 1
    assert counts["Mars"] == 1
    assert counts["Viega"] == 2
    print(f"✅ Fixture counts: {dict(counts)}")


if __name__ == "__main__":
    print("=== F124 Phenom Fixtures Test ===\n")
    
    print("1. Testing company building...")
    test_company_building()
    print()
    
    print("2. Testing fixture counts...")
    test_fixture_count()
    print()
    
    print("3. Testing adapter normalization...")
    test_adapter_normalization()
    print()
    
    print("=== All tests passed ===")