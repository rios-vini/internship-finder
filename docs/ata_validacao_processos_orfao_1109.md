# Ata — Validação operacional: processos órfãos (11/09/2026)

**Status:** decidido — **A (nenhum problema acionável)**, nenhuma alteração de código.

## Contexto

A auditoria de 08/09 (`auditoria_internship_finder_2026-09-08.md`, fora do repo) levantou o achado CF-02 (P1):

> `subprocess.run(timeout=max_secs)` SIGKILLa só o CLI; fetch_workers mp.Process filhos ficam
> órfãos até timeout próprio (≤85s). Sem start_new_session/killpg — CONFIRMADO (por leitura).

Classificação original: **confirmado por leitura de código, sem reprodução**. Esta ata reavalia
o achado com evidência empírica. Decisão prévia da tarefa: não reescrever o lifecycle nem
introduzir `killpg`/`start_new_session`/supervisor/daemon sem evidência reproduzível.

## Implementação auditada

- `src/internship_finder/collectors/ats_scraper.py` — `fetch_with_timeout` roda o fetch de cada
  tenant em subprocesso com teto (`timeout` + `TIMEOUT_MARGIN=25`) e 4 desfechos observáveis:
  sucesso / erro estruturado `("-error", code, detail)` / timeout / worker morto
  (`exitcode`/`is_alive` detectado ANTES do deadline, distinto de timeout).
- Em TODOS os caminhos o `finally` executa `_shutdown()` (linhas 99–118, 187–205):
  `terminate() → join(5s) → kill() → join(2s) → drain queue (get_nowait até Empty) →
  close() → join_thread()`.
- Cleanup existente: `scripts/test_lifecycle.py` (P1 #8, item #8 do MASTER_PLAN, 1 linha no CI).

## Testes executados (11/09, venv de produção, cwd scratch)

### 1. `test_lifecycle.py` × 5 repetições
Todas `TUDO OK` (~2,06 s cada). Cobre os cenários da tarefa com subprocesso REAL (sem rede):
timeout (fetch dorme 30 s; `CollectionError(TIMEOUT)` em ~1 s), worker morto (`os._exit(1)` →
`UNKNOWN` + exitcode no detail, antes do deadline), erro estruturado, sucesso e loop de 5
chamadas verificando **nenhum órfão** (pid real via `os.kill(pid,0)` + `active_children`).
`ps` do projeto após cada execução: **0 processos**.

### 2. Experimento A — SIGKILL direto no processo pai (cenário da tarefa)
Pai cria um `fetch_worker` REAL (trabalho simulado de 60 s) e se mata com `SIGKILL`.
Timeline observada (t = 0 no start): pai morto em t=2 s; worker **sobrevive** (ppid 918313 → 1,
adotado pelo init) e **termina sozinho em t=60 s** — 58 s de vida órfã, exatamente a duração
do próprio trabalho. Nenhum processo residual.

### 3. Experimento B — CF-02 exato (subprocess.run timeout)
Pai faz `subprocess.run([cli], timeout=4)` (mesma mecânica de `run_collection`); estoura →
`TimeoutExpired` → SIGKILL no CLI (`CompletedProcess 124`). O neto (fetch_worker, 60 s de
trabalho) fica órfão (ppid 919606 → 1) e **termina sozinho em t=62 s** — 58 s de vida órfã.
Nenhum processo residual.

### 4. Verificação do sistema
0 processos do projeto em qualquer inspeção pós-execução; VPS limpo às 22:53 UTC (17 h após o
último run cron).

## Evidência de produção (`/tmp/refresh_daily.log`, 06–11/09, 6 runs reais)

- **0 estouros do teto** (`subprocess.run` de 5400 s nunca estourou) → o gatilho do CF-02
  **nunca ocorreu em produção**. Todos os runs completaram em ~9 min (06:00:02 → ~06:09:30).
- **12 timeouts de tenant** (Lidl `successfactors:lidlstiftuP2`, 85 s = 60+25) — todos tratados
  DENTRO do lifecycle (`_shutdown` completo, run prossegue com 77/83 fontes ok). O cenário de
  timeout real roda o código P1 #8 dezenas de vezes por semana, sem órfãos (verificado a cada
  inspeção pós-run).
