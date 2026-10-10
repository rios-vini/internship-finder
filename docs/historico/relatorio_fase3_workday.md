# Relatório — Fase 3: Workday — inferência de país segura (limitação documentada)
> 📜 **Documento histórico** (período da coleta: 2026-08-12). Estado atual e plano: MASTER_PLAN.md + PROJECT_STATUS.md.

**Data:** 2026-08-12 · **Branch:** feat/fix-workday (base `main` 4c3cfa6) · **Escopo:** correção controlada #3 do parecer B (auditoria pós-expansão). Sem novas empresas/paises/regras de negócio; pacote ats-scrapers intocado.

## 1. Diagnóstico — por que as empresas Workday zeravam eligible

- **9 tenants Workday na coleta E2 (2.516–2.519 brutas):** zeissgroup/external 812, evonik/external_careers 371, hellmann/hellmannexternaljobs 320, trumpf/trumpf_graduates_and_professionals 254, sartorius/sartoriuscareers 205, zalando/zalandositewd 162, covestro/cov_external 136, trumpf/TRUMPF_Students 78, datev/Datev_Careers 63, trumpf/TRUMPF_Apprenticeships 60, freseniusglobal/fse 54 → **0 eligible**.
- **Evidência no `raw` (data/jobs.json):** a API Workday expõe majoritariamente **apenas a string de localização com a cidade sozinha** (`Oberkochen`, `Leverkusen`, `Nuremberg`, `2 Locations`) — `country_iso`/`region`/`lat`/`lon` vêm `None`. Sem país no dado, não há inferência segura possível.
- **Defeito real do nosso fallback (corrigível e corrigido):** o scan de 2 letras do `infer_country_iso` (fallback 3 antigo) aceitava **qualquer token de 2 letras em qualquer posição** da location que colidisse com ISO 3166-1. Isso **inventava ISOs falsos**: 168/2516 vagas Workday carregavam código inventado (11 delas falsamente `de`, de localizações no México/Espanha; também `im` Ilha de Man de "Freiburg im Breisgau", `do` República Dominicana de "São Bernardo do Campo", `de` Alemanha de "Ecatepec, Estado de México"). O filtro de país DE usava esses códigos falsos como se fossem reais.
- **Por que o eligible não mudava com o bug:** as vagas Workday com ISO falso caíam antes nos filtros de tipo/área; o problema real era de **qualidade do dado** (país errado/inventado), não de quantidade no eligible.

## 2. Correção (genérica, no nosso código — `src/internship_finder/filters.py`)

**`_iso_token_from_location`** substitui o scan de 2 letras: um token de 2 letras só é aceito como país em **posição confiável**:
- **último segmento** da localização (ex.: `Neckarsulm, DE`, `Stuttgart, BW, de`); ou
- **imediatamente antes de um CEP numérico** (ex.: SAP grava `Walldorf, DE, 69190` sem campo de país).

Token de 2 letras **no meio** da localização NÃO vale: é palavra (`de` es/PT, `im` DE, `do` PT) ou abreviação de estado (US/CA/AU). A correção vale para **todos os ATS** (sem exceção por empresa — quem beneficia: SAP intacto, Workday sem ISO falso, Phenom/eightfold sem junk).

Limite conhecido documentado: sigla de estado US como último segmento colide com ISO válido (`Lafayette, IN` → `in`; Indiana/India) — sem contexto para distinguir; comportamento mantido de propósito (nunca produz `de`).

Regras de Fase 1/2 intactas: `TYPE_EXCLUSION_PATTERNS` (ruído de tipo) e `_country_name_from_location`/`COUNTRY_NAMES` (nome do país no fim da location — Phenom/DHL) preservadas e priorizadas.

## 3. Funil ANTES × DEPOIS (pipeline real, `data/jobs.json` = 56.810 brutas)

| Métrica | ANTES (Fase 2) | DEPOIS (Fase 3) |
| --- | ---: | ---: |
| eligible | 293 | **293** (inalterado) |
| DHL (phenom) | 4 | 4 (preservada) |
| Workday eligible | 0 | 0 (limitação documentada) |
| ISOs falsos (junk) em qualquer ATS | presentes (ex.: `am`, `im`, `do`, `de` falso) | **eliminados** |
| eligible atuais que mudaram de ISO | — | **0** |

- `experiments/diff_final.py` (diff com o módulo real): `eligible atuais que mudam de iso: 0` — nenhuma vaga do Top/eligible mudou de país; o fix é puramente de qualidade.
- Correções por ATS no dataset bruto (amostra): eightfold `st`→`us` (`St. Louis, Missouri, United States`), `ba`→`vn` (Vietnam), phenom `am`→`de` (Remseck am Neckar, Germany), `de`→`mx` (Cienega de flores, Mexico), `do`→`br`, `la`→`fr`/`cr`; workday `de` falso→None/correto.

## 4. Validação de país (nenhum inventado)

- Todo ISO novo (ou None) vem de dado real da API: nome de país explícito na location (Fase 2) ou token de 2 letras em posição confiável (Fase 3) — sempre membro de `COUNTRY_CODES`.
- Locais Workday sem país na API ficam `None` (não inventamos): `Leverkusen`, `Oberkochen`, `Nuremberg`, `2 Locations` → None (testes F3).
- Regressões verificadas: `Walldorf, DE, 69190` → `de` (SAP); `Neckarsulm, DE` → `de`; `Stuttgart, BW, de` → `de`; `Dormagen, North Rhine-Westphalia, Germany` → `de` (Covestro).

## 5. Limitação Workday (decisão do dono: documentar em vez de inventar)

A API Workday (todos os 9 tenants observados) **não expõe país** para a maioria das vagas — apenas cidade sozinha. Sem país no dado, inferir seria inventar (proibido). **Limitação documentada:** vagas Workday sem localização com país explícito continuam fora do eligible DE até que a API/coletor exponha o país — e o pipeline agora não fabrica códigos falsos para mascarar isso.

## 6. Testes

`scripts/test_filters.py` ganhou 14 casos F3: Workday `Ecatepec, Estado de México`→None (era `de` falso), `Freiburg im Breisgau`→None (era `im`), `São Bernardo do Campo`→None (era `do`), `El Prat de Llobregat`→None (era `de`), cidades sozinhas→None, adapter com shape Workday real→country_iso None, e regressões (`Neckarsulm, DE`, `Stuttgart, BW, de`, `Berlin, DE, 10557`, Covestro nome de país) + limite conhecido `Lafayette, IN`. Suíte completa 7/7 exit 0 (test_dedup, test_fetch, test_filters, test_find_company, test_manifest, test_ranking, test_resolver).

## 7. Determinismo

`_iso_token_from_location`/`infer_country_iso` são funções puras e determinísticas (mesmos dados → mesmos ISOs → mesmo funil). Re-execução do pipeline produz o mesmo conjunto (293).

## 8. Resultado vs critérios do parecer B

- ✅ Nenhum país inferido de forma insegura (junk eliminado, Workday documentado)
- ✅ Nenhum ATS vazou para filters/ranking (correção só na inferência de país, filtro de país intacto)
- ✅ Pipeline determinístico
- ✅ Sem regressão de adapters/empresas (0 mudanças de ISO no eligible; suíte 7/7)
- ✅ Aumento sem ruído (eligible estável; qualidade do Top 20 intacta)
