# F29 — Sinais de candidatura no display (duração §16e, estimativa salarial rotulada, idade, red-flags, countdown visto)

**Data:** 2026-10-13 · **Branch:** `feature/f29-application-signals` (base: `feature/f25-backlog-reassessment` `5e3acf7`, PR #123 aberto — empilhamento precedente F4/F5) · **PR aberto, SEM merge (merge é do dono).**

Camada INFORMATIVA de display: NADA entra em score/eligibility/filters/ranking. Superfícies: página minimal (`scripts/minimal_page.py`) e digest Telegram (`scripts/ranking_digest.py`).

## Componentes

1. **`config/salary_benchmark.json`** (curado, versionado; padrão `employer_quality.json`): categorias `pflichtpraktikum` (Ø ~€1.021/mês, praktikum.info), `praktikum` (Ø ~€1.507/mês, praktikum.info), `werkstudent` (14–17 €/h, kununu Ø ~€2.400/mês FTE + Indeed Bayern Ø 17,46 €/h), `mindestlohn_2026` (€13,90/h, meinpraktikum.de/absolventa.de). Cada valor com `source_url` + `checked` (2026-10-12, pesquisa do brainstorm). Loader tolerante (`src/internship_finder/salary_benchmark.py`): ausente/corrompido → `{}` → sem badge, nunca erro.
2. **Flag duração §16e**: `opportunity_intel.job_duration` (detector existente) com `min > 6` → badge "duração N meses — acima do teto §16e (6 meses)". Faixa "6–12 Monate" NÃO flaga (começa dentro do teto — honestidade do sinal).
3. **Badge idade**: com `posted_at` → "postada há N dias" (>45d: forma completa + classe discreta `age-stale`); ≤45d mantém o "há Nd" curto da F11 (contrato preservado). >90d NÃO gera sinal extra (coberto pelo mesmo badge — item 4c).
4. **Red-flags determinísticas (badge, nunca exclusão)**: (a) "exige matrícula em universidade alemã" — padrões DE/EN (Einschreibung/Studium an einer deutschen Hochschule, enrolled at a German university) em título+descrição; (b) "remuneração não citada" quando `job_salary` ausente (honesto, sem acusação); c vaga com `posted_at` >90d já coberta pelo badge de idade.
5. **Estimativa salarial ROTULADA** — REGRA INVIOLÁVEL: JAMAIS funde com o salário detectado. Quando `job_salary` existe: SÓ o detectado. Quando ausente E categoria derivável do título (werkstudent vs praktikum/pflichtpraktikum — precedência pflicht > praktikum): linha "estimativa de mercado: ~X (fonte, MM/AAAA)". No HTML o card usa `if salary … elif estimate … elif não-citada` — a separação é estrutural (elif), não convencional.
6. **Countdown visto** (digest): 1 linha antes do ⚡ Top 5 — "📅 Visto §16e: oferta necessária até ~15/11/2026 p/ início jan/2027". Data DERIVADA de constantes (`VISA_TARGET_START=(2027,1,1)`, `VISA_LEAD_DAYS=47` ≈ meio da faixa 6–8 semanas da pesquisa 12/10), nunca hardcoded no texto.
7. **Frases jurídicas LITERAIS** (rodapé da página, definidas 1× nas constantes do módulo): "§16e: duração máxima 6 meses (AufenthG §16e Abs. 2)." e "Praktikum sob §16e NÃO exige Zustimmung da Bundesagentur für Arbeit (BeschV §15 Nr. 1) — confirmar procedimento atualizado com consulado/Ausländerbehörde."
8. **`scripts/test_f29.py`** (47 checks, 100% offline, 69ª suíte — CI array no mesmo commit): loader tolerante, estimativa sempre rotulada/nunca fundida (assert de separação), badges, countdown presente/ausente, frases literais (substring), byte budget <150KB, zero impacto (ids/scores/ordem idênticos com e sem benchmark; nenhum import de ranking/filters).

## A/B render — snapshot real (cópia em /tmp; `data/` de produção intocada)

Snapshot 13/10 pós-refresh (777 eligible; sha256 `7aec67d5…` — cópia em `/tmp/f29-ab/`):

| Métrica | before (F25, sem benchmark) | after (F29) |
|---|---|---|
| Tamanho da página | 95.084 bytes | **98.303 bytes** (< 150KB cap; +3.219 bytes) |
| Cards exibidos | 100 | **100 (idênticos)** |
| ids / scores / ordem | — | **idênticos ao before** (0 mudança) |
| Estimativa rotulada | 0 | **87 cards** |
| "remuneração não citada" | 90 | 3 (apenas as sem categoria derivável) |
| Idade >45d (age-stale) | 48 | 48 (>90d: 31, mesmo badge, sem sinal extra) |
| Duração >6m flag | 1 | 1 (top-100: "IT Procurement Internship – 12 months") |
| Matrícula universidade alemã | 1 | 1 ("Praktikum Business Analytics & Corporate Finance") |
| Linhas alteradas no diff | — | +87/−87 (exatamente os meta-bits salariais trocados) |

Universo inteiro (777): 57 com salário detectado (mostram SÓ o detectado), 693 com estimativa possível, 13 com duração citada >6 meses, 1 com exigência de matrícula alemã. Nota: a medição 12/10 (card) apontava 0 vagas >6m — hoje o sinal flaga 13 reais; o detector `job_duration` cobre pouco do universo, então 13 é piso.

Observação de baseline: idade >45d, rodapé jurídico, duração e matrícula já aparecem no "before" renderizado pela branch F29 com benchmark desligado — são código novo compartilhado entre before/after (o A/B isola APENAS o efeito do benchmark). O diff de +87/−87 linhas confirma: a ÚNICA mudança causada pelo benchmark é a troca "remuneração não citada" → "estimativa de mercado rotulada".

## Integração

- `publish_pages.render_ranking_html` passa `--salary-benchmark config/salary_benchmark.json` explícito (padrão F13/F15 de fixar contrato).
- `refresh_daily` não muda: `digest_sections` ganha o countdown por default (`visa_countdown=True`; `False` = regressão zero).
- Loader tolerante em TUDO: benchmark ausente/corrompido → sem estimativa, página/digest nunca quebram.

## Regras invioláveis respeitadas

- Estimativa JAMAIS funde com detectado (elif estrutural no card; teste A5/B6/B7).
- Frases jurídicas LITERAIS (constantes únicas; asserts de substring).
- Nada em score/eligibility/filters/ranking (teste I1/I2 — imports e idempotência de ids/scores).
- 100% offline; zero LLM; zero rede no build.
