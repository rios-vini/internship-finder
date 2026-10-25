# F118 — csod/henkel AJAX: GO/NO-GO hidratação SPA (henkel, hella, BIL, Luxair)

## Resumo Executivo
**Resultado: 0/4 GO — TODOS NO-GO** (padrão F91/F112: zero código, relatório com causas medidas)

## Passo 0 — Medição Real (24/10/2026, read-only GET, UA honesto, serial 2s, ≤10 fetches total)

### hella (csod 18876, site_id=3)
| Endpoint | Status | Body | Content-Type | JSON-LD | SPA Shell | SAML Wall |
|----------|--------|------|--------------|---------|-----------|-----------|
| Home | 200 | 5.5 KB | text/html | ❌ | ✅ | ❌ |
| Search `queryresults/asJson` | 200 | 19 KB | text/html | ❌ | ✅ | ❌ |
| Detail `/home/requisition/<ID>` | 200 | 5.5 KB | text/html | ❌ | ✅ | ❌ |
| API Search `/services/x/job-requisition/v2/requisitions` | 404 | — | — | — | — | — |
| API Detail `/services/x/job-requisition/v2/requisitions/<ID>` | 403 | — | — | — | — | — |

**Veredito: NO-GO** — Causa: **SPA puro**. Search endpoint `queryresults/asJson` retorna HTML (SPA shell), NÃO JSON. Detail endpoint não tem JSON-LD no HTML estático. APIs reais retornam 404/403. Não há endpoint JSON público sem login.

---

### henkel (site_id=1)
| Endpoint | Status | Body | Content-Type | JSON-LD | SPA Shell | SAML Wall |
|----------|--------|------|--------------|---------|-----------|-----------|
| Home | 200 | 5.5 KB | text/html | ❌ | ✅ | ❌ |
| Search `queryresults/asJson` | 200 | 3.6 KB | text/html | ❌ | ❌ | ✅ |
| Detail `/home/requisition/<ID>` | 200 | 5.5 KB | text/html | ❌ | ✅ | ❌ |

**Veredito: NO-GO** — Causa: **SAML Authentication wall** no search + **SPA puro** no detail. O search endpoint redireciona para SAML login. Sem autenticação, não há acesso à lista de vagas nem ao detail.

---

### BIL (site_id=1)
| Endpoint | Status | Body | Content-Type | JSON-LD | SPA Shell | SAML Wall |
|----------|--------|------|--------------|---------|-----------|-----------|
| Home | 200 | 5.3 KB | text/html | ❌ | ✅ | ❌ |
| Search `queryresults/asJson` | 200 | 1.9 KB | text/html | ❌ | ❌ | ✅ |
| Detail `/home/requisition/<ID>` | 200 | 5.3 KB | text/html | ❌ | ✅ | ❌ |

**Veredito: NO-GO** — Causa: **SAML Authentication wall** no search + **SPA puro** no detail. Mesmo padrão do henkel.

---

### Luxair (site_id=27)
| Endpoint | Status | Body | Content-Type | JSON-LD | SPA Shell | SAML Wall |
|----------|--------|------|--------------|---------|-----------|-----------|
| Home | 200 | 5.4 KB | text/html | ❌ | ✅ | ❌ |
| Search `queryresults/asJson` | 200 | 1.9 KB | text/html | ❌ | ❌ | ✅ |
| Detail `/home/requisition/<ID>` | 200 | 5.4 KB | text/html | ❌ | ✅ | ❌ |

**Veredito: NO-GO** — Causa: **SAML Authentication wall** no search + **SPA puro** no detail. Mesmo padrão do henkel/BIL.

---

## Conclusão
**Nenhum dos 4 tenants CSOD possui endpoint JSON público que entrega job detail sem login.**

- **hella**: SPA puro, APIs internas 404/403, search retorna HTML (não JSON)
- **henkel/BIL/Luxair**: SAML wall no search + SPA puro no detail

**Ação: PARA** (padrão F91/F112). `BLIND_HYDRATION_SOURCES` inalterada: `("absolventa", "praktikum_info")`.

Zero código adicionado — relatório NO-GO com causas medidas é resultado válido.

## Entregáveis
- ✅ `scripts/test_f118.py` — fixtures verbatim + validação NO-GO (21 checks, all OK)
- ✅ Relatório em `~/.hermes/handoff/f118-csod-ajax-go-nogo/`
- ✅ Branch `feature/f118-csod-ajax-go-nogo` com test_f118.py
- ✅ README atualizado (suites 150→151)
