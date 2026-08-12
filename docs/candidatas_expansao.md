# Expansão de empresas alemãs — Fase E1a: tabela de matching

Gerado em **2026-08-12** com `scripts/verify_companies.py` **sem `--fetch`** (matching
offline via manifest do `ats-scrapers`, `find_company`). Nenhuma coleta/rede de vagas
nesta fase; nenhuma alteração no pipeline (filtros/ranking intocados).

**Método:** para cada candidata, rodou-se `find_company` com o nome natural + variantes
(`scripts/verify_companies.py "<nomes>"`, 249 consultas, 189 grafias únicas, 1 processo =
1 download do manifest). O `CompanyCollector` filtra com seleção **exata** (slug/nome
casefold, fallback token corroborado pelo slug); quando o nome natural não passa no
coletor estrito mas a linha existe na base (slug genérico `jobs`/`karriere`, ou slug
distintivo), o match foi confirmado por consulta RAW (`ats_scrapers.find_company` cru) e
por consulta ao **slug do tenant** (que o coletor estrito aceita — ex.: `knorrbremsP2`).

## Classificações

| Classe | Significado |
| --- | --- |
| **MATCH OK** | tenant na base com scraper; coletável pelo nome natural via `--companies` |
| **MATCH OK (slug)** | tenant na base com scraper; o nome natural NÃO passa no coletor estrito — usar o slug do tenant como nome de consulta (ex.: `VWAGLPPROD10`) |
| **MATCH OK (ressalva)** | tenant na base com scraper, mas exige ajuste de coletor (ver nota phenom) |
| **MATCH SEM SCRAPER** | tenant existe, ATS **não suportado** no pacote (adp, moka, softgarden, paycom, ...) |
| **NA BASE, NÃO COLETÁVEL PELO NOME** | linha existe com slug genérico ambíguo (`jobs`/`karriere`); `--companies "<nome>"` retorna NONE hoje — exigiria tratamento manual/ajuste |
| **FALSO POSITIVO** | o match retornado é OUTRA empresa (homônimo/subsidiária/ruído) |
| **SEM MATCH** | nenhuma linha na base (nem crua) |

## Resumo (empresas, 2026-08-12)

| Classe | Nº empresas |
| --- | --- |
| MATCH OK (nome natural) | 45 |
| MATCH OK via slug do tenant | 8 |
| MATCH OK (ressalva phenom) | 2 principais (Allianz, Merck Group) |
| MATCH SEM SCRAPER | 4 (Rhenus, Bechtle, Balluff, adidas) |
| NA BASE, NÃO COLETÁVEL PELO NOME | 5 (REWE, Webasto, Bilfinger, Festo, Merck KGaA) |
| FALSO POSITIVO | 14 registrados (abaixo) |
| SEM MATCH | 52 |

---

## Tabela de matching completa

### MATCH OK — coletável pelo nome natural (`scraper=True`)

