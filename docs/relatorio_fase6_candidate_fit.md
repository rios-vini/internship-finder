# Fase 6 — Candidate Fit + Application Intelligence + Mobile UX

**Data**: 2026-09-20 · **Run de referência p/ medição**: 2026-09-20T09:00:01Z
(474 elegíveis; parcial exit 2 — falhas recorrentes já conhecidas, ver §15) ·
**Comparação "antes"**: snapshot do archive `20260919T090001Z` (476 elegíveis).

**URL pública**: https://rios-vini.github.io/internship-finder/

Objetivo da fase (enunciado do dono): o ranking deve responder também
**"esta vaga é viável para candidatura, é urgente e há obstáculos?"** — SEM
misturar esses conceitos com o score de relevância.

---

## 1. Arquivos alterados/criados

| Arquivo | Tipo | O que traz |
|---|---|---|
| `src/internship_finder/app_intel.py` | **novo** | Camada pura/determinística: `german_level`, `english_evidence`, `work_authorization`, `deadline_kind`/`days_until`/`urgency_color`, `candidate_fit`, `possible_problems`, `quality_flags`, `application_readiness` |
| `src/internship_finder/ranking.py` | alterado | Componente `language` reescrita (EN +1.5 evidência; alemão por EXIGÊNCIA) |
| `src/internship_finder/ptbr.py` | alterado | Rotulos PT-BR (work auth, níveis de alemão, deadlines, fit, problemas, flags, readiness) + explicador da componente language |
| `scripts/interface.py` | alterado | Chips, bloco "sinais de candidatura", "Como este ranking funciona", filtros novos, mobile cards, `--ref-date`/`--db-join` |
| `scripts/ranking_digest.py` | alterado | Critérios ativos com a nova regra de alemão (pesos vivos) |
| `scripts/test_app_intel.py` | **novo** | Suite do app_intel (CI 27→28) |
| `scripts/test_interface.py` | alterado | +11 casos node (filtros novos), `test_fase6_features`, fixture atualizada |
| `scripts/test_ranking.py` | alterado | Expectativa nova do componente language na fixture |
| `.github/workflows/ci.yml` | alterado | Array 28 scripts |

## 2. Alterações no tratamento do idioma (componente `language` do score)

**ANTES**: menção de inglês `+1.5` e menção de alemão `+0.5` (bônus só por
"conter alemão" — até "Deutsche Bahn"/"deutsch" num anúncio pontuava).

**DEPOIS** (pesos novos em `ranking.py`):

| Evidência no TEXTO do anúncio | Peso |
|---|---|
| Inglês mencionado (title+desc) | `+1.5` (inalterado) |
| Alemão **exigido** (required) | `−2.0` (PENALTY_LANG_DE_REQUIRED) |
| Alemão **preferido** (preferred) | `−0.5` (PENALTY_LANG_DE_PREFERRED) |
| Alemão com menção difusa (plus) | `0.0` (neutro) |
| Alemão não mencionado | `0.0` (neutro) |

Nenhum outro peso foi alterado (ver §10). O idioma em que o anúncio foi
escrito **nunca** é requisito: um anúncio em alemão sem exigência declarada
fica neutro; "Deutschland", "Deutsche Bahn", "deutsche Gesellschaft" não são
tokens de idioma.

## 3. Regras de classificação do alemão (app_intel.german_level)

Tokens de menção (word-bounded): `german`, `deutsch`, `deutschkenntnisse`,
`deutschsprachig`, par `deutscher und englischer …`. Para cada menção, janela
±45 chars e ordem de prioridade:

1. **Negação explícita** (`no/not/kein/ohne … required/erforderlich`) → `plus`
   (sem barreira);
2. Palavra branda **grudada** à menção (±25 chars: `plus/preferred/von
   Vorteil/wünschenswert/bevorzugt/nice to have/…`) → `preferred` (ex.:
   "English required, German is a plus" → preferred — a exigência forte é do
   inglês);
3. Verbo de exigência na ordem direta (`German required`, `Deutschkenntnisse
   vorausgesetzt`, `fließend/verhandlungssicher`, `in Wort und Schrift`, nível
   CEFR A1–C2, `deutschsprachiges Team/Umfeld`) → `required`;
4. Qualificador de intensidade direto (`sehr gute/excellente/very good…` +
   `deutsch/kenntnisse/sprache/skills`) → `required`;
5. Par com palavra de idioma depois (`German and English … Language/Skills`) →
   `required`; par sem intensidade → `preferred`;
