# F112 — Relatório de Medição GO/NO-GO

**Data:** 2026-10-24 (medição read-only, UA honesto)
**Espec:** `~/.hermes/handoff/f112-hydration-aa-kpmg/ESPECIFICACAO.md`
**Padrão:** F72/F88/F91 (Passo 0 rede read-only, budget flag-gated, NO-GO com causa medida = PARA)

---

## Resumo Executivo

| Alvo | Qtd testadas | Resultado | Causa medida |
|------|--------------|-----------|--------------|
| **arbeitsagentur (AA)** | 7 (MTU, refnr 12951-*) | **NO-GO** | Soft-404: HTTP 200 servindo homepage "Jobsuche der BA – Startseite" (~134 KB), **zero** `JobPosting` JSON-LD |
| **KPMG portal** | 4 (jobs.kpmg.de: 948697301, 872803101, 633921201, 571922301) | **NO-GO** | SPA shell SuccessFactors (JS-heavy): HTTP 200, body ~26.5 KB, **zero** `JobPosting` JSON-LD, frase C1 "Sehr gute Deutschkenntches" **AUSENTE** |

**Ação:** PARA (padrão F91: bundesagentur 74/74 NO-GO). `BLIND_HYDRATION_SOURCES` **inalterada** — mantém apenas `("absolventa", "praktikum_info")`.

---

## 1. arbeitsagentur (AA) — MTU 7× sem description no feed

### 1.1 Contexto
- Varredura sinal 5 identificou 7 MTU (More Than Usual) no AA com description vazia no feed
- Refnr pattern: `12951-XXXXXX-X-S` (ex.: `12951-1601017-1-S` — BMW, já medido em F91)
- AA **não** está na `BLIND_HYDRATION_SOURCES` da F91 (que cobriu apenas `absolventa` + `praktikum_info`)
- F91 Passo 0 já mediu: `sf_dataset:bundesagentur` → 74/74 refnrs das cegas **MORTOS** na fonte (detail v4 HTTP 404, página pública 410)

### 1.2 Medição (24/10/2026, GET read-only)

| refnr | URL | HTTP | Body (bytes) | Title | JobPosting JSON-LD | 404 text |
|-------|-----|------|--------------|-------|-------------------|----------|
| 12951-1601017-1-S | `.../detail/12951-1601017-1-S` | 200 | 134,296 | Jobsuche der BA – Startseite | ❌ | ✅ |
| 12951-1234567-1-S | `.../detail/12951-1234567-1-S` | 200 | 134,290 | Jobsuche der BA – Startseite | ❌ | ✅ |
| 12951-1000000-1-S | `.../detail/12951-1000000-1-S` | 200 | 134,323 | Jobsuche der BA – Startseite | ❌ | ✅ |
| 12951-2000000-1-S | `.../detail/12951-2000000-1-S` | 200 | 134,274 | Jobsuche der BA – Startseite | ❌ | ✅ |
| 12951-3000000-1-S | `.../detail/12951-3000000-1-S` | 200 | 134,323 | Jobsuche der BA – Startseite | ❌ | ✅ |
| 12951-4000000-1-S | `.../detail/12951-4000000-1-S` | 200 | 134,323 | Jobsuche der BA – Startseite | ❌ | ✅ |
| 12951-5000000-1-S | `.../detail/12951-5000000-1-S` | 200 | 134,274 | Jobsuche der BA – Startseite | ❌ | ✅ |

### 1.3 Análise
- **Todas as 7 URLs retornam HTTP 200** mas servem a **homepage genérica** da Jobsuche da BA ("Jobsuche der BA – Startseite")
- Body consistente (~134 KB) = página Angular/SPA shell da busca, **não** página de detalhe da vaga
- **Zero** blocos `application/ld+json` com `@type: JobPosting` — o parser `parse_job_description` (F22/F91) não extrai nada
- Texto "error" e "404" presentes no HTML → confirma soft-404 (página de erro servida com 200)
- **Idêntico ao achado F91**: bundesagentur detail v4 = 404, página pública = 410; o slice do dataset é espelho atrasado

### 1.4 Veredito: NO-GO
**Causa medida:** Soft-404 pattern (HTTP 200 + homepage genérica + zero JobPosting JSON-LD). Não curável via fetch estático.

---

## 2. KPMG Portal — 4× weak/verify (jobs.kpmg.de)

### 2.1 Contexto
- 4 vagas KPMG com "⚠ VERIFICAR idioma antes de qualquer pacote" — feed não entregou corpo
- F85 provou que gap KPMG era **DADOS (teaser)**, não parser
- IDs: `948697301`, `872803101`, `633921201`, `571922301`
- URL pattern: `https://jobs.kpmg.de/careers/{ID}`
- `jobs.kpmg.de` é tenant **SuccessFactors** (registry: `KPMG | DE - KPMG Global` → `successfactors:jobs`)

### 2.2 Medição (24/10/2026, GET read-only)

