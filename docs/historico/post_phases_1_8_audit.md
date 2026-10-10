# Auditoria pós-Fases 1–8 — internship-finder

**Data**: 2026-09-22 · **Baseline**: main `a92b6d5` (squash `7a4267a`, Fase 8, PR #77) · **Método**: evidência de primeira mão sobre o estado atual (código, dados do run 22/09, SQLite em cópia read-only, HTML publicado e regenerado, logs do cron, suíte executada em cwd scratch). **Nenhuma correção foi aplicada** (audit-only, conforme enunciado).

---

## 1. Executive Summary

O núcleo do pipeline está **sólido e comprovado**: ranking determinístico (md5 idêntico em 2 execuções), identidade P1.1 correta (0 colisões reais; 9 pares `source:external_id` cross-company são vagas distintas e têm IDs distintos), SQLite sem invariantes violadas (148.324 jobs, 0 `first_seen>last_seen`, 0 combinações inválidas de `active/archived`), publicação segura (escape em 61 sinks, gate de scheme, `check_public_safe` limpo, gh-pages contém só `index.html`), suíte 30/30 verde no CI (28/30 em cwd scratch — 2 scripts exigem `data/` no cwd, ver §18).

Porém, **a operação automática das Fases 1, 2 e 8 está inerte na prática**, e há **4 gaps de dados que reduzem a utilidade do sistema para o objetivo real (candidato BR→DE)**:

1. **B1 — Gate `exit_code == 0` nunca dispara**: todos os 17 runs do cron desde 06/09 terminaram exit 2 (Lidl timeout, K+N NXDOMAIN, SMA homônimo — falhas documentadas e "legítimas", mas que sujam o exit code). O gate de publicação/digest/sync exige exit 0 → **a página do GitHub Pages e o digest do Telegram só saem quando o orquestrador publica manualmente** (run_ids `fase4`, `fase5`, `fase6-manual`, `fase7` comprovam). A página publicada hoje (21/09) mostra o run de 21/09 (469 vagas), não o de hoje (390).
2. **B2 — SAP falhou hoje (71 vagas, −17,9% do eligible) sem alerta de cobertura**: `CompanyNotFoundError: SuccessFactorsScraper('https://jobs.sap.com')` — eligible caiu 474→390 e nenhum alerta de drop/zero-return disparou (o status é `error`, não `empty`; o gate de zero-return não cobre). A mensagem do Telegram, além disso, **atribuiu o erro a "BMW AG"** (bug de atribuição em `summarize_run`: o nome amigável de um source compartilhado vem do primeiro registro do run, e BMW foi o primeiro `successfactors:jobs` — quem falhou foi SAP).
3. **B3 — Lixo de teste no JSONL de produção**: 6 registros mock ("Acme", `RuntimeError: boom`, 19–21/09) geram o alerta falso `smartrecruiters:other — erro recorrente (6 runs)` **em toda mensagem diária**. Mesma classe de contaminação que foi sanitizada em 05/09, recontaminada pelas validações das Fases 4–8 rodadas do repo root.
4. **Gaps de dados** (não bloqueiam, mas reduzem o valor): (a) detector de alemão tem falsos negativos por entidades HTML não decodificadas ("Fließend in Deutsch & Englisch" → `plus`; casos reais STIHL/teampicnic no dataset); (b) detector de work authorization é estreito — 7 de 19 frases comuns de suporte caem em `unclear` e `support=0` é **opção B (detector limitado)**, não ausência real; (c) 0 deadlines de empregador = limitação da fonte (SF expõe só validade de feed), mas ~20 vagas citam prazo textual ("Bewerbungsfrist: 15.10.2026", Fraunhofer) que não é extraído; (d) 3 vagas recruitee têm salário estruturado no `raw` (1.400–1.500 €/mês) que o regex da Fase 7 não aproveita (0/3 detectados); (e) 94/390 vagas (24%) têm descrição vazia porque o cron não usa `--include-descriptions` (SmartRecruiters 50/50, Workday 18/18) — cega German/skills/English/WA/salário/work-mode para 1/4 do dataset.

**Veredito**: o sistema é confiável como **ferramenta de ranking local**, mas **não confie ainda no fluxo automático** (publicação/digest/sync nunca rodam sozinhos) nem nos **alertas de cobertura** (queda de 17% passou em branco, alerta falso diário). Corrigir B1–B3 é barato e destrava o valor já construído das Fases 1–8.

---

## 2. Phase 1–8 compliance matrix

Classificação: `OK` (implementado e comprovado end-to-end) · `PARTIAL` (funciona, mas com ressalva real medida) · `MISSING` · `BROKEN` · `CONCEPTUALLY WRONG` · `NOT APPLICABLE`.

| Fase | Requisito | Implementado? | Evidência | Qualidade | Problema |
|---|---|---|---|---|---|
| 1 | Publicação automática diária no GitHub Pages | PARTIAL | `publish_pages.py` completo (gate, atômico, push); **mas** gate `exit_code==0` nunca satisfeito no cron (17/17 runs exit 2 desde 06/09; 4 "publicacao pulada" no log; 8/8 deploys são manuais: `deploy(run fase4/fase5/fase6-manual/fase7)`) | Bom código, operação inerte | Gate acoplado a exit code que é 2 por design (falhas periféricas perpétuas) |
| 1 | Cron 06:00 America/Sao_Paulo | OK | crontab `0 9 * * *` UTC + log `09:00:01 UTC` = 06:00:01 BRT; probe CRON_TZ documentado (Vixie ignora) | OK | Se o BR voltar a ter DST, desloca 1h (documentado) |
| 1 | Página estável, só index.html, sem secrets | OK | `git ls-tree origin/gh-pages` = só `index.html`; grep secrets = 0; `check_public_safe` verde | OK | — |
| 2 | Digest diário no Telegram (novas Top 30, Top 5, movimentos, link) | PARTIAL | `ranking_digest.py` + testes OK; **mas** gated `exit_code==0` → "digest pulado" em 14/14 runs com run_info; mensagem diária real contém só o resumo operacional | Código bom, nunca roda sozinho | Mesma causa de B1 |
| 3 | Interface completa, filtros/ordenação client-side, breakdown | OK | Hotfix #72 (chave `data-rank`); score HTML == pipeline (15.0 == 15.0 verificado); breakdown exato (`Área +12.00, Skills +1.50, Idioma −0.50` = `score_breakdown` do JSON); 390/390 na regeneração | OK | HTML cresceu a 7,2 MB (ver §20) |
| 4 | Segundo perfil Materials Engineering independente | OK | `materials_ranking.py` separado; 376/390 com score>0; topo = POLYMER/Beschichtung/Verfahrenstechnik; business intacto por id | OK | — |
| 5 | Camada PT-BR determinística | OK | `ptbr.py`; títulos PT-BR + tag "Original (DE)" presentes no HTML; pipeline intocado | OK | Glossário ~80 entradas não cobre tudo (labels técnicos expostos, ver §13) |
| 6 | Alemão por exigência (required/preferred/plus/none) | PARTIAL | 162 required / 55 preferred / 11 plus / 162 none no run 22/09; regras por evidência; **FNs**: entidades HTML (`&`) quebram janela `verb_rev` → "Fließend in Deutsch & Englisch" = `plus` (STIHL Praktikum Data Analytics, teampicnic Einkauf) | Bom, com furo mensurável | Texto não passa por `html.unescape` antes da detecção |
| 6 | Work authorization 5 estados | PARTIAL | 20 existing_required / 6 unclear / 0 support / 0 no_sponsorship / 364 not_mentioned; só anúncio, sem páginas de empresa, sem dados curados; sonda: 7/19 frases de suporte comuns → `unclear`; "Hilfe bei der Arbeitsgenehmigung" fora do vocab | Conceito correto, detector estreito | `support=0` ≠ ausência real (opção B) |
| 6 | Deadline employer vs validade SF vs none | OK (com limitação de fonte) | 218 platform_sf (218/218 = `collected+30d` exato) / 172 none / 0 employer; urgência exclui SF (regra implementada e testada) | OK | 0 employer é da fonte (só SF/arbetsformedlingen expõe `application_deadline` no upstream 0.3.0); prazo textual no corpo não é extraído (~20 vagas) |
| 6 | candidate_fit / problems / quality_flags / readiness | OK | Funções puras; chips e bloco de problemas no HTML; flags medidas (218 platform_validity, 172 no_deadline, 86 short_description, 145 no_language, 49 old_posting) | OK | — |
| 7 | Company Intelligence curada com fonte/qualidade/data | OK | 12 empresas + 12 cidades versionadas; 253/390 vagas (65%) com intel; 11/64 empresas; `Not mentioned`/`Not available`/`Not disclosed` semanticamente distintos | OK | Cobertura concentrada no topo |
| 7 | Salário só por evidência | PARTIAL | 19/390 via regex; **3 vagas recruitee com `raw.salary_min/max` (1.400–1.500 €/mês) NÃO detectadas** | Dado da fonte desperdiçado | Adapter não mapeia salary estruturado do upstream |
| 7 | Custo de vida por cidade | PARTIAL | 161/390 (41%) com custo; **alias gap**: "Munich" (14 vagas, EN) não casa com a chave curada `munchen` | OK com furo | Faltam aliases EN↔DE |
| 7 | Compare 2–4 vagas | OK | Reuso no HTML; sem vencedor automático | OK | — |
| 8 | Tracker pessoal (status/prioridade/notas/candidaturas/feedback) | OK | `personal_tracker.py` + 45 checks no teste; banco privado `data/personal/jobs_personal.db` (não existe ainda — dono ainda não usou) | OK | — |
| 8 | sync-ranking diário idempotente | PARTIAL | Implementado + testado (idempotência provada); **mas** gated `exit_code==0` → nunca rodou em produção | Mesma causa B1 | — |
| 8 | Seções pessoais no Telegram (reminders ≤3d employer, aguardando resposta) | PARTIAL | `personal_sections()` implementado; gate exit 0 + banco inexistente → ainda nunca apareceu | Idem | Deadlines employer = 0 hoje, então reminders teriam 0 itens de qualquer forma |
| 8 | Hint do tracker no HTML público sem dado pessoal | OK | `data-job-id` + hint em `<details>` no HTML de hoje (regenerado); **página publicada é pré-Fase 8** (21/09) | OK | Stale publish esconde a feature |

---

## 3. Outstanding TODO/FIXME/limitations

**Grep repo-wide** (`TODO|FIXME|XXX|HACK|limitation|known issue|workaround|not implemented|pending|deferred|future|backlog|technical debt`): **zero TODO/FIXME/XXX/HACK em código** (src/ + scripts/). O que existe são limitações **documentadas** — o projeto é disciplinado nisso. Itens outstanding por prioridade:

| # | Item | Arquivo/linha | Impacto | Prioridade | Corrigir agora? |
|---|---|---|---|---|---|
| O1 | Exit 2 perpétuo → gates de publish/digest/sync inertes | `cli.py:662` (`had_failure → return 2`) × `refresh_daily.py` gates `exit_code == 0` | Features Fases 1/2/8 nunca rodam no cron; página pública stale | **Alta** | **Sim** |
| O2 | Lixo "Acme" no JSONL de produção → alerta falso diário | `data/collection_metrics.jsonl` (6 registros 19–21/09, empresa "Acme", `RuntimeError: boom`) | Alerta `smartrecruiters:other recorrente há 6 runs` toda mensagem; polui health | **Alta** | **Sim** (sanitizar + prevenir com cwd scratch nas validações) |
| O3 | Atribuição de erro por source compartilhado | `refresh_daily.py` `summarize_run` (source_names: primeiro company do run vira o nome do source) | Mensagem de hoje diz "BMW AG … erro" quando quem falhou foi SAP | **Alta** | **Sim** |
| O4 | Queda de cobertura SAP (−71 vagas) sem alerta | `health.py` (zero_return só cobre `empty`; `error` não dispara) | Perda silenciosa de 17,9% do eligible | **Alta** | **Sim** |
| O5 | FNs de German por entidades HTML | `app_intel.py:219` (janela sobre texto cru; `&`/tags quebram `verb_rev` ±30) | STIHL/teampicnic reais: "Fließend in Deutsch & Englisch" → `plus` (deveria ser required) | Média | Sim (barato: `html.unescape` no texto) |
| O6 | Salário estruturado recruitee não aproveitado | `opportunity_intel.job_salary` (regex) × `raw.salary_min/max` | 3 vagas eligible com salário real da fonte exibem "Not available" | Média | Sim |
| O7 | Prazo textual no corpo não extraído | `application_deadline` só do campo estruturado | ~20 vagas citam "Bewerbungsfrist: 15.10.2026" (Fraunhofer) e seguem "sem deadline" | Média | Deferível (regra de extração com evidência + validação) |
| O8 | Descrições vazias (94/390 = 24%) | cron sem `--include-descriptions`; SmartRecruiters 50/50, Workday 18/18, softgarden, personio, 8/10 eightfold | German/skills/English/WA/salário/work-mode cegos em 1/4 do dataset | Média | Sim (avaliar custo de rede/tempo; já há flag) |
| O9 | Lidl timeout perpétuo (×19 runs) | registry (comentário documenta feed 120 MB sob demanda) | Exit 2 diário (causa raiz de O1), 0 vagas Lidl | Média | Aceito como limitação; não silenciar (decisão 17/09) — mas O1 neutraliza o efeito no gate |
| O10 | Alias gap cidades EN↔DE no custo de vida | `location_intel.json` (sem alias "munich"→"munchen") | 14 vagas "Munich" sem custo de vida (73 de München têm) | Baixa | Sim (curadoria) |
| O11 | Nomes técnicos de empresa exibidos | `Job.company` = valor do ATS | HTML mostra BoschGroup, teampicnic, careers.allianz.com, careers.bcg.com, bahagag, hella, zeissgroup | Baixa | Deferível (mapa de display opcional; cuidado para não inventar) |
| O12 | "FULL_TIME · estágio" confuso | `ptbr.py` employment_type label | 53 vagas exibem "Período integral (FULL_TIME) · estágio" | Baixa | Deferível |
| O13 | `test_interface`/`test_ptbr` bloco real quebra em cwd scratch | scripts de teste (subprocesso usa `--input` relativo ao cwd; gate de skip olha ROOT) | Suíte não é 100% reproduzível fora do repo root (CI real passa porque gate de skip dispara antes) | Baixa | Sim (mínimo: alinhar cwd do subprocesso) |
| O14 | `MASTER_PLAN.md` ainda diz "CI verde 30/30" como se a publicação fosse automática; relatório Fase 8 §17 afirma "deploy automático diário publica" | docs | Docs prometem comportamento que não ocorre | Média | Sim (após corrigir O1, ou documentar a realidade) |

**Limitações externas documentadas (não são bugs, não reabrir)**: Workday sem país (mitigado por re-inferência); K+N cornerstone NXDOMAIN (coletado via phenom:nan); SMA oracle homônimo; SF `g:expiration_date` = validade de feed (regra correta de exclusão); CRON_TZ não suportado (cron UTC fixo).

---

## 4. Ranking audit

**Pesos vivos** (`ranking.py`, lidos do código — conferem com a seção "Como este ranking funciona" do HTML, que é renderizada das constantes vivas):

| Componente | Peso | Observação |
|---|---|---|
| area (título) | 3,0/2,0/1,0 × (primary/related/weak) | `WEIGHT_AREA_TITLE=2.0` × `area_score` do título (3/2/1); máscara de produto ("SAP Analytics Cloud") aplicada |
| area (descrição) | **0,0** (`WEIGHT_AREA_DESC=0.0`) | Calibrado a zero (templates inflavam); skills compensam |
| skills | +0,75/termo (9 padrões: inventory, supplier, process automation, system integration, python, apis, cloud, reporting, continuous improvement) | Só na descrição; sem descrição = 0 |
| english | +1,5 | Evidência word-bounded no título+descrição |
| alemão required | **−2,0** | Por nível detectado (Fase 6), não por idioma do anúncio |
| alemão preferred | −0,5 | — |
| type (título) | +1,0 | Marcador forte (Praktikum/Werkstudent/Internship...) |
| location | DE +1,0, Berlin +0,5 | 390/390 `de` → componente constante (+1,0 universal) |
| penalties | senior −3,0 · manager −1,0 · FULL_TIME −0,5 | Senior/manager só sem marcador forte no título |

**Verificações executadas**:
- **Score HTML == pipeline**: CONFIRMADO — primeiro `data-score` do HTML regenerado = 15,0 = `eligible_jobs.json[0].score` (STIHL Praktikum Data Analytics, breakdown `{area: 12.0, skills: 1.5, language: −0.5, type: 1.0, location: 1.0, penalties: 0.0}`).
- **Breakdown explica exatamente o score**: CONFIRMADO — o `<details>` "por que esta vaga?" renderiza os 6 componentes com os valores reais do `score_breakdown` (área +12,00, skills +1,50, idioma −0,50...); penalidades separadas em "o que reduziu a nota".
- **Determinismo**: CONFIRMADO — md5 da sequência (id, score) idêntico em 2 execuções de `rank_jobs` sobre o snapshot.
- **Desempate**: score desc → título casefold → empresa → id (determinístico); mas com **97% das vagas em grupos de empate** (50 scores distintos; maiores grupos: 6,0×46, 7,5×42, 5,5×35) a ordem dentro de cada grupo é essencialmente alfabética — limitação já documentada no benchmark de 11/09 (96,5% empatados, tau +0,651: o ranking TEM sinal real, mas baixa resolução ordinal).
- **Perfil Materials**: independente (376/390 com score>0; topo = HELLA POLYMER 7,25, Fraunhofer Beschichtung 7,25, BASF Verfahrenstechnik 6,5); nunca somado ao principal — CONFIRMADO por leitura + testes.
- **Empregabilidade dos componentes**: `location` hoje é invariante (todos DE, sem Berlin variando em peso suficiente para reordenar) — sonda "Location removida" manteve 30/30 do Top 30. O peso existe para o dia em que o filtro de país for `europe`/`all`.
- **FULL_TIME −0,5**: coerente (Werkstudent marcado FULL_TIME não zera), mas o rótulo exibido ("Período integral · estágio") confunde (ver §13).

**Divergências código × docs × HTML**: nenhuma nos pesos (a seção de pesos do HTML é gerada das constantes vivas — invariante testado no CI). Divergência real está em **afirmações operacionais** (docs dizem que a publicação é automática; ver §16).

---

## 5. German audit (dataset 22/09, 390 vagas)

**Distribuição**: required **162** (41,5%) · preferred **55** · plus **11** · none **162**.

O desenho está **conceitualmente correto**: classificação por exigência no TEXTO (janela ±45 chars por menção, sinal mais forte vence), nunca pelo idioma do anúncio; "Deutschland"/"Deutsche Bahn" não contam; negação explícita ("no German required") vence; CEFR/Wort und Schrift/fließend/verhandlungssicher → required; "von Vorteil"/"ein Plus" → preferred.

**Exemplos reais corretos (dataset)**:
- required/verb — STIHL "Sehr gute Deutsch- und Englischkenntnisse in Wort und Schrift" ✓
- required/verb — Miebach "Du kommunizierst sicher auf Deutsch und Englisch in Wort und Schrift" ✓
- required/verb_direct — Uniper "Proficiency in English and German (written and spoken) required" ✓
- preferred/soft — teampicnic "Sprichst fließend Englisch; Deutschkenntnisse sind ein Plus" ✓
- preferred/qual — Knorr "Sehr gute Deutsch- und gute Englischkenntnisse" — **WRONG-BORDERLINE**: "sehr gute Deutsch-" casa `qual`→required em isolado; no anúncio completo a menção "SQL, Python... sind wünschenswert" GRUDADA (±25) classificou a menção como preferred — o sinal `soft` tight venceu o `qual`. Plausível mas discutível (texto diz "sehr gute Deutsch... in Wort und Schrift" = required). 1 caso medido nessa borda.

**Falsos negativos CONFIRMADOS (2 casos, reproduzidos isoladamente)**:
- STIHL Praktikum Data Analytics: "Fließend in Deutsch & Englisch" → `plus/bare` (deveria ser required). Causa: `&` (entidade HTML não decodificada) entre "Deutsch" e "Englisch" quebra o casamento de `verb_rev` ("fließend...deutsch" exige ≤30 chars de gap) e o par DE↔EN.
- teampicnic Einkauf/Marketing Werkstudent: "<strong>Fließende Deutsch</strong>- und Englischkenntnisse" → `plus/bare`. Causa: tag `<strong>` dentro da menção quebra `verb_rev`; sem a tag o mesmo texto = preferred (par) — reproduzido.
- Impacto sistêmico: 34/390 descrições contêm tags HTML; 189 contêm `&`. A sonda isolada mostra que `html.unescape` + strip de tags antes da detecção corrige ambos os casos sem tocar nas regras.

**Falsos positivos**: nenhum encontrado na amostra auditada (menções a "Deutsche Bahn"/"Deutschland" corretamente ignoradas — anti-tests no CI cobrem).

**Idioma do anúncio ≠ requisito**: CONFIRMADO por construção (nenhum componente olha o idioma em que o anúncio foi escrito).

---

## 6. Visa / Work Authorization audit (CRÍTICA)

**Contagens no dataset 22/09 (390)**: `support` **0** · `existing_required` **20** · `no_sponsorship` **0** · `unclear` **6** · `not_mentioned` **364**.

**Como o sistema detecta** (`app_intel.work_authorization`): vocabulário-gate (visa/permit/sponsor/relocat/Arbeitserlaubnis/Aufenthaltserlaubnis/EU-Bürger/citizens etc.) → se ausente: `not_mentioned`. Presente: precedência `no_sponsorship` > `support` > `existing_required` > `unclear`. Fonte: **só o texto do anúncio** (título+descrição). Não consulta páginas de empresa, não usa dados curados (company_intel não tem campo de imigração), zero rede.

**"support = 0" — qual explicação? Evidência: opção B (detector limitado), parcialmente A.**
- 26/390 anúncios tocam no tema (vocab presente). Nenhum diz explicitamente "sponsorship offered". Mas:
- Sonda adversarial com 19 frases comuns de mercado: **7 caem em `unclear`** ("We support you with the visa process", "Assistance with visa application provided", "Wir unterstützen bei der Beantragung eines Visums", "Wir übernehmen die Beantragung der Arbeitserlaubnis", "Support with residence permit application", "The company will assist with work authorization", "Übernahme der Visakosten") e **1 em `not_mentioned`** ("Hilfe bei der Arbeitsgenehmigung wird angeboten" — "Arbeitsgenehmigung" não está no vocab). As frases que o detector pega são as formulações mais literais ("visa sponsorship available", "relocation support/package").
- Além disso, 24% das vagas têm descrição VAZIA (sem `--include-descriptions` no cron) — o detector não vê nada para 94 vagas.
- Contexto real: anúncios de estágio/Werkstudent na Alemanha raramente mencionam patrocínio de visto (estagiários de fora da UE usam visto específico §19b AufenthG / FSV; empresas grandes resolvem internamente e não escrevem no anúncio). Logo: **0 support = ausência de evidência textual (A) agravada por detector estreito (B) e descrições vazias — NÃO é prova de que nenhuma empresa apoia**. "Nenhuma evidência encontrada" é a resposta honesta; o estado `not_mentioned` (364) corretamente NÃO afirma "não patrocina".

**Os 20 `existing_required` são reais?** Sim, e a interpretação é juridicamente correta para a Alemanha: são maioritariamente **checklists de documentos** (STIHL "gültige Arbeits- und Aufenthaltserlaubnis", VW "Ggf. Arbeitserlaubnis... für Nicht-EU Bürgerinnen/Bürger", teampicnic "You have an EU citizenship or valid working visa"). Para um candidato BR sem permissão prévia, esses anúncios exigem que ele obtenha a permissão — classificar como aviso objetivo está certo.

**Nomenclatura juridicamente apropriada?** Razoável, com ressalvas: o sistema distingue visa (visto) / work permit (Arbeitserlaubnis) / residence permit (Aufenthaltserlaubnis) no vocabulário, mas o estado agregado `existing_required` mistura "valid work permit", "EU citizenship" e "Arbeitserlaubnis inkl. Zusatzblatt" sob um rótulo só — aceitável para sinalização, impreciso para decisão jurídica. `no_sponsorship=0` não significa ausência de anúncios "não patrocinamos" no universo — nenhum dos 26 que tocam o tema usa as fórmulas negativas catalogadas (sonda: "Note: we cannot offer visa sponsorship" → `no_sponsorship` funciona).

**Gap estrutural para o objetivo do usuário (BR→DE)**: o sistema não tem NENHUMA fonte de evidência externa ao anúncio (páginas de carreiras, seções "visa sponsorship" das empresas, curadoria). Para "descobrir oportunidades que aceitam candidato internacional", o dado de maior valor seria exatamente esse — e hoje ele só existe como sinal binário negativo (20 vagas a evitar). O `company_intel` (Fase 7) seria o lar natural de um campo curado "visa_policy" com fonte — não existe.

---

## 7. Deadline audit

**Contagens (dataset 22/09)**: employer **0** · platform_sf **218** (todos SuccessFactors) · none **172**.

**Por que 0 deadlines de empregador? Limitação da fonte, com dois qualifications**:
1. O upstream `ats-scrapers 0.3.0` só expõe `application_deadline` em **successfactors** (`g:expiration_date`) e **arbetsformedlingen** (fora do escopo do registry). Nenhum outro scraper dos 12 ATS em uso extrai prazo — verificado por grep no pacote instalado. Greenhouse/SmartRecruiters/Workday têm prazos em JSON bruto? Não mapeados pelo scraper.
2. O `g:expiration_date` = **validade do feed** (plataforma), não prazo do empregador — regra Fase 6 correta e COMPROVADA de novo hoje: 218/218 valores = `collected_at + 30 dias` exato.
3. **A evidência de que prazos reais existem e estão sendo perdidos**: 20/390 descrições citam prazo textual explícito — ex. Fraunhofer "Bewerbungsfrist: 15.10.2026" (vaga real de baterias). Este é o único caminho hoje para deadline de empregador e não é extraído.

**SuccessFactors especificamente**: correto — valor exibido como "Validade do anúncio (fonte)", excluído de urgência/"vagas expirando" (regra implementada + testada + 586 ocorrências do rótulo no HTML publicado). Feed expirado vira flag `sf_validity_passed` (hard) — lógica correta.

**Outros ATS onde deadline real pode existir**: Greenhouse (candidatura com prazo no corpo), SmartRecruiters (descrição vazia hoje — sem `--include-descriptions` não há nem corpo para extrair). Sem descrição, a extração textual é impossível — O8 é pré-requisito de qualquer ganho aqui.

**Datas sintéticas/incorretas**: nenhuma fabricação (invariante AGENTS respeitado: `application_deadline` só do campo estruturado; `deadline_kind` nunca deriva de posted_at). Com 150/390 posted_at preenchidos, idades medidas: ≤30d 74 · 31–60d 27 · 61–90d 11 · >90d 38 (flag `old_posting` em 49 vagas — limiar 60d).

---

## 8. Company Intelligence audit

**Cobertura medida (22/09)**: 12 empresas curadas (11/64 empresas do eligible) → **253/390 vagas (65%) com intel**. Custo de vida: 13 cidades curadas → **161/390 (41%)**.

- Campos com `sources` (fonte+URL+`checked`+`quality`): presente em todas as entradas curadas (verificado no JSON). Freshness: checados 20–21/09 (Numbeo ago–set/2026).
- Semântica dos 4 estados — usada corretamente e são distintos na interface: `Not mentioned` = campo pesquisável ausente do anúncio/dado (1.859× no HTML), `Not available` = arquivo/intel ausente para a entidade (2.140×), `Not disclosed` = empresa não divulga (salário/turnover; 1.861×), `Unknown` = pathway sem dado (1×... na verdade pathway unknown aparece por vaga sem intel). CONFIRMADO por leitura dos usos em interface.py + contagens.
- Empresas com nome técnico do ATS exibido: CONFIRMADO — `Job.company` é o valor do feed (BoschGroup 752×, teampicnic 120×, careers.allianz.com 72×, zeissgroup 84×, bahagag, hella, Telekom Growthhub, knorrbremsP2 nos tenants). Não é bug de dedup (identidade estável é o objetivo), é gap de apresentação.
- Duplicação de dados de empresa: não há (1 entrada curada por empresa; aliases no mapa). Salário estruturado desperdiçado: 3 vagas recruitee com `raw.salary_min/max` (1.400–1.500 €/mês etc.) exibem "Not available" porque o regex da Fase 7 não os consulta (achado O6).
- Alias gap de cidades: "Munich" (14 vagas EN) não casa com a chave curada `munchen` (73 vagas DE casam) → custo de vida perdido para 14 vagas (O10).
- Cache: zero rede em render (funções puras + arquivos versionados) — CONFIRMADO; arquivo ausente → `{}` → "Not available", página segue (testado no CI).

## 9. Identity / dedup audit

- **Formato do ID**: `<company>|<source>:<external_id>` (fallback hash sha1 da URL escopado por empresa) — P1.1 implementado no adapter (lido integralmente).
- **Colisões históricas**: o SQLite tem 5.996 registros com formato ANTIGO (`id` sem `|`, pré-P1.1) — **100% archived=0-active** (0 ativos): migração por churn natural correta. 9 pares `source:external_id` com 2 empresas (ex.: `phenom:nan:52554` Allianz vs `careers.bcg.com|phenom:nan:52554` BCG): **vagas distintas com IDs distintos — a correção P1.1 FUNCIONA** (mesma tripla (source, external_id) em empresas diferentes não colide).
- **Dedup**: 3 chaves (external_id escopado; URL escopada; company+title+location normalizados) — 12 removidas no run 22/09. Pares (company,title) restantes no eligible: 11 — auditados: bahagag "Werkstudent Service und Logistik" ×4 = **cidades diferentes (Offenburg/Ulm/Gelsenkirchen/Wuppertal) = vagas distintas** (anti-caso correto); Bayer Analytics Advisory ×2 = mesma vaga publicada com 2 external_ids (1429117133 DE / 1429117033 EN) + 1 via eightfold — **duplicata TRUE residual** (locations DE vs EN escritas diferentes: "Nordrhein-Westfalen" vs "North Rhine Westfalia" não normalizam). Limite documentado do dedup (tradução de local), não regressão.
- **Camadas consumidoras**: dedup escopa por (company, source); SQLite PK = id; health por (source, company); archive copia por arquivo. Coerente.

## 10. SQLite / archive audit

Cópia read-only do `jobs.db` (455 MB; 148.324 rows):
- **Invariantes lifecycle**: 0 `first_seen > last_seen`; 0 URL vazia; combinações (active,archived): apenas (0,1)=75.499 e (1,0)=72.825 — 0 inválidas. IDs distintos = 148.324 = total.
- **Falha de tenant NÃO arquiva jobs antigos** (enunciado §10): COMPROVADO em produção — hoje `successfactors:jobs` falhou para SAP, e o active total (72.825) > jobs.json do run (71.851) por exatamente as 974 vagas de tenants parcialmente falhos/ausentes que permanecem ativas. O mecanismo P1.2 (unidades confiáveis; `collection_units` só com OK/EMPTY) funciona.
- **Churn**: min first_seen 07/09 → max last_seen 22/09 09:10; ids antigos (sem pipe) 100% archived.
- **Backups**: 10 backups em `data/backups/` (~456 MB cada, diários, retenção 14d) → ~4,5 GB só de backups + archive 7,5 GB total de data/. Disco VPS: 61/96 GB (63%) — o aviso de 80% ainda não dispara, mas o crescimento é ~0,45 GB/dia de backup + ~0,2 GB/dia de jobs.db; retenção de 14 dias segura o teto. OK, monitorar.

## 11. Daily refresh / cron audit

- **Cron real**: `0 9 * * *` UTC com `flock -n` + `--pages-dir` + `--always-notify` — CONFIRMADO no crontab; horário efetivo nos logs: 09:00:01 UTC = 06:00:01 America/Sao_Paulo (BRT fixo, sem DST; probe CRON_TZ documentado). **CONFIRMADO explicitamente: America/Sao_Paulo 06:00 = 09:00 UTC.**
- **Exit codes do processo**: 17/17 runs exit 2 desde 06/09 (logs + 14 run_infos com exit_code=2). NUNCA exit 0 → gates de publish/digest/sync (`exit_code == 0`) inertes (B1).
- **Telegram**: 17 envios ok:true no log; mensagem diária chega (via --always-notify), MAS sem digest (pulado 14×: "digest pulado (exit 2 != 0)").
- **Contaminação**: 6 registros "Acme" mock no JSONL de produção (19–21/09) → alerta falso "smartrecruiters:other recorrente há 6 runs" em toda mensagem (O2). Origem: validações das Fases 4–8 rodadas do repo root (o seed do dry-run gravou no `data/` real — mesmo incidente de 05/09, reincidente).
- **Atribuição de erro**: mensagem de hoje lista "BMW AG (successfactors:jobs) — erro ao buscar vagas" mas quem falhou foi **SAP** (`CompanyNotFoundError SuccessFactorsScraper('https://jobs.sap.com')`; BMW AG coletou 830 ok) — bug O3 em `summarize_run.source_names`.
- **Cobertura**: SAP 71 vagas sumiram (474→390, −17,9%) sem nenhum alerta (status `error` não coberto pelo zero_return; sem recurring histórico para SAP) — O4.

---

## 12. GitHub Pages audit

- **Fluxo real**: VPS → cron refresh → `interface.py` (HTML) → `publish_pages.py` → gh-pages → Pages — implementado e seguro, mas **o passo automático nunca dispara** (gate exit 0; O1/B1). 8/8 deploys são manuais (`fase4`, `fase5`, `fase6-manual-exit2-parcial`, `fase7-23e7ee6`).
- **Publicação atômica**: CONFIRMADO — temp + `os.replace` no mesmo FS; commit+push só depois do gate de segurança; conteúdo idêntico → sem commit.
- **Página incompleta não substitui válida**: CONFIRMADO por construção (gate exit 0 + eligible > 0) E na prática: a página publicada hoje é a do run 21/09 (gerada 21/09 06:20 UTC) — o run de hoje (390 vagas, −17,9%) NÃO foi publicado. O gate funcionou "bem demais": protegendo contra incompletude, bloqueou a publicação por completo.
- **Secrets/jobs.db/interno no Pages**: CONFIRMADO limpo — `git ls-tree origin/gh-pages` = só `index.html`; grep `ghp_|TELEGRAM_BOT_TOKEN|/home/ubuntu|jobs.db|.env` no blob = 0 matches; `check_public_safe` cobre 10 patterns de secret + 6 fragmentos privados.
- **Deploy manual com exit 2**: o commit `b9d0ee7` ("fase6-manual-exit2-parcial") mostra que o orquestrador já publicou DE PROPÓSITO ranking parcial — o gate "nunca publica parcial" foi contornado manualmente uma vez. Decisão de dono válida, mas mostra que o gate binário não expressa a política real desejada.

## 13. HTML/UX audit

- **Conteúdo**: 390/390 vagas em 2 perfis (biz/mat), filtros/ordenação client-side, busca, Top 30 por perfil, compare 2–4, breakdown "por que esta vaga?" com valores exatos, PT-BR com original preservado, chips (deadline/idioma/visto/readiness), seções recolhíveis de Company Intel, validade SF rotulada como fonte. Mobile <760px = cards (CSS puro), dark mode. CONFIRMADO por leitura do HTML regenerado.
- **Tamanho/performance**: HTML regenerado hoje = **7,2 MB** (publicado 21/09 = 8,6 MB raw/8,4 MB); 166.509 tags no publicado; ~18,2 KB/vaga (constante: 500→9,1 MB, 1.000→18,2 MB, 5.000→91 MB). Render server-side: 4,1s/390. Threshold P3 #22 (payload >10 MB) será cruzado com ~555 vagas — próximo gate documentado.
- **Nomes técnicos**: CONFIRMADO (BoschGroup, teampicnic, careers.allianz.com, bahagag...) — o `data-company` e o texto exibido usam o valor cru do ATS.
- **FULL_TIME confuso**: CONFIRMADO — 53 vagas "Período integral (FULL_TIME) · estágio" (112 no publicado). Um Werkstudent marcado FULL_TIME pelo ATS exibe rótulo contraditório com o badge "estágio" ao lado.
- **`Not mentioned` vs `Not available`**: semanticamente distintos e usados consistentemente (1.859 vs 2.140 vs 1.861 `Not disclosed`); risco é o usuário não distinguir visualmente (labels próximas em seções recolhíveis).
- **Timestamps**: "gerado em ... UTC" presente e correto por página; freshness (desde/primeira/última vista via --db-join) por vaga — sem inconsistência encontrada no HTML regenerado. A página PUBLICADA, porém, está 1 dia stale (efeito B1, não do HTML em si).
- **Texto cortado/campos confusos**: títulos longos truncam visualmente mas o atributo completo vai ao DOM; sem corte de conteúdo detectado.

## 14. Data quality audit (dataset 22/09)

| Métrica | Valor |
|---|---|
| Raw coletado | 71.851 (127 fontes; 114 ok, 9 empty, 1 timeout, 3 error) |
| Funil | 71.851 brutas → 402 filtered (tipo+área+país) → dedup −12 → **390 eligible** |
| Empresas / tenants (eligible) | 64 / 50 |
| ATS (eligible) | successfactors 218 · smartrecruiters 50 · greenhouse 31 · phenom 22 · workday 18 · recruitee 14 · cornerstone 11 · eightfold 10 · softgarden 6 · personio 4 · ashby 3 · teamtailor 3 |
| Países | de 390/390 (100%) |
| German (título+descrição) | required 162 · preferred 55 · plus 11 · none 162 |
| Work authorization | not_mentioned 364 · existing_required 20 · unclear 6 · support 0 · no_sponsorship 0 |
| Deadline | platform_sf 218 (=collected+30d em 218/218) · none 172 · employer 0 |
| Salário (regex) | 19/390 · work mode: on_site 98 · hybrid 21 · remote 5 · not_mentioned 266 |
| employment_type | vazio 309 · FULL_TIME 53 · PART_TIME 9 · INTERN 8 · CONTRACT 7 · OTHER 4 |
| Descrição vazia (<50ch) | 94/390 (24%) — SmartRecruiters 50/50, Workday 18/18, softgarden 6/6, personio 4/4, eightfold 8/10 |
| Company intel / custo de vida | 253/390 (65%) · 161/390 (41%) |
| Qualidade | 49 old_posting (>60d) · 25 teses no título (regra aceita) · 0 títulos de graduação formal |
| Duplicatas TRUE residuais | ≥1 par Bayer (DE/EN repost mesmo cargo, ids distintos + versão eightfold) |

**Anomalias**: (1) queda 474→390 dominada por SAP (−71) sem alerta; (2) BMW AG 81→73 sem alerta (mesmo tenant OK no JSONL, erro de outro tenant); (3) alerta falso diário "Acme/smartrecruiters:other"; (4) workday/phenom com eligible apesar de país re-inferido (funcional); (5) empates: 97% (50 scores distintos, grupos 46/42/35) — ranking com sinal mas resolução ordinal baixa (herança do benchmark 11/09).

---

## 15. Ranking sensitivity analysis (diagnóstico only — nada foi alterado)

Recomputação hipotética (score_job real + delta manual, mesma chave de desempate) sobre as 390 vagas; comparação do Top 30 resultante contra o baseline:

| Cenário | Top 30 mantém | Entra novo | Interpretação |
|---|---|---|---|
| German required −4,0 (era −2,0) | 24/30 | 6 | Sensível: alemão exigido já está fora do topo; punir mais troca a cauda |
| German required 0 (sem penalidade) | 25/30 | 5 | Simétrico: −2,0 está bem calibrado (nem ausente nem dominante) |
| English removido (+1,5→0) | 22/30 | 8 | **O critério mais sensível do Top 30** |
| Location removida | 30/30 | 0 | Componente inerte hoje (100% DE) — peso morto no cenário atual |
| Área dobrada | 23/30 | 7 | Sensível na fronteira do topo |
| Type removido | 28/30 | 2 | Pouco sensível (marcador quase universal no eligible) |

**Conclusão**: o ranking é **razoavelmente robusto** — nenhum critério individual derruba o topo (mín. 22/30 mantidos), e os deltas são consistentes com a intenção declarada (alemão exigido não domina o topo; English é o discriminador mais forte). A fragilidade real não é sensibilidade a pesos, é a **resolução ordinal** (97% de empates): dentro dos grupos, a ordem é alfabética (desempate documentado). Ganho marginal de qualidade vem de critérios de DESempate (ex.: presença de descrição, posted_at mais recente, German level como ordinal), não de novos pesos.

## 16. Documentation drift

| Doc | Afirmação | Realidade | Tipo |
|---|---|---|---|
| `docs/relatorio_fase8_decision_tracking.md` §17 | "O deploy automático diário (cron 06:00 BRT) publica o HTML novo quando o PR for mergeado" | Nunca publicou sozinho (17/17 exit 2; 8/8 deploys manuais) | **Doc normativa vs sistema vivo** |
| `README.md` (várias seções) | "o refresh publica o ranking automaticamente" (implícito na seção Pages/cron) | Idem | Idem |
| `MASTER_PLAN.md` §1 | "Suíte: 23/23 scripts no CI" (seção Coleta viva, linha mais antiga) vs "30/30" (log 22/09) | 30 é o correto (array do ci.yml = 30); o "23/23" é resquício da leva 18/09 na mesma seção | Internamente inconsistente (mesma seção guarda 2 números) |
| `PROJECT_STATUS.md` | "Current snapshot = 18/09 run (476)" e funil 476 por toda parte | Snapshot real = 22/09 (390); 469/474 são os runs 21/20/09 | **Stale** (número datado sem atualização diária) |
| `README.md` | "476 eligible no run do cron 18/09" (exemplos de comando) | Histórico legítimo (datado) | Aceitável (é datado) |
| `docs/roadmap.md` | Marca-se obsoleto no topo | Correto (auto-rotulado) | OK |
| Weights/pesos em docs vs código | Pesos vivos renderizados no HTML a partir das constantes | CONFIRMADO idêntico (invariante testado) | OK |

**Drift real = afirmações de AUTOMAÇÃO**, não de arquitetura. Toda a arquitetura descrita (camadas, módulos, fluxos) confere com o código.

## 17. Dependencies

- **Declaradas (pyproject)**: `ats-scrapers>=0.3.0` (range aberto — gate P3 #30 de revalidação em nova release), `requests>=2.31`, `pydantic>=2.0`, `beautifulsoup4>=4.12`, `pycryptodome>=3.20`. **Instaladas**: ats-scrapers 0.3.0 · requests 2.34.2 · pydantic 2.13.4 · bs4 4.15.0 · pycryptodome 3.23.0 (venv). CI instala via `pip install -e .` do pyproject (sem `--no-deps` desde PR #48) + verify steps do expose e do pycryptodome — correto.
- **requirements-lock.txt**: snapshot do venv; diff vs pip freeze = só o ponteiro editable (aponta `26d2f98` antigo vs checkout `a92b6d5`) — drift conhecido e inerente ao mecanismo (não é lock declarativo; documentado). `hermes-agent==0.21.3` no venv (ferramenta do VPS, não do projeto) — poluição menor.
- **Upstream commit**: PR #268 do ats-scrapers NUNCA foi mergeado no upstream — a release 0.3.0 do PyPI (usada hoje) contém o expose. Risco: range `>=0.3.0` pode puxar 0.4.0 futura com breaking change (gate documentado P3 #30).
- **Sem uso**: nenhuma dependência declarada sem uso encontrada. `httpx` está no venv (transitiva do ats-scrapers).
- **Vulnerabilidades óbvias**: nenhuma checagem automatizada existe (sem `pip-audit`); requests/pydantic/bs4/pycryptodome atuais. Ação sugerida (não executada): adicionar pip-audit ao CI — baixo custo, mas é a única lacuna de dependências.

---

## 18. CI / tests audit

- **Array do CI**: 30 scripts — confere com `ls scripts/test_*.py` (30). CI main verde (runs 35730656253 / 35729211516 success em 22/09, pós-merge da Fase 8).
- **Execução independente em cwd scratch** (como o CI, `/tmp/suite_a` sem `data/`): **28/30 exit 0**. Os 2 exits 2 (`test_interface`, `test_ptbr`) expõem um defeito de **portabilidade do teste**: o gate de skip checa `ROOT/data/eligible_jobs.json` (existe no VPS) e então o subprocesso roda com `--input data/eligible_jobs.json` **relativo ao cwd** (que no scratch não existe) → `parser.error` exit 2. No CI o runner não tem `data/` de forma alguma, o gate dispara antes e o bloco real é pulado — por isso o CI é verde. Não é bug de produto, mas significa que **o bloco real dos 2 testes nunca roda no CI** (a validação real só acontece no VPS, fora de cwd scratch).
- **Cobertura funcional** (por leitura + execução): adapters/ranking/dedup/SQLite/archive/lifecycle/exit-codes/publish/HTML-JS (núcleo de filtros executado em node: 23+11 casos), app_intel/opportunity_intel/ptbr/materials/personal_tracker/digest/health/zero_return/identity/registry/benchmark — todos com suíte dedicada. 1.564 checks no total (log da Fase 8).
- **Funcionalidades CRÍTICAS sem teste**:
  1. **O gate de publicação sob exit 2** (o caso real de TODOS os dias) — nenhum teste cobre "coleta exit 2 + eligible > 0 → política de publicação"; o teste `test_pages_dir_integrado` usa exit 0.
  2. **Atribuição de erro por source compartilhado** (bug O3 vivo) — `test_refresh` não tem caso de 2 empresas no mesmo tenant com erro de uma delas.
  3. **Zero cobertura para "empresa que sempre teve vagas passa a dar error"** (O4) — o `zero_return` cobre `empty`, não `error`.
  4. Sanitização do JSONL (o incidente "Acme" é reincidente — 05/09 e 19–21/09).

## 19. Security audit

- **Secrets**: `.env` gitignored (600), nunca versionado (`git log --all -- .env` vazio); pickaxe `ghp_` acha só patterns de teste (token fake `ghp_01...0123` em test_publish_pages) — CONFIRMADO por `git show`.
- **Publicação**: gate `check_public_safe` (10 patterns de token + 6 fragmentos de caminho/arquivo) + verificação do blob publicado; gh-pages = só index.html; zero dado pessoal (testes de privacidade da Fase 8; banco pessoal nem existe ainda).
- **XSS via título/descrição/empresa (dados de ATS externos)**: **COBERTO** — 61 call sites de `html.escape` cobrindo todos os sinks de dados externos (title/company/location/type/chips/detalhes/intel/salário/fontes); URLs passam por `_safe_url` (scheme http/https ONLY, rejeita javascript:/data:) ANTES do escape, em todos os 6 pontos de href. Sonda no HTML gerado: nenhum atributo `on*=` de evento; entidades de anúncios chegam escapadas. Um título `<script>` serializa como texto — verificado pela função de escape aplicada em `title_esc` (1050) usada em todos os pontos de saída do título.
- **Links externos**: `target="_blank" rel="noopener"` em todos os links de anúncio/fonte — correto (sem tabnabbing).
- **Permissões VPS**: data/ 700 (ubuntu); jobs.db 644 mas dentro de data/ 700; backups dentro de data/. `.git-credentials` existe no HOME (uso do orquestrador) — fora do repo, não auditável pelo repo; risco padrão VPS, não do projeto.
- **Telegram**: token só no .env; mensagens não contêm dados pessoais (notas nunca saem — testado).
- **HTML injection via description em atributos**: descrição nunca vai a atributo (só texto escapado); `data-*` usam `_attr` (escape de aspas).

## 20. Performance audit (diagnóstico only)

| Métrica | Medição |
|---|---|
| Refresh total (cron) | 09:00:01 → 09:12:10 UTC ≈ **12 min** (coleta ~10 min p/ 127 fontes; soma de durações 520s → overhead de sequencialismo) |
| Por ATS | média 4,2s/tenant · máx 30,2s (Kaufland 17,7s; Lidl timeout 85s é o outlier crônico) |
| Geração do HTML | 4,1s @ 390 vagas |
| Tamanho HTML | **7,2 MB** @ 390 (publicado 21/09: 8,4 MB; Fase 1 era 472 KB — **17,8× em 4 dias**) |
| DOM nodes | 166.509 tags (públicado) — spans 71k, divs 65k |
| Escala projetada | 500 vagas: 9,1 MB/4,9s · 1.000: 18,2 MB/9,2s · 5.000: **91 MB/45,5s** |
| JS client-side | vanilla embutido (~30 KB?); filtros em O(n) sobre tabela estática — sem medição de runtime no cliente (não executado; DOM grande = custo de layout/render no mobile) |
| Gate P3 #22 | payload > 10 MB → dispara com **~555 vagas** (próximo documento a revisar) |

**Diagnóstico**: o gargalo iminente é o HTML monolítico (18 KB/vaga das seções recolhíveis das Fases 6–8). O teto de 10 MB do P3 #22 está a ~40% de distância. Nada foi otimizado (audit-only).

---

## 21. Production readiness ("o que está faltando para eu confiar no sistema?")

### Blockers (corrigir ANTES de confiar)

1. **B1 — Gates de publicação/digest/sync inertes** (exit 2 perpétuo × gate `exit_code==0`): a feature central do produto (ranking público diário) não opera sozinha há 17 dias. Política sugerida (decisão de dono): publicar quando `eligible > 0` e a coleta cobrir ≥ N% das fontes ok, ou tratar `exit 2` como publicável quando as falhas são as 3 documentadas periféricas (Lidl/K+N/SMA).
2. **B2 — Cobertura sem alarme**: queda de 17,9% do eligible (SAP −71) passou em silêncio; o alerta que existe ("Acme") é falso. Enquanto B2+O2/O3/O4 não forem corrigidos, o health não é confiável como detector de regressão.
3. **B3 — Sanitização do JSONL + prevenção de recontaminação** (mesmo incidente 2×).

### Important (não impedem uso, mas prejudicam a decisão)

- O5 German FNs por entidades HTML (2 casos reais no topo do ranking: STIHL #1) — correção barata.
- O8 descrições vazias (24% do dataset cego para German/WA/salário/skills) — testar `--include-descriptions` no cron (custo de tempo por tenant a medir).
- O6 salário estruturado recruitee + O10 aliases de cidade.
- O7 prazos textuais ("Bewerbungsfrist") — única fonte real de deadline employer hoje.
- O14 docs de automação (relatório Fase 8/README) descrevem comportamento inexistente.

### Nice to have

- Campo curado de visa policy por empresa no `company_intel` (fonte externa: páginas de carreiras/ Glassdoor) — o maior ganho de valor por esforço para o objetivo BR→DE, mas exige curadoria manual.
- Display name map para empresas técnicas (BoschGroup→Bosch).
- Desempate secundário informativo no ranking (descrição presente, posted_at mais recente).
- pip-audit no CI.
- Redução do HTML (lazy sections ou payload por vaga sob demanda) antes dos ~555 vagas.

### Deliberately deferred (documentado — não reabrir)

- Agregadores (LinkedIn/Indeed) — P3 #24, decisão de escopo.
- Embeddings/semantic dedup, LLM enrichment, feedback→pesos, forecasting — P4, exigem histórico.
- Retry próprio, ETag, behavioral mimicry, Knowledge Graph — descartados com motivo no MASTER_PLAN.
- Interface web de status pessoal no Pages — limitação estrutural (estático/público), CLI é a solução.
- Deadlines SF como prazo — regra correta, não mudar.

## 22. "O que eu NÃO deveria implementar?"

- **Auto-apply / bot de candidatura** — T&C das plataformas + complexidade enorme + zero alinhamento com "não é auto-apply" (AGENTS.md). NÃO.
- **Backend/DB no Pages ou segunda interface web** — a página é estática por design; o tracker CLI + Telegram já cobre o fluxo. NÃO.
- **Scraping de páginas de empresa para visa em tempo de coleta** — non-determinismo + rede + frágil; se quiser visa policy, CURATE no company_intel com fonte (determinístico, auditável). NÃO fazer o automático.
- **Tradução integral de descrições via LLM** — custo + não-determinismo + o glossário PT-BR de termos já entrega o essencial. NÃO agora.
- **Parser genérico de datas de deadline em texto livre** — alto risco de FP (datas de evento, "bis zum 15.10." de outra coisa); se extrair, só com padrão estrito ("Bewerbungsfrist: DD.MM.YYYY") + marcado como `employer_textual` separado. Cuidado.
- **Learning de pesos com o feedback pessoal** — já ratificado: feedback é collect-only; 476→390 vagas é base pequena demais. NÃO.
- **Postgres/Redis/queue** — SQLite resolve tudo medido até hoje. NÃO.
- **Whack-a-mole em nomes técnicos de empresa por regex** — mapa curado de display, ou nada.

## 23. Ações priorizadas (máx. 15)

| # | Ação | Risco/efeito | Esforço |
|---|---|---|---|
| 1 | **Reformular o gate de publicação/digest/sync** (política de dono: publicar com exit 2 quando falhas ⊆ documentadas, ou gate por % de fontes ok + eligible>0) + teste do caso exit 2 | Destrava Fases 1/2/8 de uma vez | Pequeno |
| 2 | **Sanitizar o JSONL** (remover 6 registros "Acme") + regra: validações sempre de cwd scratch | Mata alerta falso diário | Pequeno |
| 3 | **Corrigir atribuição de erro por source compartilhado** em `summarize_run` (nome do company DO registro de falha, não do primeiro do run) + teste com 2 empresas/1 tenant | Mensagens verdadeiras | Pequeno |
| 4 | **Alerta de cobertura para `error` em empresa com histórico ok>0** (extensão do zero_return) + teste | SAP nunca mais some em silêncio | Pequeno |
| 5 | `html.unescape` (+ strip de tags) no texto antes de `german_level`/`work_authorization` + testes dos 2 casos reais | FNs mortos no dataset | Pequeno |
| 6 | Mapear `raw.salary_*` no adapter/`job_salary` (recruitee) + teste | 3 salários reais recuperados | Pequeno |
| 7 | Avaliar `--include-descriptions` no cron (medir tempo/risco antes; talvez só para ATS sem descrição) | +24% de dataset visível | Médio |
| 8 | Extrair "Bewerbungsfrist: DD.MM.YYYY" como `deadline_kind=employer_textual` (regra estrita, nunca derivada) | ~20 deadlines reais | Médio |
| 9 | Aliases EN↔DE no location_intel (munich→munchen, cologne→koln, nuremberg→nurnberg) + teste | +14 vagas com custo de vida | Pequeno |
| 10 | Vocab WA: adicionar "arbeitsgenehmigung" + padrões "assist/support/übernehmen/hilfe ... visa/permit" que hoje caem em unclear + testes da sonda | Detector de support menos cego | Pequeno |
| 11 | Campo `visa_policy` curado no company_intel (12 empresas topo, com fonte+data) | O dado mais valioso p/ BR→DE | Médio (curadoria) |
| 12 | Atualizar PROJECT_STATUS/README/relatório Fase 8 §17 com o estado REAL da publicação (e refletir a nova política do item 1) | Docs honestas | Pequeno |
| 13 | Corrigir `test_interface`/`test_ptbr` bloco real (cwd do subprocesso = ROOT) para a suíte ser 100% reproduzível fora do repo | Suíte confiable | Pequeno |
| 14 | pip-audit no CI (job separado, non-blocking primeiro) | Visibilidade de CVEs | Pequeno |
| 15 | Curar display names das empresas técnicas do topo (BoschGroup→Bosch, teampicnic→TeamPicnic, bahagag→BAUHAUS) | UX sem regex frágil | Pequeno |

---
*Audit-only: nenhum arquivo de código/dados foi alterado durante esta auditoria. Único artefato produzido: este relatório. Evidências brutas citadas: run_info 22/09, /tmp/refresh_daily.log (3,7 MB), collection_metrics.jsonl, cópia read-only de jobs.db, HTML regenerado (7,2 MB) e publicado (8,4 MB), crontab, ci.yml + runs 35730656253/35729211516.*


### Nota sobre o processo
Baseline: main `a92b6d5` (22/09, pós-merge Fase 8), origin/main sincronizado, working tree limpa durante toda a coleta (único arquivo novo = este relatório, untracked). Os dados de produção (`data/`) são do run do cron 22/09 09:00 UTC; a auditoria terminou antes do próximo run (23/09 09:00 UTC), então nenhuma regeneração de `data/` ocorreu no meio — números reconciliados por run_id `2026-09-22T09:00:01.786915+00:00`. Sondas executadas sobre CÓPIA read-only do jobs.db; nenhum arquivo de código/dados alterado (audit-only).
