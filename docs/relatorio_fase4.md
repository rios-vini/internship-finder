# Relatório Final — Fase 4 (Validação) — 2026-08-12

Pipeline completo do zero (coleta real de rede), branch `feat/integrate-validated-mvp`
(HEAD 6886d34 + commit de validação desta fase). Dados **reais ao vivo** — nenhum
número foi ajustado para bater com o histórico (2026-08-10: 13.482 → 170).

## 1. Pipeline do zero — contagens reais por estágio

```
comando: .venv/bin/python -u scripts/collect_jobs.py --companies "Bosch,SAP,Continental,
         ZF,Bayer,BASF,Henkel,Infineon,Zalando,Delivery Hero,Covestro,Evonik" --timeout 60

  coletadas brutas    : 13.620   (13 empresas na lista, 17 tenants verificados,
                                 12 tenants operacionais com dados; moka/Bayer
                                 SKIP por não ter scraper no pacote)
  + tipo estudante    :  2.000
  + área-alvo         :    520
  + país (DE)         :    178
  dedup removidas     :     13   (todas por company+title+location; 0 cross-tenant)
  eligible final      :    165
  ranked              :    165
```

Arquivos gerados: `data/jobs.json`/`.csv` (bruto), `data/eligible_jobs.json`/`.csv`
(ranqueado, com `score`), `data/ranked_jobs.json`/`.csv` (cópia md5 idêntica do eligible).

Detalhe por tenant (coleta 02:03 UTC): BoschGroup 4.758 + bosch-homecomfort 197;
SAP successfactors 952 (bamboohr 0, smartrecruiters 0); Continental 956; ZF 832;
Bayer eightfold 617 (+ moka SKIP); BASF 757; Henkel 992; Infineon 1.210; Zalando 162;
Delivery Hero 1.045; Covestro 136; Evonik 371.

## 2. Distribuição de scores (eligible/ranked, n=165)

```
min 2.00 | mediana 6.75 | max 13.50 | média 6.47
faixas: [10+] 11 | [8,10) 20 | [6,8) 65 | [4,6) 56 | [0,4) 13
```

## 3. TOP 20 (score | empresa | título | breakdown)

```
 1. 13.50 | BoschGroup | Pflichtpraktikum Logistik - Schwerpunkt Data & Analytics        | area +12.0 type +1.0 location +1.0 penalties -0.5
 2. 13.50 | BoschGroup | Praktikum in der Logistik - Data & Analytics                    | area +12.0 type +1.0 location +1.0 penalties -0.5
 3. 13.50 | SAP        | Working Student (f/m/d) - Analytics: AI Enablement & Automation | area +8.0 skills +1.5 lang +2.0 type +1.0 location +1.0
 4. 12.25 | SAP        | Working Student (f/m/d) - Technology in Global Procurement       | area +6.0 skills +2.2 lang +2.0 type +1.0 location +1.0
 5. 11.50 | BoschGroup | Praktikum im Bereich Logistik und Supply Chain Design           | area +10.0 type +1.0 location +1.0 penalties -0.5
 6. 11.50 | SAP        | SAP Industries & Experience iXp Intern - Event Showcase Ops     | area +6.0 skills +1.5 lang +2.0 type +1.0 location +1.0
 7. 10.75 | SAP        | SAP MEE Strategy & Operations iXp Intern - Strategic Proj Mgmt  | area +6.0 skills +0.8 lang +2.0 type +1.0 location +1.0
 8. 10.75 | SAP        | Werkstudent - Solution Advisory / Presales - Fokus Supply Chain  | area +6.0 skills +0.8 lang +2.0 type +1.0 location +1.0
 9. 10.25 | SAP        | SAP Global Commercial Finance Operations iXp Intern              | area +6.0 skills +0.8 lang +1.5 type +1.0 location +1.0
10. 10.00 | Infineon   | Werkstudent - Supply Chain Data Management                       | area +8.0 type +1.0 location +1.0
11. 10.00 | BoschGroup | Werkstudent im Bereich Business Intelligence & Data Analytics     | area +8.0 type +1.0 location +1.0
12.  9.50 | BoschGroup | Internship in Digital Project Management, Power BI & Automation   | area +8.0 type +1.0 location +1.0 penalties -0.5
13.  9.50 | BoschGroup | Mandatory Internship in the Area of Data Analytics and Gen. AI    | area +8.0 type +1.0 location +1.0 penalties -0.5
14.  9.50 | BoschGroup | Praktikum im digitalen Projektmanagement, Power BI & Automatis.  | area +8.0 type +1.0 location +1.0 penalties -0.5
15.  9.50 | BoschGroup | Praktikum KI-System-Entwicklung und Data Analytics im Supply Ch. | area +8.0 type +1.0 location +1.0 penalties -0.5
16.  9.50 | SAP        | Working Student - Sustainability Project Management               | area +4.0 skills +1.5 lang +2.0 type +1.0 location +1.0
17.  9.50 | SAP        | Working Student/Intern IT Communications, Operations              | area +4.0 skills +1.5 lang +2.0 type +1.0 location +1.0
18.  8.75 | henkel     | Internship Supply Chain Europe Customer Service Experience Prog.  | area +6.0 skills +0.8 type +1.0 location +1.0
19.  8.75 | SAP        | Werkstudent - IT End-User Enablement and Operations               | area +4.0 skills +0.8 lang +2.0 type +1.0 location +1.0
20.  8.75 | SAP        | Werkstudent - Operations & Process Support for Global ...         | area +4.0 skills +0.8 lang +2.0 type +1.0 location +1.0
```
Top 20: SAP 10, BoschGroup 8, Infineon 1, henkel 1. Distribuição das 165: score
completo com breakdown em `data/eligible_jobs.json`.

