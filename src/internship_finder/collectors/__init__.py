"""Coletores do pipeline (ATS + APIs diretas)."""

from internship_finder.collectors.phenom_tenants import (
    PHENOM_TENANTS,
    PhenomTenantConfig,
    build_phenom_company,
    get_phenom_tenant,
)
from internship_finder.collectors.us_centric_tenants import (
    US_CENTRIC_TENANTS,
    UsCentricTenantConfig,
    build_us_centric_company,
    get_us_centric_tenant,
)
from internship_finder.collectors.personio_tenants import (  # noqa: E402
    PersonioTenantConfig,
    build_personio_company,
    get_personio_tenant,
)
