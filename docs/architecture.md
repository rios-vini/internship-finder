# Arquitetura

Pipeline **orientado a empresas** (nada de busca global por keywords — a busca
global do ats-scrapers pode travar):

```
Empresa → find_company (match exato) → ATS → scraper (subprocesso + timeout)
        → AtsJobAdapter → Job (pydantic) → filters → dedup → ranking
        → print/save (JSON/CSV)
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
| `adapters/ats.py` | `AtsJobAdapter` — normaliza schema de cada ATS para `Job` (cadeias de fallback; preenche `external_id`, `employment_type`, `country_iso`, `posted_at`, `application_deadline`, `id`, `internship`) |
| `resolver/company_resolver.py` | `CompanyResolver` — fachada sobre o matching exato (compatibilidade) |
| `filters.py` | `is_student_role(title, description)` — heuristica EN/PT/DE (intern, internship, student, Werkstudent, Praktikum, iXp...) com exclusao de senior/manager/etc. |
| `dedup.py` | deduplicacao deterministica por chave de confiabilidade (`external_id`/`id`, URL normalizada, `company+title+location`) |
| `ranking.py` | ranking por perfil: `score_job` (score + breakdown) e `rank_jobs`, ordem deterministica |
| `metrics.py` | metricas de execucao em JSONL (payload por tenant + resumo do run, com `error_code`) |
| `errors.py` | `CollectionError` + codigos de erro estruturados (classificador para o payload da queue e `error_code` no JSONL) |
| `health.py` | relatorio de health por tenant/ATS sobre o JSONL (drop de cobertura, erros recorrentes) + alertas |
| `geocoding.py` | fallback de pais por cidade (`INTERNSHIP_FINDER_GEOCODING`, cache-first; OFF por default; integrado no adapter depois de `infer_country_iso`) |
| `storage/sqlite_store.py` | `SqliteStore` — historico por vaga (`first_seen`/`last_seen`/`active`/`archived`) via `sqlite3` stdlib; flag `--sqlite PATH` |
| `cli.py` | entry point `internship-finder` (argparse) |

## Decisoes

- **Job pydantic e o modelo canonico**; `internship` e flag preenchida pelo
  adapter (heuristica), `raw` preserva o resto. `application_deadline`
  (`datetime|None`) e preenchido pelo adapter **quando o ATS expoe a data
  explicitamente** (ex.: SAP via `ats-scrapers` `ae0ad53`) e **nunca** e
  inferido de `posted_at`.
- **Matching exato** substitui a iteracao por todas as matches do
  `find_company` (evita pegar tenant parecido errado, ex.: "sap" -> asap).
- **Timeout defensivo**: cada `fetch` roda em subprocesso com teto
  (`--timeout` + margem); erro/trava vira linha FAIL e o pipeline segue.
- Multiprocessing usa o contexto default do SO (fork no Linux, spawn no
  Windows).
