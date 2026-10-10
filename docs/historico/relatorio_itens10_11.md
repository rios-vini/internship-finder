# Relatório — Itens 10–11 da auditoria pós-Fases 1–8 (Work Authorization vocab + visa_policy)

**Data**: 2026-09-24 · **Branch**: `feature/audit2-itens10-11` ·
**Estado**: suíte local 33/33 (1.834 checks, 0 falhas) · **Fonte de verdade**:
MASTER_PLAN.md (Seção 1 + Log) + PROJECT_STATUS.md + este relatório.

## 1. Arquivos alterados/criados

| Arquivo | Tipo | Conteúdo |
|---|---|---|
| `src/internship_finder/app_intel.py` | alterado | Item 10: `_WA_VOCAB` (+`arbeitsgenehmigung`, `+aufenthaltstitel`; `relocat\w*` removido), `_WA_SUPPORT` bidirecional com gabarito `_WA_THEME`/`_WA_VERB` + custeio, `_WA_NO_SUPPORT` expandida (negações EN/DE), `_WA_EXISTING` expandida (already/vorhanden/EU passport) |
| `scripts/test_app_intel.py` | alterado | +43 casos no `test_work_authorization` (FNs/FPs da spec, negações contrapartes, HTML entities, determinismo 100x); fix do invariante de deadline (dupla contagem pré-existente) |
| `src/internship_finder/opportunity_intel.py` | alterado | Item 11: `VISA_POLICY_STATES` (5 estados) + `visa_policy_state(intel)` (padrão `pathway_state`; default `not_verified`) |
| `src/internship_finder/ptbr.py` | alterado | `VISA_POLICY_LABELS` PT-BR (estilo `PATHWAY_LABELS`) |
| `scripts/interface.py` | alterado | `_job_opportunity` ganha `visa_policy`; nova seção recolhível "Política de visto (empresa)" com rótulo PT-BR + fonte (URL + checked) via `sources_for.visa_policy` |
| `scripts/test_visa_policy.py` | novo | 33º script do CI (43 checks): estados, default, curadoria, INDEPENDÊNCIA empresa×vaga, score intocado, ranking do snapshot |
| `company_intel/company_intelligence.json` | alterado | `visa_policy` nas 12 empresas (2 unclear c/ fonte, 10 not_verified c/ nota); NENHUM outro campo alterado (diff cirúrgico: 44 insertions/12 deleções) |
| `.github/workflows/ci.yml` | alterado | Array 32→33 (`test_visa_policy`) |
| `MASTER_PLAN.md`, `PROJECT_STATUS.md`, `README.md` | alterados | Seção 1 + Log 24/09; métricas pós-item 10/11; seção Fase 7 |
| `docs/relatorio_itens10_11.md` | novo | Este relatório |

## 2. Padrões WA adicionados (grupo → padrões novos)

- **`_WA_VOCAB` (tema)**: `arbeitsgenehmigung\w*`, `aufenthaltstitel\w*`.
  REMOVIDO: `relocat\w*` (relocation = mudança de cidade, não
  imigração/autorização — FP2 da spec).
