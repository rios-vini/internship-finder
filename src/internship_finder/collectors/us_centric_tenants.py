"""Local US-centric tenant registry for companies missing/incorrect in the ats-scrapers database.

These are US-headquartered companies with significant Germany presence (EN-first career sites).
Source: manual inspection of career sites (2026-10-26).
"""

from __future__ import annotations

from dataclasses import dataclass
from internship_finder.models.company import Company


@dataclass(frozen=True)
class UsCentricTenantConfig:
    """Configuration for a US-centric tenant."""
    name: str
    ats: str  # "oracle" | "workday"
    url: str  # Full careers URL (used as slug by Oracle/Workday scrapers)
    display_name: str | None = None


# Known US-centric tenants with verified configurations.
# These may be missing from the ats-scrapers database (ADI) or need explicit config.
US_CENTRIC_TENANTS: dict[str, UsCentricTenantConfig] = {
    "Texas Instruments": UsCentricTenantConfig(
        name="Texas Instruments",
        ats="oracle",
        url="https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
        display_name="Texas Instruments",
    ),
    "Analog Devices": UsCentricTenantConfig(
        name="Analog Devices",
        ats="workday",
        url="https://analogdevices.wd1.myworkdayjobs.com/External",
        display_name="Analog Devices",
    ),
    "Copeland": UsCentricTenantConfig(
        name="Copeland",
        ats="workday",
        url="https://copeland.wd5.myworkdayjobs.com/copeland_external_careers_page",
        display_name="Copeland",
    ),
}


def get_us_centric_tenant(name: str) -> UsCentricTenantConfig | None:
    """Get US-centric tenant config by company name (case-insensitive)."""
    for key, config in US_CENTRIC_TENANTS.items():
        if key.casefold() == name.casefold():
            return config
    return None


def build_us_centric_company(config: UsCentricTenantConfig, query: str) -> Company:
    """Build a Company object for a US-centric tenant with correct slug/url."""
    return Company(
        name=config.display_name or config.name,
        ats=config.ats,
        slug=config.url,  # Oracle/Workday scrapers expect full URL as slug
        url=config.url,
        query=query,
        match_kind="exact",
    )