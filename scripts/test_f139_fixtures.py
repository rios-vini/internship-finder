"""Test fixtures for F139 company host-like fix.

These are verbatim examples of the problematic company values from scrapers
and their expected canonical company names.
"""

# TI (Oracle) - company comes as host, should be "Texas Instruments"
TI_ORACLE_JOB = {
    "id": "test-ti-1",
    "source": "oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
    "title": "Intern (f/m/d) - Procurement",
    "company": "edbz.fa.us2.oraclecloud.com",  # host-like from scraper
    "location": "Munich, DE",
    "country": "DE",
    "url": "https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/123",
    "description": "Test description",
    "external_id": "123",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# DHL (Phenom) - company comes as host, should be "DHL"
DHL_PHENOM_JOB = {
    "id": "test-dhl-1",
    "source": "phenom:https://careers.dhl.com",
    "title": "Werkstudent (m/w/d) Supply Chain",
    "company": "careers.dhl.com",  # host-like from scraper
    "location": "Bonn, DE",
    "country": "DE",
    "url": "https://careers.dhl.com/job/456",
    "description": "Test description",
    "external_id": "456",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# BCG (Phenom) - company comes as host, should be "Boston Consulting Group"
BCG_PHENOM_JOB = {
    "id": "test-bcg-1",
    "source": "phenom:https://careers.bcg.com",
    "title": "Intern (m/w/d) Consulting",
    "company": "careers.bcg.com",  # host-like from scraper
    "location": "Munich, DE",
    "country": "DE",
    "url": "https://careers.bcg.com/job/789",
    "description": "Test description",
    "external_id": "789",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Roche (Phenom) - company comes as host, should be "Roche"
ROCHE_PHENOM_JOB = {
    "id": "test-roche-1",
    "source": "phenom:https://careers.roche.com",
    "title": "Praktikant (m/w/d) Procurement",
    "company": "careers.roche.com",  # host-like from scraper
    "location": "Mannheim, DE",
    "country": "DE",
    "url": "https://careers.roche.com/job/101",
    "description": "Test description",
    "external_id": "101",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Allianz (Phenom) - company comes as host, should be "Allianz"
ALLIANZ_PHENOM_JOB = {
    "id": "test-allianz-1",
    "source": "phenom:https://careers.allianz.com",
    "title": "Working Student (m/f/d) Analytics",
    "company": "careers.allianz.com",  # host-like from scraper
    "location": "Munich, DE",
    "country": "DE",
    "url": "https://careers.allianz.com/job/102",
    "description": "Test description",
    "external_id": "102",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Philips (SuccessFactors/other) - company comes as host
PHILIPS_JOB = {
    "id": "test-philips-1",
    "source": "successfactors:www.careers.philips.com",
    "title": "Intern (m/w/d) Supply Chain",
    "company": "www.careers.philips.com",  # host-like from scraper
    "location": "Hamburg, DE",
    "country": "DE",
    "url": "https://www.careers.philips.com/job/103",
    "description": "Test description",
    "external_id": "103",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Personio - Hairobotics Europe
HAIROBOTICS_PERSONIO_JOB = {
    "id": "test-hairob-1",
    "source": "personio:hairoboticseurope",
    "title": "Working Student (m/f/d) Engineering",
    "company": "hairoboticseurope.jobs.personio.com",  # host-like from scraper
    "location": "Berlin, DE",
    "country": "DE",
    "url": "https://hairoboticseurope.jobs.personio.com/job/104",
    "description": "Test description",
    "external_id": "104",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Personio - MSD
MSD_PERSONIO_JOB = {
    "id": "test-msd-1",
    "source": "personio:msd",
    "title": "Intern (m/w/d) Marketing",
    "company": "jobs.msd.com",  # host-like from scraper
    "location": "Munich, DE",
    "country": "DE",
    "url": "https://jobs.msd.com/job/105",
    "description": "Test description",
    "external_id": "105",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Personio - Sungrow EMEA
SUNGROW_PERSONIO_JOB = {
    "id": "test-sungrow-1",
    "source": "personio:sungrow-emea",
    "title": "Praktikant (m/w/d) Procurement",
    "company": "sungrow-emea.jobs.personio.com",  # host-like from scraper
    "location": "Munich, DE",
    "country": "DE",
    "url": "https://sungrow-emea.jobs.personio.com/job/106",
    "description": "Test description",
    "external_id": "106",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Marsh (other ATS)
MARSH_JOB = {
    "id": "test-marsh-1",
    "source": "icims:careers.marsh.com",
    "title": "Intern (m/w/d) Risk",
    "company": "careers.marsh.com",  # host-like from scraper
    "location": "Cologne, DE",
    "country": "DE",
    "url": "https://careers.marsh.com/job/107",
    "description": "Test description",
    "external_id": "107",
    "employment_type": "INTERN",
    "country_iso": "DE",
    "posted_at": "2026-10-01T00:00:00Z",
    "collected_at": "2026-10-27T00:00:00Z",
}

# Expected canonical company names for each test job
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

# Company objects that would be passed to the adapter (from our registries)
from internship_finder.models.company import Company

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