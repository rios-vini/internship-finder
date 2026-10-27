#!/usr/bin/env python3
"""Test script for F139 company host-like fix.

Verifies that the AtsJobAdapter correctly replaces host-like company names
from scrapers with canonical company names from our Company registry.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter, _is_host_like_company
from internship_finder.models.job import Job
from internship_finder.models.company import Company

# Inline fixtures to avoid import issues
TI_ORACLE_JOB = {
    "id": "test-ti-1",
    "source": "oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
    "title": "Intern (f/m/d) - Procurement",
    "company": "edbz.fa.us2.oraclecloud.com",
    "location": "Munich, DE",
    "country": "DE",
    "remote": None,
    "url": "https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/123",
    "description": "Test description",
    "external_id": "123",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

DHL_PHENOM_JOB = {
    "id": "test-dhl-1",
    "source": "phenom:https://careers.dhl.com",
    "title": "Werkstudent (m/w/d) Supply Chain",
    "company": "careers.dhl.com",
    "location": "Bonn, DE",
    "country": "DE",
    "remote": None,
    "url": "https://careers.dhl.com/job/456",
    "description": "Test description",
    "external_id": "456",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

BCG_PHENOM_JOB = {
    "id": "test-bcg-1",
    "source": "phenom:https://careers.bcg.com",
    "title": "Intern (m/w/d) Consulting",
    "company": "careers.bcg.com",
    "location": "Munich, DE",
    "country": "DE",
    "remote": None,
    "url": "https://careers.bcg.com/job/789",
    "description": "Test description",
    "external_id": "789",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

ROCHE_PHENOM_JOB = {
    "id": "test-roche-1",
    "source": "phenom:https://careers.roche.com",
    "title": "Praktikant (m/w/d) Procurement",
    "company": "careers.roche.com",
    "location": "Mannheim, DE",
    "country": "DE",
    "remote": None,
    "url": "https://careers.roche.com/job/101",
    "description": "Test description",
    "external_id": "101",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

ALLIANZ_PHENOM_JOB = {
    "id": "test-allianz-1",
    "source": "phenom:https://careers.allianz.com",
    "title": "Working Student (m/f/d) Analytics",
    "company": "careers.allianz.com",
    "location": "Munich, DE",
    "country": "DE",
    "remote": None,
    "url": "https://careers.allianz.com/job/102",
    "description": "Test description",
    "external_id": "102",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

PHILIPS_JOB = {
    "id": "test-philips-1",
    "source": "successfactors:www.careers.philips.com",
    "title": "Intern (m/w/d) Supply Chain",
    "company": "www.careers.philips.com",
    "location": "Hamburg, DE",
    "country": "DE",
    "remote": None,
    "url": "https://www.careers.philips.com/job/103",
    "description": "Test description",
    "external_id": "103",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

HAIROBOTICS_PERSONIO_JOB = {
    "id": "test-hairob-1",
    "source": "personio:hairoboticseurope",
    "title": "Working Student (m/f/d) Engineering",
    "company": "hairoboticseurope.jobs.personio.com",
    "location": "Berlin, DE",
    "country": "DE",
    "remote": None,
    "url": "https://hairoboticseurope.jobs.personio.com/job/104",
    "description": "Test description",
    "external_id": "104",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

MSD_PERSONIO_JOB = {
    "id": "test-msd-1",
    "source": "personio:msd",
    "title": "Intern (m/w/d) Marketing",
    "company": "jobs.msd.com",
    "location": "Munich, DE",
    "country": "DE",
    "remote": None,
    "url": "https://jobs.msd.com/job/105",
    "description": "Test description",
    "external_id": "105",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

SUNGROW_PERSONIO_JOB = {
    "id": "test-sungrow-1",
    "source": "personio:sungrow-emea",
    "title": "Praktikant (m/w/d) Procurement",
    "company": "sungrow-emea.jobs.personio.com",
    "location": "Munich, DE",
    "country": "DE",
    "remote": None,
    "url": "https://sungrow-emea.jobs.personio.com/job/106",
    "description": "Test description",
    "external_id": "106",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

MARSH_JOB = {
    "id": "test-marsh-1",
    "source": "icims:careers.marsh.com",
    "title": "Intern (m/w/d) Risk",
    "company": "careers.marsh.com",
    "location": "Cologne, DE",
    "country": "DE",
    "remote": None,
    "url": "https://careers.marsh.com/job/107",
    "description": "Test description",
    "external_id": "107",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
    "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
    "company_host_like": False,
    "raw": None,
}

EXPECTED_COMPANIES = {
    "test-ti-1": "Texas Instruments",
    "test-dhl-1": "DHL",
    "test-bcg-1": "Boston Consulting Group",
    "test-roche-1": "Roche",
    "test-allianz-1": "Allianz",
    "test-philips-1": "Philips",
    "test-hairob-1": "Hairobotics Europe",
    "test-msd-1": "MSD",
    "test-sungrow-1": "Sungrow EMEA",
    "test-marsh-1": "Marsh",
}

TEST_COMPANIES = {
    "test-ti-1": Company(
        name="Texas Instruments",
        ats="oracle",
        slug="https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
        url="https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
        query="Texas Instruments",
        match_kind="exact",
    ),
    "test-dhl-1": Company(
        name="DHL",
        ats="phenom",
        slug="https://careers.dhl.com",
        url="https://careers.dhl.com",
        query="DHL",
        match_kind="exact",
        locale="en_global",
        country="global",
    ),
    "test-bcg-1": Company(
        name="Boston Consulting Group",
        ats="phenom",
        slug="https://careers.bcg.com",
        url="https://careers.bcg.com",
        query="Boston Consulting Group",
        match_kind="exact",
        locale="en_global",
        country="global",
    ),
    "test-roche-1": Company(
        name="Roche",
        ats="phenom",
        slug="https://careers.roche.com",
        url="https://careers.roche.com",
        query="Roche",
        match_kind="exact",
        locale="en_global",
        country="global",
    ),
    "test-allianz-1": Company(
        name="Allianz",
        ats="phenom",
        slug="https://careers.allianz.com",
        url="https://careers.allianz.com",
        query="Allianz",
        match_kind="exact",
        locale="en_global",
        country="global",
    ),
    "test-philips-1": Company(
        name="Philips",
        ats="successfactors",
        slug="www.careers.philips.com",
        url="https://www.careers.philips.com",
        query="Philips",
        match_kind="exact",
    ),
    "test-hairob-1": Company(
        name="Hairobotics Europe",
        ats="personio",
        slug="hairoboticseurope",
        url="https://hairoboticseurope.jobs.personio.com",
        query="Hairobotics Europe",
        match_kind="exact",
    ),
    "test-msd-1": Company(
        name="MSD",
        ats="personio",
        slug="msd",
        url="https://msd.jobs.personio.com",
        query="MSD",
        match_kind="exact",
    ),
    "test-sungrow-1": Company(
        name="Sungrow EMEA",
        ats="personio",
        slug="sungrow-emea",
        url="https://sungrow-emea.jobs.personio.com",
        query="Sungrow EMEA",
        match_kind="exact",
    ),
    "test-marsh-1": Company(
        name="Marsh",
        ats="icims",
        slug="careers.marsh.com",
        url="https://careers.marsh.com",
        query="Marsh",
        match_kind="exact",
    ),
}

ALL_TEST_JOBS = [
    TI_ORACLE_JOB,
    DHL_PHENOM_JOB,
    BCG_PHENOM_JOB,
    ROCHE_PHENOM_JOB,
    ALLIANZ_PHENOM_JOB,
    PHILIPS_JOB,
    HAIROBOTICS_PERSONIO_JOB,
    MSD_PERSONIO_JOB,
    SUNGROW_PERSONIO_JOB,
    MARSH_JOB,
]


def test_host_like_detection() -> bool:
    """Test the _is_host_like_company helper function."""
    print("== Testing _is_host_like_company ==")
    
    test_cases = [
        # (input, expected)
        ("edbz.fa.us2.oraclecloud.com", True),
        ("careers.dhl.com", True),
        ("careers.bcg.com", True),
        ("careers.roche.com", True),
        ("careers.allianz.com", True),
        ("www.careers.philips.com", True),
        ("hairoboticseurope.jobs.personio.com", True),
        ("jobs.msd.com", True),
        ("sungrow-emea.jobs.personio.com", True),
        ("careers.marsh.com", True),
        # Legitimate company names that should NOT be flagged
        ("AT&T", False),
        ("D.E. Shaw", False),
        ("Texas Instruments", False),
        ("DHL", False),
        ("Boston Consulting Group", False),
        ("Roche", False),
        ("Allianz", False),
        ("Philips", False),
        ("Hairobotics Europe", False),
        ("MSD", False),
        ("Sungrow EMEA", False),
        ("Marsh", False),
        ("SAP", False),
        ("Bosch Group", False),
        ("BMW Group", False),
        ("", False),
        (None, False),
    ]
    
    all_pass = True
    for input_val, expected in test_cases:
        result = _is_host_like_company(input_val) if input_val else False
        status = "OK" if result == expected else "FAIL"
        if result != expected:
            all_pass = False
        print(f"  [{status}] _is_host_like_company({input_val!r}) = {result} (expected {expected})")
    
    return all_pass


def test_adapter_fix() -> bool:
    """Test the AtsJobAdapter with fixtures."""
    print("\n== Testing AtsJobAdapter fix ==")
    
    adapter = AtsJobAdapter()
    all_pass = True
    
    for job_dict in ALL_TEST_JOBS:
        job_id = job_dict["id"]
        company = TEST_COMPANIES[job_id]
        expected_company = EXPECTED_COMPANIES[job_id]
        
        # Convert dict to Job (simulating scraper output)
        scraper_job = Job(**job_dict)
        
        # Run adapter
        normalized = adapter.to_job(scraper_job, company)
        
        # Check company name
        company_ok = normalized.company == expected_company
        host_like_ok = normalized.company_host_like == True  # Should be flagged
        
        status = "OK" if (company_ok and host_like_ok) else "FAIL"
        if not (company_ok and host_like_ok):
            all_pass = False
        
        print(f"  [{status}] {job_id}: company={normalized.company!r} (expected {expected_company!r}), host_like={normalized.company_host_like}")
        if not company_ok:
            print(f"    -> FAIL: company mismatch")
        if not host_like_ok:
            print(f"    -> FAIL: company_host_like should be True")
    
    return all_pass


def test_legitimate_company_not_flagged() -> bool:
    """Test that legitimate company names are not flagged as host-like."""
    print("\n== Testing legitimate company names not flagged ==")
    
    adapter = AtsJobAdapter()
    all_pass = True
    
    # Create a job with a legitimate company name (not host-like)
    job_dict = {
        "id": "test-legit-1",
        "source": "smartrecruiters:BoschGroup",
        "title": "Intern (m/w/d) Engineering",
        "company": "Bosch Group",  # Legitimate company name
        "location": "Stuttgart, DE",
        "country": "DE",
        "url": "https://jobs.bosch.com/job/1",
        "description": "Test",
        "external_id": "1",
        "employment_type": "INTERN",
        "country_iso": "DE",
        "posted_at": "2026-10-01T00:00:00Z",
        "collected_at": "2026-10-27T00:00:00Z",
    }
    
    company = Company(
        name="Bosch Group",
        ats="smartrecruiters",
        slug="BoschGroup",
        url="https://careers.bosch.com",
        query="Bosch Group",
        match_kind="exact",
    )
    
    # F139-port: payload do scraper e um DICT (fluxo real: scrape -> dict ->
    # to_job(dict, company)); o Job da producao exige company: str (P1.1)
    normalized = adapter.to_job(job_dict, company)
    
    company_ok = normalized.company == "Bosch Group"
    host_like_ok = normalized.company_host_like == False
    
    status = "OK" if (company_ok and host_like_ok) else "FAIL"
    if not (company_ok and host_like_ok):
        all_pass = False
    
    print(f"  [{status}] Legitimate company: company={normalized.company!r}, host_like={normalized.company_host_like}")
    
    return all_pass


def test_scraper_company_none_uses_canonical() -> bool:
    """Test that when scraper doesn't provide company, canonical is used."""
    print("\n== Testing missing scraper company falls back to canonical ==")
    
    adapter = AtsJobAdapter()
    all_pass = True
    
    job_dict = {
        "id": "test-none-1",
        "source": "smartrecruiters:SAP",
        "title": "Intern (m/w/d) IT",
        "company": "",  # Empty company field (simulating missing)
        "location": "Walldorf, DE",
        "country": "DE",
        "remote": None,
        "url": "https://jobs.sap.com/job/1",
        "description": "Test",
        "external_id": "1",
        "employment_type": "INTERN",
        "country_iso": "DE",
        "posted_at": datetime.fromisoformat("2026-10-01T00:00:00Z".replace("Z", "+00:00")),
        "collected_at": datetime.fromisoformat("2026-10-27T00:00:00Z".replace("Z", "+00:00")),
        "company_host_like": False,
        "raw": None,
    }
    
    company = Company(
        name="SAP",
        ats="smartrecruiters",
        slug="SAP",
        url="https://careers.sap.com",
        query="SAP",
        match_kind="exact",
    )
    
    # F139-port: payload do scraper e DICT (producao: Job exige company: str)
    normalized = adapter.to_job(job_dict, company)
    
    company_ok = normalized.company == "SAP"
    host_like_ok = normalized.company_host_like == False
    
    status = "OK" if (company_ok and host_like_ok) else "FAIL"
    if not (company_ok and host_like_ok):
        all_pass = False
    
    print(f"  [{status}] Missing scraper company: company={normalized.company!r}, host_like={normalized.company_host_like}")
    
    return all_pass


