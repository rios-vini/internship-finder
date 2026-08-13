# Relatório Final Pós-Correções + Novo Parecer (gate para o SQLite)

**Data:** 2026-08-13 · **Branch:** `feat/relatorio-final-pos-correcoes` (base `main` 0968c2a) ·
**Escopo:** consolidação das Fases 1–3 (correções controladas do parecer B) + classificação
manual do Top 20 final + **novo parecer A/B/C**. Nenhuma alteração de código de produção;
apenas análise, medição e documentação. Scripts de análise em `/tmp` (não commitados).

**Fonte dos dados:** `data/jobs.json` (56.810 brutas, coleta E2 de 2026-08-12 04:52 UTC),
`data/eligible_jobs.json` e `data/ranked_jobs.json` (293, gerados pelo pipeline real
`internship-finder` nesta sessão — re-executado em 2026-08-13). Relatórios de fase lidos:
`docs/relatorio_fase1_ruido_tipo.md`, `docs/relatorio_fase2_phenom.md`,
`docs/relatorio_fase3_workday.md` e baseline `feat/auditoria-pos-expansao:docs/auditoria_pos_expansao.md`.

---

## 1. Estado final medido (pipeline real, re-executado nesta sessão)

Comando: `.venv/bin/internship-finder --input data/jobs.json --output data/eligible_jobs.json`
Saída real (cascata):

```
=== Cascata de filtros ===
  total            : 56810
  + tipo estudante : 3428
  + area-alvo      : 777
  + pais           : 309   (--country de)
dedup: removidas 16 (0 por external_id, 0 por URL, 16 por company+title+location)

=== 293 vagas eligible, ranqueadas por perfil ===
```

**Funil final:** 56.810 → 3.428 (tipo) → 777 (área) → 309 (país DE) → dedup −16 → **293 eligible**.
`data/eligible_jobs.json` e `data/ranked_jobs.json` contêm os 293 ranqueados (idênticos; md5
`37fb2920534433d806334598dd95df4f`).

### 1.1 Distribuição por empresa (293)
| # | Empresa | Eligible | % |
| --- | --- | ---: | ---: |
| 1 | SAP | 91 | 31,1% |
| 2 | lidlstiftup2 (Lidl) | 48 | 16,4% |
| 3 | BoschGroup | 39 | 13,3% |
| 4 | Volkswagen AG | 25 | 8,5% |
| 5 | Knorr-Bremse | 18 | 6,1% |
| 6 | BASF SE | 18 | 6,1% |
| 7 | Schaeffler Technologies | 12 | 4,1% |
| 8 | B. Braun Melsungen | 5 | 1,7% |
| 9 | Telekom Growthhub | 5 | 1,7% |
| 10 | Infineon | 5 | 1,7% |
| 11 | henkel | 4 | 1,4% |
| 12 | careers.dhl.com (DHL) | 4 | 1,4% |
| 13 | celonis | 4 | 1,4% |
| 14 | Bayer | 4 | 1,4% |
| 15 | Kaufland | 3 | 1,0% |
| 16 | MAHLE International | 3 | 1,0% |
| 17 | Brose | 2 | 0,7% |
| 18 | continental | 1 | 0,3% |
| 19 | ZF Friedrichshafen | 1 | 0,3% |
| 20 | Uniper | 1 | 0,3% |

20 empresas distintas; top-5 = 191 vagas (65,2%).

### 1.2 Distribuição por ATS (prefixo do `source`)
| ATS | Eligible | % de 293 |
| --- | ---: | ---: |
| successfactors | 229 | 78,2% |
| smartrecruiters | 40 | 13,7% |
| eightfold | 12 | 4,1% |
| cornerstone | 4 | 1,4% |
| phenom | 4 | 1,4% |
| greenhouse | 4 | 1,4% |
| workday | 0 | 0% (limitação documentada, §4) |

### 1.3 Distribuição por país
293/293 `country_iso='de'` (filtro DE; nenhum ISO None/junk no eligible — §5).

