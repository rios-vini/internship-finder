# F76.1 — DISCOVERY_RULES local: regras executáveis por ATS do registry

**Data**: 2026-10-20 · **Decisão do dono**: opção B — "mecanismo mínimo local"
(respondida 20/10 ~13:40 UTC no menu do card F76.1) · **Spec de origem**: fase
F76 E3 (`~/.hermes/handoff/f76-robustez-upstream/ESPECIFICACAO.md`, item 2;
relatório F76 §3) · **Upstream inspecionado**: `kalil0321/ats-scrapers`
@`6b44a1b` (= v0.3.0), `docs/DISCOVERY_RULES.md` (318 linhas, DOC — zero
código executável; 10 provider notes, só 4 cobrem ATS do nosso registry).

## 1. O que é "local" (e o que não é)

O doc do upstream é um guia para **humanos abrindo PRs no repositório
deles** (workflow, checklist, endpoints em prosa). Vendored, ele viraria
papel congelado que não executa nada. A opção B escolhida pelo dono destila
o subconjunto que o IF realmente usa em **regras versionadas por ATS do
registry** (14 ATS / 127 empresas, medidos 20/10) e usa a **API instalada
como máquina de validação**:

- `resolve_careers_url`/`get_scraper_for_url` (`ats_scrapers` ≥0.3.0):
  mapeamento **determinístico e offline** de URL → (ats, slug);
- o scraper do pacote é quem consome o endpoint canônico e diz se há vagas
  vivas (única rede do mecanismo, **só no uso manual**).

Implementação: `src/internship_finder/discovery_rules.py`
(`RULES` — 14 regras declarativas; `classify`/`classify_slug`/`tenant_key` —
classificador puro; `validate_candidate`/`validate_slug` — máquina com
injeção para testes). Suíte: `scripts/test_f76_1.py` (100% offline —
Grupo B verifica cada regra contra o **código instalado**).

**Não é estágio do pipeline**: discovery de tenant é procedimento humano
assistido (avaliar candidatas ao registry). Nada aqui roda no cron; nenhum
comportamento de coleta mudou.

## 2. As 14 regras (medidas 20/10 contra o pacote instalado 0.3.0)

| ATS (empresas) | CSV upstream | Endpoint canônico de validação | Sinal de vagas vivas | Resolver por URL? | Específicas de inválido |
|---|---|---|---|---|---|
| successfactors (51) | name,slug,url | `GET {host}/sitemal.xml` (RMK RSS); legacy `/career?company=…` | `rss:<item>` / `xml:<Job-Listing>` | **não** (jobs2web/careers.*) | unresolvable_url |
| workday (28) | name,slug,url | `POST {board}/wday/cxs/{company}/{site}/jobs` | `json:total` | sim (URL inteira = slug) | — |
| greenhouse (12) | name,slug,url | `GET boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | `json:jobs` | sim | — |
| smartrecruiters (8) | name,slug,url | `GET api.smartrecruiters.com/v1/companies/{slug}/postings` | `json:content` | sim | — |
| cornerstone (6) | name,slug,url | `GET {slug}.csod.com/ux/ats/careersite/{site_id}/home?c={slug}` + gateway | `json:data.requisitions` | **não** (*.csod.com) | unresolvable_url |
| phenom (6) | url,name,company_code,locale,country | `POST {base}/widgets` (CSRF via `/search-results`) | `json:totalHits` | **não** (domínio custom) | unresolvable_url |
| recruitee (4) | name,slug,url | `GET {slug}.recruitee.com/api/offers` | `json:offers` | sim | archived_board |
| eightfold (3) | name,slug,url,**domain** | `POST {base}/api/pcsx/search` | `json:data.positions` | sim | api_disabled_tenant |
| softgarden (3) | name,slug,url | `GET {tenant}.career.softgarden.de/jobs.feed.json` | `json:dataFeedElement` | sim | — |
| teamtailor (2) | name,slug,url | `GET {slug}.teamtailor.com/jobs.rss` | `rss:<item>` | sim | — |
| ashby (1) | name,slug,url | `GET api.ashbyhq.com/posting-api/job-board/{slug}` | `json:jobs` | sim | — |
| moka (1) | name,slug,url | `POST {host}/api/outer/ats-apply/website/jobs/v2` | `json:jobs` (+jobStats.total) | sim (slug `empresa/id`) | — |
| bamboohr (1) | name,slug,url | `GET {slug}.bamboohr.com/jobs/embed2.php` (JSON puro — F59) | `json:result.jobOpening` | sim | — |
| personio (1) | name,slug,url | `GET {slug}.jobs.personio.com/search.json` | `json:jobs` | sim | — |

Baseline de sucesso (todos os ATS): **HTTP 200 + ≥1 vaga viva** no sinal.
Baseline de inválido (todos): as 10 classes do §Invalid Cases do upstream
(provider_home, global_marketplace, login_shell, branded_shell_no_jobs,
stale_404_live_api, http_not_found, redirected_to_provider_home,
expired_job_page, demo_sandbox_tenant, opaque_slug_no_name,
duplicate_identity). Taxonomia canônica completa: `Invalid` no módulo
(+archived_board, +api_disabled_tenant, +unresolvable_url, +unknown_ats,
+http_error, +unreachable do mecanismo).

Critérios das provider notes que são **revisão manual** (não executáveis):
SF legacy exige `ReqId`/`JobTitle`/`Job-Description` não-vazios;
cornerstone exige nome legível (o provider expõe só slugs técnicos);
eightfold rejeita `PCSX is not enabled` e tenants só-SmartApply.

## 3. Como validar uma candidata ao registry (uso manual — REDE)

```bash
cd <repo> && .venv/bin/python - <<'PY'
import sys; sys.path.insert(0, 'src')
from internship_finder.discovery_rules import validate_candidate, validate_slug

