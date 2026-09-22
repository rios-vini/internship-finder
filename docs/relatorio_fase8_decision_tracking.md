# Relatório — Fase 8: Decision Support + Application Tracking + Feedback Loop

Data: 22/09/2026 · Branch: `feature/fase8-decision-tracking` · Base: main `351b2e8`

## 1. Arquivos alterados/criados

**Criados:**
- `scripts/personal_tracker.py` — CLI do estado pessoal (schema + 11 subcomandos).
- `scripts/test_personal_tracker.py` — 30º script da suíte (20 itens do §25).
- `docs/relatorio_fase8_decision_tracking.md` — este relatório.

**Alterados:**
- `scripts/interface.py` — hint do tracker por vaga (dentro do `<details>`
  recolhível) + `data-job-id` na `<tr>` (id canônico). Zero dado pessoal no HTML.
- `scripts/ranking_digest.py` — `personal_sections()` (reminders + aguardando
  resposta; banco ausente/corrompido → `[]`).
- `scripts/refresh_daily.py` — `_sync_personal_ranking()` (sync diário
  best-effort) + montagem das seções pessoais ANTES do link do digest.
- `.github/workflows/ci.yml` — array 29→30 scripts.
- `README.md` — seção "Decision Support + Application Tracking (Fase 8)".
- `docs/architecture.md` — bloco Personal Tracking.
- `PROJECT_STATUS.md` — estado Fase 8.

**Inalterados por design:** `ranking.py`, `filters.py`, `dedup.py`,
`materials_ranking.py`, coleta (`cli.py`/collectors/adapters) — a Fase 8 é
camada de decisão pessoal; NENHUM peso/score/filtro mudou (§12).

## 2. Modelo de status das vagas

`new · interesting · review · applied · interview · offer · rejected ·
withdrawn · ignored` — fluxo sugerido da spec
(`new → interesting/review → applied → interview → offer/rejected`) com
saídas diretas para `ignored`/`withdrawn`. Tabela `job_status` (PK
`job_id`): status, priority (`high/normal/low`), next_action (texto livre),
effort (`low/medium/high`) + effort_flags (`cv_adaptation;cover_letter;
complex_portal;referral`), note, updated_at, first_marked_at (imutável).

## 3. Modelo de persistência

SQLite `data/personal/jobs_personal.db` (stdlib `sqlite3`), 3 tabelas:
- `job_status` (PK job_id) — estado atual por vaga;
- `job_events` (PK job_id+ts+kind) — histórico append-only: `marked`,
  `status_changed`, `priority`, `note`, `applied_at`, `interview_at`,
  `response_at`, `contact`, `removed_from_ranking`, `ats_gone`,
  `feedback_liked`, `feedback_ignored`;
- `job_applications` (PK job_id) — applied_at (NOT NULL), status,
  response_at, interview_at, contact.

Escolha (§2 da spec): o projeto JÁ usa SQLite (`data/jobs.db`,
`sqlite_store.py`, backup API no refresh — passo 2b). O banco pessoal é um
segundo banco no mesmo padrão, em `data/personal/` — `data/` é gitignored,
logo o estado pessoal fica no lado privado do VPS e não no repositório.
Nenhuma arquitetura distribuída, nenhum servidor: um CLI + o cron existente.

## 4. Privacidade (como foi garantida)

1. `data/` é gitignored → `jobs_personal.db` nunca é commitado (verificado:
   `git status --porcelain` limpo após uso do tracker).
2. O publicador do Pages empurra APENAS `index.html`; o gate
   `check_public_safe` bloqueia o push se o HTML contiver tokens/caminhos
   privados (`jobs.db`, `.env`, `/home/ubuntu`, TELEGRAM_*).
3. `interface.py` não recebe NENHUM dado pessoal: o hint mostra apenas o
   comando do tracker com o id público da vaga. Teste dedicado grepa o HTML
   por status/notas/banco e confirma ausência (§20).
4. Telegram: `personal_sections` envia apenas contagens + nome
   empresa—título de vagas em reminder; notas completas NUNCA (teste).
5. Export CSV escreve só em `data/personal/` (local privado).

## 5. Funcionamento da shortlist

`list --shortlist` mostra as vagas com status interesting/review/applied/
interview/offer + contagem por status (o exemplo do §6). `--status` filtra
qualquer subconjunto. Números pessoais ficam no banco local (nunca no Pages).

## 6. Application tracking

`applied <id> --date --response --interview --contact` grava em
`job_applications` (+eventos). Marcar `--status applied` sem `applied`
registra candidatura implícita com a data de hoje. `show <id>` lista tudo
+ histórico. Não é CRM — datas mínimas e contato, como a spec pede.

## 7. Funcionamento da comparação