def test_dedup_ti_pair_funde_com_aliases() -> bool:
    """Gate 3 do card: o par TI 25011485 (dataset 'Edbz' vs coleta nova
    'Texas Instruments') FUNDE na chave F135 — sem o alias de identidade a
    mesma vaga re-entraria com ID novo e poluiria o NEW."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from internship_finder.cross_source_dedup_store import compute_cross_source_dedup_key
    from internship_finder.cross_source_dedup import load_company_aliases

    aliases = load_company_aliases()
    a_ok = aliases.get("edbz") == "Texas Instruments"
    b_ok = aliases.get("careers.dhl.com") == "DHL"
    print(f"  [{'OK' if a_ok else 'FAIL'}] alias Edbz -> Texas Instruments")
    print(f"  [{'OK' if b_ok else 'FAIL'}] alias careers.dhl.com -> DHL")

    # Par real do acervo (verbatim 27/10): a vaga 25011485 nos dois lados.
    a = {
        "company": "Edbz",
        "title": "Praktikant/in (m/f/d) im Bereich Supply Chain, Operations, Einkauf oder Pricing – 2026",
        "location": "Germany",
        "url": "https://edbz.fa.us2.oraclecloud.com/?keyword=&mode=jobs&lang=en&site_number=CX#25011485",
        "source": "sf_dataset:oracle",
        "raw": {},
    }
    b = dict(a)
    b["company"] = "Texas Instruments"  # como a coleta nova chega pós-fix
    b["source"] = "oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1"
    b["url"] = "https://edbz.fa.us2.oraclecloud.com/?keyword=&mode=jobs&lang=en&site_number=CX_1#25011485"

    ka, kb = compute_cross_source_dedup_key(a), compute_cross_source_dedup_key(b)
    funde = ka == kb and ka.startswith("company_title_city:")
    print(f"  [{'OK' if funde else 'FAIL'}] par TI 25011485 funde: {ka[:60]}...")
    return a_ok and b_ok and funde


def main() -> int:
    print("Running F139 company host-like fix tests...\n")
    
    results = [
        test_host_like_detection(),
        test_adapter_fix(),
        test_legitimate_company_not_flagged(),
        test_scraper_company_none_uses_canonical(),
        test_dedup_ti_pair_funde_com_aliases(),
    ]
    
    print(f"\n{'='*50}")
    if all(results):
        print("ALL TESTS PASSED")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    from internship_finder.models.company import Company
    raise SystemExit(main())