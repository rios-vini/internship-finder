# MASTER_PLAN — Internship Finder (fonte de verdade única)

**Versão:** 2026-08-31 · **Status:** unificado a partir de (1) roadmap original Hermes,
(2) auditoria OpenHands (ACH-01..21), (3) consolidações das sessões 27–30/08,
(4) **verificação direta no código/git em 31/08**. Nenhum item entra aqui por memória:
tudo foi conferido em `git log`, `git status`, grep no `src/` ou nos docs.

> Regra de leitura: ✅ = verificado feito · ⏳ = pendente · 🔒 = bloqueado por decisão
> do dono · ❌ = descartado com motivo. Fonte da verdade de execução: este arquivo +
> `PROJECT_STATUS.md` (estado medido) + PRs abertos. `docs/roadmap.md` está obsoleto
> (época do MVP) e não deve ser usado como plano — reescrever quando a doc for tocada.

---

## 1. Estado verificado em 2026-08-31

### Main público (GitHub)
- `main` = `da81475` (31/08): **PR #8 mergeado** ✅ (`9690c47`). main tem P0
  deadline + hardening ACH-01..09 + fix metrics + MASTER_PLAN + SQLite desbloqueado.

### Baseline de coleta (31/08, nesta instância)
- Coleta completa re-executada (39 empresas, `--timeout 60`): **37.373 brutas →
  236 eligible/ranked (todos `country_iso='de'`)** → `data/jobs.json`,
  `data/eligible_jobs.json/csv`. Baseline antigo (12/08) era 56.810→293: o
  **mercado mudou** (menos vagas), não é regressão.
- **Workday no eligible: 0** — confirma com dados reais a pendência P0.1
  (tenants Workday alemães seguem sem `country_iso`).
- **Achado novo**: `scripts/test_ranking.py` tem sanity checks **acoplados a um
  snapshot de dados (12/08)** — buscam vagas que já não existem no dataset atual
  (ex.: "Logistik und Supply Chain Design", "SAP Analytics Cloud"). `ranking.py`
  não mudou desde o MVP (`3307ec5`); o teste quebra por dados, não por código.
  → Nova pendência (P2): desacoplar `test_ranking.py` de vagas específicas
  (fixture fixa ou sanity por invariante de regra, não por presença de vaga).

### Painel do PR #8 (histórico — mergeado, manter como registro)
| Commit | Data | Conteúdo |
|---|---|---|
| `7d3c3dd` | 23/08 | P0 Application Deadline: `Job.application_deadline` (datetime\|None, nunca inferido de `posted_at`), adapter, CSV, JSON, teste; pin upstream `ae0ad53` |
| `63fb21b` | 24/08 | Hardening ACH-01..09: dedup por tenant, ids sem URL, métricas JSONL, coverage via `eligible_jobs.json`, exit code 2 p/ falha parcial |
| `dfcf415` | 31/08 | Review PR #8: `status="not_found"` + `duration` float no JSONL (eram `status=""` e string `"0.4s"`) — testes 15a–16g |

### Pipeline (validado end-to-end, parecer A)
```
56.810 brutas → 3.428 estudante → 777 área → 309 DE → dedup −16 → 293 eligible/ranked
```
- 293/293 `country_iso='de'` · scores min 2.00 / mediana 6.00 / max 16.00 · md5 do
  eligible idêntico em re-execução (determinístico) · Top 20 = 13A/5B/1C/1D.
- Baseline oficial: **293** (não 389 — 389 é pré-correções F1–F3; README desatualizado).
- 39 empresas na coleta · 20 com vagas eligible · ATS: successfactors 78%, smartrecruiters,
  eightfold, cornerstone, phenom, greenhouse; workday 0 eligible (limitação documentada).

### Limitações externas conhecidas (não são bugs internos)
- Workday: API não expõe país confiável p/ vários tenants → vagas DE sem `country_iso`.
- Hager / Boehringer / Lanxess (SuccessFactors XML malformado) / Symrise (join.com 422).
- 7 títulos de graduação na cauda (SmvP Schaeffler, Bachelor BASF) — fora dos padrões
  aprovados F1; candidatos a extensão futura, não regressão.

