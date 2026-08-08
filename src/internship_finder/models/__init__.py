"""Modelos canonicos do internship-finder (pydantic).

O pipeline coleta vagas de ATSes diferentes e normaliza tudo para estes
modelos (``Job`` e ``Company``), independentes do schema de cada ATS.
"""

from internship_finder.models.company import Company
from internship_finder.models.job import Job

__all__ = ["Company", "Job"]
