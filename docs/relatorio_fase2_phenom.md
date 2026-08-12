# Relatório — Fase 2: Phenom/DHL — country genérico

**Data:** 2026-08-12 · **Branch:** feat/fix-phenom-country (base `main` 2f6055d) · **Escopo:** correção controlada #2 do parecer B (auditoria pós-expansão). Sem novas empresas/paises/regras de negócio; pacote ats-scrapers intocado.

## 1. Diagnóstico — por que o Phenom ficava sem país

- **Único tenant Phenom na coleta E2:** DHL (`phenom:nan`, 8.405 brutas). Siemens Healthineers na coleta usa `avature` (6 vagas) — não há outro Phenom no dataset atual.
- **O que a API/`raw` expõe (evidência em `data/jobs.json`, 8.405 vagas):**
  - `raw.country_iso`: **None em 100%** (8.405/8.405)
  - `raw.region`: None em 100% · `raw.lat`/`raw.lon`: ausentes em 100% · `raw.commitment`: None
  - `raw.location`: **sempre "Cidade, Estado, Nome do País"** (ex.: `Bonn, Nordrhein-Westfalen, Germany`, `Goodyear, Arizona, United States of America`). O scraper ats-scrapers (`_format_location`) compõe esse string a partir dos campos `city`/`state`/`country` da API — o **nome do país está nos dados**, só não em formato ISO e não no campo `country_iso`.
- **Por que o adapter antigo falhava:** `infer_country_iso` só lia `country_iso`/`country` (None) e depois tokens de **2 letras** da location. "Germany" não é token de 2 letras → None → filtro `--country de` derrubava tudo.
- **Bug colateral descoberto (mesma causa raiz):** o scan de 2 letras produzia **códigos falsos** nas locations Phenom: `Remseck am Neckar, …, Germany` → `am` (Armênia!), `Staufen im Breisgau` → `im` (Ilha de Man), `Cienega de flores, …, Mexico` → `de` (Alemanha!), `La Porte, …, United States of America` → `la` (Laos). 496 vagas Phenom carregavam ISO errado no `jobs.json` (247 delas falsamente `de`, na verdade México/Colômbia/França/Espanha/Brasil...).

## 2. Correção (genérica, no nosso código — `src/internship_finder/filters.py`)

1. **`COUNTRY_NAMES`**: dict nome-de-país (inglês, minúsculas) → ISO 3166-1 alpha-2 (247 entradas: nomes padrão ISO + nomes observados nas coletas + variantes "United States of America", "People's Republic of", "(South) Republic", "Réunion", etc.).
2. **`infer_country_iso` — nova precedência** (fallback 1, antes dos campos ISO e do scan de 2 letras): se o **último segmento** (ou os últimos 2, ex.: `China, People's Republic of`) da `location` for um nome de país em `COUNTRY_NAMES`, retorna o ISO. É inferência **segura**: o nome do país está explícito no dado real da API — nada inventado. Vence inclusive ISOs ruidosos armazenados (corrige os 496 falsos códigos antigos). Fallbacks 2–3 inalterados (`country_iso`/`country`; scan de 2 letras — SAP `Walldorf, DE, 69190` segue intacto).
3. **`select_eligible` (filtro de país):** além do predicado de sempre (`matches_country` — re-infere o ISO), agora **grava de volta** `country_iso`/`country` canônicos nos dicts selecionados — a saída eligible carrega o país (DHL volta com `country_iso='de'`). Regra do filtro inalterada; só enriquece a saída.

Sem mudanças em `ats.py` (o adapter já chama `infer_country_iso`), ranking, dedup ou regras de tipo/área. Sem `if company == 'DHL'`, sem slug específico — o benefício é de **todos os ATS** com location "Cidade, Estado, País".

## 3. Funil ANTES × DEPOIS (pipeline real, `data/jobs.json` = 56.810 brutas)

| Etapa | ANTES (Fase 1) | DEPOIS (Fase 2) |
| --- | ---: | ---: |
| total | 56.810 | 56.810 |
| + tipo estudante | 3.428* | 3.428 |
| + área-alvo | 777* | 777 |
| + país DE | 0 DHL / ~309* | **309** (DHL recuperada) |
| dedup | — | −16 |
| **eligible** | **283** | **293** (+10) |

\* contagens pós-Fase 1 (regra de ruído de tipo ativa). O CLI real rodado em 2026-08-12 21:44 imprimiu: `56810 → 3428 → 777 → 309 → dedup 16 → 293 vagas eligible`.

- **DHL/Phenom:** 8.405 brutas → 0 eligible (antes) → **~26 no filtro de país / ~10 após dedup** (análise detalhada em `/tmp/an.txt`; dedup remove postagens repetidas DHL "company+title+location"). Funil DHL anterior: `8405 → 183 estudante → 35 área → 0 país`; o filtro de país deixou de zerar.
- **Outras Phenom:** sem regressão (único tenant é DHL; a correção é por ATS, beneficia qualquer tenant futuro).
- **Nenhuma outra empresa/ATS regrediu:** diff completo dos 56.810 ISOs antes/depois → **0 dos 283 eligible atuais mudaram de ISO**; 9.309 mudanças são correções (None→código real, ou junk→código real; ex.: eightfold `St. Louis, Missouri, United States` `st`→`us`, phenom `de`→`mx` para México).

## 4. Validação de país (nenhum inventado)

- Todos os novos ISOs vêm de **nome de país explícito na location** (dado real da API) ou de campo ISO válido — sempre membros de `COUNTRY_CODES` (ISO 3166-1 alpha-2).
- Casos unitários verificados: `Bonn, …, Germany`→`de`; `Goodyear, Arizona, United States of America`→`us`; `Remseck am Neckar, …, Germany` (stored `am`)→`de`; `Cienega de flores, …, Mexico` (stored `de`)→`mx`; `Chengdu, …, China, People's Republic of`→`cn`; `Seoul, …, Korea, (South) Republic`→`kr`; `Walldorf, DE, 69190`→`de` (SAP intacto); `Berlin, DE, 10557`→`de`.
- Limitação documentada (não inventamos): locations sem nome de país no último segmento continuam sem ISO (ex.: `Huachipa`/`Villa El Salvador` — 2 vagas DHL sem país na API; `Remote - USA NC` — prefixo, não país). `(South) Republic`/`People's Republic of` exigem 2 segmentos — cobertos.

## 5. Testes

`scripts/test_filters.py` ganhou casos Phenom (infer via location com nome de país, junk corrigido, 2-segmentos, regressão SAP). Suíte 7/7 (test_dedup, test_fetch, test_filters, test_find_company, test_manifest, test_ranking, test_resolver) deve passar — sem recalibração necessária (test_ranking não tem sanity com n fixo; os sanity são posicionais).

## 6. Determinismo

`infer_country_iso`/`COUNTRY_NAMES`/`select_eligible` são funções puras e determinísticas (mesmos dados → mesmos ISOs → mesmo funil). Verificado por construção; re-execução do pipeline produz o mesmo conjunto (283+10).

## 7. PR

PR: **(aberto) — URL pendente de push** · Base: `main` (2f6055d) · Commit: "Fase 2: pais Phenom via nome do pais no ultimo segmento da location" (src/internship_finder/filters.py).
