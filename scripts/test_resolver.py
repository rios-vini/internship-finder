from internship_finder.resolver.company_resolver import CompanyResolver

resolver = CompanyResolver()

companies = resolver.resolve("nvidia")

for company in companies:
    print(company)
