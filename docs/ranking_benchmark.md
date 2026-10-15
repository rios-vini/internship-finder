# Benchmark do ranking (P2.5) — medir antes de alterar

> Tarefa P2.5: **medição** do ranking heurístico atual com vagas reais
> rotuladas manualmente, antes de qualquer mudança de pesos/formula/regras.
> Nenhuma alteração de comportamento foi feita nesta tarefa — o ranking
> (`src/internship_finder/ranking.py`) segue sendo a implementação de
> referência e seus testes não foram tocados.

> **F27 — Benchmark v2 (13/10/2026)**: re-execução da MESMA metodologia no
> universo pós-F25 (~783 eligible, multi-país, sf_dataset dominante), com
> estratos de país e o componente `registry`. Seção 6. MEDIÇÃO PURA —
> nenhuma recomendação foi implementada; o que este benchmark recomenda
> vira card futuro com decisão do dono.

## 1. Existência e formato

- **Dados versionados**: `benchmarks/ranking_benchmark_v1.json` (45 KB,
  59 vagas) — a parte humana (rótulos + justificativas) e o congelamento do
  snapshot (rank, score, score_breakdown) vivem no Git; não dependem de
  planilha externa. **F27**: `benchmarks/ranking_benchmark_v2.json`
  (90 vagas, universo 12/10) no mesmo formato + campos `country` (ISO do
  estrato de país) e `stratum` (estrato da amostra), breakdown com o
  componente `registry` (F3).
- **Análise**: `scripts/ranking_benchmark.py` (relatório; `--benchmark
  benchmarks/ranking_benchmark_v2.json` para o v2 — imprime também os
  estratos DE/não-DE quando o arquivo carrega `country`) e
  `src/internship_finder/ranking_benchmark.py` (funções puras, stdlib;
  F27: validação e perfis de componente aceitam breakdown v1 de 6
  componentes E v2 de 7 com `registry`; F38: também v3 de 8 com `decay` —
  snapshots pós-F38 carregam a contribuição aditiva do freshness decay).
- **Reprodução do benchmark em snapshot novo**:
  `scripts/make_ranking_benchmark.py refresh --snapshot data/eligible_jobs.json --run-date <data>` —
  re-extrai score/breakdown/rank pelos ids (chave estavél P1.1), preserva
  rótulos/justificativas, valida antes de gravar (nunca grava benchmark
  inválido). `validate` confere schema/invariantes a qualquer momento.
- **Testes**: `scripts/test_ranking_benchmark.py` (51 checks, offline, sem
  rede/`data/`) no array do CI (19→20 scripts).
- **Snapshot de origem**: `data/eligible_jobs.json` do run cron de
  **11/09/2026 06:00 UTC** (260 eligible; funil 60.256 brutas).

## 2. Metodologia de rotulagem

Cada vaga foi lida (título + descrição + employment_type) e classificada
respondendo **"quão adequada esta vaga é para o objetivo do projeto/perfil?"**
— nunca "quanto eu gosto do score do algoritmo". Perfil de referência: o
mesmo do ranking (SC, Procurement, BI/Analytics, Automação; competências de
dados; inglês essencial; Alemanha).

| Rótulo | Critério objetivo |
| --- | --- |
| `otima` | Estágio/Working Student com área-alvo no título **e** conteúdo real (SC/Procurement/Analytics/Automação/Dados) **e** ambiente EN |
| `boa` | Área-alvo clara, mas 1 dimensão fraca: sem descrição, sem sinal de inglês, área genérica, ou função adjacente com dados |
| `aceitavel` | Aderência parcial: área tangente/indireta, dev/data-eng fora do núcleo, tese com tema relevante, HiWi |
| `ruim` | Passou nos filtros, aderência marginal: tema incidental, forma tese pura, RH/vendas |
| `falso_positivo` | **Não deveria estar no eligible**: programa de graduação dual, trainee/LDP de graduados, cargo full-time regular, candidatura espontânea |

