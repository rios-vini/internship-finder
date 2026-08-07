from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source: str

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

    raw: dict[str, Any] | None = None