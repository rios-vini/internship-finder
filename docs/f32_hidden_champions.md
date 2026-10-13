# F32 — Onda Hidden Champions: seeds estáticos → verify_companies → registry

*Data da onda: 13/10/2026 · executada fora da janela do cron (fetches ao vivo ~06:40–07:30 UTC; janela ocupada 09:00–09:15 UTC respeitada) · +17 empresas no registry (110 → 127), dentro do teto de <=40.*

## 1. Problema e método

O registry tinha 110 empresas, quase todas big corps. O Mittelstand alemão
(Weltmarktführer de nicho — máquinas, embalagem, automação, componentes) usa
Personio/SuccessFactors/Workday/SmartRecruiters — ATS que o pipeline já coleta e
hidrata. O gap era DESCOBRIR as empresas, não parsear novos ATS. Fluxo da onda:

1. **GATE robots.txt** das 3 fontes-semente (uma a uma, decisão antes do download).
2. **Download ONE-SHOT** (1 GET por página estática, sem crawling); HTML salvo em
   `/tmp` como evidência do run (NÃO commitado — policy do repo).
3. **Extração de nomes por layout** + dedup case-insensitive → 108 candidatas únicas.
4. **Pré-check OFFLINE** contra o manifest `ats-companies` do `ats-scrapers`
   (matching EXATO + variação de token) para escolher o nome canônico e separar
   homônimos ANTES de qualquer fetch.
5. **Runbook oficial ao vivo**: `scripts/verify_companies.py "..." --fetch --limit 8
   --timeout 30` em 5 lotes (valida match EXATO → scraper → fetch com vagas).
6. **Identidade** dos boards ambíguos confirmada por títulos/locais das vagas
   (padrão F16); **yield DE medido** (funil oficial `infer_country_iso`) quando a
   subsidiária suspeita aprovou no fetch.

## 2. GATE robots.txt (todas passaram)

| Fonte | robots.txt | Decisão |
|---|---|---|
| karrierebibel.de | `Disallow: /wp-admin/, /search, feeds, author` — página-semente `Allow` | ✅ leitura ONE-SHOT de `/hidden-champions/` |
| kipode.de | `User-agent: *  Allow: /` (só `/assets/private/` bloqueado; estratégia declarada de abrir p/ bots de busca e IA) | ✅ ONE-SHOT de `weltmarktfuehrer-deutschland.html` |
| deutsche-standards.de | só `wp-admin` + 1 JSON de plugin | ✅ ONE-SHOT do `wp-sitemap.xml` (índice) + `wp-sitemap-posts-post-1.xml` |

## 3. Fontes-semente — o que renderam

| Fonte | Render | Nomes | Obs |
|---|---|---|---|
| karrierebibel.de `/hidden-champions/` (Top 100) | **100** | `<li><strong>Nome</strong> (Cidade) – descrição` | lista alfabética com nicho — qualidade alta |
| kipode.de (página cita censo Simon 2020: **1.573**) | **17** | ~10 champions em `<h3>` + 7 aquisições chinesas em tabela | a página CITA a contagem, NÃO enumera 1.573; cap da onda (~120) tornava exaustão desnecessária |
| deutsche-standards.de (sitemap) | **0** | 9 posts de imprensa/eventos, sem lista enumerável de marcas | inspecionada e descartada; o conteúdo de marcas é livro impresso, fora do escopo |

Dedupe: 108 candidatas únicas; **8 já no SEED** (Continental, Hella, KraussMaffei,
Liebherr, Phoenix Contact, Sartorius, STIHL, Trumpf — match EXATO re-confirmado ao
vivo e ignoradas; nenhuma entrada existente foi alterada).

## 4. APROVADAS (17) — todas com fetch real ao vivo

