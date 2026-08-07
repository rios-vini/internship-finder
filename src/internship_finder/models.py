from dataclasses import dataclass


@dataclass
class Job:
    title: str
    company: str
    location: str | None
    url: str
    description: str | None = None
    ats: str | None = None
