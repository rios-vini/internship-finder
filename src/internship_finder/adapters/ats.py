"""Adapter: normaliza o schema de cada ATS para o modelo ``Job`` (pydantic).

Nao assumimos schema universal. O que sai de um scraper pode ser um
``ats_scrapers.models.Job`` (pydantic) ou um dict cru de um ATS qualquer.
O adapter extrai campos por cadeias de fallback (``url``/``apply_url``/
``slug``, ``title``/``name``/``position``, ``location``/``locations``/
``city``+``country``...) e guarda o resto em ``raw``.

Alem dos campos basicos, o adapter preenche os campos novos do modelo
canonico: ``external_id``, ``employment_type``, ``country_iso``,
``posted_at`` (quando o ATS expoe), ``id`` (derivado de external_id ou
hash da URL) e a flag ``internship`` (heuristica de ``filters``).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from internship_finder.filters import is_internship
from internship_finder.models.company import Company
from internship_finder.models.job import Job

log = logging.getLogger(__name__)

# Cadeias de fallback por campo do Job.
_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("title", "name", "position", "headline", "job_title", "jobTitle"),
    "company": (
        "company",
        "company_name",
        "companyName",
        "employer",
        "organization",
        "org",
    ),
    "url": ("url", "apply_url", "applyUrl", "absolute_url", "job_url", "jobUrl", "link"),
    "location": ("location", "locations", "city", "address", "workplace"),
    "description": ("description", "summary", "content", "text", "job_description", "jobDescription"),
    "external_id": (
        "external_id",
        "externalId",
        "ats_id",
        "atsId",
        "requisition_id",
        "requisitionId",
        "job_id",
        "jobId",
        "uid",
        "id",
    ),
    "employment_type": ("employment_type", "employmentType", "type", "commitment"),
    "country_iso": ("country_iso", "countryIso", "country_code", "countryCode", "country"),
    "posted_at": (
        "posted_at",
        "postedAt",
        "date_posted",
        "datePosted",
        "publication_date",
        "published_at",
        "created_at",
        "createdAt",
        "updated_at",
    ),
}


class AtsJobAdapter:
    """Converte uma vaga crua (pydantic Job ou dict) em ``Job`` normalizado."""

    def to_job(self, item: Any, company: Company) -> Job:
        """Normaliza ``item`` (dict ou modelo pydantic) para ``Job``."""
        data = self._as_dict(item)

        title = self._first(data, _FIELDS["title"]) or "Sem titulo"
        company_name = self._first(data, _FIELDS["company"]) or company.name or company.query
        url = self._first_str(data, _FIELDS["url"]) or self._url_from_slug(company)
        location = self._first_str(data, _FIELDS["location"])
        description = self._first_str(data, _FIELDS["description"])
        external_id = self._first_str(data, _FIELDS["external_id"])
        employment_type = self._first_str(data, _FIELDS["employment_type"])
        country_iso = self._first_str(data, _FIELDS["country_iso"])
        if country_iso and len(country_iso) != 2:
            country_iso = None
        # Heuristica leve: "Milwaukee, WI, us" -> country_iso "us".
        if not country_iso and location:
            tail = location.rsplit(",", 1)[-1].strip()
            if len(tail) == 2 and tail.isalpha():
                country_iso = tail.lower()
        posted_at = self._parse_dt(self._first_str(data, _FIELDS["posted_at"]))

        raw = {k: v for k, v in data.items() if k not in ("description", "raw")}
        if not raw:
            raw = None

        return Job(
            id=self._make_id(company, external_id, url),
            source=company.source,
            title=title,
            company=company_name,
            location=location,
            country=country_iso,
            url=url,
            description=description,
            internship=is_internship(title, description),
            posted_at=posted_at,
            collected_at=datetime.now(UTC),
            external_id=external_id,
            employment_type=employment_type,
            country_iso=country_iso,
            raw=raw,
        )

    @staticmethod
    def _make_id(company: Company, external_id: str | None, url: str) -> str:
        """ID estavel: ``source:external_id`` ou ``source:hash(url)``."""
        if external_id:
            return f"{company.source}:{external_id}"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return f"{company.source}:{digest}"

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        """Parse tolerante de datas (ISO 8601, ``Z`` -> ``+00:00``)."""
        if not value:
            return None
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    @staticmethod
    def _as_dict(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            try:
                return dump(mode="json")  # pydantic v2
            except TypeError:
                return dump()
        # atributos (dataclass / objeto simples)
        out: dict[str, Any] = {}
        for key in ("title", "name", "url", "company", "location", "description"):
            val = getattr(item, key, None)
            if val is not None:
                out[key] = str(val)
        return out

    @staticmethod
    def _first(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for k in keys:
            v = data.get(k)
            if v is None:
                continue
            if isinstance(v, list) and v:
                return v
            if str(v).strip():
                return v
        return None

    @classmethod
    def _first_str(cls, data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        v = cls._first(data, keys)
        if v is None:
            return None
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if str(x).strip())
            return v or None
        return str(v).strip() or None

    @staticmethod
    def _url_from_slug(company: Company) -> str:
        """Fallback de URL quando o ATS nao expoe link: careers_url + slug."""
        if company.url:
            return company.url
        return f"https://careers.{company.ats}.com/{company.slug}"