| Lista (query) | Nome canônico (manifest) | ATS | Tenant (resolução real) | Evidência ao vivo |
|---|---|---|---|---|
| Blickle | Blickle | successfactors | `successfactors:jobs (URL jobs.blickle.career)` | 8 vagas (3.1s) |
| Bundesdruckerei | Bundesdruckerei  GmbH | softgarden | `softgarden:bundesdruckerei` | 6 vagas (0.8s) |
| Delo | Delo | workday | `workday:delo/DELO-Jobs` | 8 vagas (2.2s); títulos em Windach (sede da champion) |
| EBM-Papst | ebm-papst | cornerstone | `cornerstone:https://ebmpapst.csod.com/ux/ats/careersite/4/home?c=ebmpapst` | 8 vagas (2.9s) |
| ElringKlinger | ElringKlinger | workday | `workday:elringklinger/external` | 8 vagas (2.2s) |
| Freudenberg | Freudenberg | workday | `workday:freudenberg/freudenberg-group` | 8 vagas (5.6s) |
| Karlstorz | Karlstorz | successfactors | `successfactors:karlstor01` | 181 vagas; identidade 'Karl Storz SE & Co. KG' nos títulos; 71 DE |
| Kaeser | KAESER Careers | successfactors | `successfactors:KAESERP (URL careers.kaeser.com)` | 8 vagas (2.5s) |
| Körber | Körber Group | Job Market | successfactors | `successfactors:jobs (URL jobs.koerber.com)` | 8 vagas (3.8s) |
| Multivac | Jobs - Multivac | successfactors | `successfactors:jobs (URL jobs.multivac.com)` | 8 vagas (1.9s) |
| Ottobock | Ottobock Karriereportal | Aktuelle Stellenangebote und | successfactors | `successfactors:jobs (URL jobs.ottobock.com)` | 8 vagas (2.0s) |
| Mapal | Mapal Group | successfactors | `successfactors:jobs (URL jobs.mapal.com)` | 8 vagas (2.1s) |
| Lemken | Jobs | LEMKEN The Agrovision Company | successfactors | `successfactors:lemkengmbh (URL jobs.lemken.com)` | 8 vagas (1.5s) |
| Grammer | Grammer | cornerstone | `cornerstone:grammer-performance-management` | 8 vagas (2.9s) |
| Leoni | LEONI | smartrecruiters | `smartrecruiters:LEONI1` | 8 vagas (3.3s) |
| Walter | Walter | workday | `workday:sandvik/walter-jobs` | 8 vagas (1.9s); títulos Tübingen/Zell am Harmersbach (Walter AG) |
| Rational | Rational | successfactors | `successfactors:jobs (company rationalag)` | 8 vagas (2.9s); Landsberg am Lech (sede) |

Notas de identidade (padrão F16 — nunca deduzir por slug compartilhado):

- **5 boards `successfactors:jobs`** (Blickle/Körber/Multivac/Ottobock/Mapal) +
  **Rational** desambiguados por URL do manifest (`jobs.blickle.career`,
  `jobs.koerber.com`, `jobs.multivac.com`, `jobs.ottobock.com`, `jobs.mapal.com`;
  rationalag = RATIONAL AG, Landsberg am Lech) — mesmo padrão STIHL/BMW AG (16/09).
- **Karlstorz**: nome do manifest sem til (comercial "Karl Storz"); identidade
  confirmada nos títulos (`Karl Storz SE & Co. KG`). Maior yield DE da onda (71).
- **Walter**: Walter AG sob o workday global da Sandvik (`walter-jobs`; Sandvik
  comprou a Walter AG em 2023) — títulos em Tübingen/Zell am Harmersbach; mesmo
  padrão de "Sandvik (Sandvik Jobs)" (F16).
- **Delo**: vagas de produção em Windach (sede exata da champion).

## 5. REJEITADAS / IGNORADAS (84 + 8 seed-overlap)

Motivos: `NONE` = sem match no manifest (variações de token testadas); `FP` = só
homônimos; `FETCH` = candidato real testado ao vivo e reprovado. Precedente 08/09.

