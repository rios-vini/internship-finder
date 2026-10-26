"""Local RMK (SuccessFactors Recruiting Marketing) tenant registry for tenants with shared/incorrect database entries.

The ats-scrapers database has some SuccessFactors tenants that share the generic
`successfactors:jobs` tenant. The feed returns internal company names (e.g.,
"Westnetz/Bayernwerk/HanseWerk" for E.ON) that don't match the canonical
company name. This module provides the correct RMK feed URLs so they can be
collected properly via the legacy RSS endpoint.

Each entry maps a company name to its RMK configuration:
- feed_url: Full RSS feed URL (used as slug by SuccessFactorsScraper for RMK tenants)
- company_alias: Optional mapping for the company name returned by the feed
  (E.ON feed returns Westnetz/Bayernwerk/HanseWerk; we map back to "E.ON"
  for collection identity while preserving the feed company in Job.company)

Source: manual inspection of career sites (2026-10-25, F123 RMK wave-3).
"""

from __future__ import annotations

from dataclasses import dataclass
from internship_finder.models.company import Company


@dataclass(frozen=True)
class RmkTenantConfig:
    """Configuration for an RMK (SuccessFactors RM) tenant."""
    feed_url: str  # Full RSS feed URL, e.g., "https://jobs.aldi-sued.de/services/rss/job/?locale=en_US&keywords=(Praktikum)"
    # Optional: map feed company names to canonical collection name
    # If None, the feed company name is used as-is (correct for MAHLE, Aldi Süd, KUKA)
    # For E.ON: feed returns "Westnetz"/"Bayernwerk"/"HanseWerk" -> map to "E.ON"
    company_alias: str | None = None
    # Optional: display name for the company
    display_name: str | None = None


# Known RMK tenants with verified feed URLs.
# Source: F123 RMK wave-3 live probes (2026-10-25) — all 4 respond 200 with <item>.
RMK_TENANTS: dict[str, RmkTenantConfig] = {
    "Aldi Süd": RmkTenantConfig(
        feed_url="https://jobs.aldi-sued.de/services/rss/job/?locale=en_US&keywords=(Praktikum)",
        company_alias=None,  # feed returns "Aldi Süd" (or similar)
        display_name="Aldi Süd",
    ),
    "E.ON": RmkTenantConfig(
        feed_url="https://careers.eon.com/services/rss/job/?locale=en_US&keywords=(Praktikum)",
        company_alias="E.ON",  # feed returns Westnetz/Bayernwerk/HanseWerk -> map to E.ON
        display_name="E.ON",
    ),
    "KUKA": RmkTenantConfig(
        feed_url="https://jobs.kuka.com/services/rss/job/?locale=en_US&keywords=(Praktikum)",
        company_alias=None,  # feed returns "KUKA"
        display_name="KUKA",
    ),
}


def get_rmk_tenant(name: str) -> RmkTenantConfig | None:
    """Get RMK tenant config by company name (case-insensitive)."""
    for key, config in RMK_TENANTS.items():
        if key.casefold() == name.casefold():
            return config
    return None


def build_rmk_company(config: RmkTenantConfig, query: str) -> Company:
    """Build a Company object for an RMK tenant with correct feed URL as slug."""
    return Company(
        name=config.display_name or config.feed_url,
        ats="successfactors",
        slug=config.feed_url,  # SuccessFactorsScraper expects full feed URL as slug for RMK
        url=config.feed_url,
        query=query,
        match_kind="exact",
    )