REUSO da Fase 7: o Compare opportunities existente já mostra os fatores
Candidate Fit/Job/Company/Location pedidos no §5 (score, idioma, work
authorization, deadline, vaga/salário/duração, benefícios, carreira,
Internship→Full-time, cidade, custo de vida, transporte) sem vencedor
automático. A Fase 8 NÃO duplica essa interface; apenas garante que ela
continua presente (teste de regressão) e o hint/dados canônicos por vaga.

## 8. Funcionamento dos lembretes

- `reminder_jobs()`: shortlist com deadline EMPLOYER ≤ 3 dias
  (`app_intel.deadline_kind == "employer"`; validade de feed
  SuccessFactors NUNCA — regra da Fase 6). Ordena por dias; mostra
  "hoje/amanha/em N dias".
- Telegram: seções `⚠️ Application reminders` (até 3 nomes + contagem) e
  `📌 N aplicações aguardando resposta` (applied sem response/interview).
  Entram ANTES do link (link continua última linha). Gate exit 0 (mesmo
  gate do digest). Se estourar 4096, o compactador existente preserva a
  base + link (seções pessoais somem no compact — limitação documentada).


## 9. Histórico implementado

`job_events` (append-only) responde: quando a vaga foi encontrada
(`first_seen` do jobs.db via metrics), quando foi marcada (`marked`),
quando mudou de status (`status_changed <old> -> <new>`), quando foi
aplicada (`applied_at`), quando saiu do ranking (`removed_from_ranking`) e
quando desapareceu do ATS (`ats_gone` — active=0 no jobs.db da coleta).
`sync-ranking` roda diariamente no refresh e é idempotente (no máximo um
evento de cada tipo por vaga — testado). "Quando entrou no Top 30" fica
implícito pela combinação ranking-diário + status (sem sistema de eventos
complexo, como a spec manda).

## 10. Feedback implementado

`feedback <id> --liked|--ignored [--reasons "a;b;c"]` — motivos LIVRES (os
do §11 são sugestões documentadas no help, não enum fechado). Eventos
`feedback_liked`/`feedback_ignored`. `ranking-feedback` mostra Top 30 vs
Outside com as contagens de status (§13). **§12 garantido por
construção**: nenhuma função de ranking/filtros é chamada pelo tracker; o
score é computado ANTES e independente. Testes confirmam: data-scores do
HTML idênticos antes/depois (test_personal_tracker, bloco 13/20) e
`ranking.py` intocado no diff.

## 11. Métricas disponíveis

`metrics`: contagens por status, taxa applied/(interesting+review), tempo
médio descoberta→candidatura (join com `first_seen` do jobs.db),
distribuição por empresa (marcadas no ranking atual), total. `funnel`:
Eligible → Top 30 → marcadas no Top 30 → Interesting → Applied → Interview
→ Offer (§15). Todas descritivas — nenhuma previsão, nenhuma acurácia.

## 12. Exportação

`export --csv data/personal/shortlist.csv` — header: title, company,
location, score, profile, status, application_date, deadline,
personal_priority (+ job_id, note para uso local). Vaga fora do ranking
atual: título/company = "No longer active" (§19 — não some). CSV só em
caminho local; nunca publicado.

## 13. Testes executados

Suíte COMPLETA local, cwd scratch (`/tmp/suite_full`), venv compartilhada
`PYTHONPATH=/tmp/if-fase8/src`:
**30/30 scripts — TUDO OK — 1.564 checks [OK], 0 [FAIL]** (número oficial
permanece o do CI; o bloco node do test_interface SKIPA sem node, como no
CI ubuntu ele roda).

`test_personal_tracker.py` cobre os 20 itens do §25: (1) interesting,
(2) review, (3) applied, (4) application date, (5) nota, (6) prioridade,
(7) interview, (8) offer, (9) rejected, (10) vaga some do ATS (ats_gone,
status preservado), (11) vaga aplicada some do ranking
(removed_from_ranking), (12) shortlist, (13) comparação (Compare Fase 7
presente no HTML), (14) deadline reminder (employer ≤ 3 dias), (15)
Telegram (personal_sections com banco/sem banco/corrompido; notas não
vazam; shortlist vazia → sem reminders), (16) exportação (campos §23),
(17) mobile/desktop (hint em `<details>`), (18) desktop (mesmo HTML),
(19) persistência após refresh (sync idempotente; banco reaberto mantém
estado), (20) privacidade (HTML sem dados pessoais; .gitignore cobre
data/; banco não mencionado no HTML). Fluxos reais executados: smoke
completo interesting→review→applied→interview→offer + feedback + sync +
funnel + metrics + export (saídas no corpo do relatório de commit).

## 14. Exemplos reais do fluxo

