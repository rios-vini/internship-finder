# internship-finder

Buscador de estagios (internship / working student / Praktikum / Werkstudent) com
foco em **Supply Chain, Procurement, BI, Analytics e Automacao**, prioridade para a
**Alemanha**. Pipeline **orientado a empresas**:

```
Empresa → find_company (match exato) → ATS → scraper (subprocesso + timeout) → adapter → Job (pydantic) → filtros → dedup → ranking → print/save (JSON/CSV)
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

O CLI tem tres modos: **filtro** (default), **coleta** (`--companies`) e **health** (`--health`).

**Filtro** — le vagas ja coletadas e retorna apenas as ELIGIBLE
(estudante/estagio + area-alvo + pais), **ranqueadas por perfil** (score +
TOP 20), gravando em `data/eligible_jobs.json` + `.csv` (com campo `score`;
`--no-rank` desliga o ranking). Conceitos do pipeline:

```
collected -> filtered -> eligible -> deduplicated -> ranked -> best matches
```

`eligible` e o conceito final da cascata (passou em tipo + area + pais);
**best matches = TOP N do ranked** (sem entidade/camada nova):

> **Nota (dados)**: `data/` e gitignored e local — os numeros abaixo sao
> documentacao de coleta, nao arquivos versionados. O default
> (`data/eligible_jobs.json`/`.csv`) grava localmente; para validacao sem
> depender de `data/`, use `--output`/`--filter-output`/`--metrics` dedicados
> (ex.: `/tmp/...`).

```bash
.venv/bin/internship-finder                              # data/jobs.json -> data/eligible_jobs.json (222 eligible no run do cron 06/09)
.venv/bin/internship-finder --country europe             # Europa inteira em vez de so Alemanha
.venv/bin/internship-finder --no-area                    # qualquer area, desde que estudante + Alemanha
.venv/bin/internship-finder --no-dedup                   # mantem duplicatas (258 antes da dedup)
.venv/bin/internship-finder --no-rank                    # sem ranking: ordem original + exemplos
.venv/bin/internship-finder --all                        # copia tudo, sem filtros
# validacao sem escrever em data/ (dados locais sao gitignored):
.venv/bin/internship-finder --country de --output /tmp/eligible.json --metrics /tmp/coleta.jsonl
```

**Coleta** — fluxo original (grava o bruto em `data/jobs.json`) e ja aplica a
mesma cascata, gravando o resultado em `data/eligible_jobs.json`. A lista de
empresas nao e mais colada no comando: vem do **registry** (fonte de verdade
das 39 empresas em codigo — ver "Registry de empresas" abaixo):

```bash
.venv/bin/internship-finder --registry --timeout 60
# subconjunto, na ordem informada (empresas fora do registry sao ignoradas):
.venv/bin/internship-finder --registry --companies "Bosch,SAP" --timeout 60
# ou, sem instalar:
python scripts/collect_jobs.py --companies "Bosch,SAP" --output data/jobs.json
```

### Registry de empresas

As 39 empresas operacionais da coleta (12 da validacao inicial + 27 da expansao
E2) vivem em **codigo**, no `SEED` de `src/internship_finder/registry.py` — a
fonte de verdade do "quem coleta": nome canonico (a consulta do `--companies`),
ATS/tenant de referencia e `enabled` (desabilitar tira da coleta sem apagar do
registry). Nada de lista colada em doc: o `--companies` continua aceito por
compatibilidade, mas a lista oficial e o registry.

```bash
.venv/bin/internship-finder --registry --timeout 60          # todas as ENABLED
.venv/bin/internship-finder --registry --companies "Bosch,SAP" --timeout 60  # subconjunto
```

- `--registry` (modo coleta): usa as empresas `enabled` do registry como lista;
  `--companies` so restringe a um subconjunto (na ordem informada).
- O **estado por empresa** (status/ultima coleta) NAO fica no registry: e
  derivado do JSONL de metricas (`company_status`, read-only) e exposto pelo
  `--health` (implementado em 06/09, PR #31) — registry = configuracao,
  JSONL = status (decisao de design).
- Seed e modelo: `src/internship_finder/registry.py` (pydantic, `SEED` + 39
  entradas); testes em `scripts/test_registry.py`.

### Daily refresh (P2 #17)

Rotina de producao que **faz a coleta real diariamente** e **alerta via
Telegram SOMENTE em anomalia** (anti-spam), reusando o health do P1 #6:

```bash
.venv/bin/python scripts/refresh_daily.py              # producao (cacheia em data/)
.venv/bin/python scripts/refresh_daily.py --dry-run    # demonstrativo: tempdir sintetico, sem rede/data
.venv/bin/python scripts/refresh_daily.py --always-notify  # digest diario (nao e o default)
```

Fluxo: (1) **rotacao** — copia `data/jobs.json`/`.csv`,
`data/eligible_jobs.json`/`.csv` e `data/collection_metrics.jsonl` para
`data/archive/<timestamp>/` (copia, nao move: a origem fica intacta ate o CLI
gravar; rollback = copiar de volta o archive + re-rodar `--health`); (2)
**coleta real** — subprocesso do CLI (`--registry --timeout 60`, teto total
`--max-collection-secs`, default 5400s); (3) **health** — `build_health_report`
sobre o JSONL completo pos-run; (4) **alerta** — 1 mensagem por run, alertas
deduplicados por fonte, disparado quando exit != 0 (coleta falhou/parcial) OU o
relatorio tem alertas (queda brusca / erro recorrente / **zero-return**: uma
fonte que tinha vagas e passou a responder `empty` por ≥3 runs ok>0 anteriores
— P2 #10); sem anomalia, nada é
enviado. `--always-notify` envia o resumo mesmo sem anomalia (digest, opcional).

**Comportamento novo (06/09, PR #30)**: a coleta do refresh roda com
`--sqlite data/jobs.db` (historico `first_seen`/`last_seen`/`active`/`archived`
em producao; o `.db` NAO e rotacionado — e acumulativo e vive em `data/`,
gitignored); o archive e limpo automaticamente apos cada rotacao
(`--retention-days N`, default 14, 0 = desliga); uso de disco acima de 80%
entra como `⚠️ Disco: N% usado` na mensagem; o subprocesso da coleta herda o
ambiente do chamador. Novo arquivo `requirements-lock.txt` na raiz (lock de
reproducibilidade, fora do CI).

**Credenciais** (`.env` na raiz — gitignored): `TELEGRAM_BOT_TOKEN` e
`TELEGRAM_CHAT_ID`. Sem token no `.env` o script loga aviso e NAO envia
(nunca crasha). Envio via Bot API `sendMessage` (stdlib, sem dependencia
nova); falha de rede do envio e logada, nao derruba o refresh.

**Cron** (instalado no VPS, 05/09): diario as 06:00 UTC, com `flock -n`
(nao sobrepoe runs; se o anterior ainda roda, o novo e pulado):

```
0 6 * * * /usr/bin/flock -n /tmp/internship_finder_refresh.lock /home/ubuntu/internship-finder/.venv/bin/python /home/ubuntu/internship-finder/scripts/refresh_daily.py >> /tmp/refresh_daily.log 2>&1
```

> **Corrigido 05/09 (noite)**: a 1a versao usava `flock ... cd /repo && python ...`
> (padrao da tarefa), mas **flock executa o comando via `execvp`** — `cd` e
> builtin do shell e nao existe como binario (falha "failed to execute cd",
> exit 69) e o `&&` desligaria o python do lock. A linha acima usa caminhos
> ABSOLUTOS (o script nao depende de cwd; resolve a raiz via `__file__`) e o
> lock cobre o run inteiro. Validado: preflight cron-like (`env -i PATH=/usr/bin:/bin`
> + `--dry-run`, exit 0, sem tocar `data/`) e reentrada do flock (`-n` com lock
> segurado → exit 1; liberado → exit 0).

**Limitação documentada**: o JSONL de metricas acumulava lixo historico de
validacao (registros `type: tenant` de mocks, ex.: `smartrecruiters:other` 70x
`error` de 25/08–04/09). O health e defensivo (malformados pulados), mas lixo
VALIDO entra nas contagens por fonte — uma fonte que so tem lixo emitiria
"erro recorrente" em todo run ate o JSONL ser limpo. **Sanitizado em 05/09
(noite)**: 460 → 104 linhas (removidos 142 run records de mock + 214 tenant
records Acme/DATEV por criterio de run_id dos 4 runs reais: 31/08 37.373,
01/09 1.084 x2, 05/09 38.038; preservados 100 tenant records de 39 companies).
Backups: `/tmp/collection_metrics_pre_clean_0509.jsonl` (estado pos-E2E) +
`data/archive/20260905T204307Z/collection_metrics.jsonl` (pre-E2E). Health
pos-limpeza: 1 alerta factual — `successfactors:lidlstiftuP2` timeout em 31/08
e 05/09.

Resultado do ultimo run completo (cron de 06/09 06:00 UTC; numeros reproduzidos
offline por `scripts/coverage.py` e pelo pipeline com o codigo atual):
`total 37.953 -> tipo estudante 3.080 -> area-alvo 752 -> Alemanha 246`;
pos-dedup: **222** eligible/ranked (24 remocoes, todas por company+title+location),
todos `country_iso='de'` — **24 empresas com vagas eligible** (top: SAP 71,
BoschGroup 41, Volkswagen AG 20, BASF SE 17, Knorr-Bremse 16 — demais na tabela
de cobertura). Notas: (1) desde 06/09 o filtro exclui o equivalente EN de
aprendizagem (Apprentice/Apprenticeship — mesmo criterio do Ausbildung DE;
P3 #31, PR #31); (2) o baseline antigo (12/08, 56.810 → 293) era de outra
janela de mercado; a queda de volume **nao e regressao**. Dados em `data/` sao
locais e gitignored: os numeros servem como documentacao de coleta, nao como
arquivos versionados. A coleta total leva alguns minutos — cada tenant usa
timeout proprio (`--timeout 60`).

### Cobertura (39 na coleta → 24 com vagas eligible)

**"Avaliada", "operacional" e "com vagas eligible" sao metricas DIFERENTES**:

- **Avaliada** = empresa que passou pela verificacao do runbook
  (`docs/empresas_verificacao.md`): match exato na base do `ats-scrapers` e
  teste do tenant/ATS. Apos a expansao E2 (2026-08-12), sao **39 empresas**
  operacionais na coleta (12 da validacao inicial + 27 novas).
- **Operacional** = retorna vagas no fetch real (tenant ativo, ATS com
  scraper): **39** (35 tenants com dados em `data/jobs.json`; a Bosch conta
  2x no campo `company` — tenants `BoschGroup` e `bosch-homecomfort`).
- **Com vagas eligible** = tem pelo menos 1 vaga eligible na Alemanha apos a
  cascata de filtros + dedup: **24** empresas / 20 tenants (medido no run 06/09).

Falhas conhecidas (motivo da exclusao): Siemens (tenant `teamtailor` inativo),
BMW (falso positivo: so `join_com:bmw-kuehnert`, nao a BMW AG),
Mercedes-Benz e ThyssenKrupp (sem match exato na base), Adidas (ATS `moka` sem
scraper no pacote). **Na expansao E2**: Hager Group, Boehringer Ingelheim e
Lanxess (SuccessFactors devolve XML malformado), Symrise (API join.com 422);
identidades excluidas por decisao: ifm (join 422), Metro e Otto (falsos
positivos), E.ON (sem match), Kuehne+Nagel (suica — fora do escopo "empresas
alemas"), GFT (0 vagas no momento). Limitacao de dados: **Workday** (Covestro,
Evonik, Zalando e as novas Trumpf/Sartorius/DATEV/Zeiss/Hellmann/Fresenius)
nao expoe codigo de pais nas localizacoes alemas — vagas alemas desses tenants
ficam sem `country_iso` e o filtro de pais nao as inclui. **Mitigacao
opcional**: `geocoding.py` (flag `INTERNSHIP_FINDER_GEOCODING`, OFF por
default) resolve cidade → `de` via lista local + cache + geocoder (OSM), um
fallback pos-`infer_country_iso` no adapter — com a flag ligada, o eligible
sobe para **245** (+9 Workday DE recuperadas).

Resumo de cobertura (reproduzido por `scripts/coverage.py`, offline e
deterministico — `.venv/bin/python scripts/coverage.py`):

| Metrica | Valor |
| --- | --- |
| Funil: raw → tipo → area → pais (DE) | 37.953 → 3.080 → 752 → 246 (run cron 06/09) |
| eligible (pos-dedup) → ranked | 246 → 222 (24 removidas na dedup, company+title+location; run 06/09) |
| Empresas com eligible / tenants (source) | 24 / 20 (bruto: 39 empresas / 35 tenants) |
| Top empresas (eligible) | SAP 71, BoschGroup 41, Volkswagen AG 20, BASF SE 17, Knorr-Bremse 16, Schaeffler 8, ... (24 empresas no total; run 06/09) |
| Contribuicao das maiores | top1 32,0% (SAP 71/222) — re-medir com `coverage.py` | top3 ~59% | top5 ~74% |
| Top ATS (eligible) | successfactors 150, smartrecruiters 41, eightfold 11, workday 8, phenom 5, ashby 3, greenhouse 3, cornerstone 1 |
| Paises (eligible) | `de` 222 (100%) — None/localizacao desconhecida: 0 (0,0%); (medicao historica com `INTERNSHIP_FINDER_GEOCODING=1` sobre o snapshot 31/08: 245) |

(Fase 3: `country_iso` tem fonte unica — `filters.infer_country_iso`; a
heuristica antiga de "tail da location" foi removida do adapter, entao
"Friedrichshafen, BW, DE, 88046" vira `de` e nao mais `None`.)

Saida: contagens em cascata (`total -> tipo estudante -> area-alvo -> pais`),
linha de dedup (`removidas N: X por external_id, Y por URL, Z por
company+title+location`), **TOP 20 ranqueado por perfil** (score + breakdown
curto; `--no-rank` desliga e mostra exemplos como antes) e os arquivos
gravados com o campo `score`.

Flags do CLI:

| Flag | Descricao |
| --- | --- |
| `--companies` | modo coleta: nomes separados por virgula (match exato na base; sem match, a empresa e ignorada com aviso) |
| `--registry` | modo coleta orientado ao registry: usa as empresas `enabled` do `CompanyRegistry` (fonte de verdade em codigo); com `--companies` restringe a subconjunto, na ordem informada |
| `--input` | modo filtro: JSON bruto de entrada (default: `data/jobs.json`) |
| `--output` | filtro: saida eligible (default: `data/eligible_jobs.json`); coleta: saida bruta (default: `data/jobs.json`) |
| `--filter-output` | modo coleta: saida eligible (default: `data/eligible_jobs.json`) |
| `--student` / `--no-student` | filtra tipo estudante/estagio (Internship, Working Student, Praktikum, Werkstudent, iXp...; default: ligado) |
| `--area` / `--no-area` | filtra areas-alvo do dono (Supply Chain, Procurement, BI, Analytics, Automacao; default: ligado) |
| `--country`/`--countries` | pais/localizacao: ISO alpha-2 (`de`, `de,at,ch`), `europe`, `remote` ou `all` (default: `de`; valores fora desses -> erro claro, exit 2) |
| `--all` | desliga os tres filtros de uma vez (copia o conjunto inteiro) |
| `--dedup` / `--no-dedup` | remove duplicatas da saida (default: ligado) |
| `--rank` / `--no-rank` | rankeia por compatibilidade com o perfil: score + TOP 20 (default: ligado; `--no-rank` mantem a ordem original) |
| `--timeout` | teto de segundos por scraper (defensivo: uma empresa que trava nao derruba o resto); valor `<= 0` -> erro claro, exit 2 (P3 #20) |
| `--limit N` | maximo de vagas por tenant, aplicado APOS a coleta (0 = sem limite); valor negativo -> erro claro, exit 2 (P3 #20) |
| `--include-descriptions` | busca a descricao por vaga (mais lento em ATS que exigem uma chamada por vaga, ex. SmartRecruiters) |
| `--metrics PATH` | JSONL de metricas da execucao (modo coleta; default: `data/collection_metrics.jsonl`) |
| `--sqlite PATH` | modo coleta: persiste o historico de cada vaga (`first_seen`/`last_seen`/`active`/`archived`) em banco `sqlite3` na PATH (default: desligado) |
| `--health [PATH]` | modo health (unico quando presente): relatorio JSON por tenant/ATS sobre o JSONL de metricas + alertas; arquivo inexistente -> erro no stderr e exit != 0 |
| `--verbose` | log DEBUG |

Ambiente:

| Variavel | Descricao |
| --- | --- |
| `INTERNSHIP_FINDER_GEOCODING` | OFF por default. Com `=1`, liga o geocoder de rede (OSM Nominatim) + cache no fallback de pais (`geocoding.py`). Com OFF, o fallback se limita a lista local de cidades + cache ja populado — nenhuma chamada de rede. Lei o eligible DE (snapshot 236; pipeline 232) para **245** (+9 Workday). |

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
de traducao/fuzzy, fora do escopo do MVP. No conjunto atual (31/08, snapshot):
eligible 258 -> 236 (22 removidas, todas pela chave 3; 0 por external_id/URL).
Com o dedup 2.0 (P2 #14) o pipeline produz **232** (4 duplicatas TRUE a mais —
pares EN/DE do mesmo cargo; ver `MASTER_PLAN.md` #14).

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

Sem descricao (parte das vagas em que o ATS nao expoe descricao), age-se com
graca: skills/idioma contribuem 0 e o score vem do titulo. Metrica real do
snapshot de 31/08 (236 eligible; pipeline dedup 2.0 = 232, medido por
`scripts/test_ranking.py`):
scores `min 2.50 | mediana 6.75 | max 16.75` (222 eligible, run 06/09).
Ver `scripts/test_ranking.py` (suite sintetica com `FIXTURE` fixa, desacoplada
do snapshot desde o P2 #16 — 03/09; bloco real roda como invariantes de
formato/observabilidade; suite local 17/17 TUDO OK — 16 do CI + `test_manifest`).

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
   A tabela de verificacao em `docs/empresas_verificacao.md` e **historica** —
   revalidar o estado real dos tenants com `scripts/verify_companies.py`.

### Como rodar

**Coleta** (grava o bruto em `data/jobs.json` e ja aplica a cascata, gravando
as eligible em `data/eligible_jobs.json` + `.csv`; a lista de empresas vem do
registry — ver "Registry de empresas"):
```bash
.venv/bin/internship-finder --registry --timeout 60
# subconjunto, na ordem informada:
.venv/bin/internship-finder --registry --companies "Bosch,SAP" --timeout 60
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
> Validacao/saidas gravam em `data/` por default (local, gitignored); para nao
> depender de `data/`, use `--output PATH`/`--filter-output PATH`/`--metrics PATH`.

