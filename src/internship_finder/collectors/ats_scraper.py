from ats_scrapers import find_company, get_scraper_for_url


def collect_company(company: str):
    matches = find_company(company, limit=10)

    if matches.empty:
        print(f"Company not found: {company}")
        return []

    jobs = []

    for _, row in matches.iterrows():
        ats = row["ats"]
        url = row["url"]

        print(f"Trying {company} -> {ats}")
        print(f"  URL: {url}")

        try:
            scraper = get_scraper_for_url(url)
            company_jobs = scraper.fetch()

            print(f"  Found {len(company_jobs)} jobs")
            jobs.extend(company_jobs)

        except Exception as e:
            print(f"  Failed: {e}")

    return jobs
