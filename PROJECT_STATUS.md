# Project Status

Last updated: 2026-09-29 (Fase H — production observation & data quality review, docs-only)

## Current state

- **Fase H — Production Observation & Data Quality Review — 29/09, DOCS-ONLY (sem PR de código, por design da fase; nenhum módulo alterado; produção `data/` intocada; CI main verde)**: auditoria de 1 ciclo real pós-F (29/09 09:00 UTC: 72.229 raw → 409 eligible; hydration 73/73=100%; official page 103 ok/23 JSON-LD/13 validThrough; enrichment 0 ok/21 ReadTimeout — 5h38, janela NVIDIA degradada; publish `06ae9e6` + digest encurtado por 7 alertas) contra baseline 28/09 (404, pré-F/G) e variação 27/09 (412). **A/B de código no mesmo dataset**: WA 70→17 existing_required (−53 condicionais = 100% efeito F); student_type 201/144/37/0/27 (0 conflitos); salary 28→32 (F +1 covestro 21 €/h; G +3: VW 17,80→17,8/h, Bayer 2.280,00 ×2, MAHLE 1500; roche 226→2268) — 0 regressões; G não afeta WA. HTML de hoje ainda renderiza F (G publicará 30/09 — `data-salary="80" month` visível no VW rank 21). **Auditorias** (todas com evidência textual): WA honesto (59/59 unclear têm termo; 53 condicionais + 5 VW por audiência + 1 celonis; 17 existing = 7 condicionais NÃO-cobertas "if indicated"/"falls erforderlich" + 7 não-EU + 3 teampicnic); student_type 0 FP/0 conflitos (27 unclear = 15 SHK Fraunhofer/4 teses/4 trainees FP/4 híbridos); salary 32/32 auditados (period errado ×3 por `/h` fora do vocab: VW 18,33 €/h, philips 15 €/h; BASF "annual salary 40-46k" antes-do-valor; FP Fraunhofer "12 Monate befristet" → 12 €/mês); deadlines 0 não-detectados (231 platform_sf = feed+30d; 6 Fraunhofer; 13 validThrough = validade de plataforma); descriptions 100% pós-hydration, 29 teasers = 100% phenom:nan (bloqueio persistente); official page: informação nova real = 13 validThrough + 20 location (resto redundante). **Reavaliação LLM**: TODOS os ganhos da spike E capturados por F/G (6/6 + 21/21 + 1/1 por id); 0 ganho LLM remanescente comprovado; phenom teaser (29 vagas) exige browser = fora de escopo; enrichment operacionalmente morto na janela (5→3→0 ok/dia). **Achado principal (G1)**: SAP FETCH_ERROR há 8 dias — site reconstruído (Next.js), feed legacy `sitemal.xml` 404 (probe com evidência; robots.txt aponta `/sitemap.xml` novo); era ~70 eligible/dia ≈ 17% do universo, 2ª maior fonte — maior perda de cobertura da história recente, classificada D (fonte externa); hoje também: AkzoNobel 500 no feed (regressão ok) e Siemens Healthineers empty (zero_return ok) — health detectou ambos corretamente. **Gaps G1–G11 classificados A–F**; candidatos de próxima fase (decisão do dono): fonte SAP / mini-fase vocab (`/h`, "if indicated", "falls erforderlich", guard "Monate") / cap do enrichment. Relatório: `docs/fase_h_production_observation.md`.

- **Fase G — Salary Decimal Parsing Fix — 29/09, PR #91 MERGEADO (squash `e807c08`; CI do PR verde ×3 no SHA `ebbfc23` — membership `test_faseg` conferida nos logs de todos os runs, array 42→43 — 0 PRs, branch remota deletada; produção `data/` intocada; mini-fase cirúrgica autorizada pelo dono 29/09)**: correção do bug pré-existente do `_MONEY_CLAUSE` (`opportunity_intel.py`): decimais alemães truncados (`€17,50`→17) ou corrompidos em salário-lixo pelo fragmento pós-vírgula (`17,50 Euro`→50 €/mês; VW `17,80 €/Stunde`→80 €/mês). **Fix**: cada lado do range `\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?` (alt1 exige ≥1 grupo de milhar — evita regressão `2117`→`211` — + decimal final; alt2 decimal simples); `_to_number`: milhar+decimal (último separador = decimal) → milhar puro (idêntico) → separador único = decimal (`17.50`→17.5, antes 1750) → não reconhecido = None (datas; conservador); guard >0 preservado. **Nada fora de salary**: ranking NÃO consome salary (zero refs em ranking.py); eligibility/score/pesos/dedup/cron intocados. **Dataset A/B Fase F (3.555, mesmo input)**: 228→254 salários textuais (month 206→215, hour 14→31, year 8→8); 0 perdidos; 189 idênticos; 10 truncados + 14 garbage corrigidos; 26 novos legítimos auditados 1-a-1 (MAHLE 1500 € ×14, Bayer 2.280,00 ×9, SMA, Webasto, Nestlé ×2 — 0 FPs); VW `18,33 €/h` valor corrigido, period=month pré-existente mantido (vocab `/h` fora da Fase F — não estendido). **A/B pipeline (jobs.json produção 29/09, flags offline idênticas)**: 635/635 ids mesma ordem, 0 score/breakdown diffs, Top 30 idêntico, eligible JSON byte-idêntico (sha256 igual). **A/B render (flags idênticas + db-join/enrichment/intel explícitos)**: 626/635 linhas idênticas; 9 diffs = EXATAMENTE salary; 0 fora de salary. **Testes**: `test_faseg.py` NOVO (68 checks offline, grupos A–G da spec; 43º no CI, array 42→43); `test_fasef.py` P2.3 evoluído (guard pré-G protegia o mundo do bug; pós-G 17,80 €/Stunde → 17.80/h correto — 74 checks preservados); suíte relevante OK no clone. **Limitações**: UI `euro()` não exibe decimais no card (valor interno correto + citação exata exibida); `€50,000/year` period=month (pré-existente); ranges "zwischen X und Y" capturam o piso. Docs: `docs/fase_g_salary_decimals.md` + Log 29/09 do MASTER_PLAN.

- **Fase F — Deterministic Enrichment Fixes — 29/09, PR #90 MERGEADO (squash `a848006`; CI do PR verde ×2 no SHA exato `72d4009` — membership `test_fasef` conferida nos logs de AMBOS os runs, array 41→42, 42 banners TUDO OK, 0 FAILs — + CI main pós-merge verde; 0 PRs, branch remota deletada; produção `data/` intocada)**: correção determinística dos gaps comprovados pela spike da Fase E, SEM LLM no pipeline e SEM tocar eligibility/score/pesos/ranking/Top 30/dedup/publication gate/cron (spec §12). **(P0) WA condicional**: `_wa_existing_evidence()` — guard sentence-scope no caminho `existing` do `work_authorization`: condicional ("ggf.", "gegebenenfalls", "wenn vorliegend", "if/where applicable", "if you have/hold") entre o início da sentença e o match suprime `existing_required` (→ `unclear`); abreviações DE mascaradas; precedência e vocab intactos; NÃO é a regra simplista "ggf. ⇒ unclear". Os 6 casos da spike (5× Bosch, 1× STIHL) saem de `existing_required`; adversariais §6 passam; janela verbo→tema do suporte 30→32 (0 novos matches em produção). Dataset 3.555: existing_required 190→64, unclear 98→224, restante idêntico; flips auditados 15/15 legítimos. **(P1) Student subtype (enrichment puro)**: `app_intel.student_type(job)` com gate `filters.is_student_role` (nunca reclassifica, nunca filtro/peso); 5 valores por evidência explícita; conflito title×description de subtipos específicos divergentes → `conflict=True` + publicado `unclear`; guardas anti-FP de produção (enumeração Telekom/trumpf ⇒ genérico; checklist condicional VW ⇒ não classifica; voluntário negado MAHLE ⇒ mandatory). UI: linha "Tipo de vaga estudantil: X" no Candidate Fit; genérico não emite linha. Distribuição 3.555: 1.757 internship / 670 working_student / 196 mandatory / 916 unclear / 16 voluntary / 0 conflitos. **(P2) Salary hourly**: extensão mínima de `job_salary` — "Stundenlohn von X Euro"/"Stundenvergütung"/"hourly rate|wage" antes, "€X/Stunde"/"per hour" depois ⇒ `period="hour"` (ptbr "hora"); 14 vagas ganham salário (12 None + 2 "€18/mês" absurdos); mensal/anual idênticos (208→208, 8→8); guard de fragmento decimal; **limitação aceita pelo dono 29/09**: decimais alemães truncados pelo matcher pré-existente (€17,50→"17"; sub-estimado, nunca inflado) — correção = backlog. **(P3) German/English: NÃO implementado, backlog documentado**: root cause identificada, mas `german_level`/`english_evidence` ALIMENTAM O SCORE (ranking.py −2,0/−0,5/+1,5): corrigir = mudar score/ranking, proibido pelo §12. **A/B (spec §14)**: pipeline completo no mesmo input (jobs.json produção, flags idênticas offline): 3555/3555 ids idênticos e mesma ordem, 0 score diffs, Top 30 idêntico, 0 diffs em qualquer campo; render 404: 60/60 ids/scores idênticos, diffs = exatamente o enrichment novo. **Testes**: `scripts/test_fasef.py` (74 checks, 100% offline; 42º no CI); suíte local 41/42 (test_lifecycle = pré-existente do VPS, reproduzida na base). Docs: `docs/fase_f_deterministic_fixes.md` + MASTER_PLAN Seção 1/Log + PROJECT_STATUS (este). [Fase F ✅ — LLM segue fora do pipeline; decisão de integração de LLM pendente do dono]