## Modelo `Job` (canonico, pydantic)

`id, source, title, company, location, country, remote, url, description,
internship, posted_at, collected_at, application_deadline, external_id,
employment_type, country_iso, raw`.

- `source` e `ats:slug` do tenant (ex.: `smartrecruiters:BoschGroup`).
- `id` deriva de `external_id` (ou hash da URL) prefixado pelo `source`.
- `application_deadline` (`datetime|None`) e preenchido pelo adapter **quando o
  ATS expoe a data explicitamente**; permanece `None` caso contrario e **nunca**
  e inferido de `posted_at` (regra do dono).
- `country_iso` tem FONTE UNICA: o adapter usa `filters.infer_country_iso`
  (ISO alpha-2 valido via `COUNTRY_CODES`; fallback `country_iso` -> `country`
  -> tokens da location). Nenhuma heuristica de tail no adapter — Fase 3; como
  fallback pos-`infer_country_iso`, o `geocoding.py` (opcional, flag OFF) pode
  resolver cidade → pais.
- `internship` e preenchido pelo adapter via heuristica (`filters.py`, termos
  EN/PT/DE: intern, internship, working student, Werkstudent, Praktikum,
  iXp...). Graduate/absolvent NAO entram (perfil e de estudante atual);
  `PART_TIME` sozinho nao indica vaga de estudante; os programas de trainee
  (Graduate Trainee, Management Trainee, Junior Managers Program/JMP) sao
  EXCLUIDOS mesmo com `employment_type` "trainee" (regra do dono,
  pos-auditoria — `filters.PROGRAM_EXCLUSION_PATTERNS`).
