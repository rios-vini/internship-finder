# REGISTRO DE CANDIDATURAS — reply-tracking + cadência + score 1–5 (F98)

> **Regra da casa (guardrail — ITEM 9 restrito):** `score_1_5` é o score
> **holístico do DONO** (5 dimensões, nunca média aritmética), preenchido à
> mão. **LLM/pipeline NUNCA decide ranking, veredito ou score 1–5** — o que o
> pipeline pode gerar é o EVIDENCE PACK (seção 3) com evidências por vaga.
> O score 0–10 interno do pipeline fica **INTOCADO**: é camada independente, e
> **nenhum threshold automático entra no funil**. Este registro é a triagem
> do dono, ao lado do pipeline — não dentro dele.

## Como usar

- Uma linha por candidatura ENVIADA (seção 2) e uma por vaga em triagem (seção 1).
- Datas em `AAAA-MM-DD` (ou `DD/MM/AAAA`). Campos vazios são permitidos nas
  colunas opcionais (`id_fonte`, `resposta`, `score_1_5`, `verdict`, `nota`).
- `status` ∈ `Sent` `Interview` `Offer` `Rejected` `Responded` (qualquer caixa).
- Cadência (calculada só para `Sent`, a partir de `enviada`):
  `+7d` nudge 👋 · `+14d` ping 🏓 · `+28d` encerra ⏹.
- Rejeição company-wide: uma linha `Rejected` ativa o **guard de 30 dias por
  empresa** — aplicar na mesma empresa logo após uma rejeição é ruído, mas o
  guard **vence**: rejeição antiga **não** é bloqueio eterno (rejeição sem
  `resposta` usa a data de `enviada` como base do guard).
- Ferramenta (SOMENTE-LEITURA — ela aponta, nunca edita este arquivo):

```
python3 scripts/reply_tracking.py --registro <este-arquivo> [--today AAAA-MM-DD]
python3 scripts/reply_tracking.py --init [--registro <caminho>]
```

## 1) TRIAGEM — score 1–5 do dono (preenchido ANTES de aplicar)

| empresa | vaga | id_fonte | score_1_5 | verdict | notas |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

### Rubrica holística (5 dimensões — o dono pondera, não soma)

1. **Match CV** — citar linhas exatas do CV que casam com a vaga (e as que faltam).
2. **North-star** — a vaga anda na direção da carreira-alvo (procurement/supply na Alemanha)?
3. **Comp** — Glassdoor/Levels quando disponível; senão, o que o anúncio diz.
4. **Sinais culturais** — tamanho, idioma de trabalho, time, produtos.
5. **Red flags** — só negativos (não cancelam as outras dimensões; ponderar).

### Escala do veredito (derivação automática do score — aritmética, não LLM)

| score | verdict |
|---|---|
| ≥ 4.5 | **APLICAR** — aplica já |
| 4.0–4.4 | **VALE** — vale aplicar |
| 3.5–3.9 | **OVERRIDE** — só com ordem explícita do dono |
| < 3.5 | **CONTRA** |

## 2) CANDIDATURAS ENVIADAS — reply-tracking + cadência

| enviada | empresa | vaga | id_fonte | status | resposta | score_1_5 | nota |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

## 3) EVIDENCE PACK — por vaga (o pipeline PODE preencher; o DONO pontua)

### <vaga> — <id_fonte>

- **Match CV:** <linha exata do CV> ↔ <linha exata do anúncio>
- **North-star:** <por que esta vaga anda na direção>
- **Comp:** <Glassdoor/Levels/anúncio>
- **Sinais culturais:** <tamanho, idioma, time>
- **Red flags:** <negativos, se houver>

> ITEM 13 (patterns de rejeição com ~30 datapoints) fica ADIADO até o
> registro ter massa de dados — não preencher à força.
