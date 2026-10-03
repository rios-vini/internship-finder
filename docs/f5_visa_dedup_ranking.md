# Fase F5 — visa_friendly + dedup UTM/DE-EN + ranking weights

**Data**: 03/10/2026 · **Branch**: `feature/f5-visa-dedup-ranking` (base `main`
`36319f0` = F4 mergeada) · **Commit**: `F5: visa_policy signal, dedup utm/DE-EN, ranking weights`

## O que a F5 é

A auditoria diagnosticou 4 problemas; a F5 CONECTA infraestrutura que já
existia (não recria):

1. **visa_friendly (sinal de EMPRESA)** — `opportunity_intel.visa_policy_state()`
   era código morto para o pipeline: madura e testada, mas sem ligação com
   ranking/filtros/output. A F5 liga: vaga de empresa com estado
   `explicit_support` OU `unclear` recebe `visa_friendly: true` no
   JSON/CSV/HTML. O filtro non-EU do HTML passa a ler ESTE campo (o filtro
   antigo dependia do enrichment de vagas desligado pela F1 — texto 100%
   "Not mentioned", 0 vagas). **Regra de independência preservada**: o sinal
   NÃO entra no score de relevância (badge/filtro aditivo); se o dono quiser
   peso, será fase futura.

2. **Curadoria expandida** — 12 → 16 empresas com visa_policy, cada estado
   verificado com fonte (link + citação textual + quality + checked):
   - BASF SE → **unclear** ("We support non-EU citizens with visa
     applications once our offer is accepted" — página oficial da divisão
     Management Consulting; condicional e escopo-divisão, não empresa
     inteira);
   - Volkswagen AG / Mercedes-Benz Group / Siemens →
     **candidate_must_have_authorization** (declarações oficiais de que
     non-EU precisa de work permit própria — NEGATIVO para BR, e por isso
     NÃO são visa_friendly);
   - Allianz / Deutsche Telekom → **not_verified** com nota (páginas
     checadas 03/10 sem declaração);
   - 0 explicit_support: nenhuma empresa declara suporte incondicional —
     honestidade da curadoria mantida.

3. **Dedup UTM + tier DE/EN** — `normalize_url()` remove params de tracking
   (prefixo `utm_*` por convenção + lista fixa gclid/fbclid/ref/source...)
   ANTES da chave URL, PRESERVANDO params funcionais (pid, page, id — a
   identidade de vagas eightfold vive na query). Novo tier 4
   (`company+title+location+de/en`): título com dicionário mínimo
   DE→EN de conteúdo (Logistik↔Logistics, Einkauf↔Purchasing...; marcadores
   de tipo Praktikum↔Internship JÁ eram equivalentes no tier 3) + cidade
   com alias EN↔DE (München/Munich → munchen, mesma tabela da Fase 7).

4. **WEIGHT_AREA_DESC** — experimento offline (ver §Experimento): valor
   **0.0 MANTIDO**; evidência a favor de W>0 foi fraca e o FP original da
   calibração não está na amostra. Documentado em código.

## Onde cada coisa vive

| Item | Arquivo | Função/campo |
|---|---|---|
| Estados visa_friendly | `src/internship_finder/opportunity_intel.py` | `VISA_FRIENDLY_STATES`, `visa_friendly(intel)` |
| Derivação no pipeline | `src/internship_finder/cli.py` | `_apply_visa_friendly()` (após rank, aditivo) |
| Contrato de saída | `src/internship_finder/cli.py` | `CSV_COLUMNS` + `visa_friendly` (última coluna) |
| Badge/filtro HTML | `scripts/interface.py` | `badge-vf`, `data-vf`, checkbox `f-vf`, JS `if_match` |
| Dedup tracking | `src/internship_finder/dedup.py` | `_is_tracking_param`/`_strip_tracking_params` em `normalize_url` |
| Tier DE/EN | `src/internship_finder/dedup.py` | `CONTENT_TRANSLATIONS`, `_de_en_title_key`, `_de_en_location_key`, 4ª chave |
| Curadoria | `company_intel/company_intelligence.json` | 16 empresas |
| Ranking | `src/internship_finder/ranking.py` | `WEIGHT_AREA_DESC` comentário do experimento |
| Testes | `scripts/test_f5.py` | 77 checks, 100% offline (49º do CI) |

