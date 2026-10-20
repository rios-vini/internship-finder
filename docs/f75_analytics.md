# F75 — Analítica: matriz provider×descrição + drift do funil + retenção + gêmeos residuais

Quatro instrumentos de medida **offline**, sem mudar comportamento do funil
(spec: `~/.hermes/handoff/f75-analitica/ESPECIFICACAO.md`; roadmap v5,
doc original F74). Medir primeiro, decidir depois.

## 1. Matriz provider×descrição (`scripts/provider_description_matrix.py`)

Cobertura de `description` (presença/qualidade) por **ATS provider** sobre o
elegível publicado. Provider = ATS efetivo do `source` pela MESMA regra da
hidratação (`hydration._effective_ats`: `sf_dataset:successfactors` →
`successfactors`, `direct:eures` → `eures`, `ats:slug` → `ats`).

Colunas por provider: vagas · com description · cobertura % · mediana de
comprimento (das presentes) · curtas (< 500 chars — a MESMA régua do
`HYDRATION_SHORT_LIMIT` do refresh, pinada em teste) · provenance
(`description_source`: feed/hydration).

Uso (offline, determinístico, só lê):

```bash
python scripts/provider_description_matrix.py                    # texto
python scripts/provider_description_matrix.py --json            # estruturado
python scripts/provider_description_matrix.py --input data/eligible_jobs.json
```

Exit 1 quando não há vagas legíveis. Números da produção (run 19/10) no
relatório da fase.

## 2. Drift do funil no digest (linha 📈 da seção 📅)

A linha `📈` do digest agora mostra a variação semanal **por estágio** —
último run vs o de 7 runs atrás, nos três campos já registrados no record
`type: run`:

```
📈 drift 7 runs: brutas 108059 (+59) · pré-filtrado 3121 (+21) · mantido 871 (+92)
```

Implementação: `funnel_report.weekly_stage_drift()` (generalização do
`weekly_trend`, que media só o eligible) → `build_report()["drift"]` →
`ranking_digest.funnel_seasonality_lines()`. Reports legados sem o campo
`drift` continuam renderizando o formato antigo (`elegíveis: X hoje vs Y`).
Estágio com campo ausente em qualquer lado fica FORA da linha (nunca
inventado).

## 3. Retenção do `collection_metrics.jsonl` (`internship_finder.metrics_retention`)

O JSONL de métricas crescia sem retenção (âncora 19/10: 1,87 MB, ~5,3k
registros). A partir da F75 o refresh executa em runtime (passo 1c, ANTES do
snapshot de linhas e da coleta — **nunca hand-edit**):

- **dentro do corte**: registros RAW, byte a byte;
- **além do corte**: um registro `type: metrics_rollup` POR DIA, com
  contagem por `type` e somas dos campos numéricos POR type
  (`tenant.collected` e `run.total_collected` não se misturam);
- corrompido/sem timestamp: preservado RAW (nunca destrói);
- idempotente (2ª execução = no-op) e atômico (`tmp` + `os.replace`);
- falha NUNCA derruba o run (best-effort, como o backup do jobs.db).

**Default: 90 dias** (documentado; o dono ajusta):
`refresh_daily.py --metrics-retention-days N` (`0` desliga). O RAW completo
de cada dia cortado segue no snapshot `data/archive/<ts>/` daquele dia
(pelo prazo usual do `--retention-days` do archive).

Efeito nos consumidores: o health compara contra a janela viva (≤90d);
drift/trend semanais (janela 7) não mudam.

## 4. Gêmeos residuais no digest (linha 👯 / ⚠️)

Contagem read-only de **grupos cross-source sobreviventes**: mesma empresa
(string exata, casefold) + mesmo título (chave DE/EN do dedup —
`_de_en_title_key`, uma fonte de verdade) em duas ou mais fontes distintas.
Agrupamento inspirado no `cross_source_dedup` (F48), mas sem fusão: MEDE o
que o guardrail conservador mantém — a chave empresa+título enxerga gêmeos
que uma chave por cidade não pode ver (twin com `location` ausente de um
lado, ex. absolventa). Âncora 19/10 (725 elegíveis): **10 grupos** = 8
Amazon (absolventa×amazon_jobs, loc ausente) + 1 Würth (absolventa×BA) +
1 Boston Scientific (sf×sf, cidades divergentes) — reproduzida ao vivo no
relatório da fase e estável na transição do dedup F66.

No digest (antes do 🔗): `0` = linha ausente; `1..20` = informativa 👯;
`>20` = **ALERTA ⚠️ "revisar dedup (F48)"** — que sobrevive ao compact do
Telegram (extraído por prefixo, padrão F44; a linha normal segue o destino
das demais medições).

## Testes

`scripts/test_f75.py` (113ª suíte do CI, auto-descoberta F78): 85 checks
offline — matriz (provider/números/ordem/CLI/determinismo/pin da régua),
drift (por estágio, janela, campos ausentes, legado, sinais), retenção
(corte, shape, byte-a-byte, idempotência, corrompidos, off, atômico,
wiring), gêmeos (shapes reais + negativos verbatim, linha, alerta,
extrator, compact) e zero-rede. `test_f45` atualizado com a mudança de
contrato da linha 📈 (comentário F75).
