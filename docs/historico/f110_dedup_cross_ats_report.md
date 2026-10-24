# F110 — Dedup cross-ATS: jobs.lidl ↔ praktikum.info (Relatório)

## Resumo

**Problema**: 2 pares de vagas Lidl confirmadas na mão na varredura 237 (sinal 3) sobreviveram ao dedup F92 (aliases+guards) e F103 (repost por chave vista):
- `1446902933` (sf_dataset:successfactors) ≡ `13355221` (praktikum_info) — "Preismanagement Nonfood"
- `1441830833` (sf_dataset:successfactors) ≡ `13308139` (praktikum_info) — "Lieferantenentwicklung"

**Causa-raiz**: IDs cross-ATS diferentes (cada ATS numera independentemente); empresas com labels diferentes (`lidlstiftup2` vs `Lidl Stiftung & Co. KG`); localizações com formatos diferentes (`Neckarsulm, DE` vs `74167 Neckarsulm`). Nenhum dos tiers clássicos (1-5) casa.

**Solução**: Novo tier 6 no dedup clássico (`cross_ats_mirror`) — chave `(empresa_canonica, titulo_normalizado)` aplicada **apenas** para pares de fontes espelhadas curadas (`config/dedup_mirrored_sources.json`). Fail-closed, zero FP no corpus.

## Implementação

### Arquivos modificados

1. **`src/internship_finder/dedup.py`** (+130 linhas):
   - Nova constante `KEY_CROSS_ATS_MIRROR = "cross_ats_mirror"`
   - Nova função `_load_mirrored_sources()` — carrega `config/dedup_mirrored_sources.json` (fail-closed)
   - Nova função `_canonical_company_mirror()` — resolve label do tenant via aliases do par
   - Nova função `_is_mirrored_pair()` — verifica se duas fontes formam par conhecido
   - Cache `_get_mirrored_sources()` — carrega uma vez
   - `candidate_keys()`: gera chave `cross_ats_mirror` quando fonte pertence a par curado
   - `deduplicate()`: guarda especial — só casa `cross_ats_mirror` se fontes formam par espelhado

2. **`config/dedup_mirrored_sources.json`** (novo):
   ```json
   {
     "mirrored_pairs": [{
       "name": "lidl_jobs_lidl_praktikum_info",
       "source_a": "sf_dataset:successfactors",
       "source_b": "praktikum_info",
       "company_aliases": {"lidlstiftup2": "Lidl Stiftung & Co. KG"}
     }]
   }
   ```

3. **`scripts/test_f110.py`** (novo): 18 checks offline
   - 2 pares positivos (devem fundir)
   - 3 contra-casos (NÃO fundem: Lieferantenmanagement≠Entwicklung, Preismanagement≠Marketing, mesma fonte)
   - Medição corpus inteiro: 0 FP

4. **`scripts/test_f66.py`**: H10 atualizado — agora espera que tier 6 FUNDE o par Lidl

5. **`README.md`**: documenta o 5º tier clássico + cross-ATS mirror

### Fluxo da chave

```
Job (sf_dataset:successfactors, company="lidlstiftup2", title="Praktikum Preismanagement...")
    ↓ candidate_keys()
    ↓ source in mirrored_pairs? YES (sf_dataset:successfactors ↔ praktikum_info)
    ↓ aliases = {"lidlstiftup2": "Lidl Stiftung & Co. KG"}
    ↓ company_canon = "Lidl Stiftung & Co. KG" → casefold → "lidl stiftung & co. kg"
    ↓ title_norm = normalize_title() → "datenanalyse food non preismanagement student working"
    ↓ key = ("cross_ats_mirror", ("lidl stiftung & co. kg", "datenanalyse food non preismanagement student working"))
```

Job do praktikum_info gera a **mesma chave** (company já é "Lidl Stiftung & Co. KG", title idêntico).

`deduplicate()`: ao encontrar match em `seen[key]`, verifica `_is_mirrored_pair(source_a, source_b)` — só prossegue se True.

## Validação