### 1.4 Scores
**min 2.00 | mediana 6.00 | max 16.00** (F1: min 2.0 | mediana 6.25 | max 16.0; E2: min 1.0 |
mediana 6.0 | max 16.0). Ranking intocado nas 3 fases — a distribuição reflete só o conjunto.

---

## 2. Antes/depois — evolução do funil por fase

| Métrica | E2 (main) | F1 (2f6055d) | F2 (4c3cfa6) | F3 (0968c2a) | Final (hoje) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Brutas | 56.810 | 56.810 | 56.810 | 56.810 | 56.810 |
| Tipo estudante | 4.995 | 3.428 | 3.428 | 3.428 | 3.428 |
| Área-alvo | 914 | 777 | 777 | 777 | 777 |
| País DE | 406 | 299 | 309 | 309 | 309 |
| Dedup | −17 | −16 | −16 | −16 | −16 |
| **Eligible** | **389** | **283** | **293** | **293** | **293** |

**Delta por fase:** 389 → 283 (**F1, −106** = −27,2%: ruído de tipo) → 293 (**F2, +10**:
DHL/celonis/Bayer recuperadas pelo fix de país) → 293 (**F3, 0**: só qualidade de país,
junk eliminado).

---

## 3. Fase 1 — removidas por categoria (106)

| Categoria | Qtde |
| --- | ---: |
| Duales Studium e equivalentes | 89 (2 delas com "Ausbildung" também no título) |
| Ausbildung / Berufsausbildung (puras) | 11 |
| Schülerpraktikum / Schülerpraktikant | 6 |
| **Total** | **106** |

(No agregado da categoria "Ausbildung": 13 = 11 puras + 2 que também são dual.)
Por empresa: Lidl −55 (103→48), VW −17 (42→25), Schaeffler −13 (25→12), Kaufland −10
(13→3), MAHLE −4 (7→3), BASF −3 (21→18), B. Braun −3 (8→5), ZF −1 (2→1); SAP intacta (91).

---

## 4. Fase 2 e Fase 3 — recuperadas e limitações

### F2 — recuperadas: DHL 0→4 (Phenom) e outras +10 no total
O fix genérico de país (nome do país no último segmento da location, `COUNTRY_NAMES`)
recuperou no eligible, além da DHL, vagas de outros ATS com a mesma assinatura de location:
- **DHL (phenom): 0 → 4** — todas reais (Internship Sourcing Tools; Werkstudent Operations
  Support; Intern/Praktikant HR Data & Systems), scores 4.0–6.0, nenhuma dual/ausbildung.
- **celonis (greenhouse): 0 → 4** — location "Munich, Germany" (intern/associate, 3.0–4.75).
- **Bayer (eightfold): +2** — "Werkstudent*in Digitalisierung" e "Werkstudent*in Marketing &
  Sales / Radiologie" (4.0–4.75).
- **Total F2: 283 → 293 (+10)**, todos reais (estudante/estágio), sem ruído de tipo.
  Composição verificada do +10: 4 DHL (phenom) + 4 celonis (greenhouse) + 2 Bayer (eightfold) —
  os três grupos voltaram pelo mesmo fix genérico (nome de país no fim da location).
- *Nota de precisão:* o relatório F2 estimou "~10 DHL após dedup"; a verificação final desta
  sessão mostra **4 DHL** no eligible (as outras +6 são celonis/Bayer). O número oficial é o
  verificado: DHL 4, total +10.
