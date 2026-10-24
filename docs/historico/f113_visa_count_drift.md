# F113 — Visa-friendly count drift: dashboard 235 × export 237

## Resumo

**Problema:** O contador de vagas `visa_friendly` no dashboard (GitHub Pages) mostrava **235**, enquanto o JSON de trabalho (`eligible_jobs.json`) continha **237** vagas com `visa_friendly=true`. Drift de 2 vagas.

**Causa raiz:** O contador do rodapé (`n_vf`) era computado a partir do subconjunto `shown` (vagas exibidas na página), que sofre:
- Cap de 2 vagas por empresa (`apply_company_cap`)
- Remoção de dead links (404/410)
- Remoção de vagas inaplicáveis pós-hidratação

Isso fazia o contador **subcontar** as vagas visa_friendly reais presentes no JSON completo.

**Solução:** O contador agora lê **diretamente do JSON completo** (`jobs` parameter — a lista completa de elegíveis que já traz o campo `visa_friendly` preenchido pelo pipeline), ignorando qualquer filtro/corte de exibição. Uma fonte de verdade.

## Mudanças

### 1. `scripts/minimal_page.py` (linha ~2727)

**Antes:**
```python
n_vf = sum(1 for j in shown if _visa_friendly(
    j, entry_cache.get(str(j.get("id") or ""))))
```

**Depois:**
```python
# F113 — contador visa_friendly lê do JSON (fonte única de verdade):
# usa a lista COMPLETA de elegíveis (jobs), não o subconjunto exibido
# (shown), para bater com o eligible_jobs.json que já traz o campo
# visa_friendly preenchido pelo pipeline. Evita drift (ex.: 235 vs 237)
# causado por cap 2/empresa, dead links, etc.
n_vf = sum(1 for j in jobs if j.get("visa_friendly") is True)
```

### 2. `scripts/test_f113.py` (novo)

Dois testes de regressão:
- `test_f113_visa_friendly_count_matches_json`: Verifica que o rodapé do HTML contém a contagem exata do `eligible_jobs.json` real (237).
- `test_f113_contador_nao_usa_shown`: Teste sintético que garante que o contador ignora cap/empresa e lê do JSON completo.

## Validação

```bash
# Teste unitário
.venv/bin/python scripts/test_f113.py
# ✓ F113 OK: visa_friendly count = 237 (bate com JSON)
# ✓ F113 OK: contador ignora cap/empresa e lê do JSON completo

# Teste via pytest
.venv/bin/python -m pytest scripts/test_f113.py -xvs
# 2 passed

# Suíte relacionada (sem regressões)
.venv/bin/python -m pytest scripts/test_f43.py scripts/test_f6.py scripts/test_publish_pages.py -xvs
# All passed
```

## Verificação manual

```python
# Antes da correção: 235
# Depois da correção: 237 (bate com eligible_jobs.json)
```

O rodapé agora exibe corretamente:
- **EN:** "all 688 eligible jobs · **237** with 🛂 (employer with a stated visa policy)..."
- **PT:** "todas as 688 vagas elegíveis · **237** com 🛂 (empresa com política de visto)..."

## Impacto

- **Zero breaking changes:** Apenas corrige o contador para ser honesto (mesma família do F107 — display honesto).
- **Performance:** Negligível (um `sum` sobre a lista completa vs. subconjunto).
- **Contrato:** O JSON/CSV completos continuam sendo a base de dados; o dashboard agora reflete fielmente o que está neles.

## Checklist de entrega

- [x] Diagnóstico da causa raiz (comentado no código)
- [x] Alinhamento: contador lê do JSON (fonte única)
- [x] Guard de regressão: `test_f113.py` com fixture real
- [x] README: não requer alteração (não expõe números hardcoded)
- [x] Relatório: este documento
- [x] PR: pronto para abrir