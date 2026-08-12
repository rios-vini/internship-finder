"""Modelo de empresa/tenant localizado na base do ats-scrapers."""

from __future__ import annotations

from pydantic import BaseModel


class Company(BaseModel):
    """Uma empresa/tenant localizado na base (find_company)."""

    name: str  # nome exibido na base
    ats: str  # identificador do ATS, ex.: "smartrecruiters"
    slug: str  # slug do tenant no ATS, ex.: "BoschGroup"
    url: str | None = None  # URL de careers na base
    query: str = ""  # consulta original que encontrou a empresa
    match_kind: str = "exact"  # como o match foi feito: exact | token

    @property
    def source(self) -> str:
        """Identificador composto usado como ``Job.source``."""
        return f"{self.ats}:{self.slug}"
