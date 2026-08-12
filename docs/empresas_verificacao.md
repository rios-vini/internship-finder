# Verificação de empresas-alvo (Alemanha)

Base: `ats-scrapers` (manifest + ~80k empresas). Tabela gerada em 2026-08-10
com `scripts/verify_companies.py` (match exato: slug/nome casefold, fallback
por token corroborado pelo slug). Re-rode o script para revalidar:
```bash
.venv/bin/python scripts/verify_companies.py "ZF,Bayer,BASF,Henkel,Infineon,Zalando,Delivery Hero,Covestro,Evonik,Siemens" --fetch --timeout 60
```

## Matching (find_company, sem fetch)

| Empresa | Tenant(s) na base | ATS | Slug efetivo (URL p/ URL-SLUG ATS) | Scraper |
| --- | --- | --- | --- | --- |
| Bosch | `smartrecruiters:BoschGroup` | smartrecruiters | `BoschGroup` | sim |
| Bosch | `smartrecruiters:bosch-homecomfort` | smartrecruiters | `bosch-homecomfort` | sim |
| SAP | `successfactors:jobs` | successfactors | `https://jobs.sap.com` | sim |
| Continental | `smartrecruiters:continental` | smartrecruiters | `continental` | sim |
| ZF | `successfactors:jobs` | successfactors | `https://jobs.zf.com` | sim |
| Bayer | `eightfold:bayer` | eightfold | `bayer` | sim |
| Bayer | `successfactors:jobs` | successfactors | `https://jobs.bayer.com` | sim |
| Bayer | `moka:bayer/148387` | moka | — | **não** (sem scraper) |
| BASF | `successfactors:basf` | successfactors | `https://basf.jobs` | sim |
| Henkel | `cornerstone:henkel` | cornerstone | `henkel` | sim |
| Infineon | `eightfold:infineon` | eightfold | `infineon` | sim |
| Zalando | `workday:zalando/zalandositewd` | workday | `https://zalando.wd3.myworkdayjobs.com/zalandositewd` | sim |
| Delivery Hero | `smartrecruiters:deliveryhero` | smartrecruiters | `deliveryhero` | sim |
| Covestro | `workday:covestro/cov_external` | workday | `https://covestro.wd3.myworkdayjobs.com/cov_external` | sim |
| Evonik | `workday:evonik/external_careers` | workday | `https://evonik.wd3.myworkdayjobs.com/external_careers` | sim |
| Siemens | `teamtailor:siemens` | teamtailor | `siemens` | sim (mas tenant inativo — ver status) |
| BMW | `join_com:bmw-kuehnert` | join_com | `bmw-kuehnert` | sim (**falso positivo**: é a BMW Kuehnert GmbH, não a BMW AG — excluída) |
| Mercedes-Benz | — | — | — | **sem match exato** na base |
| ThyssenKrupp | — | — | — | **sem match exato** na base |
| Adidas | `moka:adidas/140456` | moka | — | **não** (sem scraper no pacote) |

## Status real da coleta (run 2026-08-10, `--timeout 60`)

| Empresa | Tenant | ATS | Status | Vagas | Tempo |
| --- | --- | --- | --- | --- | --- |
| Bosch | `smartrecruiters:BoschGroup` | smartrecruiters | OK | 4.760 | 25.0s |
| Bosch | `smartrecruiters:bosch-homecomfort` | smartrecruiters | OK | 195 | 1.2s |
| SAP | `successfactors:jobs` (jobs.sap.com) | successfactors | OK | 948 | 9.2s |
| Continental | `smartrecruiters:continental` | smartrecruiters | OK | 960 | 5.2s |
| ZF | `successfactors:jobs` (jobs.zf.com) | successfactors | OK | 821 | 4.5s |
| Bayer | `eightfold:bayer` | eightfold | OK | 598 | 6.8s |
| Bayer | `successfactors:jobs` (jobs.bayer.com) | successfactors | OK | 614 | 9.0s |
| Bayer | `moka:bayer/148387` | moka | SKIP | — | sem scraper |
| BASF | `successfactors:basf` (basf.jobs) | successfactors | OK | 738 | 6.0s |
| Henkel | `cornerstone:henkel` | cornerstone | OK | 978 | 5.3s |
| Infineon | `eightfold:infineon` | eightfold | OK | 1.160 | 6.8s |
| Zalando | `workday:zalando/zalandositewd` | workday | OK | 155 | 2.1s |
| Delivery Hero | `smartrecruiters:deliveryhero` | smartrecruiters | OK | 1.060 | 5.5s |
| Covestro | `workday:covestro/cov_external` | workday | OK | 132 | 2.3s |
| Evonik | `workday:evonik/external_careers` | workday | OK | 363 | 2.7s |
| Siemens | `teamtailor:siemens` | teamtailor | **FAIL** | — | `CompanyNotFoundError` (tenant inativo) |

**Total bruto: 13.482 vagas** (12 empresas com dados; Siemens excluída).

### Excluídas e motivo

| Empresa | Motivo |
| --- | --- |
| Siemens | tenant `teamtailor:siemens` inativo (`CompanyNotFoundError`) |
| BMW | falso positivo: só `join_com:bmw-kuehnert` (BMW Kuehnert GmbH, não a BMW AG) |
| Mercedes-Benz | sem match exato na base |
| ThyssenKrupp | sem match exato na base |
| Adidas | ATS `moka` sem scraper no pacote |

### Limitações observadas (dados, não filtros)

