from ats_scrapers import find_company

from internship_finder.models.company import Company


class CompanyResolver:

    def resolve(self, company: str) -> list[Company]:

        df = find_company(company, limit=20)

        companies = []

        for _, row in df.iterrows():

            companies.append(
                Company(
                    name=row["name"],
                    ats=row["ats"],
                    slug=row["slug"],
                    url=row["url"],
                )
            )

        return companies
