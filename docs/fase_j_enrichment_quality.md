# Fase J — Deterministic Enrichment Quality Fixes

> Status: IMPLEMENTADA (branch `feature/fasej-enrichment-quality`).
> Escopo: 4 correções determinísticas de QUALIDADE dos detectores
> pós-eligibilidade (`job_salary` / `work_authorization`). Nada aqui toca
> eligibility, score, pesos, ranking, Top 30, dedup, mirror-dedup,
> hydration, official-page, JSON-LD, cron, Telegram, publicação ou
> integração LLM. Sem LLM, sem parser paralelo — tudo dentro de
> `opportunity_intel.py` e `app_intel.py`, reusando `_MONEY_CLAUSE` /
> `_to_number` / vocabulário existentes.

## 1. Os 4 problemas (causa-raiz, reproduzida offline no dataset 409)

### P1 — `/h` classificado como mês (gap G3 da Fase H)
`_HOURLY_AFTER_RE` não conhecia o "h" curto. Casos reais: VW `18,33 €/h`
(×2), philips `15 €/h oder 17 €/h` (×2), VDI `(16€/h)`. O valor já era
capturado corretamente pela Fase G em VW/philips; só o período estava
errado (default month). No VDI o valor vivia no TÍTULO e o conjunto
(€ colado + `/h` imediato) só passa o gate com o marcador horário — vaga
ficava sem salário.

### P2 — FP `12 Monate befristet` → `12 €/month` (gap G4)
Dois defeitos combinados no caminho textual de `job_salary`:
- (a) o grupo period do `_MONEY_CLAUSE` casava o PREFIXO `Monat` de
  `Monate` (sem `\b`) → `has_period=True` para durações ("6 Monate",
  "12 Monate", "150 Jahren");
- (b) o gate de label aceitava label da frase SEGUINTE pela janela
  forward 60 chars — Fraunhofer "Die Stelle ist zunächst i. d. R. auf
  12 Monate befristet. Die Vergütung richtet sich…" → cláusula
  `12 Monat` passava `(has_label and has_period)` SEM moeda → FP
  `12 €/month`.

### P3 — WA condicionais `if indicated` / `falls erforderlich` (gap G6)
`_WA_CONDITIONAL` (Fase F) cobria ggf./gegebenenfalls/wenn vorliegend/if
applicable/where applicable/if you have — mas NÃO `if indicated`
(Bosch ×5) nem `falls erforderlich` (continental ×2). O mecanismo
sentence-scope `_wa_existing_evidence()` já existia e é correto —
faltavam só os 2 marcadores. Scan do dataset 409: equivalentes próximos
(`if required`, `if needed`, `where required`, `falls nötig`, `sofern
erforderlich`, `bei Bedarf`) têm ZERO ocorrências — o vocabulário NÃO foi
generalizado além dos 2 evidenciados.

### P4 — salário anual lido como mensal (autorizado pelo dono 30/09)
O period group só captura período como SUFIXO ("per year"); formas com
label ANTES do valor eram invisíveis: BASF EN "Gross annual salary
(full-time): 40.000 - 46.000 €" → `40.000 €/month`; BASF DE
"Bruttojahresgehalt (Vollzeit): …" → `None` (`\bgehalt\b` não casa
composto); VW "Der Bruttostundenlohn … 18,33 €" → `None` (label a 53
chars: fora da janela 40 do gate, dentro da 60 do `_is_hourly_clause`).

## 2. Correções (design §2 da spec, implementado exatamente)

### J1 — `/h` horário
`_HOURLY_AFTER_RE` ganhou 2ª alternativa com prefixo OBRIGATÓRIO
(`^\s*(?:/|per\s+|pro\s+)\s*h\b`) — "h" solto continua sem casar; a 1ª
alternativa (`stunde|hour`) preserva 100% o comportamento pré-J.

### J2 — mata o FP `12 Monate`
1. Grupo period com `\b` nas duas pontas:
   `(?P<period>\s*(?:per\s+)?\b(?:monat|month|jahr|year)\b)?`.
   Verificado no dataset: NENHUM salário atual dependia desse grupo
   (dos 32, só o FP Fraunhofer tinha `has_period=True`). "€/Monat" não
   casa (barra) — igual antes; "monatlich" não casa — sem efeito
   (default já é month).
