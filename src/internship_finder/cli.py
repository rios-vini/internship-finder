from internship_finder.collectors.ats_scraper import collect_company


def main():
    jobs = collect_company("NVIDIA")

    print(f"\nTotal jobs: {len(jobs)}")

    for job in jobs[:10]:
        print(job.title)
        print(job.location)
        print(job.url)
        print("-" * 80)


if __name__ == "__main__":
    main()
