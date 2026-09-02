# Relatório — Fase 1: correção de ruído de tipo no eligible
> 📜 **Documento histórico** (período da coleta: 2026-08-12). Estado atual e plano: MASTER_PLAN.md + PROJECT_STATUS.md.

Data: 2026-08-12 · Branch: `feat/fix-ruido-tipo` · Correção controlada nº 1 da auditoria pós-expansão (parecer B), autorizada pelo dono.

Escopo: excluir do eligible os tipos NÃO compatíveis com estágio/working student universitário (Duales Studium, Ausbildung, Schul-/Schülerpraktikum e equivalentes, FSJ/BFD). Nenhuma alteração em filtros de área/país, ranking, adapters ou no pacote `ats-scrapers`.

## 1. Regra implementada

`TYPE_EXCLUSION_PATTERNS` em `src/internship_finder/filters.py` — 15 padrões EXPLÍCITOS de título, checados ANTES da aceitação por tipo (mesmo mecanismo da regra Trainee/JMP): a exclusão do tipo vence QUALQUER marcador forte de tipo no título (ex.: "Industriepraktikum … Dual Study Kooperation" é dual, não estágio).

| Grupo | Padrões (regex, título, case-insensitive) |
|---|---|
| Duales Studium e equivalentes | `\bdual\w* stud\w*\b`, `\bdual\w*[:/]*\w* student`, `\bdual\w* hochschule`, `\bdual\w* master` |
| Ausbildung / Berufsausbildung | `\b(berufs)?ausbildungs?` |
| Estágios escolares | `\bsch(ü\|ue)lerpraktikum`, `\bsch(ü\|ue)lerpraktikant`, `\bschulpraktikum`, `\bschulpraktikant`, `praktikum f(ü\|ue)r sch(ü\|ue)ler`, `\bberufsorientierungspraktikum` |
| Serviço voluntário (FSJ/BFD) | `\bfsj\b`, `\bbfd\b`, `\bfreiwilliges (soziales\|(ö\|oe)kologisches) jahr\b`, `\bbundesfreiwilligendienst` |

**O que NÃO exclui** (preservado de propósito):
- Palavra solta: não há pattern de "praktikum" nem de "studium" sozinhos.
- `Hochschulpraktikum` (estágio universitário válido) — o `\b` inicial de `\bschulpraktikum` evita a composição (4 vagas B. Braun preservadas).
- `Pflichtpraktikum` (16 no eligible), `Werkstudent` (53), `Working Student` (63), `Internship`/`Intern` (48), `iXp` (18), `Praktikant` (10).
- Regras de Part-time, Graduate Trainee, Management Trainee, JMP intactas (sem interação: a Fase 1 é um mecanismo independente no mesmo ponto de checagem).

## 2. Funil antes/depois (mesmo `data/jobs.json`, coleta 2026-08-12)

| Etapa | Antes (main) | Depois (Fase 1) | Δ |
|---|---|---|---|
| Brutas coletadas | 56.810 | 56.810 | — |
| Tipo estudante | 4.995 | 3.428 | −1.567 |
| Área-alvo | 914 | 777 | −137 |
| País DE | 406 | 299 | −107 |
| Dedup | −17 | −16 | +1 |
| **Eligible** | **389** | **283** | **−106 (−27,2%)** |

## 3. Removidas: 106 (27,2% do eligible anterior)

| Categoria | Qtde |
|---|---|
| Duales Studium e equivalentes | 89 (2 delas com "Ausbildung" também no título) |
| Ausbildung / Berufsausbildung (puras) | 11 |
| Schülerpraktikum / Schülerpraktikant | 6 |
| **Total** | **106** |

Por empresa (antes → depois):

| Empresa | Antes | Depois | Δ |
|---|---|---|---|
| Lidl (lidlstiftup2) | 103 | 48 | −55 |
| Volkswagen | 42 | 25 | −17 |
| Schaeffler | 25 | 12 | −13 |
| Kaufland | 13 | 3 | −10 |
| MAHLE | 7 | 3 | −4 |
| BASF | 21 | 18 | −3 |
| B. Braun | 8 | 5 | −3 |
| ZF | 2 | 1 | −1 |
| SAP | 91 | 91 | 0 (inalterada) |