2. Label forward só conta NA MESMA SENTENÇA: terminador `[.!?;](\s|$)`
   entre o fim da cláusula e o label corta a janela forward 60. O
   BACKWARD (40 chars) segue cruzando sentenças — ASSIMETRIA
   DELIBERADA: o FP evidenciado é forward; backward cross-sentence não
   tem evidência de problema e mexer nele amplia a superfície de
   regressão. Fraunhofer morre DUAS vezes (`\b` + same-sentence).
   Caso preservado: roche `€2268` (label "Vergütung" forward NA MESMA
   sentença) — continua month.

### J3 — WA condicionais
`_WA_CONDITIONAL` += `\bif\s+indicated\b` e `\bfalls\s+erforderlich\b`.
MAIS NADA. Os 7 casos caem no mecanismo da Fase F (condicional entre o
início da sentença e o match de `_WA_EXISTING_RE` suprime `existing`) →
vaga cai no fluxo padrão → `unclear`. Não é a regra simplista
"marker ⇒ unclear em todo o texto".

### J4 — período `year` + labels compostos
1. `_SALARY_LABEL`: `gehalt` → `\w*gehalt\b` (compostos
   `Monatsgehalt`/`Jahresgehalt`/`Bruttojahresgehalt`; `Gehaltsvorstellung`/
   `Gehaltsangabe` continuam NÃO-label — o `s` pós `gehalt` quebra o
   `\b` final; `Gehälter` (ä) não casa — verificado).
2. `_HOURLY_LABEL_RE`: `\bstundenlohn\b` → `\w*stundenlohn\b` (idem
   `stundenvergütung`) — pega `Bruttostundenlohn`.
3. NOVO `_YEARLY_LABEL_RE` (`\w*jahresgehalt\b|\w*jahresvergütung\b|annual|yearly
   + salary|compensation|pay|wage`).
4. NOVO `_YEARLY_AFTER_RE` (`/`, `per`, `pro` + `jahr|year|jährlich|jaehrlich`)
   — fecha a limitação "€50,000/year" da Fase G (0 ocorrências no
   dataset; coberto por testes).
5. NOVO `_is_yearly_clause`: espelho EXATO do `_is_hourly_clause`
   (backward 60 label / forward 20 after, mesmo guard de fragmento
   decimal/sufixo numérico). O guard foi extraído no helper compartilhado
   `_clause_is_number_fragment` (~4 linhas) usado por ambos — sem mudança
   de comportamento.
6. Gate em `job_salary`:
   `has_label` += `_YEARLY_LABEL_RE`; forward 60 cortado no fim da
   sentença (J2.2);
   `is_hourly`/`is_yearly` computados por cláusula;
   gate `(has_currency and (has_label or has_period or is_hourly or
   is_yearly)) or (has_label and has_period)` — marcador horário/anual
   COM moeda é evidência de salário por si (necessário para VW
   "Bruttostundenlohn… 18,33 €", label a 53 chars). A 2ª disjuntante
   (label+period sem moeda) permanece ("Salary 3,000 per month").
7. Resolução: `is_hourly` → "hour"; senão `is_yearly` → "year"; senão
   sufixo jahr/year → "year"; senão "month" (hourly vence yearly —
   sem conflito real no dataset).
8. `_to_number`, `_MONEY_CLAUSE` fora do grupo period, caminho
   estruturado recruitee, `_norm_period`: INTOCADOS.

## 3. A/B — 3 camadas (dataset 409 congelado, run 29/09 09:00 UTC)

Baseline congelada (sha256 `206dc4ef39e22499…`): 409 eligible; salary 32
(month 29 · hour 2 · year 0 · estruturado 1); WA existing_required 17 ·
unclear 59 · not_mentioned 333. Lado A = venv do repo de produção
(código main `e5be3b1`); lado B = venv do clone com a Fase J; flags
idênticas; 100% offline.

### Camada 1 — salary/WA por vaga sobre o 409 congelado
- **Salary 32 → 36**: month 29→22 · hour 2→9 · year 0→4 · estruturado 1.
  - Período corrigido (6): VW 1437020633 + 1441878133 (18,33 month→hour),
    philips 587973 + 586887 (15 month→hour), BASF 1392273633 +
    1424780033 (40.000–46.000 month→year).
  - FP morto (1): Fraunhofer 1293773901 `12 €/month` → `None`.
  - FN ganho (4): VW 1436085733 + 1437959833 (→18,33 hour,
    Bruttostundenlohn composto), BASF 1409890633 (→35.000–39.000 year) +
    1424780133 (→40.000–46.000 year).
  - **Novo auditado fora da tabela da spec (1): VDI 67324705 None →
    16 €/hour.** O título real é `Werkstudent*in Einkauf (16€/h)` —
    moeda + marcador horário reais. O §1 da spec lista VDI entre os
    casos reais de P1, mas a tabela §4 (previsão 35) não o incluía
    (a spec assumia "o valor já é capturado" — no VDI ele NÃO era, pois
    só o marcador `/h` o resgata do título). Auditoria 1-a-1 conforme
    regra §4 para novos salários: LEGÍTIMO. Total: 36 (não 35).
  - Idênticos: 25 (incl. roche €2268, STIHL 2.117, Tchibo 2.570, MAHLE
    1500€, CURRENTA estruturado, covestro 21/h, VW 17,80 €/Stunde) —
    `text` NUNCA mudou para os preservados.
