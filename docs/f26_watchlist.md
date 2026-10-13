# F26 — Watchlist re-derivada: o radar F13 estava cego para 7 do top-20

Data: 13/10/2026 · Branch: `feature/f26-watchlist` · Base: main `c720514` (F24)

## 1. Problema

O radar 🎯 do digest (F13) cruza as vagas NOVAS de ontem (diff de IDs da F11)
com `config/company_watchlist.json` — match casefold por string EXATA de
`company` como aparece no dataset. O radar só alerta o que está na lista.

A watchlist foi derivada na medição de 2026-10-06 (2.416 eligible) e nunca
re-derivada. Na medição de 2026-10-12 (783 eligible, 316 empresas, snapshot
`data/eligible_jobs.json` de 12/10 09:01–09:26 UTC), 7 das 20 empresas com
mais vagas NÃO estavam na lista — o radar as ignorava.

## 2. Medições (snapshot 12/10, 783 eligible)

Volume por empresa (`company` exata, Counter sobre o JSON real):

| # | Empresa (string exata) | Vol. | Na watchlist? |
|---|---|---|---|
| 1 | `lidlstiftup2` | 79 | sim |
| 2 | `BoschGroup` | 60 | sim |
| 3 | `BMW AG` | 40 | **AUSENTE** |
| 4 | `Robert Bosch GmbH` | 23 | sim |
| 5 | `Kraft Heinz` | 20 | **AUSENTE** |
| 6 | `trumpf` | 11 | sim |
| 7 | `Lidl Dienstleistung GmbH & Co. KG` | 11 | sim |
| 8 | `KPMG International Cooperative` | 10 | sim |
| 9 | `henkel` | 10 | **AUSENTE** |
| 10 | `Vetter Pharma-Fertigung GmbH & Co. KG` | 10 | sim |
| 11 | `Deutsche Börse AG` | 10 | sim |
| 12 | `AGCO` | 9 | sim |
| 13 | `Levio` | 8 | **AUSENTE** |
| 14 | `indiecampers` | 8 | **AUSENTE** |
| 15 | `GALERIA S.à r.l. & Co. KG Nordrhein-Westfalen - Verwaltung` | 8 | **AUSENTE** |
| 16 | `AUMOVIO SE Haupverwaltung` | 7 | sim |
| 17 | `Exclusive Associates` | 7 | **AUSENTE** |
| 18 | `Würth Group` | 6 | sim |
| 19 | `SAP` | 6 | sim |
| 20 | `careers.dhl.com` | 6 | sim |
| 21 | `Amazon` | 6 | **AUSENTE** |
| 22 | `mllerservi` | 6 | sim |
| 23 | `Vanderlande` | 5 | **AUSENTE** |
| 28 | `www.careers.philips.com` | 5 | **AUSENTE** |
| 29 | `Google` | 5 | **AUSENTE** |

Demais ausentes do top-30 sem volume relevante: `JACOBSDOUWEEGBERTS` (4 vagas,
abaixo do corte de >=5 do card) — não adicionado nesta onda.

## 3. Critério F13 (preservado)

Empresas visa_friendly da curadoria (F9/F10) priorizadas por volume eligible +
nicho do dono (procurement/supply chain/data/materiais). As adições seguem a
mesma lógica: prioridade para as 7 cegas do top-20 (volume eligible dominante)
e, entre as demais ausentes do top-30, apenas as com >=5 vagas.

## 4. Adições (11 strings exatas, copiadas do dataset real)

Onda ADITIVA: nenhuma entrada existente foi removida (remoção = decisão do
dono). Todas as strings conferem byte a byte com o campo `company` do JSON
real (casefold exato — regra do arquivo).