| Empresa | Tenant(s) na base | ATS | Slug efetivo (URL p/ URL-SLUG ATS) | Scraper |
| --- | --- | --- | --- | --- |
| Schaeffler | `successfactors:jobs` | successfactors | `https://jobs.schaeffler.com` | sim |
| Mahle | `successfactors:mahleinter` | successfactors | `https://careers.mahle.com` | sim |
| Trumpf | `workday:trumpf/TRUMPF_Apprenticeships` | workday | `https://trumpf.wd3.myworkdayjobs.com/TRUMPF_Apprenticeships` | sim |
| Trumpf | `workday:trumpf/TRUMPF_Students` | workday | `https://trumpf.wd3.myworkdayjobs.com/TRUMPF_Students` | sim |
| Trumpf | `workday:trumpf/trumpf_graduates_and_professionals` | workday | `https://trumpf.wd3.myworkdayjobs.com/trumpf_graduates_and_professionals` | sim |
| SICK AG | `successfactors:jobs` | successfactors | `https://jobs.sick.com` | sim |
| Voith | `successfactors:jobs` | successfactors | `https://jobs.voith.com` | sim |
| Siemens Healthineers | `avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs` | avature | `https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs` | sim |
| Lanxess | `successfactors:lanxessP` | successfactors | `https://career5.successfactors.eu/career?company=lanxessP` | sim |
| Boehringer Ingelheim | `successfactors:BoehringerPRD` | successfactors | `https://career5.successfactors.eu/career?company=BoehringerPRD` | sim |
| Symrise | `join_com:symrise` | join_com | `symrise` | sim |
| Sartorius | `workday:sartorius/sartoriuscareers` | workday | `https://sartorius.wd3.myworkdayjobs.com/sartoriuscareers` | sim |
| Uniper | `successfactors:jobs` | successfactors | `https://jobs.uniper.energy` | sim |
| Vattenfall (sueca, grandes operações DE) | `smartrecruiters:Vattenfall` | smartrecruiters | `Vattenfall` | sim |
| Deutsche Telekom | `eightfold:telekom-growthhub` | eightfold | `telekom-growthhub` | sim |
| Deutsche Telekom | `smartrecruiters:deutschetelekomitsolutions` | smartrecruiters | `deutschetelekomitsolutions` | sim |
| Celonis | `greenhouse:celonis` | greenhouse | `celonis` | sim |
| TeamViewer | `smartrecruiters:teamviewer1` (+ `teamtailor:teamviewer`) | smartrecruiters | `teamviewer1` | sim |
| DATEV | `workday:datev/Datev_Careers` + `workday:datev/ENG_DATEV` | workday | `https://datev.wd3.myworkdayjobs.com/Datev_Careers` / `.../ENG_DATEV` | sim |
| SUSE | `workday:suse/jobsatsuse` | workday | `https://suse.wd3.myworkdayjobs.com/jobsatsuse` | sim |
| Contentful | `greenhouse:contentful` | greenhouse | `contentful` | sim |
| Deutsche Bank | `smartrecruiters:deutschebank` | smartrecruiters | `deutschebank` | sim |
| Puma | `workday:puma/jobs_at_puma` (+ `puma/Work_at_stichd` subsidiária) | workday | `https://puma.wd502.myworkdayjobs.com/jobs_at_puma` | sim |
| HelloFresh | `greenhouse:hellofresh` | greenhouse | `hellofresh` | sim |
| Zeiss Group | `workday:zeissgroup/external` + `lever:zeiss` | workday/lever | `https://zeissgroup.wd3.myworkdayjobs.com/external` / `zeiss` | sim |
| Dräger | `successfactors:draegerP` | successfactors | `https://recruitment.draeger.jobs` | sim |
| Hellmann (Worldwide Logistics) | `workday:hellmann/hellmannexternaljobs` | workday | `https://hellmann.wd103.myworkdayjobs.com/hellmannexternaljobs` | sim |
| Kuehne+Nagel (suíça, gigante SCM na DE) | `cornerstone:kuehne-nagel` (+ `phenom:nan` jobs.kuehne-nagel.com) | cornerstone | `kuehne-nagel` | sim |
| ElringKlinger | `workday:elringklinger/external` | workday | `https://elringklinger.wd3.myworkdayjobs.com/external` | sim |
| Leoni | `smartrecruiters:LEONI1` | smartrecruiters | `LEONI1` | sim |
| Phoenix Contact | `greenhouse:phoenixcontact` | greenhouse | `phoenixcontact` | sim |
| ifm (IFM GmbH — verificar identidade no fetch) | `join_com:ifm` | join_com | `ifm` | sim |
| Statista | `ashby:statista` | ashby | `statista` | sim |
| Flix | `greenhouse:flix` | greenhouse | `flix` | sim |
| Scout24 | `greenhouse:scout24` (+ AutoScout24, TruckScout24, ImmoScout24) | greenhouse | `scout24` | sim |
| BioNTech | `successfactors:biontechse` | successfactors | `https://jobs.biontech.com` | sim |
| Evotec | `workday:evotecgroup/evotec_career_site` | workday | `https://evotecgroup.wd3.myworkdayjobs.com/evotec_career_site` | sim |
| Tchibo | `successfactors:jobs` | successfactors | `https://jobs.tchibo.com` | sim |
| Viessmann (Generations Group) | `ashby:viessmann` | ashby | `viessmann` | sim |
| KraussMaffei | `successfactors:jobs` | successfactors | `https://jobs.kraussmaffei.com` | sim |
| Hager Group | `successfactors:HagerGroup` | successfactors | `https://career012.successfactors.eu/career?company=HagerGroup` | sim |
| Linde (plc, origem alemã, grande presença DE) | `cornerstone:linde` (+ jazzhr:linde, +2 cornerstone careersite) | cornerstone | `linde` | sim |
| Sonepar (francesa, grandes operações DE) | `successfactors:career` | successfactors | `https://career.sonepar.com` | sim |
| GFT Technologies SE | `workable:gft` | workable | `gft` | sim |
| EPLAN (Friedhelm Loh Group, software CAE) | `jazzhr:eplan` | jazzhr | `eplan` | sim |
| Lidl (Schwarz Gruppe) | `successfactors:lidlstiftuP2` | successfactors | `https://jobs.lidl` | sim |
| Kaufland (Schwarz Gruppe) | `successfactors:jobs` | successfactors | `https://jobs.kaufland.com` | sim |
| DHL Group (Deutsche Post DHL) | `avature:dpdhlgroup` (+ `phenom:nan` careers.dhl.com, `avature:dhlconsulting`, `taleo` DHL eCommerce) | avature | `https://dpdhlgroup.avature.net/jobs/SearchJobs` | sim |

### MATCH OK via slug do tenant (nome natural NÃO passa no coletor estrito)