Rotulagem feita em 11/09/2026 por revisão manual de revisão (orquestraçao;
revisável pelo dono — cada vaga tem justificativa e URL). A seleção da
amostra é estratificada e determinística (documentada no campo `sampling` do
arquivo): topo do ranking (12), maiores grupos de empate (8 grupos × 3 com
empresas distintas), vagas sem marcador forte de tipo, cauda do ranking e
casos especiais — **não** é o mero Top 20 (evita viés de seleção).

## 3. Amostra

59 vagas. Dados do run 11/09/2026:

| Rótulo | n | |
| --- | --- | --- |
| ótima | 5 | 8,5% |
| boa | 22 | 37,3% |
| aceitável | 15 | 25,4% |
| ruim | 5 | 8,5% |
| falso positivo | 12 | 20,3% |

Cobertura: ranks 1–260 (topo e cauda), 25 empresas, scores de 1.0 a 16.75,
grupos de empate de vários tamanhos (incluindo grupos mistos inteiros).

## 4. Métricas e resultados

Reproduzir em qualquer momento:

```bash
.venv/bin/python scripts/ranking_benchmark.py --snapshot data/eligible_jobs.json
```

### 4.1 Distribuição dos scores (universo: 260 eligible do run 11/09)

- **39 scores distintos** para 260 vagas; **251 vagas (96,5%) empatadas** com
  pelo menos outra; 30 grupos de empate.
- Maiores grupos: **7.5 ×33**, 5.5 ×28, 6.75 ×26, 4.75 ×24, 6.0 ×21, 8.0 ×17.
- Causa estrutural: o score é soma de 6 componentes com poucos valores
  possíveis (pesos 0.25/0.5/0.75/1.0/1.5/2.0/3.0), e `location` é constante
  (todas as vagas do eligible são DE: +1.0 fixo) — o espaço de scores é
  grosseiro por construção.

### 4.2 Qualidade humana vs posição (amostra de 59)

| Rótulo | n | média de score | faixa |
| --- | --- | --- | --- |
| ótima | 5 | **12,45** | 10.0–13.75 |
| boa | 22 | 9,57 | 4.0–16.75 |
| aceitável | 15 | 5,95 | 2.0–12.75 |
| ruim | 5 | 6,35 | 4.75–10.0 |
| falso positivo | 12 | **3,65** | 1.0–7.0 |

- **Concordância ordinal (pares comparáveis, 1.289 pares): 82,5%** concordes;
  tau (Kendall-like) = **+0,651**. O ranking **tem sinal real**: vagas melhores
  tendem a ficar acima, e as ótimas ocupam o topo (ranks 2/5/6/7/25).
- Ruído observado: `ruim` com média (6,35) > `aceitavel` (5,95) — pequeno n
  (5), puxado por falsos-analytics com score alto (ex.: "Sensory Analytics"
  10.0, ver 4.4).

### 4.3 Empates (o ponto central)

- Na amostra: 14 grupos de empate; **9 (64%) com labels humanas DIFERENTES**;
  32 vagas (**67% das empatadas**) em grupos mistos; dispersão máxima de **3
  níveis** de qualidade dentro de um mesmo score.
- Pior caso: **score 10.0 ×8** contém ótima, boa, aceitável **e** ruim
  (ranks 23–35); o score 4.0 ×3 mistura `falso_positivo`, `boa` e
  `aceitavel`.
- **Conclusão parcial: os empates escondem diferenças reais de qualidade em
  ~2/3 dos casos** — a baixa resolução não é só estética, é perda de
  ordenação útil.

### 4.4 Exemplos representativos de falha (padrões, não anedotas)

1. **Mesma vaga, 3 posições**: a Bayer "Analytics Advisory & Data
   Democratization / SC&L Analytics" aparece nos ranks **2 (DE, 13.75), 5
   (EN, 13.0) e 25 (EN sem descrição, 10.0)** — dedup não fundiu e a
   **ausência de descrição sozinha custa 3,0–3,75 pontos** (skills/idioma
   zeram). É uma distorção não-semântica: o conteúdo da vaga é idêntico.
2. **Falso "analytics" pontua como analytics**: "Internship / Thesis -
   Sensory Analytics" (análise sensorial de alimentos) = **10.0**, no mesmo
   score do rank 25 (ótima de verdade); o termo "analytics" do título é de
   outra disciplina.
