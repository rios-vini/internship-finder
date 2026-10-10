# Fase 4 — Segundo perfil: Materials Engineering (relatório)

**Data:** 2026-09-19 · **Branch:** `feature/fase4-materials-profile`

## Objetivo

Manter uma segunda possibilidade de busca alem do perfil principal
(Procurement / Supply Chain / BI / Analytics / Automation): um ranking de
**Materials Engineering** (Materials Science, Metallurgy, Polymer, Composites,
Ceramics, Metals, Surface Engineering, Corrosion, Failure Analysis,
Characterization, Materials Testing, Laboratory, Manufacturing, Production,
Process Engineering, Quality/R&D com contexto técnico) sobre **o mesmo
conjunto de vagas elegíveis** — sem nova coleta, sem novos filtros, sem alterar
a elegibilidade e sem alterar o ranking principal.

## Decisões de design (documentadas, mensuráveis)

1. **Perfil = módulo novo, score próprio** — `src/internship_finder/
   materials_ranking.py` adiciona `materials_score` + `materials_breakdown` a
   cada vaga; `score`/`score_breakdown` do principal NUNCA mudam (nunca
   `business + materials`). Verificado por id em todas as 476 vagas.
2. **Título manda, descrição corrobora** — descrição conta no máximo **1x por
   bloco** (calibração: templates de institutos, ex. Fraunhofer IGCV, citavam
   "Composite- und Verarbeitungstechnik" no rodapé e inflavam; medido 10,5
   pontos só de descrição antes do ajuste).
3. **Gate de contexto técnico** — Quality/R&D/lab/teste só pontuam quando o
   TÍTULO tem ≥1 termo de núcleo ou adjacente ("Sales Development", "Quality
   Engineer" de qualquer setor, "Sensory Analytics" NÃO pontuam como
   materiais).
4. **Penalidades só no título** — função de negócio (compras/SCM -1,5;
   logística/vendas/finanças/RH/jurídico/software/admin -1,0 por categoria);
   boilerplate de descrição ("MS Office", áreas organizacionais citando
   "Einkauf") não penaliza (medido: vaga real de bateria penalizada por
   menção da área organizacional antes do ajuste).
5. **"material(s)" solta nunca conta** — só compostos/frases explícitas:
   "Materialwirtschaft" (compras) e "Materialfluss" (logística) não pontuam.
6. **Sem IA/LLM/embeddings** — regex determinística sobre título+descrição;
   barata, reproduzível, explicável.
7. **Interface: mesma página, seletor de perfil** — `scripts/interface.py`
   gera UMA página com duas tabelas (mesma estrutura/JS da Fase 3; 476 linhas
   em cada perfil); `render_html` sem `materials` reproduz EXATAMENTE a página
   da Fase 3 (compat preservada). O JS client-side filtra/ordena a tabela do
   perfil ativo (núcleo puro inalterado, testado em node).
8. **Telegram: seção compacta** — `ranking_digest.py` computa o ranking
   materials sobre as mesmas vagas já carregadas (zero arquivo novo) e anexa
   "Perfil Materials Engineering" (Top 5 + novas no Top 30 Materials) à mesma
   mensagem; o link do ranking completo segue como última linha. Nada de
   reformulação do sistema de notificações (próxima fase se o dono quiser).

## Arquivos alterados/criados

| Arquivo | Mudança |
| --- | --- |
| `src/internship_finder/materials_ranking.py` | **novo** — perfil Materials (sinais, pesos, `materials_score_job`, `rank_materials_jobs`) |
| `scripts/interface.py` | seletor de perfil + segunda tabela + stats por perfil (Fase 3 intacta sem `materials`) |
| `scripts/ranking_digest.py` | seção "Perfil Materials Engineering" + linha do perfil secundário nos critérios |
| `scripts/test_materials_ranking.py` | **novo** — 39 checks offline + bloco real (no CI, array 25→26) |
| `scripts/test_interface.py` | +22 checks (dual render, bloco real 2 tabelas, guarda ACTIVE) |
| `scripts/test_digest.py` | +9 checks (materiais: ordem, top próprio, novas, sem snapshot) |
| `.github/workflows/ci.yml` | array 25→26 scripts |
| `README.md` / `docs/architecture.md` / `AGENTS.md` | docs atualizadas (dois perfis) |
| `MASTER_PLAN.md` / `PROJECT_STATUS.md` | registro da Fase 4 (ver pós-merge) |

## Sinais positivos utilizados

- **Núcleo** (título +2,5/termo; descrição corrobora +1,0): materials
  engineering/science/testing/characterization, materialwissenschaft,
  -technik, -kunde, -prüfung, werkstoff*, metallurg*, metals, steel,
  aluminium, alloy*, polymer*, plastics, kunststoff*, spritzguss, injection
  molding, composite*, ceramic*, keramik*, corrosion, korrosion, surface
  engineering/technology, oberflächentechnik, coating, beschichtung, failure
  analysis, schadensanalyse, characterization, NDT/non-destructive.
- **Adjacentes** (título +1,25; descrição +0,5): manufacturing/Fertigung,
  production/Produktion, process engineering, prozesstechnik,
  verfahrenstechnik, mechanical/Maschinen, industrial engineering,
  battery/Batterie, electrolysis, fuel cell, semiconductor/Halbleiter,
  chemistry/Chemie, additive manufacturing/3D print, anlagenbau, laboratory/
  Labor, laser, presswerk, catalysts/Katalysator, welding/Schweiß.
