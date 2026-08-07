from ats_scrapers import find_company
from ats_scrapers.scrapers import get_scraper

print("Finding company...")

companies = find_company("stripe", limit=1)

row = companies.iloc[0]

ats = row["ats"]
slug = row["slug"]

print(f"ATS: {ats}")
print(f"Slug: {slug}")

print("\nCreating scraper...")

scraper = get_scraper(ats, slug)

print(f"Scraper: {scraper}")

print("\nFetching jobs...")

jobs = scraper.fetch()

print(f"\nFound {len(jobs)} jobs\n")

for job in jobs[:5]:
    print(job)
    print("-" * 80)
