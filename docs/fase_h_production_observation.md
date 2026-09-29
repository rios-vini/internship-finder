# Fase H — Production Observation & Data Quality Review (29/09/2026)

**Natureza:** fase de OBSERVAÇÃO E AUDITORIA. Nenhuma mudança funcional de código.
**Commit-base observado:** `main` = `e807c08` (Fase G) / docs `cfbeb24`. 0 PRs abertos.
**Ciclos observados:** run cron 2026-09-29T09:00:02Z (pós-Fase F) contra baseline imediato 2026-09-28T09:00:02Z (pré-F/G) e referência de variação natural 27/09 (412 eligible).

> **Enquadramento honesto (parcialmente observacional):** a Fase F (`a848006`) chegou à produção ~05:41 UTC de 29/09 — o ciclo das 09:00 UTC de hoje rodou **com F viva**. A Fase G (`e807c08`) chegou ~10:15 UTC, **depois** do ciclo — **ainda não existe ciclo pós-G real**. O efeito da G foi medido por reprojeção offline (mesmo dataset 29/09, código G) e pela evidência do HTML publicado. Primeiro ciclo pós-G real: 30/09 09:00 UTC. Marcado conforme spec §1.

---

## 1. Ciclo observado — 29/09 09:00 UTC (pós-F, pré-G)

| Métrica | Valor |
|---|---|
| run_id | `2026-09-29T09:00:02.445884+00:00` |
| Duração coleta+pipeline | 09:00:02 → 09:15:57 UTC (~15m55s) |
| Raw jobs | 72.229 |
| Filtro tipo/área | 425 filtered |
| Dedup (clássica + mirrors) | −16 → **409 eligible** |
| Fontes | 112 ok (72.229 vagas) · 10 sem vagas · 1 timeout · 4 erros |
| Exit code | 2 (parcial — gate `publication_allowed` publicou) |
| Alertas health | 7 (ver §10) |
| Publicação Pages | ✅ commit `06ae9e6` 09:16:08 UTC |
| Digest Telegram | ✅ ok:true (msg 489) — **ENCURTADO** (4096 chars: 7 alertas comprimiram o digest a 1 linha + link; comportamento documentado) |
| Hydration | 73/73 (100%), 56,9s; cobertura descriptions 336→409 |
| Official page | 150 GETs / 151,4s: 103 ok · 31 redirected · 13 js_rendered · 2 http_error · 1 empty |
| Enrichment LLM | 21 selecionadas (cap 24) → **0 ok / 21 ReadTimeout**, 42 retries, **20.275s (~5h38)**; 6 preservados; fim 14:54 UTC |
| Re-publicação pós-enrichment | idempotente — mesmo commit `06ae9e6` (HTML byte-idêntico, push condicional) |

**Baseline 28/09:** 72.338 raw → 404 eligible; 114 ok / 9 empty / 1 timeout / 3 erros; exit 2; 5 alertas; `d35068f`. **Referência 27/09:** 412 eligible.

### Contagens do ciclo (409 eligible, código F+G — o que a página renderiza)

| Campo | Valor |
|---|---|
| WA | existing_required **17** · support 0 · no_sponsorship 0 · unclear **59** · not_mentioned 333 |
| student_type | internship **201** · working_student **144** · mandatory **37** · voluntary 0 · unclear **27** · conflicts 0 |
| salary | month **29** · hour **2** · year 0 · period=None 1 (CURRENTA estruturado) · missing 377 |
| deadlines | platform_sf **231** (todas `2026-10-29` = feed+30d) · employer_textual **6** (Fraunhofer) · none 172 |
| descriptions | sem 0 · teaser ≤400 **29** (100% `phenom:nan`) · mediana 2.902 chars |
| official page (150) | ok 103 · redirected 31 · js_rendered 13 · http_error 2 · empty 1 |
| Top 30 | WA: 21 nm / 8 unclear / 1 existing · student: 21 internship / 5 ws / 3 mandatory / 1 unclear · salário em 6 · validThrough oficial 1 (informativo) |

