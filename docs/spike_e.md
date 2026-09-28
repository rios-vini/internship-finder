# Fase E — LLM Enrichment Spike (isolada)

Spike CONTROLADA que mede quanto conhecimento novo e confiável um LLM
extrai de texto JÁ COLETADO quando os detectores determinísticos não
resolvem. O pipeline determinístico permanece a AUTORIDADE para
descoberta/eligibility/dedup/ranking/filtros — o LLM NÃO entra no
pipeline oficial, não altera score/pesos/Top 30/cron/Telegram/jobs.db.

## O que é

Pacote isolado `src/internship_finder/spike_e/`:

- `schema.py` — `SpikeERecord` (pydantic, enums EXATOS da spec §7-A–F:
  WA 8 estados, idiomas required/preferred/not_required/not_mentioned/
  unclear, deadline com kind, salary min/max/currency/period, student com
  subtipos). Validação ESTRITA: valor fora do enum → campo rejeitado com
  erro registrado (`field_errors`), nunca fallback heurístico. Evidence
  ≤200 chars obrigatória em estado informativo (§8); confidence
  high/medium/low (§9). Guardas determinísticas pós-LLM (defense in
  depth): condicionais (ggf./if applicable) nunca `explicit_support`;
  DEI genérico e "international environment" sem vocabulário de aceitação
  nunca `international_candidates_accepted`; relocation-only e
  "already hold a permit" nunca sponsorship (confusões nomeadas na spec).
- `sample.py` — amostra estratificada DETERMINÍSTICA (seed 20260928):
  10 WA-gap (desc normalizada >1500, maiores textos reais) + 5 phenom
  teaser + 5 official-page problem (js_rendered) + 5 condicionais §18 +
  5 controle (WA informativo, random com seed). Um job entra em UM
  bucket (prioridade a>b>c>d>e).
- `input_builder.py` — input do LLM por prioridade (§6): description
  normalizada (`app_intel.normalize_text` — spec §6: nunca HTML bruto;
  teaser <400 usa JSON-LD description quando existe) + structured fields
  rotulados + bloco `official_page` COMO CONTEXTO MARCADO (§12:
  js_rendered/teaser com instrução explícita de NÃO inferir conteúdo).
  Cap 12k chars; truncagem registrada. O MESMO texto fica no record
  (reprodutibilidade do manual review §17).
- `prompt.py` — prompt curto extração-puro (§13) com as distinções da
  spec e few-shots condicional/DEI (adaptados do enrichment v1); schema
  JSON exato embutido; temperature 0; zero instruções de ranking.
- `compare.py` — relations §11 por campo (agree / llm_adds_information /
  conflict / deterministic_missing / llm_missing), computadas contra o
  determinístico RODADO NA SPIKE (funções puras de `app_intel`/
  `opportunity_intel` sobre a MESMA amostra). Conflito NUNCA é resolvido
  automaticamente.
- `runner.py` — batch sequencial (§14): reusa o cliente
  `enrichment.llm.extract` (3 tentativas, backoff 30/60s, `_sanitize`);
  erro por job não interrompe; aborto automático >50% de falha nos
  primeiros 10; records JSONL incremental com skip-if-done (resume).
  Transport injetável (testes offline: FakeTransport, zero rede).

Script CLI: `scripts/spike_e_run.py` (`--plan` zero LLM / `--run` real /
`--analyze` comparação §16). Testes: `scripts/test_spike_e.py` (15 grupos
da spec §21, 100% offline, fixtures sintéticas) — no array do CI.

## Como rodar

    # amostra + inputs + baseline determinístico (zero LLM):
    .venv/bin/python scripts/spike_e_run.py --plan
    # batch real (1 chamada LLM/job, sequencial):
    .venv/bin/python scripts/spike_e_run.py --run
    # comparação det×LLM + tabelas + flags de evidência não encontrada:
    .venv/bin/python scripts/spike_e_run.py --analyze

Inputs: dataset em `/tmp/if-fasee-data/eligible_jobs.json` (read-only) e
`NVIDIA_API_KEY` em `/tmp/if-fasee-data/env` (nunca em código/artefato).

## Artefatos (FORA do repo — contêm dados de vagas, nunca commitados)

    /tmp/if-fasee-artifacts/
      sample.json                  # 30 ids + buckets + motivos + desvios
      baseline_deterministic.json  # lado det computado NA spike (§11)
      records/spike_records.jsonl  # 1 record/job (input + extração + meta)
      records/plan_inputs.jsonl    # inputs montados (auditabilidade)
      run_manifest.json            # modelo, tokens, latências, ok/erro
      analysis/comparison.json|md  # tabelas det×LLM por campo (§16)
      manual_review/               # vereditos da revisão manual (§17)

## Limitações (honestas)

- n=30, UMA amostra, UM modelo (glm-5.3-flash), UMA janela da API
  (28/09, com timeouts em rajada). NÃO generalizar.
- O LLM lê o mesmo texto truncado (cap 12k) — menções na cauda cortada
  ficam invisíveis para ele (o determinístico lê o texto completo).
- `llm_adds_information` é evidência-CANDIDATA, nunca verdade canônica;
  conflitos com o determinístico são REGISTRADOS, não resolvidos.
- Records de erro (timeout/parse) contam como falha de extração, não
  como "sem informação" — a taxa de erro faz parte do custo medido.

## NÃO-integração

Esta spike NÃO integra nada: nenhum módulo existente importa `spike_e/`,
`spike_e/` nunca importa `ranking`/`filters`/`dedup`, e nenhum artefato
vira campo canônico de `Job`/jobs.db/eligible_jobs/Pages. A decisão de
integrar (A/B/C/D da spec §23) é POSTERIOR e baseada nos números do
relatório da spike.
