# Arquitetura

Pipeline **orientado a empresas** (nada de busca global por keywords — a busca
global do ats-scrapers pode travar):

```
Empresa → find_company (match exato) → ATS → scraper (subprocesso + timeout)
        → AtsJobAdapter → Job (pydantic) → print/save (JSON/CSV)
```

## Modulos

| Modulo | Responsabilidade |
| --- | --- |
| `models/job.py` | `Job` pydantic — modelo canonico da vaga (qualquer ATS vira um `Job`) |
| `models/company.py` | `Company` pydantic — tenant/empresa localizado na base |
| `collectors/company.py` | `CompanyCollector` — `find_company` com selecao EXATA (slug/nome casefold; fallback token+slug) e checagem de scraper |
| `collectors/ats_scraper.py` | `collect_company` — orquestra fetch com timeout por subprocesso; `URL_SLUG_ATS` (successfactors/workday/taleo/icims usam URL como slug) |
| `collectors/greenhouse.py` | `GreenhouseCollector` — API direta do Greenhouse (exemplo de coletor fora do ats-scrapers) |
| `collectors/base.py` | `BaseCollector` (ABC) — contrato de coletor |
| `adapters/ats.py` | `AtsJobAdapter` — normaliza schema de cada ATS para `Job` (cadeias de fallback; preenche `external_id`, `employment_type`, `country_iso`, `posted_at`, `id`, `internship`) |
| `resolver/company_resolver.py` | `CompanyResolver` — fachada sobre o matching exato (compatibilidade) |
| `filters.py` | `is_internship(title, description)` — heuristica EN/PT/DE (intern, trainee, student, Werkstudent, Praktikum, iXp...) com exclusao de senior/manager/etc. |
| `cli.py` | entry point `internship-finder` (argparse) |

## Decisoes

- **Job pydantic e o modelo canonico**; `internship` e flag preenchida pelo
  adapter (heuristica), `raw` preserva o resto.
- **Matching exato** substitui a iteracao por todas as matches do
  `find_company` (evita pegar tenant parecido errado, ex.: "sap" -> asap).
- **Timeout defensivo**: cada `fetch` roda em subprocesso com teto
  (`--timeout` + margem); erro/trava vira linha FAIL e o pipeline segue.
- Multiprocessing usa o contexto default do SO (fork no Linux, spawn no
  Windows).