- **Contexto (gate técnico)** (título +0,75; descrição +0,5): Quality/Qualität,
  R&D/research/Forschung, development/Entwicklung, testing/Versuch/Prüfung,
  characterization.

## Sinais negativos

- **Função de negócio no título**: compras/SCM (Einkauf, Purchasing,
  Procurement, Supplier, Sourcing, Beschaffung, Supply Chain) **-1,5**;
  logística/transport/warehouse/inventory, sales/marketing/customer,
  finance/controlling, HR/People, legal/compliance/risk, software/IT/cloud,
  office/administration **-1,0** (por categoria, uma vez).
- **Não-sinais**: "student/engineering/internship/manufacturing" sozinhos;
  palavra solta "material(s)"; descrição não abre o gate de contexto.

## Fórmula do score

```
materials_score = materials + adjacent + context + type + location + penalties
```

Blocos `materials`/`adjacent`/`context` = termos únicos no título × peso do
bloco + (1 × peso-desc se a descrição tiver ≥1 termo do bloco). `context` só
com ≥1 termo de núcleo/adjacente NO TÍTULO. `type` +1,0 (marcador estudantil
no título, mesma regra do principal). `location` DE +1,0 / Berlin +0,5.
`penalties` conforme acima (título apenas). Desempate: score desc → título →
empresa → id (mesmo critério do principal).

## Validação (dados reais do run 19/09, 476 elegíveis)

1. Quantidade elegível permanece igual: **476/476** (mesmo arquivo, nada
   recolhido/filtrado).
2. Ranking principal: **intacto** (score/breakdown por id, 476/476).
3. Ranking Materials gerado: **sim** (476 com `materials_score`).
4. Posições independentes: **Top 30 principal ≠ Top 30 Materials** (1 id em
   comum na verificação do run 18/09; ordens diferentes).
5. Vagas claramente de materiais no topo: **sim** — #1 HELLA "Operations
   Processes Development POLYMER" (7,25), #2 Fraunhofer "Prozessentwicklung
   Beschichtung" (7,25), #3 BASF "Verfahrenstechnik & chemische
   Prozessoptimierung" (6,5), #5 BMW "Batteriezellfertigung", #7 VW
   "Battery Cell Technology Development", #8 Fraunhofer "Testung von
   Katalysatoren".
6. Engenharia genérica NÃO domina: documentos com só "Engineering" ficam na
   base de score (~2,0), abaixo de todas as técnicas; o topo exige sinais de
   materiais.
7. Vagas sem relação não recebem score artificial: topo do principal
   ("Praktikum Data Analytics / Data Science", 17,5 business) cai para #215
   materials; graduate programs e controlling/HR no fundo (scores negativos).
8. Breakdown honesto: `total == soma(componentes)` checado no top 1 e em
   testes; interface exibe só componentes implementados.
9. Filtros/links: 21+ links http/https da página OK; filtros client-side
   verificados por perfil (jsdom: baterie→3, empresa BMW→81 no perfil
   materials); núcleo JS 23/23 casos em node.
10. GitHub Pages: publicado pós-merge neste dia (URL estável abaixo).
11. Atualização diária: cron 06:00 BRT continua gerando/publicando a mesma
    página (agora com os dois perfis — o run 19/09 09:00 UTC já passou pelo
    fluxo novo).

## Falsos positivos encontrados (amostra Top 20 — inspeção manual)

- "Working Student - Discrete Manufacturing Industries" (SAP, ×2) — termo
  "Manufacturing" vem do RÓTULO DE INDÚSTRIA do SAP, não da função; caiu nas
  proximidades de #26-27 (topo não contaminado). Ajuste objetivo rejeitado de
  propósito: seria whack-a-mole de um rótulo específico; o breakdown mostra o
  componente "Manufatura/Processo" e o dono pode decidir na Fase 5.
- "Praktikant Einkauf Aluminium"/"Einkauf Spritzguss" (BMW) — função comercial
  + termo de material; núcleo 3,5 - penalidade 1,5 → #9-10. É defesa legítima
  (a MATÉRIA é o produto) e o breakdown é transparente.
- Café Fraunhofer IGCV: descrição com nome do instituto ("Composite- und
  Verarbeitungstechnik") corrobora +1,0 — limitado a 1x por calibração.
- "Sensory Analytics" (food science) — não recebe mais crédito de
  characterization (movido para contexto com gate); caiu de #12 para #34+.

## Confirmação de não-regressão do perfil principal

`git diff` em `src/internship_finder/ranking.py`, `filters.py`, `dedup.py`,
`cli.py` = **0**; `test_ranking.py`/`test_dedup.py`/`test_filters.py` verdes
sem alteração. Suíte local **26/26 OK** (25 anteriores + test_materials_ranking).

## URL

https://rios-vini.github.io/internship-finder/ (botões
[ Procurement / Supply Chain ] [ Materials Engineering ])

## Pendências registradas (Fase 5)

- Tradução/resumo PT-BR e melhoria da explicação das vagas (Fase 5 do plano).
- Telegram: se o dono quiser envio dedicado de vagas novas por perfil, isso
  exige reforma do sistema de notificações — documentado, fora desta fase.