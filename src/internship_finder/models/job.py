"""Modelo canonico de vaga (``Job``) — pydantic.

Uma vaga de qualquer ATS vira um ``Job`` com campos estaveis: id, source,
title, company, location, country, remote, url, description, internship,
posted_at, collected_at, external_id, employment_type, country_iso. Campos
extras do ATS ficam preservados em ``raw``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Job(BaseModel):
    """Vaga normalizada, independente do schema do ATS de origem."""

    model_config = ConfigDict(extra="ignore")

    id: str
    source: str  # identificador da origem, ex.: "smartrecruiters:BoschGroup"
    title: str
    company: str
    location: str | None = None
    country: str | None = None
    remote: bool | None = None
    url: str
    description: str | None = None
    internship: bool = False
    posted_at: datetime | None = None
    collected_at: datetime
    # Campos adicionados na integracao do MVP validado (set/2026).
    external_id: str | None = None
    employment_type: str | None = None
    country_iso: str | None = None
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializacao JSON-friendly (datetimes viram ISO strings)."""
        return self.model_dump(mode="json")

    def __str__(self) -> str:
        loc = self.location or "-"
        return f"{self.title} | {self.company} | {loc} | {self.url}"