| Empresa | Consulta E1b (slug) | Tenant | ATS | Slug efetivo (URL) | Scraper |
| --- | --- | --- | --- | --- | --- |
| Volkswagen Group | `VWAGLPPROD10` | `successfactors:VWAGLPPROD10` | successfactors | `https://jobs.volkswagen-group.com` | sim |
| Knorr-Bremse | `knorrbremsP2` | `successfactors:knorrbremsP2` | successfactors | `https://careers.knorr-bremse.com` | sim |
| B. Braun | `bbraunprd` | `successfactors:bbraunprd` | successfactors | `https://jobs.bbraun.com` | sim |
| Brose | `brosefahrz` | `successfactors:brosefahrz` | successfactors | `https://job.brose.com` | sim |
| Fresenius (SE + Medical Care + Kabi) | `freseniusglobal` | `workday:freseniusglobal/fse`, `.../fme`, `.../fk_careers` (+ `icims:fresenius-kabi`) | workday/icims | `https://freseniusglobal.wd3.myworkdayjobs.com/fse` etc. | sim |
| About You | `aboutyougmbh` | `smartrecruiters:aboutyougmbh` | smartrecruiters | `aboutyougmbh` | sim |
| Krones | `kronesag` | `successfactors:kronesag` | successfactors | `https://career.krones.com` | sim |
| KAESER Kompressoren | `KAESERP` | `successfactors:KAESERP` | successfactors | `https://careers.kaeser.com` | sim |

### MATCH OK (ressalva) — tenant phenom com `slug='nan'` na base

O `PhenomScraper` exige a **URL completa** como slug; a base traz `slug='nan'` (NaN) e a
URL correta em `company.url`. O `URL_SLUG_ATS` do coletor (`ats_scraper.py`) não inclui
`phenom`, então `scraper_slug()` devolveria `'nan'` e o fetch falharia. **Ajuste mínimo
para E1b/E2 (coletor, NÃO filtro/ranking):** adicionar `"phenom"` a `URL_SLUG_ATS`. Sem
isso, essas candidatas não coletam.

| Empresa | Tenant | ATS | URL (slug efetivo após ajuste) | Scraper |
| --- | --- | --- | --- | --- |
| Allianz | `phenom:nan` | phenom | `https://careers.allianz.com` | sim |
| Merck Group (Merck KGaA — alemã) | `phenom:nan` | phenom | `https://careers.merckgroup.com` | sim |
| DHL (tenant alternativo; principal = avature acima) | `phenom:nan` | phenom | `https://careers.dhl.com` | sim |
| Kuehne+Nagel (tenant alternativo; principal = cornerstone acima) | `phenom:nan` | phenom | `https://jobs.kuehne-nagel.com` | sim |

### MATCH SEM SCRAPER — ATS NÃO SUPORTADO no pacote

| Empresa | Tenant | ATS (não suportado) | Observação |
| --- | --- | --- | --- |
| Rhenus | `adp:...` | **adp** | tenant real da logística; sem scraper |
| Bechtle (via HanseVision GmbH) | `softgarden:hansevision` | **softgarden** | entidade do grupo Bechtle; sem scraper |
| Balluff | `paycom:BALLUFF INC` | **paycom** | é a INC americana (não a matriz alemã); sem scraper |
| adidas (reavaliação) | `moka:adidas/140456` | **moka** | confirmado: sem scraper no pacote |

### NA BASE, NÃO COLETÁVEL PELO NOME (slug genérico ambíguo `jobs`/`karriere`)

A linha existe com scraper, mas `--companies "<nome>"` retorna NONE hoje (o coletor
estrito exige token do nome **corroborado por segmento do slug**; slug `jobs`/`karriere`
não corrobora). Coleta exigiria tratamento manual (URL fixa) ou ajuste de coletor —
**não recomendadas para E1b** sem decisão explícita.

| Empresa | Tenant RAW | ATS | URL | Scraper |
| --- | --- | --- | --- | --- |
| REWE Group | `successfactors:karriere` | successfactors | `https://karriere.rewe-group.com` | sim |
| Webasto | `successfactors:jobs` | successfactors | `https://jobs.webasto.com` | sim |
| Bilfinger | `successfactors:jobs` | successfactors | `https://jobs.bilfinger.com` | sim |
| Festo | `successfactors:jobs` | successfactors | `https://jobs.festo.com` | sim |
| Merck KGaA (successfactors) | `successfactors:jobs` | successfactors | `https://jobs.vibrantm.com` | sim |

### FALSOS POSITIVOS registrados (excluídos; desconfiar de homônimos)

