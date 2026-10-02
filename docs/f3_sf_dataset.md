# F3 — SF dataset como fonte primária, registry como lista de interesse

**Data:** 2026-10-02 · **Branch:** `feature/f3-sf-dataset` (base `main` `b282d09`) ·
**Status:** implementado; A/B de não-regressão executado (números abaixo)

## O que mudou (a inversão arquitetural)

Antes da F3, o fluxo era: **registry de 101 empresas** (lista de existência)
→ coleta per-tenant via scrapers do `ats-scrapers` → funil. Uma vaga só
existia se a empresa estivesse no registry. O dono pediu a inversão:

1. **Fonte nova `sf_dataset`** (módulo
   `src/internship_finder/dataset_source.py`): consome o dataset HOSPEDADO
   do `ats-scrapers` (Cloudflare R2, manifest público
   `https://storage.stapply.ai/jobhive/v1/manifest.json`, atualização
   diária ~05h UTC, sem API key — 5,1M jobs / 80.390 empresas / 63 fontes)
   com **prefilter em streaming** (DE + estágio) ANTES de materializar
   qualquer `Job`. As rows sobreviventes (~21,6k medidas) viram `Job` e
   entram no MESMO funil filtros → dedup → hidratação → ranking.
2. **Registry deixa de ser filtro e vira lista de interesse**: componente
   novo `registry` no `Score.breakdown`
   (`ranking.WEIGHT_REGISTRY_INTEREST = +1.0`). Vaga de empresa FORA do
   registry entra no eligible normalmente — só perde o desempate. O peso é
   aditivo e determinístico (invariante §7.1: único delta permitido no
   ranking).
3. **CLI**: `--dataset` (BooleanOptionalAction; default ON no modo
   `--registry`, OFF no `--companies` explícito; `--no-dataset` reverte) e
   `--dataset-budget-secs` (default 1800). O `refresh_daily.py`
   `collection_command()` passa `--dataset` explicitamente — o cron não
   muda (chama o refresh sem flags de coleta; conferido no código).
4. **Hidratação sob demanda adaptada** (`hydration.py`): para jobs
   `sf_dataset:<ats>`, o ATS efetivo é o SUFIXO do source
   (`_effective_ats`) e o slug de hidratação é derivado da URL da vaga
   (`_slug_from_url`): workday pela regex existente, smartrecruiters pelo
   primeiro segmento do path (`jobs.smartrecruiters.com/<slug>/...`),
   personio pelo label do host (`<tenant>.jobs.personio.<tld>` →
   `<tenant>`), eightfold pelo hostname. Não derivável →
   `unsupported_no_detail` (vaga preservada, contada — mesmo contrato).
   Nunca scraper com slug inventado.

## Por que NÃO `Client.search()` (fatos medidos, não opinião)

O pacote expõe `Client.search()`, mas ele é INVIÁVEL como mecanismo de
ingestão (medido ao vivo, §2 da spec):

- filtra CLIENT-SIDE sobre um DataFrame materializado; params: `query`
  (substring literal no título), `location`, `company`, `ats`, `remote`,
  `salary_*`, `experience_max`, `limit`. **Não existe `country_iso`** (é
  coluna do schema, não filtro) e "estágio" não é expressável de forma
  confiável;
- `load(ats=...)` materializa a fatia por-ATS INTEIRA em RAM (BytesIO →
  DataFrame); full snapshot = 16,8 GB; o venv de produção não tem pyarrow
  (parquet);
- `by_date` está VAZIO no manifest vivo — não há delta diário publicado.

A borda correta é: manifest público + fatias por-ATS (CSV) + streaming
(`csv.DictReader`) com prefilter linha a linha. Pico de disco = maior fatia
(workday 4,6 GB); cada fatia é apagada logo após o prefilter (nunca
acumula).

## Design da fonte (`dataset_source.py`)

- `fetch_manifest()` → `by_ats` (63 fontes; TODAS processadas por default,
  ordenadas — sem allowlist manual; fontes com 0 rows DE+intern custam só
  o download da fatia pequena).