- *Observação de transparência (limitação pré-existente do dedup, não regressão):* 2 das vagas
  Bayer recuperadas ("Werkstudent*in Digitalisierung" e "Werkstudent*in Marketing & Sales /
  Radiologie") são o **mesmo posto publicado em dois ATS** (eightfold e successfactors) com
  strings de location levemente diferentes ("Bitterfeld-Wolfen,Saxony-Anhalt,Germany" vs
  "Bitterfeld-Wolfen, Sachsen-Anhalt, DE") — o dedup por chave exata company+title+location
  não as une. Não afetam o Top 20 (scores 4.0–4.75). Registrado aqui como nota, não como
  correção pendente.

### F3 — Workday: 0→0 com limitação documentada
A API Workday (9 tenants, 2.516 brutas) **não expõe país** (cidade sozinha) para a maioria das
vagas. Sem dado de país, inferir seria inventar (proibido pelo dono). **Limitação documentada:**
vagas Workday sem país explícito continuam fora do eligible DE até a API/coletor expor o país.
Nenhum código falso é fabricado para mascarar isso.

---

## 5. ISOs falsos corrigidos (qualidade de país, não contagem)

| Fase | Escopo | ISOs falsos eliminados | Exemplos |
| --- | --- | ---: | --- |
| F2 | Phenom (junk do scan antigo) | **496** (247 falsamente `de`) | `am` (Remseck am Neckar), `im` (Staufen im Breisgau), `de`→`mx` (Cienega de flores, Mexico), `la`→`fr`/`cr` |
| F3 | Workday (junk do scan antigo) | **168** (11 falsamente `de`) | `im` (Freiburg im Breisgau), `do` (São Bernardo do Campo), `de` falso (Ecatepec, Estado de México) |

`_iso_token_from_location` (F3) só aceita token de 2 letras em posição confiável (último
segmento ou antes de CEP) — elimina o junk **em todos os ATS**. Limite conhecido documentado:
sigla de estado US como último segmento colide com ISO válido (`Lafayette, IN` → `in`), nunca
produz `de`. **Eligible atuais que mudaram de ISO: 0** (verificado em F2 e F3) — o fix é
puramente de qualidade do dado bruto.

---

## 6. Top 20 final (293) — scores, breakdown e classificação manual

Classificação: **A** = match claro (4 áreas do perfil + estudante) · **B** = relevante com
ressalva · **C** = fraca · **D** = falso positivo. Re-verificada manualmente nesta sessão
título por título (fonte: `data/ranked_jobs.json`).

| # | Score | Classe | Vaga | Empresa | Breakdown resumido (area/skills/lang/tipo/loc/pen) |
| --- | ---: | --- | --- | --- | --- |
| 1 | 16.00 | **A** | Werkstudent Data Analytics & Logistics | Knorr-Bremse | 12/0/2/1/1/0 |
| 2 | 13.50 | **A** | Pflichtpraktikum Logistik - Schwerpunkt Data & Analytics | Bosch | 12/0/0/1/1/−0.5 |
| 3 | 13.50 | **A** | Praktikum in der Logistik - Data & Analytics | Bosch | 12/0/0/1/1/−0.5 |
| 4 | 13.50 | **A** | WS Analytics: AI Enablement & Automation | SAP | 8/1.5/2/1/1/0 |
| 5 | 12.75 | **A** | Praktikant Purchasing Controlling, Data Analytics, Supplier Mgmt | Knorr | 8/0.75/2/1/1/0 |
| 6 | 12.25 | **A** | WS Supply Chain International - Data & Prototyping | Lidl | 8/0.75/1.5/1/1/0 |
| 7 | 12.25 | **A** | WS Technology in Global Procurement Organization | SAP | 6/2.25/2/1/1/0 |
| 8 | 12.00 | **A** | Hochschulpraktikum Prozessoptimierung im Einkauf | B. Braun | 10/0/0/1/1/0 |
| 9 | 11.50 | **A** | Praktikanten Business Intelligence & Analytics | Knorr | 6/1.5/2/1/1/0 |
| 10 | 11.50 | **A** | Praktikum Logistik und Supply Chain Design | Bosch | 10/0/0/1/1/−0.5 |
| 11 | 11.50 | **D** | SAP iXp Intern - Event Showcase Operations Support | SAP | 6/1.5/2/1/1/0 — eventos/showcase, não é das 4 áreas; "Operations" genérico. **Pré-existente** (baseline parecer B #11). |
| 12 | 10.75 | **A** | Freiwilliger Praktikant strategischer Indirekter Einkauf | Knorr | 6/0.75/2/1/1/0 |
| 13 | 10.75 | **B** | Praktikum Analytics After Sales | VW | 6/0.75/2/1/1/0 — analytics real, contexto pós-venda |
| 14 | 10.75 | **A** | Praktikum Data Analytics & Digitalisierung | Lidl | 8/0.75/0/1/1/0 |
| 15 | 10.75 | **B** | Praktikum Data Analytics - Digital Workflows Aktionsplanung | Lidl | 8/0.75/0/1/1/0 — analytics, contexto promoções |
| 16 | 10.75 | **B** | Praktikum Lidl Plus - Customer Data & Analytics | Lidl | 8/0.75/0/1/1/0 — BI real, contexto customer/marketing |
| 17 | 10.75 | **C** | SAP MEE Strategy & Operations iXp - Strategic PM | SAP | 6/0.75/2/1/1/0 — strategy/PM, fora das 4 áreas (pré-existente) |
| 18 | 10.75 | **B** | WS Solution Advisory / Presales - Fokus Supply Chain | SAP | 6/0.75/2/1/1/0 — presales com foco real em SC |
| 19 | 10.75 | **A** | WS Strategischer Einkauf Electronics / Commodity Mgmt | Knorr | 6/0.75/2/1/1/0 |
| 20 | 10.75 | **B** | WS Analytics After Sales | VW | 6/0.75/2/1/1/0 — mesmo caso do #13 |

**Resultado: 13 A · 5 B · 1 C · 1 D** — **idêntico ao baseline do parecer B** (Top 20 do
conjunto de 389: mesmas 20 vagas, mesma ordem, mesmos scores). As fases 1–3 não alteraram
ranking nem removeram nenhuma vaga do Top 20.

### 6.1 As 4 áreas seguem representadas?
| Área | Posições no Top 20 | Avaliação |
| --- | --- | --- |
| Supply Chain | #1, #2, #3, #6, #10 (+ #18 presales SC, B) | 5–6/20, bem posicionadas ✓ |
| Procurement / Einkauf | #5, #7, #8, #12, #19 | 5/20, todas A ✓ |
| BI / Analytics | #1, #4, #5, #9, #13, #14, #15, #16, #20 (sobreposição) | 9/20, a mais representada ✓ |
| Automação / Process Excellence | #4 (AI Enablement & Automation), #8 (Prozessoptimierung im Einkauf) | 2 explícitas — a mais fraca, sem regressão vs. baseline ✓ |

### 6.2 Comparação com o Top 20 da Fase 1 (283)
O relatório F1 (§4) registrou o mesmo Top 20 ("o topo ficou inalterado; nenhum título do Top 20
antigo saiu"; as 4 áreas seguem representadas). A comparação Fase 1 → Final é trivialmente
**sem piora**: F2 adicionou 10 vagas com scores 3.0–6.0 (todas fora do Top 20) e F3 não mudou
nada — o Top 20 final é byte a byte o mesmo da Fase 1 e do parecer B.

### 6.3 Falsos positivos novos?
**Nenhum falso positivo novo no Top 20** (idêntico ao baseline). Fora do topo (cauda, score ≤ 3),
todos os suspeitos são **pré-existentes** (já estavam no conjunto de 389, documentados no parecer
B): Lidl "Praktikum Marketing/Reisen/Talkability/Warengeschäft" (area 0, entram por tipo+país),
BASF Abschlussarbeit/Bachelor, VW "Unsolicited application". Nenhum veio das correções.
Observação de transparência: 7 títulos de programa de graduação pré-existentes (2 Schaeffler
"Studium mit vertiefter Praxis" + 5 BASF "Bachelor of Science/Arts/Engineering") seguem no
eligible com `internship=True` vindo da API e scores 2.5–4.5 (fundo da cauda) — **fora dos
padrões explícitos aprovados na F1** (que cobrem dual/ausbildung/schüler); são candidatos a
uma eventual extensão de padrões, **não** uma regressão das correções.

---

## 7. Critérios de aceitação do dono — um a um, com evidência

- **(a) Qualidade do Top 20 não piorou** ✅ — Top 20 final idêntico ao baseline do parecer B
  (13A/5B/1C/1D, mesmas posições/scores); 0 falsos positivos novos no topo; as 4 áreas seguem
  representadas (§6). Comparação com F1: mesmo Top 20.
- **(b) Sem regressão de adapters/empresas** ✅ — 0 mudanças de ISO nos eligible (F2: "0 dos 283
  eligible atuais mudaram de ISO"; F3: "eligible atuais que mudam de iso: 0"); suíte 7/7
  re-executada nesta sessão com exit 0 (test_dedup, test_fetch, test_filters,
  test_find_company, test_manifest, test_ranking, test_resolver).
- **(c) Nenhum país inferido de forma insegura** ✅ — todo ISO novo vem de nome de país explícito
  na location (F2) ou token de 2 letras em posição confiável (F3), sempre membro de
  `COUNTRY_CODES`; locais Workday sem país ficam `None` (documentado, nunca inventado);
  limite conhecido `Lafayette, IN` documentado.
- **(d) Nenhum ATS vazou para filters/ranking** ✅ — correções só na inferência de país
  (`infer_country_iso`/`_iso_token_from_location`/`COUNTRY_NAMES`); filtros de área/tipo e o
  ranking intocados nas 3 fases (diffs dos PRs #3/#4/#5: apenas `filters.py` + testes + docs).
- **(e) Aumento sem ruído** ✅ — F2 +10: 4 DHL reais (sem dual/ausbildung; scores 4–6) + 4
  celonis + 2 Bayer; verificação direta: **0 títulos do eligible casam com
  `TYPE_EXCLUSION_PATTERNS`** (sanity F1 re-executado nesta sessão → 0 ruído).
- **(f) Pipeline determinístico** ✅ — re-execução nesta sessão produziu `eligible_jobs.json`
  com md5 idêntico ao pré-existente (`37fb2920534433d806334598dd95df4f`); verificado também
  2× anteriormente (md5 `a4810790` citado pelo lead; F1: `523fa1c7...`). Funis idênticos
  (56810 → 3428 → 777 → 309 → −16 → 293) nas execuções F2/F3/hoje.

---

## 8. NOVO PARECER: **A — pronto para o SQLite**

Justificativa (curta e honesta): as 3 correções controladas foram entregues e verificadas —
ruído de tipo zerado (−106, 0 dual/ausbildung/schüler no eligible), DHL recuperada 0→4
(+10 total reais), país seguro em todos os ATS (664 ISOs falsos eliminados, 0 mudanças nos
eligible), Workday com limitação documentada em vez de inferência inventada. A qualidade do
Top 20 **não piorou** (idêntico ao baseline: 13A/5B/1C/1D, sem falsos positivos novos), a
suíte 7/7 passa, o pipeline é determinístico (md5 idêntico em re-execução) e nenhum ATS vazou
para filtros/ranking. O dataset de 293 representa corretamente "eligible" sob as regras
ratificadas — **pode iniciar o SQLite (backlog aa5996fe)**.

Ressalvas de transparência (não bloqueiam; todas pré-existentes ou externas): (1) Workday 0
eligible — limitação externa da API, documentada por decisão do dono; (2) 7 títulos de
programa de graduação na cauda (Schaeffler SmvP, BASF Bachelor, scores 2.5–4.5) fora dos
padrões aprovados na F1 — sugerir extensão futura de padrões se o dono quiser cauda 100%
limpa; (3) os 4 collectors que falham (Hager/Boehringer/Lanxess/Symrise) são limitações
externas conhecidas do parecer B — **não entram neste parecer**.

---

## Referências
- `docs/relatorio_fase1_ruido_tipo.md` (389→283, −106 por categoria) · PR #3 (2f6055d)
- `docs/relatorio_fase2_phenom.md` (283→293, DHL, COUNTRY_NAMES, 496 junk) · PR #4 (4c3cfa6)
- `docs/relatorio_fase3_workday.md` (293 estável, `_iso_token_from_location`, 168 junk) · PR #5 (0968c2a)
- `feat/auditoria-pos-expansao:docs/auditoria_pos_expansao.md` (parecer B, Top 20 = 13A/5B/1C/1D)
- Dados: `data/jobs.json` (56.810), `data/eligible_jobs.json` e `data/ranked_jobs.json` (293)
