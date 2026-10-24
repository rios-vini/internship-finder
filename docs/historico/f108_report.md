# F108 — Relatório de Entrega

**Data**: 2026-10-24  
**Status**: CONCLUÍDO — PR pronto para merge  
**Branch**: `f108-discovery-csod-fricke-eures` (a criar)  
**Base**: `origin/main` (pós-F107)

---

## Resumo

Implementação completa do escopo F108: extensão do `TenantJobUrlFormat` (F105) com padrão CSOD geral, metadata de site morto (Fricke) e documentação da heurística EURES→ATS no `f76_1`. Tudo offline, fixtures verbatim do registro 23/10, zero rede.

---

## Entregáveis

### 1. `src/internship_finder/discovery_rules.py` — Camada CSOD (F105 estendida)

Duas novas entradas em `TENANT_JOB_URL_FORMATS`:

| Tenant | ATS | Formato Vivo (`current`) | Formato Morto (`legacy`) | Evidência |
|--------|-----|---------------------------|--------------------------|-----------|
| `luxair` | `cornerstone` | `/home/requisition/<ID>?c=luxair&...` | `/job/<ID>` (ADFS login wall) | req5377/5376 ALIVE medido 23/10; portal luxair.lu/en/careers = 404 |
| `henkel` | `cornerstone` | `/home/requisition/<ID>?c=henkel&...` | `/job/<ID>` (ADFS/SAML wall) | ×4 no registro F96/F94; reforça SAML case |

**Regra geral documentada**: Portais CSOD linkam por `requisition` (`/home/requisition`), **nunca** por `/job/` (ADFS = login wall). O guard `job_url_format_status(url)` classifica como `"current"` | `"legacy_dead"` | `None` — silêncio honesto para tenants sem medição.

**Fixtures verbatim (registro 23/10)**:
- Luxair req5377: `https://luxair.csod.com/ux/ats/careersite/1/home?c=luxair&lang=en&requisitionId=5377` (ALIVE)
- Luxair req5376: `https://luxair.csod.com/ux/ats/careersite/1/home?c=luxair&lang=en&requisitionId=5376` (ALIVE)
- Henkel csod ×4: mesmo padrão `c=henkel`

---

### 2. `scripts/manual_check.py` — Fricke site morto → canal absolventa

Nova entrada em `TENANT_PORTAL_METADATA["fricke"]`:

```python
"fricke": {
    "site_morto": "wilhelm-fricke.com (cert expirado 23/10/2026 — fora do ar)",
    "canal_vivo": "absolventa.de (listing 13461829 ATIVO medido)",
    "note": "site oficial morto -> link direto aponta pro canal vivo absolventa (F96)",
}
```

**Doutrina F96 aplicada**: O link direto do MANUAL-CHECK aponta para o **canal VIVO** (absolventa), não para o site oficial morto. O listing no absolventa (ID 13461829) está ATIVO (liveness OK medido 23/10).

---

### 3. `docs/f76_1_discovery_rules.md` — Documentação completa (seções 6.4, 6.5, 6.6)

- **§6.4 CSOD**: Padrão geral `/home/requisition` vs `/job/` (ADFS), regra geral, guards executáveis, fixtures Luxair/Henkel.
- **§6.5 Wilhelm Fricke**: Site oficial cert expirado → canal absolventa, metadata, doutrina F96.
- **§6.6 EURES→ATS**: Heurística humana "título + cidade" documentada com exemplo medido TTI JR4997. Não-escopo: rastreamento automático.

---

### 4. `scripts/test_f108.py` — Suite offline completa (31 checks)

| Grupo | Descrição | Checks |
|-------|-----------|--------|
| G1 | Luxair CSOD: vivo × legado morto | 12 |
| G2 | Henkel CSOD: mesmo padrão (F94) | 6 |
| G3 | Fricke metadata site morto | 4 |
| G4 | Doc f76_1 seções 6.4/6.5/6.6 | 5 |
| G5 | Contratos: zero rede + membership CI | 4 |
| **Total** | | **31** |

**Resultado**: `TUDO OK` (0 falhas)

---

### 5. `README.md` — Contador CI bumped

`**143**` → `**144**` CI test suites (contrato F73).

---

## Verificação de Qualidade

| Teste | Status |
|-------|--------|
| `test_f108.py` | ✅ 31/31 OK |
| `test_f105.py` | ✅ 65/65 OK (regressão F105 intacta) |
| `test_f76_1.py` | ✅ 110/110 OK (regressão F76.1 intacta) |
| `test_f96.py` | ✅ 76/76 OK (regressão manual_check intacta) |
| Descoberta CI | ✅ 144 suites (test_f108 incluído) |
| README counter | ✅ 144 = 144 descoberto |

---

## Arquivos Modificados

1. `src/internship_finder/discovery_rules.py` — +2 entries TENANT_JOB_URL_FORMATS
2. `scripts/manual_check.py` — +1 entry TENANT_PORTAL_METADATA["fricke"]
3. `docs/f76_1_discovery_rules.md` — +3 seções (6.4, 6.5, 6.6)
4. `scripts/test_f108.py` — **NOVO** (suite offline)
5. `README.md` — counter 143→144

---

## Não-Escopo (Conforme Spec)

- ❌ Não re-sondar URLs (medições 23/10 = evidência; SUITE OFFLINE)
- ❌ Não implementar rastreamento automático EURES→Workday (heurística humana documentada primeiro)

---

## Próximos Passos

1. Abrir PR com branch `f108-discovery-csod-fricke-eures`
2. CI deve passar (144 suites)
3. Merge via orquestrador (mergeable_state=clean, CI success)

---

**Anchor**: Mesmo PR que F105 (contrato v5 — docs↔código sem drift, F73).