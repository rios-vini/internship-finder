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

### Dependencias do projeto vs snapshot do ambiente

Dois arquivos na raiz com papeis diferentes (nao confundir):

- **`pyproject.toml`** — a fonte de verdade das dependencias do projeto
  (declaradas + restricoes de versao). A instalacao padrao (`pip install -e .`,
  acima) e o CI resolvem as dependencias a partir dele.
- **`requirements-lock.txt`** — snapshot congelado do ambiente resolvido
  (`pip freeze` do venv), para reproducao exata do ambiente quando necessario.
  Nao e um lock declarativo moderno (uv.lock/poetry.lock), nao e a fonte primaria
  das dependencias e nao e usado pelo CI nem pela instalacao padrao. Regenerar na
  raiz do repo com `.venv/bin/python -m pip freeze > requirements-lock.txt`
  (o cabecalho do arquivo documenta isso).

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
.venv/bin/internship-finder                              # data/jobs.json -> data/eligible_jobs.json (476 eligible no run do cron 18/09)
.venv/bin/internship-finder --country europe             # Europa inteira em vez de so Alemanha
.venv/bin/internship-finder --no-area                    # qualquer area, desde que estudante + Alemanha
.venv/bin/internship-finder --no-dedup                   # mantem duplicatas (507 antes da dedup)
.venv/bin/internship-finder --no-rank                    # sem ranking: ordem original + exemplos
.venv/bin/internship-finder --all                        # copia tudo, sem filtros
# validacao sem escrever em data/ (dados locais sao gitignored):
.venv/bin/internship-finder --country de --output /tmp/eligible.json --metrics /tmp/coleta.jsonl
```

**Coleta** — fluxo original (grava o bruto em `data/jobs.json`) e ja aplica a
mesma cascata, gravando o resultado em `data/eligible_jobs.json`. A lista de
empresas nao e mais colado no comando: vem do **registry** (fonte de verdade
das 101 empresas em codigo — ver "Registry de empresas" abaixo):

```bash
.venv/bin/internship-finder --registry --timeout 60
# subconjunto, na ordem informada (empresas fora do registry sao ignoradas):
.venv/bin/internship-finder --registry --companies "Bosch,SAP" --timeout 60
# ou, sem instalar:
python scripts/collect_jobs.py --companies "Bosch,SAP" --output data/jobs.json
```

### Registry de empresas

As 101 empresas operacionais da coleta (12 da validacao inicial + 27 da expansao
E2 + 25 da expansao 08/09 — P3 #23, Otto removida em 15/09 — + 17 da expansao
de cobertura 15/09 + 6 da auditoria 16/09 + 9 da auditoria próxima fronteira
17/09 + 5 da última onda de cobertura 18/09: Sungrow EMEA, AutoScout24, Huawei
Research Center Germany, EAT HAPPY GROUP, VDI Technologiezentrum GmbH — ver
`docs/` e MASTER_PLAN #23 e o
Log de mudanças) vivem em **codigo**, no `SEED` de
`src/internship_finder/registry.py` — a
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
- A **consistencia Registry x runtime** (tenant declarado x tenant que o
  runtime efetivamente resolve/coleta) e verificada por empresa pelo
  `--health` na secao `registry_consistency` (classificacao por empresa:
  `consistent` / `drift` / `multi` / `dynamic` / `not_found` / `no_data` —
  logica pura em `src/internship_finder/registry.py`, testes em
  `scripts/test_registry_consistency.py`). Medido em 18/09/2026: 0 drift;
  83 consistent, 15 multi (declarado presente com cobertura extra) e
  3 dynamic (None declarado, resolucao pela base).
- Seed e modelo: `src/internship_finder/registry.py` (pydantic, `SEED` com as
  101 entradas operacionais); testes em `scripts/test_registry.py`.

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
ambiente do chamador. Novo arquivo `requirements-lock.txt` na raiz (snapshot de
reproducibilidade via pip freeze, fora do CI).

**Credenciais** (`.env` na raiz — gitignored): `TELEGRAM_BOT_TOKEN` e
`TELEGRAM_CHAT_ID`. Sem token no `.env` o script loga aviso e NAO envia
(nunca crasha). Envio via Bot API `sendMessage` (stdlib, sem dependencia
nova); falha de rede do envio e logada, nao derruba o refresh.

### Backup do jobs.db (P3)

O historico SQLite (`data/jobs.db`, first_seen/last_seen/active/archived) tem
**backup proprio** a cada run do refresh — o `.db` e acumulativo e nao
rotaciona, entao merece snapshot independente do archive de JSONs.

- **Onde**: `data/backups/jobs-<timestamp>.db` (`jobs-YYYYMMDDTHHMMSSZ.db`,
  UTC — multiplos backups com historico ordenavel). `data/` e gitignored.
- **Mecanismo**: backup API do sqlite3 (`sqlite3.Connection.backup()`,
  stdlib), com a origem aberta **read-only** — snapshot CONSISTENTE mesmo com
  o banco em uso, sem risco para o banco principal (nunca e escrito pela
  rotina). O artefato sai em `journal_mode=DELETE`: **um unico arquivo SQLite
  standalone**, sem sidecars `-wal`/`-shm`, validado por `PRAGMA quick_check`
  antes do nome final (escrita atomica: temporario + rename).
- **Automatico**: apos a coleta de cada refresh (`scripts/refresh_daily.py`).
  Falha de backup NUNCA derruba o run nem muda o exit code — e logada e
  entra como `⚠️ Backup do jobs.db falhou: ...` na mensagem do Telegram (so
  quando ha envio no run).
- **Manual**:
  ```bash
  .venv/bin/python scripts/backup_db.py                              # data/jobs.db -> data/backups/
  .venv/bin/python scripts/backup_db.py --db data/jobs.db --retention-days 14  # + limpeza
  .venv/bin/python scripts/backup_db.py --dry-run                    # so mostra destino
  ```
  Exit 0 = backup criado (imprime o caminho); 2 = falha (stderr claro, banco
  principal intocado). No script manual a retencao e OPCIONAL (default 0 =
  nao apaga nada) — backup manual nao deve apagar historico por surpresa.
- **Retencao**: simples e documentada, mesma politica do archive —
  `--backup-retention-days N` no refresh (default **14** dias; `0` desliga;
  negativo rejeitado); nomes fora do formato `jobs-*.db` sao preservados com
  aviso. Sem lifecycle complexo (deliberado).
- **Restauracao manual**: parar o refresh (ou garantir que nada esta
  escrevendo no banco) e sobrescrever o banco com o backup:
  ```bash
  cp data/backups/jobs-<timestamp>.db data/jobs.db
  ```
  O arquivo e um SQLite normal e utilizavel; o `SqliteStore` reativa o WAL no
  proximo open. Recomendado conferir com
  `.venv/bin/python -c "import sqlite3; print(sqlite3.connect('data/jobs.db').execute('PRAGMA integrity_check').fetchone())"`.
- **Limitação**: a origem pode ganhar sidecars `-wal`/`-shm` transientes
  durante o snapshot (comportamento WAL normal do SQLite; somem quando a
  proxima conexao de escrita fecha). O backup em si e sempre um arquivo unico.

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

Resultado do ultimo run completo (cron de 18/09 06:00 UTC; numeros reproduzidos
offline por `scripts/coverage.py` e pelo pipeline com o codigo atual):
`total 72.866 -> tipo estudante 6.635 -> area-alvo 1.411 -> Alemanha 507`;
pos-dedup: **476** eligible/ranked (31 remocoes), todos `country_iso='de'` —
**65 empresas com vagas eligible** (top: BMW AG 81, SAP 74, BoschGroup 48,
Volkswagen AG 23, teampicnic 20, Fraunhofer-Gesellschaft 19, Knorr-Bremse 15,
Liebherr-International S.A. 13 — demais na tabela de cobertura). Notas: (1) desde 06/09 o filtro exclui o equivalente EN de
aprendizagem (Apprentice/Apprenticeship — mesmo criterio do Ausbildung DE;
P3 #31, PR #31); (2) o baseline antigo (12/08, 56.810 → 293) era de outra
janela de mercado; a queda de volume **nao e regressao**. Dados em `data/` sao
locais e gitignored: os numeros servem como documentacao de coleta, nao como
arquivos versionados. A coleta total leva alguns minutos — cada tenant usa
timeout proprio (`--timeout 60`).

### Cobertura (101 na coleta → 65 com vagas eligible no run 18/09)

**"Avaliada", "operacional" e "com vagas eligible" sao metricas DIFERENTES**:

- **Avaliada** = empresa que passou pela verificacao do runbook
  (`docs/empresas_verificacao.md`): match exato na base do `ats-scrapers` e
  teste do tenant/ATS. Apos as expansoes de 15/09, 16/09, 17/09 e 18/09, sao **101 empresas**
  operacionais na coleta (12 da validacao inicial + 27 novas + 25 da expansao
  08/09, Otto removida 15/09 + 17 de cobertura 15/09 + 6 da auditoria 16/09
  + 9 da auditoria próxima fronteira 17/09: Picnic, cbs Corporate Business
  Solutions, AIXTRON SE, Holzland Becker, CarOnSale, CURRENTA GRUPPE, Miebach
  Consulting, Engelhart, audibene/hear.com + 5 da onda final 18/09: Sungrow
  EMEA, AutoScout24, Huawei Research Center Germany, EAT HAPPY GROUP, VDI
  Technologiezentrum GmbH).
- **Operacional** = retorna vagas no fetch real (tenant ativo, ATS com
  scraper): **39** no snapshot 07/09 (**pré-expansão #23** — 35 tenants com
  dados em `data/jobs.json`; a Bosch conta 2x no campo `company` — tenants
  `BoschGroup` e `bosch-homecomfort`). Re-medição feita no 1º run com 65
  empresas (08/09 — ver MASTER_PLAN #37 e o Log de mudanças de 08/09); run
  18/09 (101 empresas): **115 fontes ok no run (100 empresas com vagas
  coletadas; 9 sem vagas → bruto com 114 nomes de `company` distintos / 92
  tenants com dados, contando variantes reportadas pelo ATS — ex.:
  `careers.dhl.com`, `BoehringerPRD`).**
- **Com vagas eligible** = tem pelo menos 1 vaga eligible na Alemanha apos a
  cascata de filtros + dedup: **65** empresas / 50 tenants (medido no run 18/09).

Falhas conhecidas (motivo da exclusao): Siemens (tenant `teamtailor` inativo),
Mercedes-Benz e ThyssenKrupp (sem match exato na base). BMW entra somente como
**BMW AG** (16/09, `successfactors:jobs` jobs.bmwgroup.com) — a consulta "BMW"
sozinha continua falso positivo (`join_com:bmw-kuehnert`). **Expansao E2**:
Symrise (API join.com 422), Hager Group e Lanxess ja RESOLVIDAS (adicionadas
15/09; o "XML malformado" era limitacao do pin antigo do ats-scrapers);
identidades excluidas por decisao:
ifm (join 422), Metro (falso positivo), E.ON (sem match), GFT
(0 vagas + FP `icims:gannettfleming`). Kuehne+Nagel (suica) entrou em 15/09
via `phenom:nan` (multi; cornerstone DNS-fail recorrente por run, esperado).

**Falhas recorrentes DOCUMENTADAS (investigadas em 17/09, classificadas como
legitimas/externas — continuam aparecendo no health/refresh de proposito,
NAO silenciar)**:

1. **Lidl** (`successfactors:lidlstiftuP2`) — timeout recorrente (15 runs em 18/09):
   feed externo enorme gerado sob demanda; aumentar timeout global/por fonte nao e
   aceitavel.
2. **Kuehne+Nagel** (`cornerstone:kuehne-nagel`) — tenant Cornerstone morto/NXDOMAIN;
   a empresa valida continua sendo coletada via `phenom:nan`.
3. **SMA** (`oracle:fa-exow-saasfaprod1/cx_1`) — homonimo externo confirmado
   (academia maritima em Sharjah); nao adicionar `oracle` ao mecanismo de slug e
   nao criar exclusao especifica (decisao 17/09).
Adidas e
Boehringer Ingelheim **nao sao mais exclusoes atuais**: a Adidas coleta
normalmente (run 13/09 com **74 vagas** coletadas), a Boehringer coleta via
`successfactors:BoehringerPRD` (run 14/09: **462 vagas** coletadas), todas
participando da coleta; **Otto foi REMOVIDA em 15/09** (falso positivo —
`jazzhr:otto` = otto.applytojob.com, nao e o Otto Group; nao readicionar).
Limitacao de dados: **Workday** (Covestro,
Evonik, Zalando e as novas Trumpf/Sartorius/DATEV/Zeiss/Hellmann/Fresenius)
nao expoe codigo de pais nas localizacoes alemas — vagas alemas desses tenants
ficam sem `country_iso` e o filtro de pais nao as inclui. **Mitigacao
opcional**: `geocoding.py` (flag `INTERNSHIP_FINDER_GEOCODING`, OFF por
default) resolve cidade → `de` via lista local + cache + geocoder (OSM), um
fallback pos-`infer_country_iso` no adapter — com a flag ligada, o eligible
do snapshot historico 31/08 subiu de 236 para **245** (+9 Workday DE
recuperadas; medicao historica). No run 18/09, 16 vagas eligible vieram de
tenants workday mesmo com a flag OFF (re-inferencia via location).

Resumo de cobertura (reproduzido por `scripts/coverage.py`, offline e
deterministico — `.venv/bin/python scripts/coverage.py`):

| Metrica | Valor |
| --- | --- |
| Funil: raw → tipo → area → pais (DE) | 72.866 → 6.635 → 1.411 → 507 (run cron 18/09, 101 empresas) |
| eligible (pos-dedup) → ranked | 507 → 476 (31 removidas na dedup, company+title+location; run 18/09) |
| Empresas com eligible / tenants (source) | 65 / 50 (bruto run 18/09: 114 nomes de empresa / 92 tenants com dados; registry: 101; fontes ok no run: 115) |
| Top empresas (eligible) | BMW AG 81, SAP 74, BoschGroup 48, Volkswagen AG 23, teampicnic 20, Fraunhofer-Gesellschaft 19, Knorr-Bremse 15, Liebherr-International S.A. 13, BASF SE 13, STIHL 12, ... (65 empresas no total; run 18/09) |
| Contribuicao das maiores | top1 17,0% (BMW AG 81/476) | top3 42,6% | top5 51,7% |
| Top ATS (eligible) | successfactors 296, smartrecruiters 54, greenhouse 33, phenom 24, workday 16, recruitee 14, eightfold 12, cornerstone 10, softgarden 6, ashby 4, personio 4, teamtailor 3 |
| Paises (eligible) | `de` 476 (100%) — None/localizacao desconhecida: 0 (0,0%); (medicao historica com `INTERNSHIP_FINDER_GEOCODING=1` sobre o snapshot 31/08: 245) |

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
| `--sqlite PATH` | modo coleta: persiste o historico de cada vaga (`first_seen`/`last_seen`/`active`/`archived`) em banco `sqlite3` na PATH (default: desligado). **P1.2**: o lifecycle (archive de nao-vistos) e atualizado POR UNIDADE de coleta confiavel `(company, source)` — empresas/tenants com timeout/erro/not_found nao tem vagas arquivadas (ausencia observada != ausencia por falha de coleta) |
| `--health [PATH]` | modo health (unico quando presente): relatorio JSON por tenant/ATS sobre o JSONL de metricas + alertas; arquivo inexistente -> erro no stderr e exit != 0 |
| `--verbose` | log DEBUG |

Ambiente:

| Variavel | Descricao |
| --- | --- |
| `INTERNSHIP_FINDER_GEOCODING` | OFF por default. Com `=1`, liga o geocoder de rede (OSM Nominatim) + cache no fallback de pais (`geocoding.py`). Com OFF, o fallback se limita a lista local de cidades + cache ja populado — nenhuma chamada de rede. Medicao historica (snapshot 31/08): levava o eligible DE de 236 (pipeline 232) para **245** (+9 Workday). |

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
de traducao/fuzzy, fora do escopo do MVP. No snapshot de 31/08 (historico):
eligible 258 -> 236 (22 removidas, todas pela chave 3; 0 por external_id/URL).
Com o dedup 2.0 (P2 #14) o pipeline produzia **232** (4 duplicatas TRUE a mais —
pares EN/DE do mesmo cargo; ver `MASTER_PLAN.md` #14). No run 18/09:
507 -> 476 eligible (31 removidas).

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
graca: skills/idioma contribuem 0 e o score vem do titulo. Metrica do
snapshot de 31/08 (historico; 236 eligible; pipeline dedup 2.0 = 232, medido por
`scripts/test_ranking.py`):
scores `min 1.0 | mediana 6.0 | max 16.75` (257 eligible, run 14/09 — historico).
No run 18/09 (476 eligible): scores `min 1.0 | mediana 6.25 | max 17.5`.
Ver `scripts/test_ranking.py` (suite sintetica com `FIXTURE` fixa, desacoplada
do snapshot desde o P2 #16 — 03/09; bloco real roda como invariantes de
formato/observabilidade; suite local 23/23 TUDO OK — 23 do CI + o probe manual
`scripts/manifest_probe.py`, que nao faz parte da suite do CI).

**Medicao do ranking (P2.5, 11/09/2026)**: benchmark versionado com **59 vagas
reais rotuladas manualmente** (`benchmarks/ranking_benchmark_v1.json`).
Resultado: universo 260 eligible com **96,5% das vagas empatadas**, concordancia
ordinal 82,5% (tau +0,65 — o ranking tem sinal real), mas **67% das vagas
empatadas da amostra em grupos com qualidade humana diferente** → decisao
**Caso C (baixa resolucao real)**: calibracao justificada, redesign/embeddings/ML
sem evidencia. Metodologia, metricas e hipoteses de calibracao (H1 descricao
ausente, H2 language, H3 desempate): `docs/ranking_benchmark.md`. Relatorio
reproduzivel: `.venv/bin/python scripts/ranking_benchmark.py`; reproduzir o
benchmark em snapshot novo: `scripts/make_ranking_benchmark.py refresh`.

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
   inativos/devolvem 0 vagas — ex.: Siemens/teamtailor → erro, Mercedes-Benz
   → NONE (sem match exato na base)):
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

**Interface** (P3 #25, 08/09) — leitura amigavel das vagas ranqueadas, sem servidor:
```bash
.venv/bin/python scripts/interface.py                # HTML em /tmp/interface.html (top 25 por score)
.venv/bin/python scripts/interface.py --top 50 --company sap --keyword student --output -
.venv/bin/python scripts/interface.py --db data/jobs.db   # SQLite (sem score: ordena por last_seen)
```
Pagina HTML auto-contida (CSS/JS inline, zero dependencia nova): top N por score,
filtros `--company`/`--keyword`/`--country`, URL clicavel, breakdown do score em
badges. Filtragem client-side do browser e so ocultacao sobre o conjunto ja
filtrado na geracao; a logica testada e a do script (`scripts/test_interface.py`).

## Modelo `Job` (canonico, pydantic)

`id, source, title, company, location, country, remote, url, description,
internship, posted_at, collected_at, application_deadline, external_id,
employment_type, country_iso, raw`.

- `source` e `ats:slug` do TENANT (origem tecnica; ex.:
  `smartrecruiters:BoschGroup`). O mesmo tenant pode ser compartilhado por
  varias empresas (ex.: `successfactors:jobs` cobre SAP/ZF/Kaufland/...;
  `phenom:nan` cobre DHL/Allianz/Merck/...) — `source` NAO identifica a
  empresa (P1.1).
- `id` = `<company>|<source>:<external_id>` (ou `<company>|<source>:<hash da
  URL>` sem `external_id`) — identidade escopada por empresa + tenant ATS:
  duas empresas no MESMO tenant com o MESMO `external_id` produzem ids
  diferentes, estaveis e deterministicos.
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
(antes ausente em 100% das linhas). **Ambos** (JSON e CSV) sao escritos com
substituicao atomica (temporario no mesmo diretorio + `os.replace`, ver
`_write_atomic` em cli.py): falha na geracao preserva o arquivo final
anterior intacto, sem temporarios residuais.

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
├── registry.py     # CompanyRegistry: fonte unica das 101 empresas de coleta (SEED, P2 #13)
└── cli.py          # entry point `internship-finder` (filtro default + coleta)
scripts/collect_jobs.py   # atalho p/ rodar sem instalar
scripts/refresh_daily.py  # refresh diario + alertas Telegram (rotacao -> coleta -> health -> alerta)
scripts/verify_companies.py  # runbook de empresas (match exato + fetch)
scripts/coverage.py       # cobertura: funil + empresas/ATS/paises (offline)
scripts/interface.py      # interface simples: top vagas ranqueadas + filtros (HTML stdlib; P3 #25)
scripts/test_*.py         # suite standalone ([OK]/[FAIL]; exit 0 = TUDO OK) — test_refresh = refresh diario
requirements-lock.txt      # snapshot do ambiente (pip freeze; fora do CI; deps = pyproject.toml)
```

## Status / Roadmap

Os numeros e o plano de execucao sao mantidos no **`MASTER_PLAN.md`** (fonte de
verdade do plano: ranking P0–P4 com status ✅/⏳) e no **`PROJECT_STATUS.md`**
(estado medido atual). `docs/roadmap.md` ficou como historico do MVP. CI:
GitHub Actions (`.github/workflows/ci.yml`) roda a suite standalone
(`scripts/test_*.py`) em runner limpo — exit 0 = TUDO OK. Licença: MIT
(`LICENSE`); políticas de segurança em `SECURITY.md`.

## Notas

- O schema de cada ATS e diferente (`url` vs `slug`, `title` vs `name`,
  `location` vs `locations`/`city`...); **nada e assumido universal** — o adapter
  resolve por cadeias de fallback e preserva campos extras em `raw`.
- SuccessFactors/Workday/Taleo/iCIMS exigem a **URL completa de careers como
  slug** (o slug da base, ex.: `jobs` p/ SAP/ZF, nao e usavel sozinho) — tratado
  automaticamente (`URL_SLUG_ATS`).
- Comportamento defensivo: timeout por scraper (subprocesso), erro registrado,
  segue para as proximas empresas.
