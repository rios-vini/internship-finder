# Fase I — SAP Source Recovery (relatório §15)

**Status**: mergeado via PR #92 | **Data**: 2026-09-29 | **Base**: main `f27131a` (Fase H docs) sobre `e807c08` (Fase G)
**Escopo**: recuperação EXCLUSIVA da fonte SAP. Ranking/score/weights/eligibility/student_type/salary/WA/hydration/official_page/LLM/Telegram/cron/publication gate/dedup/mirror dedup: NÃO tocados.

---

## 1. Causa-raiz do outage SAP

O portal público de carreiras da SAP foi reconstruído: `jobs.sap.com` — historicamente o site RMK (Recruiting Marketing) da SuccessFactors — virou um **board Next.js novo** que não expõe o feed RSS legacy em `/sitemal.xml` (retorna **404 HTML**, página `__next_error__`). Como o scraper SuccessFactors 0.3.0 busca exatamente `https://<host-careers>/sitemal.xml` quando o slug é uma URL, a coleta passou a falhar com:

```
CompanyNotFoundError: SuccessFactorsScraper('https://jobs.sap.com') not found
```

→ FETCH_ERROR diário no JSONL de 22/09 a 29/09 (8 dias, 8 registros, erro byte-idêntico ao reproduzido). Último SAP ok: **21/09 (971 vagas, ~13s)**. SAP era ~17% do universo eligible (2ª maior fonte) — a ausência reduzia materialmente a cobertura.

**A cadeia de resolução**: registry (`SAP` → `successfactors:jobs`) → `find_company("SAP")` (CSV hospedado upstream, linha `SAP,jobs,https://jobs.sap.com`) → `scraper_slug()` devolve `company.url` (successfactors ∈ `URL_SLUG_ATS`) → GET `jobs.sap.com/sitemal.xml` → 404.

## 2. Endpoints antigos vs novos

| papel | antigo (até 21/09) | atual |
|---|---|---|
| careers público | `jobs.sap.com` (RMK) | board Next.js novo (17 vagas EN no sitemap; sem feed) |
| **feed RSS de vagas** | `jobs.sap.com/sitemal.xml` → 200 | **404** (removido) |
| feed RSS (vivo) | — | **`careers.sap.com/sitemal.xml` → 200, 913 itens, ~15.3MB** |
| sitemap | `sitemal.xml` (RSS) | `sitemap.xml` multi-idioma (en/fr/de) — board novo, parcial |

## 3. Arquitetura atual do site (investigação read-only §2)

- **`jobs.sap.com`** (novo, Next.js/RSC): board novo em rollout PARCIAL — sitemap de jobs EN tem 17 URLs (DE/FR: 0); JSON-LD `JobPosting` por vaga (title/description/identifier `REF*`/datePosted/employmentType/jobLocation); sem API pública de listagem sem browser (apenas `/api/auth`, `/api/jobs/match-cv/`, `/api/jobs/recommendations/` — CV matching, não inventário). `robots.txt` allow-all.
- **`careers.sap.com`** (RMK legacy, Career Site Builder): **vivo e completo**. `/jobs` com locales (`en_US`/`de_DE`/`fr_FR`), `/topjobs/`, `/viewalljobs/`. `robots.txt` não bloqueia `/jobs/*`. O feed `sitemal.xml` é o mesmo de sempre — mesmo typo-path de décadas.
- Backend RCM SuccessFactors: vivo (identifiers `REF*` no board novo = mesmo backend de requisitions; o board é só um front).
- `www.sap.com/careers.html` → redirect → `jobs.sap.com/en/` (o site institucional aponta para o board novo).

**Conclusão**: a SAP migrou o FRONT, mas manteve o RMK legacy com o feed completo. O ponto de entrada correto do pipeline é `careers.sap.com`.

## 4. Evidência do endpoint novo (reprodução §5)

```
OLD: SuccessFactorsScraper('https://jobs.sap.com')  → CompanyNotFoundError (0.4s)
NEW: SuccessFactorsScraper('https://careers.sap.com') → 913 jobs (9.1s), scraper 0.3.0 intocado
```