---

## 2. Comparação com baseline (antes → depois → diferença → interpretação)

Causas: **A** código (F/G) · **B** novas vagas · **C** fontes/ATS · **D** variação natural.

### WA
| Snapshot × código | existing | unclear | not_mentioned |
|---|---|---|---|
| 28/09 dataset + pré-F/G (= publicado 28/09) | 66 | 5 | 333 |
| 29/09 dataset + pré-F/G (contrafactual) | 70 | 6 | 333 |
| 29/09 dataset + F (publicado hoje) | 17 | 59 | 333 |
| 29/09 dataset + F+G (renderiza amanhã) | 17 | 59 | 333 |

**Interpretação:** dataset neutro (70 vs 66 = B/D). Efeito **100% A**: a F moveu 53 vagas `existing_required`→`unclear` no MESMO dataset (70→17), quase todas condicionais "ggf./wenn vorliegend" Bosch/STIHL — exatamente o desenho da fase. `not_mentioned` estável. G não altera WA (confirmado coluna a coluna).

### student_type (campo novo da F)
Antes: inexistente → Depois: 201/144/37/0/27 (internship/working_student/mandatory/voluntary/unclear), 0 conflitos.
**Interpretação: A** — ganho integral da F. Os 27 unclear: 15 SHK Fraunhofer, 4 teses, 4 trainees (FPs de eligibility, §10), AIXTRON/zeiss/Uniper/ABB 4.

### Salary
| Versão de código (dataset 29/09 idêntico) | com salário | diffs de valor |
|---|---|---|
| pré-F/G | 28 (27 month + 1 None) | VW 80 €/mês (lixo); VW 33 €/mês ×2; roche 226 €/mês |
| F | 29 (+1 hour) | mesmos lixos |
| F+G | **32** (29 month + 2 hour + 1 None) | VW 17,80→**17,8/hour**; VW 18,33 (permanece month — §5); roche 226→**2268**; Bayer 2.280,00 ×2 novos; MAHLE **1500** novo |

**Interpretação: A.** A G corrige valores e ganha +3 salários no mesmo dataset; nenhum salário perdido (0 regressões — consistente com o A/B da Fase G). O HTML publicado HOJE ainda renderiza com F (ex.: `data-salary="80" data-salary-period="month"` no VW do rank 21): o processo do refresh carregou o código às 09:00, antes do merge da G; a re-publicação 14:54 é do mesmo processo (push condicional, mesmo commit). Os fixes da G aparecem publicamente no ciclo de 30/09.

### Deadlines / descriptions / idiomas
| Campo | 28/09 | 29/09 | Causa |
|---|---|---|---|
| platform_sf/textual/none | 225/6/173 | 231/6/172 | **B** (+6 SF novas; zero efeito de código) |
| descriptions sem/teaser | 0/29 | 0/29 | estável (hydration 100% ambos os dias) |
| german required/preferred/plus/none | 262/41/6/95 | 265/40/7/97 | **B/D** (F/G deliberadamente não tocam — backlog com root cause, §9) |
| english_evidence | 301 | 305 | **B/D** |

### Delta de conjunto 28→29 (B/C/D)
395 ficaram · 9 saíram · 14 entraram (VW +4 net, Fraunhofer +2, MAHLE +2, …). Rotina normal de churn. A ausência de SAP nas 3 janelas (0 vagas) é **C** — ver §10-G1.

---

## 3. Auditoria de WA

Distribuição pós-F (409): existing_required 17 · unclear 59 · not_mentioned 333 · support 0 · no_sponsorship 0.

### Os 17 `existing_required` restantes — composição por evidência
| Classe | n | Evidência textual (exemplo) |
|---|---|---|
| Condicionais NÃO-cobertas | 7 | Bosch ×5 "…and **if indicated** a valid work and residence permit"; continental ×2 "**Falls erforderlich**, zusätzlich: Gültiger Aufenthaltstitel Arbeitsgenehmigung inkl. Zusatzblatt" |
| Requisito por audiência não-EU | 7 | MAHLE ×6 "Für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich"; VW ×1 idem |
| Requisito genuíno | 3 | teampicnic "You have an **EU citizenship or valid working visa**" / "EU citizenship or valid EU working permit required" |