- Por fatia: download streaming em disco (urllib stdlib, chunks de 1 MiB)
  → prefilter (título com marcador de estágio
  `filters.STUDENT_TYPE_PATTERNS`; SEM exclusões
  `TYPE_EXCLUSION_PATTERNS`+`PROGRAM_EXCLUSION_PATTERNS`; DE por
  `country_iso == "de"` OU location `\bDE\b|deutschland|germany`) →
  `row_to_job` → unlink da fatia.
- Identidade (P1.1 preservada): `id = "<company>|sf_dataset:<ats_type>:<ats_id>"`
  (hash sha1 16-hex da URL quando `ats_id` ausente — mesma regra do
  `AtsJobAdapter._make_id`); `source = "sf_dataset:<ats_type>"`. O escopo
  company+source distingue o job do dataset da vaga equivalente da coleta
  do registry: o colapso cross-fonte acontece no `deduplicate()` pela
  chave URL (b) naturalmente (fato §2.7: 0 divergências de company nos 413
  overlaps; `deduplicate()` zero-change).
- `raw` é o contrato: row inteira MENOS `description` (padrão do adapter).
- Row sem company/title/url → SKIP com contador `invalid_rows` (nunca
  crash, nunca Job fabricado).
- Budget `DATASET_BUDGET_SECONDS = 1800` checado ENTRE fatias; estourado →
  fatias restantes viram `skipped_budget` e o run segue.
  `DATASET_HTTP_TIMEOUT = 120s` por request.
- Falha do dataset NUNCA derruba o run: log + registro JSONL
  `type: dataset` com `status: failed`; exit code segue a regra do
  registry (dataset failed NÃO gera exit 2).

## Peso de registry no ranking (`ranking.py`)

- `WEIGHT_REGISTRY_INTEREST = +1.0`, componente `registry` no breakdown.
- Match: `Job.company` casefold == nome canônico do registry OU nome
  canônico é SUBSTRING do company (casefold). O dataset traz nomes legais
  ("Robert Bosch GmbH" vs registry "Bosch"; "MAHLE International GmbH" vs
  "Mahle"). Substring casefold: FN barato > FP caro (decisão §4.2).
- Nomes vêm de `CompanyRegistry().entries` (lazy singleton, computado
  uma vez por processo) — a MESMA fonte de verdade da coleta.
- **NÃO é filtro**: vaga fora do registry entra no eligible e no ranking
  normalmente, só com −1.0 relativo (na prática, desempate).

## Decisões e invariantes (§7)

1. **Registry-only byte-idêntico**: `--no-dataset` + caminho filtro
   seguem com zero mudança de comportamento em
   filters/dedup/mirror/countries/heurísticas; o ÚNICO delta no ranking é
   o componente `registry` (+1.0 aditivo, determinístico — testes D4/H1).
2. `Job.id` de jobs do registry: inalterado (prefixo company|source do
   tenant REAL).
3. Produção `data/` intocada (A/B §6.4: md5 iguais antes/depois).
4. Cron/exit codes/publish gate `publication_allowed`: inalterados.
5. `raw` preservado (menos description, padrão do adapter).
6. Testes 100% offline (nenhum request de rede; CI runner limpo).
7. Cron não editado: `collection_command()` é código do repo e ganha
   `--dataset` explicitamente (conferido: o cron chama
   `refresh_daily.py` sem flags de coleta).
8. **SQLite/lifecycle**: jobs do dataset NÃO entram no lifecycle — só as
   unidades de coleta do registry (`collection_units`) persistem. Decisão:
   a fonte dataset é EFÊMERA, re-derivada a cada run (21,6k rows do
   zero); arquivar first_seen/last_seen para jobs que renascem a cada
   run poluiria o histórico sem ganho (o lifecycle existe para detectar
   vagas que DESAPARECEM da coleta do registry — fenômeno que não existe
   numa fonte re-derivada). Documentado aqui e no relatório da fase.
9. **Mirror-dedup**: candidato = mesma company + MESMO `source` + mesmo
   `requisition_id`. Jobs dataset têm `source = "sf_dataset:<ats>"` ≠
   tenant sources → a chave nunca casa cross-fonte (teste C3).
10. `deduplicate()` intocado (zero-change); o colapso cross-fonte
    acontece pela chave URL naturalmente.

## A/B de não-regressão (números; método §6)

