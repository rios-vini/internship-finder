# Fase F — Correções determinísticas pós-spike (WA condicional, student subtype, salary hourly)

**Data:** 28–29/09/2026 · **Branch:** `feature/fasef-deterministic-fixes` ·
**Spec do dono:** Fase F — Deterministic Enrichment Fixes (PR #89 como evidência).

Corrige SOMENTE os gaps com evidência suficiente para virar regra determinística,
descobertos pela Fase E (spike LLM isolada). **Nenhum LLM no pipeline** (a spike
permanece experimento histórico); **ranking/eligibility/score/dedup/pesos
intocados** (spec §12).

## P0 — Work authorization: condicionais não são exigência pre-existente

### O problema (evidência da spike)

6/6 casos `llm_missing` da Fase E eram o detector classificando como
`existing_required` uma autorização citada **condicionalmente** no checklist de
documentos da aplicação:

| job | evidência problemática | interpretação correta |
|---|---|---|
| Bosch ×5 (SR) | "sowie **ggf.** eine gültige Arbeits- und Aufenthaltserlaubnis bei" | "se aplicável" — o anúncio pede o documento SE houver; não exige autorização pré-existente |
| STIHL (SF) | "sowie **wenn vorliegend** Arbeitszeugnisse und deine gültige Arbeits- und Aufenthaltserlaubnis" | "se houver/existindo" — idem |

### A regra

`_wa_existing_evidence()` (app_intel.py) — guard **sentence-scope** sobre o
caminho `existing`:

- O qualificador condicional ("ggf.", "gegebenenfalls", "wenn vorliegend",
  "if applicable", "where applicable", "if you have/hold/possess") suprime o
  match de `_WA_EXISTING_RE` **apenas quando aparece entre o início da SENTENÇA
  e a evidência** (verbo/tema/objeto na mesma unidade semântica — spec §3).
- Abreviações alemãs com ponto ("ggf.", "z.B.", "bzw.") são **mascaradas**
  antes do cálculo de início de sentença (o ponto interno não é fim).
- **Não é** a regra simplista "ggf. ⇒ unclear" (proibida pela spec): a
  precedência `no_sponsorship > support > existing > unclear` e TODO o resto do
  detector seguem intactos; apenas a **evidência** que alimenta
  `existing_required` ganhou checagem contextual.
- Se TODAS as evidências `existing` estão sob condicional, a vaga sai de
  `existing_required` e cai no fluxo padrão (vocab presente sem outra
  classificação ⇒ `unclear`).

Continuam válidos (spec §4): "must already have", "bereits vorhanden",
"vorhandene Arbeitserlaubnis", "gültige Arbeitserlaubnis erforderlich" —
nenhuma condicional na mesma sentença.

### Correção lateral (janela de suporte 30→32)

"Wir unterstützen Sie bei der Beantragung einer Arbeitserlaubnis" (adversarial
spec §6-F) tem 31 chars entre verbo e tema — a janela de 30 não casava.
Medido no dataset: janela 32 adiciona **0** novos matches de suporte em
produção (a correção ativa apenas o caso-prova da spec).

### Métricas (dataset 28/09, 3.555 eligible pós-pipeline)

| estado | antes (main) | depois (branch) |
|---|---|---|
| existing_required | 190 | 64 |
| unclear | 98 | 224 |
| not_mentioned / no_sponsorship | 3.264 / 3 | 3.264 / 3 |

126 vagas deixaram de ser rotuladas `existing_required` — todas com
condicional real no texto (auditoria de amostra: 15/15 flips legítimos no
snapshot de 404; 100% deles Bosch "ggf.", STIHL "wenn vorliegend", VW "If
applicable"). Zero mudanças em outras categorias.

## P1 — Student subtype (enrichment puro)

Novo campo `student_type` (app_intel.py): subtipo de vaga estudantil
computado **apenas para vagas que JÁ são student-role pelo filtro atual**
(gate `filters.is_student_role` com os MESMOS inputs do filtro — nunca
reclassifica; spec §7).

Valores e evidência exigida (spec §8):

- `working_student` — "Working Student"/"Werkstudent" (inequívoco);
- `mandatory_internship` — "Pflichtpraktikum", "mandatory internship", ou
  exclusividade/escopo explícito ("nur Pflichtpraktika", "ausschließlich
  Pflichtpraktikum", "we can only offer mandatory internships");
- `voluntary_internship` — "freiwilliges Praktikum"/"voluntary internship"
  explícito (NUNCA inferido pela ausência de "mandatory");
- `internship` — Praktikum/Internship genérico;
- `unclear` — student-role sem evidência de subtipo.

**Guardas anti-FP da audit de produção** (cada um com caso real citado no
código):

- Enumeração de opções ("Ob Pflicht- oder freiwilliges Praktikum" — Telekom ×2,
  trumpf) ⇒ genérico, não classifica;
- Checklist condicional de documentos ("Bei einem Pflichtpraktikum
  zusätzlich..." — Volkswagen ×3) ⇒ não classifica a POSIÇÃO;
- Voluntário negado ("purely voluntary internships cannot be offered" — MAHLE
  ×2) ⇒ Praktikum alemão é binário Pflicht/freiwillig ⇒ `mandatory_internship`;
- Conflito title×description com subtipos ESPECÍFICOS divergentes (ex. title
  "Working Student" × description "Pflichtpraktikum") ⇒ registrado em
  `conflict=True`, valor publicado `unclear` (registro, nunca arbitração —
  spec §9, padrão `structured_fields.employment_type_relation`); o genérico
  "internship" REFINA em vez de conflitar.

UI (spec §13): linha única no Candidate Fit ("Tipo de vaga estudantil:
Working Student (Werkstudent)") para subtipos específicos; o genérico
`internship` NÃO emite linha (não duplicaria o sinal student_type existente).

Distribuição (3.555 eligible): 1.757 internship / 670 working_student /
196 mandatory_internship / 916 unclear / 16 voluntary_internship /
0 conflitos.

## P2 — Salary hourly (extensão mínima)

Extensão do `job_salary` (opportunity_intel.py) para período horário:

- Rótulo antes: "Stundenlohn von 21 Euro" (Covestro — caso da spike),
  "Stundenlohn: 15 €", "hourly rate/wage" (EN);
- Marcador depois: "13 €/Stunde", "€21 per hour".

`period="hour"` (label ptbr "hora"). O caminho estruturado (raw salary_*),
mensal e anual seguem IDÊNTICOS (A/B: 208→208 month, 8→8 year).

Métrica: **14 novas vagas com salário** (todas Werkstudent/HiWi —
"hourly wage €17.50", "hourly rate: €18.06/hour", "Stundenlohn beträgt 14
Euro", "18 €/Stunde"); no main, 12 delas não tinham salário e 2 eram rotuladas
"€18/mês" (absurdo para Werkstudent).

**Limitação conhecida e aceita pelo dono (29/09)**: o `_MONEY_CLAUSE`
pré-existente trunca decimais alemães (€17,50 → captura "17"); os casos
hourly com decimal ficam sub-estimados (€17/hora em vez de €17,50/hora —
nunca inflados). Corrigir o decimal toca o core do parser de TODOS os
salários textuais (mensais inclusos) — fora do escopo desta fase; registrado
como backlog. O guard de fragmento decimal impede que o FRAGMENTO pós-vírgula
(ex. "80" de "17,80") seja rotulado hourly.

## P3 — German/English: NÃO implementado (backlog documentado)

A spike indicou 3 conflitos German (ABB "Ideal for candidates with strong
German", Bosch "verhandlungssicheres Deutsch" ×2) e 2 English (typo "Englis h"
do feed, 2× celonis). Root cause investigada:

- **German bosch**: "wünschenswert" de OUTRA frase a <45 chars do token
  suprime o `verb_rev` legítimo ("verhandlungssicheres Deutsch") — a janela de
  qualificadores mistura frases vizinhas.
- **German ABB**: "strong German and English skills" — o qualificador
  `qual` não casa "strong" sem palavra de língua imediatamente após.
- **English**: typo do feed "Englis h" quebra o word-bound `\benglish\b`.

**Por que não nesta fase**: `german_level` e `english_evidence` alimentam o
SCORE diretamente (ranking.py `_language_score`: PENALTY_LANG_DE_REQUIRED
−2.0, PREFERRED −0.5, WEIGHT_LANG_EN +1.5). Qualquer correção nesses
detectores muda scores/ordem — a spec §12 desta fase PROÍBE mudança de
score/ranking. Os fixes ficam como backlog para uma fase que autorize
calibração de score.

## A/B (spec §14)

- **Pipeline completo** (3555 eligible, jobs.json produção 222MB, flags
  idênticas `--no-hydrate-descriptions --no-official-page` — offline puro):
  **ids idênticos na mesma ordem, 0 score diffs, Top 30 idêntico, 0 diffs em
  qualquer campo de pipeline** (score/score_breakdown/eligibility/dedup/
  description/...). Um par A/B com rede (default) mostrou 2 score diffs por
  GETs em momentos distintos (variância conhecida da Fase A) — A/B decisivo é
  o offline.
- **Render** (interface.py sobre eligible_jobs.json 404): 60/60 ids
  idênticos, scores idênticos; diffs = exatamente o enrichment novo (WA
  🔴→🟡 nos corrigidos; linha de subtipo adicionada).

## O que NÃO mudou

eligibility, score, pesos, ranking, Top 30, dedup, publication gate, cron,
enrichment LLM (permanece OFF no pipeline), spike_e (histórico isolado),
histórico SQLite, Pages. O WA corrigido usa a UI existente (chips/fit lines);
salary usa a apresentação atual; student type é uma linha a mais no bloco de
fit — nenhuma nova seção grande.

## Testes

`scripts/test_fasef.py` (74 checks, 100% offline, 42º no CI):
6 casos da spike (textos verbatim), 7 adversariais da spec §6, escopo de
condicional (sentença × documento), 14 regressões do test_app_intel,
determinismo (100×), student (working/mandatory/voluntary/genérico/unclear/
conflito/não-student/anti-FP de produção), salary (hourly ×4 formatos,
mensal/anual/inválidos, guard de decimal).