- `raw` guarda os campos extras do ATS (sem duplicar a `description`).

### Saida (JSON/CSV) — contrato P3 #20/ACH-18

`save_outputs` grava sempre um par no mesmo caminho de base (`--output
data/jobs.json` -> `data/jobs.csv`): o **JSON e a fonte completa** (todos os
campos do Job, incluindo `description`, `raw` e `score_breakdown`); o **CSV e
a visao tabular** com as 16 colunas de `CSV_COLUMNS` (`id, title, company,
location, country, country_iso, remote, url, source, external_id,
employment_type, internship, posted_at, application_deadline, collected_at,
score`) — `description`/`raw`/`score_breakdown` ficam de fora de proposito
(texto grande/aninhado). Medido 05/09: jobs.csv com 38.038/38.038 linhas do
jobs.json (0 ids divergentes); a coluna `remote` foi adicionada em 06/09
(antes ausente em 100% das linhas).

## Estrutura

```
src/internship_finder/
├── models/         # Job e Company (pydantic, canonicos)
├── collectors/     # CompanyCollector (match exato), ats_scraper (fetch c/ timeout)
├── adapters/       # AtsJobAdapter: normaliza schema de cada ATS para Job
├── resolver/       # CompanyResolver (fachada sobre o matching exato)
├── storage/        # sqlite_store: historico por vaga (first_seen/last_seen/active/archived)
├── filters.py      # filtros de utilidade: is_student_role, area-alvo, pais, cascata
├── countries.py    # pais/localizacao: ISO codes, nomes, infer_country_iso, spec (extraido de filters.py, P2 #12)
├── dedup.py        # deduplicacao: chaves por confiabilidade (id/external_id, URL, c+title+loc)
├── ranking.py      # ranking por perfil: score_job (score + breakdown) e rank_jobs
├── metrics.py      # metricas de execucao em JSONL (por tenant + resumo do run)
├── errors.py       # codigos de erro estruturados (CollectionError + classificador)
├── health.py       # relatorio de health por tenant/ATS sobre o JSONL + alertas
├── geocoding.py    # fallback de pais por cidade (cache-first; flag OFF por default)
├── registry.py     # CompanyRegistry: fonte unica das 39 empresas de coleta (SEED, P2 #13)
└── cli.py          # entry point `internship-finder` (filtro default + coleta)
scripts/collect_jobs.py   # atalho p/ rodar sem instalar
scripts/refresh_daily.py  # refresh diario + alertas Telegram (rotacao -> coleta -> health -> alerta)
scripts/verify_companies.py  # runbook de empresas (match exato + fetch)
scripts/coverage.py       # cobertura: funil + empresas/ATS/paises (offline)
scripts/test_*.py         # suite standalone ([OK]/[FAIL]; exit 0 = TUDO OK) — test_refresh = refresh diario
requirements-lock.txt      # lock de reprodutibilidade (pip freeze; fora do CI; adicionado 06/09)
```

## Status / Roadmap

Os numeros e o plano de execucao sao mantidos no **`MASTER_PLAN.md`** (fonte de
verdade do plano: ranking P0–P4 com status ✅/⏳) e no **`PROJECT_STATUS.md`**
(estado medido atual). `docs/roadmap.md` ficou como historico do MVP. CI:
GitHub Actions (`.github/workflows/ci.yml`) roda a suite standalone
(`scripts/test_*.py`) em runner limpo — exit 0 = TUDO OK.

## Notas

- O schema de cada ATS e diferente (`url` vs `slug`, `title` vs `name`,
  `location` vs `locations`/`city`...); **nada e assumido universal** — o adapter
  resolve por cadeias de fallback e preserva campos extras em `raw`.
- SuccessFactors/Workday/Taleo/iCIMS exigem a **URL completa de careers como
  slug** (o slug da base, ex.: `jobs` p/ SAP/ZF, nao e usavel sozinho) — tratado
  automaticamente (`URL_SLUG_ATS`).
- Comportamento defensivo: timeout por scraper (subprocesso), erro registrado,
  segue para as proximas empresas.