| Query da lista | Motivo | Detalhe/evidência |
|---|---|---|
| Abus | FP | sem match EXATO — só homônimos: Abusix (ashby); Datalabusa (bamboohr); Oklahoma Department of Mental Health and Substance Abuse Services (jazzhr) |
| Aesculap | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Amazone | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Arburg | FP | sem match EXATO — só homônimos: Warburg Pincus LLC (greenhouse); Grupo Carburgo (gupy); Schneider Hotel, Gastro & Event GmbH (softgarden) |
| Bauer | FP | sem match EXATO — só homônimos: BAUER concept GmbH (join_com); Willy Bauer KG (recruitee); Bauer's (adp) |
| Bihler | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Bizerba | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Brückner Group | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Chiron | FP | sem match EXATO — só homônimos: Chiron Technology Services, Inc. (icims); Chiron Management Company (workable) |
| Claas | FP | sem match EXATO — só homônimos: Steuerberatung Philipp Claaßen (join_com) |
| Dornbracht | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Dräger | FP | sem match EXATO — só homônimos: Dräger Gebäudetrocknung GmbH (join_com); Janine Dräger (join_com) |
| Duravit | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Dürr | FP | sem match EXATO — só homônimos: Christoph Dürr GmbH (join_com); Dürr Kunststofftechnik GmbH & Co. KG (join_com); Agrarhandel & Service GmbH Dürrenhofe (join_com) |
| Eberspächer | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Ejot | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Eppendorf | FP | sem match EXATO — só homônimos: Ev. Kinder- und Jugendhaus Eppendorf (join_com); RAN Sanitär-Heizung-Haustechnik-Service GmbH (join_com); Dermatologische Praxis Dr. med. Susanne Steinkraus - Dermatologikum Hamburg Eppendorf MVZ GmbH (join_com) |
| Erco | FP | sem match EXATO — só homônimos: Mercor (ashby); Percona (ashby); Andercore (ashby) |
| Fendt | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Festo | FP | sem match EXATO — só homônimos: Jobs Festo (successfactors) |
| Fuchs | FP | sem match EXATO — só homônimos: Michael Fuchs Transporte (join_com); dr. Fuchs Personalberatung KG (join_com); EDELFUCHS-LODGE (join_com) |
| Giesecke + Devrient | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Goldhofer | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Grimme | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Grob-Werke | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Grohe | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Guhring | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Harting | FP | sem match EXATO — só homônimos: gocharting (bamboohr) |
| Hauni | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Hecker | FP | sem match EXATO — só homônimos: DieFinanzchecker GmbH (join_com) |
| Heidelberger Druckmaschinen | FETCH | FAIL — nome canônico do manifest 'Heidelberger Druckmaschinen AG' (join_com) 422 (bug ATS-wide) |
| Hermle | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Hoppecke | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Horsch | FETCH | FAIL — join_com:horsch 422 (bug ATS-wide do scraper join.com; precedente Symrise F16) |
| Herrenknecht | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Index-Werke | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Interprint | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Kabelmetal | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Karl Storz | NONE | sem match no manifest ats-companies (variações de token testadas) |
| KHS | FETCH | FAIL — candidato do manifest 'KHS Gruppe' (join_com:khs-gmbh) 422 (bug ATS-wide); homonímia com KHS AG/Dortmund não confirmada |
| Komet Group | NONE | sem match no manifest ats-companies (variações de token testadas) |
| König & Bauer | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Krone | FP | sem match EXATO — só homônimos: Kelley Kronenberg (icims); Autohaus Kronenberger GmbH (join_com); miveS GmbH (join_com) |
| Krones | FP | sem match EXATO — só homônimos: Jobs at Krones (successfactors); Kronesusa (successfactors) |
| Lapp | FP | sem match EXATO — só homônimos: vegaamericasinternalapplications (greenhouse); Cyql BV (join_com); Schlappohr (join_com) |
| Lürssen | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Maha | FP | sem match EXATO — só homônimos: Yamaha Motor Canada (adp); qfhsomaha (greenhouse); Grupo Yamaha Brasil (gupy) |
| Mayr Antriebstechnik | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Mennekes | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Paul Hartmann | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Paul Horn | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Peri | FP | sem match EXATO — só homônimos: Harper (ashby); Periodic Labs (ashby); Semperis (ashby) |
| Pilz | FETCH | EMPTY — bamboohr:pilz respondeu 0 vagas |
| Putzmeister | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Renolit | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Rittal | FETCH | FP — jazzhr:rittal = Rittal LLC (subsidiária US, vagas/Eplan); 55 vagas, 0 DE |
| Rovema | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Schattdecor | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Schuler | FP | sem match EXATO — só homônimos: SCHULER Fahrzeugbau GmbH (join_com); Schuler Bäckereitechnik GmbH & Co. KG (join_com) |
| Schuler Pressen | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Schunk | FP | sem match EXATO — só homônimos: Schunk Mobilraum GmbH (join_com) |
| SMS Group | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Sto | FP | sem match EXATO — só homônimos: BELFOR Property Restoration Canada (adp); Cornerstone Community Financial Credit Union (adp); Johnstone Supply (adp) |
| Symrise | FP | sem match EXATO — só homônimos: SYMRISE (join_com); FITCO (workday) |
| Tente | FP | sem match EXATO — só homônimos: Extenteam Careers (greenhouse); ALTEN Technology USA (greenhouse); Ambient Enterprises (greenhouse) |
| Utsch | FP | sem match EXATO — só homônimos: Outschool (bamboohr); Deutsche Telekom (eightfold); Outschool (greenhouse) |
| Wacker Neuson | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Wago | FP | sem match EXATO — só homônimos: lewagon (bamboohr); GOWAGO AG (join_com); Newrest Wagons-Lits Austria GmbH (recruitee) |
| Wanzl | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Webasto | FP | sem match EXATO — só homônimos: Webasto Jobportal (successfactors) |
| Weidmüller | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Wilo | FP | sem match EXATO — só homônimos: WILOFA DIAMANT Willi Lohmann GmbH & Co. KG (join_com); WWI Logistik GmbH (join_com) |
| Windmöller & Hölscher | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Winterhalter | FETCH | EMPTY — bamboohr:winterhalter 0 vagas (+ join_com:winterhalter 422, mesmo bug) |
| ZF Friedrichshafen | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Ziehl-Abegg | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Züblin | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Würth | FP | sem match EXATO — só homônimos: Eisenwerk Würth (join_com); Würth Cloud Services GmbH (join_com) |
| Kärcher | NONE | sem match no manifest ats-companies (variações de token testadas) |
| Knauf | FP | sem match EXATO — só homônimos: Knauf Insulation (icims); Knauf Gypsum NEE South-East (teamtailor); Knauf Aquapanel (teamtailor) |
| Kiekert | NONE | sem match no manifest ats-companies (variações de token testadas) |
| KUKA | FP | sem match EXATO — só homônimos: クウカン株式会社 (herp); 学校法人信学会 (hrmos); Lummo (Formerly Bukukas) (recruiterbox) |
| Biotest | NONE | sem match no manifest ats-companies (variações de token testadas) |
| ACPS Automotive (Marke Oris) | NONE | sem match no manifest ats-companies (variações de token testadas) |