**Nota:** "if indicated"/"falls erforderlich" são a MESMA classe semântica que os condicionais corrigidos pela F ("if applicable"/"wenn vorliegend") — marcadores fora do vocab atual. Ganho determinístico futuro claro e seguro (7 casos hoje; 2 novos marcadores).

### Amostral dos 59 `unclear`
- **59/59 têm termo WA no texto** (nenhum `unclear` sem evidência — o estado é honesto).
- **53/59** = condicional explícita detectada ("wenn vorliegend Arbeitszeugnisse und deine gültige Arbeits- und Aufenthaltserlaubnis" — STIHL ×14, Bosch ×35, VW ×4): listas de documentos onde a permissão é pedida CONDICIONALMENTE.
- **5/59** = VW "Arbeitserlaubnis für Nicht-EU Bürgerinnen/Bürger" — condicional POR AUDIÊNCIA: o texto diz algo relevante para o candidato BR (não-EU precisa de permissão), mas não é "exigência incondicional". Correto como unclear; porém o texto é ACIONÁVEL para o Vinícius e a UI só mostra "incerto".
- **1/59** = celonis Field Marketing — "sponsorship opportunities across Germany…" (patrocínio de EVENTOS, FP conhecido e documentado).

**Pergunta central ("unclear é honesto ou existe lacuna determinística relevante?"):** honesto — 0/59 sem termo, 53/59 condicionais reais. Lacunas determinísticas identificadas: (a) 7 condicionais "if indicated"/"falls erforderlich" que hoje ficam `existing_required` (sobre-classificação, mesma classe da F); (b) consumo de evidência na UI para os 5 VW não-EU. Nenhuma exige LLM.

## 4. Auditoria de student_type

Distribuição: internship 201 · working_student 144 · mandatory 37 · voluntary 0 · unclear 27 · **conflitos 0**.

- Falsos positivos: **0** (amostral por subtipo auditada; guardas anti-FP da F confirmados em produção).
- Falsos negativos óbvios: **0** nos marcadores claros. Os 27 unclear são genuinamente ambiguos no texto: 15 "Studentische Hilfskraft" (SHK = HiWi, categoria própria não mapeada), 4 teses ("Masterarbeit/Abschlussarbeit"), 4 trainees (FPs de eligibility — §10), AIXTRON "Studentische Hilfskraft/ Werksstudent" (híbrido legítimo), zeiss "Abschlussarbeit", Uniper "Master's Thesis", ABB "Thesis Student".
- Conflito título×descrição: 0 ocorrências.
- Regra futura potencial (NÃO implementada — proposta): mapear `studentische hilfskraft|hiwi` → categoria própria (ou working_student por decisão do dono); 15 casos hoje, determinístico, seguro. As teses continuam melhor como internship/genérico (a F decidiu certo).

## 5. Auditoria de salary

32/409 com salário (29 month · 2 hour · 1 period=None estruturado · 0 year). Todos auditados um a um:

