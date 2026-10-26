# Avature Provider Discovery — Guia Reutilizável (F125)

**Data:** 26/10/2026 | **Contexto:** Descoberta de 2 tenants Avature (Siemens Energy + TenneT) via caça manual. Ambos portais modernos com Algolia/InstantSearch (SPA pesada), mas **ambos expõem feed RSS funcional** em `/feed/` com `pubDate` + job URL estável.

---

## 1. Padrão Avature Identificado

| Atributo | Valor |
|----------|-------|
| **ATS family** | `avature` (novo em `discovery_rules.RULES`) |
| **Marker HTML** | `<meta name="avature.portal.id" content="..."/>`, `<meta name="avature.portal.name" content="..."/>` |
| **Arquitetura** | SPA com Algolia/InstantSearch (`listSpecId`, `searchIndexId` no JS) |
| **Endpoint confiável** | RSS feed em `{base}/{locale}/{path}/feed/?folderRecordsPerPage=N` ou `jobRecordsPerPage=N` |
| **Job URL format** | Varia por tenant — medir e registrar em `TENANT_JOB_URL_FORMATS` (F105) |
| **posted_at** | `pubDate` no RSS (RFC 2822) — converter para ISO 8601 no adapter |
| **external_id** | Final numérico da URL (`/FolderDetail/.../123456` ou `/JobDetail/.../123456`) |
| **Country filter** | Crítico para tenants multinacionais (TenneT: NL/DE) — via country-specific feeds ou location parsing |

---

## 2. Passo a Passo de Discovery (SEM Browser)

### 2.1 Confirmar Avature
```bash
curl -sL "https://jobs.exemplo.com" | grep -i "avature.portal"
# Procura: avature.portal.id, avature.portal.name, avature.wizard.registrars
```

### 2.2 Encontrar RSS Feed
1. Acesse a página de busca (ex.: `/en_US/jobs/SearchJobsGermany` ou `/en_US/careers/SearchJobs`)
2. Procure `<link rel="alternate" type="application/rss+xml" ...>` no `<head>`
3. Padrões comuns:
   - `/{locale}/jobs/SearchJobs{Country}/feed/?folderRecordsPerPage=20`
   - `/{locale}/careers/SearchJobs/feed/?jobRecordsPerPage=20`
   - `/{locale}/jobs/SearchJobs/feed/?jobRecordsPerPage=20`

### 2.3 Validar Feed
```bash
curl -sL "https://jobs.exemplo.com/en_US/jobs/SearchJobsGermany/feed/?folderRecordsPerPage=20" | head -30
# Deve retornar XML com <item><title>, <link>, <guid>, <pubDate>
```

### 2.4 Medir Job URL Format
Extraia 3-5 `<link>` do feed e identifique o padrão:
- Siemens Energy: `https://jobs.siemens-energy.com/jobs/FolderDetail/<slug>/<ID>/`
- TenneT: `https://careers.tennet.eu/careers/JobDetail/<slug>/<ID>/`

Registre em `discovery_rules.TENANT_JOB_URL_FORMATS` (F105).

### 2.5 Verificar Multinacional / Country Filter
- TenneT: feed único mistura NL + DE → filtrar por location parsing (`Germany`, `Deutschland`, `DE`) ou buscar feeds country-specific
- Siemens Energy: feeds country-specific (`SearchJobsGermany`, `SearchJobsUS`, etc.) → mais simples

---

## 3. Registry Entry (src/internship_finder/registry.py)

```python
RegistryEntry(
    name="Nome Canonico",           # consulta exata do --companies
    ats="avature",
    tenant="avature:https://jobs.exemplo.com",  # URL completa do portal (URL_SLUG_ATS)
    enabled=True,
)
```

**Notas:**
- `tenant` usa URL completa porque `avature ∈ URL_SLUG_ATS` (collector/ats_scraper.py)
- O scraper AvatureScraper aceita URL completa como slug
- `find_company` do upstream NÃO resolve domínios custom Avature → discovery manual obrigatório

---

## 4. Discovery Rule (src/internship_finder/discovery_rules.py)

Já adicionada em F125 — reutilize `rule_for("avature")`:

```python
"avature": DiscoveryRule(
    ats="avature",
    csv_columns=("name", "slug", "url"),
    slug_semantics="URL COMPLETA do portal Avature (dominio CUSTOM por tenant)...",
    canonical_endpoint="GET {base}/<locale>/<path>/feed/?folderRecordsPerPage=N (RSS)",
    jobs_signal="rss:<item> (title, link, guid, pubDate)",
    success=_SUCCESS,
    invalid=_BASELINE_INVALID + (Invalid.UNRESOLVABLE_URL,),
    sample_url="https://jobs.siemens-energy.com",
    resolvable=False,   # dominio custom: resolver -> None
    url_as_slug=True,   # input do scraper = URL completa
),
```