- **WA 17 → 10 existing_required; unclear 59 → 66**: flips = EXATAMENTE
  os 7 condicionais (Bosch ×5 `if indicated`, continental ×2 `falls
  erforderlich`), todos → `unclear`. Os 10 que ficam = MAHLE ×6,
  teampicnic ×3, VW 1415181033 (`existing` real: EU citizenship /
  Nicht-EU-Bürger Aufenthaltstitel erforderlich). ZERO outras mudanças
  de estado. Support/no_sponsorship: 0 (inalterados).
- 19 diffs no total — **zero fora do previsto** (11 da tabela + 7 WA +
  VDI auditado).

### Camada 2 — pipeline completo (invariância)
Mesmo input (`jobs.json` 220,5 MB congelado), flags idênticas
(`--country europe --no-hydrate-descriptions --no-official-page`,
modo filtro offline, `--metrics` em /tmp):
- Lado A sha256 `c8114b4fc64aa3a5d822bb49ed209b93b50523879fc2993fcb9b8a33ce998b99`
- Lado B sha256 `c8114b4fc64aa3a5d822bb49ed209b93b50523879fc2993fcb9b8a33ce998b99`
- **eligible JSON byte-idêntico** (635 ids mesma ordem, mesmos scores,
  breakdowns, Top 30, dedup). Salary/WA não são campos do eligible —
  manifestam-se só no render.

### Camada 3 — render (interface.py, flags explícitas)
Flags explícitas nos dois lados (`--db-join`, `--enrichment`,
`--company-intel`, `--location-intel` — pitfall de auto-detect da Fase G)
+ `--ref-date 2026-09-29` fixo:
- Sobre o 409 congelado: 818 rows (409 × 2 perfis) idênticos na ordem;
  **38 rows divergentes = exatamente 19 ids × 2 perfis** — a tabela §4
  completa (11 salary) + 7 WA + VDI auditado. ZERO diffs fora.
