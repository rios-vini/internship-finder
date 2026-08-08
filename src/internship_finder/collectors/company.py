"""CompanyCollector: localiza empresas na base do ats-scrapers com selecao EXATA.

O ``find_company`` do pacote faz busca por substring (case-insensitive) e
pode devolver ruido (ex.: "sap" -> asap, Casap, Sapien). Para nao pegar
empresa parecida errada, este coletor refiltra os candidatos com regras
estritas:

1. ``exact``: slug ou nome igual (casefold) a consulta.
2. ``token`` (fallback, so se nao houver match exato): algum token do nome
   (separado por nao-alfanumerico) e igual a consulta E a consulta e um
   segmento inteiro do slug. Ex.: "bosch" -> "Bosch Group"/slug "BoschGroup"
   casa; "Grabosch Media GmbH" e "Boschman Advanced Packaging" nao casam.
"""

from __future__ import annotations

import logging
import re

from ats_scrapers import find_company as ats_find_company
from ats_scrapers.scrapers import ScraperRegistry

from internship_finder.models.company import Company

log = logging.getLogger(__name__)

_SPLIT_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _name_tokens(name: str) -> set[str]:
    return {t for t in _SPLIT_NON_ALNUM.split(name.casefold()) if t}


def _slug_segments(slug: str) -> set[str]:
    parts = _CAMEL.split(slug)
    return {t for t in _SPLIT_NON_ALNUM.split(" ".join(parts).casefold()) if t}


class CompanyCollector:
    """Wrapper do find_company com selecao exata e checagem de scraper."""

    def __init__(self, limit: int = 10) -> None:
        self.limit = limit

    def find_company(self, name: str) -> list[Company]:
        """Retorna as empresas da base que casam EXATAMENTE com ``name``."""
        q = name.strip()
        if not q:
            return []
        qf = q.casefold()
        try:
            rows = ats_find_company(q, limit=self.limit)
        except Exception as exc:  # rede/parse: nao derruba o pipeline
            log.error("find_company(%r) falhou: %s", q, exc)
            return []

        exact: list[Company] = []
        for row in rows.itertuples(index=False):
            slug = str(getattr(row, "slug", "") or "")
            rname = str(getattr(row, "name", "") or "")
            if slug.casefold() == qf or rname.casefold() == qf:
                exact.append(self._build(row, q, "exact"))

        candidates = exact if exact else self._token_fallback(rows, q, qf)
        return self._dedupe(candidates)

    def _token_fallback(self, rows, q: str, qf: str) -> list[Company]:
        """Fallback: token do nome exato + corroboracao pelo slug."""
        out: list[Company] = []
        for row in rows.itertuples(index=False):
            slug = str(getattr(row, "slug", "") or "")
            rname = str(getattr(row, "name", "") or "")
            if qf in _name_tokens(rname) and qf in _slug_segments(slug):
                out.append(self._build(row, q, "token"))
        return out

    def _build(self, row, query: str, kind: str) -> Company:
        return Company(
            name=str(getattr(row, "name", "") or ""),
            ats=str(getattr(row, "ats", "") or ""),
            slug=str(getattr(row, "slug", "") or ""),
            url=str(getattr(row, "url", "") or "") or None,
            query=query,
            match_kind=kind,
        )

    @staticmethod
    def _dedupe(companies: list[Company]) -> list[Company]:
        seen: set[tuple[str, str]] = set()
        out: list[Company] = []
        for c in companies:
            key = (c.ats, c.slug)
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def has_scraper(self, company: Company) -> bool:
        """True se existe scraper registrado para o ATS da empresa."""
        return ScraperRegistry.has_scraper(company.ats)
