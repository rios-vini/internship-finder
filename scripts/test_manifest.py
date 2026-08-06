import httpx
from time import perf_counter

url = "https://storage.stapply.ai/jobhive/v1/manifest.json"

print("Downloading manifest...")

start = perf_counter()

response = httpx.get(url, timeout=30)

print(response.status_code)
print(f"Time: {perf_counter() - start:.2f}s")

data = response.json()

print(data.keys())

print(data["stats"])

print()

print(data["all"])

print()

print(data["by_ats"].keys())

print()

print(data["by_ats"]["greenhouse"])

print()

print(data["by_ats"]["greenhouse"]["parquet_size_bytes"])

print()

print(data["by_ats"]["greenhouse"])