- Cron diário 06:00 + `flock -n`: sem sobreposição de runs (janela de órfão potencial, quando
  existir, é de minutos; intervalo entre runs é de 24 h).

## Investigação do cenário SIGKILL (separada)

1. **Ocorre na implementação atual?** O mecanismo sim (Exps A e B): `SIGKILL` não propaga a
   filhos/netos; sem `killpg`/`start_new_session` o worker órfão é adotado pelo init e não é
   morto pelo pai. É o comportamento padrão do SO — nenhuma implementação de `multiprocessing`
   muda isso sem as primitivas citadas.
2. **Por quanto tempo?** Até o fim do próprio trabalho do worker (medido: 58 s de vida órfã
   para 60 s de trabalho). Em produção o trabalho é bound pela lib (timeout por request); o
   caso mais longo observado (Lidl) é justamente um fetch que estoura 85 s — a vida órfã é da
   ordem de segundos a poucos minutos no pior caso.
3. **Mecanismos existentes que presumem o cenário:** (a) fetch com timeout na lib
   (self-terminating); (b) cron diário + `flock -n` (sem sobreposição); (c) **workers órfãos
   não escrevem dados** — só a queue; jobs.json/jobs.db/CSV são escritos exclusivamente pelo
   processo principal do CLI, com escrita atômica (PR #44), então um término tardio não
   corrompe nada; (d) cache de geocoding é a única escrita possível de worker órfão
   (idempotente, benigna).
4. **Impacto persistente no ambiente?** Nenhum observado: 0 acúmulo de processos, 0
   estouros de teto, 0 resíduos entre runs, sem escrita concorrente em estado durável.
5. **Problema operacional relevante?** Não há evidência. O cenário exige um duplo acidente
   (teto do refresh estourar **e** um tenant estar no meio de um fetch naquele instante) —
   nunca aconteceu em 6 runs reais.

## Decisão

**A — nenhum problema acionável.** O lifecycle atual (`terminate → join → kill → join + queue
drenada`) é suficiente; os testes demonstram ausência de órfãos em todos os desfechos de
falha/timeout relevantes. **Nenhuma alteração de implementação.**

A limitação inevitável do `SIGKILL` no pai é documentada, não corrigida (decisão da tarefa:
sem `killpg`, `start_new_session`, supervisor, daemon ou nova arquitetura sem evidência).
Se um dia houver evidência de fetches que sobrevivem por horas (ex.: bug de timeout na lib),
reavaliar com a MENOR correção (ex.: `start_new_session` + `killpg` apenas no CLI do
`run_collection`) — reabrir #38 nesse caso.

## Entregáveis

- Arquivos alterados: **nenhum** (código/intocado). Este documento + item #38 do MASTER_PLAN
  (registro da decisão).
- Testes executados: `scripts/test_lifecycle.py` ×5; Exps A/B (scripts de reprodução em
  `/tmp/orphan_exp/`, fora do repo); inspeção `ps`/`/proc` pós-execução.
- Cenários testados: timeout; worker morto (`os._exit(1)`); erro estruturado; sucesso; loop de
  5; SIGKILL do pai; CF-02 (timeout do `subprocess.run`).
- Processos órfãos reproduzidos: **sim, apenas no cenário sintético de SIGKILL**
  (duração = trabalho restante do worker, auto-terminantes, 0 resíduos). Em condições normais
  de falha/timeout do lifecycle: **nenhum**.

## Riscos residuais

1. Worker órfão pós-SIGKILL vive até o fim do seu fetch (bound por timeout da lib); se a lib
   travar sem timeout efetivo, o órfão poderia persistir — sem evidência atual; sinal de
   monitoramento: fetch de duração anômala no health/JSONL.
2. Escrita tardia do cache de geocoding por worker órfão (idempotente; benigna).