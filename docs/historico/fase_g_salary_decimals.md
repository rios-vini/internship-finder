# Fase G — Correção do parsing de decimais em salários textuais

**Data:** 29/09/2026 · **Spec do dono:** Fase G — Salary Decimal Parsing Fix ·
**Escopo:** cirúrgico, determinístico, sem LLM.

Corrige o bug pré-existente do `_MONEY_CLAUSE` documentado como backlog na
Fase F (decisão do dono 29/09): valores alemães com decimal (`€17,50`) eram
capturados como `17` (truncado) ou, pior, o fragmento pós-vírgula virava um
salário-lixo (`17,50 Euro` → 50 €/mês; `17,80 €/Stunde` → 80 €/mês).
**Nada** fora de salary muda: ranking/eligibility/dedup/cron intocados (o
ranking não consome salary — `ranking.py` não referencia o campo).

## O bug (causa-raiz)

O grupo numérico do `_MONEY_CLAUSE` era uma alternância ORDENADA:

```
\d{1,3}(?:[.,]\d{3})*   |   \d+(?:[.,]\d+)?
```

Para `17,50`, a 1ª alternativa casa `17` (o `*` aceita zero grupos de
milhar) e o engine **nunca tenta** a 2ª — o `,50` sobrava como um SEGUNDO
match `50` que, com moeda/rotulo na janela, passava o gate e virava o
"salário" da vaga. O `_to_number` tinha o bug irmão: `17.50` → `1750`
(pontos removidos como se fossem milhar) e `50,000.00` → `50`.

## A correção (menor alteração possível — 2 regex + docstring)

**`_MONEY_CLAUSE`** — cada lado do range (grupos `a`/`b`):

```
\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?   |   \d+(?:[.,]\d{1,2})?
```

1. **Milhar + decimal final opcional** (`+` = PELO MENOS um grupo de
   milhar): `2.117`, `2,000`, `1.400,50`, `1,400.50`, `2.410,00`,
   `50,000.00`. O `+` é o detalhe crítico: com `*`, `2117` casaria `211` na
   1ª alternativa (regressão); exigindo milhar, números sem separador caem
   inteiros na alternativa 2.
2. **Número simples com decimal de 1–2 dígitos**: `17,50`, `18,06`,
   `17.50`, `3,5`, `17`, `2117`.

Decimal limitado a **2 dígitos** nas duas alternativas: `3,500` (vírgula +
3 dígitos) continua lido como MILHAR — regra conservadora pré-existente,
nunca alterada (distinguir `1,400`=milhar de `1,40`=decimal por lookahead
agressivo seria parser universal, fora do escopo).

**`_to_number`** — regras da mais para a menos específica:

| token | regra | resultado |
|---|---|---|
| `1.400,50` / `1,400.50` | milhar + decimal final (último separador = decimal) | 1400.50 |
| `2.117` / `2,000` / `50,000` | milhar puro (como antes) | 2117 / 2000 / 50000 |
| `17,50` / `17.50` / `1,5` | separador único = decimal | 17.5 / 17.5 / 1.5 |
| `2117` / `17` | sem separador | 2117 / 17 |
| `1.10.2026` (data) | não reconhecido | None (conservador) |

Guard `> 0` preservado (`0`/`00` → None — era o que impedia o fragmento
`00 €` de virar salário no teampicnic `2.410,00`).

## O que NÃO mudou

- Gate moeda+rotulo±periodo, `has_period`/`best` preference, hourly da Fase
  F (`_is_hourly_clause` + guard de fragmento — agora latente para
  decimais reais, ativo para sufixos numéricos), structured recruitee
  (precedência), period default `month`, ranges `–`, currency `currency`.
- `€50,000/year` continua **month** (pré-existente): o period group não
  captura `/year` — documentado como limitação, fora do escopo desta fase.
- UI (`interface.py` `euro()`): formata `{v:,.0f}` — decimais não aparecem
  no card Salary, mas a linha "Source: job posting — citação exata" exibe o
  texto original (`17,80 €/Stunde`) como evidência. Display de decimais na
  UI fica como limitação de apresentação (o valor interno `min`/`max` está
  correto e disponível para qualquer consumidor futuro).

## Antes → depois (casos reais do dataset)

| vaga (texto no anúncio) | antes | depois |
|---|---|---|
| VW `Vergütung: 17,80 €/Stunde` | **80 €/month** (lixo) | **17.80 €/hour** |
| VW `hourly wage of €17.50` | 17 €/hour (truncado) | **17.50 €/hour** |
| Fraunhofer `hourly rate: €18,06/hour` | 18 €/hour (truncado) | **18.06 €/hour** |
| teampicnic `gross hourly wage of €16,75` | 16 €/hour (truncado) | **16.75 €/hour** |
| teampicnic `2.410,00 €/Monat` | None (perdido) | **2410.00 €/month** |
| teampicnic `1.000,00 €/Monat` | None (perdido) | **1000.00 €/month** |

## Testes

- `scripts/test_faseg.py` NOVO: 68 checks offline (grupos A–G da spec).
- `scripts/test_fasef.py` P2.3 EVOLUÍDO: o guard pré-Fase G protegia o
  comportamento do bug ("fragmento não rotulado hourly" porque era lixo
  `80€/month`); pós-Fase G o valor E o período estão corretos — o check
  afirma o comportamento novo (17.80/hour), contagem 74 preservada.
- CI: array 42→43 (`test_faseg`).