| Empresa | Valor lido | Texto-fonte | Classificação do problema |
|---|---|---|---|
| STIHL ×9 | 2.117 €/mês | "Gehalt: 2.117 €" | ✅ correto |
| Bayer ×9 | 2.280 €/mês | "2.280 € brutto/Monat" e "2.280,00€" (G) | ✅ correto |
| nxp | 2.120 €/mês | "€2,120.00" | ✅ correto (valor; decimais ok) |
| covestro ×1 | 21 €/hora | "Stundenlohn von 21 Euro" | ✅ correto (novo da F) |
| VW (rank 21) | 17,8 €/hora | "Vergütung: 17,80 €/Stunde" | ✅ valor/período pós-G (no HTML de hoje: "80 €/mês" — G publica amanhã) |
| VW ×2 (18,33) | 18,33 €/**mês** | "Der Bruttostundenlohn für Werkstudenten liegt bei aktuell 18,33 €/h • …" | ⚠️ **período incorreto**: valor correto (G), mas `/h` não está no vocab (`_HOURLY_AFTER_RE` só conhece stunde/hour) e o label "Stundenlohn" está a **4.125 chars** do valor (janela=60) — backlog F: estender vocab `/h` |
| philips ×2 | 15 €/**mês** | "liegt Dein Gehalt bei 15 €/h oder 17 €/h" | ⚠️ **período incorreto** (mesma causa `/h`); valor ok |
| BASF ×2 | 40.000–46.000 €/**mês** | "Gross **annual** salary (full-time): 40.000 - 46.000 €" | ⚠️ **período incorreto**: "annual" vem ANTES do valor (grupo period só captura sufixo); também são vagas full-time FP de eligibility (§10) |
| Fraunhofer ×1 | 12 €/mês | "Die Stelle ist zunächst i. d. R. auf **12 Monate befristet**. Die Vergütung richtet sich…" | ❌ **FP puro**: duração de contrato lida como salário — grupo period casa prefixo "Monat**e**" sem `\b` e o label "Vergütung" da frase SEGUINTE entra pela janela forward 60 chars |
| roche / Tchibo / nestlé / MAHLE / CURRENTA | 2268 · 2570 · 2227 · 1500 · 16480–21203 (None) | — | ✅ corretos (roche/Tchibo/nestlé/MAHLE corrigidos ou validados pela G; CURRENTA estruturado sem período — upstream recruitee não publica, documentado) |

**Resumo de classificação (spec §5):**
- Deterministicamente corrigível: `/h` no vocab horário (3 vagas: VW ×2, philips ×2 — 5 anúncios, 4 vagas com período errado); FP "N Monate befristet" (1 vaga: `\b` no grupo period + label não pode vir de frase seguinte).
- Ambíguo: nenhum novo.
- Requer fonte externa: nenhum.
- Não vale complexidade: nenhum além dos já cobertos.

## 6. Auditoria de deadlines

platform_sf 231 (**todas** `2026-10-29` = data do feed +30d — horizonte da plataforma, nunca prazo do empregador; comportamento documentado) · employer_textual 6 (Fraunhofer "Bewerbungsfrist: DD.MM.YYYY", detector estrito confirmado) · none 172.

- Employer deadline não-detectado: scan `bewerb*|apply|application|until|bis zum|frist` + data DD.MM.YYYY sobre os 172 `none` → **0 suspeitos**. Não há lacuna mensurável de detector textual.
- validThrough JSON-LD (13, todas em vagas `none`): datas 2027-03–2028-09 — são validades longas do JobPosting (provável fechamento automático da plataforma/publicação), **não prazos de empregador**. A D2 acertou ao mantê-las informativas, sem urgência.
- Confusão publicação×deadline: 0 casos (datePosted 23/23 já com posted_at do ATS).
- Múltiplas datas: o único padrão é o Fraunhofer (Bewerbungsfrist + "12 Monate befristet" — este gera o FP de salary do §5, não de deadline).

## 7. Auditoria de descriptions

- Antes do pipeline (feed): 336/409 (82%). Pós-hydration: **409/409 (100%)** — 73/73 hidratadas (SR 44, WD 20, EF 7, PS 2), 0 falhas, 56,9s.
- Teasers ≤400 chars: **29/409 (7,1%)** — **100% `phenom:nan`** (DHL 7, Allianz 7, Philips 5, BCG 5, ABB 3, Roche 2). Concentração exata prevista: phenom é o único ATS sem detail endpoint na 0.3.0; teaser é o comportamento do feed.
- Descrição muito curta não-teaser: 0 (próxima menor >314 chars e é teaser phenom também).
- Elegíveis sem descrição: **0**.
- O bloqueio phenom persiste e é total (29/29); o redirect client-side é o root cause documentado na Fase D — GET determinístico não resolve; browser fora de escopo por decisão do dono. Única via: LLM (custo 29 fetch+extração) ou upgrade upstream.

## 8. Auditoria de official page / JSON-LD

150 verificadas (limit 150; 259 cortadas por prioridade): ok 103 · redirected 31 (home) · js_rendered 13 · http_error 2 · empty 1. JSON-LD JobPosting matched: 23 · conflitos 0.

**Informação NOVA que não existia no ATS (a pergunta da spec):**
| Campo | n | Valor real |
|---|---|---|
| validThrough em vagas SEM deadline | 13 | ÚNICA data de validade dessas 13 vagas (exibida informativa — D2) |
| location confirmada | 20 (3 conflitos) | Confirmação; cidade canônica inalterada |
| description melhorada | **0** | Fase A já cobriu as ausentes; matched tinham desc ATS completa |
| salary preenchida | 0 (1 "unchanged_ats_wins") | duplica ATS — sem valor |
| employment_type | 23 (11 FULL_TIME em Praktikum) | regime≠natureza; internamente descartado pela D2 — correto |
| date_posted | 23 (23/23 já têm posted_at) | redundante |
| identifier | 15 | evidência técnica |

**Conclusão:** o valor incremental REAL do estágio hoje se resume a **13 validThrough + 20 location confirmadas** (consumo D2 já implementado). O custo (150 GETs/151s por ciclo) é proporcional? O estágio também produz os 103 "página ok" (confirmação de existência) — mas a UI só mostra o `not_found` (1 caso). O limite 150 já prioriza corretamente (desde D). Nenhuma mudança recomendada nesta fase; possibilidade futura: afrouxar o gate de candidatos (hoje exige teaser/sem-deadline/sem-salary — as 259 cortadas incluem vagas que só precisariam de confirmação), decisão do dono.

---

## 9. Reavaliação do LLM (reavaliar a Fase E com o estado atual)

Baseline: spike E (PR #89, n=30, 25 ok/5 timeout, janela degradada). **Nenhuma chamada LLM nova foi executada nesta fase.** Desfecho de cada achado da spike contra o production de HOJE (409 eligible):

| Achado spike E | Estado hoje | O que sobra para o LLM? |
|---|---|---|
| (1) WA-gap = gap de TEXTO (0 llm_adds/19) | Confirmado: 333/409 not_mentioned | **Nada** — as vagas não falam do tema |
| (2) 6 llm_missing (condicionais ggf./wenn vorliegend) | **6/6 agora `unclear`** pela F (verificado por id) | **Nada** — resolvido deterministicamente |
| (3) student subtipo: 21 deterministic_missing | **21/21 resolvidos pela F** (verificado por id: 13 internship/4 ws/4 mandatory hoje com subtipo) | **Nada** — o maior ganho da spike foi capturado sem LLM |
| (4) salary covestro 21 €/h (Stundenlohn fora do vocab) | **Resolvido pela F** (21 €/hora textual) | **Nada** |
| (5) German: 2 conflicts (ABB "Ideal for candidates… strong German", Bosch "verhandlungssicheres") | Det continua required/preferred em ambos (root causes da janela ±45/strong-German vivos; 1 "strong German" e 44 "wünschenswert" no dataset de hoje) | **Marginal** — 2-3 casos/dataset; correção determinística possível, mas german_level alimenta o SCORE (−2,0/−0,5): qualquer mudança exige fase de recalibração, não LLM |
| (6) English: 2 adds via typo "Englis h" | 0 ocorrências do typo hoje (feed corrigiu o split) | **Nada** (instável e irrelevante) |
| (7) deadline: LLM não converteu validThrough | — | **Nada** (e a D2 já consome validThrough informativamente) |

### Cobertura operacional do enrichment em produção
Store: 44 records, 13 com extração OK (5 no 25/09, 2 no 26, 3 no 27, 3 no 28, **0 no 29**) — **9 úteis no corte de hoje (2,2% dos 409; 30% do Top 30)**. Trend da janela NVIDIA degradada: 27/09 5 ok/14 falha → 28/09 3/16 → 29/09 **0/21** (21 chamadas, 42 retries, 5h38 de tentativa — zero sucesso; tokens in/out 0). O enrichment está **operacionalmente morto** nesta janela: cada ciclo desperdiça ~5h em retries ReadTimeout (o subprocesso não aborta; trava o flock até 14:54).

### Métricas factuais por possível uso do LLM (spec §9)
| Uso | Ganho observado | Frequência | Importância p/ candidato | Custo | Risco | Determinístico? |
|---|---|---|---|---|---|---|
| WA semântico | 0 adds (spike) | — | alta (mas sem texto não há nada a extrair) | alto (5h38 hoje p/ 0) | alucinação baixa (evidence-first) | sim (F cobriu) |
| Student subtipo | capturado pela F | 382/409 | média | — | — | **sim (feito)** |
| Salary textual | capturado pela F/G | 32/409 | média | — | — | **sim (feito)**; restante = vocab `/h` + FP "Monate" |
| Phenom teasers (29) | não testado na spike (bucket page-problem: redirect home) | 29/409 (7%) | média (29 vagas sem descrição utilizável no topo: DHL #15, BCG #19 do dia) | 29 extrações/ciclo | redirect client-side: LLM precisaria de fetch JS — **fora de escopo (browser)** | não (fenômeno de render) |
| German/English fino | 2-3 casos | raro | baixa-média | alto | médio | parcialmente (fase de recalibração) |

**Conclusão da reavaliação:** após F+G, **não sobrou nenhum ganho comprovado do LLM** sobre o que o pipeline determinístico já produz. A decisão de integração A/B/C/D da Fase E permanece pendente do dono, mas os candidatos fortes da spike (student subtipo + salary) foram **capturados por código determinístico**. O único caso LLM-potencial real permanece o **phenom teaser** (29 vagas), mas exige render de JS (browser), que é fora de escopo por decisão anterior. Enquanto a janela NVIDIA seguir degradada, qualquer uso LLM adicional tem custo operacional real sem contrapartida (hoje: 5h38 → 0 extrações).

## 10. Gaps classificados (A–F)

| ID | Gap | Categoria | Evidência | Frequência | Impacto | Risco | Dependências |
|---|---|---|---|---|---|---|---|
| G1 | **SAP sem coleta há 8 dias** — site reconstruído (Next.js); feed legacy `sitemal.xml` → 404; scraper sf:jobs 0.3.0 não suporta o novo layout. Era ~70 eligible/dia (~17% do universo, 2ª maior fonte) | **D (fonte externa)** | probe 29/09: `jobs.sap.com/sitemal.xml`→404 HTML Next.js; root→403; `robots.txt`→200 aponta `/sitemap.xml` novo com estrutura multi-idioma; JSONL: FETCH_ERROR 22–29/09; eligible SAP 67 (22/09)→0 (23/09 em diante) | 8 dias | **ALTO** — maior perda de cobertura da história recente | nenhuma mudança interna | upstream ats-scrapers (novo adapter ou fix do sf scraper p/ o feed novo); decisão do dono sobre patch local |
| G2 | Enrichment LLM 0/21 (janela NVIDIA degradada 26–29/09); 5h38 de retries por ciclo | **C/monitoramento operacional** | enrichment_status.json 29/09; trend 5→3→0 | 3+ dias | médio (chips 🔎 não atualizam; run alongado até 14:54) | baixo (best-effort por design) | janela do provider; possibilidade: cap de retries/tempo no runner (decisão do dono) |
| G3 | Salary período incorreto por `/h` fora do vocab (VW 18,33 ×2, philips ×2) | **A/B (determinístico agora ou backlog)** | "18,33 €/h", "15 €/h oder 17 €/h" no texto | 4 vagas | médio (salário de werkstudent exibido 100× menor) | baixíssimo (extensão de vocab análoga à da F) | fase determinística futura |
| G4 | FP de salary "12 Monate befristet" (Fraunhofer) | **A (corrigível determin. — futuro)** | grupo period sem `\b` + label da frase seguinte | 1 vaga | baixo (salário fictício 12 €/mês) | baixo | fase determinística futura |
| G5 | FPs de eligibility por marker na description: `placement` (3 BMW trainee programmes + 1 MediaMarkt "ad placements") e `internships?` (3 BASF "Junior Controller" full-time) | **A (corrigível determin. — futuro)** | "four placements (including two abroad)"; "e.g. in the context of internships" | 7/409 (1,7%) | baixo (todos ranks 149–307, scores 2,0–6,5, fora do Top 30; poluem contagens/filtros de tipo) | médio (endurecer `is_student_role` pode derrubar TP — exige A/B de funil como toda mudança de filtro) | fase de filtro futura + `funnel_measure` |
| G6 | Condicionais "if indicated" (Bosch ×5) / "falls erforderlich" (continental ×2) fora do vocab da F → `existing_required` indevido | **A (corrigível determin. — futuro)** | texto citado no §3 | 7 vagas | médio (chip 🔴 falso em vagas do Top 30: Bosch ranks 8/28) | baixíssimo (2 marcadores, mesma classe da F) | fase determinística futura |
| G7 | UI não mostra a evidência textual dos unclear (VW "Arbeitserlaubnis für Nicht-EU-Bürger") | **B (backlog determinístico de consumo)** | 5 vagas VW | 5 vagas | médio p/ candidato BR (informação acionável escondida) | baixo (view-only) | fase de UI futura |
| G8 | Digest Telegram encurtado ontem e hoje (7 alertas > 4096) | **E/F (cosmético/valor questionável)** | msg 489; log | 2 dias | baixo (link continua; digest completo vai ao Pages) | zero | decisão do dono: silenciar/recap de alertas antigos no template |
| G9 | `data-salary="80" month` no HTML de hoje (G ainda não renderizada) | **não-gap** (transição) | gh-pages `06ae9e6` | 1 dia | zero | zero | resolve sozinho no ciclo 30/09 |
| G10 | CURRENTA period=None (estruturado recruitee sem período) | **E/F** | upstream | 1 vaga | zero | zero | — |
| G11 | German/English root causes (janela ±45, strong-German, wünschenswert×44) | **B (backlog — exige recalibração de score)** | PR #90 P3 | ~3 casos | baixo | alto (muda score de centenas) | fase própria do dono |

**Problemas que NÃO merecem implementação:** G4–G10 isolados (baixa frequência/impacto), sprites cosméticos do digest, qualquer refatoração do pipeline por causa da auditoria (o pipeline está são: 0 regressões de F/G no mesmo dataset, hydration 100%, dedup estável, CI 43/43).

## 11. Estado e próxima ação (sem decisão automática de Fase I)

### Estado do pipeline (o que está sólido)
- Coleta estável (~72k raw, 112 fontes ok) e funil consistente (425→409 com dedup −16, churn 9 sai/14 entra = variação normal).
- F e G cumpriram o desenho no primeiro ciclo real: WA 70→17 existing_required (53 condicionais reclassificadas, auditadas), student_type 382/409 com subtipo (0 conflitos), salary +4 corrigidas/+3 novas, **0 regressões** em qualquer campo do mesmo dataset.
- Hydration 100% (73/73), official page 103 ok/23 JSON-LD matched, validThrough consumido informativamente (13), page publicada + digest enviado, CI 43/43 no main.
- Alertas de health funcionando como desenhado: regressão AkzoNobel (primeiro dia) e zero-return Siemens Healthineers detectados corretamente HOJE; Lidl/K+N/SMA recorrentes documentados.

### Gaps relevantes (comprovados)
1. **G1 SAP** — perda real de ~17% do universo de vagas há 8 dias, silenciosa (o alerta existe mas a reincidência normaliza a leitura). É externo ao código, mas é O gap de valor para o candidato.
2. **G2 enrichment morto na janela degradada** — 5h38/dia de retries sem 1 sucesso (custo operacional real; sem ganho).
3. **G3+G6** — 11 vagas com período salarial errado ou chip WA falso no Top 30; ambos extensões de vocab da mesma classe da F (cirúrgicas, risco baixo).

### Gaps irrelevantes
G4 (1 vaga), G5 (7 vagas no rabo), G7 (5 vagas, UI), G8–G10.

### LLM
Sem evidência de benefício remanescente após F+G (§9). O único caso não-determinístico (phenom teaser, 29 vagas) exige browser/render — fora de escopo por decisão anterior. Recomendação factual: **não integrar por enquanto**; reavaliar apenas se (a) a janela NVIDIA estabilizar e (b) surgir um campo cujo texto exista mas a semântica escape do regex (hoje: 0 casos comprovados).

### Candidatos para próxima fase (máx 3, SEM implementar — decisão do dono)
1. **Ação de fontes externas (G1):** investigar/patch do novo feed SAP (sitemap novo publicizado no robots.txt) — maior retorno por esforço para o candidato; envolve upstream ou adapter local + A/B de funil.
2. **Mini-fase determinística de vocab (G3+G6+G4):** `/h` no period, "if indicated"/"falls erforderlich" no vocab condicional, guard `\b`+label-same-sentence no money clause — 3 extensões cirúrgicas, ~12 vagas impactadas, sem tocar score/ranking/eligibility.
3. **Cap operacional do enrichment (G2):** limite de duração/retries por run no runner (ex.: abortar após N falhas consecutivas) — decisão de operação, código mínimo.

## 12. Documentação e verificação

- Este relatório: `docs/fase_h_production_observation.md` (novo).
- `MASTER_PLAN.md`: Log de mudanças 29/09 (Fase H) + Seção 1 atualizada.
- `PROJECT_STATUS.md`: bloco Fase H no Current state.
- **Nenhuma mudança funcional**: `git status` no repo = apenas os 3 arquivos de documentação; `data/` intocado (produção preservada); nenhum PR de código (spec: "Não criar PR de código nesta fase"); scripts de teste NÃO executados contra `data/` de produção.

## 13. Critério de aceite — verificação

| Critério | Status |
|---|---|
| ≥1 ciclo real pós-F/G observado | ✅ 1 ciclo pós-F (29/09 09:00Z, full telemetry); pós-G = reprojeção offline + HTML (ciclo real 30/09 pendente — marcado parcialmente observacional) |
| Métricas principais coletadas | ✅ §1 (funil, fontes, duração, publicação, digest, hydration, official, enrichment, Top 30) |
| F/G comparadas contra baseline | ✅ §2 (contrafactual pré-F/G no mesmo dataset + baseline 28/09 + variação 27/09) |
| WA auditado | ✅ §3 (17 existing + 59 unclear, evidência textual) |
| student_type auditado | ✅ §4 (5 subtipos, 0 conflitos, 27 unclear classificados) |
| salary auditado | ✅ §5 (32/32 um a um, causas-raiz) |
| deadlines auditados | ✅ §6 (231 platform_sf + 6 textual + 13 validThrough + scan de não-detectados) |
| descriptions auditadas | ✅ §7 (feed/hydration/teaser/ATS) |
| official page auditado | ✅ §8 (informação nova vs ATS) |
| Fase E/LLM reavaliada com estado atual | ✅ §9 (por id, sem nova chamada LLM) |
| gaps classificados | ✅ §10 (G1–G11, A–F) |
| nenhuma mudança funcional | ✅ (docs-only; `git status` confere) |
| documentação atualizada | ✅ (este arquivo + MASTER_PLAN + PROJECT_STATUS) |
| CI continua verde | ✅ main `cfbeb24` → success (runs de 10:12–10:16 UTC 29/09; docs commits não disparam CI novo além destes) |