| Empresa buscada | Match retornado | Motivo |
| --- | --- | --- |
| BMW | `join_com:bmw-kuehnert` | é a **BMW Kuehnert GmbH** (concessionária), não a BMW AG — confirmado, nenhuma variante (BMW Group, bayerische motoren werke) tem match |
| Porsche | `join_com:seeland-klassische-porsche`, `workable:porsche-asia-pacific`, `workable:porsche-cars-gb-ltd`, `personio:porsche-ep-doo` | clássicos/dealer + subsidiárias estrangeiras; só `personio:porsche-ep` (Porsche Engineering, alemã) é real — candidata de menor prioridade |
| Mercedes-Benz | `lever:MBRDNA`, `pageup:Mercedes-AMG HPP`, `workday:mbgp/mercedes-amgf1` | R&D EUA / HPP UK / F1 UK; matriz alemã **sem match**; `recruitee:mbio` (Mercedes-Benz.io, Berlim) é subsidiária digital real — candidata parcial |
| Schott | `join_com:schott-meissnerde` | Schott & Meissner (outra empresa); Schott AG não está na base |
| PNE | `icims:pne` | **Pacific National Exhibition** (Canadá), não a PNE AG de energia |
| GFT | `icims:gannettfleming` | Gannett Fleming (EUA); o tenant correto é `workable:gft` |
| Software AG | `join_com:gw-software`, `join_com:proxia` | G&W Software AG / Proxia (outras); Software AG de Darmstadt sem match |
| Messer | `join_com:klotzli` | Messer Klötzli Bern (suíça); Messer Group sem match |
| Metro | `icims:metro` | Superior Air-Ground Ambulance (EUA); tenants greenhouse/smartrecruiters `metro` são ambíguos — verificar no fetch |
| dm-drogerie markt | `bamboohr:dm`, `rippling:dm` | nome genérico `dm`/`DM` — provável outra empresa; dm-drogerie usa karriere.dm.de (sem match) |
| Nemetschek | `recruiterbox:nemetschek` | **Nemetschek OOD Bulgaria** (subsidiária búlgara), não o Nemetschek Group alemão |
| adesso | `recruitee:adesso1` | **adesso Belgium** (subsidiária belga), não a adesso SE alemã |
| Otto | `jazzhr:otto` | `otto.applytojob.com` — provável outra "Otto"; Otto Group sem match confiável |
| E.ON | `bamboohr:eon`, `greenhouse:eonio` | nome genérico — provável outra empresa; E.ON SE sem match confiável |

### SEM MATCH (nenhuma linha na base, nem crua)

Audi, BMW (real), Mercedes-Benz (matriz), Daimler Truck, KION Group, Jungheinrich,
GEA Group, KUKA, Rheinmetall, MTU Aero Engines, Nordex, SMA Solar, Siemens (matriz —
tenant teamtailor inativo), Siemens Energy, Wacker Chemie, Beiersdorf, Qiagen, RWE,
EnBW, DB Schenker, Deutsche Bahn, Lufthansa, Fraport, HHLA, Otto Group, Schwarz Gruppe
(como nome; **Lidl e Kaufland cobrem o grupo**), Munich Re, Commerzbank, Talanx, ERGO,
Leica, Dachser, Fiege, Nagel Group, BLG Logistics, Aurubis, Heraeus, BayWa r.e., juwi,
Encavis, Cancom, CureVac, HUK-Coburg, WAGO, Harting, SEW-Eurodrive, Lenze, NORD, Obeta,
Personio (ironia: o próprio ATS não está na base de empresas), Software AG (matriz),
ThyssenKrupp (todas as grafias — só ruído `breezy:apex-tk-llc`).

---

## Reavaliação das 5 falhas conhecidas

| Empresa | Status anterior | Status E1a (2026-08-12) | Veredito |
| --- | --- | --- | --- |
| **Siemens** | tenant `teamtailor:siemens` inativo | matriz continua só com teamtailor (inativo) e **Siemens Energy sem match**; **Siemens Healthineers tem tenant `avature` com scraper** | **CANDIDATA — Siemens Healthineers** (avature, URL como slug, sem ajuste) |
| **BMW** | falso positivo `bmw-kuehnert` | confirmado; variantes BMW Group / bayerische motoren werke → 0 rows | SEM MATCH (falso positivo mantido) |
| **Mercedes-Benz** | sem match exato | matriz sem match; subsidiária digital **Mercedes-Benz.io** (`recruitee:mbio`, Berlim) existe | CANDIDATA PARCIAL (baixa prioridade; verificar no fetch) |
| **ThyssenKrupp** | sem match exato | todas as grafias (`thyssenkrupp`, `tk`, `Thyssen`, AG) → 0 rows; só ruído | SEM MATCH (confirmado) |
| **Adidas** | ATS moka sem scraper | confirmado: `moka:adidas/140456`, `scraper=False` | MATCH SEM SCRAPER (mantido) |

---

## Shortlist recomendada para a fase de fetch (E1b) — 33 candidatas novas

Priorizadas por área do perfil (Supply Chain, Procurement, Analytics/BI,
Automation/Process Excellence, indústria/tech) e viabilidade de coleta. `(slug)` =
usar o slug do tenant como nome no `--companies`.

### Tier 1 — Logística / Supply Chain (6)
1. **DHL Group** (Deutsche Post DHL) — `avature:dpdhlgroup`
2. **Hellmann Worldwide Logistics** — `workday:hellmann/hellmannexternaljobs`
3. **Kuehne+Nagel** — `cornerstone:kuehne-nagel` (suíça, mas SCM gigante na DE — avaliar)
4. **Lidl** (Schwarz Gruppe) — `successfactors:jobs` (jobs.lidl)
5. **Kaufland** (Schwarz Gruppe) — `successfactors:jobs` (jobs.kaufland.com)
6. **Volkswagen Group** `(slug: VWAGLPPROD10)` — `successfactors` (jobs.volkswagen-group.com)

