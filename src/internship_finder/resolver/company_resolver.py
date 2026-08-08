"""CompanyResolver: localiza empresas na base com selecao EXATA.

O ``find_company`` do pacote faz busca por substring e pode devolver ruido
(ex.: "sap" -> asap, Casap...). A logica de matching exato (slug/nome
casefold + fallback por token corroborado pelo slug) vive no
``CompanyCollector``; o resolver e a fachada mantida para compatibilidade
(usada por scripts/test_resolver.py e por quem prefere a API "resolver").
"""

from __future__ import annotations

from internship_finder.collectors.company import CompanyCollector
from internship_finder.models.company import Company


class CompanyResolver:
    def __init__(self, limit: int = 10) -> None:
        self._collector = CompanyCollector(limit=limit)

    def resolve(self, company: str) -> list[Company]:
        """Retorna as empresas da base que casam EXATAMENTE com ``company``."""
        return self._collector.find_company(company)