Exemplos reais de títulos removidos (do eligible anterior de 389):
- Dual: `Duales Studium BWL - Handelsmanagement / International Retail Management - Bereich Einkauf 2027` (Lidl); `Duales Studium BWL - Handelsmanagement / Retail Management im Bereich Beschaffung 2027` (Lidl); `Duales Studium (TH) inkl. Ausbildung (IHK) - Informatik (d/m/w) 2027` (Schaeffler).
- Ausbildung: `Ausbildung Elektronikerin / Elektroniker für Automatisierungstechnik (w/m/d) 2027` (Volkswagen).
- Dual + Ausbildung no título: `Dualer Student (B.Sc) Künstliche Intelligenz & Data Science mit Ausbildung Elektroniker (w/m/d)` (B. Braun).
- Schüler: `Längerfristiges Schülerpraktikum im Logistikzentrum (m/w/d)` (Lidl); `Schülerpraktikant im Bereich Technik - Logistik (m/w/d)` (Kaufland).

## 4. Top 20 novo

As 4 áreas-alvo seguem representadas; o topo ficou inalterado (nenhum título do Top 20 antigo saiu):

| # | Score | Vaga | Empresa |
|---|---|---|---|
| 1 | 16.00 | Werkstudent Data Analytics & Logistics (m/w/d) | Knorr-Bremse |
| 2–3 | 13.50 | Pflichtpraktikum / Praktikum Logistik - Data & Analytics | Bosch |
| 4 | 13.50 | Working Student (f/m/d) - Analytics: AI Enablement & Automation | SAP |
| 6 | 12.25 | Werkstudent Supply Chain International - Data & Prototyping (m/w/d) | Lidl |
| 8 | 12.00 | Hochschulpraktikum (w/m/d) im Bereich Prozessoptimierung im Einkauf | B. Braun |
| 18 | 10.75 | Werkstudent (w/m/d) - Solution Advisory / Presales - Fokus auf Supply Chain Management | SAP |

Distribuição de scores: **min 2.0 | mediana 6.25 | max 16.0** (antes: min 1.0 | mediana 6.0 | max 16.0 — o ranking em si não mudou; a distribuição reflete o conjunto menor).

## 5. Determinismo

2 execuções do CLI sobre `data/jobs.json` produziram **saídas idênticas** (md5 `523fa1c7cc90e6e89ddbb91ea23a35a3` em `data/eligible_jobs.json` e na 2ª execução; diff estrutural vazio).

## 6. Observação de verificação (fix desta delegação)

O sanity "Fase1: nenhum ruído de tipo no eligible" de `scripts/test_ranking.py` FALHAVA (FALHA: 1) porque duplicava a regex local em vez de usar a fonte única, e a alternativa `schulpraktik` (sem `\b` inicial) casava DENTRO de "Hochschulpraktikum" — 4 vagas VÁLIDAS da B. Braun que a Fase 1 preservou de propósito (estágio universitário). Corrigido: o sanity agora importa e usa `TYPE_EXCLUSION_PATTERNS` de `internship_finder.filters` (fonte única de verdade) — `any(re.search(p, j["title"], re.IGNORECASE) for p in TYPE_EXCLUSION_PATTERNS)` — e a regex duplicada foi removida. O eligible de 283 tem 0 ruído real de tipo.

## 7. Critérios de aceitação (Fase 1)

- [x] Suíte completa 7/7 com exit 0 (`test_dedup`, `test_fetch`, `test_filters`, `test_find_company`, `test_manifest`, `test_ranking`, `test_resolver`).
- [x] Sanity Fase 1 passando e `Hochschulpraktikum` segue no eligible (sanity dedicado).
- [x] 0 falsos positivos de tipo no eligible (verificação direta: nenhum dual/ausbildung/schüler/FSJ/BFD).
- [x] Pipeline determinístico (2 execuções → saídas idênticas).
- [x] Sem alteração em filtros de área/país, ranking, adapters, pacote `ats-scrapers` (só `filters.py` + testes + doc).

## Próximos passos (sequência autorizada pelo dono)

Fase 2 — Phenom/DHL (country no adapter, genérico) → Fase 3 — Workday (9 empresas zeradas) → relatório final antes/depois + novo parecer antes do SQLite.
