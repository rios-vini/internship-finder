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
| `adapters/ats.py` | `AtsJobAdapter` — normaliza schema de cada ATS para `Job` (cadeias de fallback; preenche `external_id`, `employment_type`, `country_iso`, `posted_at`, `application_deadline`, `id`, `internship`) |
| `resolver/company_resolver.py` | `CompanyResolver` — fachada sobre o matching exato (compatibilidade) |
| `filters.py` | `is_student_role(title, description)` — heuristica EN/PT/DE (intern, internship, student, Werkstudent, Praktikum, iXp...) com exclusao de senior/manager/etc. |
| `countries.py` | país/localização — `COUNTRY_CODES`, `EUROPE_COUNTRIES`, `COUNTRY_NAMES`, `infer_country_iso`, `parse_country_spec` (extraído de `filters.py` no P2 #12; `filters.py` re-exporta os símbolos) |
| `dedup.py` | deduplicacao deterministica por chave de confiabilidade (`external_id`/`id`, URL normalizada, `company+title+location`) |
| `ranking.py` | ranking do perfil principal: `score_job` (score + breakdown) e `rank_jobs`, ordem deterministica |
| `materials_ranking.py` | ranking do perfil secundário (Fase 4): `materials_score_job` + `rank_materials_jobs` — MESMAS vagas elegíveis, score/breakdown próprios, independentes do principal |
| `ptbr.py` | camada PT-BR (Fase 5): glossário determinístico (`title_pt`), `detect_language`, `employment_type_pt`, `country_label`, `relevance_signals`/`penalties` — só apresentação; nunca toca score/ranking |
| `app_intel.py` | Application Intelligence (Fase 6): `german_level` (exigência de alemão por EVIDÊNCIA no texto), `english_evidence`, `work_authorization` (5 estados, só com evidência), `deadline_kind` (empregador vs. validade do feed SuccessFactors vs. ausente), `urgency_color`, `candidate_fit`, `possible_problems`, `quality_flags`, `application_readiness` — funções puras e determinísticas; alimenta ranking (componente language) e interface |
| `metrics.py` | metricas de execucao em JSONL (payload por tenant + resumo do run, com `error_code`) |
| `errors.py` | `CollectionError` + codigos de erro estruturados (classificador para o payload da queue e `error_code` no JSONL) |
| `health.py` | relatorio de health por tenant/ATS sobre o JSONL (drop de cobertura, erros recorrentes) + alertas |
| `geocoding.py` | fallback de pais por cidade (`INTERNSHIP_FINDER_GEOCODING`, cache-first; OFF por default; integrado no adapter depois de `infer_country_iso`) |
| `registry.py` | `CompanyRegistry` — fonte única das 101 empresas de coleta em código (`SEED` + `enabled`; P2 #13; estado derivado do JSONL via `company_status`) |
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
- **Publicacao em GitHub Pages (Fase 1, 18/09)**: o refresh diario reusa
  `scripts/interface.py` para gerar o HTML do ranking e o publica na branch
  `gh-pages` via `scripts/publish_pages.py` (clone de deploy fora do repo,
  escrita atomica de `index.html`, commit+push; so com coleta ok e `eligible >
  0`). Decisao de reuso: o HTML local e a pagina publica sao o MESMO artefato
  — sem frontend novo, sem servidor, sem dependencias novas. Nenhum dado
  interno e publicado: gate `check_public_safe` (tokens/caminhos privados)
  antes do push.
- **Dois perfis, um pipeline (Fase 4, 19/09)**: o conjunto elegivel alimenta
  DOIS rankings independentes — `ranking.py` (perfil principal) e
  `materials_ranking.py` (Materials Engineering). `score`/`score_breakdown`
  do principal NUNCA mudam (o perfil secundario adiciona
  `materials_score`/`materials_breakdown`, nunca soma os dois). Nenhuma
  alteracao de elegibilidade/coleta/dedup: o segundo perfil responde apenas
  "entre as vagas ja elegiveis, quais sao mais relevantes para Materials?".
  A interface (`scripts/interface.py`) mostra os dois rankings com seletor de
  perfil (abas) na mesma pagina.
- **Camada PT-BR de apresentacao (Fase 5, 19/09)**: `ptbr.py` traduz o
  TITULO de forma deterministica por glossario (campo separado "PT-BR"; o
  original permanece com tag "Original (EN/DE)"), rotula tipo do anuncio e
  pais em portugues e explica cada componente REAL do breakdown do perfil
  ativo em PT-BR (inclusive penalidades). NAO traduz descricao, NAO usa
  LLM/API/servico externo e NAO altera score/ranking/filtros/dedup — apenas
  a apresentacao. Como adicionar termos: editar `GLOSSARY` em `ptbr.py`
  (frase composta antes da generica; identidade `frase_pt=None` protege
  nomes de produto).
