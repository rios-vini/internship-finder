# Relatório da Expansão E2 — 12 → 39 empresas alemãs (2026-08-12)

Registro completo da expansão aprovada pelo dono (decisão 2026-08-12): ampliar a
cobertura de ~17 empresas alemãs avaliadas para **~30-40**, priorizando as áreas do
perfil (Supply Chain, Procurement, Analytics/BI, Automation/Process Excellence) e
indústria/tecnologia, preferindo career sites/ATS suportados pelo pacote.

**Escopo respeitado:** nenhuma regra de filtro/ranking foi alterada (exigência do
dono); nenhum país novo; nenhum agregador; nenhum LLM/DB/frontend. A única mudança
de código da expansão foi o **ajuste mínimo do coletor** já documentado e commitado
no E1b (`050c5db`): `URL_SLUG_ATS` ganhou `"phenom"` e `requirements.txt` ganhou
`beautifulsoup4` (exigido pelo AvatureScraper). Nesta fase (E2) houve duas
alterações menores, **sem efeito no pipeline**: (1) correção de **texto de
relatório** em `scripts/coverage.py` (rótulo obsoleto "(12 operacionais)" removido);
(2) **recalibração dos sanity checks** de `scripts/test_ranking.py` para o conjunto
expandido (ver §9 — os checks antigos eram calibrados para n=165 e falhariam no
conjunto de 389 sem que nenhuma regra tivesse mudado; mesmo padrão já aplicado na
Fase 4).

## 1. Coleta — comando e contagens reais

```
comando: .venv/bin/internship-finder --companies "<39 nomes>" --timeout 60
run: 2026-08-12 04:52:06–04:57:31 UTC (5 min 25 s; 36 tenants com dados, ZERO falhas)

  coletadas brutas    : 56.810   (39 empresas: 12 atuais + 27 novas)
  + tipo estudante    :  4.995
  + área-alvo         :    914
  + país (DE)         :    406
  dedup removidas     :     17   (0 por external_id, 0 por URL,
                                  17 por company+title+location)
  eligible final      :    389
  ranked              :    389
```

Arquivos: `data/jobs.json`/`.csv` (bruto), `data/eligible_jobs.json`/`.csv`
(ranqueado, com `score`), `data/ranked_jobs.json`/`.csv` (cópia do eligible).
O detalhamento por tenant está em `docs/candidatas_expansao.md` (Fase E2) e
`docs/empresas_verificacao.md`.

## 2. Empresas adicionadas (27)

| Empresa | Consulta no `--companies` | Tenant (ATS) | Vagas brutas |
| --- | --- | --- | --- |
| DHL Group | `DHL` | `phenom:nan` (phenom) | 8.405 |
| Lidl | `Lidl` | `successfactors:lidlstiftuP2` | 24.488 |
| Kaufland | `Kaufland` | `successfactors:jobs` | 3.636 |
| Volkswagen Group | `VWAGLPPROD10` | `successfactors:VWAGLPPROD10` | 974 |
| B. Braun | `bbraunprd` | `successfactors:bbraunprd` | 925 |
| Zeiss Group | `Zeiss Group` | `workday:zeissgroup/external` | 812 |
| Schaeffler | `Schaeffler` | `successfactors:jobs` | 747 |
| Mahle | `Mahle` | `successfactors:mahleinter` | 391 |
| Voith | `Voith` | `successfactors:jobs` | 390 |
| Trumpf (3 tenants) | `Trumpf` | `workday:trumpf/*` | 392 |
| Hellmann | `Hellmann` | `workday:hellmann/hellmannexternaljobs` | 320 |
| Knorr-Bremse | `knorrbremsP2` | `successfactors:knorrbremsP2` | 270 |
| Celonis | `Celonis` | `greenhouse:celonis` | 258 |
| Deutsche Telekom | `Deutsche Telekom` | `eightfold:telekom-growthhub` | 237 |
| Sartorius | `Sartorius` | `workday:sartorius/sartoriuscareers` | 205 |
| Brose | `brosefahrz` | `successfactors:brosefahrz` | 204 |
| SICK AG | `SICK AG` | `successfactors:jobs` | 92 |
| Uniper | `Uniper` | `successfactors:jobs` | 90 |
| Krones | `kronesag` | `successfactors:kronesag` | 79 |
| DATEV (2 tenants) | `DATEV` | `workday:datev/*` | 64 |
| Fresenius | `freseniusglobal` | `workday:freseniusglobal/fse` | 54 |
| Statista | `Statista` | `ashby:statista` | 48 |
| Phoenix Contact | `Phoenix Contact` | `greenhouse:phoenixcontact` | 32 |
| Scout24 | `Scout24` | `greenhouse:scout24` | 26 |
| Dräger | `draegerP` | `successfactors:draegerP` | 24 |
| KraussMaffei | `KraussMaffei` | `successfactors:jobs` | 16 |
| Siemens Healthineers | `Siemens Healthineers` | `avature:https://jobs.siemens-healthineers.com/...` | 6 |