---

## 5. TenantJobUrlFormat (F105) — discovery_rules.py

```python
"exemplo": TenantJobUrlFormat(
    tenant="Nome Canonico",
    ats="avature",
    current=re.compile(r"https://jobs\.exemplo\.com/jobs/FolderDetail/[^/?#]+/\d+/?"),
    legacy=(),
    evidence="registro DD/MM/AAAA: medido via RSS feed (...); pubDate presente; IDs estáveis",
),
```

**Uso:** `job_url_format_status(url)` retorna `"current"` | `"legacy_dead"` | `None` — guard para não linkar URLs mortas.

---

## 6. Adapter / Scraper — Pré-processamento RSS

O `AtsJobAdapter` espera campos específicos. No scraper (ou no teste), pré-processe:

```python
def _prep_rss_item(item: dict) -> dict:
    out = dict(item)
    link = item.get("link", "")
    # external_id do final da URL
    m = re.search(r"/(\d+)/?$", link)
    if m:
        out["external_id"] = out["ats_id"] = out["job_id"] = m.group(1)
    # pubDate (RFC 2822) -> ISO 8601 para _parse_dt do adapter
    pub = item.get("pubDate") or item.get("pubdate")
    if pub:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub)
        iso = dt.isoformat().replace("+00:00", "Z")
        for k in ("posted_at","postedAt","date_posted","datePosted",
                  "publication_date","published_at","created_at","createdAt"):
            out[k] = iso
    return out
```

---

## 7. Checklist de Validação (Offline)

- [ ] Registry: entrada no SEED com `ats="avature"`, `tenant="avature:<URL>"`
- [ ] Discovery rule: `rule_for("avature")` retorna regra coerente
- [ ] Fixture RSS: salva em `fixtures/f125/<tenant>.xml` (verbatiam)
- [ ] Parse RSS: `title`, `link`, `guid`, `pubDate` presentes em ≥10 items
- [ ] Adapter: `external_id` extraído da URL, `posted_at` parseado do `pubDate`
- [ ] Dedup: mesmo item → mesmo ID; cross-tenant IDs diferentes
- [ ] F105: `job_url_format_status(url)` retorna `"current"` para URLs do feed
- [ ] Liveness F94: `pubDate` ausente → `posted_at=None` (flag, NÃO delete)
- [ ] URL_SLUG_ATS: `"avature"` em `collectors/ats_scraper.URL_SLUG_ATS`
- [ ] README: count empresas +1, ATS platforms +1

---

## 8. Próximos Avature Conhecidos (Candidatos)

| Empresa | Portal | Status |
|---------|--------|--------|
| Trendence | jobs.trendence.de? | Investigar |
| Deutsche Telekom (já eightfold) | — | — |
| BMW (já successfactors) | — | — |
| Outras big-corp DE | Verificar `avature.portal.id` no HTML | TODO |

---

## 9. Lições Aprendidas (Anti-Padrões)

1. **NÃO concluir "site morto" se HTML vier vazio** — Avature é SPA, o XHR/RSS existe (lição F3/RMK)
2. **NÃO inventar spec** — discovery_rules deriva de MEDIÇÃO (feed RSS real, job URLs reais)
3. **posted_at pode vir ausente** → liveness F94 + re-check; NUNCA excluir por stale (flag only)
4. **Multinacional = filtro DE crítico** — TenneT mistura NL/DE no mesmo feed
5. **RSS > JSON API** — feed RSS é estável, não requer browser, tem pubDate nativo
6. **External ID na URL** — Avature usa IDs numéricos estáveis no final da URL, não no feed

---

## 10. Referências Cruzadas

- `src/internship_finder/discovery_rules.py` — regra `avature`, `TENANT_JOB_URL_FORMATS`
- `src/internship_finder/registry.py` — SEED entries Siemens Energy, TenneT
- `src/internship_finder/collectors/ats_scraper.py` — `URL_SLUG_ATS` inclui `avature`
- `scripts/test_f125.py` — suite offline completa (fixtures + adapter + F105 + classify)
- `fixtures/f125/siemens_energy_de.xml`, `fixtures/f125/tennet.xml` — fixtures verbatim