### Tier 2 — Indústria / Automação / Process Excellence (11)
7. Schaeffler — successfactors (jobs.schaeffler.com)
8. Mahle — successfactors (careers.mahle.com)
9. Trumpf — workday (3 tenants; **TRUMPF_Students** é foco direto de estágio)
10. SICK AG — successfactors (jobs.sick.com)
11. Voith — successfactors (jobs.voith.com)
12. **Knorr-Bremse** `(slug: knorrbremsP2)` — successfactors
13. **Brose** `(slug: brosefahrz)` — successfactors
14. Phoenix Contact — greenhouse
15. KraussMaffei — successfactors
16. **Krones** `(slug: kronesag)` — successfactors
17. Hager Group — successfactors

### Tier 3 — Química / Farma / Healthcare SCM (6)
18. Boehringer Ingelheim — successfactors
19. **B. Braun** `(slug: bbraunprd)` — successfactors
20. Sartorius — workday
21. Lanxess — successfactors
22. Symrise — join_com
23. **Fresenius** `(slug: freseniusglobal)` — workday (fse/fme/fk_careers) + icims (Kabi)

### Tier 4 — Analytics / BI / Tech (6)
24. Deutsche Telekom — eightfold (telekom-growthhub) + smartrecruiters (IT Solutions)
25. Celonis — greenhouse (process mining — área direta do perfil)
26. DATEV — workday (2 tenants)
27. Statista — ashby (dados/BI)
28. Scout24 — greenhouse
29. GFT Technologies SE — workable

### Tier 5 — Medtech / Óptica / Energia (4)
30. **Siemens Healthineers** (reavaliada) — avature
31. Zeiss Group — workday (+ lever)
32. Dräger — successfactors
33. Uniper — successfactors

### Reserva (viáveis, prioridade menor — incluir se faltar cobertura)
ElringKlinger, Leoni, ifm (verificar identidade), Viessmann, EPLAN, KAESER
`(slug: KAESERP)`, BioNTech, Evotec, About You `(slug: aboutyougmbh)`, SUSE,
Contentful, TeamViewer, Flix, Puma, HelloFresh, Tchibo, Deutsche Bank, Vattenfall
(sueca), Linde (plc), Sonepar (francesa), Siemens Healthineers já na lista, Allianz
*(ressalva phenom)*, Merck Group *(ressalva phenom)*.

---

## Notas para E1b/E2

1. **Nomes de consulta para os MATCH OK (slug):** usar `VWAGLPPROD10`, `knorrbremsP2`,
   `bbraunprd`, `brosefahrz`, `freseniusglobal`, `aboutyougmbh`, `kronesag`, `KAESERP`
   no `--companies` — o coletor estrito aceita o slug (match exato), o nome natural não.
2. **phenom (Allianz, Merck Group):** adicionar `"phenom"` a `URL_SLUG_ATS` em
   `src/internship_finder/collectors/ats_scraper.py` (1 linha; coletor, não
   filtro/ranking). Sem isso o `PhenomScraper` recebe `'nan'` e falha.
3. **`--fetch --timeout` decide o status real** (tenant ativo/inativo, 0 vagas,
   falso positivo de identidade tipo ifm/metro/otto/eon) — E1b roda
   `scripts/verify_companies.py "<nomes>" --fetch --timeout 60` com a shortlist.
4. **Workday não expõe país** (limitação conhecida: Covestro/Evonik/Zalando) —
   candidatas Workday novas (Trumpf, Sartorius, DATEV, SUSE, Zeiss, Hellmann,
   ElringKlinger, Evotec, Fresenius) podem ter vagas alemãs sem `country_iso`;
   não é motivo para excluir, mas afeta o funil.
5. **Nenhuma regra de filtro/ranking foi alterada**; a expansão só adiciona empresas
   à coleta. Requisitos do dono preservados (qualidade > quantidade).

---

# Fase E1b — fetch de validação (2026-08-12) — tabela de status real

Gerado com `scripts/verify_companies.py "<lista>" --fetch --timeout 60` sobre as
**33 candidatas da shortlist** (Tiers 1-5) + 4 verificações de identidade ambígua
(ifm, Metro, Otto, E.ON). Dois lotes:

- **Lote 1** (04:28:21–04:31:06 UTC, **2 min 45 s**): as 33 candidatas com os
  nomes de consulta do E1a (slug para os tenants com slug genérico).
- **Lote 2** (04:31:59–04:32:31 UTC, **32 s**): retries — nomes de consulta
  alternativos (Hellmann, GFT, Dräger) e re-teste de tenants que falharam no
  lote 1 após 2 ajustes mínimos de ambiente (ver §Ajustes).

**Nenhuma regra de filtro/ranking foi alterada.** Ajustes aplicados (commit
separado `050c5db`): `"phenom"` adicionado a `URL_SLUG_ATS` (coletor) e
`beautifulsoup4` no requirements (extra exigido pelo scraper avature).

## Ajustes mínimos aplicados (commit 050c5db, documentado)