3. **Falso positivo acima de vaga boa no mesmo score**: 4.0 ×3 —
   `AI Native Developer` (full-time, FP) vem ANTES de `Allianz Data & AI
   Engineering Intern` (boa) por desempate alfabético do título — o
   desempate atual não tem relação com qualidade.
4. **FP com score alto**: Trainee Operations Controlling **7.0** (programa de
   graduados), Duales Studium B.A. Logistics 6.5, Business Analyst HR 5.75 —
   entram por `area`+`language` do título.
5. **Excelente sub-ranqueada**: "Menu Planner Working Student" (6.0) — área 0
   no título, mas conteúdo com python, supply chain ponta-a-ponta e
   automação: o ranking não vê (área da descrição zerada por calibração, e
   skills não pegaram os termos).

### 4.5 Componentes do breakdown vs qualidade (descritivo)

| componente | ótima | boa | aceitável | ruim | FP | leitura |
| --- | --- | --- | --- | --- | --- | --- |
| area | 8,00 | 6,91 | 2,93 | 3,20 | 1,00 | **discriminador dominante** (direção correta) |
| skills | 1,05 | 0,20 | 0,35 | 0,15 | 0,31 | separa só o topo |
| language | 1,40 | 0,52 | 0,90 | 1,10 | **1,33** | **não discrimina** (FP ≈ ótima) |
| type | 1,00 | 1,00 | 0,73 | 1,00 | **0,00** | separa FP (que não têm marcador) |
| location | 1,00 | 1,07 | 1,03 | 1,00 | 1,00 | constante (sem sinal) |
| penalties | 0,00 | −0,14 | 0,00 | −0,10 | 0,00 | raro e suave |

## 5. Decisão — conclusão A/B/C

> **Caso C — baixa resolução real** (predominante), com **componentes de
> Caso B** localizados.

**O ranking não está quebrado** (tau +0,65; 82,5% dos pares comparáveis
concordes; ótimas no topo; FP em média 8,8 pontos abaixo das ótimas) — **não
há evidência para reescrita, embeddings, ML ou novos pesos globais**. Mas a
baixa resolução produz **perda significativa de ordenação útil**: 96,5% das
vagas empatadas, 67% das empatadas da amostra em grupos com qualidade humana
diferente, dispersão de até 3 níveis no mesmo score. **Uma tarefa de
calibração é justificada** — restrita, com hipóteses testáveis (abaixo), não
um redesign.

### Hipóteses para a próxima tarefa de calibração (em ordem de custo/objetividade)

1. **Descrição ausente ≠ vaga pior** (B, mensurável, mais barato): a MESMA
   vaga oscila 3,0–3,75 pontos só por ter/não ter descrição (caso Bayer
   ranks 2/5/25). Hipótese: sinalizar/compensar vagas sem descrição (usar
   `raw`/título) ou tratar (empresa+título) como grupo antes de pontuar.
   Evidência: mesmo job em 3 posições do ranking — 3 pontos de faixa.
2. **`language` não discrimina** (B): FP/ruim pontuam (1,33/1,10) tanto
   quanto ótima (1,40) — "english/englisch" aparece em boilerplate e
   títulos EN sem exigir inglês real. Hipótese: reduzir peso ou exigir
   contexto de requisito. Evidência: média por rótulo em 4.5.
3. **Desempate semântico** (C): no mesmo score, o título alfabético decide
   (FP acima de boa, caso 4.4.3). Hipótese: apenas documentar, ou um
   desempate leve (ex.: marcador de tipo antes do alfabético). Evidência:
   mix 4.0 ×3.
4. **Falsos positivos são gap de FILTRO, não do ranking** (fora do escopo
   desta tarefa): Trainee full-time, Duales Studium sem a palavra "dual" no
   título, "Berufserfahrene", "Limited employment", "Initiativbewerbung"
   chegam ao eligible com score até 7.0. Hipótese (tarefa futura de
   P-filtro): estender `TYPE_EXCLUSION_PATTERNS`/`PROGRAM_EXCLUSION_PATTERNS`
   com esses marcadores, medindo antes/depois no funil.

