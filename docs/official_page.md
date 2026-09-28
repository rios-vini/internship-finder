# Fase D — Official Page + JSON-LD Enrichment

> Status: **mergeado** — PR #87, squash `d996b13` (+ docs `1f2b715`); CI do PR
> verde ×2 no SHA `2ac4cd2` (membership `test_official_page` conferida nos
> logs de ambos) + CI main pós-merge e pós-docs verde; 0 PRs, branch
> deletada; produção `data/` intocada (A/B em /tmp).

## Objetivo

Usar a página oficial individual da vaga (`job.url`) como **segunda fonte
determinística de evidência**, principalmente para informações que o ATS não
expõe ou expõe de forma incompleta. A página oficial é **fonte de
ENRIQUECIMENTO, não de descoberta** — nenhuma vaga nova entra por aqui.

Restrições da fase (todas cumpridas): sem LLM, sem browser, sem alterar
eligibilidade/pesos/dedup/identidade, sem novo banco, sem substituir o
pipeline.

## Onde o estágio entra

```
coleta → Job → filtros (eligibilidade congela AQUI)
      → dedup → mirror-dedup (Fase C)
      → hydration (Fase A)
      → official-page enrichment (Fase D — ESTA FASE)
      → ranking → outputs
```

`src/internship_finder/official_page.py` (~660 linhas); integração no
`run_filter_pipeline` (`cli.py`) entre a hidratação e o ranking, mesma
disciplina best-effort da Fase A: falha por vaga é capturada/contada e o
pipeline segue; try externo cobre falha estrutural; **exit codes e gate de
publicação (PR #78) inalterados**. Flags: `--official-page` /
`--no-official-page` (default ligado) e `--official-page-limit N` (default
150; `0` = sem limite).

## Critérios de seleção de candidatos (spec §3)

Vaga é candidata quando: description ausente **ou** teaser (< 400 chars,
janela `TEASER_MAX_CHARS` da Fase A) **ou** sem `application_deadline` **ou**
sem `raw.salary_min/max`. Prioridade de fetch: sem description (1) > teaser
(2) > sem deadline (3) > sem salary (4); o limite corta por prioridade
(ordem original preservada — determinismo). Custo medido no probe pré-fase:
~1,4 s por GET → 150 páginas ≈ 2,5 min (run controlado documentado; budget
de segurança `OFFICIAL_PAGE_BUDGET_SECONDS = 600 s` checado entre fetchs).

## Status da página (semântica da spec × implementação)

A distinção semântica da spec é preservada com os nomes do enum
`PageStatus` que o projeto já usa (enrichment LLM), mais `mismatch`:

| Spec | `job.official_page.status` | Contador |
|---|---|---|
| page_verified | `ok` (+ `reason=redirect_target_job` quando houve redirect p/ vaga equivalente) | `pages_ok`, `redirects_target_job` |
| redirected (p/ home/search/landing) | `redirected` (`reason=redirect_target_other`) | `pages_redirect_other` |
| page_unavailable | `not_found` / `http_error` / `timeout` / `fetch_error` / `empty_content` | `pages_unavailable` |
| page_unsupported | `js_rendered` | `pages_unsupported` |
| page_mismatch | `mismatch` (`reason=jobposting_conflict`) | `pages_mismatch` |
| not_checked | vaga não candidata / cortada pelo limite | `candidates_skipped_limit` |

Registrado por vaga: `original_url`, `final_url`, `http_status`, `checked_at`,
`status`, `reason`. **`job.url` nunca é alterado.**

HTTP 200 ≠ vaga existe: `classify_page` (reuso integral do fetch LLM) confere
shell de SPA (`js_rendered`), texto mínimo (`empty_content`) e redirect cujo
conteúdo não casa com o título (`redirected`).

## JSON-LD: extração e validação

- Blocos `<script type="application/ld+json">` parseados com BeautifulSoup
  (dependência existente); blocos com JSON inválido são ignorados e contados
  (`jsonld_invalid_only`).
- Objetos `@type=JobPosting` procurados em objeto único, array, múltiplos
  objetos e `@graph` (`_iter_jobpostings`) — **nunca assume que o primeiro
  JSON-LD é a vaga**.
- Validação de correspondência (`match_jobposting`, spec §7): identifier ==
  external_id/requisition_id (forte) → URL final contém external_id/requisition_id
  (forte) → título normalizado idêntico (`normalize_title` da dedup) ou tokens
  do título da vaga presentes (≥ 0.5 via `title_match` do spike) + organização
  NÃO conflitante. Conflito forte (título radicalmente diferente ou
  identifier explicitamente diferente) → `page_mismatch`, **dado ATS
  preservado**.

## Campos extraídos (spec §8) e hierarquia de evidência FIELD-SPECIFIC

Evidência em `job["official_page"]["jsonld"]` (snake_case): `title`,
`valid_through`, `date_posted`, `salary {min,max,currency,period}`,
`employment_type`, `location {city,region,postal_code,country,street,telecommute?}`,
`description`, `identifier`, `location_relation`.

| Campo | Regra |
|---|---|
| description | Substitui **só** teaser atual quando a do JSON-LD é maior (≥ 200 chars e > atual); description ATS completa nunca é tocada; proveniência `description_source="official_page_jsonld"` |
| baseSalary | Preenche `raw.salary_min/max/currency/period` **só** quando o ATS não tem NENHUM; placeholders 0.0 (caso real softgarden) rejeitados via `_to_float_or_none` (>0) |
| validThrough | Evidência `valid_through` — **nunca** vira `application_deadline` nem se mistura com `deadline_kind` (employer_textual vs platform_sf vs página) |
| datePosted | Evidência `date_posted` — nunca altera `posted_at` |
| employmentType | Evidência complementar — **nunca** filtro/eligibilidade (enum descreve regime do contrato, não a natureza da vaga; conflito 55/72 já medido na Fase B) |
| jobLocation | Comparação de cidade via `resolve_city_key` (aliases) → `location_relation=confirmed/conflict`; localização canônica nunca muda |
| identifier | Evidência — nunca altera `external_id` |

Hierarquia geral: ATS structured > ATS description > official page JSON-LD >
futuras evidências — **por campo**, nunca global.

## Work authorization

Nenhuma interpretação semântica nesta fase: JSON-LD não traz WA estruturada
(auditoria 26/09). A detecção textual existente
(`app_intel.work_authorization`) continua sendo a fonte vigente; os casos
semânticos (international candidates, visa sponsorship, EU citizenship,
residence permit condicional) ficam para a futura fase LLM.

## Métricas (registro `type: official_page` no JSONL de métricas)

`eligible_before`, `candidates_total` (+ por motivo), `candidates_fetched`,
`candidates_skipped_limit/budget`, `http_success`, `http_errors`,
`redirects` (+ `redirects_target_job`), `pages_redirect_other`,
`pages_unavailable`, `pages_unsupported`, `pages_mismatch`, `pages_ok`,
`jsonld_found`, `jsonld_invalid_only`, `jobposting_found`,
`jobposting_matched`, `jobposting_conflict`, `descriptions_improved`,
`descriptions_unchanged`, `salaries_filled`, `salaries_unchanged_ats_wins`,
`deadlines_new`, `locations_confirmed`, `locations_conflict`,
`employment_types_found`, `duration_seconds`, `by_ats` (+ `phenom`:
candidates/jsonld/description_improved/chars antes↔depois).

## Resultado real no snapshot 28/09 (A/B, dataset produção 27/09)

- Lado A (`--no-official-page`) vs lado B (default, limite 150): **408/408
  eligible, ids e ordem idênticos, 0 diffs de score (sha256 idêntico), Top 30
  idêntico, 0 vagas alteradas fora de `official_page`**, application_deadline
  234/234, raw.salary 2/2 — dedup Fase C (4 mirrors) idêntica nos dois lados.
- B: 150 páginas tentadas em **148 s** (probe pré-fase: ~1,4 s/GET); 145
  HTTP 200; 44 redirects (12 p/ vaga equivalente; 31 p/ home — fenômeno
  phenom dominante); 12 `js_rendered` (workday/cornerstone); 101 páginas ok;
  31 com JSON-LD válido; **23 JobPosting matched** (0 conflitos);
  13 `valid_through`; 15 locations confirmadas / 8 conflitos; 23 employmentTypes.
- **Descriptions melhoradas: 0.** Razão medida: a Fase A já cobriu 100% das
  ausentes; os 29 teasers phenom não têm JSON-LD JobPosting na home de
  redirect (`/global/en`), e os demais matched já tinham description ATS
  completa (que nunca é substituída). Salários: 0 preenchidos (o único
  baseSalary estruturado do matched era placeholder 0.0).
- Impacto no ranking: **zero** (previsível — nenhum campo consumido pelo
  score mudou).

### Phenom (spec §10) — medido e encerrado nesta via

29 candidatos, 6 páginas com JSON-LD válido, 0 com JobPosting, 0 descriptions
melhoradas (7.873 chars antes = depois). **A via determinística (GET +
JSON-LD) não resolve o teaser phenom**: a página renderiza client-side e o
redirect para a home não carrega o JobPosting. Caso fica disponível para a
futura fase LLM/extraction (ou upstream, se o ats-scrapers algum dia expor
detail do phenom) — registro honesto, sem inventar dados.

## Limitações

- Cobertura limitada pelo share de ATS JS-rendered (workday, cornerstone) —
  já conhecida do enrichment LLM (JS-rendered → fora de escopo por decisão
  do dono).
- Redirect phenom → home é sistêmico: os 29 teasers phenom seguem sem
  description completa.
- 150 de 408 candidatos no primeiro run (limite da spec §3); os demais ficam
  `not_checked` para o próximo run — sem cache entre runs nesta fase
  (re-verificado a cada execução; `already_enriched` só aplica dentro do
  mesmo processo).
- `validThrough` do JSON-LD é data de validade da *página/posting*, não um
  prazo declarado pelo empregador — mantido como evidência separada.

## Custos/runtime

- 150 GETs ≈ 2,5 min (1 tentativa, timeout 10/30 s, UA identificável do
  spike); budget 600 s; 1 GET por vaga candidata por run; nenhum retry.
- Nenhum dado novo em disco: evidência vive no job dict (JSON/CSV de saída;
  CSV continua com colunas fixas — `official_page` visível só no JSON).

## Casos que ficam para a fase LLM (futura)

- Interpretação semântica de work authorization (sponsorship, EU citizenship,
  residence permit condicional etc.).
- Extração de texto fora do JSON-LD (descriptions phenom via página
  client-side — exigiria browser, fora de escopo por decisão do dono).
- Resolução dos 8 conflitos de location e dos employmentTypes conflitantes
  (evidência registrada; decisão humana/LLM futura).
