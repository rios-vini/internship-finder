# F30 — Fontes keyless nicho: Amazon search.json + Jobmensa sitemap + ABSOLVENTA/Praktikum.info

**Data:** 13/10/2026 · **Branch:** `feature/f30-niche-sources` · **Status:** PR aberto (sem merge — decisão exclusiva do dono)

## Objetivo

Diversificar a coleta além do dataset ats-scrapers de terceiro (~70% do eligible; risco de concentração — SAP já ficou 8 dias fora). Quatro fontes candidatas keyless, no padrão F21 (`research_sources.py`): adapters diretos, fail-soft, 1 fetch/dia, prefilter DE+estágio ANTES de materializar reusando as funções existentes, dedup delegado ao estágio existente.

## §0 Gate anti-violação — robots.txt por fonte (verificado 13/10, UA honesto `internship-finder-research/1.0`)

| Fonte | robots.txt | Veredicto |
|---|---|---|
| amazon.jobs | `User-agent: *` → Disallow só de `/internal*` (12 variantes de locale); sem Crawl-delay | **LIBERADO** — `/en/search.json` fora de qualquer Disallow |
| jobmensa.de | `User-Agent: *` → `Allow: /`; **o próprio robots anuncia `Sitemap: https://www.jobmensa.de/sitemaps/jobsearch_jobs.xml.gz`**; sem Crawl-delay | **LIBERADO** — o sitemap é o canal que o site QUER que seja lido |
| absolventa.de | `User-agent: *` → Disallow só de `/p/formular-zur-meldung-von-rechtswidrigen-inhalten` | **LIBERADO** — `/jobs/*` livre |
| praktikum.info | idem absolventa (mesma plataforma) | **LIBERADO** — `/stellenangebote` livre |

Proibidos por spec (XING, LinkedIn, Indeed, Stepstone): não tocados. Zero browser/headless no pipeline (lição Kununa preservada).

## §1 Probes ao vivo (1–2 requests/fonte, UA honesto, fixtures em /tmp/f30-probes)

- **amazon.jobs** `GET /en/search.json?offset=0&result_limit=10&sort=recent` → 200, schema `{"jobs": [...], "hits": ...}`. Com `normalized_country_code[]=DEU`: **704 vagas DE**. Fatos medidos:
  - `result_limit=100` honrado (500 em 5 páginas).
  - Filtro server-side de estágio **NÃO existe**: `category[]=internship` → 0 resultados; `is_intern=1` → ignorado (hits=10000). O campo `is_intern` vem **None** por item. → prefilter client-side no título (reuso integral de `row_is_intern_candidate`).
  - `country_code` é **alpha-3** ("DEU") — `is_country_row("DEU", ...)` = **False** medido (prefilter/funil só conhecem alpha-2). Adapter converte DEU→de (mapa `_AMAZON_ALPHA3_TO_ISO`).
  - `description` inline completa; `company_name` é a entidade legal real ("Amazon Logistik Winsen GmbH", "Amazon EU SARL (Germany Branch) - D70"…).
- **jobmensa.de** `GET /sitemaps/jobsearch_jobs.xml.gz` → 200, 53 KB, **1781 URLs de vagas** (`/jobs/ex/...`, `/jobs/in/...`, `/jobs/<slug>`). Detail (probe de 2 URLs) tem JSON-LD JobPosting completo (title/description/hiringOrganization=jobvalley/jobLocation DE), ~140 KB/página — detail em massa fora do budget; sem lastmod por URL.
- **absolventa.de** `GET /jobs?query=...` → a query é **ignorada server-side** (IDs idênticos para "supply chain" e "praktikum" — medido). O caminho certo é o filtro de **positions**: checkbox `positions[]=praktikum` (2.554 jobs) e `positions[]=werkstudent`; e os **canais** por área: `/jobs/channel/materialwirtschaft` (Einkauf/Logistik — o nicho exato do projeto) com **91 jobs** nas positions combined. Cards HTML estáveis (`teaser_job_offer_<id>`, `<h2>` título, empresa no `<span>`/alt, CEP+cidade). Paginação `page=N` (20 cards/página).
- **praktikum.info** — MESMA plataforma ("uno") e MESMA DB da ABSOLVENTA: IDs de card **idênticos 18/20** entre os boards, mesmos assets `uno-production.imgix.net`, badge 2.473 ⊂ 2.554. O path `/praktikum/angebote` **ignora o param `page`** (overlap 20/20 medido page1×page2); a paginação real vive em `/stellenangebote?page=N`.

## §2 Adapters (padrão F21)

Registrados em `RESEARCH_SOURCE_ORDER` (10 fontes; orçamento de 300 s mantido — soma medida F30 ≈ 27 s):

| Fonte | Endpoint | Requests/dia | Cap | Prefilter |
|---|---|---|---|---|
| `amazon_jobs` | `/en/search.json?...&normalized_country_code[]=DEU` | 5 (offset 0..400, sort=recent) | 100/página | título (`row_is_intern_candidate`) + DE (`is_country_row` via DEU→de) |
| `jobmensa` | `/sitemaps/jobsearch_jobs.xml.gz` | 1 | sitemap inteiro | slug do último segmento (`row_is_intern_candidate`) |
| `absolventa` | `/jobs/channel/materialwirtschaft?positions[]=praktikum&positions[]=werkstudent&page=N` | ≤5 | 20 cards/página | título do `<h2>` |
| `praktikum_info` | `/stellenangebote?positions[]=...&page=N` | ≤5 | 20 cards/página | idem (adapter existe; **default OFF**) |

