# Fase F1 — Desligar componentes mortos (disable dead components)

> Status: IMPLEMENTADA (branch `feature/f1-dead-components`, base `f4f2a2f`).
> Data: 01/10/2026. Escopo autorizado pelo dono (prompt F1): desligar 3
> componentes que consomem recurso sem gerar valor — mantendo o código
> preservado para uso futuro sob demanda.

## 0. Motivação (auditoria — números de produção)

Três componentes com custo real e retorno zero:

| # | Componente | Evidência de produção |
| --- | --- | --- |
| 1 | **Enrichment LLM (GLM-5.3-Flash via NVIDIA)** | Janela NVIDIA degradada 26–30/09: `enrichment_status.json` de 29/09 — 21 chamadas LLM, 42 retries, **5h38min de run, 0 extrações** (todas `ReadTimeout` ~264s); o subprocesso segurou o flock do cron até 14:54 UTC e o ciclo do dia foi perdido. 30/09: 17.615s (~4h53), 22 chamadas / 6 ok / 16 falha. Fase H §G2 já apontava: "enrichment operacionalmente morto nesta janela". |
| 2 | **Deadline hydration** (`application_deadline` de SuccessFactors) | PROJECT_STATUS P1.4, auditado **231/231**: o campo é a validade do FEED (`g:expiration_date` = data do feed + 30 dias), não o prazo real de fechamento. O ranking nunca leu o campo (`ranking.py`/`filters.py`/`dedup.py` — 0 referências; verificado por grep + testes C1–C4). A UI já rotula `platform_sf` como "validade do anúncio", não prazo. |
| 3 | **Official page / intel** (Fase D) | Cookie-wall + páginas JS-rendered: Fase H — 100% "Not mentioned" nos campos de intel; Fase A já cobriu as descriptions ausentes e o estágio não gerou informação nova (0 descriptions melhoradas na A/B da Fase D). |

## 1. Desenho — 3 kill switches, tudo reversível

Princípio da fase: **default OFF, código preservado, reativação sob demanda**.
Nada é deletado; nenhum contrato é quebrado. Cada componente ganhou um gate
independente:

### 1.1 Enrichment LLM → gate de configuração + teto de tempo

- **Gate env `INTERNSHIP_FINDER_ENRICHMENT`** (default OFF): a flag CLI
  `--enrichment` do `refresh_daily.py` só é efetiva quando a env var `=1`
  (herdada do ambiente OU injetada do `.env` — mesmo caminho da
  `NVIDIA_API_KEY`). O cron de produção **não define a env var** → o
  enrichment fica OFF sem tocar na linha do crontab (que não deve ser editada
  fora de janela sancionada; o README documenta que a linha mantém
  `--enrichment` e por que isso agora é inócuo).
- **Teto `--enrichment-max-secs`** (default 1800s): o subprocesso do
  enrichment agora roda com `subprocess.run(timeout=...)`. Este é o fix
  estrutural do flock: mesmo reativado no futuro, um run zumbi morre em 30min
  e vira log de UMA linha — o refresh termina com o exit code da coleta.
  Segurança da morte: o store é atômico por record (upsert + `os.replace`) e
  o lock interno `.enrichment.lock` é flock do SO — morte de processo nunca
  corrompe dados nem deixa lock preso.
- Ordem dos gates: `publication_allowed` (exit 1/124/eligible 0) continua
  ANTES do gate F1 — refresh inválido nunca roda enrichment, com ou sem a
  env var (test_f1 A4).

### 1.2 Deadline hydration → flag no adapter

- Flag env `INTERNSHIP_FINDER_DEADLINE_HYDRATION` (default OFF) +
  `deadline_hydration_enabled()`/`set_deadline_hydration_enabled()` em
  `adapters/ats.py` — mesma mecanica da flag
  `INTERNSHIP_FINDER_GEOCODING` (geocoding.py), que é o padrão de env-flag
  do projeto.
- OFF: `AtsJobAdapter.to_job()` não popula `Job.application_deadline` (o
  campo existente em dados históricos/SQLite continua legível — a UI e o
  `app_intel.deadline_kind()` seguem funcionando: o gate é apenas na
  POPULAÇÃO, não na leitura).
- O modelo `Job`, o schema SQLite, o `raw` (contrato), a serialização e o
  caminho de parse (ISO/Z/offset) permanecem intactos — reativação = 1 env
  var, sem migracão.
- **"Remova deadline dos critérios de ranking se estiver em uso"**: não
  estava em uso — `ranking.py`, `filters.py`, `dedup.py` e
  `materials_ranking.py` têm **zero** referências ao campo (verificação por
  grep + prova por teste). O que existia era classificação de URGENCIA
  pós-ranking (app_intel), que já tratava `platform_sf` como "validade", e
  continua igual. Nada a remover; o critério já estava limpo — agora com
  teste de invariante (C1–C4) para não regredir.

### 1.3 Official page / intel → default OFF

- `--official-page` do CLI: default `True` → **`False`** (o cron não passa a
  flag; produção roda com o default). `--official-page` explícito reativa
  sob demanda.
- `run_filter_pipeline(official_page=...)` default idem. O estágio D2 (view
  read-only da evidência) segue lendo o que já existe em `data/` — apenas o
  GET de coleta morre.

## 2. Mudanças por arquivo