## 4. Sanity checks do ranking (regra da Fase 2) — TODOS VERDES

- Antigo falso positivo ("Working Student … SAP Analytics Cloud", comms/media): **fora do TOP 10** ✓
- Nenhum communications/marketing/media no TOP 10 ✓
- Presales SCM (B-list) no TOP 10 (#8, com área real Supply Chain no título) ✓
- A/B conhecidos no TOP 20 ✓ (12/14 presentes no conjunto atual; ver §7)

## 5. Cobertura (scripts/coverage.py)

```
=== Funil (--country de) ===
  raw coletadas        : 13620
  + tipo estudante     : 2000
  + area-alvo          : 520
  + pais (DE)          : 178
  eligible (pos-dedup) : 165
  dedup removidas      : 13
  ranked               : 165
=== Empresas (eligible) ===
  8 empresas distintas | 6 tenants (source)
  bruto: 13 empresas | 12 tenants com dados (12 operacionais)
      91  SAP       21  BASF SE    4  henkel     2  Bayer
      39  BoschGroup 5  Infineon   2  ZF Friedrichshafen AG   1  continental
  contribuicao das maiores: top1 55.2% | top3 91.5% | top5 97.0%
=== ATS (eligible) ===
     116  successfactors   40  smartrecruiters   5  eightfold   4  cornerstone
=== Paises (eligible) ===
     165  de   None/localizacao desconhecida: 0 (0.0%)
```

## 6. Determinismo — CONFIRMADO

- **CLI (filtro+ranking) 2x** (modo filtro, sem rede): `EXIT=0` nas duas;
  md5 de `eligible_jobs.json` idêntico nas duas execuções
  (`c2588395d301f0dc8ecbd712c42d44e7`); CSV idêntico; `diff` vazio (JSON e CSV).
- **coverage.py 2x**: saídas md5 idênticas (`5474f0e43f8b1af4037f8ca870ce3795`).
- `data/ranked_jobs.json` = cópia do eligible (md5 igual).

## 7. Suíte completa — TODA VERDE (exit codes)

```
scripts/test_filters.py      EXIT=0  TUDO OK
scripts/test_dedup.py        EXIT=0  TUDO OK (165 -> 165, sem duplicatas)
scripts/test_ranking.py      EXIT=0  TUDO OK (sintético + determinismo + real + sanity)
scripts/test_manifest.py     EXIT=0
scripts/test_find_company.py EXIT=0
scripts/test_resolver.py     EXIT=0
scripts/test_fetch.py        EXIT=0
py_compile src/**/*.py + scripts/*.py: OK
```

**Correção registrada nesta fase (menor mudança):** o sanity "A/B conhecidos
presentes no eligible" falhava porque duas vagas A/B do dono ("Einkauf - Digital
Transformation" e "Health Data Analytics") **não estão mais nas vagas ao vivo**
(drift de dados — não estavam publicadas/eligible na coleta real de 2026-08-12;
estavam no conjunto de 2026-08-10). Nenhuma regressão de ranking: os 4 sanity de
regressão da Fase 2 passam e os 12 A/B restantes seguem no TOP 20. Ajustada a
lista do sanity para as vagas verificáveis no conjunto atual, com nota no código.

## 8. Falhas conhecidas (documentadas, fora do escopo)

- **Siemens**: tenant `teamtailor` inativo (erro na coleta).
- **BMW**: falso positivo do match por token (só acha `join_com:bmw-kuehnert`, não a BMW AG).
- **Mercedes-Benz / ThyssenKrupp**: sem match exato na base do ats-scrapers.
- **Adidas**: ATS `moka` na base, mas sem scraper no pacote (SKIP).
- **Workday**: fonte não fornece código de país; `country_iso` vem de
  `filters.infer_country_iso` (fallback country/location) — nos 165 eligible,
  0 None (100% com ISO).

## 9. Veredito

Validação final **APROVADA**: pipeline reprodutível do zero, determinístico,
suíte completa verde, sanity checks da Fase 2 mantidos, cobertura registrada.
Próximo passo sugerido (decisão do dono): expansão controlada de empresas alemãs.