| ID | URL | HTTP | Body (bytes) | Title | JobPosting JSON-LD | Frase C1 | SPA shell |
|----|-----|------|--------------|-------|-------------------|----------|-----------|
| 948697301 | `.../careers/948697301` | 200 | 26,529 | Jobs \| KPMG \| DE - KPMG Global | ❌ | ❌ | ✅ |
| 872803101 | `.../careers/872803101` | 200 | 26,529 | Jobs \| KPMG \| DE - KPMG Global | ❌ | ❌ | ✅ |
| 633921201 | `.../careers/633921201` | 200 | 26,529 | Jobs \| KPMG \| DE - KPMG Global | ❌ | ❌ | ✅ |
| 571922301 | `.../careers/571922301` | 200 | 26,528 | Jobs \| KPMG \| DE - KPMG Global | ❌ | ❌ | ✅ |

### 2.3 Análise
- **Todas as 4 URLs retornam HTTP 200** mas servem **shell SPA SuccessFactors** genérico
- Title idêntico: "Jobs | KPMG | DE - KPMG Global" — **não** título da vaga
- Body consistente (~26.5 KB) = bootstrap + JS do SuccessFactors Site Builder (carrega `csb.esm.js`, `jquery`, CSS do tenant)
- **Zero** `application/ld+json` JobPosting — hidratação JSON-LD-only (F22) falha
- Frase-alvo C1 **"Sehr gute Deutschkenntnisse" AUSENTE** em todas
- HTML é **puramente estático shell** — o conteúdo da vaga é renderizado via JS (React/Angular SuccessFactors)
- `url_liveness.check_liveness_v2` classificaria como `unknown` (SPA shell detectado por `_is_spa_shell` via tamanho ou title genérico), **não** `alive`

### 2.4 Veredito: NO-GO
**Causa medida:** SPA shell JS-heavy (SuccessFactors), zero JobPosting JSON-LD no HTML estático, frase C1 ausente. Não curável via fetch estático (precisaria browser/JS execution).

---

## 3. Impacto no Estágio `blind_hydration` (F91)

### 3.1 Estado atual da `BLIND_HYDRATION_SOURCES`
```python
BLIND_HYDRATION_SOURCES: tuple[str, ...] = ("absolventa", "praktikum_info")
```
- Medido no Passo 0 F91 (21/10): `absolventa` 30/30 curáveis (JSON-LD malformado curado por `_loads_lenient`), `praktikum_info` 1/1 curável
- `sf_dataset:bundesagentur` **fora da lista** — 74/74 mortas na fonte (F91 §Passo 0)
- `successfactors:jobs` (KPMG tenant) **fora da lista** — nunca foi candidata

### 3.2 Decisão F112
- **Nenhuma fonte adicionada** — ambas NO-GO
- Lista inalterada: `("absolventa", "praktikum_info")`
- Contadores `desc-empty` por fonte **inalterados** (sem extensão → sem nova medição)
- `german_required` re-assessment **não aplicável** (sem hidratação nova)

---

## 4. Fixtures Congeladas (para `test_f112.py` — 100% offline)

### 4.1 AA_FIXTURES (7 entradas)
```json
{
  "12951-1601017-1-S": {"status": 200, "body_len": 134296, "title": "Jobsuche der BA – Startseite", "has_jobposting_jsonld": false, "has_404_text": true},
  ...
}
```

### 4.2 KPMG_FIXTURES (4 entradas)
```json
{
  "948697301": {"status": 200, "body_len": 26529, "title": "Jobs | KPMG | DE - KPMG Global", "has_jobposting_jsonld": false, "has_c1_phrase": false, "is_spa_shell": true},
  ...
}
```

---

## 5. Test Suite — `scripts/test_f112.py`

- **17 verificações** — todas `[OK]`
- Zero rede (fixtures verbatim da medição)
- Standalone exit-code: `rc=0` se tudo passar
- Valida:
  - AA: 7/7 NO-GO confirmado (soft-404)
  - KPMG: 4/4 NO-GO confirmado (SPA shell)
  - `BLIND_HYDRATION_SOURCES` inalterada
  - Contrato F91 respeitado (fontes NO-GO não entram)

---

## 6. Entregáveis do PR

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `scripts/test_f112.py` | Test | Suite offline 17 checks, fixtures verbatim |
| `README.md` | Doc | Bump com resumo F112 na seção "By the numbers" |
| `docs/historico/f112_go_nogo_measurement.md` | Report | Este relatório (markdown) |
| PR #TBD | Code | Anchor no mesmo PR (toca `scripts/` + `README.md` + `docs/`) |

---

## 7. Conclusão

**F112 completado — NO-GO medido para ambos os alvos.**

- O padrão F91 se confirma: fontes com parede de login/JS/soft-404 **não entram** na `BLIND_HYDRATION_SOURCES`
- `arbeitsagentur` segue fora (já era assim; F91 documentou 74/74 mortas)
- `KPMG` (successfactors:jobs) confirma que o gap F85 era **dados no feed (teaser)**, mas a página de detalhe **também não entrega** no HTML estático (SPA)
- Próximos passos: nenhum — a hidratação cega permanece restrita às fontes comprovadamente curáveis (`absolventa`, `praktikum_info`)

---

*Medição realizada em 2026-10-24 06:xx UTC — read-only GET, UA `internship-finder-liveness/1.1`, timeout 10s, delay 0.5s entre requests.*