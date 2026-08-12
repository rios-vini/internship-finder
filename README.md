# internship-finder

Buscador de estagios (internship / working student / Praktikum / Werkstudent) com
foco em **Supply Chain, Procurement, BI, Analytics e Automacao**, prioridade para a
**Alemanha**. Pipeline **orientado a empresas**:

```
Empresa → find_company (match exato) → ATS → scraper (subprocesso + timeout) → adapter → Job (pydantic) → print/save (JSON/CSV)
```

Base de empresas/ATS: pacote [`ats-scrapers`](https://pypi.org/project/ats-scrapers/)
(~80k empresas, 65 ATS). A busca global do pacote pode travar; por isso o fluxo e por
empresa (`find_company` com selecao exata para nao pegar empresa parecida errada,
ex.: "sap" -> asap/Casap).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Requer Python **>= 3.12** (testado em 3.12; vale para 3.13/3.14).

## Como rodar

O CLI tem dois modos: **filtro** (default) e **coleta** (`--companies`).

**Filtro** — le vagas ja coletadas e retorna apenas as ELIGIBLE
(estudante/estagio + area-alvo + pais), **ranqueadas por perfil** (score +
TOP 20), gravando em `data/eligible_jobs.json` + `.csv` (com campo `score`;
`--no-rank` desliga o ranking). Conceitos do pipeline:

```
collected -> filtered -> eligible -> deduplicated -> ranked -> best matches
```

`eligible` e o conceito final da cascata (passou em tipo + area + pais);
**best matches = TOP N do ranked** (sem entidade/camada nova):

```bash
.venv/bin/internship-finder                              # data/jobs.json -> data/eligible_jobs.json (170 vagas ranqueadas, sem duplicatas)
.venv/bin/internship-finder --country europe             # Europa inteira em vez de so Alemanha
.venv/bin/internship-finder --no-area                    # qualquer area, desde que estudante + Alemanha
.venv/bin/internship-finder --no-dedup                   # mantem duplicatas (182 vagas)
.venv/bin/internship-finder --no-rank                    # sem ranking: ordem original + exemplos
.venv/bin/internship-finder --all                        # copia tudo, sem filtros
```

**Coleta** — fluxo original (grava o bruto em `data/jobs.json`) e ja aplica a
mesma cascata, gravando o resultado em `data/eligible_jobs.json`. Lista-alvo
atual (12 empresas com dados, validada em 2026-08-10; ver
`docs/empresas_verificacao.md`):

```bash
.venv/bin/internship-finder --companies "Bosch,SAP,Continental,ZF,Bayer,BASF,Henkel,Infineon,Zalando,Delivery Hero,Covestro,Evonik" --timeout 60
# ou, sem instalar:
python scripts/collect_jobs.py --companies "Bosch,SAP" --output data/jobs.json
```

Resultado do ultimo run completo (13 empresas candidatas, 13.482 vagas brutas):
`total 13.482 -> tipo estudante 1.995 -> area-alvo 510 -> Alemanha 182` (SAP 94,
Bosch 43, BASF 21, Henkel 4, ZF 3, Bayer 2, Infineon 2, Continental 1; pos-dedup
sao **170**). Com dedup, as 182 eligible viram **170** (12 duplicatas removidas:
10 SAP + 2 Bosch — versoes EN/DE do mesmo cargo e repostagens). Apos a auditoria
(Fase 1), a regra de tipo mudou e os 3 Junior Managers Program (Bosch) sairam do
eligible (173 -> 170); Siemens foi testada e excluida (tenant `teamtailor`
inativo). A coleta total leva alguns minutos — cada tenant usa timeout proprio
(`--timeout 60`).

Saida: contagens em cascata (`total -> tipo estudante -> area-alvo -> pais`),
linha de dedup (`removidas N: X por external_id, Y por URL, Z por
company+title+location`), **TOP 20 ranqueado por perfil** (score + breakdown
curto; `--no-rank` desliga e mostra exemplos como antes) e os arquivos
gravados com o campo `score`.

Flags do CLI:

| Flag | Descricao |
| --- | --- |
| `--companies` | modo coleta: nomes separados por virgula (match exato na base; sem match, a empresa e ignorada com aviso) |
| `--input` | modo filtro: JSON bruto de entrada (default: `data/jobs.json`) |
| `--output` | filtro: saida eligible (default: `data/eligible_jobs.json`); coleta: saida bruta (default: `data/jobs.json`) |
| `--filter-output` | modo coleta: saida eligible (default: `data/eligible_jobs.json`) |
| `--student` / `--no-student` | filtra tipo estudante/estagio (Internship, Working Student, Praktikum, Werkstudent, iXp...; default: ligado) |
| `--area` / `--no-area` | filtra areas-alvo do dono (Supply Chain, Procurement, BI, Analytics, Automacao; default: ligado) |
| `--country`/`--countries` | pais/localizacao: ISO alpha-2 (`de`, `de,at,ch`), `europe`, `remote` ou `all` (default: `de`) |
| `--all` | desliga os tres filtros de uma vez (copia o conjunto inteiro) |
| `--dedup` / `--no-dedup` | remove duplicatas da saida (default: ligado) |
| `--rank` / `--no-rank` | rankeia por compatibilidade com o perfil: score + TOP 20 (default: ligado; `--no-rank` mantem a ordem original) |
| `--timeout` | teto de segundos por scraper (defensivo: uma empresa que trava nao derruba o resto) |
| `--limit N` | maximo de vagas por tenant (0 = sem limite) |
| `--include-descriptions` | busca a descricao por vaga (mais lento em ATS que exigem uma chamada por vaga, ex. SmartRecruiters) |
| `--verbose` | log DEBUG |

### Deduplicacao

A saida filtrada passa por dedup por padrao (`--no-dedup` desliga), usando
chaves em ordem de confiabilidade — a primeira que bater decide (`src/internship_finder/dedup.py`):

1. `external_id`/`id` do ATS (identidade oficial da vaga na origem);
2. URL normalizada (sem fragmento, sem barra final, casefold; a query e
   mantida — eightfold carrega o id da vaga nela);
3. `company + titulo normalizado + localizacao normalizada` — pega versoes
   EN/DE do mesmo cargo e repostagens: o titulo e normalizado (casefold, sem
   acentos, sem sufixos de genero `m/w/d`/`f/m/d`/`w/m/div.`, `Werkstudent`
   tratado como `Working Student`, sem palavras funcionais EN/DE e comparado
   como saco de palavras — ordem indiferente).

Quando duas versoes da mesma vaga existem, o "vencedor" e deterministico:
a com `description` preenchida; senao a com `employment_type`; senao a que
veio primeiro. O CLI reporta quantas foram removidas e por qual chave.
Titulos que sao traducao real (conteudo diferente, ex.: "Marketing
Deutschland" vs "Marketing Germany") NAO sao fundidos — exigiria dicionario
de traducao/fuzzy, fora do escopo do MVP. No conjunto atual: eligible
182 -> 170 (12 removidas, todas pela chave 3; 10 SAP + 2 Bosch).

### Ranking por perfil

Depois de filtrar e deduplicar, o CLI **ranqueia as vagas por compatibilidade
com o perfil do dono** (`src/internship_finder/ranking.py`) — heuristica
deterministica, sem ML — e mostra as melhores primeiro (TOP 20). Cada vaga
ganha `score` (total) e `score_breakdown` (por componente) no JSON/CSV; o
desempate e deterministico (score desc -> titulo -> empresa -> id).

Score = `area + skills + language + type + location + penalties`:

| Componente | Peso | Fonte |
| --- | --- | --- |
| `area` | titulo x2.0; descricao x0.0 | reusa `filters.area_score` (PRIMARY 3 / RELATED 2 / WEAK 1 no titulo). A area da descricao e **zerada** por calibracao no conjunto real: templates genericos (ex.: SAP) citam `data`/`sap`/`reporting` em vagas de Marketing e inflavam a area; o valor da descricao entra por skills e idioma. Fase 2: frases de PRODUTO com termos de area no titulo (`AREA_TITLE_PRODUCT_PATTERNS`: "SAP Analytics Cloud", "Analytics Cloud") sao **mascaradas** antes da deteccao — o termo e do nome do produto, nao da funcao ("Working Student ... Communications / Media Production in SAP Analytics Cloud" nao e vaga de Analytics). Lista curta e fixa, calibrada no caso real; a frase mais especifica vem primeiro (senao sobraria o "sap" fraco pontuando) |
| `skills` | +0.75 por competencia (descricao) | Inventory Management, Supplier Relationships/Management, Process Automation, System Integration, Python, APIs, Cloud, Reporting, Continuous Improvement |
| `language` | ingles +1.5, alemao +0.5 | detectados no titulo+descricao (`english`/`englisch`; `german`/`deutsch` como palavra — "Deutschland" nao conta) |
| `type` | +1.0 | marcador forte de tipo no TITULO (Praktikum, Werkstudent, Internship, iXp... — reusa `filters.STUDENT_TYPE_PATTERNS`; Trainee/JMP NAO sao marcadores: os programas de `filters.PROGRAM_EXCLUSION_PATTERNS` nao chegam ao eligible) |
| `location` | DE explicito +1.0; Berlin +0.5 | ISO alpha-2 via `filters.infer_country_iso`; remoto neutro |
| `penalties` | senior/director/head/principal -3.0; manager -1.0; FULL_TIME -0.5 | senioridade e "manager" SO valem sem marcador forte de tipo no titulo (Praktikum/Werkstudent/Internship no titulo protegem; JMP/Trainee nao protegem — nao sao marcadores); FULL_TIME e suave (Werkstudent/Praktikum vêm marcados FULL_TIME no conjunto e nao zeram) |

Sem descricao (46 das 170), age-se com graca: skills/idioma contribuem 0 e o
score vem do titulo. Exemplo real do conjunto atual (2026-08-10, 170
eligible, pos-Fase 2): scores `min 1.00 | mediana 6.75 | max 13.50`; TOP 1 =
"Pflichtpraktikum Logistik - Schwerpunkt Data & Analytics" (13.50); o antigo
TOP 1 "Working Student ... Communications / Media Production in SAP Analytics
Cloud" (14.00 — falso positivo: a area 8.0 vinha do NOME DO PRODUTO) caiu
para **6.00 (posicao 99/170)** — mascarado o produto no titulo, a area zerou
e so restaram skills/idioma/tipo/local; "Praktikum im Bereich Logistik und
Supply Chain Design" em 5o (11.50); "Working Student - Marketing" nao chega
ao quartil superior; nenhuma vaga senior no TOP 10; nenhum JMP no eligible;
nenhum communications/marketing/media no TOP 10 (novo sanity da Fase 2);
o presales SCM (B-list do dono) segue no TOP 10 com a area real de Supply
Chain no titulo (a mudanca nao penaliza contexto).
Ver `scripts/test_ranking.py` (sintetico + run real + sanity checks).

## Runbook

### Como adicionar empresas

Toda empresa-alvo entra pela base do `ats-scrapers` (match exato — o CLI
ignora com aviso qualquer nome que nao bata na base, para nao pegar empresa
parecida errada). Passos:

1. **Verifique o tenant exato, o ATS e o slug/URL** (baixa o manifest ~1–2 min):
   ```bash
   .venv/bin/python scripts/verify_companies.py "ZF,Bayer,BASF"
   ```
   Mostra, por empresa: tenant (`ats:slug`), o slug efetivo e se ha scraper
   registrado para o ATS. **Cuidado com falso positivo**: o match por token
   pode achar empresa parecida (ex.: `BMW` → `join_com:bmw-kuehnert`, que NAO
   e a BMW AG) — confira o nome retornado antes de incluir.

2. **Atencao a ATS que exigem a URL como slug**: `successfactors`, `workday`,
   `taleo` e `icims` — o slug da base (`jobs`) nao e usavel sozinho; o
   collector ja troca pelo `company.url` automaticamente (ex.: ZF →
   `https://jobs.zf.com`, BASF → `https://basf.jobs`, Zalando →
   `https://zalando.wd3.myworkdayjobs.com/zalandositewd`).

3. **Teste o status real do tenant** (alguns existem na base mas estao
   inativos/devolvem 0 vagas — ex.: Siemens/teamtailor → erro, Adidas/moka →
   sem scraper no pacote):
   ```bash
   .venv/bin/python scripts/verify_companies.py "ZF,Bayer" --fetch --timeout 60
   ```
   Reporta por tenant: `OK` com N vagas / `FAIL` (inativo) / `SKIP` (sem
   scraper) / `NONE` (sem match). So inclua na lista final empresas com `OK`.
   A tabela de verificacao atual (incl. excluidas e motivos) esta em
   `docs/empresas_verificacao.md`.

### Como rodar

**Coleta** (grava o bruto em `data/jobs.json` e ja aplica a cascata, gravando
as eligible em `data/eligible_jobs.json` + `.csv`):
```bash
.venv/bin/internship-finder --companies "Bosch,SAP,Continental,ZF,Bayer,BASF,Henkel,Infineon,Zalando,Delivery Hero,Covestro,Evonik" --timeout 60
```
**Filtro** (re-aplica a cascata sobre o bruto ja coletado, sem rede):
```bash
.venv/bin/internship-finder --country de          # Alemanha (default)
.venv/bin/internship-finder --country europe      # Europa inteira
.venv/bin/internship-finder --no-area             # qualquer area, desde que estudante
.venv/bin/internship-finder --no-rank             # sem ranking (ordem original)
```
Saida: contagens em cascata (`total → tipo estudante → area-alvo → pais`),
linha de dedup, **TOP 20 ranqueado por perfil** com score + breakdown, e os
arquivos gravados (`data/eligible_jobs.json`/`.csv` com campo `score`).

## Modelo `Job` (canonico, pydantic)

`id, source, title, company, location, country, remote, url, description,
internship, posted_at, collected_at, external_id, employment_type, country_iso, raw`.

- `source` e `ats:slug` do tenant (ex.: `smartrecruiters:BoschGroup`).
- `id` deriva de `external_id` (ou hash da URL) prefixado pelo `source`.
- `internship` e preenchido pelo adapter via heuristica (`filters.py`, termos
  EN/PT/DE: intern, internship, working student, Werkstudent, Praktikum,
  iXp...). Graduate/absolvent NAO entram (perfil e de estudante atual);
  `PART_TIME` sozinho nao indica vaga de estudante; os programas de trainee
  (Graduate Trainee, Management Trainee, Junior Managers Program/JMP) sao
  EXCLUIDOS mesmo com `employment_type` "trainee" (regra do dono,
  pos-auditoria — `filters.PROGRAM_EXCLUSION_PATTERNS`).
- `raw` guarda os campos extras do ATS (sem duplicar a `description`).

## Estrutura

```
src/internship_finder/
├── models/         # Job e Company (pydantic, canonicos)
├── collectors/     # CompanyCollector (match exato), ats_scraper (fetch c/ timeout),
│                   # greenhouse (API direta), base (ABC)
├── adapters/       # AtsJobAdapter: normaliza schema de cada ATS para Job
├── resolver/       # CompanyResolver (fachada sobre o matching exato)
├── filters.py      # filtros de utilidade: is_student_role, area-alvo, pais, cascata
├── ranking.py      # ranking por perfil: score_job (score + breakdown) e rank_jobs
└── cli.py          # entry point `internship-finder` (filtro default + coleta)
scripts/collect_jobs.py   # atalho p/ rodar sem instalar
```

## Notas

- O schema de cada ATS e diferente (`url` vs `slug`, `title` vs `name`,
  `location` vs `locations`/`city`...); **nada e assumido universal** — o adapter
  resolve por cadeias de fallback e preserva campos extras em `raw`.
- SuccessFactors/Workday/Taleo/iCIMS exigem a **URL completa de careers como
  slug** (o slug da base, ex.: `jobs` p/ SAP/ZF, nao e usavel sozinho) — tratado
  automaticamente (`URL_SLUG_ATS`).
- Comportamento defensivo: timeout por scraper (subprocesso), erro registrado,
  segue para as proximas empresas.
