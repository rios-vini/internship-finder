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
| 9 | **Documentação operacional** | ✅ **implementado 02/09** (PR #15, main f55dc95, run verde) — README atualizado para o estado real (funil 37.373→236 eligible, cobertura 19 empresas/14 tenants, flags `--metrics`/`--sqlite`/`--health`, modelo com `application_deadline`, módulos novos, nota `data/` gitignored + exemplo de validação em `/tmp/`); PROJECT_STATUS → 02/09 (entregas P0..P1/P3 #18, próximas P2, limitações reais); `docs/roadmap.md` → histórico apontando MASTER_PLAN; `docs/architecture.md` → `is_student_role()` + pipeline filtros→dedup→ranking + módulos novos; 8 relatórios antigos marcados como histórico (conteúdo preservado). Números copiados da saída real de `scripts/coverage.py`. |

### 🟡 P2 — qualidade e automação (após acumular histórico)
| # | Item | Status | Notas |
|---|---|---|---|
| 10 | **Zero-return + anomaly detection** | ✅ **implementado 05/09** | Gate histórico por source (espelha o drop); 3º tipo de alerta no health: `zero_return` (último run `empty` após ≥3 ok>0). Ver Log de mudanças 05/09. |
| 11 | **Job validation forte** | ✅ **mergeado 03/09** (PR #16, main 88a9936) — validators pydantic no `Job` (title/url vazios = erro de validação; opcionais vazio→None), `normalize_job_dict` no caminho filtro (4 títulos de borda limpos, baseline 236 ids intacto), adapter com título ausente → `NORMALIZATION_ERROR` (defensivo, 0 ocorrências), `test_validation.py` no CI (run 33695286158 verde). |
| 12 | **Country/domain module** | ✅ **mergeado 03/09** (PR #17, main 7a4e6c9) — `countries.py` extrai país/localização de `filters.py` (COUNTRY_CODES, EUROPE_COUNTRIES, COUNTRY_NAMES, `_country_name_from_location`, `_iso_token_from_location`, `infer_country_iso`, `is_remote`, `parse_country_spec`, `matches_country` — movidos verbatim), `filters.py` re-exporta (consumidores intactos: ranking/cli/adapters/geocoding), `test_countries.py` no CI (run 33706802355 verde); baseline 236 preservado. |
| 13 | **Company Registry operacional** + tirar empresas da lógica do CLI | ✅ **mergeado 04/09** (PR #20, main `e7604db`, run `33840628495` verde) — `src/internship_finder/registry.py` com `SEED` das 39 empresas (fonte única em código: nome canônico de coleta + ATS/tenant de referência + `enabled`), `CompanyRegistry` + `company_status` (estado por empresa **derivado do JSONL de métricas**, read-only — registro malformado nunca derruba) e ponte `registry_names` para o CLI; flag `--registry` (coleta usa as ENABLED do registry; com `--companies` restringe a subconjunto, na ordem informada; modo `--companies` puro continua funcionando) — decisão de design: **registry = configuração, status = JSONL** (sem duplicar estado). `test_registry.py` offline/determinístico (seed, enabled, subconjunto, ponte CLI, company_status via tempfile — sem rede/data); **adicionado ao CI** (13 scripts). Docs: README subseção "Registry de empresas" + PROJECT_STATUS + este log (04/09). |
| 14 | **Dedup 2.0 textual** | ✅ **mergeado 03/09** (PR #19, main `4ed28d8`) — medição real no dataset (03/09): 12 pares candidatos EN/DE, 4 da MESMA vaga com marcadores diferentes escapavam (Knorr `Praktikant`≈`Working Student` Purchasing Controlling, SAP `Intern`≈`Working Student` Bid Council, VW `Praktikum`≈`Werkstudentin/Werkstudent` Analytics After Sales, MAHLE `Internship`≈`Praktikum` Lead-Buying — conteúdo 1:1); `TYPE_EQUIVALENCES` estendida com regex de fronteira de palavra (`praktikums?`/`praktikanten?`/`interns?`/`internships?` → working student) + colapso de repetidas na bag (`Werkstudentin / Werkstudent`); `Pflichtpraktikum` NÃO é atingido (obrigatório ≠ voluntário, anti-teste), trainee fora do domínio; description NÃO entrou no fingerprint (0 pares exigiram — ruído/falso positivo); `test_dedup` +casos reais medidos e anti-casos; `test_countries` desacoplado do número mágico `236` (invariante subconjunto + observabilidade do delta, autorizado pelo dono — precedente #16); baseline 236→232 (4 duplicatas TRUE por company+title+location), suíte local 16/16, CI run `33799148404` verde. |
| 15 | **Padronizar `--country de/europe/all`** (ACH-11) | ✅ **implementado 05/09** — `parse_country_spec` agora VALIDA a spec (token não-ISO ou spec vazia → `ValueError` claro; `all` canônico, `world`/`any` mantidos por compat), e o CLI valida cedo (`parser.error`, exit 2). Antes: `--country xx` → 0 vagas silencioso e `de,xx` ignorava o token inválido; agora erro claro. Filtro INALTERADO p/ specs válidas (baseline `--country de` → 232 ids idênticos lista-a-lista; `europe` 371 / `all` 31006 / `remote` 1 idênticos). `test_countries` +21 checks. |
| 16 | **Desacoplar `test_ranking.py` do snapshot de dados** | ✅ **mergeado 03/09** (PR #18, main b82ff8e) — `FIXTURE` fixa (18 jobs sintéticos) + `test_fixture_ranking()` (regras no nível do rank: topo de área-alvo, sem senior/head/director, A-grade por área no TOP N, presales SCM com area≥6 sem penalidade, SAP Analytics Cloud mascarado na 2ª metade, marketing sem área fora do top 25%, JMP/trainee penalizado); bloco real reduzido a invariantes de formato + observabilidade; `test_synthetic`/`test_determinism` intactos (50→51 checks); suíte 16/16 local + determinismo 2x; CI run 33727053547 verde. |
| 17 | **Daily refresh + alertas** (Telegram?) | ✅ **implementado 05/09** | Depois do health check; detecção primeiro, notificação depois. Rotina `scripts/refresh_daily.py` (rotacao → coleta real → health → alerta Telegram só em anomalia); ver Log de mudanças 05/09. |

### 🟢 P3 — manutenção / escala (baixa urgência)
| # | Item | Status | Notas |
|---|---|---|---|
| 18 | **Sincronizar venv com o pyproject (pin ats-scrapers)** | ✅ **RESOLVIDO 01/09** — venv reinstalado do pin `ae0ad53` (via `refs/pull/268/head`: o upstream NUNCA mergeou o PR #268 — o commit só existe como ref de PR, por isso `git clone` simples + checkout falha; usar `git fetch origin refs/pull/268/head`). Validação real: SAP 1086/1086 com `application_deadline` (antes 0/37.373); eligible 84/84 com deadline; suíte verde (deadline/filters/hardening). ❌ risco recorrente: instalação fresca volta ao 0.2.0 PyPI sem expose — **ELIMINADO 04/09** pelo #19 (release 0.3.0 no PyPI; range aberto `>=0.3.0` monitorado no #30). |
| 19 | Trocar pin git `ae0ad53` → release PyPI do ats-scrapers quando existir | ✅ **implementado 04/09** — release 0.3.0 (02/09/2026) contém o expose do PR #268; pyproject pina `"ats-scrapers>=0.3.0"`, CI instala do PyPI mantendo o passo de verify do expose; validado offline em venv /tmp (232 eligible, delta 4 ids, suite 14/14, `data/` intocada) — detalhes no log de 04/09. |
| 20 | Validação `--timeout`/`--limit` (ACH-14) · `remote` preenchido vs campo (ACH-16) · `country` vs `country_iso` (ACH-17) · CSV completo decisão JSON=completo/CSV=tabular (ACH-18) · parsing datas DD.MM.YYYY se medir necessidade (ACH-20) · `EUROPE_COUNTRIES`/BY documentar (ACH-19) | ✅ **concluído 06/09** | Medições reais por item + decisões; ver Log de mudanças 06/09 abaixo. |
| 21 | Código morto (ACH-13) | ✅ **concluído 06/09** | Auditoria de referências (73 símbolos + 4 scripts); remoção só de zero-refs; ver Log de mudanças 06/09. |
| 22 | Separar código/dados (repo de dados) · Parquet quando volume justificar · chunking p/ frontend | ⏳ | Não por moda; quando o dado crescer. |
| 23 | Expansão internacional (NL/CH/AT → BE/FR/nórdicos/UK) + mais empresas DE (39→60→100) | ⏳ | Depois de estabilizar qualidade; ATS novo só se relevante p/ cobertura. |
| 24 | Agregadores (LinkedIn/Indeed/Glassdoor) | ⏳ | Depois de persistência + dedup maduro (identidade cross-source é complexa). |
| 25 | Interface simples (top vagas, filtros, link) | ⏳ | Sem frontend sofisticado; dashboard/lista basta. |
| 30 | Reavaliar range `>=0.3.0` do ats-scrapers quando o upstream evoluir (maturidade da release) | ⏳ **checado 2026-09-06** | P3 #19 eliminou a ref de PR `ae0ad53`; restou o range aberto no pyproject. Na próxima release do ats-scrapers (≥0.4.0): revalidar expose de `application_deadline` + suíte e decidir cap (`==0.3.*`) se a API mudar. Gate: nova release observada no PyPI ou falha de install/import. **Checagem 06/09 19:47 UTC (re-verificação independente): PyPI última release 0.3.0 (releases 0.1.0/0.2.0/0.3.0, upload 02/09) — sem release ≥0.4.0; venv instalado 0.3.0; import OK; expose de `application_deadline` presente na instalação; refresh diário sem falha de install/import → gate NÃO disparado, range `>=0.3.0` mantido, zero mudança de código (caminho B; ver Log de mudanças).** |

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
- **2026-09-05 (P2 #10)**: **Zero-return + anomaly detection implementado** —
  o health (P1 #6) ganhou o 3º tipo de alerta que faltava: **`zero_return`**
  (`src/internship_finder/health.py`, `_detect_zero_return`): uma source cujo
  run MAIS RECENTE (por `run_id`) respondeu `empty` depois de
  **`MIN_OK_HISTORY_FOR_ZERO_RETURN = 3`** runs `ok` anteriores com vagas
  (`collected > 0`) — regressão de cobertura (tenant que enchia de vagas e
  passou a responder 0), com gate de histórico espelhando o espírito do drop
  (1–2 oks podem ser flutuação; 3+ ok>0 e depois 0 sugere problema real).
  `empty` continua legítimo para source empty-consistente (nunca ok>0 → NUNCA
  alerta — anti-casos `bamboohr:sap`/`smartrecruiters:sap` testados). Decisões:
  gate por source, não global (o item do plano citava "≥5 execuções
  persistidas" como pré-requisito de histórico; a detecção funciona com o
  histórico que existir e amadurece com o cron diário — hoje 4 runs reais no
  JSONL sanitizado); ok depois de empty = recuperado, sem alerta; alertas
  coexistindo por fonte (1 por fonte por run, dedup preservado). Fluxo:
  `build_health_report` inclui o tipo (drop + recurring + zero_return) e a
  mensagem do `scripts/refresh_daily.py` formata `voltou a zero (empty) após N
  runs com vagas (último ok: M)` — o Telegram propaga sem mudar o anti-spam.
  **Calibração com histórico real (baseline antes/depois)**: sobre os 4 runs
  reais (31/08 37.373→236 · 01/09 ×2 1.084→84 subset · 05/09 38.038→224) o
  detector dispara **0 alertas de zero-return** (nenhuma source com ok>0 E
  empty no histórico — baseline limpa; health ativo segue com 1 alerta factual,
  `successfactors:lidlstiftuP2` recurring). Testes: `scripts/test_zero_return.py`
  (offline, tempfile, 20 checks: gate satisfeito/curto, limite exato 3,
  empty-consistente, OK-depois-de-empty, ordem de run_id, coexistência com
  recurring_error, malformado, bloco real de leitura com 0 zero-return) —
  **no array do CI** (14→15 scripts); `test_health` bloco real aceita o tipo
  novo no schema; `test_refresh` +2 checks de formatação. Suíte local 16/16
  TUDO OK de cwd scratch (15 CI + test_manifest); `data/` intocada (stat
  antes==depois colado). [#10 ✅]
- **2026-09-05 (P2 #17)**: **Daily refresh + alertas Telegram implementado** —
  `scripts/refresh_daily.py` (padrão standalone/CLI do repo): (1) **rotação** —
  cópia (não move) de `data/jobs.json`/`.csv`, `data/eligible_jobs.json`/`.csv`
  e `data/collection_metrics.jsonl` para `data/archive/<timestamp>/` antes do
  run (rollback = copiar de volta; `run_info.json` no archive registra o run
  que substituiu o snapshot; hardlink rejeitado — `open("w")` truncaria o
  mesmo inode); (2) **coleta real** — subprocesso `python -m
  internship_finder.cli --registry --timeout 60` (cwd = raiz; PYTHONPATH=src;
  teto `--max-collection-secs` default 5400s; exit 0/1/2 mapeado na mensagem);
  registros do run isolados por **snapshot de linhas do JSONL** antes×depois
  (sem adivinhar run_id); (3) **health** — `build_health_report` reusado
  integralmente sobre o JSONL completo pós-run; (4) **alerta** — 1 mensagem
  por run, alertas deduplicados por fonte; dispara quando exit != 0 OU
  relatório com alertas (queda brusca/erro recorrente); sem anomalia → sem
  envio (anti-spam); `--always-notify` = digest diário (documentado, não é o
  default); **cooldown limitado**: o JSONL acumula lixo histórico de validação
  (ex.: `smartrecruiters:other` 70× error de mocks) — o health é defensivo
  (malformados pulados) mas lixo VÁLIDO alerta em todo run até o JSONL ser
  limpo (alternativa rejeitada: filtrar só fontes do run esconderia anomalias
  reais). Credenciais em `.env` (gitignored): `TELEGRAM_BOT_TOKEN`/
  `TELEGRAM_CHAT_ID`; sem token → aviso e NÃO envia (nunca crasha). Telegram
  via stdlib `urllib` (sem dep nova). `--dry-run` = tempdir sintético, sem
  rede/data, valida rotação+health+mensagem. Testes: `scripts/test_refresh.py`
  (offline, tempfile, 37 checks: rotação, snapshot/resumo, mensagem com
  anomalia tipo `smartrecruiters:other` presente e sem anomalia → None,
  anti-spam/exit codes, .env, url+send mockado do Telegram, comando do
  subprocesso, dry-run com stat data/ antes==depois) — **no array do CI**
  (13→14 scripts). **E2E real autorizado (uma execução)**: run
  `2026-09-05T20:43:07.735642+00:00` — rotação para
  `data/archive/20260905T204307Z/` (5 arquivos de 31/08 preservados), funil
  **38.038 brutas → 248 filtered → 224 eligible (dedup −24)**; tenants 43 ok
  / 2 empty / 1 timeout (`successfactors:lidlstiftuP2` TIMEOUT) / 1 error
  (`moka:bayer/148387` FETCH_ERROR — pycryptodome ausente, limitação do
  scraper, não do repo); exit 2 (parcial). Health pós-run: 2 alertas —
  `smartrecruiters:other` erro recorrente (70 runs — a anomalia conhecida
  validou a detecção) + `successfactors:lidlstiftuP2` erro recorrente (2, novo
  e factual). Envio Telegram confirmado: `{"ok": true, "result":
  {"message_id": 318, ...}}` (bot @vrios_bot → chat 695791270). **Cron
  instalado** (backup do crontab em `/tmp/crontab_backup_0509.txt`, não havia
  crontab): `0 6 * * * /usr/bin/flock -n /tmp/internship_finder_refresh.lock
  cd /home/ubuntu/internship-finder && .venv/bin/python
  scripts/refresh_daily.py >> /tmp/refresh_daily.log 2>&1` (diário 06:00 UTC —
  antes do horário comercial europeu; flock evita sobreposição de runs;
  JUSTIFICATIVA de concorrência: 2 runs simultâneos de 37k+ requests
  duplicariam trabalho e disputariam os mesmos arquivos de data/). **Corrigido
  à noite**: `flock ... cd ... && python` NÃO funciona — flock executa o
  comando via `execvp` e `cd` é builtin do shell (prova: exit 69 "failed to
  execute cd"); o `&&` desligaria o python do lock. Linha final (instalada e
  documentada no README): `0 6 * * * /usr/bin/flock -n
  /tmp/internship_finder_refresh.lock /home/ubuntu/internship-finder/.venv/bin/
  python /home/ubuntu/internship-finder/scripts/refresh_daily.py >>
  /tmp/refresh_daily.log 2>&1` (caminhos absolutos; o script resolve a raiz via
  `__file__` e não depende de cwd; lock cobre o run inteiro). Validada com
  preflight cron-like (`env -i PATH=/usr/bin:/bin` + `--dry-run` → exit 0, sem
  rede, data/ intocada) e reentrada do flock (`-n` com lock segurado → exit 1;
  liberado → exit 0). **JSONL sanitizado (05/09, noite)**: critério de run_id
  dos 4 runs reais (31/08 37.373, 01/09 1.084 ×2, 05/09 38.038) — removidos
  142 run records + 214 tenant records de mock (`successfactors:acme` 140×,
  `smartrecruiters:other` 70×, Acme/DATEV; todos `collected=1` / company de
  teste); 460 → 104 linhas, 100 tenant records de 39 companies preservados.
  Backups: `/tmp/collection_metrics_pre_clean_0509.jsonl` + archive E2E.
  Health pós-limpeza: 1 alerta factual (`successfactors:lidlstiftuP2`, timeout
  31/08 + 05/09); a anomalia `smartrecruiters:other` (70×) era lixo de mock e
  sumiu do health vivo (preservada nos backups/docs como evidência E2E). Suíte
  15/15 TUDO OK de cwd scratch (14 CI + test_manifest local-only);
  `data/` intocada nas validações (stat antes==depois); `.env` não commitado
  (git status limpo de credenciais). [#17 ✅]
- **2026-09-05 (P2 #15)**: **`--country`/`--countries` padronizado e validado** (ACH-11) — antes, valor inválido era silencioso: `--country xx` → 0 vagas com exit 1 sem mensagem (frozenset que nunca casa) e token não-ISO em lista (`de,xx`) era ignorado. Agora `parse_country_spec` levanta `ValueError` citando os tokens inválidos (spec vazia `,` também) e o CLI converte em `parser.error` (mensagem clara + exit 2), antes de ler input/coletar. **Sem alterar o filtro**: specs válidas passam pelo mesmo parse de `select_eligible` — prova por código: `--country de` → **232 ids idênticos** (lista-a-lista, mesma ordem, antes × depois; delta vs snapshot 236 = só os 4 TRUE dups do #14), `europe` 371, `all` 31006, `remote` 1 idênticos. `all` canônico (world/any aceitos por compat, docstring); case-insensitive (`DE,AT`); vírgulas duplas ok. Testes: `test_countries` +21 checks (validação de spec + bloco CLI exit 2/mensagem); suite 14/14 TUDO OK de cwd scratch; `data/` intocada (stat antes==depois). [#15 ✅]
- **2026-09-05 (Limpeza de repo — P3 #21)**: **array do CI corrigido 16→13 e
  remoção de 9 arquivos mortos/redundantes** — auditoria do orquestrador em 05/09: 3
  itens do array (`test_fetch`, `test_find_company`, `test_resolver`) **não eram
  testes** — smokes de rede SEM assertions (prints + fetch ao vivo), incluídos por
  engano no PR #21 (o run ficava verde sem prover cobertura real). **Lição
  registrada**: "CI verde" não prova cobertura — conferir membership no workflow;
  um script só é teste se tem ASSERTIONS. Removidos do repo e do array; contagens
  reais: CI = **13**, suite local = **14** (13 + `test_manifest`, local-only por
  rede externa). Deleções com re-grep de 0 refs: `collectors/base.py` +
  `collectors/greenhouse.py` (código morto, 0 refs externas no grafo de imports),
  `experiments/ats_test.py` (scratch), `ARCHITECTURE.md` e `DEVELOPMENT.md`
  (duplicados, 0 refs — as 2 regras únicas do DEVELOPMENT.md migradas para
  AGENTS.md), `requirements.txt` (pin git `ae0ad53` obsoleto — pyproject é a fonte
  de deps; removido também do cache-dependency-path do CI).
  Docs sincronizadas: README (suite 14/14, três modos do CLI, `countries.py`/
  `registry.py` na estrutura, tabela de verificação marcada **histórica**),
  AGENTS.md (2 regras migradas), docs/architecture (módulos) e PROJECT_STATUS
  (13 scripts).
- **2026-09-04 (P3 #19)**: **Pin git `ae0ad53` → release PyPI ats-scrapers 0.3.0** —
  pyproject troca `"ats-scrapers @ git+https://github.com/kalil0321/ats-scrapers@ae0ad53"`
  por `"ats-scrapers>=0.3.0"` (release 02/09/2026 contém o expose de
  `application_deadline` do PR #268); `[tool.hatch.metadata] allow-direct-references`
  **REMOVIDO** — com dep PyPI normal o hatchling constrói o editable sem a flag
  (evidência: `pip install -e .` completo, com deps, em venv /tmp fresco → build
  okay + ats-scrapers 0.3.0 do PyPI + `import internship_finder.cli` OK). CI:
  passo "Install ats-scrapers (PyPI >=0.3.0)" substitui o tarball `ae0ad53`;
  passo de verify do expose MANTIDO (valida a 0.3.0 instalada); array de testes
  inalterado (13 scripts; `test_manifest` segue fora — rede externa; corrigido 05/09). Validação
  offline em venv /tmp (rede só p/ pip): expose confirmado no successfactors
  instalado (2 hits em `application_deadline`), `import internship_finder.cli`
  OK, pipeline `--country de --no-rank` sobre `data/jobs.json` → **232 eligible**
  (ids subconjunto do snapshot 236; delta = as 4 duplicatas TRUE do #14: VW
  After Sales, SAP Bid Council, Knorr Purchasing Controlling, MAHLE Lead-Buying),
  suite standalone **14/14 TUDO OK**, `data/` intocada (stat antes == depois).
  Limitação declarada: `application_deadline` 0/232 preenchido — o snapshot
  local (31/08) foi coletado com 0.2.0 (sem expose); o pipeline serializa o
  campo (chave presente, `None`); preencher exige coleta nova, fora do escopo
  (rede de ATS proibida na tarefa). Restou obrigação de maturidade da release →
  item P3 #30 (registrado com data). [#19 ✅]
- **2026-09-06 (P3 #20)**: **Validações ACH pequenas — "medir antes de corrigir"** (PR #27) — medições reais sobre `data/` (05/09: 38.038 raw / 224 eligible; funil reproduzido com o código novo, idêntico: 38.038 → 3.122 → 759 → 248 → 224, dedup 24). Por item:
  - **ACH-18 (CSV)**: `data/jobs.csv` = 38.038 linhas = `jobs.json` (0 ids divergentes; 15 campos/linha em 100% das linhas) — **sem truncamento**, mas coluna `remote` ausente em **38.038/38.038** linhas (e **224/224** no eligible), além de `description`/`raw`/`score_breakdown` (aninhados/texto). Decisão: **JSON=completo, CSV=tabular** (documentado em `save_outputs` + README); correção mínima: coluna `remote` adicionada a `CSV_COLUMNS` (escalar, relevante ao filtro; cli.py:66). `data/` não regenerada (não regenerar sem coleta — shape muda na próxima coleta/refresh).
  - **ACH-16 (remote)**: campo `remote` = `None` em **0/38.038** (nenhum ATS expõe; adapter não mapeia); filtro `--country remote` funciona via location (`is_remote`: 101 locais com marcador; cascata → **1 eligible**). Decisão: funciona por design — documentado, sem mudança de código; teste novo: `matches_country` remote via location (test_countries).
  - **ACH-17 (country vs country_iso)**: **0/38.038 mismatches** (35.987 com ambos iguais por construção do adapter — cli/ats.py gravam o MESMO valor inferido nos dois campos; 2.051 ambos `None`; 0 não-ISO); eligible **224/224** consistentes. Decisão: medido, sem ação (0 ocorrências).
  - **ACH-14 (--timeout/--limit)**: `limit` = corte por tenant **pós-coleta** (ats_scraper.py:256-257 `if limit and len(raw_jobs) > limit: raw_jobs[:limit]`); medido via mock: limit=2 → 2/tenant (4 total), limit=0 → todos (6), limit=1 → 2; fetch não é reduzido pelo limit. `--timeout <= 0` / `--limit < 0` eram aceitos com comportamento indefinido (deadline virava só a margem de 25s / slice `[:-k]` sutil). Correção mínima: validação no CLI antes de coleta (cli.py, mesmo ponto do `--country` P2 #15): `--timeout <= 0` → erro claro exit 2; `--limit < 0` → erro claro exit 2; help atualizado (semântica explícita). `scripts/test_collect_flags.py` (NOVO, 19 checks, offline — mocks, sem rede/data) **entrou no CI** (array 15→16).
  - **ACH-20 (DD.MM.YYYY)**: **0 ocorrências** (eligible: `posted_at` ISO 64 / None 160; `application_deadline` ISO 152 / None 72; `raw`: 0 valores DD.MM.YYYY em 38.038) — **"não mediu necessidade"**, fechado sem parser, documentado.
  - **ACH-19 (EUROPE_COUNTRIES/BY)**: `BY` **estava** no frozenset (45 códigos) apesar do comentário dizer "RU/BY ficam de fora" — contradição código/melhor-documentação; medido **0** vagas reais com ISO `by` (e 0 `ru`). Decisão: **BY excluído** (alinha código ao critério documentado — viabilidade de estágio/estudo em alemão no contexto do dono; mesmo critério do RU; docstring justifica); teste: `by`/`ru` not in `EUROPE_COUNTRIES` (test_countries).
  - Suíte local **17/17 TUDO OK** (16 CI + manifest) de cwd scratch; `data/` intocada (stat antes == depois, colado no relatório); funil 224 reproduzido (zero mudança de comportamento). Docs: MASTER_PLAN #20 ✅, PROJECT_STATUS (Next = #30), README (tabela de flags `--timeout`/`--limit` + subseção "Saida (JSON/CSV) — contrato"). [#20 ✅]
- **2026-09-06 (P3 #21)**: **Código morto (ACH-13) — auditoria de referências + remoção de zero-refs** — método: inventário (73 símbolos públicos em 17 módulos + 4 scripts não-teste) + grep de referências em TODO o repo (`src/`, `scripts/`, `.github/`, docs, README, AGENTS — word-boundary, linha a linha) + pyflakes (venv /tmp descartável, sem tocar no venv do projeto) para pegar imports/locais não usados que grep de nome não vê. **Nenhum símbolo público de src/ ficou sem referência** (todo símbolo tem uso interno, em teste ou doc — mínimo `Score.to_dict`, 0 call sites; `CompanyResolver`/`company_status` só referenciados por testes+docs, mantidos por serem API pública testada/documentada; `__version__` no `__init__`, 0 refs, mantido por convenção de pacote). **Removido (16 itens, todos com 0 refs verificadas + pyflakes limpo depois)**:
  - `src/internship_finder/ranking.py`: método `Score.to_dict` (0 call sites — a serialização real é `d["score"] = score.total` / `d["score_breakdown"] = score.breakdown` no `rank_jobs`).
  - `src/internship_finder/health.py`: `import json` (0 usos — docstring menciona `json.dumps` como contrato do caller).
  - `src/internship_finder/filters.py`: re-export dead de 4 nomes de `countries` (`EUROPE_COUNTRIES`, `COUNTRY_NAMES`, `_country_name_from_location`, `_iso_token_from_location` — 0 consumidores importando de `filters`; os consumidores importam de `countries`, fonte única; mantidos COUNTRY_CODES/is_remote — exercitados pelo `test_compat_re_export` do test_countries — e os usados internamente).
  - imports não usados em testes (pyflakes): `test_health.py` DROP_THRESHOLD; `test_hardening.py` `import json`, `from internship_finder import collectors`, 2× `Job`, `ats_scraper`, `UTC` (imports com `# noqa: F401` explícito MANTIDOS — deliberados); `test_registry.py` SEED; `test_sqlite.py` `import sqlite3`.
  - locais não usados: `test_registry.py` `unspecified`; `refresh_daily.py` `n_fail`; `test_dedup.py` `keys_w = dict(candidate_keys_for_audit := {})` (junk walrus); `test_validation.py` `as e`; `test_ranking.py` `sc_bonus`.
  - Array do CI INALTERADO (16) — nenhum teste do array saiu; suíte local 17/17 TUDO OK de cwd scratch (pré e pós); `data/` intocada (stat antes == depois); `__version__`/`CompanyResolver`/`company_status`/4 scripts utilitários mantidos com justificativa (ver relatório exec). Observações registradas: README diz que `company_status` é "exposto pelo `--health`" mas o cli.py não o chama (doc ≠ código, fora do escopo); `filters.py` re-export vivo (COUNTRY_CODES/is_remote) precisaria de `# noqa: F401` num eventual passo de lint; imports `# noqa: F401` deliberados no test_hardening (Job importável no bloco). [#21 ✅]
- **2026-09-06 (P3 #30)**: **Range `ats-scrapers>=0.3.0` reavaliado — gate NÃO
  disparado, range mantido, zero mudança de código** — gate executado ao vivo em
  06/09 15:01 UTC (`curl https://pypi.org/pypi/ats-scrapers/json`): `info.version`
  = **0.3.0**, releases = `[0.1.0, 0.2.0, 0.3.0]` (última upload 02/09T20:53Z) →
  **nenhuma release ≥0.4.0**. Instalação no venv do projeto: ats-scrapers 0.3.0
  (`pip show`), `import ats_scrapers.scrapers.successfactors` OK (path:
  `.venv/lib/python3.12/site-packages/ats_scrapers/scrapers/successfactors.py`),
  expose de `application_deadline` presente na instalação (3 ocorrências no
  módulo — critério do CI satisfeito). Refresh diário (cron 06/09 06:00 UTC,
  `/tmp/refresh_daily.log`): sem falha de install/import — únicos erros são os
  alertas conhecidos (`moka:bayer/148387` pycryptodome ausente — limitação do
  scraper upstream; `successfactors:lidlstiftuP2` timeout). **Caminho B do item
  #30**: checagem registrada, range `>=0.3.0` mantido, gate continua monitorado
  (próxima checagem: release ≥0.4.0 no PyPI ou falha de install/import).
  `data/` intocada (stat antes==depois); git: branch `feature/p3-30-ats-range`
  com commit de docs, sem PR (decisão do dono). [#30 checagem ✅]
- **2026-09-06 (P1 #5)**: **Persistência SQLite marcada como ✅ implementada no plano — registro retroativo (drift documental corrigido)**. O código do P1 #5 estava implementado, mergeado e testado desde **01/09 (PR #10, commit `e683cd8`** — "feat(p1): Persistencia SQLite first/last_seen/active/archived (P1 #5) (#10)", main), mas o MASTER_PLAN nunca havia sido atualizado: o item #5 continuava 🔓 DESBLOQUEADO 31/08 e o Log não tinha entrada do PR #10 — registro pendente desde o merge, agora corrigido. Verificação real (evidência > suposição, tudo no código/git, não por memória): `git fetch origin` → main local = remota = `87b8dca`, 0 PRs abertos; `git merge-base --is-ancestor e683cd8 HEAD` → OK (o próprio `e683cd8` é o commit squash do PR #10, contido no main; data 01/09; tocava 3 arquivos: `scripts/test_sqlite.py` +212, `src/internship_finder/cli.py` +27, `src/internship_finder/storage/sqlite_store.py` +261). Artefatos conferidos no working tree: `storage/sqlite_store.py` — `SqliteStore` (linha 114), `LIFECYCLE_COLUMNS = ["first_seen", "last_seen", "active", "archived"]` (linha 59), DDL `CREATE TABLE ... jobs` com `application_deadline TEXT` (linha 75) + `first_seen`/`last_seen` NOT NULL + `active`/`archived` INTEGER (linhas 80-83) — o campo do plano (application_deadline junto com first/last_seen) está refletido no schema real; `cli.py` — flag `--sqlite PATH` (linhas 386-393, help documenta first/last_seen/active/archived) e bloco `if args.sqlite:` (linhas 535-547) gravando o run via `SqliteStore` com `except Exception as exc:  # noqa: BLE001` — falha de sqlite nunca derruba a coleta; CI — `scripts/test_sqlite.py` no array de testes de `.github/workflows/ci.yml` (linha 96, 16 scripts). Prova viva: smoke `test_sqlite.py` → "TUDO OK" (offline, tempfile, sem rede/data). `PROJECT_STATUS.md` já listava o P1 #5 como completado (consistente) — só ganhou a data 01/09 na entrada existente (correção factual mínima, nada reescrito). `data/` intocada (stat antes == depois). Nenhuma mudança de código (tarefa de registro, não de implementação). [#5 ✅ registro retroativo]
- **2026-09-06 (P3 #30)**: **Range `ats-scrapers>=0.3.0` reavaliado — gate NÃO
+  disparado (caminho B): range mantido, zero mudança de código** — checagem
+  independente executada ao vivo em 06/09 **19:47 UTC** com re-verificação feita
+  na hora (a checagem da manhã de 06/09 15:01 UTC segue na branch local não
+  mergeada `feature/p3-30-ats-range`; este registro re-valida as mesmas
+  evidências sobre o main). **PyPI** (`curl -s https://pypi.org/pypi/ats-scrapers/json`):
+  `info.version` = **0.3.0**; releases = `0.1.0, 0.2.0, 0.3.0` — 0.3.0 com 2
+  arquivos, último upload **2026-09-02T20:53:41Z**; **nenhuma release ≥0.4.0
+  existe → critério literal do gate (release ≥0.4.0) NÃO atingido**. **Instalado**:
+  `.venv/bin/pip show ats-scrapers` → Version **0.3.0**; `import
+  ats_scrapers.scrapers.successfactors` OK (path
+  `.venv/lib/python3.12/site-packages/ats_scrapers/scrapers/successfactors.py`);
+  expose de `application_deadline` **presente** no módulo instalado (2
+  ocorrências via grep — critério do CI satisfeito). **Install/import**:
+  `/tmp/refresh_daily.log` (run do cron 06/09 06:00 UTC, arquivo existe, 118 KB)
+  sem nenhuma falha de instalação/importação — únicos erros são os alertas
+  CONHECIDOS do upstream, que não disparam o gate (`moka:bayer/148387`:
+  ScraperError "Moka scraper requires pycryptodome" — limitação do scraper;
+  `successfactors:lidlstiftuP2`: timeout). **Decisão — caminho B do item #30**:
+  checagem registrada, `pyproject.toml` intocado (range `>=0.3.0` mantido), gate
+  continua monitorado (próxima checagem: release ≥0.4.0 no PyPI ou falha real de
+  install/import). Validação: suíte local **17/17 TUDO OK** de cwd scratch;
+  `data/` intocada (stat antes==depois); branches `feature/p3-30-ats-range`
+  (c7e55b6) e `feature/p1-05-sqlite-registro` (abf13df) inalteradas; sem push,
+  sem PR (decisão do dono). [#30 checado ✅ caminho B]
  main `e7604db`, run `33840628495` verde; mergeado 04/09) — `registry.py` com
  `SEED` das 39 empresas (fonte única em código: nome canônico de coleta +
  ATS/tenant de referência + `enabled`; substitui a lista colada do README),
  `CompanyRegistry` (get/enabled/entries) e `company_status` que **deriva o
  estado por empresa do JSONL de métricas** (`data/collection_metrics.jsonl`),
  read-only e defensivo (registro malformado nunca derruba). CLI: flag
  `--registry` (usa as ENABLED do registry como lista de coleta; com
  `--companies` restringe a subconjunto na ordem informada; `--companies` puro
  segue funcionando como antes). Decisão de design: **registry = configuração,
  JSONL = status/última coleta** — estado operacional tem fonte única e o
  registry não duplica resultado. `test_registry.py` (offline, tempfile, sem
  rede/data: seed 39, enabled, subconjunto preservando ordem, ponte
  registry→CLI com mock do fetch, company_status) — **entrou no CI** (array 12→13
  scripts; `test_manifest` segue fora por depender de rede externa
  storage.stapply.ai; corrigido 05/09). Suite local 14/14 TUDO OK; docs README/PROJECT_STATUS
  atualizadas (04/09). Decisão: registry vira a forma default de coleta nos
  próximos passos; `--companies` mantido por compatibilidade. [#13 ✅]
- **2026-09-03 (P2 #14)**: **Dedup 2.0 textual implementado** (PR #19, main
  `4ed28d8`, run verde `33799148404`) — medição real primeiro (mandato da
  tarefa): sobre país-DE 258→236, 12 pares candidatos; 4 verdadeiros escapavam
  (Knorr `Praktikant`/`Working Student` Purchasing Controlling, SAP
  `Intern`/`Working Student` Bid Council DPO, VW `Praktikum`/`Werkstudentin
  /Werkstudent` Analytics After Sales, MAHLE `Internship`/`Praktikum`
  Lead-Buying Mechatronics — descrições 1:1 EN/DE, veredito manual por
  conteúdo). `TYPE_EQUIVALENCES` estendida com `\b` de fronteira de palavra
  (`praktikums?`, `praktikanten?`, `interns?`, `internships?` → working
  student) + colapso de palavras repetidas na bag (variante real
  "Werkstudentin / Werkstudent" não difere de um único "working student").
  `Pflichtpraktikum`/`Hochschulpraktikum` NÃO são atingidos (composto:
  obrigatório≠voluntário — anti-testes); `trainee` fora do domínio;
  description NÃO entrou no fingerprint (0 pares exigiram; normalizar desc é
  ruído e risco de falso positivo — decisão documentada). `test_dedup` +71
  linhas (casos reais medidos + anti-casos + sintético determinístico);
  `test_countries` desacoplado do número mágico `236` (invariante: pipeline é
  subconjunto do snapshot, dedup só remove + observabilidade do delta —
  autorizado pelo dono, precedente P2 #16). Baseline eligible 236→232 (4
  duplicatas TRUE, todas por company+title+location; ids auditados); suíte
  local 16/16 TUDO OK; delegado OpenHands flash-0731 (1 run, sem resume
  necessário). [#14 ✅]
- **2026-09-02 (P1 #9)**: **Documentação operacional implementada** (PR #15, main
  `f55dc95`, run verde) — README/PROJECT_STATUS/architecture/roadmap atualizados
  para o estado real (funil 37.373→236, flags novas, `is_student_role`, módulos
  novos), 8 relatórios antigos marcados como histórico. Números validados contra
  `scripts/coverage.py` ao vivo. P2 #10 segue com gate (≥5 execuções de coleta
  real — histórico atual: 1 run completo 31/08 + validações pontuais). [#9 ✅]
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