6. Verbo de exigência na ordem inversa (`We require German`) **só se não há
   palavra branda na janela** → `required`;
7. `basic/Grundkenntnisse` → `preferred`; menção nua → `plus`.

O sinal mais forte entre todas as menções vence (required > preferred > plus).
Resultado medido no run 20/09 (474): **required 183 · preferred 96 · plus 17 ·
sem menção 178**.

## 4. Work authorization (app_intel.work_authorization)

Estados: `support` / `existing_required` / `no_sponsorship` / `unclear` /
`not_mentioned`. Classificação **somente por evidência explícita** no anúncio
(visa sponsorship/relocation → suporte; "must have existing work
authorization", "gültige Arbeits- und Aufenthaltserlaubnis", "EU citizens" →
autorização existente; "no sponsorship"/"cannot sponsor" → sem suporte; vocab
sem classificação → unclear; sem vocab → not_mentioned). Empresa multinacional
ou localização alemã **nunca** geram suporte inferido.

Medido (474): not_mentioned 444 · existing_required 20 · unclear 10 · support 0
· no_sponsorship 0. Na interface: linha `Work authorization — 🟡 Não
mencionado` (emoji por estado) + chip. **Nenhum estado é inventado.**

## 5. Deadline (primeira classe, nunca inventado)

- `application_deadline` **do empregador** → `Deadline: <data> (N dias
  restantes)` com cor de urgência.
- **SuccessFactors** (`successfactors:*`) → o campo vem do feed
  `g:expiration_date` = `collected_at + 30d` (validade do feed da plataforma,
  NÃO prazo de candidatura — verificado 295/295 exatos). Exibido como
  `Validade do anúncio (fonte): <data>` e **excluído** de urgência e de
  "vagas expirando".
- Ausente → `Deadline: Not specified` (nenhuma data artificial; nunca
  `first_seen + N`).

Urgência (só deadline do empregador): 🟢 > 14 dias · 🟡 7–14 · 🟠 3–6 · 🔴 ≤ 2
(inclui vencida).

## 6. "Vagas expirando"

Filtro no painel (deadline confiável): ≤ 2 / ≤ 7 / ≤ 14 dias. Vagas **sem**
deadline confiável (incluindo a validade do feed SF) **não** aparecem como
expirando. Resumo honesto no painel: "0 com deadline confirmado em até 7 dias
(de 0 com deadline do empregador; 474 sem deadline confirmado não entram neste
filtro)" — o snapshot atual **não tem nenhum deadline real de empregador**.

## 7. Candidate Fit (sinais, não número opaco)

Linhas objetivas por vaga (✓/⚠/·): Alemanha, vaga de estudante, inglês
mencionado, alemão (nível), work authorization, localização informada,
descrição disponível. Todos derivados dos dados reais (título/descrição/
campos); nada de compatibilidade inventada.

## 8. Possíveis problemas + Quality flags (só com evidência)

Problemas (→ readiness/precisam revisão): alemão exigido, alemão preferido,
work auth (autorização existente exigida / sem sponsorship / não clara),
deadline ≤ 2 dias (ou vencida), validade SF vencida, título com senioridade
sem marcador de estudante. **Nunca** julgamento de empresa/vaga.

Quality flags (dados): sem deadline, validade de plataforma (SF), localização
ausente, descrição ausente/curta, sem menção a idioma, publicação antiga (>60
dias). `Application readiness`: 🟢 **pronta para revisar** = zero problemas;
🟡 **precisa verificação** = ≥1 (com a ressalva explícita de que não é
garantia de contratação).

## 9. Mobile UX