- Id estável: `<company>|<source>:<external_id>` (Amazon: `id_icims`; uno: card id; Jobmensa: sha16 da URL do sitemap — mesma regra do `AtsJobAdapter`).
- Fail-soft integral: falha de fetch/parse → `[]` + registro `status: failed` no summary (o run NUNCA cai; testes E2/E6/E7).
- Zero HTTP na suíte (openers injetáveis, padrão test_f21).

Bugs encontrados e corrigidos durante a validação viva (todos com teste):
1. `urlencode` de lista **precisa de `doseq=True`** — sem ele `positions[]` virava a string literal `['praktikum', 'werkstudent']` e a ABSOLVENTA devolvia o board sem filtro → 0 jobs (teste D7 trava a serialização correta).
2. Cards da página 3+ da plataforma uno usam sufixo `-b-` (páginas 1–2: `-p-`) — regex aceita `[a-z]` (teste C6).
3. Praktikum.info pagina em `/stellenangebote`, não em `/praktikum/angebote`.

## §5 A/B offline contra cópia do snapshot (13/10 09:21 UTC, produção intocável — mtime/size/inode antes×depois idênticos)

Snapshot: `data/eligible_jobs.json` de 12/10 (**783 eligible**), copiado para `/tmp/f30-ab/`. Fontes rodadas UMA vez:

| Fonte | Raw do board | Kept (prefilter) | Eligible (funil completo) | Novas vs snapshot | Observações |
|---|---|---|---|---|---|
| `amazon_jobs` | 500 (5 págs) | **100** | **81** | **81** (0 overlap) | 4 werkstudent_puro; área mantém 85 |
| `jobmensa` | 1785 URLs | 187 | **0** | 0 | 22 sobrevivem de área, **100% Werkstudent puro** → mortos pela aplicabilidade F18 |
| `absolventa` | 78 (canal materialwirtschaft) | 78 | **49** | 48 (1 colapsa) | 1 thesis_title, 2 werkstudent_puro |
| `praktikum_info` | 100 | 100 | 23 | 23 | **16/23 external_id idênticos** à ABSOLVENTA |

- Novas únicas vs snapshot: **152 → 137 após dedup interno** (15 colapsadas cross-fonte pela chave (c) company+title+location — ABSOLVENTA×Praktikum.info principalmente).
- Overlap geral com o snapshot existente: 1 vaga (ABSOLVENTA) — as fontes são **aditivas de verdade** (diversificação real, não re-contagem).

## §6 Honestidade — defaults OFF com evidência

Duas fontes entram **DESLIGADAS por default** (`F30_DEFAULT_OFF_SOURCES`; env CSV continua o kill switch por cima; religar = remover 1 linha):

- **`jobmensa` — zero-yield estrutural.** O board é da agência jobvalley (Studitemps): emprega o estudante e o coloca em clientes; não há Praktikum direto. 187 vagas passam no prefilter de estágio, 22 sobrevivem ao filtro de área e **100% delas são Werkstudent puro por título** — exatamente o que a aplicabilidade F18 exclui (exige matrícula em universidade alemã). 0 eligible num run completo. Não é acidente de safra; é a natureza do board. Evidência: A/B 13/10 acima.
- **`praktikum_info` — duplicata estrutural.** Mesma plataforma/DB da ABSOLVENTA (IDs 18/20 idênticos, badge 2.473 ⊂ 2.554). A dedup existente **não** colapsa cross-host de forma confiável (chave (a) escopada por source; chave (b) por host; só a (c) salva, e nem toda vaga tem location) — ligar as duas = dupla contagem. O adapter existe para o caso da ABSOLVENTA sair do ar / divergirem.

## Resultado vs critério de aceitação

- **≥2 fontes funcionando com números reais**: `amazon_jobs` (81 eligible novos) + `absolventa` (48 novas) — **2 fontes ON por default**, ambas com números medidos acima. ✅
- **Robots verificado por fonte**: tabela §0. ✅
- **Suíte verde**: 68º script `test_f30.py` (43 checks) no CI, mesmo commit. ✅
- **PR aberto, sem merge** (exclusivo do dono). ✅

## Notas operacionais

- Janela 09:00–09:15 UTC respeitada: todos os fetchs pesados correram fora dela (último A/B às 09:21–09:23).
- A soma viva das 4 fontes é ~27 s (amazon 11,5 s; jobmensa 0,8 s; absolventa 7,6 s; praktikum_info 7,4 s) — dentro do orçamento de 300 s com folga.
- `praktikum_info` default OFF significa custo real hoje: amazon (5 req) + absolventa (≤5 req) = ~10 requests/dia novos.
- Não alteramos nada da coleta existente (registry/dataset/direct_fetch/refresh); nenhum payload de vaga commitado (fixtures do teste são snippets mínimos verbatim).