```
$ personal_tracker.py mark "BMW AG|successfactors:jobs:123" --status interesting --priority high --note "contato procurement analytics"
[OK] BMW AG|successfactors:jobs:123 -> status=interesting priority=high note='contato procurement analytics'

$ personal_tracker.py applied "BMW AG|successfactors:jobs:123" --date 2026-09-22 --contact LinkedIn
[OK] candidatura registrada: BMW AG|successfactors:jobs:123 applied_at=2026-09-22

$ personal_tracker.py sync-ranking   (vaga removida do ranking no dia seguinte)
[OK] sync-ranking: 1 marcadas; +1 removed_from_ranking; +0 ats_gone (idempotente — status/historico preservados)

$ show "BMW AG|successfactors:jobs:123"
status: offer  prioridade: high ... candidatura: applied_at=2026-09-22  contato: LinkedIn
historico: marked interesting · status_changed interesting -> review · applied_at 2026-09-22 · feedback_liked area;empresa · removed_from_ranking
```

## 15. Confirmação: o ranking NÃO aprende/altera pesos

- `ranking.py`/`filters.py`/`materials_ranking.py` fora do diff.
- Nenhum caminho de código liga job_status/job_events ao score.
- `ranking-feedback`/`metrics` são leitura pura.
- Teste: HTML data-score idêntico pré/pós-mudança de interface.
Qualquer mudança de peso continua sendo decisão explícita do dono.

## 16. Confirmação: dados pessoais não são publicados

- `git status --porcelain` não mostra `data/` (gitignored).
- `publish_pages` empurra só `index.html` (branch gh-pages).
- Teste de privacidade grepa o HTML por status/notas/banco: ausente.
- `check_public_safe` continua verde (test_publish_pages TUDO OK).
- Telegram recebe apenas contagens + empresa—título (sem notas).

## 17. URL do GitHub Pages

https://rios-vini.github.io/internship-finder/ — a página pública ganhou o
hint por vaga (recolhível, sem poluição da tabela; mobile: dentro do card).
O deploy automático diário (cron 06:00 BRT) publica o HTML novo quando o
PR for mergeado (o run usa o checkout principal).

## 18. Limitações

1. **GitHub Pages é estático/público** (§2/§21 da spec): não há como
   persistir status/notas no browser com privacidade — o estado pessoal
   mora no CLI + banco local do VPS (solução local/private com limitação
   documentada, exatamente como a spec autoriza). Ações pessoais são
   comandos, não cliques na página.
2. **Seções pessoais somem no compact 4096**: se o digest + seções pessoais
   estourarem o limite do Telegram, o compactador preserva a base + link e
   descarta as seções (não o contrário).
3. **Deadline employer é minoria**: a maioria das vagas tem validade de
   feed SF (não prazo real) ou nenhum deadline — os reminders cobrem só
   vagas com prazo do empregador (regra Fase 6, sem exceção).
4. **`ranking-feedback`/`funnel` com poucos dados**: as primeiras leituras
   são triviais; a utilidade cresce com o uso real. Nenhuma acurácia é
   calculada (§13 da spec).
5. **`sync-ranking` depende do run exit 0**: em run parcial o sync pula
   (mesmo gate do digest) para não gerar falsos `removed_from_ranking`.
6. **"Quando entrou no Top 30"** não é evento dedicado (implícito nos
   rankings diários arquivados) — deliberado (§10: sem sistema de eventos
   complexo).

## 19. Commits

- `scripts/personal_tracker.py` + `scripts/test_personal_tracker.py` +
  patches de integração (interface/ranking_digest/refresh_daily/ci.yml) +
  docs — branch `feature/fase8-decision-tracking`, PR aberto via REST
  (merge só com CI verde + autorização do dono, regra permanente).

## "O que deliberadamente NÃO implementei"

- **Aplicação automática/semiautomática** — anti-enunciado (o sistema
  marca, o usuário aplica).
- **Interface web de status no Pages** — impossível com privacidade em
  site estático público (limitação documentada; hint CLI no lugar).
- **Aprendizado de pesos/feedback loop** — §12: feedback é collect-only.
- **CRM completo** (pipeline stages custom, anexos, e-mails) — §7 pede o
  mínimo.
- **Notificações push por vaga** (só o digest diário existente ganhou as
  seções).
- **Importação de candidaturas externas** (aplicado fora do sistema) —
  seria novo dado de entrada sem fonte confiável.
- **Histórico de posição no ranking por dia** (série temporal completa) —
  o archive diário já guarda os rankings; um índice dedicado é
  complexidade extra.
- **Edit/delete de eventos** — append-only por design (§10).
- **Comparação >4 vagas** — mantido o máximo da Fase 7 (4 colunas
  legíveis).
- **Deadline de validade SF como prazo** — nunca (regra Fase 6).