Feed `careers.sap.com/sitemal.xml`: RSS 2.0, `<language>en_US</language>`, `<ttl>720</ttl>`, 913 itens, 15.292.070 bytes. Tags por item: `title`, `description` (CDATA completa), `link`, `guid`, `g:id`, `g:expiration_date`, `g:employer`, `g:job_function`, `g:location` — **contrato idêntico ao pré-outage em todos os campos que o projeto consome** (sem `pubDate`/`g:job_type`, como sempre).

## 5. Auditoria do `ats-scrapers` upstream (§3)

- Instalado: **0.3.0** (PyPI wheel; origem confirmada por `dist-info`: INSTALLER=pip, sem `direct_url.json`).
- Último commit no `successfactors.py`: `828f630` 2026-08-23 (#268, application deadline) — já incluído na 0.3.0. Sem tag ≥0.4.0.
- Issues/PRs upstream sobre SAP/SuccessFactors/sitemal: **nenhuma** (search na API GitHub; 49 PRs abertas, nenhuma relacionada). Fork `rios-vini/ats-scrapers`: ahead_by=0.
- **Perguntas A–E**: (A) upstream não corrigiu — o scraper não tem bug; (B) sem PR pronta; (C) sem implementação experimental; (D) **o tenant continua 100% SuccessFactors** (feed idêntico, mesmo backend RCM); (E) o dado stale é a URL de careers no CSV `ats-companies/successfactors.csv` — correção genérica upstream = 1 linha no CSV (issue arquivada como cortesia).
- Manifest hospedado (`storage.stapply.ai/jobhive/v1/manifest.json`) vivo — a coleta das outras 15 empresas do tenant segue ok (14.207 jobs de 15 empresas no jobs.json de 29/09).

## 6. Alternativas consideradas (§4 da spec)

| alternativa | evidência | complexidade | manutenção | risco |
|---|---|---|---|---|
| **override de URL por empresa (local)** ← escolhida | reprodução NEW 913 jobs com scraper intocado; URL stale só no CSV upstream; identidade/dedup preservadas (§7) | **baixa** (1 dict + 4 linhas) | **baixa** (lista explícita; removível quando upstream corrigir) | **baixo** (source/id/dedup intocados; A/B comprova) |
| fix no scraper upstream | não há bug no scraper | n/a | release ≥0.4.0 sem data | não aplicável |
| PR upstream do CSV | linha `SAP,jobs,jobs.sap.com` → `careers.sap.com` | baixa | resolve p/ todos | **latência**: aceitação/merge/publish do manifest fora do nosso controle |
| novo scraper do board Next.js | 17 vagas EN; sem API pública completa sem browser | **alta** (RSC, paginação client, multi-idioma) | **alta** (JS-drift, rollout parcial) | **alto** (inventário parcial 913→17) |
| adapter específico SAP local | schema idêntico — não-problema | média | média | rejeitado |

**Decisão (Caso B/C)**: override local por empresa + issue upstream de cortesia. Documentado como decisão arquitetural: quando o upstream atualizar o manifest/CSV, remover a entrada (o mapa é auto-contido; o teste `test_fasei` B1 garante o escopo exato).

## 7. Implementação (§9)

`src/internship_finder/collectors/ats_scraper.py`:
- `TENANT_URL_OVERRIDES: dict[(ats, slug, name) -> url]` com a entrada `("successfactors", "jobs", "SAP") -> "https://careers.sap.com"`.
- `scraper_slug()` consulta o override ANTES da regra `URL_SLUG_ATS`. Chave por **EMPRESA** (nome exato resolvido da base, mesmo critério de identidade da coleta), nunca por tenant — `successfactors:jobs` é compartilhado por 16 empresas do registry (ZF, Kaufland, Schaeffler, Bayer, BMW, HORNBACH, Voith, Tchibo, Webasto, Uniper, STIHL, SICK, Festo, Wacker, KraussMaffei); um override de tenant redirecionaria todas para o site da SAP.
- `Company.source` (`successfactors:jobs`), `Job.id` (`SAP|successfactors:jobs:<gid>`), dedup, ranking: **inalterados por construção** — só o HOST do feed muda.

## 8. Testes (§9)

`scripts/test_fasei.py` (44º do CI) — **42 checks, 100% offline**, fixture REAL (recorte público do feed de 29/09, descriptions redacted):
- **A/B**: override SAP resolve careers.sap.com; ZF/Kaufland/Schaeffler (mesmo tenant) seguem suas URLs; BASF (outro slug) idem; ATS fora do mapa segue comportamento puro; SAP sem URL na base também resolve.
- **B**: escopo cirúrgico da chave (exatamente 1 entrada; whitespace; outro ATS/outro slug não herdam).
- **C**: contrato do feed (g:id/g:employer/g:location/g:expiration_date/g:job_function; posted_at None; description CDATA; URL careers.sap.com).
- **D**: identidade via AtsJobAdapter — `SAP|successfactors:jobs:<gid>`, source inalterado, external_id=g:id, country_iso derivado (pe/de).
- **E**: sem fallback mágico (override é URL absoluta única).
- **F**: zero resultados (RSS válido sem itens → []).
- **G**: schema inesperado (HTML Next.js 404 → ScraperError).
- **H**: duplicidade (g:id duplicado → seen set do scraper).
- **I**: **11 vagas reais offline** (recorte do feed público), campo a campo, 9/11 DE.
- **J**: single-shot RSS (sem paginação).
- Suíte completa: **44/44 OK** no clone (43 pré-existentes + novo).

## 9. A/B offline (§10) — mesmo snapshot (jobs.json 29/09, 72.229 jobs, 0 SAP), código da branch

| métrica | ANTES (sem SAP) | DEPOIS (com SAP) |
|---|---|---|
| raw | 72.229 | 73.142 (+913 SAP) |
| tipo (funil) | 6.432 | 6.612 |
| área (funil) | 1.217 | 1.382 |
| **eligible** | **425** | **499 (+74 SAP)** |
| pós-dedup | 413 | 474 |
| pós-mirror | 409 | **470 (+61 SAP)** |
| dedup stats | company+title+location: 12 | 25 (+13 intra-SAP: pares DE/EN com mesma location) |
| mirror stats | mirrors_de_en: 4 | 4 (**inerte p/ SAP** — req_id None no RSS, comportamento histórico) |
| **Top 30** | — | **30/30 ids/ordem/scores idênticos** |
| non-SAP diffs | — | **0** (scores e membership) |
| score mediana/máx | 5.50 / 15.75 | 5.50 / 15.75 |
| runtime filtro | 67.6s | 72.0s (+4.4s = +6.5%, feed 15.3MB/9s) |

**SAP no ranking**: 61 vagas; melhor rank 54 (score 9.0, "iXp Intern Event Showcase"); ranks seguintes 63, 92, 115, 135...

**Churn vs SAP (atribuição correta)**: as +74 eligible SAP são reincidência de identidade (825/913 ids já existiam no histórico; 971 ativos no último run ok de 21/09), não churn de outras fontes — os 409 non-SAP do AFTER são byte-idênticos aos do BEFORE.

## 10. DE/EN (§11)

Feed único `en_US` com pares DE/EN internos (~60 grupos de título normalizado idêntico no feed atual; ex. `1382711433` Kommunikation/Marketing DE + `1382711533` Communication EN, ambos St. Leon-Rot). **Nenhuma regra nova de dedup criada** (spec §11): o mirror dedup existente (Fase C) fica inerte para SF (req_id=None no RSS → nunca candidato), exatamente como no pré-outage. Os pares entram como vagas separadas, conforme histórico.

## 11. Impacto de produção (§12)

- Produção `data/` **intocada durante a fase** (todas as medições read-only; A/B em clone/scratch).
- Cron/publicação **não alterados**. Após o merge, o run normal das 09:00 UTC de 30/09 valida a recuperação na produção (esperado: tenant SAP `ok` com ~900+ coletados, +61 vagas no ranking).

## 12. Critérios de aceite (§14)

1. **Por que parou?** jobs.sap.com reconstruído (Next.js), feed legacy 404 desde 22/09. ✅
2. **Nova fonte?** `careers.sap.com/sitemal.xml` (RMK legacy vivo, 913 itens). ✅
3. **Ainda é SuccessFactors?** Sim — feed idêntico, backend RCM vivo. ✅
4. **Upstream tem solução?** Não (0 issues/PRs; CSV stale; issue nossa arquivada). ✅
5. **Implementação correta?** Override de URL por empresa em `scraper_slug` — menor ponto, identidade preservada. ✅
6. **Vagas SAP atuais?** 913 no feed (histórico: ~1.000/dia; 21/09 = 971). ✅
7. **Elegíveis?** 74 eligible DE-student no A/B (61 pós-dedup; histórico ~70/dia — consistente). ✅
8. **DE/EN mirrors?** ~60 grupos; coletados como separados (comportamento histórico); mirror dedup inerte (req_id None). ✅
9. **Identidade/dedup preservadas?** Sim — mesmo espaço de ID (825/913 overlap), `Job.id` idêntico, 0 non-SAP diffs. ✅
10. **Impacto funil?** eligible 425→499 (+17,4%), final 409→470 (+14,9%). ✅
11. **Impacto ranking?** Top 30 intocado; 61 SAP entram a partir do rank 54. ✅
12. **Custo runtime?** +4.4s no filtro (+6,5%); fetch feed ~9s (vs ~13s histórico — neutro). ✅

## 13. Limitações

- **Override**: vive até o upstream corrigir o CSV/manifest (rastreado pela issue upstream PREPARADA — texto no §14; postagem pendente do dono); remoção = deletar 1 entrada + teste.
- O board novo (`jobs.sap.com`) NÃO é coberto — é rollout parcial (17 vagas EN) e sem feed público; se um dia substituir 100% o RMK, será uma nova fase (scraper dedicado, fora do escopo).
- `g:job_function` do feed mapeia `department` (Information Technology, Marketing...) — comportamento histórico, sem mudança.
- Feed sem `pubDate` (posted_at=None) — idêntico ao histórico; deadlines continuam `platform_sf` (`g:expiration_date`).

## 14. Próximos passos

1. Merge → CI main → docs (este arquivo + MASTER_PLAN Log + PROJECT_STATUS).
2. Issue upstream `kalil0321/ats-scrapers` (texto PRONTO abaixo — postagem pendente do dono):
   - **Título**: `SAP careers URL is stale in ats-companies/successfactors.csv — jobs.sap.com no longer serves /sitemal.xml (RMK moved to careers.sap.com)`
   - **Corpo**: Since ~22 Sep 2026, `jobs.sap.com` serves a new Next.js board and the legacy Recruiting Marketing RSS feed at `https://jobs.sap.com/sitemal.xml` returns 404 (HTML error page). The full RMK feed is alive at `https://careers.sap.com/sitemal.xml` — same schema (RSS 2.0 + Google Merchant `g:id`/`g:location`/`g:employer`/`g:expiration_date`/`g:job_function`, 913 items, full CDATA descriptions). `SuccessFactorsScraper` 0.3.0 collects the new feed unmodified; only the company directory row is stale: `ats-companies/successfactors.csv` line `SAP,jobs,https://jobs.sap.com` should become `SAP,jobs,https://careers.sap.com`. Evidence: `GET https://jobs.sap.com/sitemal.xml` → 404 HTML; `GET https://careers.sap.com/sitemal.xml` → 200 RSS, 913 `<item>`. Suggest also re-checking other `jobs.*` rows whose hosts were rebuilt recently.
3. Observar o cron 09:00 UTC 30/09: tenant SAP `ok` (~900+), +61 vagas no ranking, health sem FETCH_ERROR SAP.
4. Backlog Fase H segue pendente do dono: vocab `/h`, "if indicated", FP "N Monate", markers em description, cap enrichment.

---
*Artefatos da investigação (scratch, fora do repo): feed completo (`sap_careers_sitemal_full.xml`, 15.3MB), records JSON, 913 adapted JSON, A/B JSON.*
