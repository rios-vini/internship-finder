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

**Filtro** — le vagas ja coletadas e retorna apenas as CANDIDATAVEIS
(estudante/estagio + area-alvo + pais), gravando em
`data/relevant_jobs.json` + `.csv`:

```bash
.venv/bin/internship-finder                              # data/jobs.json -> data/relevant_jobs.json (186 vagas)
.venv/bin/internship-finder --country europe             # Europa inteira em vez de so Alemanha
.venv/bin/internship-finder --no-area                    # qualquer area, desde que estudante + Alemanha
.venv/bin/internship-finder --all                        # copia tudo, sem filtros
```

**Coleta** — fluxo original (grava o bruto em `data/jobs.json`) e ja aplica a
mesma cascata, gravando o resultado em `data/relevant_jobs.json`. Lista-alvo
atual (12 empresas com dados, validada em 2026-08-10; ver
`docs/empresas_verificacao.md`):

```bash
.venv/bin/internship-finder --companies "Bosch,SAP,Continental,ZF,Bayer,BASF,Henkel,Infineon,Zalando,Delivery Hero,Covestro,Evonik" --timeout 60
# ou, sem instalar:
python scripts/collect_jobs.py --companies "Bosch,SAP" --output data/jobs.json
```

Resultado do ultimo run completo (13 empresas candidatas, 13.482 vagas brutas):
`total 13.482 -> tipo estudante 2.159 -> area-alvo 541 -> Alemanha 186` (SAP 104,
Bosch 49, BASF 21, Henkel 4, ZF 3, Bayer 2, Infineon 2, Continental 1).
Siemens foi testada e excluida (tenant `teamtailor` inativo). A coleta total
leva alguns minutos — cada tenant usa timeout proprio (`--timeout 60`).

Saida: contagens em cascata (`total -> tipo estudante -> area-alvo -> pais`),
exemplos (titulo, empresa, local, URL) e os arquivos gravados.

Flags do CLI:

| Flag | Descricao |
| --- | --- |
| `--companies` | modo coleta: nomes separados por virgula (match exato na base; sem match, a empresa e ignorada com aviso) |
| `--input` | modo filtro: JSON bruto de entrada (default: `data/jobs.json`) |
| `--output` | filtro: saida filtrada (default: `data/relevant_jobs.json`); coleta: saida bruta (default: `data/jobs.json`) |
| `--filter-output` | modo coleta: saida filtrada (default: `data/relevant_jobs.json`) |
| `--student` / `--no-student` | filtra tipo estudante/estagio (Internship, Working Student, Praktikum, Werkstudent, iXp, trainee/JMP...; default: ligado) |
| `--area` / `--no-area` | filtra areas-alvo do dono (Supply Chain, Procurement, BI, Analytics, Automacao; default: ligado) |
| `--country`/`--countries` | pais/localizacao: ISO alpha-2 (`de`, `de,at,ch`), `europe`, `remote` ou `all` (default: `de`) |
| `--all` | desliga os tres filtros de uma vez (copia o conjunto inteiro) |
| `--timeout` | teto de segundos por scraper (defensivo: uma empresa que trava nao derruba o resto) |
| `--limit N` | maximo de vagas por tenant (0 = sem limite) |
| `--include-descriptions` | busca a descricao por vaga (mais lento em ATS que exigem uma chamada por vaga, ex. SmartRecruiters) |
| `--verbose` | log DEBUG |

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
as candidataveis em `data/relevant_jobs.json` + `.csv`):
```bash
.venv/bin/internship-finder --companies "Bosch,SAP,Continental,ZF,Bayer,BASF,Henkel,Infineon,Zalando,Delivery Hero,Covestro,Evonik" --timeout 60
```
**Filtro** (re-aplica a cascata sobre o bruto ja coletado, sem rede):
```bash
.venv/bin/internship-finder --country de          # Alemanha (default)
.venv/bin/internship-finder --country europe      # Europa inteira
.venv/bin/internship-finder --no-area             # qualquer area, desde que estudante
```
Saida: contagens em cascata (`total → tipo estudante → area-alvo → pais`),
exemplos (titulo, empresa, local, URL) e os arquivos gravados.

## Modelo `Job` (canonico, pydantic)

`id, source, title, company, location, country, remote, url, description,
internship, posted_at, collected_at, external_id, employment_type, country_iso, raw`.

- `source` e `ats:slug` do tenant (ex.: `smartrecruiters:BoschGroup`).
- `id` deriva de `external_id` (ou hash da URL) prefixado pelo `source`.
- `internship` e preenchido pelo adapter via heuristica (`filters.py`, termos
  EN/PT/DE: intern, trainee, student, working student, Werkstudent, Praktikum,
  iXp...). Graduate/absolvent NAO entram (perfil e de estudante atual) e
  `PART_TIME` sozinho nao indica vaga de estudante.
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
