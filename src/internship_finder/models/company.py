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
        """Identificador composto do TENANT ATS usado como ``Job.source``.

        Representa a ORIGEM TECNICA da vaga (coleta/troubleshooting), NAO a
        identidade da empresa: o mesmo tenant pode ser compartilhado por varias
        empresas (ex.: ``successfactors:jobs`` cobre SAP/ZF/Kaufland/...;
        ``phenom:nan`` cobre DHL/Allianz/Merck/...). A identidade empresarial
        da vaga e o campo ``company`` do Job (P1.1).
        """
        return f"{self.ats}:{self.slug}"
