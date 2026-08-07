from __future__ import annotations

from abc import ABC, abstractmethod

from internship_finder.models.job import Job


class BaseCollector(ABC):

    @abstractmethod
    def collect(self, company: str) -> list[Job]:
        pass