### Testes unitários (test_f110.py)
```
== Normalização de título == (4 OK)
== Pares positivos (devem fundir) == (6 OK)
== Contra-casos (NÃO devem fundir) == (9 OK)
== Medição corpus inteiro (0 FP) == (2 OK)
==== test_f110 OK ====
```

### Regressão (test_dedup.py, test_f66.py, test_f97.py)
Todos passam (0 falhas). `test_f66.py` H10 agora valida que tier 6 FUNDE o par Lidl.

### Corpus de produção (eligible_jobs.json, 688 vagas)
- `sf_dataset:successfactors` (lidlstiftup2): 88 vagas
- `praktikum_info` (Lidl Stiftung & Co. KG): 1 vaga (demais filtradas por elegibilidade)
- Dedup: 688 → 688 (0 removidas no corpus atual — apenas 1 lado de cada par no eligible)
- **0 falso-positivo** detectado

> Nota: no raw `jobs.json` (antes dos filtros) ambos os lados de cada par existem e seriam fundidos. O eligible já passou por filtros de área/país/tipo que removem um dos lados.

## Contra-medida (Zero FP)

Padrão F66: 20 twins medidos, zero FP. F110 herda:
- Curadoria estrita: só entra par auditado (slugs/URLs confirmam mesmo empregador)
- Chave conservadora: `normalize_title` (bag de palavras, ordem indiferente, marcadores de tipo colapsados, palavras funcionais removidas) — um token de conteúdo divergente impede fusão
- Guard de fonte: `_is_mirrored_pair()` impede fusão intra-fonte (ex.: 2 vagas "Warengeschäft" no mesmo SF não fundem)
- Alias exato casefold: `"lidlstiftup2"` → `"Lidl Stiftung & Co. KG"`; substring nunca casa

### Contra-casos validados
| Título A | Título B | Resultado |
|----------|----------|-----------|
| Lieferantenentwicklung & Prozessoptimierung | Lieferantenmanagement - Konzepte & Projekte | NÃO funde (conteúdo diferente) |
| Preismanagement & Datenanalyse Non Food | Marketing International - Product Content Non Food | NÃO funde (conteúdo diferente) |
| Qualquer par mesma fonte (praktikum_info × praktikum_info) | — | NÃO funde (não é cross-ATS) |

## Impacto no pipeline

- **Ordem**: tier 6 roda DENTRO do `deduplicate()` clássico, antes de `deduplicate_ms_wildcard` (F23), `deduplicate_mirrors_de_en` (Fase C) e `deduplicate_cross_source` (F48)
- **Reversível**: `--no-dedup` desliga tudo (inclui tier 6); arquivo de config ausente/ilegível → `{}` (degradação graciosa)
- **Estatística**: `cross_ats_mirror` aparece no relatório do CLI e no JSONL `type: run` (`dedup_removed`)
- **Winner**: regra `_prefer` padrão (description > employment_type > frescor > ordem entrada) — o lado do dataset (com description) vence

## Próximos passos

- [x] Implementação + testes + README
- [ ] PR com anchor no MESMO branch (P0 v5)
- [ ] Deploy via refresh_daily (próximo run 09:00 UTC)
- [ ] Monitorar alerta F75 (radar de grupos) — pode subir se novos espelhos aparecerem

## Evidência de diagnóstico (Passo 0)

```python
# Antes do F110: candidate_keys NÃO gerava cross_ats_mirror
keys_sf = candidate_keys(JOB_LIDL_PREIS)  # sem cross_ats_mirror
keys_pi = candidate_keys(JOB_PI_PREIS)    # sem cross_ats_mirror
# tiers 1-5: external_id diferentes, URL diferentes, company diferentes, location diferentes
# Resultado: 2 vagas no eligible

# Depois do F110:
keys_sf = candidate_keys(JOB_LIDL_PREIS)  # COM cross_ats_mirror
keys_pi = candidate_keys(JOB_PI_PREIS)    # COM cross_ats_mirror (mesma chave)
# dedup casa → 1 vaga no eligible
```