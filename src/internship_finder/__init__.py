"""Pacote internship_finder: pipeline de coleta orientada a empresas.

Empresa -> find_company (match exato) -> ATS -> scraper (subprocesso +
timeout) -> adapter -> Job (pydantic) -> print/save (JSON/CSV).
"""

__version__ = "0.1.0"