Snapshot de produção PRE-cron 02/10 (`data/archive/20261002T090001Z/jobs.json`,
73.074 jobs — o cron das 09:00 UTC regravou `data/jobs.json` DURANTE o A/B;
usar o arquivo arquivado torna o A/B reprodutível) + dataset prefilterado
das 63 fatias (arquivos baixados pelo orquestrador em
`~/.hermes/cache/scratch/f3-probe/`, 18 GB — pipeline idêntico ao de
produção, só a origem das fatias muda). Flags offline:
`--no-hydrate-descriptions --no-official-page`.

| Métrica | Valor |
|---|---|
| Dataset rows lidas (63 fatias) | 5.812.369 |
| Dataset rows prefilteradas (DE+estágio) | **22.256** |
| Rows inválidas (sem company/title/url) | 0 |
| Dataset Jobs criados | 22.256 |
| Bytes lidos (fatias locais) | 18,0 GB |
| Duração do estágio dataset | 781s (~13 min; probe sem rede) |
| Eligible A (registry-only, recomputado offline) | **475** (= baseline produção) |
| Eligible B (com dataset) | **2.168** |
| Novos eligible vindos do dataset | **+1.740** |
| Empresas novas no eligible | **768** |
| Overlaps dataset×produção (bruto, company+URL) | 2.101 |
| Overlaps no nível ELIGIBLE (dataset eligible com twin registry) | 45 (+2 ABB pela chave (c)) — análogo aos ~413 do orquestrador no universo pós-funil bruto |
| Targets no eligible B: Deloitte WP / AGCO / Levio | **24 / 16 / 8** ✓ (critério §6.3) |
| md5 data/ antes == depois | ✓ (contra o snapshot pós-cron) |

**Braço A == baseline main**: 475 eligible, mesma ordem determinística,
invariante aditiva job-a-job (breakdown.registry == registry_interest(company)
para todos; ordem intra-registry invariante ao subtrair +1.0).

**Braço B ⊇ A, com 47 colapsos cross-fonte legítimos**: 45 vagas do registry
têm twin no dataset com a MESMA URL (chave (b)) e o vencedor foi o job do
dataset (regra `_prefer`: tem description — fato §2.4, successfactors 100%);
2 ABB colapsaram pela chave (c) (company+title+location; "abb" vs "Abb" —
workday normaliza o case do nome). Vaga preservada, apenas o id muda de
fonte. Nenhuma duplicata residual no eligible B (verificado por chaves).

Amostra manual de 5 overlaps (spec §6.1c): Bayer ×5 (talent.bayer.com,
mesma URL/título — Werkstudent KI & Data Engineering, PPS Engineer, etc.) —
colapso correto pela chave URL.

## Limitações conhecidas (declaradas)

- **Bundesagentur sem description** (0% na fatia; board federal, espelhos
  sem description): rows entram SEM description e a hidratação as marca
  `unsupported_no_detail` (bundesagentur ∉ mapa de detail da 0.3.0) —
  honesto; `raw` preserva tudo.
- **Description embutida ~75% dos candidatos eligible** (fato §2.4):
  successfactors/smartrecruiters/workday/join_com/welcometothejungle/eures
  100%, greenhouse/recruitee/softgarden/cornerstone/amazon/tiktok 100%,
  bundesagentur 0%.
- `Client.search()` inviável (acima); `by_date` vazio (sem delta diário);
  pyarrow ausente no venv de produção (parquet fora).
- Hidratação de jobs sf_dataset depende do slug derivável da URL;
  workday/smartrecruiters/personio/eightfold cobertos, o resto vira
  `unsupported_no_detail` (vaga preservada).
- FN/FP do componente registry: substring casefold pode gerar FP raro
  (benigno: +1.0 a mais) e o critério é deliberadamente barato em FN.

## Testes (`scripts/test_f3.py`, 47º script do CI)

73 checks em 10 grupos (A prefilter, B row→Job, C dedup cross-fonte +
mirror, D peso registry, E hidratação sf_dataset, F CLI defaults/falha,
G budget, H registry NÃO-filtro, I JSONL, J membership CI). 100% offline
(fixtures CSV sintéticas; download injetado). O commit que adiciona o
teste edita o array `tests=(...)` do `ci.yml` no MESMO commit.