# URL reconhecível (11 dos 14 ATS) — resolve + aplica a regra + classifica:
v = validate_candidate("https://12build.recruitee.com")
print(v.valid, v.reason, v.evidence)

# ATS de domínio custom (successfactors/cornerstone/phenom) — pelo (ats, slug):
v = validate_slug("phenom", "https://jobs.bell.ca")   # slug-URL p/ SF/phenom
v = validate_slug("cornerstone", "henkel")            # token p/ cornerstone
PY
```

O veredito carrega evidência (url, ats, slug, endpoint, status, job_count,
tenant_key, company) — o upstream pede evidência por linha emitida.
`tenant_key` dá a identidade estável para dedupe (variantes de
scheme/www/barra/utm_* colapsam; params funcionais preservados).

## 4. Drift-check LEVE (procedimento MANUAL — nunca CI)

O mecanismo tem **dois eixos de drift**, com tratamento diferente:

### 4.1 Eixo "pacote instalado ↔ regras" — AUTOMÁTICO e offline

O `test_f76_1.py` Grupo B verifica, para cada um dos 14 ATS, que os tokens
do endpoint canônico e do sinal de vagas **existem no fonte do scraper
instalado**. Consequências:

- bump de `ats-scrapers` no pyproject que mude endpoint/sinal → suíte
  vermelha **no CI, sem rede e sem procedimento**;
- `coverage()` acusa no mesmo teste se o registry ganhar/perder ATS sem a
  regra acompanhar (A1).

**Quando rodar**: nada a fazer — roda em todo CI. Ao elevar a versão do
`ats-scrapers`, uma suite vermelha aqui é o detector fazendo seu trabalho.

### 4.2 Eixo "doc upstream ↔ regras" — MANUAL, leve (rede)

O doc do upstream evolui (provider notes novas, classes de inválido novas).
Procedimento **manual** sugerido (ex.: mensal, ou antes de uma onda de
expansão do registry — nunca no CI):

1. Baixar o doc vivo e conferir as seções que alimentam as regras:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/kalil0321/ats-scrapers/main/docs/DISCOVERY_RULES.md -o /tmp/DR_upstream.md
   grep -n -A12 '### SuccessFactors\|### Recruitee\|### Cornerstone\|### Eightfold' /tmp/DR_upstream.md
   grep -n -A14 '## Invalid Cases' /tmp/DR_upstream.md
   grep -n -A9 '## Baseline Rule' /tmp/DR_upstream.md
   ```
2. Conferir contra: §2 deste doc (tabela), `Invalid` no módulo (taxonomia),
   `EXTRA_INVALID` no `scripts/test_f76_1.py` (classes específicas).
3. Divergência relevante (ex.: provider note muda o endpoint de validação,
   classe de inválido nova que se aplique aos nossos ATS) → atualizar
   regra/doc/teste em um PR de fase curto (a suite Grupo B segue guardiã do
   eixo 4.1).
4. Provider notes de ATS FORA do nosso registry (gem, taleo, oracle, adp,
   pinpoint, avature) ficam FORA de escopo por definição — regra só existe
   para ATS do registry (A1: `set(RULES) == registry_ats()`).

## 5. Limitações honestas