1. **`URL_SLUG_ATS` += `"phenom"`** em `src/internship_finder/collectors/ats_scraper.py`
   — a base traz `slug='nan'` para tenants phenom e a URL real em `company.url`;
   sem a inclusão o `PhenomScraper` recebia `'nan'` e falhava. Com o ajuste,
   **DHL (8.405 vagas)** e **Kuehne+Nagel (1.109 vagas)** passaram a coletar.
2. **`beautifulsoup4>=4.12`** em `requirements.txt` — o `AvatureScraper`
   (Siemens Healthineers, DHL) exige bs4 (extra opcional do ats-scrapers);
   sem ele o fetch falhava com `ScraperError`. Com a instalação,
   **Siemens Healthineers** passou a coletar (6 vagas).

Suíte de testes após os ajustes: **7/7 arquivos EXIT=0** (test_dedup, test_fetch,
test_filters, test_find_company, test_manifest, test_ranking, test_resolver).

## Tabela de status — 33 candidatas (lote 1 + lote 2 consolidados)

| Empresa | Consulta E1b | Tenant (ATS) | Status | Vagas | Motivo (se falha) |
| --- | --- | --- | --- | --- | --- |
| DHL Group | `DHL` (lote 2; avature testado 2x) | `phenom:nan` (phenom) | **OK** | 8.405 | avature `dpdhlgroup` inativo (`Avature site not found`) — coleta via phenom `careers.dhl.com` |
| Hellmann | `Hellmann` (lote 2) | `workday:hellmann/hellmannexternaljobs` | **OK** | 320 | nome completo não casa no coletor estrito |
| Kuehne+Nagel | `Kuehne+Nagel` | `phenom:nan` (phenom) | **OK** | 1.109 | cornerstone `kuehne-nagel` falha DNS (`Name or service not known`) — coleta via phenom `jobs.kuehne-nagel.com` |
| Lidl | `Lidl` | `successfactors:lidlstiftuP2` | **OK** | 24.488 | — |
| Kaufland | `Kaufland` | `successfactors:jobs` | **OK** | 3.636 | — |
| Volkswagen Group | `VWAGLPPROD10` | `successfactors:VWAGLPPROD10` | **OK** | 974 | — |
| Schaeffler | `Schaeffler` | `successfactors:jobs` | **OK** | 747 | — |
| Mahle | `Mahle` | `successfactors:mahleinter` | **OK** | 391 | — |
| Trumpf | `Trumpf` | `workday:trumpf/TRUMPF_Apprenticeships` | **OK** | 60 | — |
| Trumpf | `Trumpf` | `workday:trumpf/TRUMPF_Students` | **OK** | 78 | — |
| Trumpf | `Trumpf` | `workday:trumpf/trumpf_graduates_and_professionals` | **OK** | 254 | — |
| SICK AG | `SICK AG` | `successfactors:jobs` | **OK** | 92 | — |
| Voith | `Voith` | `successfactors:jobs` | **OK** | 390 | — |
| Knorr-Bremse | `knorrbremsP2` | `successfactors:knorrbremsP2` | **OK** | 270 | — |
| Brose | `brosefahrz` | `successfactors:brosefahrz` | **OK** | 204 | — |
| Phoenix Contact | `Phoenix Contact` | `greenhouse:phoenixcontact` | **OK** | 32 | — |
| KraussMaffei | `KraussMaffei` | `successfactors:jobs` | **OK** | 16 | — |
| Krones | `kronesag` | `successfactors:kronesag` | **OK** | 79 | — |
| Hager Group | `Hager Group` (2x) | `successfactors:HagerGroup` | **FAIL** | — | `SuccessFactors returned malformed XML (line 15, col 51)` — persistente nos 2 lotes |
| Boehringer Ingelheim | `Boehringer Ingelheim` (2x) | `successfactors:BoehringerPRD` | **FAIL** | — | idem (malformed XML) |
| B. Braun | `bbraunprd` | `successfactors:bbraunprd` | **OK** | 924 | — |
| Sartorius | `Sartorius` | `workday:sartorius/sartoriuscareers` | **OK** | 205 | — |
| Lanxess | `Lanxess` (2x) | `successfactors:lanxessP` | **FAIL** | — | idem (malformed XML) |
| Symrise | `Symrise` (2x) | `join_com:symrise` | **FAIL** | — | API join.com retorna **422** (endpoint quebrado/company id desatualizado) |
| Fresenius | `freseniusglobal` | `workday:freseniusglobal/fse` | **OK** | 54 | só o tenant `fse` casa no coletor (fme/fk_careers não) |
| Deutsche Telekom | `Deutsche Telekom` | `eightfold:telekom-growthhub` | **OK** | 237 | tenant smartrecruiters não casa com o nome |
| Celonis | `Celonis` | `greenhouse:celonis` | **OK** | 258 | — |
| DATEV | `DATEV` | `workday:datev/Datev_Careers` + `workday:datev/ENG_DATEV` | **OK** | 63 + 1 | — |
| Statista | `Statista` | `ashby:statista` | **OK** | 48 | — |
| Scout24 | `Scout24` | `greenhouse:scout24` | **OK** | 26 | — |
| GFT Technologies SE | `GFT` (lote 2) | `workable:gft` | **OK (0 vagas)** | 0 | tenant ativo, sem vagas no momento; nome completo não casa |
| Siemens Healthineers | `Siemens Healthineers` | `avature:https://jobs.siemens-healthineers.com/...` | **OK** | 6 | lote 1 falhou por bs4 ausente (ambiente); lote 2 OK |
| Zeiss Group | `Zeiss Group` | `workday:zeissgroup/external` | **OK** | 812 | tenant lever `zeiss` não casa com o nome |
| Dräger | `draegerP` (lote 2) | `successfactors:draegerP` | **OK** | 24 | nome com umlaut (`Dräger`) não casa; usar o slug |
| Uniper | `Uniper` | `successfactors:jobs` | **OK** | 90 | — |

