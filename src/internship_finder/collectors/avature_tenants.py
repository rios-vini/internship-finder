"""Local Avature tenant registry for tenants missing from the ats-scrapers database.

The ats-scrapers upstream database (avature.csv) does not include custom-domain
Avature portals discovered manually (Siemens Energy, TenneT). This module
provides the correct configuration so they can be collected properly.

Each entry maps a company name to its Avature configuration:
- portal_url: Full careers portal URL (used as slug by AvatureScraper)
- display_name: Optional display name for the company

The Avature scraper (ats-scrapers 0.3.0) accepts the full portal URL as the
tenant slug. For tenants returning HTTP 406, the scraper falls back to
httpcloak (server-rendered HTML from /SearchJobs/ pages).

RSS feeds at `{portal_url}/<locale>/<path>/feed/?...` are the discovery
channel (F125), not the collection channel — collection uses the installed
AvatureScraper with the full URL as slug.

Source: manual discovery via RSS feeds (2026-10-26, F125).
"""

from __future__ import annotations

from dataclasses import dataclass
from internship_finder.models.company import Company


@dataclass(frozen=True)
class AvatureTenantConfig:
    """Configuration for an Avature tenant."""
    portal_url: str  # Full careers portal URL, e.g., "https://jobs.siemens-energy.com"
    display_name: str | None = None


# Known Avature tenants with verified portal URLs.
# Source: F125 live discovery (2026-10-26) — both portals expose functional RSS feeds.
AVATURE_TENANTS: dict[str, AvatureTenantConfig] = {
    "Siemens Energy": AvatureTenantConfig(
        portal_url="https://jobs.siemens-energy.com",
        display_name="Siemens Energy",
    ),
    "TenneT": AvatureTenantConfig(
        portal_url="https://careers.tennet.eu",
        display_name="TenneT",
    ),
}


def get_avature_tenant(name: str) -> AvatureTenantConfig | None:
    """Get Avature tenant config by company name (case-insensitive)."""
    for key, config in AVATURE_TENANTS.items():
        if key.casefold() == name.casefold():
            return config
    return None


def build_avature_company(config: AvatureTenantConfig, query: str) -> Company:
    """Build a Company object for an Avature tenant with correct portal URL as slug."""
    return Company(
        name=config.display_name or config.portal_url,
        ats="avature",
        slug=config.portal_url,  # AvatureScraper expects full portal URL as slug
        url=config.portal_url,
        query=query,
        match_kind="exact",
    )