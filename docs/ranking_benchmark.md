# Benchmark do ranking (P2.5) — medir antes de alterar

> Tarefa P2.5: **medição** do ranking heurístico atual com vagas reais
> rotuladas manualmente, antes de qualquer mudança de pesos/formula/regras.
> Nenhuma alteração de comportamento foi feita nesta tarefa — o ranking
> (`src/internship_finder/ranking.py`) segue sendo a implementação de
> referência e seus testes não foram tocados.

## 1. Existência e formato

- **Dados versionados**: `benchmarks/ranking_benchmark_v1.json` (45 KB,
  59 vagas) — a parte humana (rótulos + justificativas) e o congelamento do
  snapshot (rank, score, score_breakdown) vivem no Git; não dependem de
  planilha externa.
- **Análise**: `scripts/ranking_benchmark.py` (relatório) e
  `src/internship_finder/ranking_benchmark.py` (funções puras, stdlib).
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