## Decisões de identidade ambígua (verificação pelo resultado do fetch)

| Consulta | Resultado | Decisão |
| --- | --- | --- |
| `ifm` | `join_com:ifm` = ifm electronic GmbH (tenant correto), mas API join.com retorna 422 | **Não incluir** — identidade confirmada, coleta quebrada (mesma falha do Symrise) |
| `Metro` | 3 tenants: greenhouse 2 vagas, smartrecruiters 0, icims 28 — vagas de **segurança/EMS nos EUA** (Protective Security Officer, Paramedic/Firefighter) | **Falso positivo** — não é a Metro AG alemã; excluir |
| `Otto` | `jazzhr:otto` (otto.applytojob.com) 2 vagas remotas genéricas | **Falso positivo** — não é o Otto Group (Hamburgo); excluir |
| `E.ON` | NONE (sem match exato) | **Sem match** — excluir |

## Lista final de operacionais NOVAS (28 com vagas coletadas)

| # | Empresa | Tenant | ATS | Vagas (brutas) |
| --- | --- | --- | --- | --- |
| 1 | DHL Group | `phenom:nan` | phenom | 8.405 |
| 2 | Lidl | `successfactors:lidlstiftuP2` | successfactors | 24.488 |
| 3 | Kaufland | `successfactors:jobs` | successfactors | 3.636 |
| 4 | Kuehne+Nagel (suíça — avaliar) | `phenom:nan` | phenom | 1.109 |
| 5 | Volkswagen Group | `successfactors:VWAGLPPROD10` | successfactors | 974 |
| 6 | B. Braun | `successfactors:bbraunprd` | successfactors | 924 |
| 7 | Zeiss Group | `workday:zeissgroup/external` | workday | 812 |
| 8 | Schaeffler | `successfactors:jobs` | successfactors | 747 |
| 9 | Mahle | `successfactors:mahleinter` | successfactors | 391 |
| 10 | Voith | `successfactors:jobs` | successfactors | 390 |
| 11 | Trumpf (3 tenants) | `workday:trumpf/*` | workday | 392 |
| 12 | Hellmann | `workday:hellmann/hellmannexternaljobs` | workday | 320 |
| 13 | Knorr-Bremse | `successfactors:knorrbremsP2` | successfactors | 270 |
| 14 | Celonis | `greenhouse:celonis` | greenhouse | 258 |
| 15 | Deutsche Telekom | `eightfold:telekom-growthhub` | eightfold | 237 |
| 16 | Sartorius | `workday:sartorius/sartoriuscareers` | workday | 205 |
| 17 | Brose | `successfactors:brosefahrz` | successfactors | 204 |
| 18 | SICK AG | `successfactors:jobs` | successfactors | 92 |
| 19 | Uniper | `successfactors:jobs` | successfactors | 90 |
| 20 | Krones | `successfactors:kronesag` | successfactors | 79 |
| 21 | DATEV (2 tenants) | `workday:datev/*` | workday | 64 |
| 22 | Fresenius | `workday:freseniusglobal/fse` | workday | 54 |
| 23 | Statista | `ashby:statista` | ashby | 48 |
| 24 | Phoenix Contact | `greenhouse:phoenixcontact` | greenhouse | 32 |
| 25 | Dräger | `successfactors:draegerP` | successfactors | 24 |
| 26 | Scout24 | `greenhouse:scout24` | greenhouse | 26 |
| 27 | KraussMaffei | `successfactors:jobs` | successfactors | 16 |
| 28 | Siemens Healthineers | `avature:https://jobs.siemens-healthineers.com/...` | avature | 6 |

**Total novas com vagas: 28 empresas** (+ GFT com 0 vagas, tenant ativo — incluir
apenas se houver interesse em monitorar). Soma bruta: 44.293 vagas.

## Falhas documentadas (5 definitivas) + motivo

| Empresa | ATS | Motivo | Observação |
| --- | --- | --- | --- |
| Hager Group | successfactors | `malformed XML (line 15, col 51)` no sitemap — persistente (2 lotes) | instância `career012.successfactors.eu` devolve XML inválido; não corrigível no nosso lado |
| Boehringer Ingelheim | successfactors | idem | instância `career5.successfactors.eu` |
| Lanxess | successfactors | idem | instância `career5.successfactors.eu` |
| Symrise | join_com | API `join.com/api/public/companies/95418/jobs` retorna **422** | endpoint quebrado/desatualizado; persistente |
| ifm (Reserva) | join_com | idem (company 140788) | identidade correta, coleta quebrada |

