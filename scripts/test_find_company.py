from ats_scrapers import find_company

companies = find_company("nvidia", limit=5)

print(companies)
print()
print(companies.columns)