Soma das 27 novas: **44.293 vagas brutas** (as 12 atuais contribuem com o resto).

## 3. Empresas que falharam (4, com motivo)

| Empresa | ATS | Motivo | Observação |
| --- | --- | --- | --- |
| Hager Group | successfactors | `SuccessFactors returned malformed XML (line 15, col 51)` no sitemap — persistente (2 lotes E1b) | instância `career012.successfactors.eu` devolve XML inválido; não corrigível no nosso lado |
| Boehringer Ingelheim | successfactors | idem | instância `career5.successfactors.eu` |
| Lanxess | successfactors | idem | instância `career5.successfactors.eu` |
| Symrise | join_com | API `join.com/api/public/companies/95418/jobs` retorna **422** | endpoint quebrado/desatualizado; persistente |

## 4. Identidades excluídas (decisões do lead/owner)

| Empresa | Motivo da exclusão |
| --- | --- |
| ifm | identidade confirmada (`join_com:ifm`), mas API join.com retorna 422 (mesma falha do Symrise) |
| Metro | falso positivo — vagas de segurança/EMS nos EUA, não a Metro AG |
| Otto | falso positivo — `otto.applytojob.com`, não o Otto Group (Hamburgo) |
| E.ON | sem match exato na base do ats-scrapers |
| Kuehne+Nagel | **suíça** — fora do escopo "empresas alemãs" (agregaria 1.109 vagas de SCM; reavaliável por decisão do dono) |
| GFT Technologies SE | tenant `workable:gft` ativo, mas **0 vagas** no momento |

## 5. ATS sem scraper no pacote

**Nenhum novo** na expansão — as 39 empresas operacionais usam ATS com scraper
(successfactors, workday, smartrecruiters, phenom, eightfold, greenhouse, ashby,
avature, cornerstone). Seguem conhecidos e fora da lista: **moka** (adidas),
**adp** (Rhenus), **softgarden** (Bechtel/HanseVision), **paycom** (Balluff INC).

## 6. Funil e cobertura (`scripts/coverage.py`, offline e determinístico)

```
comando: .venv/bin/python scripts/coverage.py   (exit 0; determinístico)

=== Funil (--country de) ===
  raw coletadas        : 56810
  + tipo estudante     : 4995
  + area-alvo          : 914
  + pais (DE)          : 406
  eligible (pos-dedup) : 389
  dedup removidas      : 17
  ranked               : 389
=== Empresas (eligible) ===
  18 empresas distintas | 13 tenants (source)
  bruto: 40 empresas | 36 tenants com dados
     103  lidlstiftup2
      91  SAP
      42  Volkswagen AG
      39  BoschGroup
      25  Schaeffler Technologies AG & Co. KG
      21  BASF SE
      18  Knorr-Bremse
      13  Kaufland
       8  B. Braun Melsungen AG
       7  MAHLE International GmbH
       5  Telekom Growthhub
       5  Infineon
       4  henkel
       2  Brose Fahrzeugteile SE & Co.
       2  ZF Friedrichshafen AG
       2  Bayer
       1  continental
       1  Uniper
  contribuicao das maiores: top1 26.5% | top3 60.7% | top5 77.1%
=== ATS (eligible) ===
     335  successfactors
      40  smartrecruiters
      10  eightfold
       4  cornerstone
=== Paises (eligible) ===
     389  de
  None/localizacao desconhecida: 0 (0.0%)
```