## ATS sem scraper no pacote

Nenhum **novo** ATS sem scraper apareceu entre as 33 candidatas (todas tinham
scraper registrado). Os ATS sem scraper conhecidos seguem os do E1a: **moka**
(adidas), **adp** (Rhenus), **softgarden** (Bechtel/HanseVision), **paycom**
(Balluff INC).

## Notas para E2 (adição à coleta)

1. **Nomes de consulta finais** (alguns diferem do E1a): `DHL` (não "DHL Group"),
   `Hellmann` (não o nome completo), `GFT`, `draegerP` (slug), além dos slugs já
   previstos (`VWAGLPPROD10`, `knorrbremsP2`, `bbraunprd`, `brosefahrz`,
   `freseniusglobal`, `kronesag`).
2. **Lidl (24.488 vagas)** é o maior tenant; o fetch levou 79s (timeout 60 +
   margem 25) — OK, mas é o item mais pesado da coleta E2.
3. **Workday não expõe país** (limitação conhecida): Hellmann, Trumpf, Sartorius,
   DATEV, Zeiss, Fresenius terão vagas sem `country_iso` — afeta o funil
   (filtro `--country de`), não a coleta.
4. **Kuehne+Nagel é suíça** — manter na lista a critério do lead/owner (agrega
   1.109 vagas de SCM gigante com forte presença DE).
5. **GFT (workable) com 0 vagas** — registrar como operacional sem vagas no
   momento; reavaliar em E2 se voltou a publicar.
6. **Fresenius**: só o tenant `fse` casa com `freseniusglobal`; fme/fk_careers
   exigiriam consulta própria (não testados — fora da decisão desta fase).

---

# Fase E2 — resultado final (adição à coleta, 2026-08-12)

Coleta final em **2026-08-12 04:52:06–04:57:31 UTC** com as **39 empresas**
(12 atuais + 27 novas) via `--companies` + `--timeout 60`. **Nenhuma regra de
filtro/ranking foi alterada** (exigência do dono); a única mudança de código da
expansão foi o ajuste mínimo do coletor já aplicado no E1b (commit `050c5db`:
`URL_SLUG_ATS` += phenom; `beautifulsoup4` no requirements). Nesta fase, apenas
correção de texto de relatório em `scripts/coverage.py` (rótulo "(12
operacionais)" obsoleto, sem efeito em números).

## Empresas adicionadas (27)

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

## Empresas que falharam (4) + motivo

| Empresa | ATS | Motivo |
| --- | --- | --- |
| Hager Group | successfactors | `SuccessFactors returned malformed XML (line 15, col 51)` — instância `career012.successfactors.eu` devolve XML inválido (persistente nos 2 lotes E1b) |
| Boehringer Ingelheim | successfactors | idem — instância `career5.successfactors.eu` |
| Lanxess | successfactors | idem — instância `career5.successfactors.eu` |
| Symrise | join_com | API `join.com/api/public/companies/95418/jobs` retorna **422** (endpoint quebrado) |

## Identidades excluídas

| Empresa | Motivo |
| --- | --- |
| ifm | identidade correta (`join_com:ifm`), API join.com 422 (mesma falha do Symrise) |
| Metro | falso positivo — vagas de segurança/EMS nos EUA, não a Metro AG |
| Otto | falso positivo — `otto.applytojob.com`, não o Otto Group |
| E.ON | sem match exato na base |
| Kuehne+Nagel | suíça — fora do escopo "empresas alemãs" (decisão do lead/owner) |
| GFT Technologies SE | tenant ativo, **0 vagas** no momento |

## ATS sem scraper no pacote

**Nenhum novo** na expansão — todas as 39 operacionais usam ATS com scraper.
Seguem conhecidos (fora da lista): moka (adidas), adp (Rhenus), softgarden
(Bechtel/HanseVision), paycom (Balluff INC).

## Funil da coleta final

```
raw 56.810 → tipo estudante 4.995 → área-alvo 914 → país DE 406 → dedup 17 → eligible 389 → ranked 389
```

## Duplicatas

`dedup: removidas 17 (0 por external_id, 0 por URL, 17 por company+title+location)`
 versões EN/DE e repostagens; zero cross-tenant.

## Impacto no ranking (distribuição antes/depois)

| Métrica | Baseline Fase 4 (n=165) | E2 (n=389) |
| --- | --- | --- |
| min | 2.0 | 1.0 |
| mediana | 6.75 | 6.0 |
| max | 13.5 | 16.0 |
| média | 6.47 | 6.01 |
| faixas [10+]/[8,10)/[6,8)/[4,6)/[0,4) | 11/20/65/56/13 | 37/43/125/110/74 |

TOP 20 antes/depois e análise completa: `docs/relatorio_expansao.md`.
