# REGISTRO DE AVALIAÇÕES DE VAGAS — Outubro 2026
**Candidato:** Vinicius Pereira Rios · **Projeto:** internship-finder (pipeline próprio) · **Gerado:** 18.10.2026
**Fontes:** ranking próprio (rios-vini.github.io/internship-finder) + LinkedIn (vagas fora do ranking)
**Propósito:** documento de feedback — cada vaga avaliada é uma **linha rotulada** (aceita/recusada + motivo). É o dataset de treino para melhorar o pipeline: extração de requisitos, filtros de idioma/visto/duração e pesos do score.

**Vereditos:** ENVIADA (aplicação enviada) · PREPARADA (pacote pronto, aguardando envio) · PENDENTE (decisão do dono pendente) · ELIMINADA (recusada na triagem) · DUP (re-postagem de vaga já no funil)

**Regras de honestidade aplicadas em todas:** alemão A1–A2 (nunca "fluent"); Forage = simulações de trabalho virtuais; sistema de ranking = "designed and directed"; patente = não-inventor; "5M+" = enquadramento do dataset upstream; dogfooding ("I found this posting through my own daily job-ranking system") **só quando a vaga veio do ranking próprio**.

---

## 13/10/2026 — Top-5 do ranking (primeiro lote DE)

| Vaga | ID | Score | Veredito | Motivo | Sinal p/ o pipeline |
|---|---|---|---|---|---|
| adidas Global Procurement (Herzogenaurach) | SF 1442838433 | 11.5 (#19) | **ENVIADA 13/10** | Pflichtpraktikum explícito, €1.930/mês, inglês, procurement global = eixo central. Dogfooding VERDADEIRO. | Vaga de alta qualidade confirmada pelo score; sem bloqueios. |
| Würth Logistik/Import-Beschaffung (Bad Mergentheim) | SF 1439347933 | 13.5 (#2) | **PREPARADA 13/10 → ENVIADA 17/10** | Melhor encaixe temático (import procurement + logística), alemão NÃO exigido (badge data-de="none" correto). Dogfooding VERDADEIRO. | Extração de idioma correta neste caso (SuccessFactors). |
| TRUMPF Controlling & Business Analytics (Ditzingen) | Workday R00043505 | 13.0 (#3) | **PREPARADA 13/10 → ENVIADA 17/10** | Pflichtpraktikum OU freiwilliges aceitos, Power BI/Python, SS 2027. Dogfooding VERDADEIRO. | Workday como fonte funciona bem. |
| Lidl Controlling SAP BI | SF 1436050633 (Ref 747147) | 12.5 (#4) | **PREPARADA 13/10 → PENDENTE** | ⚠ "Ab sofort für 6 Monate" (início imediato) conflita com jan/2027 + Notenspiegel obrigatório. Decisão do dono pendente. | **FALHA:** "ab sofort" não detectado como conflito de data de início. |
| B.Braun Prozessoptimierung im Einkauf (Melsungen) | SF 1171013101 (Req 2767) | 12.0 (#5) | **PREPARADA 13/10 → ENVIADA 17/10** | Procurement + processos = eixo; data "01.04.2025" é rolling/stale, não bloqueio. Dogfooding VERDADEIRO. | Datas stale em postings não devem penalizar demais. |
| KPMG Data Science / Data Analytics & BI | SF 927796101 | 14.0 | **ELIMINADA** | "Sehr gute Deutschkenntnisse" (C1) = bloqueio de idioma. | **FALHA GRAVE:** score 14.0 mas requisito de alemão C1 não extraído → passou no filtro f-de. |

## 14/10/2026 — Refresh do ranking: Bosch Ansbach entra no Top-5 (no lugar da KPMG)

| Vaga | ID | Score | Veredito | Motivo | Sinal p/ o pipeline |
|---|---|---|---|---|---|
| Bosch Beschaffungsplanung Logistik (Ansbach) | SR 744000147439805 (REF295648Q) | 14.7 | **PREPARADA 14/10 → ENVIADA 17/10** | "NUR Pflichtpraktikum Bachelor" = perfeito p/ estágio obrigatório; "deutsch, englisch" sem nível declarado. Dogfooding VERDADEIRO. | Postings "NUR Pflichtpraktikum" são sinal de alta qualidade — considerar boost. |
| (Würth, TRUMPF, B.Braun — preparados 13/10, ver seção acima) | — | — | PREPARADAS | Cartas datadas 14.10.2026; **envio efetivo 17/10** (ver seção 17/10). | — |

## 17/10/2026 — Envio dos lotes DE + Luxemburgo

| Vaga | ID | Score | Veredito | Motivo | Sinal p/ o pipeline |
|---|---|---|---|---|---|
| Lote DE: Würth, TRUMPF, B.Braun, Bosch Ansbach | ver 13–14/10 | — | **ENVIADAS 17/10** | Dossiês marcados "ENVIADA 17/10/2026 pelo dono (movida para `feitas\`)". | — |
| BCL EPCO Procurement Trainee (Lux) | ST-10/EPCO/2026 | n/a (LinkedIn) | **ENVIADA 17/10** | Melhor encaixe LU: procurement puro, deadline 15/11/2026 cumprido com folga. Sem dogfooding (LinkedIn). | Vagas com deadline explícito = priorizar cedo. |
| Utmost IT Procurement Intern (Lux) | utmost.bamboohr.com/806 | n/a | **ENVIADA 17/10** | Procurement + IT, encaixe razoável. Sem dogfooding. | BambooHR como fonte funciona. |
| Amazon BI Intern (Luxembourg) | Job ID 10557454 | n/a | **ENVIADA 17/10** | BI/data = eixo; risco = requisito formal de CS (MODERATE). CV variante LU. | Requisitos formais de graduação (CS) = campo a extrair. |
| Deutsche Börse/CFC Non-Financial Risk Intern | req 27313 (SuccessFactors) | n/a | **ENVIADA 17/10** | Pasta em feitas\, mas dossiê ainda diz "PREPARADA aguardando envio" — **texto stale, confirmar com dono**. | **PROCESSO:** status do dossiê deve ser atualizado ao mover pasta p/ feitas\. |
| Palana (Lux) | — | n/a | **ELIMINADA na triagem** | Eliminada na conversa, sem dossiê — **motivo não documentado** (ver lição). | **PROCESSO:** toda eliminação deve deixar registro do motivo. |

## 18/10/2026 — Lote Amazon-2 (LinkedIn) + as 21 do ranking

**Lote Amazon-2 (LinkedIn, sem dogfooding):**

| Vaga | ID | Score | Veredito | Motivo | Sinal p/ o pipeline |
|---|---|---|---|---|---|
| Amazon SCM Intern (Lux) | Job ID 10579255 | n/a | **PREPARADA 18/10** | STRONG — melhor encaixe SCM puro do lote (supply/demand, fluxo de bens, network capacity, Python plus). | — |
| Amazon Process Improvement Intern (Lux) | Job ID 10555845 | n/a | **PREPARADA 18/10 — MODERATE-GOOD** | Dados/IA/automação encaixa; ops de site é terreno novo. Exclusões honestas: Lean/Six Sigma/Minitab/Access. | — |
| Société Générale Trainee Junior PM | 26000M0G | n/a | **ELIMINADA** | "Advanced level of French and English" + início Nov/Dez 2026 (antes de jan/2027). | **FALHA:** requisito de francês + início antes de jan/2027 não detectados. |
| DB Intern IT Touchpoint | req 25802 | n/a | **ELIMINADA** | Helpdesk IT, fora do eixo procurement/SC/data; já existe candidatura DB melhor pendente. | — |

**As 21 do ranking (contabilidade completa: 5 aprovadas + 6 já no funil + 9 eliminadas + 1 dup):**

| Vaga | ID | Score | Veredito | Motivo | Sinal p/ o pipeline |
|---|---|---|---|---|---|
| Bosch Strategic Purchasing (Stuttgart-Feuerbach) | SR 744000155984519 | 14.9 (#3) | **PREPARADA 18/10** | "Very good English and basic German" = A1–A2 serve; procurement de serviços logísticos = EXCELLENT; contato Alexandre Khodr. Dogfooding VERDADEIRO. | 🆕 1d badge correto; twin arbeitsagentur REF298797V (#4, 14.9) = mesma vaga em outra fonte. |
| Vitesco Risk Management Purchasing (Regensburg) | SF 1372399957 (Req 42803) | 13.0 (#11) | **PREPARADA 18/10** | MS Office + Power BI + Python EXPLICITAMENTE exigidos = encaixe exato; fluency English sem alemão. Dogfooding VERDADEIRO. | Requisitos explícitos de ferramentas = alta qualidade de extração. |
| Lidl Controlling International BI | Ref 753618 (praktikum.info 13308134) | 9.0 (#111) | **PREPARADA 18/10** | Sem requisito de idioma; Power-BI wünschenswert; €1.300 Pflichtpraktikum; irmã BI Req Eng ELIMINADA por alemão C1. | Score baixo (9.0) mas vaga VÁLIDA — score ≠ validade. |
| Lidl Lieferantenentwicklung | praktikum.info 13308139 | 7.0 (#182) | **PREPARADA 18/10** | Supplier development = core dele; "Technik/Naturwissenschaften" encaixa Materiais DIRETO. Dogfooding VERDADEIRO. | Score baixo mas vaga válida — área "Technik/Naturwissenschaften" = fit Materiais. |
| Lidl Preismanagement Nonfood | praktikum.info 13355221 | 7.0 (#185) | **PREPARADA 18/10** | "Sehr gute Englischkenntnisse" = inglês, não alemão; Schnittstelle com Einkauf. Dogfooding VERDADEIRO. | Extração correta: "Englischkenntnisse" ≠ alemão. |
| Würth Logistik/Import (já aplicada) | SF 1439347933 | 15.0 (#2) | **JÁ NO FUNIL** | Enviada 17/10. | — |
| Würth IS twin (absolventa) | absolventa:13251590 | 13.5 (#8) | **JÁ NO FUNIL** | Mesma vaga Würth em outra fonte (absolventa). | Twin detection funcionou na análise manual. |
| Bosch Ansbach (já aplicada) | SR 744000147439805 | 14.7 (#5) | **JÁ NO FUNIL** | Enviada 17/10. | — |
| B.Braun (já aplicada) | SF 1171013101 | 13.5 (#7) | **JÁ NO FUNIL** | Enviada 17/10. | — |
| TRUMPF (já aplicada) | Workday R00043505 | 13.0 (#12) | **JÁ NO FUNIL** | Enviada 17/10. | — |
| Lidl SAP BI (já preparada) | SF 1436050633 | 13.0 (#13) | **JÁ NO FUNIL** | Preparada 13/10, pendente decisão "ab sofort". | — |
| KPMG Data Science & BI | SF 927796101 | 14.0 (#6) | **ELIMINADA** | Alemão C1 ("Sehr gute Deutschkenntnisse"). | **FALHA:** passou no filtro f-de — extração de idioma falhou nesta fonte. |
| MOLEQLAR | SF 13258677 | 13.5 | **ELIMINADA** | "Sehr gut Deutsch" exigido. | **FALHA:** passou no filtro f-de. |
| CANAL+ | SF 1373297557 | 13.0 | **ELIMINADA** | Francês exigido, fora dos 5 mercados-alvo. | **FALHA:** idioma francês não detectado. |
| Lidl BI Requirement Engineering | SF 13308116 | 9.0 | **ELIMINADA** | "Sehr gute Deutschkenntnisse" = bloqueio de idioma (irmã da BI 753618, aprovada). | **FALHA:** passou no filtro f-de — extração de idioma falhou. |
| Lidl Marketing Analytics International | SF 1437485233 / praktikum.info 13231269 | 11.0/9.0 | **ELIMINADA** | Marketing, fora do eixo procurement/SC/data. | Score alto (11.0) por área+6, mas off-axis — pesos de área podem superestimar. |
| MAHLE Lead-Buying Mechatronics | SF 1373497333 | 4.5 | **ELIMINADA** | "Ab sofort" + "Für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich" = bloqueio §16e primeira entrada. | **FALHA:** bloqueio de visto + início imediato não detectados. |
| BASF Global HR Reporting (Berlin) | SR 1445672433 | 6.5 | **ELIMINADA** | HR data, fit marginal, €850; SmartRecruiters 404 no fetch. | SmartRecruiters pode 404 — retry/fallback. |
| Fraunhofer Hamburg | SF 1444227733 | 5.5 | **ELIMINADA** | 12 meses > teto §16e (6 meses). | Badge ⏳ duração FUNCIONA (12 meses detectado). |
| Fraunhofer Kaiserslautern | SF 1446740233 | 6.5 | **ELIMINADA** | Student assistant ≠ Pflichtpraktikum (não satisfaz estágio obrigatório UFSCar). | "Student assistant" ≠ Pflichtpraktikum — campo a extrair. |
| Lidl SAP BI re-post | praktikum.info 13231277 | 11.0 | **DUP** | Re-postagem da vaga já preparada (1436050633), detectada na análise das 21. | Badge 🆕 re-exibe dups — dedup deve cobrir re-posts entre fontes. |

---

## RESUMO DOS SINAIS PARA O PIPELINE

**Falhas de extração (corrigir no pipeline):**
1. **Idioma (f-de):** KPMG C1, MOLEQLAR, Lidl BI Req Eng passaram no filtro "sem alemão exigido" apesar de exigirem alemão. A extração de requisito de idioma falha em parte das fontes (SuccessFactors em particular). É a falha mais grave — 3 falsos positivos.
2. **Bloqueio de visto:** "gültiger Aufenthaltstitel erforderlich" (MAHLE) não detectado como bloqueio §16e primeira entrada.
3. **Início imediato:** "ab sofort" (MAHLE, Lidl SAP BI) não detectado como conflito com jan/2027.
4. **Idioma francês:** CANAL+ exigia francês e a extração de idioma não sinalizou (a vaga já fica fora do filtro 🛂, mas o campo idioma segue faltando).
5. **Bug de salário:** LexisNexis R119275 "€17.200–€28.700/mês" = anual parseado como mensal.
6. **SmartRecruiters 404:** BASF — fetch falhou; retry/fallback necessário.

**O que funciona (não mexer):**
- Badge ⏳ duração (Fraunhofer HH 12 meses detectado corretamente).
- Badge 🛂 (Resmed 16.0 #1 corretamente SEM 🛂; CANAL+ sem 🛂).
- Dedup manual/twin detection (Würth×2, Bosch Strategic×2, Lidl SAP BI re-post).
- praktikum.info extrai conteúdo completo apesar do cookie wall.
- jobs.lidl/sti → jobs.lidl.de/rdr/jump-to-job/<id> redirect (re-fetch no target).

**Insight central:** score ≠ validade. KPMG 14.0 eliminada; Lidl Preis 7.0 aprovada. O score mede atratividade, não elegibilidade. **Extração estruturada de requisitos (idioma, visto, duração, início, tipo de vaga) vale mais do que tuning de pesos.**

**Lições de processo:**
- Toda eliminação deve deixar motivo documentado (Palana sem registro).
- Status do dossiê deve ser atualizado ao mover pasta p/ feitas\ (DB/CFC stale).
- Regra 9: pacotes datados 18.10.2026 só valem se enviados HOJE; senão re-datar + re-assinar via stamp_signature.py.
