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