- **Delivery Hero**: 59 vagas de estudante, mas fora da Alemanha (SG/ES/BR...) → 0 eligible em `de`.
- **Covestro/Evonik/Zalando**: vagas alemãs (ex.: "Praktikant:in Sustainability Strategy" em
  Leverkusen, "Pflichtpraktikum Employer Branding" em Essen, Working Student em Berlim) vêm do ATS
  **sem código de país** na localização (`country_iso` nulo) → o filtro de país não consegue
  inferir DE. Conhecido; um enriquecimento futuro (geocodificação/cidades) resolveria.
- **bosch-homecomfort**: sem vagas de tipo estudante.

---

## Expansão E2 (2026-08-12) — 27 empresas novas (adicionadas à coleta)

Verificação em `docs/candidatas_expansao.md` (E1a: matching; E1b: fetch de
validação). Status E2 = coleta real final (run 04:52–04:57 UTC, `--timeout 60`):
**27 OK com vagas, 0 falhas** na lista adicionada. Consulta = nome usado no
`--companies` (slug do tenant quando o nome natural não passa no coletor
estrito).

| Empresa | Consulta | Tenant (ATS) | Slug efetivo / URL | Status E2 | Vagas |
| --- | --- | --- | --- | --- | --- |
| DHL Group | `DHL` | `phenom:nan` (phenom) | `https://careers.dhl.com` | OK | 8.405 |
| Lidl | `Lidl` | `successfactors:lidlstiftuP2` | `https://jobs.lidl` | OK | 24.488 |
| Kaufland | `Kaufland` | `successfactors:jobs` | `https://jobs.kaufland.com` | OK | 3.636 |
| Volkswagen Group | `VWAGLPPROD10` | `successfactors:VWAGLPPROD10` | `https://jobs.volkswagen-group.com` | OK | 974 |
| B. Braun | `bbraunprd` | `successfactors:bbraunprd` | `https://jobs.bbraun.com` | OK | 925 |
| Zeiss Group | `Zeiss Group` | `workday:zeissgroup/external` | `https://zeissgroup.wd3.myworkdayjobs.com/external` | OK | 812 |
| Schaeffler | `Schaeffler` | `successfactors:jobs` | `https://jobs.schaeffler.com` | OK | 747 |
| Mahle | `Mahle` | `successfactors:mahleinter` | `https://careers.mahle.com` | OK | 391 |
| Voith | `Voith` | `successfactors:jobs` | `https://jobs.voith.com` | OK | 390 |
| Trumpf | `Trumpf` | `workday:trumpf/*` (3 tenants) | `https://trumpf.wd3.myworkdayjobs.com/...` | OK | 392 |
| Hellmann | `Hellmann` | `workday:hellmann/hellmannexternaljobs` | `https://hellmann.wd103.myworkdayjobs.com/hellmannexternaljobs` | OK | 320 |
| Knorr-Bremse | `knorrbremsP2` | `successfactors:knorrbremsP2` | `https://careers.knorr-bremse.com` | OK | 270 |
| Celonis | `Celonis` | `greenhouse:celonis` | `celonis` | OK | 258 |
| Deutsche Telekom | `Deutsche Telekom` | `eightfold:telekom-growthhub` | `telekom-growthhub` | OK | 237 |
| Sartorius | `Sartorius` | `workday:sartorius/sartoriuscareers` | `https://sartorius.wd3.myworkdayjobs.com/sartoriuscareers` | OK | 205 |
| Brose | `brosefahrz` | `successfactors:brosefahrz` | `https://job.brose.com` | OK | 204 |
| SICK AG | `SICK AG` | `successfactors:jobs` | `https://jobs.sick.com` | OK | 92 |
| Uniper | `Uniper` | `successfactors:jobs` | `https://jobs.uniper.energy` | OK | 90 |
| Krones | `kronesag` | `successfactors:kronesag` | `https://career.krones.com` | OK | 79 |
| DATEV | `DATEV` | `workday:datev/Datev_Careers` + `.../ENG_DATEV` | `https://datev.wd3.myworkdayjobs.com/...` | OK | 64 |
| Fresenius | `freseniusglobal` | `workday:freseniusglobal/fse` | `https://freseniusglobal.wd3.myworkdayjobs.com/fse` | OK | 54 |
| Statista | `Statista` | `ashby:statista` | `statista` | OK | 48 |
| Phoenix Contact | `Phoenix Contact` | `greenhouse:phoenixcontact` | `phoenixcontact` | OK | 32 |
| Scout24 | `Scout24` | `greenhouse:scout24` | `scout24` | OK | 26 |
| Dräger | `draegerP` | `successfactors:draegerP` | `https://recruitment.draeger.jobs` | OK | 24 |
| KraussMaffei | `KraussMaffei` | `successfactors:jobs` | `https://jobs.kraussmaffei.com` | OK | 16 |
| Siemens Healthineers | `Siemens Healthineers` | `avature:https://jobs.siemens-healthineers.com/...` | URL completa como slug | OK | 6 |

**Total E2: 27 novas operacionais** (+ 12 atuais = **39**; 36 tenants com dados;
zero falhas). Empresas avaliadas e NÃO incluídas na expansão, com motivo, em
`docs/relatorio_expansao.md` §3-4 (Hager/Boehringer/Lanxess/Symrise falharam;
ifm/Metro/Otto/E.ON/Kuehne+Nagel/GFT excluídas). A cobertura final (funil,
empresas, ATS, países) está em `docs/relatorio_expansao.md` §6.
