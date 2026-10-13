# F25 — Reavaliação de aplicabilidade pós-hidratação sobre o backlog

**Data:** 2026-10-13 · **Branch:** `feature/f25-backlog-reassessment` · **Status:** PR aberto, aguardando merge do dono

## O buraco

O estágio Fase A roda `filters.select_eligible` (applicability hard-exclude
da F18) **ANTES** de `hydrate_descriptions`. A F20 já reavalia a
aplicabilidade depois de hidratar, mas **só para as vagas que aquele passe
do liveness hidrata** (top exibido, `description_hydrated_at` novo). Vagas
hidratadas pelo estágio Fase A — cuja descrição completa revela
`german_required` — ficavam no backlog **sem marcador**, recomendadas no
digest para um dono com alemão A1–A2.

Medição 12/10 no `eligible_jobs.json` real: **126 de 783 vagas (16,1%)**
com `german_level=required` pelo detetor oficial, **todas** com
`description_source=="hydration"`, **zero** com `hydration_inapplicable`,
incluindo o topo do ranking (Bosch 15,5, nº1).

## A correção (sem estágio novo no filtro)

`_reassess_backlog_applicability(ranking)` em `scripts/refresh_daily.py`,
chamado a cada run entre o liveness e o publish:

- Candidatos: TODAS as vagas de `eligible_jobs.json` com
  `description_source=="hydration"` que AINDA NÃO têm
  `hydration_inapplicable` (idempotente — já-flagadas nunca re-flagam).
- Reuso obrigatório: cada candidata passa pela MESMA reavaliação da F20
  (`_reassess_hydrated_applicability` → detetores puros da F18). Zero
  lógica paralela.
- Persistência: flag gravada na vaga + `_write_json_atomic` no
  `eligible_jobs.json` (somente quando há novas flagadas — sem hidratadas
  ou nada a flagar, o arquivo fica **byte a byte idêntico**, preservando a
  regressão F22).
- Semântica F20: flag ⇒ desce das superfícies exibidas (página
  `minimal_page` + os DOIS Top 5 do digest via `excluded_ids`,
  unificados com as mortas do liveness), **fica no JSON**.
- Métricas: registro próprio `type: hydration_reassessment` no JSONL
  (`reassessed` / `newly_flagged` / `by_reason`) + linha de log.
  Contadores `applicability_excluded_*` do select_eligible intocados.
- Best-effort total: qualquer falha do estágio vira log; o run segue com
  o exit da coleta.

`filters.select_eligible`, `app_intel.german_level/requires_master`,
pesos/ranking/Top-30/dedup: **intocados**.

## A/B offline (snapshot real 13/10, cópia em /tmp — produção intocada)

| Métrica | Antes (A) | Depois (B) |
|---|---|---|
| Vagas no eligible | 783 | 783 (mesmas, mesma ordem) |
| Hidratadas (`description_source=="hydration"`) | 162 | 162 |
| Com marcador `hydration_inapplicable` | 0 | **126** |
| Hidratadas aplicáveis (sem marcador) | 162 | 36 |
| Não-hidratadas | 621 | 621 — **0 tocadas** |
| Campos mudados por vaga | — | só a flag (diff de dicts, nenhum outro campo) |
| Top 5 exibido | nº1 e nº2 = Bosch 15,5/14,75 german-required | descem; nº1 novo = Bosch 14,5 aplicável |

- Baseline independente (detetor F18 oficial sobre todas as hidratadas):
  **126 `german_required`** — o estágio flagou exatamente as 126
  (`newly_flagged == baseline`), `by_reason={german_required: 126}`.
- Scores das flagadas: 3,5 a **15,5** (o nº1 do ranking).
- Top-5 antes: 1. Praktikum Logistik Data & Analytics (Bosch, 15,5)
  ❌inaplicável · 2. Pflichtpraktikum Logistik (Bosch, 14,75)
  ❌inaplicável · Top-5 depois: 1. Praktikum Beschaffungsplanung Supply
  Chain (Bosch, 14,5) · 2–3. Bayer 14,25/14,0 · 4. teampicnic 14,0 ·
  5. KPMG 14,0 — **nenhuma vaga flagada em nenhuma superfície**
  (verificação: render com `excluded_ids` == render da lista
  pré-filtrada, byte a byte, nos dois Top 5).
- Idempotência: 2ª passada `reassessed=36, newly_flagged=0` (flagadas
  puladas); JSON estável.
- `data/` real: byte-identical antes==depois (sha256 verificado).

## Testes

- `scripts/test_f25.py` — 100% offline, **54 checks**: núcleo puro
  (flag/ordem/byte-a-byte), idempotência, persistência atômica,
  exclusão nas superfícies (página + 2 Top 5 do digest), e2e do refresh
  com mocks de disco (estágio roda, persiste, publica com ids unificados,
  registra no JSONL), regressão F22 (sem hidratadas → arquivo byte a
  byte idêntico), robustez (não-dicts, lista vazia).
- Suíte completa: 67→68 scripts verdes no clone (Python 3.12, mesma
  versão do CI/produção). `test_lifecycle` no host local sob Python
  3.14 falha **pré-existentemente no main puro** (mudança de
  multiprocessing no 3.14, não relacionada à F25 — CI roda 3.12).

## O que o dono verá no próximo digest

As vagas impossíveis (alemão C1+ exigido) saem do Top 5; vagas aplicáveis
sobem. As 126 flagadas continuam no `eligible_jobs.json` com o marcador
`hydration_inapplicable="german_required"` — auditável, reversível,
sem perda de dado.