## Impacto medido (snapshot eligible 478, 02/10 23:xx UTC)

- `visa_friendly: true` em **115/473 vagas (24%)** — SAP 58 + Bosch 43 +
  BASF 14; Volkswagen AG (28 vagas) corretamente False.
- HTML: 15 badges no Top-40 business (SAP/Bosch dominam o topo).
- A/B main vs branch (mesmo input, `--no-hydrate-descriptions
  --no-official-page`): **0 score diffs nos 473 comuns, ordem relativa
  100% preservada, nenhum outro campo alterado**. As 5 diferenças de
  conjunto são fusões do tier DE/EN — todas Bayer, espelhos DE/EN
  cross-ATS (successfactors↔eightfold) do MESMO cargo na mesma cidade,
  descriptions ~idênticas em tamanho (ex.: "Praktikant*in Analytics
  Advisory & Data Democratization" ↔ "Internship Analytics Advisory & Data
  Democratization"). Zero falsos positivos na auditoria manual par a par.

## Trade-offs do tier DE/EN (documentados)

- **Conservador por construção**: a fusão exige empresa E cidade E TODO o
  conteúdo do título bater pós-tradução; um token fora do dicionário já
  impede a fusão. Falsos positivos exigiriam duas vagas REAIS diferentes
  com títulos que traduzem para a mesma bag na mesma empresa+cidade
  (ex.: "Praktikum Marketing" vs "Marketing Internship" fundem — mas são
  a mesma vaga mesmo; "Praktikum Data" vs "Praktikum IT" NÃO fundem).
- Dicionário mínimo e deliberado: só termos funcionais unívocos; nada de
  jargo de empresa/produto. Alargá-lo é backlog com curadoria por caso.
- O tier 3 original (title exato) continua ANTES do tier 4 — nada muda
  para quem já fundava.

## Experimento WEIGHT_AREA_DESC (§3.4 da spec)

Setup: `benchmarks/ranking_benchmark_v1.json` (59 vagas rotuladas 11/09)
cruzado com o eligible atual (478, descriptions completas) = **29 pares**
(os 30 restantes saíram do eligible por churn; archive começa 19/09 —
snapshots da época rotacionados; N menor declarado). Re-score com
`WEIGHT_AREA_DESC` ∈ {0.0, 0.25, 0.5, 1.0}, métricas Kendall-tau sobre
labels humanos + gap de médias elite/ruim + drift top-10:

| W | tau | gap elite−bad | inversões elite<bad | drift top-10 |
|---|---|---|---|---|
| 0.0 | +0.712 | +6.26 | 3 | — |
| 0.25 | +0.712 | +6.47 | 3 | 0 |
| 0.5 | +0.712 | +6.68 | 3 | 0 |
| 1.0 | +0.732 | +7.10 | 2 | 1 permuta boa↔boa |

Leitura honesta: W=1.0 melhora as métricas MARGINALMENTE, mas as duas
classes sobem JUNTAS (o gap cresce por inflação geral, não por separação),
a amostra N=29 é dominada por vagas do próprio perfil (dados/supply) e o
FP que motivou o 0.0 original (Marketing citando "data" em template SAP)
NÃO está na amostra — o churn o removeu. A calibração original (13.482
vagas reais) continua sendo a evidência mais forte. **Decisão: manter
0.0** e documentar — honestidade > completude. Revisitar quando o
benchmark ganhar vagas FP de template no corte.

## Como reverter

Tudo é aditivo: `--no-dedup` já reverte o tier DE/EN para o comportamento
pré-F5 (os tiers 1–3 são inalterados); o campo `visa_friendly` é ignorado
por qualquer consumidor que não o conheça; o checkbox/badge não afeta
consumidores antigos do HTML (data-attribute novo).