- **Fase E — LLM Enrichment Spike — 28/09, PR #89 MERGEADO (squash `93168fa`; CI do PR verde ×2 no SHA exato `ca286cba` — membership `test_spike_e` conferida no log do run (`==== test_spike_e OK ====`), array 40→41 — + CI main pós-merge verde; 0 PRs, branch remota deletada; produção `data/` intocada)**: spike CONTROLADA e ISOLADA — mede quanto conhecimento novo e confiável um LLM extrai de texto JÁ COLETADO onde os detectores determinísticos não resolvem. **100% isolada**: pacote novo `src/internship_finder/spike_e/` (schema pydantic com enums exatos da spec §7 + validador evidence-first [estado informativo EXIGE evidence], amostra estratificada §5 determinística seed 20260928, input builder §6/§12 com normalização HTML via `app_intel.normalize_text` [3 feeds ~90% HTML noise exigiram ranking por texto normalizado], prompt §13 curto [sponsorship≠relocation, existing≠sponsorship, required≠preferred], comparator §11 [agree/llm_adds_information/conflict/deterministic_missing/llm_missing], runner idempotente skip-if-done) + `scripts/spike_e_run.py` (--run/--plan/--skip-llm; cliente `enrichment/llm.py` reusado — glm-5.3-flash; erro por job NÃO interrompe batch) + `scripts/test_spike_e.py` (15 grupos §21, 48 checks, 100% offline FakeTransport; 41º no CI) + docs. **NENHUM módulo existente importa spike_e; spike_e NUNCA importa ranking/filters/dedup; zero impacto em score/eligibility/dedup/Top 30/cron/Telegram/jobs.db/Pages; artefatos FORA do repo (dados de vagas).** **Run real n=30** (10 WA-gap + 5 phenom teaser + 5 page-problem + 5 condicionais + 5 controle; composição exata, zero desvios): **25 ok / 5 ReadTimeout** (janela degradada 26–28/09; máx 20% erro, sem aborto), 86.243 tokens (~0,5% free tier), 3h16 total, mediana 201s/job. **Achados**: (1) **WA-gap é gap de TEXTO** — 0 novas informações do LLM nos 19 gaps (as vagas não falam de sponsorship/autorização; LLM não inventa); (2) **6 llm_missing** (det existing_required → LLM unclear): condicionais "ggf."/"wenn vorliegend" que o det rotula existing_required SEM checar — sobre-classificação det corrigível DETERMINISTICAMENTE (achado inesperado); (3) **maior ganho real: student subtipo — 21 deterministic_missing** (13 internship / 4 working_student / 4 mandatory_internship, evidências verificadas in-input; campo inexistente no det); (4) salary: 1 nova (covestro €21/h "Stundenlohn" — fora do vocab det) + 4/4 confirmações exatas; (5) German: 2 conflicts com manual review dando razão ao LLM (ABB "Ideal for candidates…", Bosch "verhandlungssicheres" — mais sobre-classificação det); (6) English: 2 adds lendo através do typo "Englis h" do feed; (7) deadline: 0 (não converteu validThrough/feed em prazo — §12 respeitada 25/25). **Manual review §17 (23 casos): 22 OK / 0 FP / 1 ambíguo / 0 alucinações; 0 evidências não-encontradas**. **Decisão de integração (A/B/C/D §23) PENDENTE do dono** — números indicam: NÃO integrar p/ WA; candidatos reais = student subtipo + salary em vagas de texto rico; reavaliar fora da janela degradada (16,7% ReadTimeout = custo operacional). Verificação independente: diff 12 arquivos permitidos (+2236/−1), suíte 41/41 worktree independente, key 0 ocorrências, produção intacta, números reproduzidos contra artefatos. Artefatos: `/tmp/if-fasee-artifacts/`; relatório: `~/.hermes/handoff/fasee-spike/relatorio_fase_e.md`. [Fase E ✅]

- **Fase D2 — Consumo da evidência da página oficial — 28/09, PR #88 MERGEADO (squash `43a2f0a`; CI do PR verde ×2 no re-run — 1º par falhou em flake de resolver PyPI (pandas build-from-source), sem relação com o código; membership `test_official_evidence` nos logs, array 39→40 — + CI main pós-merge verde no SHA exato; produção `data/` intocada)**: menor conjunto de consumo útil da evidência da Fase D — **view read-only, sem GET novo, sem LLM/browser, sem tocar ranking/eligibility/dedup/pesos/limite-150**. Módulo novo `src/internship_finder/present_official.py` (padrão `enrichment/present.py`: contato ÚNICO produtos↔evidência, zero imports de ranking/filters/dedup). UI (`scripts/interface.py`): linha "página oficial verificada em <data>" (status `ok`), "validThrough do JobPosting (página oficial): <data>" (13 casos, 5 no Top 30, 13/13 vagas sem deadline — NUNCA `application_deadline`), "local confirmado pela página oficial" (15), chip `c-warn` p/ `not_found` (1 — o único fato acionável antes do clique). **Internos por decisão de evidência**: employmentType (regime≠natureza), conflitos de location (3 reais pós-fix), datePosted (23/23 já com posted_at), salary JSON-LD (duplica ATS), identifier, status técnicos. **Fix comparator**: `_location_relation` usa `city_and_region` (Fase 7) — mata 5 FPs (AIXTRON rua→cidade); ranking intacto (comparador é pós-eligibilidade). **A/B real**: render 408 vagas — scores/ids/ordem/Top 30 100% idênticos; diferenças = exatamente o consumo novo. Limite 150 preservado. Testes: `test_official_evidence.py` (36 checks, 40º no CI); suíte 40/40. Docs: docs/official_page.md §D2 + README. Detalhes: Log 28/09 do MASTER_PLAN.
- **Fase D — Official page + JSON-LD enrichment — 28/09, PR #87 MERGEADO (squash `997a884`; CI do PR verde no SHA `e6e0f65` — membership `test_official_page` conferida no log, array 38→39 — + CI main pós-merge verde; produção `data/` intocada)**: estágio `enrich_official_pages` ENTRE `hydrate_descriptions` e `rank_jobs` (`src/internship_finder/official_page.py`; `--official-page` default ON; `--official-page-limit` default 150). Candidata = description ausente/teaser (<400) OU sem deadline OU sem salary, cortadas por prioridade. UM GET por vaga (reuso de `enrichment/fetch`: fetch_page/classify_page/title_match; UA/timeout do spike; cap 1MB; budget 600s). Status: `ok` (page_verified; +`redirect_target_job`), `redirected` (home — jamais evidência), unavailable (`not_found/http_error/timeout/fetch_error/empty_content`), `js_rendered` (unsupported), `mismatch` (JobPosting conflitante). `job.url` nunca alterado. JSON-LD `JobPosting` procurado em objeto/array/`@graph`/múltiplos blocos e **validado contra a vaga** (identifier/external_id/requisition_id → URL → título+org) antes de extrair; evidência em `job["official_page"]["jsonld"]` (valid_through, salary, employment_type, location+relation, description, identifier, date_posted). Hierarquia FIELD-SPECIFIC: description só substitui teaser (`description_source="official_page_jsonld"`); salary só preenche `raw.*` vazio (placeholder 0.0 rejeitado); validThrough/datePosted/identifier nunca promovidos; employmentType nunca filtro. A/B snapshot 28/09: 408/408 ids idênticos, **0 score diffs**, Top 30 idêntico, 0 vagas alteradas fora `official_page`; 150 GETs/148s; 23 JobPosting matched, 13 valid_through, 15 loc confirmadas/8 conflitos, **0 descriptions melhoradas** (Fase A cobriu as ausentes; teasers phenom = redirect home sem JobPosting — caso p/ fase LLM). Testes: `test_official_page.py` (62 checks, 39º no CI); `test_hydration` bloco 10 anti-GET. Suíte 38/38. Docs: README + docs/official_page.md. Detalhes: Log 28/09 do MASTER_PLAN.