- Universo 635 do pipeline offline (extra): +5 ids divergentes, todos
  AUDITADOS 1-a-1 e legítimos (mesmos fixes agindo em vagas fora do
  congelado, sem description hidratada no run offline):
  - BMW 1248603201: main tinha o MESMO FP da classe P2 ("duration of
    **12 months** with a salary of € 2.303,00" → main: `12 €/month`);
    fase J reporta o salário REAL `€ 2.303,00/month`.
  - VW 1437064533: main=None (FN composto "Monatsbruttogehalt von
    € 2.174"); fase J: `€ 2.174/month` (label+moeda reais).
  - simon-kucher ×3: main tinha FP `40 €/year` ("over **40 years** of
    experience … willing to **pay**" — prefixo de duração + label "pay"
    de outra frase); fase J: `None`. O `\b` do J2.1 mata os 3.

### Invariante global
Eligible ids/scores/ordem/Top 30/breakdowns/dedup IDÊNTICOS (camada 2
byte-idêntica). Salary/WA nunca alimentaram score — confirmado
empiricamente pelos 635 ids com scores iguais nos dois lados.

## 4. Casos reais corrigidos (por id)

| id (sufixo) | empresa | antes | depois |
|---|---|---|---|
| VWAGLPPROD10:1437020633 | VW | 18,33 €/month | 18,33 €/hour |
| VWAGLPPROD10:1441878133 | VW | 18,33 €/month | 18,33 €/hour |
| philips:587973 | philips | 15 €/month | 15 €/hour |
| philips:586887 | philips | 15 €/month | 15 €/hour |
| basf:1392273633 | BASF | 40.000–46.000/month | 40.000–46.000/year |
| basf:1424780033 | BASF | 40.000–46.000/month | 40.000–46.000/year |
| fraunhofer:1293773901 | Fraunhofer | 12 €/month (FP) | None |
| VWAGLPPROD10:1436085733 | VW | None | 18,33 €/hour |
| VWAGLPPROD10:1437959833 | VW | None | 18,33 €/hour |
| basf:1409890633 | BASF | None | 35.000–39.000/year |
| basf:1424780133 | BASF | None | 40.000–46.000/year |
| vdijobs:67324705 | VDI | None | 16 €/hour (auditado §3) |
| BoschGroup ×5 (744000151022049, 744000151296789, 744000144711789, 744000144712529, 744000147012239) | Bosch | existing_required | unclear (`if indicated`) |
| continental ×2 (744000149805950, 744000150080299) | continental | existing_required | unclear (`falls erforderlich`) |

## 5. Testes

`scripts/test_fasej.py` (45º do CI, 60 checks, 100% offline): grupos
A (`/h` horário, decimais EN/DE, com/sem label, "h" solto não casa),
B (`12 Monate` adversarial — incluindo o Fraunhofer real e
`12 Monatsgehälter à 1.500 €` → captura o valor REAL 1500, não 12),
C (durações `6 Monate`/`2 Jahre` → None; mensais reais preservados),
D (year: BASF EN/DE, `€50,000/year`, `Jahresgehalt:`, sufixo `pro Jahr`),
E (hourly composto: VW 53 chars, `Stundenlohn: 21 €`, covestro Fase F),
F (WA: os 7 da spec + não-regressões Fase F), G (não-regressão geral:
roche/STIHL/Tchibo/MAHLE/covestro/CURRENTA estruturado/determinismo),
H (adversarial `\w*gehalt`: `Gehaltsvorstellung` NÃO é label;
`Monatsgehalt` é; `Gehälter` documentado).
Suíte completa no clone: 44/45 OK — `test_lifecycle` é a única falha,
PRÉ-EXISTENTE e reprodutível na base `e5be3b1` LIMPA sob Python 3.14
(venv do clone); produção/CI usam Python 3.12 (passa). Não relacionado
à Fase J.

## 6. Limitações e backlog

- **`X Euro/Stunde` por extenso** ("12 Euro/Stunde"): o post group
  captura `Eur` e deixa `o/Stunde` — `period=month` (pré-existente
  main=branch; alternância `€|eur|euro` é ORDERED). A spec J1 dizia que
  isso "já funciona hoje" — NÃO funciona, nem antes nem depois (0
  ocorrências no dataset 409; codificado no teste A8 como defesa
  latente). Corrigir exigiria tocar o `_MONEY_CLAUSE` fora do grupo
  period — fora de escopo (intocável por spec).
- **`pro Jahr`/`monatlich` ANTES do valor** ("pro Jahr 50.000 €"):
  continua `month` default — o `_YEARLY_AFTER_RE` só casa marcador como
  SUFIXO (após o valor), como especificado. Documentado no teste D6.
  (`"Vergütung: 50.000 € pro Jahr"` — sufixo — captura year
  corretamente via `has_period` pré-existente.)
- **WA caso (7) da spec §6-F**: o literal "valid work permit required,
  relocation assistance provided" (MESMA sentença, vírgula) retorna
  `support` — PRÉ-EXISTENTE na main: o `_WA_SUPPORT` bidirecional
  (janela 25 chars) casa "work permit … assistance" atravessando
  "relocation". O INTENTO da regra (existing vence contexto de
  relocation) é coberto pelo teste F7 com sentença separada (→
  `existing_required`) e pelo caso análogo pré-existente do
  `test_fasef.py` ("…must already have a valid work permit. We can
  provide relocation assistance." → existing_required). Mexer na
  janela do `_WA_SUPPORT` é fora de escopo J3 ("+2 patterns, MAIS
  NADA") — registrado como backlog.
- **`Gehälter`/`Monatsgehälter`** (ä/umlaut) não casam `\w*gehalt\b` —
  comportamento documentado; "12 Monatsgehälter" com contexto
  monetário real captura o valor REAL (teste B6), nunca o "12".
- German/English detection conflicts, phenom teasers, NVIDIA/LLM ops,
  Telegram >4096, SAP upstream issue: backlog fora de escopo (crônico).

## 7. Arquivos alterados

- `src/internship_finder/opportunity_intel.py` — J1, J2, J4
- `src/internship_finder/app_intel.py` — J3 (2 padrões no `_WA_CONDITIONAL`)
- `scripts/test_fasej.py` — novo (45º do CI)
- `.github/workflows/ci.yml` — array +1
- `docs/fase_j_enrichment_quality.md` — este documento
