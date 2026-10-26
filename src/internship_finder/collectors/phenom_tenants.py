"""Local Phenom tenant registry for tenants with incorrect/missing database entries.

The ats-scrapers database has some Phenom tenants with placeholder slugs ('nan')
or incorrect ATS assignments. This module provides the correct configuration
for known tenants so they can be collected properly.

Each entry maps a company name to its Phenom configuration:
- base_url: Full careers site URL (used as slug by PhenomScraper)
- locale: Phenom locale code (e.g., 'en_global', 'en_eu', 'en_us')
- country: Phenom country code (e.g., 'global', 'eu', 'us')
"""

from __future__ import annotations

from dataclasses import dataclass
from internship_finder.models.company import Company


@dataclass(frozen=True)
class PhenomTenantConfig:
    """Configuration for a Phenom tenant."""
    base_url: str
    locale: str
    country: str
    # Optional: display name for the company
    display_name: str | None = None


# Known Phenom tenants with verified configurations.
# Source: manual inspection of career sites (2026-10-25).
PHENOM_TENANTS: dict[str, PhenomTenantConfig] = {
    "Hugo Boss": PhenomTenantConfig(
        base_url="https://careers.hugoboss.com",
        locale="en_global",
        country="global",
        display_name="Hugo Boss",
    ),
    "Mars": PhenomTenantConfig(
        base_url="https://careers.mars.com",
        locale="en_global",
        country="global",
        display_name="Mars",
    ),
    "Viega": PhenomTenantConfig(
        base_url="https://careers.viega.com",
        locale="en_eu",
        country="eu",
        display_name="Viega",
    ),
}


def get_phenom_tenant(name: str) -> PhenomTenantConfig | None:
    """Get Phenom tenant config by company name (case-insensitive)."""
    for key, config in PHENOM_TENANTS.items():
        if key.casefold() == name.casefold():
            return config
    return None


def build_phenom_company(config: PhenomTenantConfig, query: str) -> Company:
    """Build a Company object for a Phenom tenant with correct slug/url."""
    return Company(
        name=config.display_name or config.base_url,
        ats="phenom",
        slug=config.base_url,  # PhenomScraper expects full URL as slug
        url=config.base_url,
        query=query,
        match_kind="exact",
        locale=config.locale,
        country=config.country,
    )