**Correções da auditoria pós-Fases 1–8 (PR #78, 23/09)** — 4 pontos operacionais,
nenhuma mudança de ranking/filtros/pesos/coleta:

- **Gate de publicação parcial segura**: predicado ÚNICO
  `publish_pages.publication_allowed(exit_code, eligible)` — exit 0/2 com
  eligible > 0 publica (Pages), monta digest e roda o sync-ranking; exit 1
  (dataset vazio), eligible == 0 e exit 124 (run truncado) bloqueiam. O exit
  code operacional do refresh (0/1/2/124, P1.3) é preservado para
  cron/monitoramento — publicar e exit code são decisões independentes. Fim
  do stale perpétuo: 17+ runs exit 2 seguidos nunca publicavam.
- **Isolamento estrutural de testes**: cli.main em modo coleta SEM `--metrics`
  gravava em `data/collection_metrics.jsonl` RELATIVO AO CWD (vetor da
  contaminação "Acme" 19–21/09, 2ª ocorrência). Fix: `--metrics` explícito em
  tempdir no test_hardening + teste sentinel byte-identical (pseudo-repo com
  `data/`, cwd no root — cenário exato do incidente) + guarda estrutural
  (nenhum cli.main collect-mode sem --metrics). Regra: testes/validações
  NUNCA escrevem em `data/` de produção.
- **Atribuição de erro por `(source, company)`**: falhas do run carregam o
  company do registro QUE FALHOU (não o primeiro company do source); mensagem
  Telegram aponta a empresa certa em tenants compartilhados (erro da SAP em
  `successfactors:jobs` não é mais anunciado como "BMW AG").
- **Alerta de regressão histórica**: `health._detect_regression` — série
  `(source, company)` historicamente ok (≥3 runs ok) cujo run mais recente
  falhou (error/timeout) gera alerta com company/source/error_code; sem
  histórico ok nunca alerta. Schema de alertas: drop / recurring_error /
  zero_return / **regression**.
- Suíte CI: 30 → 31 scripts (`scripts/test_audit_fixes.py`, 61 checks).
- **PR #79 (24/09, main `b1f5a2e`)** — itens 5–9 da auditoria (qualidade de dados): suíte CI 31 → 32
  (`scripts/test_audit2_quality.py`, 67 checks). German (snapshot 23/09, 391 eligible): required
  192 / preferred 36 / plus 4 / none 159 (25 FNs corrigidos pela normalização HTML + fix `verb_rev`;
  pesos intocados). WA inalterado (23/6/362). Deadlines: `platform_sf` 212 / **`employer_textual`
  6** (Fraunhofer, "Bewerbungsfrist: 23.10.2026" — novo; 0 employer estruturado; SF nunca vira
  employer). Salary 21/391 (18 textual + 3 recruitee estruturado €1.400–1.500/mês —
  `raw.salary_min/max/currency/period` mapeados antes do regex; period None quando ausente).
  Custo de vida 179/391 (aliases determinísticos munich/cologne/nuremberg → chaves canônicas;
  valor exibido inalterado). `--include-descriptions` AVALIADO e NÃO ativado (6 tenants
  estourariam a janela 85s do fetch_with_timeout — Bosch/Infineon/ABB/Bayer/RedBull/Roche;
  ver Log 24/09 do MASTER_PLAN; pendência de decisão: timeout por tenant escalado ou fetch
  seletivo por ATS). Eligible/ids idênticos (391==391); ranking/filters/pesos intocados.
- **Itens 10–11 (24/09, branch `feature/audit2-itens10-11`, PR aberto)** — WA vocab + visa_policy:
  suíte CI 32 → 33 (`scripts/test_visa_policy.py`, 43 checks). **Item 10** (snapshot 23/09, 391
  eligible): WA 23/6/362 → **23 existing / 4 unclear / 364 not_mentioned** (2 celonis
  unclear→not_mentioned pela saída de `relocat\w*` do tema — FP2 corrigido; FP1 corrigido:
  required+relocation → existing_required; 8 FNs de suporte + custeio cobertos por teste —
  padrões prontos p/ coletas futuras, sem ocorrência no dataset; negações expandidas EN/DE com
  contrapartes testadas; existing already/vorhanden/EU passport; precedência inalterada).
  **Item 11**: `visa_policy` da empresa (5 estados; condicional → unclear) — SAP + BoschGroup
  `unclear` c/ fonte primary verificada 2026-09-23, 10 empresas `not_verified` c/ nota de
  rastreabilidade; INDEPENDÊNCIA visa_policy(empresa) × work_authorization(vaga) verificada
  (ambos preservados e distintos; visa_policy NÃO entra no score — data-attrs idênticos).
  Fix pré-existente: invariante de deadline do test_app_intel (dupla contagem campo SF +
  textual; suíte local c/ data/ real 31/32 desde o PR #79 → 33/33). Eligible/ids idênticos
  (391==391); ranking recomputado antes/depois: sequência+scores idênticos (0 diffs); data/
  byte-identical antes==depois. Detalhes: `docs/relatorio_itens10_11.md`.

- **Camada de enrichment (isolada) — 25/09, PR #81 MERGEADO (squash `64683fd`, CI do PR verde 34/34 + CI main pós-merge verde; carga real inicial: 12 records gravados, 6 extrações completas — 5 high — na janela degradada da API, falhas persistidas para retry)**: primeira versão da camada de enriquecimento por LLM, ferramenta
  STANDALONE — nenhum módulo existente importa o novo pacote
  `src/internship_finder/enrichment/` (schema/fetch/html_norm/llm/runner/store) e
  nenhum módulo existente mudou (só ci.yml + docs). O que é: amostra determinística
  (top 16 + 4 WA + 4 sem description de `data/eligible_jobs.json`) → fetch da página
  oficial → normalização HTML→texto → extração GLM-5.3-Flash (JSON estruturado com
  evidência por campo, taxonomia WA de 8 conceitos separados, guardas pós-LLM para os
  2 FPs reais do spike: condicional "ggf." → unclear, frase DEI → not_mentioned) →
  record pydantic (`schema_version=1`) → JSONL incremental com escrita atômica.
  Como rodar: `scripts/enrichment_run.py --dry-run` (plano, zero rede) e, com
  `NVIDIA_API_KEY` exportada no env, `scripts/enrichment_run.py` (sequencial,
  16–290s/vaga; cache por job_id+final_url+content_hash; retry 3× backoff
  30/60s em 429/5xx/rede/vazio/parse_error). Onde persiste:
  `data/enrichment/enrichment_results.jsonl` (gitignored, key=job_id, upsert com
  preservação de sucesso por content_hash). O que NÃO faz: não altera
  eligibility/score/ranking, não usa LLM como filtro/decisor, não integra ao
  HTML/Telegram/Pages, sem browser (JS-render fica `js_rendered`). Testes:
  `scripts/test_enrichment.py` no CI (33→34; 114 checks offline, TUDO OK); suíte no
  clone 33/34 (única falha = drift pré-existente do `test_visa_policy`). Detalhes:
  `docs/enrichment.md`.

- **Enrichment Fase 2 (incremental) — 26/09, PR #82 MERGEADO (squash
  `ce40285`; CI do PR verde ×2 + CI main pós-merge verde, membership dos
  testes novos conferida no log do run)**: a camada virou
  processo incremental integrado ao refresh diário, sem mudar
  score/eligibility/ranking/Telegram/HTML. Delta por `(job_id, final_url,
  content_hash)` sobre o **corte do ranking `--top-n` (default 30, decisão
  do dono 26/09 — só o topo do dia entra no plano; vagas fora do corte
  nunca acumulam backlog e são cobertas ao reentrar)** (planejamento
  new/retry/seen + fetch sweep do corte + cache_hit sem LLM); pool
  `retry → new → changed/changed_source` com cap `--limit` (default 24
  extrações LLM/run; backlog máx ~30 — cap 24 quase esvazia no dia
  seguinte); `refresh_daily.py --enrichment --enrichment-limit N
  --enrichment-top-n N` (default OFF; gate único `publication_allowed`;
  key env/.env injetada no subprocesso; exit do refresh NUNCA muda);
  concorrência via flock (exit 3); preservação com pendência
  (`pending_content_hash` — falha de conteúdo novo não apaga o último sucesso
  válido); health em `data/enrichment/enrichment_status.json`; exit codes 0/1/2/3.
  Cron de produção ativado com `--enrichment` (26/09) + `NVIDIA_API_KEY` no
  `.env`. Fix no mesmo PR: fixture do `test_personal_tracker` com deadline
  fixo expirou (quebrou o CI da base) — deadline agora relativo.
  Testes offline: `test_enrichment.py` 114→159 checks (+6 do corte top-N),
  `test_refresh.py` +27 (gate, exit inalterado, key ausente pulada com log,
  propagação `--top-n`); zero API NVIDIA. Detalhes:
  `docs/enrichment.md` (reescrito para a fase 2) e Log 26/09 do MASTER_PLAN.

- **Enrichment Fase 3 (integração aos produtos) — 26/09, PR #83 MERGEADO (squash
  `19b0972`; CI do PR verde ×2 — membership `test_enrichment_present` conferida no
  log do run, array 34→35 — + CI main pós-merge verde)**: o enrichment agora INFORMA
  os três produtos sob a regra "Deterministic pipeline decides. LLM enrichment
  informs." — A/B programático comprovado (sequências data-score/data-job-id/data-rank
  IDÊNTICAS com/sem enrichment; zero diff em ranking/filters/app_intel/publish/
  refresh). Novo `enrichment/present.py` (view read-only: `not_mentioned`→omissão
  nunca "não", `unclear`→"incerto", PIP=false invisível, stale por
  `pending_content_hash`, evidências ≤200 chars escapadas e rotuladas "trecho citado
  da página oficial"). Ranking HTML: bloco "🔎 Análise da página oficial (LLM)" por
  vaga + chip 🔎 LLM (auto-detect do store — a página pública ganha enrichment sozinha
  no próximo run). Candidate Fit: linhas enr_* ADITIVAS após os sinais determinísticos;
  `eu_citizenship_required=true` → ⚠ (teampicnic #8/#9, evidência real). Telegram:
  seção "🔎 Enrichment — dados da página oficial (Top 5 com análise)" antes do link,
  best-effort (sem store → seção some; corrompido → idem). Cobertura medida (spec
  §11, `scripts/enrichment_coverage.py`): student 78% · internship 78% · location
  78% · english 78% · german 56% · salary 22% · work_mode 22% · deadline 0% ·
  eu_citizenship 22% — NENHUM campo entra no score (§12: candidato futuro denso =
  eu_citizenship_required, decisão do dono). Testes: `test_enrichment_present.py`
  NOVO (75 checks, 35º no CI) + interface (152) + digest (82); suíte VPS 34/35 —
  `test_lifecycle` falha PREEXISTENTE na base (reproduzida em worktree limpo; passa
  no CI). Detalhes: Log 26/09 (Fase 3) do MASTER_PLAN e `docs/enrichment.md`.

- **Fase B — Consumo dos campos estruturados do `raw` — 27/09, PR #85 MERGEADO (squash `3cd7424`; CI do PR verde ×2 no SHA `0db1899` — membership `test_structured_fields` nos logs de ambos, array 36→37 — + CI main pós-merge verde; produção `data/` intocada)**: novo `src/internship_finder/structured_fields.py` (acessores puros read-only sobre `job["raw"]`, padrão `opportunity_intel`) + métricas de conflito (`employment_type_relation`, `remote_relation`). Consumido: `apply_url` → botão "candidatar-se" quando ≠ `job.url` (`job.url` nunca substituído); `department` → linha "área:" nos detalhes; enum `employment_type` → linha "classificação ATS" só quando difere do label exibido (0 ocorrências no dataset). `commitment` = origem do label canônico (57/61) — permanece evidência. Cobertura (411 eligible): department 63,3% · enum ET 17,5% (INTERN 9) · is_remote 71 · apply_url 22 (16 úteis) · requisition_id 119 · global_id 100%. Conflitos: ET **17 match / 55 conflict / 339 missing** (enum = regime do contrato, não natureza da vaga) — NUNCA substitui o filtro de tipo; remote 70 match / 1 conflict. requisition_id: 112 únicos, 7 dups/tenant = 4 mirrors DE/EN legítimos (Bosch ×3, ABOUT YOU) + 3 FPs → req_id sozinho não é chave de dedup; combinado com título normalizado é o caminho p/ uma futura Fase C (decisão do dono). global_id: único, 0 colisões — identidade P1.1 mantida. A/B: 0 diffs de score/ranking/Top 30; HTML idêntico exceto fragmentos aditivos. Produção real (run cron 27/09): 32 botões candidatar-se + 382 linhas "área" publicados. Testes: `test_structured_fields.py` (51 checks, 37º no CI); `structured_fields_coverage.py` manual. Suíte VPS: 37/37 estáveis (race do cron `test_countries` e drift pré-existente `test_visa_policy` explicados; ambos passam re-executados/CI). Docs: README + architecture.md. Detalhes: Log 27/09 do MASTER_PLAN.

- **Fase A — Hidratação seletiva de descriptions — 27/09, PR #84 MERGEADO (squash
  `7460a122`; CI do PR verde ×2 no SHA exato — membership `test_hydration` conferida
  no log, array 35→36 — + CI main pós-merge verde; suíte 36/36 rodada de forma
  independente pelo orquestrador)**: estágio entre dedup e rank preenche a
  description AUSENTE das vagas elegíveis via `ats-scrapers 0.3.0`
  `get_description` (detail por vaga, best-effort — falha não derruba o run nem
  muda exit codes; budget 600s). ATS com endpoint: SR/WD/EF/PS; softgarden no feed
  (`include_descriptions=True` local na coleta, custo zero); phenom pendente (29
  teasers só contados). Proveniência: `Job.description_source` ("hydration" vs
  ausente=feed). Métricas: registro `type: hydration` no JSONL (coverage
  antes/depois, por ATS, feed vs hydration, duração). A/B (staged 26/09, 411
  eligible): B1 sem hidratação = 0 divergência; B2 real 77/77 em ~58s, cobertura
  **79,8% → 98,5%**; 74 scores mudaram APENAS em language/skills (detectores
  existentes vendo texto novo — 0 mudança nas não-hidratadas; critérios/pesos
  intocados). Relatório: `~/.hermes/handoff/hydration-fase-a/relatorio_fase_a.md`;
  Log 27/09 do MASTER_PLAN.

The project is a working company-oriented ATS collection pipeline (collection →
filtering → dedup → ranking), with SQLite persistence, structured error codes,
observability (health), CI and standardized requirement tracking in
`MASTER_PLAN.md`. Since the **Fase 4 (19/09)**, the eligible set feeds **two
independent rankings**: the main profile (`ranking.py` — Supply Chain /
Procurement / BI / Analytics / Automation) and the **Materials Engineering
profile** (`materials_ranking.py` — `materials_score`/`materials_breakdown`
own components; the main score is never touched and never summed). Same 476
eligible jobs, no new collection/filters/dedup; the public page has a
profile switcher and the Telegram digest a compact "Perfil Materials
Engineering" section. Details in the MASTER_PLAN log (19/09, FASE 4) and
`docs/relatorio_fase4_perfil_materials.md`.

Current collection scope includes **101 evaluated/operational companies**
(12 initial + 27 E2 expansion + 25 added 08/09, P3 #23 — Lote A: 8 DE
(Allianz, Adidas, Puma, Hella, Fraunhofer, Merck, Boehringer Ingelheim,
HelloFresh; Otto removed 15/09 — false positive); Lote B: 17 NL/CH/AT (Philips,
ING, Heineken, Adyen,
Nestlé, Novartis, ABB, Red Bull, Roche, Swiss Re, Schindler, Shell,
Unilever, AkzoNobel, Rabobank, NXP, OMV); all validated with
`verify_companies.py --fetch` — match exato + scraper + fetch OK)
+ **17 added 15/09** (cobertura: Liebherr, STIHL, Simon-Kucher, BAUHAUS/bahagag,
BCG, MediaMarkt/mediasatur, Tchibo, HORNBACH, About You, Hager Group, Lanxess,
Linde, Sonepar, Flix, Kuehne+Nagel, Vattenfall, 4flow)
+ **6 added 16/09** (auditoria próxima onda: BMW AG, SMA, Jobs Festo, Wacker,
Webasto Jobportal, Roland Berger — nomes exatos do manifest; `successfactors:jobs`
compartilhado desambiguado por URL)
+ **9 added 17/09** (auditoria próxima fronteira: Picnic, cbs Corporate Business
Solutions, AIXTRON SE, Holzland Becker, CarOnSale, CURRENTA GRUPPE, Miebach
Consulting, Engelhart, audibene/hear.com — nomes canônicos = nomes exatos do
manifest)
+ **5 added 18/09** (última onda de cobertura: Sungrow EMEA, AutoScout24, Huawei
Research Center Germany, EAT HAPPY GROUP, VDI Technologiezentrum GmbH).
+ **Fase 6 (20/09)**: **Candidate Fit + Application Intelligence + Mobile UX** —
  conceitos separados do score de relevância (score = SÓ relevância; sinais de
  candidatura nunca entram nele). Novo `app_intel.py` (puro/determinístico):
  alemão por EXIGÊNCIA detectada no TEXTO (required −2,0 / preferred −0,5 /
  plus e sem menção neutros — fim do bônus por "conter alemão"; EN +1,5
  inalterado; `german_level` com negação explícita, CEFR, "von Vorteil",
  "English required, German is a plus"→preferido; "Deutsche Bahn"/"Deutschland"
  não contam), `work_authorization` (5 estados SÓ com evidência; 444/474 `not
  mentioned`), `deadline_kind` (employer vs validade do feed SuccessFactors
  [`g:expiration_date` = collected+30d, validado 295/295] vs none — SF nunca
  vira prazo/urgência/"vagas expirando"), urgency 🟢>14/🟡7–14/🟠3–6/🔴≤2,
  `candidate_fit`/`possible_problems`/`quality_flags`/`application_readiness`.
  Interface: chips por vaga, bloco "sinais de candidatura e possíveis
  problemas", seção "Como este ranking funciona" com PESOS REAIS das
  constantes (nada duplicado), filtros novos (vagas expirando ≤2/≤7/≤14 — só
  deadline confiável; work auth; idioma; Top 30; quality flags; contador
  "Filtros (N)"), **mobile: tabela → card <760px** sem scroll horizontal,
  dark mode, `--ref-date`/`--db-join` (freshness first/last_seen). Ranking
  real (run 20/09, 474 vs archive 19/09, 476): 448 comuns; **278 (62%)
  mudaram** (deltas −2,5×148, −2,0×30, −1,0×73, −0,5×27); Top 30: 23 ficam,
  7 saem/7 entram (saídas = alemão exigido). Suíte local **28/28**, CI 27→28
+ **Fase 7 (20/09)**: **Company & Location Intelligence** — camada de
+  desempate SEPARADA do score (Job Fit) e do Candidate Fit (Fase 6):
+  Opportunity Intelligence em `opportunity_intel.py` (funções puras) +
+  arquivos curados versionados `company_intel/*.json` (12 empresas e 12
+  cidades com fonte+qualidade+data). Empresa (setor/porte/sede/internacional/
+  áreas/site/carreiras), benefícios (só com fonte — nenhum presumido),
+  carreira (evidência oficial), Internship→Full-time (Explicitly supported/
+  Evidence available/Not mentioned/Unknown — nunca probabilidade), turnover
+  (fato com fonte e período), salário SOMENTE quando citado no anúncio
+  (18/474 no run 20/09: STIHL 2.117 €/mês, Bayer 2.280 €), work mode por
+  evidência (hybrid 91/remote 5/on_site 105), cidade real da string (108
+  cidades; "Germany" não vira cidade), custo de vida contexto (Numbeo
+  ago–set/2026, 12 cidades). Interface: seções recolhíveis por vaga
+  (Empresa/Benefícios/Carreira/Pathway/Localização/Salário/Turnover/Fontes)
+  + Compare opportunities (2–4 vagas; fatores; sem vencedor automático).
+  NADA entra no score; ranking intocado (data-scores idênticos ao snapshot);
+  zero rede em tempo de render (arquivo ausente → Not available, página
+  continua). Suíte local **29/29**, CI 28→29. Relatório:
+  `docs/relatorio_fase7_company_location_intel.md`.
+ **Fase 8 (22/09)**: **Decision Support + Application Tracking + Feedback
+  Loop** — camada de decisão PESSOAL, separada do ranking:
+  `scripts/personal_tracker.py` (CLI novo) + banco SQLite PRIVADO
+  `data/personal/jobs_personal.db` (job_status/job_events/job_applications;
+  PK = `Job.id` canônico). Status (new→interesting/review→applied→
+  interview→offer/rejected; withdrawn/ignored), prioridade pessoal
+  (high/normal/low — nunca afeta o score), notas, candidaturas (data/
+  resposta/entrevista/contato), feedback de gostei/ignorei (motivos livres,
+  collect-only — §12: NUNCA altera pesos), histórico append-only com
+  `sync-ranking` diário idempotente (vaga que sai do ranking/ATS ganha
+  evento e NUNCA é apagada — §19). Telegram: `personal_sections` no digest
+  (⚠️ Application reminders com deadline EMPLOYER ≤3 dias apenas — SF
+  feed nunca; 📌 aguardando resposta; notas nunca enviadas; banco ausente
+  → seções vazias, run segue). Interface pública: hint por vaga com o
+  comando do tracker + `data-job-id` (ZERO dado pessoal no HTML — Pages
+  estático/público, limitação documentada); comparação = reuso do Compare
+  Fase 7. Export CSV local; metrics/funnel/ranking-feedback descritivos.
+  Ranking/filtros/coleta intocados (data-scores idênticos; nenhuma função
+  de ranking chamada pelo tracker). Suíte local **30/30 — 1.564 checks —
+  0 falhas** (test_personal_tracker: 20 itens do §25; CI 29→30). Relatório:
+  `docs/relatorio_fase8_decision_tracking.md`.
  (`test_app_intel.py` novo; `test_interface` +11 casos node + Fase 6).
  Detalhes: `docs/relatorio_fase6_candidate_fit.md`. Status pessoal =
  evolução futura (página estática, sem backend); Company Intelligence
  (Fase 7) NÃO implementada.
+ **Fase 5 (19/09)**: camada **PT-BR determinística** na interface (`src/internship_finder/ptbr.py` — novo: glossário ≈80 entradas, `title_pt`, `detect_language`, `employment_type_pt`, `country_label`, `relevance_signals`); o HTML público mostra **título PT-BR como campo separado** (original sempre visível com tag `Original (EN/DE)`, 467/476 títulos traduzidos), tipo do anúncio e país em PT-BR, e o bloco **"por que esta vaga?"** explica cada componente REAL do breakdown do perfil ativo em PT-BR (penalidades separadas em "o que reduziu a nota"). SEM tradução integral de descrições, SEM LLM/API/serviço externo; `ranking.py`/`materials_ranking.py`/filtros/dedup/coleta **intocados**. Suíte local **27/27 scripts — 1.345 checks — 0 falhas** (test_ptbr: 59 checks, CI 26→27). Detalhes: `docs/relatorio_fase5_ptbr.md`.
+ **Fase 4 (19/09)**: segundo perfil **Materials Engineering** — `src/internship_finder/materials_ranking.py` (novo): o MESMO conjunto elegível (476) ganha `materials_score`/`materials_breakdown` próprios (materiais/metais/polímeros/cerâmicas/superfície/corrosão/ensaios + manufatura/processo; quality/R&D gated por contexto técnico; penalidades de função de negócio no título); `score` do principal intacto por id; interface com **seletor de perfil** (2 tabelas na mesma página, JS da Fase 3 reusado); digest do Telegram com seção "Perfil Materials Engineering" (Top 5 + novas no Top 30). Verificado: 476/476, rankings independentes, topo = polímero/beschichtung/verfahrenstechnik/bateria; suíte **26/26** (test_materials_ranking no CI).
+ **Fase 3 (18/09)**: interface do ranking reescrita (`scripts/interface.py` —
apresentação pura): a página pública mostra **todas as vagas elegíveis** (476)
com resumo no topo, **filtros/ordenação client-side** (JS vanilla embutido,
sem backend), posição = posição no ranking do pipeline, badge Top 30 e
"por que este score" com os componentes reais do `score_breakdown`;
pipeline/pesos/filtros/dedup intocados; `publish_pages.py`/`refresh_daily.py`
intocados (regeneração diária automática preservada). Detalhes no Log do
MASTER_PLAN (18/09, FASE 3).

Latest documented full runs (cron 06:00 UTC; reproduced offline by `scripts/coverage.py` and the current pipeline). **Current snapshot = 18/09 run** (1st with 101 companies); earlier runs below are historical records:

- **18/09 (current): 72,866 raw → 6,635 student-type → 1,411 target-area → 507 Germany → 476 eligible (dedup −31)** — registry at **101 companies**; CI suite **23/23 scripts — 1033 checks — 0 failures** (re-run 18/09, on the #65 head); 65 companies / 50 tenants with eligible jobs (BMW AG 81, SAP 74, BoschGroup 48, Volkswagen AG 23, teampicnic 20, Fraunhofer-Gesellschaft 19, Knorr-Bremse 15, Liebherr-International S.A. 13, BASF SE 13, STIHL 12); ATS (eligible): successfactors 296, smartrecruiters 54, greenhouse 33, phenom 24, workday 16, recruitee 14, eightfold 12, cornerstone 10, softgarden 6, ashby 4, personio 4, teamtailor 3; scores min 1.0 | median 6.25 | max 17.5; health: 3 alerts (all documented external/legitimate: Lidl timeout ×15, Kuehne+Nagel cornerstone ×3, SMA oracle homonym ×2)
- **17/09 (histórico): 71,735 raw → 414 eligible** — registry at 96 companies (1st run with 96)
- **16/09 (histórico): 69,586 raw → 5,813 student-type → 1,167 target-area → 355 Germany → 331 eligible (dedup −24)** — registry at 87 companies; 47 companies / 35 tenants with eligible jobs
- **14/09 (histórico): 60,222 raw → 281 filtered → 257 eligible (dedup −24)** — registry at 65 companies; CI suite 23/23 — 958 checks
- 06/09 (histórico): 37,953 raw → 3,080 student-type → 752 target-area → 246 Germany-eligible → **222 eligible** (dedup −24)
- 07/09 (histórico): **37,957 raw → 220 eligible** (dedup −24; 43 tenants ok / 2 empty / 1 timeout / 1 error — falhas recorrentes conhecidas: moka Bayer + Lidl timeout, ver MASTER_PLAN P3 #36)
- Companies/tenants with eligible jobs and the ATS breakdown below were measured on the 06/09–07/09 runs (histórico; the ATS figures sum to the 06/09 total of 222):
  - 24 companies / 20 tenants (source) with eligible jobs (SAP 71, BoschGroup 41, Volkswagen AG 20, BASF SE 17, Knorr-Bremse 16, ... — see README coverage table)
  - ATS (eligible): successfactors 150, smartrecruiters 41, eightfold 11, workday 8, phenom 5, ashby 3, greenhouse 3, cornerstone 1.

Scores (measured 06/09 — histórico): min 2.50 | mediana 6.75 | max 16.75 · 222/222 `country_iso='de'`.

With `INTERNSHIP_FINDER_GEOCODING=1` (Workday fallback, OFF by default): historical measurement over the 31/08 snapshot was 245 eligible (+9 Workday DE).

## Completed

- Company-based ATS discovery
- Exact company matching
- ATS scraper execution
- Subprocess timeout protection
- ATS-specific adapters
- Normalized `Job` model
- Internship/student filtering
- Target-area filtering
- Country filtering
- Deduplication
- Ranking
- JSON output (atomic write)
- CSV output (atomic write)
- E2 company expansion
- 39-company collection scope (E2 expansion, 2026-08-12 — **historical**; expanded to 65 on 08/09, P3 #23; registry today: **101** after the 15/09 → 18/09 waves)
- Post-audit corrections F1–F3 (parecer A, 2026-08-13)
- **P0 — Application deadline + hardening ACH-01..09** (PR #8, merged 31/08): `Job.application_deadline` (`datetime|None`, never inferred from `posted_at`), dedup per tenant, IDs without URL, JSONL metrics, exit code 2 on partial failure.
- **P0.1 — Workday Country/Location Resolver** (PR #9, merged 01/09): `geocoding.py`, cache-first, flag `INTERNSHIP_FINDER_GEOCODING` (OFF), adapter fallback after `infer_country_iso`; +9 Workday DE recovered with the flag on.
- **P1 #5 — SQLite persistence** (PR #10): `storage/sqlite_store.py`, flag `--sqlite PATH` (stdlib `sqlite3`), canonical Job schema + `first_seen`/`last_seen`/`active`/`archived`.
- **P1 #3 — CI GitHub Actions** (PR #11): `.github/workflows/ci.yml` runs the standalone suite (`scripts/test_*.py`) on a clean Python 3.12 runner; exit 0 = TUDO OK.
- **P1 #6 — Observability** (PR #12): `health.py`, flag `--health [PATH]` — JSON report per tenant/ATS over the JSONL + drop/recurring-error alerts.
- **P1 #7 — Structured error codes** (PR #13): `errors.py` (`CollectionError` + codes), structured queue payload, `error_code` in the JSONL.
- **P1 #8 — Multiprocessing lifecycle** (PR #14, merged 02/09): `fetch_with_timeout` with 4 outcomes (timeout / dead worker / erro / success), cleanup in `finally`.
- **P3 #18 — venv synced with `ats-scrapers` pin `ae0ad53`**: reinstall from the pin; SAP exposes `application_deadline` (1086/1086).
- **P2 #11 — Job validation forte** (PR #16, merged 03/09): pydantic validators on `Job` (empty `title`/`url` = validation error; empty optionals → `None`), `normalize_job_dict` for the filter path, adapter rejects missing titles (`NORMALIZATION_ERROR`, defensive), `test_validation.py` in CI.
- **P2 #12 — Country/domain module** (PR #17, merged 03/09): country/location logic extracted from `filters.py` into `countries.py` (constants + inference + spec functions, moved verbatim, behavior unchanged); `filters.py` re-exports the symbols (consumers untouched); `test_countries.py` in CI.
- **P2 #16 — test_ranking decoupled from the data snapshot** (PR #18, merged 03/09): fixed synthetic `FIXTURE` (18 jobs) + `test_fixture_ranking()` validating the ranking rules at rank level (top = target area, no senior in top, A-grade per area in TOP N, presales SCM preserved, SAP Analytics Cloud masked, marketing w/o area out of top 25%, JMP/trainee penalized); `test_real_data()` reduced to format invariants + observability; suite 16/16 local, deterministic; the 5 pre-existing failures are gone.
- **P2 #14 — Dedup 2.0 textual** (PR #19, merged 03/09): measured first on the real dataset (12 candidate EN/DE pairs, 4 TRUE duplicates of the same job escaping as `Praktikant`≈`Working Student`, `Intern`≈`Working Student`, `Internship`≈`Praktikum`); `TYPE_EQUIVALENCES` extended with word-boundary regex + repeated-token collapse in the bag; `Pflichtpraktikum`/`trainee` NOT touched (anti-tests); description kept OUT of the fingerprint (decided); baseline 236→**232** (4 TRUE dups, company+title+location); `test_countries` decoupled from the magic number 236 (subset invariant + delta observability); suite 16/16 local, CI run `33799148404` green.
- **P2 #13 — Company Registry operacional** (PR #20, merged 04/09, main `e7604db`, CI run `33840628495` green): `src/internship_finder/registry.py` is the single source of truth for the collection companies in code (39 when merged; the registry SEED now holds 65 — canonical name + reference ATS/tenant + `enabled`); `--registry` CLI flag collects the ENABLED entries (`--registry --companies "Bosch,SAP"` restricts to a subset, order preserved; plain `--companies` still works); per-company status is derived from the metrics JSONL via `company_status` (read-only, malformed records never crash) — design decision: **registry = configuration, JSONL = status**; `test_registry.py` added to CI (array now 13 scripts); README gained a "Registry de empresas" section.
- **P2 #15 — `--country` standardized and validated** (05/09): `parse_country_spec` now raises `ValueError` for non-ISO tokens or an empty spec (e.g. `de,xx`, `,`); the CLI converts it to `parser.error` (clear message, exit 2) before reading input/collecting. Previously an invalid value silently produced 0 jobs (`--country xx`) or ignored bad tokens (`de,xx`). Filter behavior unchanged for valid specs: baseline `--country de` → 232 identical ids (list-by-list); `europe` 371 / `all` 31006 / `remote` 1 unchanged. `test_countries.py` +21 checks (spec validation + CLI error block); suite 14/14, `data/` untouched.
- **P2 #10 — Zero-return + anomaly detection** (05/09): 3rd alert type in `health.py` (`_detect_zero_return`): a source whose most recent run (by `run_id`) is `empty` after ≥3 prior `ok` runs with jobs (`collected > 0`) → coverage regression; empty-consistent sources (`bamboohr:sap`, `smartrecruiters:sap`) never alert (anti-tests); gate mirrors the drop's spirit (1–2 oks = plausible fluctuation). `build_health_report` now emits drop + recurring_error + zero_return; `scripts/refresh_daily.py` formats it ("voltou a zero (empty) após N runs com vagas") — Telegram flows unchanged (anti-spam intact). Calibrated on the real history (4 runs): **0 zero-return alerts** (no source with ok>0 and empty — clean baseline); live health stays at the 1 factual alert. `scripts/test_zero_return.py` (offline, 20 checks) added to the CI array (now 15 scripts); suite 16/16 local; `data/` untouched (stat before==after).
- **P2 #17 — Daily refresh + alerts** (05/09): `scripts/refresh_daily.py` runs the real collection (`--registry --timeout 60`) daily with rotation of `data/` outputs into `data/archive/<ts>/` **before** the run (rollback = copy back), evaluates health via the existing `build_health_report` on the updated JSONL, and sends a Telegram alert **only on anomaly** (exit != 0 or drop/recurring-error alerts; 1 message per run, alerts deduped by source; `--always-notify` = optional daily digest; no token in `.env` → warning, no send, never crashes). `--dry-run` validates rotation+health+message in a synthetic tempdir without network or `data/` writes. Cron installed (05/09, 06:00 UTC, `flock -n` guard covering the whole run — absolute paths, corrected the same night after `flock ... cd ... &&` proved broken: flock execs via `execvp` and `cd` is a shell builtin; backups in `/tmp/crontab_backup_0509.txt` and `/tmp/crontab_backup_0509_v2.txt`). Tested offline (`scripts/test_refresh.py`, in CI — array now 14 scripts) and with one authorized real run: `2026-09-05T20:43:07` → 38.038 raw → 248 filtered → **224 eligible** (dedup −24), 43 ok / 2 empty / 1 timeout / 1 error tenants, health found the known `smartrecruiters:other` anomaly (70 runs) + a new real one (`successfactors:lidlstiftuP2`), Telegram answered `ok:true` (message_id 318). Rollback documented in README "Daily refresh". The metrics JSONL was sanitized the same night (05/09): only the 4 real runs' records kept (37.373 / 1.084 ×2 / 38.038 → 104 lines, 39 companies), removing mock junk (`smartrecruiters:other` 70×, `successfactors:acme` 140×); post-clean health shows one factual alert (`successfactors:lidlstiftuP2` — timeout 31/08 + 05/09).

- **P3 #20 — ACH validations, measured first** (06/09): (ACH-18) CSV contract decided — **JSON = complete source, CSV = tabular view**; `remote` column added to `CSV_COLUMNS` (was absent in 38.038/38.038 `jobs.csv` rows and 224/224 eligible rows; `description`/`raw`/`score_breakdown` intentionally stay CSV-out); (ACH-14) `--limit` semantics confirmed post-fetch per tenant (limit=2 → 2/tenant via mock) and the CLI now rejects `--timeout <= 0` / `--limit < 0` with a clear exit-2 error before collection (undefined behavior before: deadline=only margin, `[:-k]` slice); new offline `scripts/test_collect_flags.py` (19 checks) in CI (array 15→16); (ACH-16) `remote` field never populated by any ATS (0/38.038) — filter works via location text (101 markers, 1 remote-eligible), documented no-op; (ACH-17) country vs country_iso 0/38.038 mismatches (same inferred value by adapter construction), measured no-op; (ACH-20) 0 dates in DD.MM.YYYY anywhere (eligible + raw) — "no measured need", no parser; (ACH-19) BY removed from `EUROPE_COUNTRIES` (code contradicted the documented "RU/BY out" rule; 0 real `by` jobs). Local suite 17/17 TUDO OK from scratch cwd; `data/` untouched (stat before==after); funnel reproduced 38.038→224 identical.
- **P3 #21 — Dead code (ACH-13), reference audit** (06/09): every public symbol in `src/` (73 across 17 modules) and every non-test script was grep-audited repo-wide (src/, scripts/, .github/, docs, README, AGENTS — word-boundary) plus a pyflakes pass (throwaway /tmp venv, project venv untouched). No public symbol ended with 0 references — the minimum was `Score.to_dict` (0 call sites; real serialization is `d["score"] = score.total` / `score_breakdown`). Removed 16 zero-reference items, all behavior-neutral: `Score.to_dict`; unused `import json` in `health.py`; 4 dead re-export names in `filters.py` (`EUROPE_COUNTRIES`, `COUNTRY_NAMES`, `_country_name_from_location`, `_iso_token_from_location` — consumers import from `countries`; `COUNTRY_CODES`/`is_remote` kept, exercised by `test_compat_re_export`); unused imports/locals in 6 test files + `refresh_daily.py` (including `keys_w = dict(candidate_keys_for_audit := {})` walrus junk in test_dedup). Deliberate `# noqa: F401` imports kept (author intent); `CompanyResolver`/`company_status` kept (tested + documented public APIs); `__version__` kept (package convention). CI array unchanged (16); local suite 17/17 TUDO OK before and after from scratch cwd; `data/` untouched (stat before==after). Observation: README states `company_status` is "exposed by `--health`" but `cli.py` does not call it (doc≠code, out of scope).

- **P3 #31 — Corrections batch** (PR #31, merged 06/09, main `c2fcfb2`): Apprentice/Apprenticeship (EN learning programs) excluded like the DE Ausbildung rule (2 real VW jobs left eligible); `trainee` removed from `STUDENT_EMPLOYMENT_TYPES` (generic trainee no longer passes on `employment_type` alone; 0 jobs affected, measured); `read_metrics` skips malformed JSONL lines instead of crashing; `company_status` orders by `(run_id, timestamp)` instead of file position; `--health` now exposes `company_status` under the `companies` key (doc minus code gap closed). Funnel measured: 37,953 -> 3,080 -> 752 -> 246 -> **222** (before the fix: 248 -> 224). Suite 17/17 OK before/after; `data/` untouched.
- **P3 #30 — Operations batch** (PR #30, merged 06/09, main `d0a3ea1`): daily refresh now collects with `--sqlite data/jobs.db` (first_seen/last_seen/active/archived persisted in production; the `.db` is not rotated); archive cleanup with `--retention-days` (default 14, 0 = off, runs after each rotation); disk usage >80% adds a "⚠️ Disco: N% usado" line to the Telegram message; collection subprocess inherits the caller env; `requirements-lock.txt` added (snapshot of the resolved environment via pip freeze; reproducibility only — outside CI and the standard install; pyproject.toml remains the source of truth for declared dependencies). `test_refresh` 43->60 asserts; suite 17/17; `data/` untouched.
- **P2 #29 — Docs consolidation** (PR #29, merged 06/09, main `9477339`): P1 #5 SQLite registered as implemented (documental drift fixed) + P3 #30 gate checks 15:01 and 19:47 UTC (path B - gate not fired, PyPI still 0.3.0), both recorded in MASTER_PLAN log.
- **P3 #35 — Mensagem do Telegram didática** (07/09): template em linguagem natural ("X de Y fontes falharam", nomes de empresa via `company` do JSONL, códigos de erro traduzidos, "recorrente há N runs"); `test_refresh` +4 checks didáticos.
- **P3 #36 — Falhas recorrentes do refresh** (07/09): `pycryptodome>=3.20` no pyproject resolve `moka:bayer/148387` (Bayer — validação real na coleta do cron seguinte); Lidl timeout aceito como limitação monitorada.
- **Ata da auditoria 06/09** (07/09): `docs/ata_auditoria_0609.md` — registro permanente dos achados A1–A9 e ações (antes só na conversa).

- **P3 #22 — Data/code separation + Parquet + chunking: measured, no action** (08/09; full numbers in the MASTER_PLAN log): `jobs.json` is 114MB (37,957 jobs, ~3KB/job) and loads in 828ms; 3 consecutive runs show ~0% daily growth (38,038→37,953→37,957; churn ~116 ids/day, net ~0 — only the cumulative `jobs.db` grows, ~+0.13GB/year); real format measurements: gzip −9 = 14.4MB, parquet-zstd = 12.2MB, SQLite read 358ms, parquet-zstd read 52ms. Fixed thresholds declared before measuring (parquet only if JSON ≥1GB or read >10s; data repo only if `data/` ≥10GB or disk >75%; chunking only if a future #25 interface payload >10MB) — none hit, so no new dependency (pyarrow/pandas/duckdb stay out), JSON/CSV/SQLite contracts untouched, cron/refresh untouched. Reopen condition recorded in MASTER_PLAN #22. `data/` untouched; suite 17/17 OK from scratch cwd.
- **P2.5 — Benchmark do ranking: medido, NÃO alterado** (11/09; PR #45): `benchmarks/ranking_benchmark_v1.json` (59 vagas reais do run 11/09 rotuladas manualmente: 5 ótima / 22 boa / 15 aceitável / 5 ruim / 12 falso positivo; justificativa + URL por vaga) + análise stdlib reproduzível. **Resultado**: universo 260 eligible (run 11/09/2026) com **96,5% das vagas empatadas** (39 scores distintos; maior grupo 7.5×33); concordância ordinal **82,5%** em 1.289 pares (tau +0,651 — o ranking tem sinal real); **67% das vagas empatadas da amostra em grupos com qualidade humana diferente** (até 3 níveis no mesmo score). **Decisão: Caso C — baixa resolução real**, sem evidência para redesign; hipóteses de calibração (H1 descrição ausente custa 3,0–3,75 pts na mesma vaga; H2 `language` não discrimina — FP 1,33 ≈ ótima 1,40; H3 desempate alfabético arbitrário; H4 FPs = gap de FILTRO, fora do ranking) em `docs/ranking_benchmark.md`. Ferramentas: `scripts/ranking_benchmark.py` (relatório determinístico), `scripts/make_ranking_benchmark.py` (refresh/validate — nunca grava benchmark inválido); `scripts/test_ranking_benchmark.py` no CI (19→20 scripts). Suíte local 20/20 TUDO OK de cwd scratch; `data/` intocada. Nenhum peso/formula/regra alterado.
- **Batch 12–13/09 (PRs #48–#53, merged)**: CI passa a instalar dependências via `pyproject.toml` — sem lista manual nem `--no-deps` (#48); papel do `requirements-lock.txt` documentado como snapshot, não lock declarativo (#49); `test_manifest.py` renomeado para `manifest_probe.py` — probe manual (rede), fora da suíte do CI (#50); `coverage.py` suporta zero vagas elegíveis sem `IndexError` (#51); escopo do registry consolidado 39/60 → 65 + `RegistryEntry.source` removido (#52); detecção de drift entre tenant do registry e tenant resolvido (#53). Com P3 #40 (backup do jobs.db, 13/09) e o README pós-auditoria com a suite 23/23 (#55), fecham a leva P1–P3 desta auditoria.
- **Fase 1 — GitHub Pages + cron 06:00 America/Sao_Paulo** (18/09; PRs #67 + #68; main `d36791c`; CI 24/24 — 1.062 checks): o ranking HTML local ganhou **publicação automática no GitHub Pages** — URL estável **https://rios-vini.github.io/internship-finder/** (repo público, source branch `gh-pages`/root; a branch contém só `index.html`, 472 KB). Fluxo: refresh diário → `scripts/interface.py` (mesmo HTML do uso local) → **`scripts/publish_pages.py`** (novo: gate `check_public_safe`, escrita atômica no clone de deploy `/home/ubuntu/internship-finder-ghpages`, commit+push da `gh-pages`; `--dry-run` para ensaio) → Pages. O refresh ganhou a flag **`--pages-dir`** (default OFF; habilitada no cron): publica só após o run com exit 0 + eligible > 0; falha de deploy não derruba o run (`publish_error` na mensagem Telegram/`run_info.json`) e a página anterior permanece no ar. **Cron**: era `0 6 * * *` UTC (= 03:00 BRT) → **`0 9 * * *` UTC = 06:00 America/Sao_Paulo** (UTC-3 fixo, sem DST no Brasil desde 2019; Vixie 3.0pl1 local **não suporta `CRON_TZ`** — testado com probe; comentário no crontab + README). Watchdogs `*/5` intactos. Segurança: `check_public_safe` + verificação do blob publicado (0 matches de `ghp_|TELEGRAM_BOT_TOKEN|/home/ubuntu|jobs.db`). Documentação: README (seção GitHub Pages + Cron corrigido), `docs/architecture.md`. Testes novos: `scripts/test_publish_pages.py` (28 checks), `test_refresh.py` +16.
- **Fase 2 — Telegram Daily Digest** (18/09; PR #70; CI 25/25 — 1.163 checks): o Telegram virou o **resumo diário do estado da busca** (ranking completo segue no GitHub Pages). Novo `scripts/ranking_digest.py` (funções puras, zero infra nova): compara o ranking do run contra o **snapshot da própria rotação** (`data/archive/<ts>/eligible_jobs.json` — estado anterior já copiado antes da coleta desde o P2 #17; nenhum arquivo/banco novo). Seções anexadas à mensagem única do refresh_daily: perfil/critérios ativos (**pesos lidos das constantes vivas** de ranking.py/filters.py — nada duplicado), **novas vagas no Top 30** (id ausente do ranking elegível anterior; "nova" ≠ "subiu" — vaga antiga que entrou vai para "Entraram no Top 30"), Top 5 atual, mudanças (entradas/saídas + movimentos ≥ 5 posições), link do GitHub Pages (sempre a última linha). Gates: digest só com exit 0; falha ao montar nunca derruba o run; **limite do Telegram (4096 chars)** — run com muitas anomalias preserva a mensagem base e o digest vira 1 linha compacta com o link. **Cron**: linha ganhou `--always-notify` (digest diário todos os dias). Testes: novo `scripts/test_digest.py` no CI (24→25), `test_refresh.py` +2 blocos, e **testes órfãos da Fase 1 registrados** (com fix de fixture em `test_pages_dir_integrado`: type:run gravado DURANTE a coleta fake, como o CLI real — antes o snapshot de linhas zerava o resumo e `publish_ranking` recebia eligible 0). Suíte local 25/25, 1.163 checks, 0 falhas; mensagem real (18/09: 476 vs 414 → 5 novas no Top 30) enviada ao Telegram **ok:true**. [ver MASTER_PLAN Log 18/09]
- **Fase 4 — Segundo perfil Materials Engineering** (19/09; PR #73; main `9ad6bf8`; CI 26/26): o MESMO conjunto elegível é classificado por dois rankings independentes — `src/internship_finder/materials_ranking.py` adiciona `materials_score`/`materials_breakdown` próprios (núcleo de materiais + adjacentes industriais + contexto quality/R&D gated por contexto técnico no título + tipo + local + penalidades de função de negócio no título); `score`/`score_breakdown` do principal INTACTOS (nunca somados); elegibilidade/coleta/dedup inalteradas. Interface (`scripts/interface.py`): seletor de perfil `[Procurement / Supply Chain | Materials Engineering]`, duas tabelas na mesma página reusando o JS da Fase 3 (filtros/ordenação por perfil); `render_html` sem `materials` = página da Fase 3 idêntica. Digest (`ranking_digest.py`): seção "Perfil Materials Engineering" (Top 5 + novas no Top 30 Materials) na mesma mensagem, link continua última linha. Testes: `test_materials_ranking.py` no CI (25→26), interface +22 checks, digest +9; suíte local 26/26. Validação real (run 19/09, 476): mesma quantidade, business intacto por id, Top 30s independentes, vagas de polímero/beschichtung/verfahrenstechnik/bateria no topo, topo do principal cai para #215 no materials; DOM real (jsdom) 25/25 checks; docs em README/architecture/MASTER_PLAN/PROJECT_STATUS + `docs/relatorio_fase4_perfil_materials.md`. [ver MASTER_PLAN Log 19/09]

## Next priorities

- **P1–P3 desta leva: fechados e comprovados (auditoria 14/09)** — não existe defeito técnico conhecido em aberto. O que permanece abaixo é **monitoramento** de itens externos/operacionais (Lidl timeout, gate de versão do `ats-scrapers`) e **decisões futuras de escopo/produto** (P3 #24, próximas ondas de expansão) — não dívida técnica aberta. Expansões concluídas desde então: **65→87→96→101** (ondas 15/09 a 18/09, PRs #59, #62, #65; 18/09 = ondas de cobertura encerradas por decisão do dono).
- **P3 #20/#21/#29/#30/#31 complete** (06/09 - see Completed). Backlog remainders:
  - **P3 #22**: DONE (08/09) — measured, no action (see Completed); reopen if jobs.json > 1GB or read > 10s or data/ > 10GB
  - **P3 #23**: international expansion + more DE companies (39→60→100) — **DONE 08/09** (39→65, 26 validated; 22 rejected with evidence; 65→87 on 15/09+16/09 waves, PR #59; 87→96 on 17/09, PR #62; 96→101 on 18/09, PR #65 — **expansão de cobertura encerrada por decisão do dono em 18/09**) — see MASTER_PLAN #23
  - **P3 #24**: aggregators (LinkedIn/Indeed/Glassdoor) - needs owner scope decision
  - **P3 #25**: simple interface (top jobs, filters, link) — **DONE 08/09**: `scripts/interface.py` (HTML auto-contido, stdlib, zero deps novas) + `scripts/test_interface.py` no CI (array 16→17) — see MASTER_PLAN #25
  - **P3 #37**: health agora agrega por (source, company) — **DONE 08/09** (PR #39): elimina falsos drops em tenants compartilhados (phenom:nan 6 companies; successfactors:jobs 9); run 08/09 pós-fix: 1 alerta (só Lidl); CI 17 scripts. See MASTER_PLAN #37
  - **P3 #40**: backup simples do jobs.db — **DONE 13/09** (PR #54, squash `e07b7e9`): snapshot via backup API do sqlite3 (stdlib) pós-coleta no refresh (`data/backups/jobs-<ts>.db`, artefato standalone sem sidecars WAL), manual via `scripts/backup_db.py`, retenção `--backup-retention-days` (default 14), falha reportada no Telegram sem derrubar o run; `scripts/test_db_backup.py` no CI (22→23); RESTAURAR = `cp data/backups/jobs-<ts>.db data/jobs.db`. See MASTER_PLAN #40
  - **P3 #30**: stays monitored - re-check when upstream releases >=0.4.0 or an install/import failure appears (last check 06/09 19:47 UTC: gate not fired, range kept)
- **P3 #36 (lidl)**: timeout 85s aceito como limitação monitorada — reavaliar quando o ats-scrapers ganhar timeout por fonte ou a Lidl mudar de tenant.
- Full ranked plan (P0–P4, status ✅/⏳): see `MASTER_PLAN.md` (source of truth).

## Known limitations

- Nenhum item abaixo é defeito técnico conhecido em aberto — são limitações documentadas, fatores externos ou itens de monitoramento (comprovado pela auditoria final de 14/09).
- Some Workday tenants do not expose country information clearly enough for the current country filter (documented; nothing fabricated). **Partially mitigated** by the optional `geocoding.py` fallback (OFF by default; +9 Workday DE when enabled; network geocoding only with the flag on).
- **`application_deadline` em tenants SuccessFactors (P1.4, provado por origem — NÃO é bug):** o feed RSS de Google Merchant (`<host>/sitemal.xml`) publica `g:expiration_date` com **um único valor por feed, igual a `data do feed + 30 dias`, aplicado a todas** as vagas (ex.: feed 11/09 → `2026-10-11`). Trata-se de um horizonte de validade gerado pela própria plataforma (a fonte), não de um prazo de candidatura definido pelo empregador. **O valor VEM DA FONTE**: ats-scrapers 0.3.0 só parseia `g:expiration_date` e o adapter deste projeto só mapeia/parseia — nenhuma camada soma +30 dias nem aplica default. Verificado por reprodução em 4 feeds (SAP/Kaufland/ZF/AkzoNobel) e por auditoria de código. Por isso **não se remove** o valor por heurística de `+30 dias`/frequência (um prazo real que coincida com +30 seria apagado); a interface deve tratar esse campo em SuccessFactors como "providenciado pela fonte", não como prazo garantido do empregador.
- Some companies/ATS combinations currently fail or are excluded for documented reasons (Siemens/teamtailor inativo; re-probe pós-release do PR #285 upstream; Mercedes-Benz/ThyssenKrupp/Kärcher/Heraeus/Aurubis/Rheinmetall/Nordex/SEW/Lenze/Beckhoff/Arvato/BLG/Dachser/Bechtle/Jungheinrich/KUKA sem match real no manifest 17/09 — nunca no SEED; BMW entra somente como "BMW AG" desde 16/09 — a consulta "BMW" sozinha continua FP (`join_com:bmw-kuehnert`); Hager Group e Lanxess foram ADICIONADAS ao SEED em 15/09 (coletam OK no ats-scrapers 0.3.0 — "XML malformado" era limitação do pin antigo); Symrise/ifm/Kerkhoff/Efficio seguem bloqueadas pela API join.com 422 (reconfirmado 17/09); GFT: FP icims:gannettfleming (283 vagas EUA) e workable:gft EMPTY; tenant real da GFT é `sf:jobs` jobs.gft.com (0 eligible DE medido 17/09; exigiria nome canônico longo); Rhenus exige fix `URL_SLUG_ATS`+"adp" (medido pós-fix: 3 raw, 0 eligible)).
- **3 falhas recorrentes DOCUMENTADAS e legítimas (continuam no health/refresh de propósito — não silenciar; investigadas 17/09, PR #64)**: Lidl `successfactors:lidlstiftuP2` timeout ×15 runs (feed externo enorme sob demanda); Kuehne+Nagel `cornerstone:kuehne-nagel` NXDOMAIN (empresa válida coletada via phenom:nan); SMA `oracle:fa-exow-saasfaprod1/cx_1` homônimo externo (sem exclusão específica, decisão 17/09).
- Eligible count (current, documented): the daily cron regenerates `data/eligible_jobs.json` (**18/09 run: 476 eligible** — 72,866 raw → 6,635 → 1,411 area → 507 DE, dedup −31, registry 101). Historical figures: 17/09 → 414 (71,735 raw, registry 96), 16/09 → 331 (69,586 raw, registry 87), 14/09 → 257 (60,222 raw), 07/09 → 220 and 06/09 → 222 (the 222→220 drift was documented in the 07/09 update); older numbers in docs (236/232 from the 31/08 snapshot) are historical. The 476 number is the eligible count of the supported ATS/registry universe — **not** an estimate of the entire German market.
- Eligible tail (measured 18/09): **0 formal bachelor-degree titles** (Bachelor of.../Praxisverbund rules since 16/09 — PR #61; SmVdP since 15/09) + **27 academic-thesis titles** (Abschlussarbeit/Bachelor-/Masterarbeit/Thesis — accepted by the 15/09 thesis rule, not a regression); candidates for future pattern extension.

Data in `data/` is local and gitignored: numbers serve as collection documentation, not as versioned files.

See `docs/` for detailed collection, correction and expansion reports (they are historical).