- **`_WA_SUPPORT` (suporte)** — gabarito bidirecional (`_WA_THEME` =
  visa|visum|work permit|working permit|arbeitserlaubnis|
  arbeitsgenehmigung|aufenthaltserlaubnis|aufenthaltstitel|residence
  permit|work authorization|right to work|immigration; `_WA_VERB` =
  support|assist|help|unterstütz*|unterstuetz*|hilfe*|übernehm*|
  uebernehm*|übernahme|uebernahme|begleit*|behilflich):
  - ordem direta `sponsor…→tema` estendida a `arbeitsgenehmigung`/
    `aufenthaltserlaubnis`/`residence permit`;
  - `tema…{0,25}→verbo` ("We support you with the visa process",
    "Assistance with visa application provided");
  - `verbo…{0,30}→tema` ("Wir unterstützen bei der Beantragung eines
    Visums", "Support with residence permit application");
  - **custeio**: `(übernahme|uebernahme|coverage|covering)… visa(gebühren|
    kosten|gebuehren|costs?|fees?)` e `visa…(costs?|kosten…)…{0,20}(covered|
    paid|übernommen|by us|wir)` ("Übernahme der Visakosten", "visa costs
    covered by us").
- **`_WA_NO_SUPPORT` (negação — precedência máxima)**: `no (visa|work
  permit|work authorization|residence permit) (support|assistance|
  sponsor|help)`; `(not|cannot|do not|doesn't)…{0,20}(provide|offer|give|
  help)…{0,20}(visa|work permit|arbeitserlaubnis|residence permit)`;
  `cannot help with (the) (visa|work permit…)`; DE: `kein* (unterstützung|
  hilfe)…{0,25}(visa|visum|arbeitserlaubnis|arbeitsgenehmigung|aufenthalt|
  erlaubnis)`; `(ohne|kein*) übernahme der visa*`; custeio negado:
  `visa…costs…{0,15}not…{0,15}(covered|paid|included|übernommen)` e
  `visa…kosten…{0,15}nicht…{0,15}(übernommen|getragen|erstattet)`.
- **`_WA_EXISTING` (requisito existente)**: estendido a
  `arbeitsgenehmigung`/`aufenthaltstitel`; verbos DE
  `erforderlich|vorausgesetzt`; "Nicht-EU-Bürger" com `bürgerinnen?` e
  partícula opcional (padrão real do dataset: "Für Nicht-EU-Bürger:
  gültiger Aufenthaltstitel erforderlich"); "must/need/have/should +
  already + hold/possess/have + tema" (EN, ordem direta e inversa:
  "Candidates already possessing a work permit are eligible");
  DE: `vorhandene(r|m|s) (arbeitserlaubnis|aufenthaltstitel|
  arbeitsgenehmigung|aufenthaltserlaubnis)` e `tema…{0,20}bereits
  (vorhanden|vorliegen|besitzen)`; EN: `valid EU passport required` /
  `eu passport (required|necessary|needed)`.
- **Precedência INALTERADA**: `no_sponsorship > support >
  existing_required > unclear > not_mentioned`. O caso combinado
  "must have valid work permit + we sponsor visas" continua `support`
  (regra documentada: o aviso mais útil ao candidato).

## 3. Distribuição WA antes/depois (snapshot 23/09, 391 eligible)

| Estado | Antes | Depois | Δ |
|---|---|---|---|
| support | 0 | 0 | 0 |
| existing_required | 23 | 23 | 0 |
| no_sponsorship | 0 | 0 | 0 |
| unclear | 6 | 4 | −2 |
| not_mentioned | 362 | 364 | +2 |

Total 391 == 391, ids idênticos. As expansões de suporte/negação/existing
não mudaram NENHUMA vaga real (medido: nenhum padrão novo casa no dataset
com par verbo-tema — ver §4). A única mudança real vem da direção 1
(relocation fora do tema).

## 4. Vagas reclassificadas (2 — por id, antes→depois, padrão responsável)

| id | Empresa | Antes | Depois | Padrão responsável |
|---|---|---|---|---|
| `celonis\|greenhouse:celonis:7814021003` | celonis | unclear | not_mentioned | remoção de `relocat\w*` do tema (única menção era "a possible relocation to Munich after" — mudança de cidade, sem visto no texto) |
| `celonis\|greenhouse:celonis:7819725003` | celonis | unclear | not_mentioned | idem (mesmo anúncio duplicado no feed, dedup preservado) |

Amostragem manual dos reclassificados (contexto verificado por grep no
texto cru): ambos os trechos falam APENAS de mudança de cidade Madrid→
Munich após onboarding — classificação nova `not_mentioned` está CORRETA
(nenhuma menção de visto/autorização; 0 falsos positivos na amostragem).

## 5. Falsos positivos e falsos negativos

**FPs corrigidos pela tarefa** (spec item 10, cobertos por testes):
- FP1 (precedência): "Applicants must already have a valid work permit.
  We can provide relocation assistance." → antes `support`, agora
  `existing_required` (relocation saiu do `_WA_SUPPORT`).
- FP2 (relocation): "We support your relocation to Munich." → antes
  `support`, agora `not_mentioned`.

**FPs identificados na amostragem dos reclassificados**: 0 (ver §4).

**Falsos negativos conhecidos remanescentes (4 unclear — fora da direção 6
da spec, SEM expansão especulativa; precisão > cobertura)**:
1. `Volkswagen AG|successfactors:VWAGLPPROD10:14` (3 vagas): "Ggf.
   Arbeits- und Aufenthaltserlaubnis inkl. Zusatzblatt für Nicht-EU
   Bürgerinnen/Bürger" — condição "Ggf." (se aplicável) + trabalhos DE;
   requereria inferência condicional ("ggf." → existing_required) fora da
   direção 6; hoje `unclear` (vocab sem classificação).
2. `celonis|greenhouse:celonis:7998271003`: "sponsorship opportunities
   across Germany" — "sponsorship" de EVENTOS de marketing, não de visto;
   classificar exigiria desambiguação semântica de "sponsorship";
   hoje `unclear` (correto pela semântica conservadora: toca no tema sem
   classificar).

**FNs suporte corrigidos** (8 da spec + "Visa costs are covered by us"):
nenhuma vaga real do dataset os continha (o dataset não tem par
verbo-tema de visto — 227 "unterstütz" são todos de tarefas de negócio).
Os padrões estão prontos para coletas futuras.

## 6. Modelo final de visa_policy (item 11)

5 estados fixos em `VISA_POLICY_STATES`, lidos do campo curado
`visa_policy` da entrada de Company Intelligence por
`visa_policy_state(intel) -> str` (analogia exata com `pathway_state`;
ausente/inválido/None → `not_verified`):

- `explicit_support` — fonte oficial declara suporte INCONDICIONAL ao
  processo de visto/autorização;
- `explicit_no_support` — fonte oficial declara que NÃO patrocina/assist;
- `candidate_must_have_authorization` — fonte oficial exige autorização
  prévia do candidato;
- `unclear` — fonte oficial TOCA no tema mas de forma condicional/
  seletiva ("may sponsor", "case-by-case", "for eligible roles and
  locations", "coverage varies") — citação textual preservada na fonte;
- `not_verified` — sem evidência pública verificável (default).

**Regra semântica central**: declarações CONDICIONAIS → `unclear` (a
curadoria já foi feita, não redecidida em código). `visa_policy` é da
EMPRESA; `work_authorization` é da VAGA — nunca um deriva do outro
(independência coberta por teste com os dois preservados e distintos
na saída; `visa_policy` nunca entra no score — data-attrs idênticos
com/sem o campo preenchido).

## 7. Empresas efetivamente curadas (12)

- **unclear (2, com fonte primary)**: SAP, BoschGroup.
- **not_verified (10, com `visa_policy_note` de rastreabilidade)**:
  BMW AG, Volkswagen AG, Fraunhofer-Gesellschaft, Knorr-Bremse,
  Liebherr-International S.A., BASF SE, STIHL, Schaeffler Technologies
  AG & Co. KG, Bayer, teampicnic.
- NENHUMA promovida a `explicit_support` (curadoria honesta; as
  declarações de SAP/Bosch são condicionais de processo/cobertura).
- Sem evidência contraditória em anúncio de empresa no dataset
  (verificado: nenhuma vaga SAP/Bosch/teampicnic contém declaração
  textual de suporte incondicional de visto).

## 8. Fontes utilizadas (2)

| Fonte | URL | Qualidade | checked |
|---|---|---|---|
| SAP Careers — Privacy Statement (global mobility services para working visa/residency permit) | https://jobs.sap.com/en/sap-privacy-statement-careers?locale=en_US | primary | 2026-09-23 |
| Bosch Careers FAQ — "Does Bosch sponsor visas or work permits...?" ("For eligible roles and locations, Bosch may sponsor visas or work permits... Coverage varies by country and role.") | https://www.bosch.com/careers/faq | primary | 2026-09-23 |

## 9. Datas de verificação

- Curadoria visa_policy (fontes SAP/Bosch): **2026-09-23** (feita pelo
  orquestrador; aplicada nesta entrega sem redecisão).
- Notas de rastreabilidade das 10 not_verified: mesma string com
  **2026-09-23**.
- Campos `checked` das fontes: **2026-09-23** (os demais campos das
  entradas preservados com seu `checked` original 2026-09-20).

## 10. Testes adicionados

- `scripts/test_visa_policy.py` (novo, **33º do CI**): **43 checks** —
  5 estados válidos; campo ausente/inválido ("maybe", 123)/None/intel
  vazio → not_verified; determinismo 100x; arquivo curado (12 empresas =
  10 not_verified + 2 unclear; fontes com url+quality+checked; 10 notas;
  nenhuma explicit_support); INDEPENDÊNCIA visa_policy(empresa) ×
  work_authorization(vaga) (existing_required + explicit_support AMBOS
  preservados e distintos; visa_policy não muda com texto da vaga; WA
  not_mentioned mesmo com empresa explicit_no_support); interface (seção
  presente ×3, rótulo PT-BR da curada, fonte com URL na página, default
  not_verified, partial intel/sem intel não quebram, dados de origem não
  mutados, data-attrs de score IDÊNTICOS com/sem visa_policy); bloco real
  (391 ids, ordem topo/cauda preservada, scores idênticos ao snapshot,
  rótulo unclear exibido para SAP/Bosch, WA 23/4/364 invariante da VAGA).
- `scripts/test_app_intel.py::test_work_authorization`: **+43 casos**
  (54 no total, antes 12): FNs conhecidos (9 incl. custeio), FP1/FP2,
  combinação required+sponsorship → support, negações expandidas (9
  contrapartes), existing expandidos (5), não-inferência (3), HTML
  entities (2), sem sinal → not_mentioned, determinismo 100x.
- Fix pré-existente no mesmo arquivo: invariante de deadline
  ("deadlines presentes == fonte OU textual") fazia soma de contagens —
  um job SF com campo (validade de feed) E Bewerbungsfrist no texto era
  contado 2x (218+6 ≠ 218; 6 Fraunhofer). Corrigido para invariante por
  KIND com comentário do porquê. Verificado: falha pré-existente no
  checkout de produção (suíte com data/ real falhava 31/32 desde o PR
  #79); com o fix, 33/33 com data/ real.
- **CI**: array 32→33 (`test_visa_policy`); suíte completa local
  **33/33, 1.834 checks, 0 falhas** (data/ real presente, byte-identical
  antes==depois).

## 11. Confirmação: ranking/score/filtros/pesos não alterados

- Nenhum toque em `ranking.py`, `materials_ranking.py`, `filters.py`,
  `dedup.py`, `adapters/`, `collectors/`, `publish_pages.py`,
  `refresh_daily.py`, `ranking_digest.py`, `cli.py` (git diff conferido).
- Evidência: `ranking.rank_jobs` recomputado no snapshot 391 com o código
  HEAD~2 (sem meus commits) vs HEAD (com meus commits) → **sequência de
  ids idêntica e scores+breakdowns idênticos (0 diffs)**.
- data-scores do HTML idênticos com/sem visa_policy preenchida
  (`test_visa_policy::test_interface_render`).
- O snapshot 23/09 reproduz exatamente o pipeline da coleta
  (recomputado com o código `4db49b8` da data do run == snapshot: ordem
  + scores 391/391). Os 25 diffs de score/breakdown do snapshot vs o
  código ATUAL são o delta documentado do PR #79 (25 FNs de German
  corrigidos — language −2,0 vs +1,5/+1,0), PRÉ-EXISTENTE a esta tarefa
  e idêntico antes/depois dela.
- Funil: eligible/ids 391==391; nenhum filtro alterado; WA é detector
  pós-eligibilidade (nunca afeta funil).

## 12. Limitações e o que permaneceu not_verified

- **4 unclear do WA da VAGA** (§5): "Ggf. Arbeits- und Aufenthaltserlaubnis
  …" (VW ×3, condição "ggf." fora da direção 6 da spec) e "sponsorship
  opportunities" de eventos (celonis, desambiguação de "sponsorship"
  fora de escopo) — ficam `unclear` (conservador e correto pela
  semântica); expandir exige decisão de semântica nova, não padrão
  especulativo.
- **10 empresas com `visa_policy: not_verified`**: páginas oficiais de
  carreiras checadas em 2026-09-23 sem declaração pública aplicável
  sobre visto/autorização para os contextos das vagas (DE); fontes de
  subsidiárias US/UK não são extrapoláveis. Nota de rastreabilidade
  registrada em cada entrada; a interface exibe "Não verificado"
  honestamente com a nota.
- Os padrões de suporte/negação novos não têm ocorrência no snapshot
  atual (o dataset não contém par verbo-tema de visto); cobertura real
  só é mensurável nas próximas coletas do cron.
- `visa_policy` é estado curado por empresa — empresas fora das 12
  curadas exibem `not_verified` (mesmo comportamento "Not available" do
  pathway; sem inferência de multinacional/setor/localização).