---

## 2. Ranking oficial (ordem de execução)

### 🔴 P0 — desbloqueio e valor
| # | Item | Status | Notas |
|---|---|---|---|
| 1 | **Merge do PR #8** (`7d3c3dd`+`63fb21b`+`dfcf415` → main) | ✅ mergeado 31/08 (main 9690c47) | P0 deadline + hardening liberados; main atualizado. |
| 2 | **Workday Country/Location Resolver** (P0.1 original) | ✅ **implementado 01/09** (PR #9, main 35a215a) — `geocoding.py` cache-first + flag `INTERNSHIP_FINDER_GEOCODING` (OFF), integração no adapter (fallback pós-`infer_country_iso`), testes novos; **9 vagas Workday DE recuperadas no eligible (baseline 0)** — medição reproduzida pelo orquestrador. |

### 🟠 P1 — fundação operacional (nesta ordem)
| # | Item | Status | Notas |
|---|---|---|---|
| 3 | **CI — GitHub Actions** | ✅ **implementado 01/09** (PR #11, main 7b88f76) — `.github/workflows/ci.yml`: push (main, feature/*) + pull_request; runner limpo Python 3.12; pin `ae0ad53` instalado do tarball oficial do GitHub (`archive/ae0ad53.tar.gz`, pois o commit só existe como `refs/pull/268/head`) com verificação do expose de `application_deadline`; `test_dedup`/`test_ranking` ganharam skip do bloco real quando `data/` ausente (runner não tem dados); run real verde no PR (7/7 TUDO OK). |
| 4 | **Regenerar baseline de coleta** nesta instância | ✅ coleta 31/08 (37.373 brutas → 236 eligible; fallhas parciais documentadas: Lidl timeout etc.) | `data/` populado; base p/ medir. P0.1 usou (baseline 0 Workday) e P3 #18 validou. |
| 5 | **Persistência SQLite** + `first_seen`/`last_seen`/`active`/`archived` | 🔓 **DESBLOQUEADO 31/08** (decisão do dono; era ON HOLD desde 13/08) | `sqlite3` basta; sem Postgres/Redis/ORM. Pré-requisito do histórico; o parecer A já autorizava. Campo `application_deadline` entra no schema junto com first/last_seen. |
| 6 | **Observabilidade de consumo** (health por tenant/ATS sobre o JSONL já existente) | ✅ **implementado 01/09** (PR #12) — `src/internship_finder/health.py` + flag `--health [PATH]` (default `data/collection_metrics.jsonl`): relatório JSON por source/ATS (status, collected, duration, médias ok) + alertas de queda brusca (gate ≥3 runs ok, <50% da mediana) e erro recorrente (≥2 consecutivos); `duration` antiga string `"1.0s"` normalizada; malformados não derrubam. SQLite não é fonte (guarda vagas, não métricas de execução — decisão informada). Testes `scripts/test_health.py` (bloco real com SKIP sem `data/`, padrão CI). 1ª medição real: 1 alerta factual — `smartrecruiters:other`, 22/22 runs `error`. |
| 7 | **Structured error codes** | ✅ **implementado 01/09** (PR #13) — `src/internship_finder/errors.py` (+ `CollectionError`, classificador lazy com fallback `UNKNOWN`): payload da `mp.Queue` deixa de ser texto livre e vira `("-error", code, detail)` com estágios fetch/normalize separados; `summary` timeout/failed com `(source, code, erro)`; registro JSONL ganha `error_code` (kwarg keyword-only; `error` legível preservado; JSONL antigo continua válido). Testes `scripts/test_errors.py` (no CI). |
| 8 | **Multiprocessing lifecycle** (ACH-07) | ✅ **implementado 02/09** (PR #14, main 006f210) — `fetch_with_timeout` com 4 desfechos observáveis (timeout / worker-morto / erro estruturado / sucesso), sem status novo (6 do summary preservados); worker morto (`os._exit`/segfault/kill — o `except` não captura) detectado via `exitcode`/`is_alive` ANTES do deadline e distinto de timeout (`CollectionError(UNKNOWN, "worker morreu (exitcode N) sem mensagem")` vs `TIMEOUT`); cleanup em TODOS os caminhos no `finally` — `terminate()` → `join(5)` → se vivo `kill()` → `join(2)` (`_shutdown`) + queue drenada (`get_nowait` até `Empty`) e fechada (`close()`/`join_thread()`); margem parametrizável (`margin=`, default `TIMEOUT_MARGIN=25` — produção inalterada); payload `("-error", code, detail)` e códigos do P1 #7 herdados. `scripts/test_lifecycle.py` standalone (subprocesso real, sem rede/data): timeout ~1s, worker morto ~0.2s (deadline 35s), erro 0.05s, sucesso, loop de 5 sem órfãos (`pid_alive` + `active_children`) — no CI. |
| 9 | **Documentação operacional** | ⏳ | PROJECT_STATUS (P0 feito, SQLite desbloqueado), README 389→293, `docs/roadmap.md` (reescrever), `docs/architecture.md` (`is_internship()` → `is_student_role()`), relatórios antigos = histórico. |

### 🟡 P2 — qualidade e automação (após acumular histórico)
| # | Item | Status | Notas |
|---|---|---|---|
| 10 | **Zero-return + anomaly detection** | ⏳ gate: ≥5 execuções persistidas | Sem histórico estatístico hoje; rebaixado de P1. |
| 11 | **Job validation forte** | ⏳ | title/url/country_iso sem `""`/`"   "`; ausência ≠ dado falso. |
| 12 | **Country/domain module** | ⏳ | centralizar codes/aliases/inferência (hoje espalhado em filters.py). |
| 13 | **Company Registry operacional** + tirar empresas da lógica do CLI | ⏳ | company/ATS/tenant/enabled/status/última coleta; execução vira "run collection". |
| 14 | **Dedup 2.0 textual** | 🟡 parcial | fingerprint (company+title+location normalizados+desc), normalização multilíngue (Praktikum≈Internship≈Werkstudent). |
| 15 | **Padronizar `--country de/europe/all`** (ACH-11) | ⏳ | CLI já aceita; padronizar enrichment sem alterar filtro. |
| 16 | **Desacoplar `test_ranking.py` do snapshot de dados** | ⏳ | Achado 31/08: sanity checks buscam vagas do baseline 12/08 que não existem mais (dataset atual 236 eligible). Fixture fixa ou invariantes de regra (não presença de vaga). |
| 17 | **Daily refresh + alertas** (Telegram?) | ⏳ | Depois do health check; detecção primeiro, notificação depois. |

### 🟢 P3 — manutenção / escala (baixa urgência)
| # | Item | Status | Notas |
|---|---|---|---|
| 18 | **Sincronizar venv com o pyproject (pin ats-scrapers)** | ✅ **RESOLVIDO 01/09** — venv reinstalado do pin `ae0ad53` (via `refs/pull/268/head`: o upstream NUNCA mergeou o PR #268 — o commit só existe como ref de PR, por isso `git clone` simples + checkout falha; usar `git fetch origin refs/pull/268/head`). Validação real: SAP 1086/1086 com `application_deadline` (antes 0/37.373); eligible 84/84 com deadline; suíte verde (deadline/filters/hardening). ⚠️ risco recorrente: instalação fresca volta ao 0.2.0 PyPI sem expose — `uv.lock`/lockfile resolve (#19). |
| 19 | Trocar pin git `ae0ad53` → release PyPI do ats-scrapers quando existir | ⏳ | Depois de resolver o #18; monitorar release com PR #268. |
| 20 | Validação `--timeout`/`--limit` (ACH-14) · `remote` preenchido vs campo (ACH-16) · `country` vs `country_iso` (ACH-17) · CSV completo decisão JSON=completo/CSV=tabular (ACH-18) · parsing datas DD.MM.YYYY se medir necessidade (ACH-20) · `EUROPE_COUNTRIES`/BY documentar (ACH-19) | ⏳ | Itens pequenos; "medir antes de corrigir". |
| 21 | Código morto (ACH-13) | ⏳ | Só após referências zero; limpeza independente. |
| 22 | Separar código/dados (repo de dados) · Parquet quando volume justificar · chunking p/ frontend | ⏳ | Não por moda; quando o dado crescer. |
| 23 | Expansão internacional (NL/CH/AT → BE/FR/nórdicos/UK) + mais empresas DE (39→60→100) | ⏳ | Depois de estabilizar qualidade; ATS novo só se relevante p/ cobertura. |
| 24 | Agregadores (LinkedIn/Indeed/Glassdoor) | ⏳ | Depois de persistência + dedup maduro (identidade cross-source é complexa). |
| 25 | Interface simples (top vagas, filtros, link) | ⏳ | Sem frontend sofisticado; dashboard/lista basta. |

### 🔵 P4 — inteligência (só com dados históricos reais)
| # | Item | Status | Notas |
|---|---|---|---|
| 26 | Embeddings / semantic dedup | ⏳ | Só depois do dedup textual provar insuficiente com dados reais. |
| 27 | Feedback do usuário (viu/ignorou/gostou/aplicou) → ranking adaptativo | ⏳ | Estatística simples antes de qualquer RL. |
| 28 | LLM enrichment pós-determinístico | ⏳ | Nunca decide validade da vaga; extrai características. |
| 29 | Análise de mercado / tendências / forecasting | ⏳ | P5; exige meses de histórico; estatística simples antes de LSTM. |

### ❌ Descartado (ratificado, com motivo)
| Item | Motivo |
|---|---|
| `remote` None→False | None = desconhecido, não = não-remoto. |
| Patterns → YAML/JSON | Regras de filtro são lógica de domínio, não config. |
| `lru_cache` no ranking | Sem gargalo medido. |
| Retry/backoff próprio | ats-scrapers já tem; observar/coordenar, não duplicar. |
| ETag/Last-Modified | Só se bandwidth/tempo virar problema real. |
| Self-healing LLM scraper | Extração determinística + erros observáveis; LLM não adivinha parser. |
| Behavioral mimicry | Não virar bot de browser. |
| Knowledge Graph / Neo4j | Não resolve problema atual. |
| Reinforcement Learning | Feedback simples vem antes; overkill. |

---

## 3. Decisões de engenharia ratificadas (não reabrir sem evidência)
- Arquitetura ATS→adapter→Job→filters→dedup→ranking **não desmontar** (filtros/ranking
  não dependem de campos de ATS específicos).
- Ranking **heurístico, determinístico, sem ML**, com score_breakdown auditável.
- Inferência de país **segura por construção**: nome explícito ou token em posição
  confiável; nunca fabricar; Workday sem país = `None` documentado.
- **Dados não versionados** (`data/` no .gitignore): números são documentados em
  relatórios; dados são artefato local de coleta. (Reabrir só por decisão do dono.)
- `application_deadline` **nunca** inferido de `posted_at`; `None` quando ausente.
- **Persistência autorizada** (decisão dono 31/08): SQLite via `sqlite3` stdlib,
  sem ORM/Postgres/Redis; schema mínimo (Job canônico + first_seen/last_seen/active).

## 4. Como este documento é mantido
- Proposta de mudança de prioridade/item → registro com data + verificação no código
  (nunca por memória de sessão).
- Tarefas saem daqui direto para o fluxo: **cronograma → prompt-builder → OpenHands →
  conferir → git** (skill `openhands-orchestration`).
- Itens P1+ exigem critério de "pronto" verificável antes de delegar.

## 5. Log de mudanças
- **2026-09-02 (P1 #8)**: **Multiprocessing lifecycle implementado** (PR #14, main
  `006f210`, run verde `33597994938`) — `fetch_with_timeout` reestruturado em
  `_wait_worker` (poll `get(0.2)` + monitoramento `exitcode`/`is_alive` a cada
  iteração) + `_shutdown` (cleanup completo no `finally`): worker morto sem
  mensagem (`os._exit`/segfault/kill) detectado ANTES do deadline e distinguido
  de timeout (`CollectionError(UNKNOWN, "worker morreu (exitcode N) sem
  mensagem")`); terminate→join(5)→kill→join(2); queue drenada + close/join_thread
  em todos os desfechos; `margin=` parametrizável (default `TIMEOUT_MARGIN=25`,
  produção inalterada); 6 status do summary e payload `("-error", code, detail)`
  do P1 #7 preservados. `scripts/test_lifecycle.py` (standalone, subprocesso real,
  sem rede/data) — 5 cenários: timeout ~1.01s, worker morto ~0.20s (deadline 35s),
  erro 0.05s, sucesso, loop de 5 sem órfãos; 1 linha no array do CI. Delegado via
  OpenHands retomado 2× (janela LLM ruim — exit 0 sem relatório na 1ª, resume
  completou). [#8 ✅]
- **2026-09-01 (P1 #7)**: **Structured error codes implementados** (PR #13) —
  `errors.py` (5 códigos + classificador lazy + `CollectionError`); payload da
  queue estruturado `("-error", code, detail)`; estágios fetch/normalize separados
  no worker; `error_code` no registro JSONL (keyword-only, `error` preservado).
  Delegado 01/09 com retomada via `openhands --resume` (parada prematura do agente
  na 1ª janela — código parcial sem quebra; resume completou testes + CI). [#7 ✅]
- **2026-09-01 (P1 #6)**: **Observabilidade implementada** (PR #12) — `health.py` +
  flag `--health` (relatório JSON por tenant/ATS + alertas de queda brusca com gate
  e erro recorrente); `test_health.py` no padrão standalone com SKIP sem `data/`
  (entrou no array do CI); 1ª medição real: `smartrecruiters:other` 22/22 `error`.
  Decisão informada: SQLite não é fonte (guarda vagas, não métricas do run). [#6 ✅]
- **2026-09-01 (P1 #3)**: **CI implementado** (PR #11, main `7b88f76`, run verde
  `33502983892`) — workflow GitHub Actions com suíte standalone em runner limpo;
  decisões: tarball `ae0ad53` (pin que só existe como ref de PR) + skip do bloco
  real nos testes quando `data/` ausente; validação local reproduzida em venv
  temporário (expose de `application_deadline` confirmado). [#3 ✅]
- **2026-08-31 (3ª edição)**: **baseline de coleta gerado** nesta instância —
  37.373 brutas → 236 eligible (todos `de`), Workday 0 confirmado com dados reais.
  Achado: `test_ranking.py` acoplado a snapshot → nova pendência P2 #16.
  `PROJECT_STATUS` desbloqueio SQLite refletido; main = da81475.
- **2026-08-31 (2ª edição)**: **PR #8 mergeado** no main (9690c47, dono autorizou) —
  main agora tem P0 deadline + hardening + fix metrics + MASTER_PLAN. **SQLite
  desbloqueado** (era ON HOLD desde 13/08): item sobe para P1 #5, na frente da
  observabilidade (que passa a poder consumi-lo); `application_deadline` entra no
  schema junto com first/last_seen.
- **2026-08-31**: consolidação única criada a partir de 3 fontes concorrentes
  (roadmap original, auditoria ACH, consolidações de sessão) + verificação no código.
  P0 deadline e ACH-01..09 marcados como feitos na branch do PR #8; fix `dfcf415`
  registrado; ACH-10 (SAP Analytics Cloud) **removido** do backlog (implementado);
  P0.1 Workday confirmado como **nunca implementado**; CI subido a P1; anomalia/
  zero-return com gate de histórico; baseline de coleta adicionado.