- `<760px`: tabela vira **card por vaga** (tr block, data-label em cada célula,
  #/score inline, título, empresa, local, tipo, desde, chips, "sinais de
  candidatura ▾", "por que esta vaga? ▾", botão "abrir ↗" em área de toque) —
  sem scroll horizontal.
- Topo compacto: título menor, KPIs em grade 2×2, "Informações da atualização"
  em `<details>`, busca em largura total.
- Filtros em painel recolhível com contador **"Filtros (N)"** dos ativos.

## 10. Como os pesos passaram a ser exibidos

Nova seção **"Como este ranking funciona — pesos e regras reais"** (antes da
lista, alterna por perfil): critérios, penalidades e regras renderizados das
**constantes vivas** de `ranking.py`/`materials_ranking.py` (nenhum número
duplicado no HTML — a seção muda junto com o código). Ex.: área no título
+2,0; skills +0,75/termo; inglês +1,5; tipo +1,0; DE +1,0; Berlin +0,5;
alémão exigido −2,0; alemão preferido −0,5; senioridade −3,0; manager −1,0;
full-time −0,5 (perfil biz); materiais +2,5/termo no título etc. (perfil
Materials). "Por que este score?" continua usando os componentes REAIS do
breakdown (positivos e negativos separados).

## 11. Comparação do ranking antes/depois (mesmas vagas, 448 comuns)

- Componente `language` antes: `{0.0:171, 0.5:13, 1.5:45, 2.0:247}` · depois
  (474): `{−2.0:28, −0.5:156, 0.0:156, 1.0:95, 1.5:39}`.
- 448 vagas comuns aos dois runs: **278 (62%) mudaram de score** (todas para
  baixo, máx −2,5): −2,5 → 148 · −2,0 → 30 · −1,0 → 73 · −0,5 → 27 · 0 → 170.
- 246/448 moveram ≥ 50 posições no ranking; **Top 30: 23 permanecem, 7 saem, 7
  entram** (8 dos 30 antigos saíram por correr com conjunto de 20/09 — 2 vagas
  saíram do eligible por churn diário).

## 12. Exemplos reais afetados

| Vaga | Antes | Depois | Por quê |
|---|---|---|---|
| STIHL — Praktikum Data Analytics / Data Science (#1) | 17,5 (lang +2,0) | **15,0** (lang −0,5) | "Sehr gute Deutsch- und Englischkenntnisse in Wort und Schrift" → alemão exigido (−2,0) com EN (+1,5) |
| Liebherr — Werkstudent Operations Management | 8,0 #148 | **5,5** #264 | Alemão exigido no anúncio (−2,5) |
| teampicnic — Masterarbeit Business Analytics | 13,5 #8 | **13,0** #7 | "Deutsch … von Vorteil" → preferido (−1,0; cai menos) |
| engelhart — Weather Analytics Internship Program | 11,5 #37 | **11,5** #20 | EN-only, alemão não citado → score intacto, sobe (outros caíram) |
| SAP — Working Student Operations Team (Top 30) | 16,8 #2 | saiu do Top 30 | Alemão exigido (run 20/09: fora do eligible id? — saiu junto com 1 vaga-churn) |

## 13. Testes executados

- Suíte local **28/28 — 0 falhas** (nova: `test_app_intel.py`; `test_interface`
  com +11 casos node para os filtros novos e `test_fase6_features` com
  determinismo de página).
- CI GitHub Actions: array 27→28 (script novo) — PR #?. 

## 14. URL do GitHub Pages

https://rios-vini.github.io/internship-finder/ — publicada manualmente nesta
fase (run de 20/09 saiu exit 2 por falhas recorrentes; o gate automático do
cron só publica com exit 0, ver §15). O cron volta a publicar sozinho no
próximo run verde.

## 15. Limitações encontradas

- **Run 20/09 exit 2 (parcial)**: 4/127 fontes falharam — Lidl
  (`successfactors:lidlstiftuP2`, timeout ×17), Kuehne+Nagel (cornerstone,
  ×5), SMA (oracle homônimo, ×4), Siemens Healthineers (avature, ×2 — nova) e
  `smartrecruiters:other` (erro técnico ×4). 474 elegíveis (vs 476) — churn
  normal; página publicada manualmente com o ranking completo do pipeline.
- **Nenhum deadline de empregador no snapshot atual** (0/474): todos os 295
  deadlines são validade de feed SF (+30d) — "vagas expirando" mostra 0 e isso
  é o comportamento correto (nada inventado).
- **Work authorization**: 444/474 sem evidência → "não mencionado" (preferível
  a inventar).
- `german_level` residual: frases EN onde "required" se refere ao inglês e o
  alemão tem outro qualificador a >25 chars podem cair em `required` (a regra
  do "soft grudado" cobre os padrões comuns; documentada).
- Status pessoal (Interessante/Revisar/Aplicada/Ignorar): página estática sem
  backend não tem persistência limpa; **documentado como evolução futura**
  (não usamos localStorage como solução definitiva — enunciado §17).
- Company Intelligence (Fase 7) **não** foi implementada (enunciado §18).

## 16. Commits

- `9e992c3` Fase 6 (parte 1): app_intel + tratamento de idioma + UI candidatura
- (parte 2: documentação — este relatório, README, architecture, MASTER_PLAN,
  PROJECT_STATUS)
- Publicação: `b9d0ee7` deploy(run 2026-09-20T090001Z-fase6-manual-exit2-parcial)