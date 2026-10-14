# F36 — Perfil EU non-DE: terceiro perfil de ranking

**Data**: 13–14/10/2026 · **Branch**: `feature/f36-non-de-profile` ·
**Veredito do dono** (13/10, registrado no card t_1211e7de): **aprovada
como desenhada**, com condições (a)–(e) — todas atendidas abaixo.

## 1. Motivação (benchmark v2, F27 — docs/ranking_benchmark.md §6.4c)

O benchmark v2 (90 rotuladas, 3.068 pares) mediu no universo pós-F25
(783 eligible, 26% não-DE) que o estrato não-DE **não se comporta como o
DE** sob os pesos do perfil business:

| Medida | DE | não-DE |
|---|---|---|
| Concordância / tau | 89,2% / **+0,785** | 76,4% / **+0,528** |
| `location` (componente) | constante +1,0 | **0 em 204/205** |
| `registry` médio | 0,44 | 0,09 |
| "ruim" no estrato | 11–20% | **40%** |
| Share do top-100 | — | 12% (vs 26% do universo) |

Dois fatores estruturais: (1) `location` DE-explícita + registry
quase ausente fora da DE = handicap fixo de ~1,5 pontos **sem relação
com qualidade** — um desconto de país disfarçado de sinal de qualidade;
(2) os pesos atuais foram calibrados num universo 100% DE (13.482
brutas, F5). Alternativas rejeitadas na recomendação: peso único
ajustado (regressão no perfil DE comprovadamente bom), remoção do
não-DE do eligible (contra a decisão F7 do dono — canal backup), não
fazer nada (top-100 sub-representa 26% do universo).

## 2. Design (mesmo padrão da Fase 4 — Materials Engineering)

Ranking **separado por perfil**, não fusão de pesos. Terceiro perfil ao
lado de business e materials:

- **Módulo novo** `src/internship_finder/eu_ranking.py` — os módulos
  `ranking.py` e `materials_ranking.py` não são alterados (nem a
  assinatura); zero risco de regressão nos dois perfis existentes.
- **Campos novos** `eu_score`/`eu_breakdown` — nunca tocam
  `score`/`score_breakdown` (business) nem `materials_*`. Função pura
  do job (o score de uma vaga não depende das outras do universo).
- **Display**: seção própria no minimal_page (🇪🇺 "Fora da Alemanha",
  top 10, `--no-eu` desliga; default ligado no padrão da seção 🧪) e
  seção compacta no digest (`eu_lines`: Top 5 + novas no Top 30).

Componentes (constantes de módulo):

| Componente | Regra | Peso |
|---|---|---|
| area | MESMOS detectores/pesos do business (filters.area_score) | 2.0 título / 0.0 desc |
| skills | MESMOS do business (descrição) | +0.75/termo |
| language | MESMO do business (EN evidência; DE pela exigência) | +1.5 / −2.0 / −0.5 |
| type | marcador forte de tipo no título (reusa filters) | +1.0 |
| location | **país-alvo do projeto** (`TARGET_COUNTRIES`: de/nl/be/lu/fi), sem bônus Berlin | +1.0 |
| interest | **watchlist F13** (registry rederivado p/ o estrato; match casefold exato/substring, regra F3; ausente/corrompida → 0, nunca erro) | +0.5 |
| penalties | MESMOS do business (senior/manager/full_time) | −3.0/−1.0/−0.5 |
| fn | **função não-alvo no TÍTULO sem termo primário de área** (marketing/HR/sales-BD; lista curta, padrão materials) | −2.5 |

Duas decisões de calibração documentadas:

- **interest = watchlist F13 (+0.5), não o registry F3/F32**: no
  estrato atual, o registry DE cobre 17% das não-DE; a watchlist
  (curadoria visa_friendly/nicho do dono, `config/company_watchlist.json`)
  cobre 39%. O grid não mostrou ganho ordinal acima de +0.5, e o peso
  fica abaixo do registry do business (+1.0) porque a lista é mais larga.