| Arquivo | Mudança |
| --- | --- | 
| `scripts/refresh_daily.py` | `ENRICHMENT_ENV_FLAG` + gate em `run_enrichment` (default OFF, log de 1 linha); `DEFAULT_ENRICHMENT_MAX_SECS=1800` + `timeout=` no subprocesso + `TimeoutExpired` → log; flag `--enrichment-max-secs`; help atualizado |
| `src/internship_finder/adapters/ats.py` | `DEADLINE_HYDRATION_ENV` + `deadline_hydration_enabled()`/`set_...()`; `to_job` popula deadline só com a flag ON |
| `src/internship_finder/cli.py` | `--official-page` default `False` (+docstrings) |
| `scripts/test_f1.py` | NOVO — 22 checks, grupos A–E (gates, timeout, ranking sem campos mortos, defaults) |
| `scripts/test_refresh.py` | Blocos de enrichment com a env flag F1 onde o subprocesso deve rodar; novo check "F1: --enrichment SEM INTERNSHIP_FINDER_ENRICHMENT=1 -> pulado" |
| `scripts/test_application_deadline.py` | Caminho do adapter agora roda COM a flag ON (contrato preservado); novo bloco F1 (default OFF + reativação) |
| `scripts/test_hardening.py` | 12a roda com flag ON; novo 12c (default OFF não hidrata) |
| `scripts/test_fasei.py` | Blocos D/I rodam com flag ON (restaurada no finally) |
| `.github/workflows/ci.yml` | `test_f1` no array (45→46) |
| `README.md` | Tabela de ambiente (2 flags novas), `--official-page` default DESLIGADO, nota F1 no bloco do cron |
| `docs/fase_f1_dead_components.md` | Este relatório |

## 3. A/B (efeito no pipeline, mesmo snapshot)

O A/B da F1 é trivial por construção — os 3 gates desligam estágios, não
alteram transformações:

1. **Ranking/eligibilidade**: zero diff esperado — nenhum dos 3 componentes
   toca score/eligibilidade/dedup (C1–C4 travam por teste). Deadline OFF só
   zera o campo na SAÍDA bruta (o eligible JSON nunca o usou para decisão).
2. **Official page OFF**: nas A/Bs anteriores (Fase D, test_official_evidence
   17/18) já era demonstrado byte-idêntico com e sem o estágio — score/ids/
   ordem idênticos. A coleta fica ~150 GETs/dia mais leve.
3. **Enrichment OFF**: nenhuma chamada LLM, nenhum fetch sweep (~40 GETs),
   nenhuma re-publicação pós-enrichment. Os chips 🔎 existentes continuam
   renderizando (store preservado) — apenas param de atualizar.

**Efeito operacional esperado no cron**: run de ~10–30min de volta ao normal
(vs. 5h38+ do zumbi), flock liberado logo após a coleta, zero chamadas NVIDIA
enquanto a env var não existir.

## 4. Testes

- `scripts/test_f1.py` (novo, 22 checks): A1–A6 (gate enrichment: default
  pulado, reativação env/.env, precedência publication_allowed, timeout →
  log sem crash, teto 1800), B1–B4 (deadline: default OFF, flag ON preserva
  parse/persistência), C1–C4 (score/eligibilidade/dedup idênticos com/sem
  deadline + contrato por inspeção), D1–D3 (official-page default OFF no
  parser e no pipeline, reativação explícita), E1–E2 (refresh sem
  subprocesso; lock flock do runner preservado).
- Suíte completa no worktree (py3.12, venv isolada): **46/46 TUDO OK**
  (suíte sem `data/`, igual ao CI).
- Baseline antes das mudanças (base `f4f2a2f`): 42/45 no VPS — as 3 falhas
  (`test_countries`, `test_visa_policy`, `test_zero_return`) são drifts
  pré-existentes de blocos "real" que dependem de `data/` de produção
  (passam no CI sem `data/`); **zero relação com F1** (reproduzidas na base
  intocada antes de qualquer edição).

## 5. Reativação sob demanda (runbook)

```bash
# Enrichment LLM (fora de janela degradada; monitorar enrichment_status.json):
INTERNSHIP_FINDER_ENRICHMENT=1 .venv/bin/python scripts/refresh_daily.py \
    --enrichment --pages-dir ... --always-notify
# ou persistente: INTERNSHIP_FINDER_ENRICHMENT=1 no .env (gitignored)

# Deadline hydration (se uma fonte com prazo real aparecer):
INTERNSHIP_FINDER_DEADLINE_HYDRATION=1 .venv/bin/python -m internship_finder.cli --registry ...

# Official page:
... -m internship_finder.cli --registry --official-page ...
```

Nota sobre o enrichment: reativar sem trocar a env var não faz nada (gate
pulado com log). O teto de 1800s é defesa permanente: mesmo reativado, o
flock nunca mais fica preso por um run zumbi.

## 6. Limitações / notas honestas

- A linha do crontab NÃO foi editada (regra do projeto: produção muda via
  git pull). O `--enrichment` explícito na linha é inócuo sem a env var —
  comportamento novo é o gate. O dono pode remover a flag do crontab em
  janela sancionada por higiene, mas não é necessário.
- `test_refresh.py` herda o mock de `subprocess.run` — os novos asserts do
  teto (A5) testam o CAMINHO do timeout (log + exit preservado), não um
  timeout real de relógio.
- Chips 🔎 do enrichment param de atualizar (store congelado no último run);
  dados existentes continuam renderizando. Limpar o store = decisão futura.
- O enrichment_run.py standalone (manual) NÃO tem gate F1 — continua
  funcionando direto (o gate é no refresh_daily; uso manual já era o fluxo
  de drenagem controlada).