**Não implementar agora**: qualquer mudança de pesos, desempate, filtro ou
sinal. O benchmark fica como o instrumento de medição para avaliar a
calibração quando ela for feita (mesmas métricas, antes/depois).

---

## 6. Benchmark v2 (F27, 13/10/2026) — o universo pós-F25

### 6.0 Por que re-medir

O v1 (11/09) mediu um universo que não existe mais: 404 vagas PRÉ-F3 (o
dataset não era fonte), PRÉ-F7 (sem multi-país) e PRÉ-F18 (sem
applicability). O universo atual (snapshot 12/10, run cron 09:32 UTC) tem
**783 eligible** (funil 126.842 brutas), **578 DE / 109 NL / 58 BE / 34 LU
/ 4 FI (26% não-DE)**, `sf_dataset` dominante (545/783), `registry` como
componente (+1,0 em 323/783) e a reavaliação F25 moldando o topo
(126 german_required; 2 no top-12). Este v2 é o baseline exigido antes de
qualquer discussão de pesos (visa, salário, idade) — sem ele, calibrar é
calibrar no escuro. **MEDIÇÃO PURA**: nenhum peso/regra/ranking.py mudou
neste card.

### 6.1 Metodologia (idêntica ao v1 + estratos de país)

- Mesma rubrica de 5 classes, mesma pergunta ("quão adequada esta vaga é
  para o objetivo do projeto/perfil?"), rotulagem por revisão de conteúdo
  (título + descrição, dado público do dataset), justificativa por vaga.
- Amostra estratificada **determinística** (zero RNG: chave oficial de
  ordenação + slices/strides posicionais documentados no campo `sampling`
  do arquivo): top 12 (T1), 8 maiores grupos de empate ×3 com empresas
  distintas (T2), cauda 8 (T3), casos especiais — sem descrição,
  hidratadas (alvo F25: german_required reproduzido com os detetores
  oficiais F18/F25), sf_dataset vs não-sf_dataset, werkstudent FULL_TIME
  (T4) — e **estratos de país** (T5): 12 DE espalhados + não-DE por país
  (NL 7, BE 6, LU 4, FI 2), oversample deliberado do não-DE (39% da
  amostra vs 26% do universo) para poder comparar os dois mundos.
- 90 vagas rotuladas: DE 55 / NL 14 / BE 11 / LU 8 / FI 2; ranks 1–783;
  36 scores distintos; 79 empresas.

| Rótulo | n | % | | Rótulo | n | % |
| --- | --- | --- | --- | --- | --- | --- |
| ótima | 5 | 5,6% | | ruim | 20 | 22,2% |
| boa | 29 | 32,2% | | falso positivo | 13 | 14,4% |
| aceitável | 23 | 25,6% | | | | |

### 6.2 Métricas e resultados (v2)

Reproduzir:

```bash
.venv/bin/python scripts/ranking_benchmark.py --benchmark benchmarks/ranking_benchmark_v2.json --snapshot data/eligible_jobs.json
```

**Concordância ordinal: 83,41% dos 3.068 pares comparáveis; tau +0,668**
(v1: 82,5% / +0,651). 509 inversões (16,6% dos pares comparáveis). O sinal
real do ranking SOBREVIVEU à troca de universo: 3× mais pares comparáveis,
mesma taxa de acerto.

**Qualidade humana vs posição** — o gradiente está em todos os quartos do
ranking (qualidade média 0–4 por faixa de rank): 1–100: **3,20**; 101–300:
2,13; 301–600: 1,84; 601–783: **0,83**. Score médio por rótulo: ótima
13,75 (12,5–14,25), boa 9,57, aceitável 5,82, ruim 3,75, FP 2,92 — ordem
PERFEITA das médias (o v1 tinha a anomalia ruim > aceitável; no v2 isso
desapareceu). As 5 ótimas estão nos ranks 4/5/6/8/12 — topo limpo.

**Distribuição e empates (universo)**: 53 scores distintos para 783 vagas;
**775 (99,0%) empatadas** (v1: 96,5%); 45 grupos; maiores: 8,0 ×51, 3,0
×51, 6,0 ×50, 5,5 ×44, 6,5 ×38. A resolução piorou de leve (o universo
triplicou, o espaço de scores quase não): o problema estrutural do v1
continua e agrava.

**Empates na amostra**: 20 grupos, **15 mistos (75%)**; **60 vagas (81% das
empatadas) em grupos com qualidade diferente** (v1: 64%/67%); dispersão
máxima de 3 níveis persiste. Pior grupo: **6,5 ×6** contém boa, aceitável,
ruim E falso-positivo (ranks 307–339). O grupo 8,0 ×51 (maior do universo)
aparece na amostra com boa/aceitável/ruim/FP juntos.

### 6.3 Comparativo v1 → v2 (o que mudou com o universo novo)

| Métrica | v1 (11/09, 260 eligible) | v2 (12/10, 783 eligible) |
| --- | --- | --- |
| Concordância ordinal | 82,54% (1.289 pares) | **83,41% (3.068 pares)** |
| tau | +0,651 | **+0,668** |
| Empates (universo) | 96,5% empatadas, 30 grupos | **99,0% empatadas, 45 grupos** |
| Empates mistos (amostra) | 9/14 grupos, 67% das empatadas | **15/20 grupos, 81% das empatadas** |
| FP na amostra | 12/59 (20,3%) | 13/90 (14,4%) |
| Ordem das médias por rótulo | ruim (6,35) > aceitável (5,95) — anomalia | **ótima > boa > aceitável > ruim > FP — monotônica** |
| `language` por rótulo | FP 1,33 ≈ ótima 1,40 (não discriminava) | **FP 0,12 ≪ ótima 1,10** (ver 6.4a) |
| Componentes no breakdown | 6 (sem registry) | 7 (+registry F3) |

Mudança QUALITATIVA nos falsos positivos: os FP do v1 eram trainee/LDP de
graduados e Duales Studium com score até 7,0 (gap de filtro em inglês); os
do v2 são quase todos **alemães e de classe trabalhadora** — 7 GALERIA
"Aushilfe" (Nebenjob de varejo, score 0,5, cauda) e 5
Ausbildung/Schnupperpraktikum "Kaufmann Spedition" (score 5,5–6,5) —
entraram pela BA/eURES via termo "Logistikdienstleistung". O único FP
não-DE graduado (Amazon #179, 8,0) e o Citi placement (#623) confirmam o
padrão antigo em escala menor. FP com score alto caiu de 7,0 para 8,0 mas
são 2 casos isolados.

### 6.4 As quatro perguntas do card F27

**(a) `language` discrimina agora?** **Sim — a Fase 6 consertou a direção
topo-vs-FP, mas o meio continua confuso.** No v1, FP (1,33) pontuava
praticamente igual à ótima (1,40) — o componente não separava nada. No v2:
ótima 1,10 / boa 0,36 / aceitável 0,50 / ruim 0,95 / FP **0,12** — o gap
ótima-FP de ~1,0 ponto apareceu. CUIDADO com a leitura: o que separa o FP
hoje não é "inglês essencial" como requisito — é o IDIOMA DO ANÚNCIO (os
FP alemães de varejo/aprendizagem não contêm a palavra "english"; 12 dos
13 FP têm language=0). O componente virou um proxy de "anúncio em inglês",
que correlaciona com vagas internacionais, não um detector de "ambiente
EN". Dentro do estrato DE o quadro é o mesmo (ótima 1,33, boa 0,08, ruim
0,67, FP 0,0) e o "ruim" (marketing/BD EN) continua pontuando perto da
ótima. **Resposta: discrimina o extremo (FP), não o meio.**

**(b) `registry` (+1,0) ajuda ou infla?** **Ajuda — e é o componente mais
monotônico do v2.** Perfil por rótulo: ótima 0,60 / boa 0,38 / aceitável
0,35 / ruim 0,20 / FP 0,08 — gradiente monotônico com a qualidade (o
"monotono" da tabela 4; area/skills/type também o são, mas registry separa
com o menor ruído). Comparação direta na amostra: registry=1 → FP 3,7%,
ótima+boa 52%, qualidade média 2,41; registry=0 → FP 19,0%, ótima+boa 32%,
qualidade 1,71. O único FP com +1,0 é um Ausbildung (315) que pegou o
bônus pela empresa. Não há evidência de inflação sistemática: o bônus não
coloca FP no topo (2 FP acima de 5,5, nenhum no top-100 com registry). A
amostra não captura o efeito no longo da cauda (registry=1 é raro lá),
mas no intervalo onde o dono olha (top), o sinal é real. **Resposta: o
componente paga o que promete — lista de interesse captura empresas cujas
vagas são de fato melhores.**

**(c) O estrato não-DE se comporta como o DE?** **Não exatamente — e a
diferença é estrutural, não de qualidade de ranking.** Concordância
dentro do estrato: DE 89,2% (tau +0,785) vs não-DE 76,4% (tau +0,528).
Composição: não-DE tem MENOS FP (2/35 = 5,7% vs 20% no DE — o funil
multi-país F7 é mais limpo: vagas de empresas internacionais com
"internship" no título) porém MUITO mais "ruim" (40% vs 11% —
marketing/BD/HR de startups EN que passam pelos filtros). Dois fatores
estruturais: (1) **`location` é constante-1,0 no DE e constante-0,0 no
não-DE (204/205)** — handicap fixo de −1,0 ponto; junto com registry
(quase ausente fora da DE: 0,09 vs 0,44), vagas não-DE partem ~1,5 pontos
atrás SEM RELAÇÃO COM QUALIDADE: score médio DE 6,46 vs NL 4,42 / BE 4,83
/ LU 5,68, e o não-DE tem 12% do top-100 contra 26% do universo. (2) A
escala do tau não-DE (n=35, 432 pares, LU tau −0,41 com n=8) é frágil —
BE +0,90 e NL +0,61 apontam ordenação razoável; o −0,41 de LU vem de 17
pares. **Resposta (RECOMENDAÇÃO, não implementação): o não-DE merece
tratamento separado em qualquer discussão futura de pesos — hoje o
componente location cria um desconto de país disfarçado de sinal de
qualidade; os pesos atuais foram calibrados num universo 100% DE. Card
futuro, decisão do dono.**

**(d) Empates continuam escondendo dispersão de qualidade?** **Sim —
PIOROU.** 99,0% do universo empatado (v1: 96,5%), 15/20 grupos da amostra
mistos (75%), 81% das vagas empatadas em grupos com qualidade diferente
(v1: 67%), dispersão de 3 níveis no mesmo score persiste, e as inversões
DENTRO de grupos de empate (decididas pelo desempate alfabético de
título) somam 33 pares na amostra. O maior grupo do universo (8,0 ×51)
contém boa/aceitável/ruim/FP juntos. A baixa resolução deixou de ser
estética: com 783 vagas e 53 scores, o dono olha para faixas de 50 vagas
idênticas. A causa é a mesma do v1 (soma de poucos componentes discretos
+ location constante no DE) e a recomendação de calibração restrita do v1
se mantém — agora com evidência 3× maior.

### 6.5 Conclusão v2

O ranking **não está quebrado no universo novo** — tau +0,668 com 3.068
pares, médias monotônicas por rótulo, ótimas no topo (ranks 4–12), gradiente
de qualidade em todo o comprimento do ranking. Não há evidência para
redesign/ML/novos pesos globais. Os problemas medidos são os mesmos do v1,
agora quantificados num universo 3× maior e multi-país: (1) resolução de
empates piorou (99% empatado); (2) location/registry criam um viés
estrutural DE-vs-não-DE que não é sinal de qualidade; (3) language separa
os extremos mas é proxy do idioma do anúncio; (4) FP alemães de
varejo/aprendizagem entraram pela janela "Logistikdienstleistung" da BA —
gap de FILTRO (tipo do v1 §4.4.4), não do ranking. Tudo isso vira card
futuro com decisão do dono — este card é a linha de base.
