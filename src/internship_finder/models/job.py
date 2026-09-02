"""Modelo canonico de vaga (``Job``) — pydantic.

Uma vaga de qualquer ATS vira um ``Job`` com campos estaveis: id, source,
title, company, location, country, remote, url, description, internship,
posted_at, collected_at, external_id, employment_type, country_iso. Campos
extras do ATS ficam preservados em ``raw``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

# Campos obrigatorios do Job: ATS sem valor util (vazio/so whitespace) nao
# produz uma vaga valida. Ausencia vira erro de validacao, nunca dado falso.
_REQUIRED_STR_FIELDS = ("title", "url")
# Campos opcionais: ausencia ou valor vazio/so whitespace vira ``None``
# (ausencia != dado falso — AGENTS.md).
_OPTIONAL_STR_FIELDS = (
    "company",
    "location",
    "country",
    "description",
    "employment_type",
    "country_iso",
    "external_id",
    "source",
)

# Todos os campos normalizaveis do Job (obrigatorios + opcionais).
_STR_FIELDS = _REQUIRED_STR_FIELDS + _OPTIONAL_STR_FIELDS


def _strip(value: Any) -> str | None:
    """Normaliza um valor para ``str`` sem borda de whitespace (None preserva)."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_job_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Normaliza as strings de um dict de vaga (mesma regra dos validators).

    Usado no caminho de filtro do CLI (que opera sobre dicts crus, sem
    reconstruir ``Job``): ``strip`` em title/url/company/location/country/
    country_iso/description/employment_type/external_id/source, e valor
    vazio/so-whitespace vira ``None``. Nao rejeita nada nem valida
    (inferencia/pais continua no adapter/filters).
    """
    result = dict(data)
    for field in _STR_FIELDS:
        if field in result:
            result[field] = _strip(result[field])
    return result


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
    # Prazo explicito de candidatura, quando o ATS o expoe (P0 deadline).
    # Nunca inferido de posted_at/fetched_at; None quando ausente.
    application_deadline: datetime | None = None
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

    # ------------------------------------------------------------------
    # Validacao forte de campos essenciais (P2 #11). Roda em ``mode="before"``
    # para normalizar o valor cru antes de qualquer atribuicao (aceita None e
    # preserva os defaults dos campos opcionais). Nada de inferencia de pais:
    # ``country_iso`` so e normalizado aqui — a origem do valor continua no
    # adapter/filters.
    # ------------------------------------------------------------------

    @field_validator(*_REQUIRED_STR_FIELDS, mode="before")
    @classmethod
    def _normalize_required_str(cls, value: Any, info: ValidationInfo) -> Any:
        stripped = _strip(value)
        if not stripped:
            raise ValueError(f"campo obrigatorio '{info.field_name}' vazio")
        return stripped

    @field_validator(*_OPTIONAL_STR_FIELDS, mode="before")
    @classmethod
    def _normalize_optional_str(cls, value: Any) -> Any:
        return _strip(value)