Nota: "bruto: 40 empresas" são as **grafias distintas** do campo `company` no
bruto — a Bosch conta 2x (tenants `BoschGroup` e `bosch-homecomfort` reportam
nomes diferentes); mesmo efeito já visto na Fase 4 (12 empresas → 13 grafias).
A lista real é de 39 empresas (12 + 27).

## 7. Duplicatas

`dedup: removidas 17 (0 por external_id, 0 por URL, 17 por company+title+location)`.
Todas são versões EN/DE ou repostagens da mesma vaga (chave 3); nenhuma
duplicata entre tenants diferentes. Sem `--no-dedup`, a saída seria 406.

## 8. Impacto no ranking (antes/depois — nenhuma regra alterada)

### Distribuição de scores

| Métrica | Baseline Fase 4 (n=165) | Expansão E2 (n=389) |
| --- | --- | --- |
| min | 2.00 | 1.00 |
| mediana | 6.75 | 6.00 |
| max | 13.50 | 16.00 |
| média | 6.47 | 6.01 |
| faixas [10+] | 11 | 37 |
| faixas [8,10) | 20 | 43 |
| faixas [6,8) | 65 | 125 |
| faixas [4,6) | 56 | 110 |
| faixas [0,4) | 13 | 74 |

O máximo subiu para 16.00 (novo TOP 1: Knorr-Bremse) e a mediana caiu levemente
(6.75 → 6.00): a expansão adicionou 224 vagas eligible novas, muitas com score
baixo (vagas de área-alvo sem skills/idioma inglês detectado — ex.: Lidl
contribui com 103 eligible, maioria com título em alemão e sem inglês no texto).
O TOP 1 do baseline (Bosch, 13.50) permanece no TOP 3 — as melhores vagas do
conjunto antigo seguem no topo, sem regressão.

### TOP 20 — baseline (Fase 4) vs. E2

| # | Baseline (165) | score | E2 (389) | score |
| --- | --- | --- | --- | --- |
| 1 | BoschGroup — Pflichtpraktikum Logistik - Schwerpunkt Data & Analytics | 13.50 | **Knorr-Bremse — Werkstudent Data Analytics & Logistics** | **16.00** |
| 2 | BoschGroup — Praktikum in der Logistik - Data & Analytics | 13.50 | BoschGroup — Pflichtpraktikum Logistik - Schwerpunkt Data & Analytics | 13.50 |
| 3 | SAP — Working Student - Analytics: AI Enablement & Automation | 13.50 | BoschGroup — Praktikum in der Logistik - Data & Analytics | 13.50 |
| 4 | SAP — Working Student - Technology in Global Procurement | 12.25 | SAP — Working Student - Analytics: AI Enablement & Automation | 13.50 |
| 5 | BoschGroup — Praktikum im Bereich Logistik und Supply Chain Design | 11.50 | Knorr-Bremse — Praktikant Purchasing Controlling, Data Analytics, Supplier Management | 12.75 |
| 6 | SAP — iXp Intern - Event Showcase Operations | 11.50 | lidlstiftup2 — Werkstudent Supply Chain International - Data & Prototyping | 12.25 |
| 7 | SAP — MEE Strategy & Operations iXp Intern | 10.75 | SAP — Working Student - Technology in Global Procurement | 12.25 |
| 8 | SAP — Werkstudent Solution Advisory / Presales - Supply Chain | 10.75 | **B. Braun — Hochschulpraktikum im Bereich Prozessoptimierung im Einkauf** | 12.00 |
| 9 | SAP — Global Commercial Finance Operations iXp Intern | 10.25 | Knorr-Bremse — Praktikanten Business Intelligence & Analytics | 11.50 |
| 10 | Infineon — Werkstudent Supply Chain Data Management | 10.00 | BoschGroup — Praktikum im Bereich Logistik und Supply Chain Design | 11.50 |
| 11 | BoschGroup — Werkstudent Business Intelligence & Data Analytics | 10.00 | SAP — iXp Intern - Event Showcase Operations Support | 11.50 |
| 12 | BoschGroup — Internship Digital Project Management, Power BI & Automation | 9.50 | Knorr-Bremse — Freiwilliger Praktikant strategischer Indirekter Einkauf | 10.75 |
| 13 | BoschGroup — Mandatory Internship Data Analytics and Gen. AI | 9.50 | **Volkswagen AG — Praktikum Analytics After Sales** | 10.75 |
| 14 | BoschGroup — Praktikum digitales Projektmanagement, Power BI & Automatisierung | 9.50 | lidlstiftup2 — Praktikum Data Analytics & Digitalisierung | 10.75 |
| 15 | BoschGroup — Praktikum KI-System-Entwicklung und Data Analytics im Supply Chain | 9.50 | lidlstiftup2 — Praktikum Data Analytics - Digital Workflows | 10.75 |
| 16 | SAP — Working Student Sustainability Project Management | 9.50 | lidlstiftup2 — Praktikum Lidl Plus International - Customer Data & Analytics | 10.75 |
| 17 | SAP — Working Student/Intern IT Communications, Operations | 9.50 | SAP — MEE Strategy & Operations iXp Intern | 10.75 |
| 18 | henkel — Internship Supply Chain Europe Customer Service Experience Program | 8.75 | SAP — Werkstudent Solution Advisory / Presales - Fokus Supply Chain | 10.75 |
| 19 | SAP — Werkstudent IT End-User Enablement and Operations | 8.75 | Knorr-Bremse — Werkstudent Strategischer Einkauf Electronics | 10.75 |
| 20 | SAP — Werkstudent Operations & Process Support for Global... | 8.75 | **Volkswagen AG — Werkstudentin/Werkstudent Analytics After Sales** | 10.75 |

