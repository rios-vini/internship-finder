from ats_scrapers import search


jobs = search(
    query="intern",
    ats="greenhouse",
    limit=10,
)

print(jobs.head())