| Empresa (string exata) | Vol. | Motivo |
|---|---|---|
| `BMW AG` | 40 | **nicho** — 21/40 vagas com títulos procurement/logistik/einkauf (Direkter Einkauf, Inbound Logistik, Containermanagement); maior ausente do top-20. Curadoria: visa_policy `not_verified`. |
| `Kraft Heinz` | 20 | **nicho** — 4 títulos procurement/supply/logistics (Procurement Finance, Supply chain & Logistics, Logistics & Inventory). |
| `henkel` | 10 | **nicho** — 3 títulos procurement (Procurement Digital, Procurement of Contract Manufacturing, Supply Chain Europe). |
| `Levio` | 8 | **nicho** — 2 títulos (Logistics, Digital Supply Chain Management). |
| `indiecampers` | 8 | volume (top-14), mas nicho 0 e sem curadoria — monitorar; Erasmus+ nos títulos. |
| `GALERIA S.à r.l. & Co. KG Nordrhein-Westfalen - Verwaltung` | 8 | volume (top-15). String artificial de ATS (8x "Aushilfe") — sinal de ruído, mas volume real de vagas novas diárias (7 das 13 novas de 12/10 eram da GALERIA). |
| `Exclusive Associates` | 7 | volume (top-17). Nicho aparente é ruído: "Sourcing" = recruiting/talent, NÃO procurement — documentado, não motivo de inclusão. |
| `Amazon` | 6 | **visa** — curadoria: `Amazon EU S.à r.l.` com visa_policy `unclear`; 6/6 vagas marcadas visa_friendly no dataset. |
| `Vanderlande` | 5 | volume (top-23) — warehouse automation, adjacente a supply chain; sem curadoria. |
| `www.careers.philips.com` | 5 | **visa** — curadoria: `Philips Germany` visa_policy `unclear`; 5/5 vagas visa_friendly no dataset. |
| `Google` | 5 | volume (top-29), data-center/tech; sem curadoria. |

## 5. Efeito comprovado (funções reais do radar, snapshot real)

Par usado: `current` = snapshot 12/10 (783 vagas) vs `previous` = archive
`20261012T090001Z` (779 vagas, coleta de 11/10) — o mesmo par que o digest
diário usou. Funções reais de `scripts/ranking_digest.py`:
`new_since_previous` → `radar_events` → `radar_lines`.

Diff de IDs: **13 vagas novas**. Eventos de radar:

| | ANTES (56 empresas) | DEPOIS (67 empresas) |
|---|---|---|
| Eventos 🎯 | 2 | 11 |
| Cobertura top-20 | 13/20 | **20/20** |
| Cobertura top-30 | 18/30 | **29/30** |
| Vagas do top-30 cobertas | 274 | **396** (de 400) |

Saída real de `radar_lines` DEPOIS (cap 5 + colapso):

```
🎯 Empresas-alvo (watchlist) — vagas novas de ontem nas empresas que você acompanha — 11 nova(s)
  🎯 1. BASF SE: Praktikant:in Global HR Reporting & Campaign Support (m/w/d) (Berlin)
  🎯 2. Kraft Heinz: Logistics Finance Intern (Amsterdam)
  🎯 3. Fraunhofer-Gesellschaft: Studentische Hilfskraft Software Entwicklung für autonome u… (Hamburg)
  🎯 4. Kraft Heinz: Sustainability, Risk & Resilience Intern (Amsterdam)
  🎯 5. GALERIA S.à r.l. & Co. KG Nordrhein-Westfalen - Verwaltung: Aushilfe (w/m/d) (44791 Bochum)
  (+6 outras — ver página)
```

Das 13 vagas novas de ontem, 9 deixaram de ser invisíveis (7 da GALERIA + 2 da
Kraft Heinz). As demais adições (BMW AG, henkel, Amazon etc.) não tinham vagas
novas NAQUELE dia, mas disparam no dia em que tiverem — é o design do radar.

## 6. Mudanças

**Alterado:** `config/company_watchlist.json` — `companies` 56 → 67 (+11
strings exatas) e `_comment` com a data da nova medição (2026-10-12).

**Criado:** `docs/f26_watchlist.md` — este relatório.

**Inalterados por design:** código-fonte, `company_intel/`, `MASTER_PLAN.md`,
`PROJECT_STATUS.md`, `data/` (produção; snapshot lido via cópia read-only em
/tmp). Nenhum dado de `data/` foi commitado.

## 7. Observações para o dono (fora do escopo deste PR)

- `indiecampers`, `GALERIA` e `Exclusive Associates` têm nicho 0 em
  procurement — estão na lista por volume. Se o ruído de "Aushilfe" da GALERIA
  encher o radar, remoção é decisão sua (ondas futuras são aditivas por padrão).
- `JACOBSDOUWEEGBERTS` (4 vagas) ficou fora pelo corte >=5; primeira ausente
  futura a reavaliar.
- Curadoria F9/F10 não cobre Kraft Heinz, henkel, Levio, indiecampers, GALERIA,
  Exclusive Associates, Vanderlande, Google — o campo visa dessas empresas é
  desconhecido (dataset marca 0 visa_friendly).
