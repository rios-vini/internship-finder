from __future__ import annotations

from datetime import UTC, datetime

import requests

from internship_finder.models.job import Job


class GreenhouseCollector:

    API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"

    def collect(self, company: str) -> list[Job]:

        response = requests.get(
            self.API.format(company=company),
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        jobs: list[Job] = []

        for item in payload.get("jobs", []):

            jobs.append(
                Job(
                    id=str(item["id"]),
                    source="greenhouse",
                    title=item["title"],
                    company=company,
                    location=(item.get("location") or {}).get("name"),
                    url=item["absolute_url"],
                    description=item.get("content"),
                    internship=False,
                    posted_at=None,
                    collected_at=datetime.now(UTC),
                    raw=item,
                )
            )

        return jobs