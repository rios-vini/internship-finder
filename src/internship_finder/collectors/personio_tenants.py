"""Local Personio tenant registry for tenants with incorrect/missing database entries.

Personio career sites live at `{slug}.jobs.personio.com`. When the scraper
doesn't extract the company name from the payload, the adapter fills it with
the host (e.g., `hairoboticseurope.jobs.personio.com`).

This module provides correct configuration for known Personio tenants.
"""

from __future__ import annotations

from dataclasses import dataclass
from internship_finder.models.company import Company


@dataclass(frozen=True)
class PersonioTenantConfig:
    """Configuration for a Personio tenant."""
    slug: str  # e.g., "hairoboticseurope"
    display_name: str


# Known Personio tenants with verified configurations.
# Source: manual inspection of career sites (2026-10-27).
PERSONIO_TENANTS: dict[str, PersonioTenantConfig] = {
    "Hairobotics Europe": PersonioTenantConfig(
        slug="hairoboticseurope",
        display_name="Hairobotics Europe",
    ),
    "MSD": PersonioTenantConfig(
        slug="msd",
        display_name="MSD",
    ),
    "Sungrow EMEA": PersonioTenantConfig(
        slug="sungrow-emea",
        display_name="Sungrow EMEA",
    ),
}


def get_personio_tenant(name: str) -> PersonioTenantConfig | None:
    """Get Personio tenant config by company name (case-insensitive)."""
    for key, config in PERSONIO_TENANTS.items():
        if key.casefold() == name.casefold():
            return config
    return None


def build_personio_company(config: PersonioTenantConfig, query: str) -> Company:
    """Build a Company object for a Personio tenant with correct slug/url."""
    base_url = f"https://{config.slug}.jobs.personio.com"
    return Company(
        name=config.display_name,
        ats="personio",
        slug=config.slug,
        url=base_url,
        query=query,
        match_kind="exact",
    )