### Rejeitadas com fetch ao vivo (destaque)

| Candidata | Desfecho |
|---|---|
| Horsch (join_com) | FAIL — 422 do scraper join.com (bug ATS-wide; precedente Symrise F16) |
| Heidelberger Druckmaschinen (AG) | FAIL — 422 (join.com; nome canônico do manifest testado) |
| KHS (KHS Gruppe) | FAIL — 422 (join.com); homonímia com KHS AG não confirmada |
| Pilz (bamboohr) | EMPTY — 0 vagas |
| Winterhalter (bamboohr) | EMPTY — 0 vagas (+ join 422) |
| Rittal (jazzhr) | FP — "Rittal LLC" subsidiária US; 55 vagas, 0 DE |
| Knauf Insulation (icims) | FP/yield — subsidiária US; 33 vagas: 30 US / 0 DE |

## 6. Mudanças em código/testes

- `src/internship_finder/registry.py`: SEED 110 → **127** (bloco comentado da onda,
  nomes canônicos EXATOS, tenant = resolução real do runtime; nenhuma remoção).
- **Parametrização (precedente `test_visa_policy`)**: `scripts/test_registry.py`
  agora deriva a lista canônica do próprio SEED (`CANONICAL = sorted(…)`) com a
  contagem absoluta em UMA constante (`EXPECTED_SEED_N`); `test_f16.py`/`test_f24.py`
  idem (`SEED_COUNT`), checks relativos (T4c/T6a/T3c) mantidos;
  `test_registry_consistency.py` usa `len(CompanyRegistry().entries)`. Fim dos
  12 literais `110` — a próxima onda bumpa 1 constante.
- Docs sincronizados: README (127 companies / 15 ATS — conjunto de ATS inalterado),
  `docs/README-operacional.md`, `docs/architecture.md`.
- **Nota de ambiente**: `scripts/test_lifecycle.py` falha em Python 3.14 local
  (default de multiprocessing mudou de fork → forkserver; quebra no HEAD limpo
  também). CI roda 3.12 — suíte executada localmente com 3.12.10: **67/67 verdes**.

## 7. OBRIGAÇÃO FUTURA MONITORADA

> **O funil completo (registry 127 → eligible/ranking) mede-se no PRÓXIMO CRON
> 09:00 UTC (14/10)** — obrigação monitorada: comparar `eligible`/fontes ok vs. run
> 13/10; o registro operacional continua no JSONL de métricas (o registry é
> configuração, não resultado). Esta fase NÃO roda o cron manualmente.

## 8. Evidência do run (não commitada)

HTMLs das fontes: `/tmp/kb_hidden.html`, `/tmp/kipode_wmf.html`, `/tmp/ds_sitemap.xml`,
`/tmp/ds_posts.xml`. Saídas de fetch: `/tmp/f32_fetch_b1.txt` + logs dos lotes 2–4.
JSONs de matching: `/tmp/f32_matches.json` (108 rows), `/tmp/f32_rejected.json`.