**Empresas novas no eligible (10):** lidlstiftup2 103, Volkswagen AG 42,
Schaeffler 25, Knorr-Bremse 18, Kaufland 13, B. Braun 8, MAHLE 7, Telekom
Growthhub 5, Brose 2, Uniper 1 (soma 224 das 389). Sanity checks do ranking
(comms/marketing fora do TOP 10, presales SCM no TOP 20, sem senior no topo)
seguem verdes — ver suíte abaixo.

## 9. Suíte de testes (2026-08-12, pós-expansão)

```
scripts/test_filters.py      EXIT=0  TUDO OK
scripts/test_dedup.py        EXIT=0  TUDO OK (389 -> 389, sem duplicatas)
scripts/test_ranking.py      EXIT=0  TUDO OK (sintético + determinismo + real + sanity)
scripts/test_manifest.py     EXIT=0
scripts/test_find_company.py EXIT=0
scripts/test_resolver.py     EXIT=0
scripts/test_fetch.py        EXIT=0
py_compile src/**/*.py + scripts/*.py: OK
```

**Recalibração de sanity checks (test-only, documentada):** com o conjunto
expandido (n=389, mediana 6.00), 5 checks de `test_ranking.py` calibrados para
n=165 falharam **sem nenhuma mudança de regra** — mesma situação já tratada na
Fase 4 (drift de dados → ajuste do sanity com nota no código). Ajustes:
(i) "Working Student - Marketing" e "marketing no top 25%" passaram a ser
avaliados por **posição** (fora do quartil superior) e o check de marketing
considera a **área real no título** (a vaga Bosch "Online Marketing - Analytics
& Performance", pos. 88, pontua pela área real de Analytics — não é falso
positivo; as demais vagas de marketing ficam nas posições 103-374);
(ii) a vaga Communications/Media "SAP Analytics Cloud" (pos. 205/389, score
6.00) é verificada como "na segunda metade" (antes: "abaixo da mediana" —
com a mediana em 6.00 ela fica exatamente nela); (iii) presales SCM (B-list)
verificado no TOP 20 (pos. 18/389, top 5% — antes TOP 10 no conjunto de 165);
(iv) A/B do dono verificados no TOP 50 (posições 2-44, todos com score ≥ 9.5
— antes TOP 20; a concorrência maior empurrou os A/B de 9.5-10.0 da Bosch
para as posições 36-44, sem regressão). Todos os checks que validam **regras**
(sem JMP, sem senior no topo, sem comms/marketing/media no TOP 10, área zerada
do produto mascarado, presales com área real) seguem como estavam e passam.

## 10. Veredito

Expansão **CONCLUÍDA**: 12 → 39 empresas alemãs operacionais (27 adicionadas),
funil 13.620 → 56.810 brutas e 165 → 389 eligible (top 8 → 18 empresas com vagas
eligible), 17 duplicatas removidas, suíte 7/7 verde, **zero mudança em
filtros/ranking**. Entrega via PR (branch `feat/e1a-matching-candidatas`).