- 10 dos 14 ATS não têm provider note específica no doc upstream — as regras
  desses derivam do **código instalado** (que é o que o IF consome) e do
  baseline genérico; se o upstream publicar notas específicas, o
  drift-check 4.2 as incorpora.
- `validate_candidate` não segue redirects além do que o scraper do pacote
  segue; WAF/403 classifica como `http_error` (a semântica fail-loud da F76).
- Discovery por URL não existe para successfactors/cornerstone/phenom
  (domínio custom): o resolver devolve None **por desenho** — o caminho é
  `validate_slug(ats, slug)`, e para SF/phenom o slug É a URL completa do
  board (`url_as_slug=True`, espelhando o `URL_SLUG_ATS` do coletor).

## 6. Notas operacionais de tenant (F105 — medições 23/10/2026)

Fatos MEDIDOS no registro do dono (abertura ao vivo, do Brasil) que
atravessam a regra por ATS — código e docs no MESMO PR (contrato F73:
docs↔código sem drift). Re-sondar estas URLs só em re-medição datada; a
suíte é OFFLINE e consome fixtures verbatim do registro.

### 6.1 Vetter — migração do formato de URL de vaga

- **Legado MORTO**: `careers.vetter-pharma.com/jobs/<ID>` → **404**.
- **Vivo**: `careers.vetter-pharma.com/job/<slug>/<ID>/` (IDs
  inalterados; 7 vagas ATIVAS verificadas 23/10).
- Apply: botão "Jetzt bewerben" na página da vaga → Bewerberkonto no
  SuccessFactors (`career5.successfactors.eu`, `company=Vetter`) — uma
  conta serve as 7. Sem geoblock.
- Guard executável: `discovery_rules.TENANT_JOB_URL_FORMATS["vetter"]` +
  `job_url_format_status(url)` → `"current"` | `"legacy_dead"` | `None`.
  O formato legado é reconhecido como morto e NUNCA seguido/reconstruído
  (não existe reescrita no código — o guard só classifica; o consumo é o
  drift-check manual).

### 6.2 Arvato Systems — preferência pelo portal oficial Bertelsmann

- O geoblock que derrubou o dossier era **SÓ do agregador**
  `absolventa.de`; o portal oficial `jobsearch.createyourowncareer.com`
  (multi-empregador: ARVATO/Arvato_Systems/RTL/BFS/Bertelsmann_Corporate)
  **abre do Brasil**, e a candidatura roda no SmartRecruiters
  corporativo (`jobs.smartrecruiters.com/Bertelsmann-Jobs/…` —
  formulário abre normalmente).
- Regra executável (link DIRETO do MANUAL-CHECK, doutrina F96: o alvo
  aplicável ao dono): `manual_check.official_portal_twin_url` — quando a
  vaga na fila está num agregador geobloqueante
  (`GEOBLOCKED_AGGREGATOR_HOSTS`) e o gêmeo no portal oficial
  (`OFFICIAL_PORTAL_HOSTS`) existe no MESMO ranking (título normalizado
  igual + mesmo país + overlap de descrição Jaccard ≥ 0.5; o único par
  misto medido do funil tem 0.744), a linha da fila aponta pro portal,
  marcada `_(link direto: portal oficial — agregador geobloqueado)_`.
  Sem prova de mesma vaga → sem swap (fail-closed).
- Rota completa de candidatura no mapa `manual_check.TENANT_PORTAL_METADATA`.

### 6.3 J&J Beerse (BE) — gate EXTERNO de acordo (manual-check)

- A vaga só começa se a universidade assinar o **standardized Belgium
  internship agreement** do próprio J&J ("External agreements cannot be
  accepted" — verbatim R-106104/R-102271). Gate EXTERNO à candidatura:
  a vaga SEGUE elegível (resolvível pela universidade do dono) e entra
  na fila manual-check com o motivo novo
  `external_agreement_gate` (`manual_check.MOTIVO_EXTERNAL_AGREEMENT_GATE`,
  flag persistida no padrão id_collision; NUNCA exclui).
- Detector: `manual_check.detect_external_agreement_gates` — família
  medida no corpus inteiro: J&J ×2 (padrão "external agreements cannot
  be accepted") + Danone ×5 ("3-party internship agreement signed by
  your university"). A família de MATRÍCULA local (Continental
  "Studium an einer deutschen Hochschule", Avery "enrolled at a Dutch
  university" — exclusão F99 / card F106) e menções genéricas de acordo
  (boilerplate "can provide an internship agreement") NÃO acendem.