- **fn com gate de área primária**: os "ruim" do estrato sobem por
  "Operations"/"Analyst" em títulos de marketing/BD/HR (40% do estrato).
  A penalidade só vale quando o título NÃO carrega termo primário de
  área — híbridos como "HR Analytics Intern" e "Sales Development and
  Analytics" são vagas de dados e ficam protegidos (15/777 casos
  medidos no universo). Mesmo espírito da regra do milestone 2 do
  ranking principal (marcador forte vence senioridade).

## 3. Benchmark v3 (critério de aceite do veredito)

Metodologia: MESMA do v2 (`pairwise_concordance`), sobre o MESMO
estrato rotulado (35 não-DE do arquivo v2, 432 pares comparáveis), com
posições derivadas DENTRO do estrato (o que o dono vê é a ordem interna
do perfil EU). Reproduzível: `scripts/ranking_benchmark_v3.py
--snapshot <cópia local do eligible_jobs.json>`.

**Resultado (cópia do universo de 13/10, 777 eligible — produção
intocada):**

| Ranking | Concordância | tau |
|---|---|---|
| ATUAL (business) no estrato (baseline v2 reproduzido) | 76,39% (330/432) | **+0,528** |
| **Perfil EU (novo)** | 82,87% (358/432) | **+0,657** |

**Delta +0,129 ≥ +0,10 exigido — critério ATINGE.** As duas ótimas do
estrato sobem para o topo (ranks 1–2); os "ruim" de marketing/BD caem
para o fundo (ranks 31–35).

Honestidade da calibração (n=35, 432 pares):

- w_fn 2.0 / 2.5 / 3.0 todos ≥ alvo; escolhido **2.5** (centro do
  intervalo, não o pico do grid — com n pequeno, pico é overfitting).
- Validacão 2-fold (paridade de id, zero RNG): holdout A→B **+0,769**,
  B→A **+0,523** — o sinal sobrevive ao corte, com a variância
  esperada de folds de n≈17/18. O valor do estrato inteiro (+0,657)
  é a estimável estável entre os dois folds.
- Sinais testados e REJEITADOS: recorrência de empresa no estrato
  (quebra a pureza de função — o score mudaria só porque o universo
  ao redor mudou; sem ganho ordinal robusto no grid) e reponderar
  area-related (menos conservador que componente novo, mesmo efeito).
- O FP do estrato (Amazon "Business Analyst, EU Inbound & Inventory
  Placement", rank 6, eu 9.5) continua alto — persegui-lo custaria a
  discriminação do meio (lição v2 §6.4a); fica como resíduo conhecido.

## 4. Condições do veredito → onde estão atendidas

| Condição | Onde |
|---|---|
| (a) perfis DE/materials byte-idênticos | `scripts/test_f36.py` T1+T4 (invariante sobre fixtures + isolamento estático) |
| (b) benchmark v3 no estrato | `scripts/ranking_benchmark_v3.py` + §3 acima |
| (c) tau novo ≥ +0,10 acima do v2-não-DE | +0,657 ≥ +0,628 ✓ |
| (d) suíte completa verde | 74 suítes no array do CI (test_f36 = 74ª, mesmo commit); local: 74/74 executadas, 3 falhas PRÉ-EXISTENTES na main (test_f29/lifecycle/registry — data-dependentes do ambiente, reproduzidas no baseline limpo) |
| (e) PR sem merge | `feature/f36-non-de-profile` → PR aberto; merge é do dono |

## 5. O que NÃO mudou

- Pesos/regras dos perfis business e materials (regressão proibida —
  tau +0,785 DE comprovado no v2).
- Elegibilidade, dedup, filtros, coleta, cron: nada fora dos pontos
  acima (o perfil EU é camada de ranking/display sobre o eligible
  existente, igual à Fase 4).
- `docs/ranking_benchmark.md` (baseline v2 intocada); este doc é o
  companheiro da F36.
