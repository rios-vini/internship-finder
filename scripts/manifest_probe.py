"""Probe manual do manifest do ats-scrapers — NAO e um teste automatizado.

Consulta o manifest externo (storage.stapply.ai) e imprime estatisticas do
acervo de empresas/ATS servido pelo pacote ats-scrapers. Sem assertions, sem
uso no CI: e uma verificacao manual/operacional para conferir a acessibilidade
do manifest e inspecionar rapidamente as stats expostas (total, por ATS,
tamanho dos parquet, etc.).

Uso:  python scripts/manifest_probe.py
"""

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