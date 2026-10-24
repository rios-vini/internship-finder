#!/usr/bin/env python3
"""Testes da Fase F53 — interatividade vanilla na página full-list (offline).

Atrito de produto que a F53 fecha: no scan diário o dono re-lê vagas
velhas, não lembra o que já viu/aplicou e a busca sem resultados deixa
a página "morta" sem aviso. Tudo client-side, vanilla, inline, zero
estado no servidor — progressive enhancement: SEM JS a página renderiza
e funciona idêntica à F51 (contrato do item 6 da spec).

ÂMBITO (decisão documentada no relatório): TODA a interatividade vive no
regime FULL-LIST — o que o publish entrega (PUBLIC_TOP >= PAGE_TOP_FULL).
O regime top-N legado permanece BYTE A BYTE o da F51 (contratos F43/F51
preservados por construção; prova por A/B contra o SHA congelado).

Contratos testados:

- T1: split de regimes — toggles "mostrar já vistas"/"esconder
  aplicadas", CSS e JS F53 SÓ no full; legado sem NENHUM marcador F53.
- T2: data-factors (item 3) — top-3 do breakdown no <span> do score,
  no build (função pura: empate por chave, só ≠0, formatação compacta);
  score_key da seção decide QUAL breakdown (🧪/🇪🇺 explicam o próprio
  score exibido); top-N fica SEM custo por card.
- T3: data-ps (item 2) — status do tracker (view F41 do event log) vira
  atributo por card no full; status SEM ícone (new/interesting/review)
  não vira; legado não ganha o atributo.
- T4: item 6 — A/B byte a byte do legado contra o minimal_page.py
  PRÉ-F53 (SHA congelado, subprocesso, mesma fixture/carimbo); HTML
  estático do full SEM nenhum elemento da interatividade (botões,
  empty-state, voltar-ao-topo são criados por JS).
- T5: JS executado em node (padrão F5/F13/F43) com localStorage
  mockado: "já vi" persiste e dima/oculta, gêmeos entre seções
  sincronizam, "esconder aplicadas" respeita 'ignored', empty-state da
  busca, tooltip dos fatores, voltar-ao-topo (núcleo puro f53Top).
- T6: orçamento — chrome F53 medido (< 3,5KB), data-factors < 80 B/card
  em média, full continua <= cap proporcional, legado < 150KB, A/B de
  tamanho full (pós > pré, dentro do orçamento previsto).
- T7: caminho do publish (from_file com top=PAGE_TOP_FULL) entrega a
  interatividade sem flag nova.

Fixtures: SINTÉTICAS, campos mínimos — nenhum payload real, zero rede.
Uso:  .venv/bin/python scripts/test_f53.py   (ou bash scripts/test_f53.py)
"""

from __future__ import annotations

import hashlib
import html as _html
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

STAMP = "2026-10-18 01:20"  # carimbo fixo: renders A/B comparáveis
REPO = Path(__file__).resolve().parent.parent
# main pré-F53 (contém F51+F54.1+F47+F55; NUNCA 'main' móvel — mesma regra
# do _AB_BASELINE_SHA do test_f51: pós-merge o A/B não pode comparar F53
# com ela mesma). Atualizado no REBASE da wave (main moveu F47+F55 depois
# da abertura da branch; minimal_page.py IDÊNTICO entre e0d75c2 e 1b548c1
# — o byte-identity do legado é o mesmo, só a âncora se move p/ o pai
# direto, que também valida a pré-condição src/).
# F56 (18/10): src/ moveu de novo (rescore_hydrated_jobs em ranking.py) —
# mas pós-merge da F53 a âncora única não pode mais servir aos 3 papéis:
# a pré-condição src/ precisa do estado ATUAL (move por fase que toca
# src/), enquanto o render legado precisa do minimal_page.py PRÉ-F53
# (permanente — 1b548c1 é o último main sem as features F53). SPLIT:
# _AB_BASELINE_SHA = estado src/ (pré-condição; move com a fase);
# _AB_LEGACY_PAGE_SHA = minimal_page.py pré-F53 (render legado + medida
# do _JS_PROFILE; fixo em 1b548c1, que vive no main para sempre).
# F50 (18/10): src/ moveu de novo (enrichment/runner.py — reasoning_effort
# low no call-site, fix F34; geocoding.py — reparo Nominatim addressdetails
# + lazy attach; gates F1 intactos, flags default OFF). Padrão F56: a
# âncora da pré-condição src/ move para o head da fase que tocou src/; o
# render legado permanece congelado em _AB_LEGACY_PAGE_SHA (minimal_page.py
# intocado pela F50 — byte-identity do legado inalterado).
# F58 (18/10, retroativo — detectado na F59): a F58 tocou src/
# (collectors/ats_scraper.py TENANT_ATS_OVERRIDES + health.py
# SERIES_STALE_HOURS + registry.py re-point) e NÃO moveu a âncora; o CI
# dela passou porque 4f2815c (head de branch pré-squash) não resolve no
# checkout raso do runner ([SKIP]) — mas na VPS, com história completa,
# o pós-merge do main ficou FALHANDO neste check (diff 4f2815c..main
# = os 3 arquivos da F58). Landmine da F58, não da fase atual.
# F59 (19/10): src/ moveu de novo (registry.py comentário BCG + health.py
# docstring _detect_zero_return — só documentação de condição
# conhecida, zero mudança de comportamento). Padrão F56: âncora move
# para o head da fase que tocou src/ (69585ce) — o que também cura o
# landmine da F58 (a âncora agora carrega o estado src/ pós-F58). O
# render legado permanece congelado em _AB_LEGACY_PAGE_SHA (1b548c1).
# F59.1 (19/10): src/ moveu de novo (upstream_patches/ NOVO — parser
# BambooHR do PR #300 vendado, auto-removível; collectors/ats_scraper.py
# factory no fetch_worker; registry.py/health.py comentários F59.1).
# Padrão F56/F50/F59: âncora move para o head da fase que tocou src/
# (7e4f708). O render legado permanece congelado em _AB_LEGACY_PAGE_SHA
# (1b548c1 — minimal_page.py intocado pela F59.1).
# F60 (19/10): src/ moveu de novo (app_intel.py — 'gut' BARE no
# qualificador de intensidade + verbo 2ª pessoa 'sprichst' +
# 'deutschsprachig' advérbio/janela reversa + eixo francês
# french_level, SINAL nunca exclusão). Padrão F56/F59: âncora move
# para o commit da fase que tocou src/ (406c8cd = commit F60 do
# app_intel.py; o commit seguinte só edita TESTES — src/ idêntico, o
# que mantém o diff vazio na branch, no CI raso ([SKIP]) e no main
# pós-squash). O render legado: a F60 é a PRIMEIRA fase pós-F53 que
# ADICIONA bytes ao legado pt (data-fr por card + item de legenda 🇫🇷
# + badge FR + CSS .fr quando há francês qualificado) — o byte a byte
# pré-F53 passa a valer MÓDULO o delta F60 determinístico (strip
# cirúrgico no ``_strip_f60``; qualquer OUTRA divergência de byte
# continua FAIL).
# F61 (19/10): src/ moveu de novo (filters.py — detector
# requires_existing_permit_for_non_eu wired em
# applicability_exclusion_reason sob visa_blocked; §16e primeira
# entrada, MAHLE verbatim). Padrão F56/F59/F60: âncora move para o
# commit da fase que tocou src/ (fc709b0 = commit F61 do filters.py;
# o commit seguinte só edita TESTES — src/ idêntico, o que mantém o
# diff vazio na branch, no CI raso ([SKIP]) e no main pós-squash).
# O render legado: a F61 NÃO toca minimal_page.py — o byte a byte
# (módulo o strip F60) segue idêntico.
# F63 (19/10): src/ moveu de novo (opportunity_intel.py — heurística
# anual×mensal display-only: _apply_salary_plausibility com
# provenance "anual convertido p/ mensal" / "unidade não confirmada"
# para bounds > €6.000; fix rsplit do period group "per year" colado;
# _YEARLY_LABEL_RE += "Jährliche Vergütung"). Padrão F56/F59/F60/F61:
# âncora move para o commit da fase que tocou src/ (cbcbac1 = commit
# F63 1/2, SÓ src/; o commit 2/2 edita testes/scripts/ci — src/
# idêntico). O render legado: a F63 altera o minimal_page ATUAL
# (_fmt_salary consome provenance) mas as fixtures da F53 NÃO citam
# salário implausível — suíte local verde sem strip adicional (o
# byte a byte módulo F60 segue idêntico).
# F65.1 (19/10): F50.1 (#164) tocou src/ (enrichment/llm.py — MODEL
# flash→normal + env override INTERNSHIP_FINDER_ENRICHMENT_MODEL) e NÃO
# moveu a âncora — landmine pós-merge da MESMA classe do F58 (diff
# cbcbac1..main = llm.py; main quebrado 91/92, CI imune por [SKIP]
# no checkout raso; achado da F65, fix roteado no card F65.1). Padrão
# F56/F59/F60/F61/F63: âncora move para o estado src/ da fase que
# tocou src/ — F50.1 = ab2c230. Confirmado o origin/main do dia:
# f604fe3 (F65 #165 mergeou entretanto, SÓ scripts/ci.yml — src/
# byte-idêntico a ab2c230, diff vazio conferido), então a âncora
# apoia no main do dia = base da branch, que carrega exatamente o
# estado src/ pós-F50.1. Decisão consciente (escopo do card): MOVER
# em vez de excluir enrichment/ do escopo do diff — desde o split
# F56 esta âncora serve SÓ à pré-condição src/ (o render legado lê
# _AB_LEGACY_PAGE_SHA congelado), e excluir o pacote cegaria o
# check p/ qualquer fase futura em enrichment/. O A/B pré-F53
# (byte-identity + orçamento) segue lendo 1b548c1 — inalterado.
# F66 (19/10): src/ moveu de novo (cross_source_dedup.py — alias de
# identidade tenant-label→empresa real: load_company_aliases +
# canonical_company consumidos pelo _pair_ok do estágio cross-fonte
# F48; mapa versionado config/dedup_company_aliases.json, match exato
# casefold antes da tokenização; dedup/ranking/display seguem pela
# string ORIGINAL). Padrão F56/F59/F60/F61/F63: âncora move para o
# commit da fase que tocou src/ (5ea23e0 = commit F66 1/2; o commit
# 2/2 edita SÓ este teste — src/ idêntico, o que mantém o diff vazio
# na branch, no CI raso ([SKIP]) e no main pós-squash). O render
# legado: a F66 NÃO toca minimal_page.py — o byte a byte (módulo o
# strip F60) segue idêntico.
# F73 (19/10): src/ moveu de novo (doc-sync D1 — dataset_source.py +
# ranking.py docstrings contagem 101→127; janela do upstream ~05h→
# ~14:30 UTC em dataset_source.py/direct_fetch.py/ats_scraper.py; só
# documentação, zero mudança de comportamento). Padrão F56/F59/F66:
# âncora move para o commit da fase que tocou src/ (5794d27 = commit
# F73 1/2; o commit 2/2 edita SÓ este teste — src/ idêntico, o diff
# segue vazio na branch, no CI raso ([SKIP]) e no main pós-squash).
# O render legado segue congelado em _AB_LEGACY_PAGE_SHA (a F73 NÃO
# toca minimal_page.py).
# F75 (20/10, orquestrador no rebase de verificação): src/ moveu de novo
# (metrics_retention.py NOVO em src/internship_finder/ — a fase adicionou
# módulo; o worker moveu a âncora do test_f45, mas a pré-condição src/ é
# do test_f53) — âncora move para 24a1281 (head da fase que tocou src/;
# padrão F56/F58-retroativo/F81: commit 2/2 edita SÓ este teste, diff
# src/ segue vazio na branch, [SKIP] no CI raso, clone-da-produção
# retém o SHA pós-squash).
# F76.1 (20/10, orquestrador na verificação — 4ª ocorrência da classe
# F58, guard VIVO pegando LOUD como projetado): discovery_rules.py
# NOVO em src/ sem mover a âncora. Move: →ac19014 (head da fase).
# F72.1 (20/10, orquestrador na verificação — padrão F58 pela 3ª vez,
# agora com o guard VIVO e pegando): a F72.1 tocou src/
# (collectors/ats_scraper.py override + registry.py re-point AkzoNobel)
# sem mover a âncora — o check falhou LOUD na verificação (como
# deve). Move: →98e1e27 (head da fase). A lição está consolidada
# nos cards F75/F80/F70; verificação da próxima fase src/ confere
# cat-file + pré-condição REAL (não [SKIP]).
# F80 (20/10, orquestrador na verificação — LANDMINE descoberto e
# curado): a F80 tocou src/ (dataset_source.py + cli.py) sem mover a
# âncora (classe F58) E o guard estava CEGO desde a F75: a âncora
# 24a1281 (commit de branch da F75) NUNCA existiu na store da
# produção (o trabalho da F75 correu em clone separado; produção
# só pull origin main) → "bad revision" → [SKIP] silencioso em
# TODO contexto com história. LIÇÃO ESTRUTURAL: âncora em commit
# de branch é retida pela produção SÓ SE o branch foi fetchado
# lá enquanto vivo; trabalho em clone separado órfã a âncora.
# Move: 24a1281→d97209e (head da F80, fetchado na verificação;
# padrão F56/F81). Convencionalizar: fase que toca src/ move a
# âncora no MESMO PR; verificação confere resolução do SHA na
# produção (cat-file), não só exit-code do teste.
# F81 (20/10): src/ moveu de novo (doc do tenant compartilhado
# phenom:nan em registry.py — docstring do módulo + comentários por
# entrada DHL/Allianz/Merck/Kuehne+Nagel + docstring do
# tenant_consistency_report; fase SEM purge, SÓ documentação, zero
# mudança de comportamento/coleta). Padrão F56/F59/F66/F73: âncora
# move para o commit da fase que tocou src/ (e2371ac = commit F81 1/2;
# o commit 2/2 edita SÓ este teste — src/ idêntico, o diff segue vazio
# na branch, no CI raso ([SKIP]) e no main pós-squash). O render
# legado segue congelado em _AB_LEGACY_PAGE_SHA (a F81 NÃO toca
# minimal_page.py).
# F70 (20/10): idem F80 — src/ moveu (dataset_seen.py novo + wiring em
# dataset_source/cli/sqlite_backup); âncora -> commit F70 1/2
# (016da00), o 2/2 edita SÓ este teste. A F70 NÃO toca minimal_page.py
# (render legado segue congelado).
# F76 (20/10): idem F80/F70 — src/ moveu (dataset_fetch.py novo + wiring
# em dataset_source); âncora -> commit F76 1/2 (8bbe9d8, REBASE pós-F72.1
# 312b34d — o 1/2 original fcf4112 foi refeito), o 2/2 edita
# SÓ este teste. A F76 NÃO toca minimal_page.py (render legado segue
# congelado em _AB_LEGACY_PAGE_SHA).
# F85 (20/10): idem F80/F70/F76 — src/ moveu (app_intel.py — corpus de
# idioma v2: A1/A2 básico grudado à própria menção NÃO exclui, native/
# bilingual DE no glued F18, eixo FR courant/bilingue pós-nominal +
# soft-anexado _FRENCH_SOFT_AFTER_RE); âncora -> commit F85 1/2
# (c549948), o 2/2 edita SÓ testes/README. A F85 NÃO toca
# minimal_page.py (render legado segue congelado em _AB_LEGACY_PAGE_SHA;
# A/B byte a byte conferido na suíte local — fixtures sem courant/
# bilingual/A1-A2, zero divergência de badge).
# F86 (20/10): src/ moveu de novo (filters.py + app_intel.py — job_type_of
# + requires_experience + motivos job_type_non_internship/
# experience_required na cascata e na tupla F37.3; detector
# "não-é-estágio-pra-graduando" das 6 vagas do registro de recusas 20/10;
# job_type_ambiguous_title no app_intel). Padrão F56/F59/F60/F61/F63:
# âncora move para o commit da fase que tocou src/ (1b0e025 = commit F86
# 1/2 — filters.py + app_intel.py, SÓ src/; o commit 2/2 edita
# testes/scripts/README — src/ idêntico, o diff segue vazio na branch, no
# CI raso ([SKIP]) e no main pós-squash). O render legado: a F86 toca
# minimal_page.py (badge ⚠️ de tipo ambíguo + item da legenda ⏳/⚠️) — mas
# o badge só acende em TÍTULO DUPLO Werkstudent+Praktikum e as fixtures
# da F53 não têm título duplo; o item da legenda ⏳/⚠️ mudou de texto →
# o strip F86 cobre o delta determinístico (ver _strip_f86).
# F88 (21/10): src/ moveu de novo (registry.py +18 entradas da onda F88
# top-up de frescor, 127->145; docstrings de contagem do dataset_source/
# ranking seguem). Nenhuma mudança de render: o badge/legenda da página
# não dependem do SEED — o byte a byte da F53 segue válido módulo os
# strips F60/F83/F86 (fixtures sem empresa da onda).

# F92 (21/10): src/ moveu de novo (cli.py — estágio de normalização de
# ingestão F92 entre select_eligible e dedup; dedup.py — normalize_location
# trata o sentinela '—' como ausente; company_aliases.py NOVO — loader
# fail-closed + aplicação dos aliases canônicos e guards de location).
# Nenhuma mudança de render: o estágio reescreve company/location no DADO
# (pós-filter, pré-dedup) — as fixtures da F53 não usam labels do mapa
# F92 nem locations com prefixo postal, o byte a byte segue válido
# módulo os strips F60/F83/F86. Padrão F56/F88: âncora move para o head
# da fase que tocou src/.
# F99 (22/10): src/ moveu de novo (filters.py — 3 detectores novos de
# hard-eligibility [native_language, duration_conflict, recent_graduate]
# + extensões de eu_citizenship_required/nl_enrolment_required/
# requires_master + normalização de apóstrofo tipográfico U+2019 na
# cadeia; ptbr.py — APPLICABILITY_REASON_LABELS display-only). Nenhuma
# mudança de render: minimal_page.py intocado, os motivos são chaves
# técnicas de metrics/JSON — o byte a byte da F53 segue válido módulo os
# strips F60/F83/F86. Padrão F56/F88/F92: âncora move para o commit da
# fase que tocou src/ (667925e = commit F99 1/2 — SÓ src/; o commit 2/2
# edita testes/README — src/ idêntico, o diff segue vazio na branch, no
# CI raso ([SKIP]) e no main pós-squash).
# F100 (22/10): src/ moveu de novo (registry.py — onda F100 de 2 entries
# Issgovernance/JACOBS DOUWE EGBERTS + header 147; dataset_source.py e
# ranking.py — docstrings de contagem 145→147, parseados pelo test_f73).
# Nenhuma mudança de render/pipeline de ranking: a onda só acrescenta
# entradas de coleta ao SEED e bumpa docstrings — as fixtures da F53 não
# dependem do SEED, o byte a byte segue válido módulo os strips. Lição F58
# aplicada: âncora movida NO commit da fase (head pré-squash 355ca62).
# F104 (23/10): src/ moveu de novo (countries.py — lógica core do sanity
# cidade→país [loader fail-closed + check_city_country_mismatch];
# cli.py — flag country_mismatch pós select_eligible + métrica no JSONL).
# Port do resgate F104 (branch rescue + stash^3 → PR; a F104 original foi
# executada direto na produção sem commit). Nenhuma mudança de render do
# legado: o badge ⚠ do country_mismatch só acrescenta bytes quando o job tem
# country_mismatch=True — fixture da F53 não tem, byte a byte segue válido
# módulo os strips F60/F83/F86. Lição F58/F103 aplicada: âncora movida NO
# ciclo da fase (5b09ca2b = commit da fase, SÓ src/+scripts+README; o
# commit seguinte edita testes — src/ idêntico, o diff segue vazio na
# branch, no CI raso ([SKIP]) e no main pós-squash).
# F105 (23/10): src/ moveu de novo (discovery_rules.py — camada
# TENANT_JOB_URL_FORMATS/job_url_format_status p/ o formato de URL de
# vaga do Vetter, guard do legado morto; zero mudança de render — as
# fixtures da F53 não usam discovery_rules, o byte a byte segue válido
# módulo os strips). Padrão F56/F88/F100/F104: âncora move para o commit
# da fase que tocou src/ (5b6e85e = commit da fase, rebased sobre o main
# pós-F104 #205); o commit da âncora não toca src/ — o diff da
# pré-condição segue vazio na branch, no CI raso ([SKIP]) e no main
# pós-squash.
# F106 (23/10): src/ moveu de novo (filters.py — detector
# requires_de_enrolment + motivo de_enrolment_required na cadeia F37.3;
# ptbr.py — legenda 🇩🇪 da classe nova; funnel_report.py — rótulo no
# ✂ do digest; zero mudança de render — as fixtures da F53 não tocam
# matrícula local, o byte a byte segue válido módulo os strips). Padrão
# F56/F88/F100/F104/F105: âncora move para o commit da fase que tocou
# src/ (7d9d6da = commit da fase, SÓ src/+scripts+README; o commit
# seguinte edita testes — src/ idêntico, o diff segue vazio na branch,
# no CI raso ([SKIP]) e no main pós-squash).
_AB_BASELINE_SHA = "40a0db5fdb3755ab8d7efb72ec980517037621a3"
_AB_LEGACY_PAGE_SHA = "1b548c1"

# F60 — adições determinísticas da fase ao render (todas as línguas):
# 1. ``data-fr="..."`` por card (sinal de francês; NUNCA consumido por
#    filtro JS); 2. badge ``<span class="fr">…🇫🇷…</span>`` quando a
#    menção é qualificada (required/preferred); 3. item da legenda
#    única (dt/dd) explicando o sinal. O strip remove EXATAMENTE essas
#    três peças para os A/B byte a byte pré-F53/pré-F46 continuarem
#    verificando regressão de TODO o resto.
_F60_ATTR_RE = re.compile(r' data-fr="[^"]*"')
_F60_BADGE_HTML = ' <span class="fr"><span aria-hidden="true">🇫🇷</span></span>'
_F60_LEGEND_RE = re.compile(
    r'<dt><span aria-hidden="true">🇫🇷</span>.*?</dt><dd>.*?</dd>', re.DOTALL)
# CSS do badge FR (light + dark) — parte do delta F60 no <style>.
_F60_CSS_RE = re.compile(r'\.fr\{[^}]*\}\n')


def _strip_f60(html: str) -> str:
    """Remove as adições F60 do render (A/B byte a byte módulo F60)."""
    out = _F60_ATTR_RE.sub("", html)
    out = out.replace(_F60_BADGE_HTML, "")
    out = _F60_LEGEND_RE.sub("", out)
    return _F60_CSS_RE.sub("", out)


# F83 — sufixo de ocultas da linha do stamp (p_line), anexado quando
# total_eligible > len(shown) — o caso da fixture T4 (24 jobs/8
# empresas: cap 2/empresa do legado esconde 8). Mesma mecânica da F60
# (segunda fase pós-F53 que adiciona bytes ao legado pt): o byte a
# byte pré-F53 vale MÓDULO esse delta (strip cirúrgico); qualquer
# OUTRA divergência de byte continua FAIL.
_F83_HIDDEN_RE = re.compile(r" · \d+ ocultas? pelos filtros")


def _strip_f83(html: str) -> str:
    """Remove o delta F83 (sufixo de ocultas da p_line) — A/B módulo F83."""
    return _F83_HIDDEN_RE.sub("", html)


# F86 — item da legenda ⏳/⚠️ ganhou o terceiro sinal ("tipo ambíguo
# Werkstudent/Praktikum (F86 — decidir na vaga)"); o badge ⚠️ em si só
# acende em TÍTULO DUPLO (nenhuma fixture da F53 tem) — o delta do legado
# é SÓ o texto da legenda pt/en. Strip: novo -> antigo (a pré-F53 não
# tinha o terceiro sinal); qualquer OUTRA divergência de byte FAIL.
_F86_LEGEND_NEW = (
    "sinais informativos do §16e: duração citada acima do teto de 6 meses"
    " / anúncio exige matrícula ativa em universidade alemã / tipo ambíguo"
    " Werkstudent/Praktikum (F86 — decidir na vaga)")
_F86_LEGEND_OLD = (
    "sinais informativos do §16e: duração citada acima do teto de 6 meses"
    " / anúncio exige matrícula ativa em universidade alemã")
_F86_LEGEND_NEW_EN = (
    "informational §16e signals: stated duration above the 6-month cap /"
    " posting requires active enrollment at a German university /"
    " ambiguous Werkstudent/Praktikum type (F86 — decide on the posting)")
_F86_LEGEND_OLD_EN = (
    "informational §16e signals: stated duration above the 6-month cap /"
    " posting requires active enrollment at a German university")


def _strip_f86(html: str) -> str:
    """Remove o delta F86 (texto da legenda ⏳/⚠️) — A/B módulo F86."""
    return (html.replace(_F86_LEGEND_NEW, _F86_LEGEND_OLD)
                .replace(_F86_LEGEND_NEW_EN, _F86_LEGEND_OLD_EN))


# F95 — delta de render da fase (data-nl + badge 🇳🇱 + item 🇳🇱 da legenda;
# os badges 🔒/🤝/🎓/⚠ TOO_EARLY não acendem nas fixtures sintéticas —
# sem sinais F95 no texto). Strip cirúrgico, padrão _strip_f60.
_F95_NL_ATTR_RE = re.compile(r' data-nl="[^"]*"')
_F95_NL_BADGE = ' <span class="nl"><span aria-hidden="true">🇳🇱</span></span>'
_F95_NL_LEGEND_RE = re.compile(
    r'<dt><span aria-hidden="true">🇳🇱</span> holandês \(sinal\)</dt>'
    r"<dd>.*?</dd>", re.DOTALL)


def _strip_f95(html: str) -> str:
    """Remove o delta F95 de render (F95 não toca o legado pré-F53 além
    desses bytes determinísticos; qualquer OUTRO byte divergente FAIL)."""
    html = _F95_NL_ATTR_RE.sub("", html)
    html = html.replace(_F95_NL_BADGE, "")
    return _F95_NL_LEGEND_RE.sub("", html)


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Fixture sintética — breakdowns variados exercitam os casos da função
# pura (top-3, empate por chave, todos-zero, ausente, só-negativo).
# ---------------------------------------------------------------------------

N_JOBS = 24
N_COMPANIES = 8  # cap 2/empresa do legado morde (24/8 = 3 por empresa)

_BREAKDOWN = {
    "area": 2.0, "skills": 0.75, "language": 1.5, "type": 1.0,
    "location": 0.5, "penalties": -0.25, "registry": 1.0, "decay": -0.13,
}
_MAT_BREAKDOWN = {"area": 3.0, "skills": 1.0, "language": 1.5,
                  "penalties": 0.0, "decay": -0.2}
_EU_BREAKDOWN = {"area": 1.0, "language": 2.0, "location": 1.5}


def make_jobs(n: int = N_JOBS, n_companies: int = N_COMPANIES) -> list[dict]:
    jobs = []
    for i in range(n):
        iso = "nl" if i % 6 == 5 else "de"
        job = {
            "id": f"fx|f53:{i}",
            "title": f"Praktikum Supply Chain Beschaffung {i} (m/w/d)",
            "company": f"Firma {i % n_companies} GmbH",
            "location": f"Stadt {i}, {iso.upper()}",
            "country_iso": iso,
            "employment_type": "FULL_TIME",
            "url": f"https://jobs.example.com/f53/{i}",
            "description": "Beschaffung und supplier management. " * 8,
            "score": round(50.0 - i * 0.5, 2),
            "score_breakdown": dict(_BREAKDOWN),
        }
        if i == 7:
            job["score_breakdown"] = {k: 0.0 for k in _BREAKDOWN}
        if i == 8:
            del job["score_breakdown"]  # snapshot antigo: campo ausente
        if i == 9:
            job["score_breakdown"] = {"penalties": -0.5}
        if i % 4 == 0:
            job["materials_score"] = round(40.0 - i * 0.25, 2)
            job["materials_breakdown"] = dict(_MAT_BREAKDOWN)
        if iso == "nl":
            job["eu_score"] = round(30.0 - i * 0.1, 2)
            job["eu_breakdown"] = dict(_EU_BREAKDOWN)
        jobs.append(job)
    return jobs


def make_tracker(path: Path, rows: list[tuple[str, str]]) -> Path:
    """Banco job_status mínimo (mesmas colunas lidas pelo
    personal_status_map; a view F41 do event log mantém essa tabela)."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS job_status ("
        "job_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT)")
    con.executemany(
        "INSERT INTO job_status (job_id, status, updated_at) "
        "VALUES (?, ?, '2026-10-18T00:00:00Z')", rows)
    con.commit()
    con.close()
    return path


def render_full(jobs: list[dict], **kw) -> str:
    # F46: default do render virou EN (decisão do dono 15/10); esta suíte
    # valida o chrome/bytes da fase — force lang="pt" (contrato (b) F46).
    return mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        full_list=True, profile_maps=mp._profile_maps(jobs),
        lang="pt", **kw)


def render_legacy(jobs: list[dict], **kw) -> str:
    return mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        top=mp.PAGE_TOP, lang="pt", **kw)


def card_block(page: str, jid: str) -> str:
    """O <li> que carrega o data-jid dado (lista única OU seção)."""
    needle = f'data-jid="{esc(jid)}"'
    idx = page.find(needle)
    if idx == -1:
        return ""
    start = page.rfind("<li", 0, idx)
    end = page.find("<li", idx)
    if end == -1:
        end = len(page)
    return page[start:end]


def strip_scripts(page: str) -> str:
    return re.sub(r"<script>.*?</script>", "", page, flags=re.S)


# ---------------------------------------------------------------------------
# T1 — split de regimes: interatividade SÓ no full
# ---------------------------------------------------------------------------

_F53_MARKERS = (
    'id="f-seen"', 'id="f-app"', "mostrar já vistas", "esconder aplicadas",
    "data-factors=", "if53seen:", "seenb", "f53Top",
    "localStorage", "nenhuma vaga corresponde",
)
# data-ps tem check PRÓPRIO no T3 (requer tracker com status; sem tracker
# o atributo legitimamente não existe em nenhum card).


def test_regime_split() -> None:
    section("T1: toggles/CSS/JS F53 no full; legado sem NENHUM marcador")
    jobs = make_jobs()
    full = render_full(jobs)
    legacy = render_legacy(jobs)
    for m in _F53_MARKERS:
        check(f"full contém {m!r}", m in full)
    for m in _F53_MARKERS:
        check(f"legado SEM o marcador {m!r}", m not in legacy,
             "regime top-N byte a byte o da F51")
    check("full: CSS do data-seen (opacidade reduzida) presente",
          'li.c[data-seen="1"]{opacity:.45}' in full)
    check("legado: CSS F53 ausente", "opacity:.45}" not in legacy)
    check("full: botão voltar-ao-topo estilizado (#totop) no CSS",
          "#totop{position:fixed" in full)
    check("legado: sem #totop", "#totop" not in legacy)


# ---------------------------------------------------------------------------
# T2 — data-factors (item 3): build puro + custo ZERO no top-N
# ---------------------------------------------------------------------------

def test_factors_build() -> None:
    section("T2: data-factors — top-3 do breakdown no elemento do score")
    attr = mp._score_factors_attr({"score_breakdown": dict(_BREAKDOWN)})
    check("função pura: top-3 por valor (empate por chave asc)",
          attr == ' data-factors="área +2 · idioma +1.5 · interesse +1"',
          attr)
    check("breakdown ausente -> '' (attr omitido)",
          mp._score_factors_attr({}) == ""
          and mp._score_factors_attr({"score_breakdown": {}}) == "")
    check("todos-zero -> '' (nada a explicar)",
          mp._score_factors_attr({"score_breakdown": {"area": 0.0}}) == "")
    check("só-negativo aparece com sinal",
          mp._score_factors_attr({"score_breakdown": {"penalties": -0.5}})
          == ' data-factors="penal -0.5"')
    check("score_key mapeia o breakdown da SEÇÃO (materials)",
          mp._score_factors_attr(
              {"materials_breakdown": dict(_MAT_BREAKDOWN)},
              "materials_score")
          == ' data-factors="área +3 · idioma +1.5 · skills +1"')
    check("score_key mapeia o breakdown da SEÇÃO (eu)",
          mp._score_factors_attr(
              {"eu_breakdown": dict(_EU_BREAKDOWN)}, "eu_score")
          == ' data-factors="idioma +2 · local +1.5 · área +1"')

    jobs = make_jobs()
    full = render_full(jobs, materials=[j for j in jobs
                                        if "materials_score" in j][:3],
                       eu=[j for j in jobs if "eu_score" in j][:3])
    main_block = full.split('<ol id="list">')[1].split("</ol>")[0]
    # job 0 tem breakdown business E materials: na lista única os fatores
    # são do business; na seção 🧪, do materials (o score exibido muda).
    list_card = card_block(main_block, jobs[0]["id"])
    check("lista única: fatores do BUSINESS no span do score",
          'data-factors="área +2 · idioma +1.5 · interesse +1"'
          in list_card, list_card[:120])
    mat_block = full.split("🧪 Materials Engineering — ")[1].split(
        "🇪🇺 Fora da Alemanha — ")[0]
    mat_card = card_block(mat_block, jobs[0]["id"])
    check("seção 🧪: fatores do MATERIALS (o score da coluna)",
          'data-factors="área +3 · idioma +1.5 · skills +1"' in mat_card,
          mat_card[:120])
    zero_card = card_block(main_block, jobs[7]["id"])
    check("todos-zero: card SEM data-factors (custo zero)",
          "data-factors" not in zero_card)
    missing_card = card_block(main_block, jobs[8]["id"])
    check("breakdown ausente: card SEM data-factors",
          "data-factors" not in missing_card)
    neg_card = card_block(main_block, jobs[9]["id"])
    check("só-negativo: attr presente com o fator negativo",
          'data-factors="penal -0.5"' in neg_card)

    # o attr vive NO <span> do score (spec: "no elemento do score")
    spans = re.findall(r'<span class="s" data-factors="[^"]*">',
                       main_block)
    check("data-factors no <span class=s> (elemento do score)",
          len(spans) == N_JOBS - 2, f"{len(spans)} spans com fatores "
          f"(24 − 2: todos-zero + breakdown ausente; o só-negativo TEM)")

    legacy = render_legacy(jobs)
    check("top-N: ZERO data-factors (sem custo por card)",
          "data-factors" not in legacy)


# ---------------------------------------------------------------------------
# T3 — data-ps (item 2): estado do tracker/view F41 no card
# ---------------------------------------------------------------------------

def test_application_state() -> None:
    section("T3: data-ps — status do tracker (view F41) por card")
    jobs = make_jobs()
    with tempfile.TemporaryDirectory() as td:
        db = make_tracker(
            Path(td) / "tracker.db",
            [(jobs[0]["id"], "applied"), (jobs[1]["id"], "interview"),
             (jobs[2]["id"], "rejected"), (jobs[3]["id"], "ignored"),
             (jobs[4]["id"], "review"), (jobs[5]["id"], "withdrawn")])
        full = render_full(jobs, tracker_db=db)
        legacy = render_legacy(jobs, tracker_db=db)
        main_block = full.split('<ol id="list">')[1].split("</ol>")[0]
        for i, status in ((0, "applied"), (1, "interview"),
                          (2, "rejected"), (3, "ignored"),
                          (5, "withdrawn")):
            blk = card_block(main_block, jobs[i]["id"])
            check(f"full: data-ps={status!r} no card de {jobs[i]['id']}",
                  f'data-ps="{status}"' in blk)
        check("full: status SEM ícone (review) não vira data-ps",
              "data-ps=" not in card_block(main_block, jobs[4]["id"]))
        check("full: vaga fora do tracker sem data-ps",
              "data-ps=" not in card_block(main_block, jobs[6]["id"]))
        check("full: badge ✅ coexiste com o data-ps (contrato F14/F41)",
              "✅" in card_block(main_block, jobs[0]["id"]))
        check("legado: NENHUM data-ps (byte a byte pré-F53)",
              "data-ps=" not in legacy)


# ---------------------------------------------------------------------------
# T4 — item 6: sem JS a página é a da F51; legado byte a byte (A/B)
# ---------------------------------------------------------------------------

def _baseline_source() -> str | None:
    """Fonte do minimal_page.py PRÉ-F53 (SHA congelado) — lida 1×.

    F56: lê de ``_AB_LEGACY_PAGE_SHA`` (página pré-F53, permanente) e não
    mais de ``_AB_BASELINE_SHA`` (que virou a âncora do estado src/ da
    pré-condição e, pós-merge da F53, já carrega as features F53).
    """
    try:
        return subprocess.run(
            ["git", "show", f"{_AB_LEGACY_PAGE_SHA}:scripts/minimal_page.py"],
            capture_output=True, text=True, cwd=str(REPO), check=True,
        ).stdout
    except Exception:  # noqa: BLE001
        return None


def _baseline_const(name: str) -> str | None:
    """Valor de uma constante-triple-quoted do baseline (p/ medir a
    extensão do _JS_PROFILE — parte do chrome F53)."""
    src = _baseline_source()
    if src is None:
        return None
    m = re.search(rf'^{name} = """(.*?)"""', src, re.S | re.M)
    return m.group(1) if m else None


def _baseline_render(jobs: list[dict], *, full: bool):
    """Render com o minimal_page.py PRÉ-F53 (SHA congelado) em subprocesso
    isolado. Mesma fixture, mesmo carimbo, mesmo sys.path de src/ (a F53
    não toca src/ — verificado no check de abertura). None = indisponível.
    """
    blob = _baseline_source()
    if blob is None:
        return None
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "scripts").mkdir(parents=True)
        (tdp / "scripts" / "minimal_page.py").write_text(blob, encoding="utf-8")
        jp = tdp / "jobs.json"
        jp.write_text(json.dumps(jobs), encoding="utf-8")
        if full:
            call = ("html = mp.render_minimal_html(jobs, "
                    "total_eligible=len(jobs), generated_at=STAMP, "
                    "full_list=True, profile_maps=mp._profile_maps(jobs), "
                    "with_snippets=True)\n")
        else:
            call = ("html = mp.render_minimal_html(jobs, "
                    "total_eligible=len(jobs), generated_at=STAMP, "
                    "top=mp.PAGE_TOP, with_snippets=True)\n")
        code = (
            "import sys, json, hashlib\n"
            f"sys.path.insert(0, r'{tdp / 'scripts'}')\n"
            f"sys.path.insert(0, r'{REPO / 'src'}')\n"
            "import minimal_page as mp\n"
            f"STAMP = {STAMP!r}\n"
            f"jobs = json.load(open(r'{jp}', encoding='utf-8'))\n"
            + call +
            "h = html.encode('utf-8')\n"
            "print(len(h))\n"
            "print(hashlib.sha256(h).hexdigest())\n"
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("      [A/B pré-F53] subprocesso falhou:",
                  (r.stderr.strip().splitlines() or ["?"])[-1])
            return None
        lines = r.stdout.strip().splitlines()
        return int(lines[0]), lines[1]


def test_nojs_and_legacy_ab() -> None:
    section("T4: item 6 — sem JS a página é a da F51; legado byte a byte")
    jobs = make_jobs()
    # HTML estático do full: NENHUM elemento da interatividade — tudo é
    # criado/ativado por JS. Sem JS: todos os cards visíveis e funcionais.
    # (Checks independentes de ambiente — rodam no CI raso também.)
    full = render_full(jobs)
    static = strip_scripts(full)
    check("estático: sem botão '✓ já vi' (vem do JS)",
          not re.search(r"<button[^>]*seenb", static))
    check("estático: sem #totop (voltar-ao-topo vem do JS)",
          'id="totop"' not in static)
    check("estático: sem #empty (empty-state vem do JS)",
          'id="empty"' not in static)
    check("estático: nenhum <li> marcado como já visto",
          not re.search(r"<li [^>]*data-seen", static))
    check("estático: mensagem do empty-state só no JS (1 ocorrência)",
          full.count("nenhuma vaga corresponde") == 1
          and "nenhuma vaga corresponde" not in static)
    main_block = full.split('<ol id="list">')[1].split("</ol>")[0]
    check("sem JS: todos os cards visíveis (sem display:none na lista)",
          "display:none" not in main_block
          and main_block.count("<li ") == N_JOBS,
          f"{main_block.count('<li ')} cards")
    legacy = mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        top=mp.PAGE_TOP, with_snippets=True, lang="pt")
    check("full difere do legado (features existem de fato)",
          len(full.encode()) != len(legacy.encode()))

    # ---- A/B contra o SHA congelado (precisa de história git) ----
    # CI roda com checkout RASO (fetch-depth=1 do actions/checkout): o
    # `git show` do SHA não resolve — MESMA convenção do test_f51
    # (_ab_before retorna None e a suíte segue): [SKIP] no CI; o A/B
    # roda onde há história (local/VPS — resultado no relatório).
    diff = subprocess.run(
        ["git", "diff", "--name-only", _AB_BASELINE_SHA, "--", "src/"],
        capture_output=True, text=True, cwd=str(REPO))
    if diff.returncode != 0:
        print("  [SKIP] A/B pré-F53 indisponível no CI (checkout raso — "
              "sem história p/ git show); byte-identity verificado na "
              "suíte local (relatório §T4)")
        return
    check("pré-condição A/B: src/ intocado vs baseline",
          diff.stdout.strip() == "", diff.stdout.strip()[:120])

    base = _baseline_render(jobs, full=False)
    if base is None:
        print("  [SKIP] A/B legado indisponível (git show falhou)")
        return
    # F60 — o legado pt carrega as adições da fase (data-fr + legenda
    # 🇫🇷 + badge FR); o byte a byte pré-F53 vale módulo esse delta
    # determinístico (strip cirúrgico; qualquer outro byte divergente
    # continua FAIL).
    # F83 — idem: o legado pt ganhou o sufixo de ocultas da p_line
    # (fixture 24/8: cap 2/empresa esconde 8). Strip F60+F83.
    # F86 — idem: o item da legenda ⏳/⚠️ ganhou o sinal de tipo
    # ambíguo (badge só acende em título duplo, sem fixture). Strip
    # F60+F83+F86.
    legacy_f60 = _strip_f95(_strip_f86(_strip_f83(_strip_f60(legacy))))
    cur_sha = hashlib.sha256(legacy_f60.encode("utf-8")).hexdigest()
    check("legado BYTE A BYTE igual ao pré-F53 módulo adições F60+F83 (sha256)",
          cur_sha == base[1], f"{base[0]}B, sha {base[1][:12]}…")


# ---------------------------------------------------------------------------
# T5 — JS em node: já-vi, esconder aplicadas, empty-state, tooltip, topo
# ---------------------------------------------------------------------------

# Cards do harness: j-a aplicada (com fatores) · j-b JÁ VISTA no
# localStorage (com fatores) · j-c ignorada (👁️ — NÃO é candidatura) ·
# j-d entrevista (sem fatores) · gêmeo de j-a (mesma vaga numa seção).
_CARD_SPECS = [
    ("j-a", "praktikum einkauf alpha", "12", "1", "applied",
     "área +2 · tipo +1"),
    ("j-b", "praktikum logistik beta", "15", "2", None,
     "idioma +1.5 · skills +0.8"),
    ("j-c", "internship controlling gamma", "9", "3", "ignored", None),
    ("j-d", "werkstudent data delta", "8", "4", "interview", None),
    ("j-a", "praktikum einkauf alpha", "12", "5", "applied",
     "área +2 · tipo +1"),
]


def _harness() -> str:
    cards_js = []
    for jid, q, s, r, ps, fac in _CARD_SPECS:
        attrs = {"data-jid": jid, "data-q": q, "data-s": s, "data-r": r}
        if ps:
            attrs["data-ps"] = ps
        cards_js.append(f"cards.push(mkcard({json.dumps(attrs)},"
                        f" {json.dumps(fac)}));")
    return """
var REG=[];
function mk(o){o=o||{};var n={a:o.attrs||{},style:o.style||{},kids:[],
 handlers:{},className:o.className||'',textContent:o.textContent||'',
 type:'',id:o.id||'',parentNode:null,
 getAttribute:function(k){return (k in this.a)?this.a[k]:null;},
 setAttribute:function(k,v){this.a[k]=String(v);},
 removeAttribute:function(k){delete this.a[k];},
 appendChild:function(c){var i=this.kids.indexOf(c);if(i>-1)this.kids.splice(i,1);
   this.kids.push(c);c.parentNode=this;},
 insertBefore:function(c,ref){this.kids.unshift(c);c.parentNode=this;},
 addEventListener:function(ev,fn){(this.handlers[ev]=this.handlers[ev]||[]).push(fn);},
 _find:function(sel){for(var i=0;i<this.kids.length;i++){var k=this.kids[i];
   if(sel==='.bd'&&k.className==='bd')return k;
   if(sel==='.s'&&k.className==='s')return k;
   if(sel==='.seenb'&&typeof k.className==='string'&&k.className.indexOf('seenb')===0)return k;
   if(k._find){var r=k._find(sel);if(r)return r;}}
   return null;},
 querySelector:function(sel){return this._find(sel);}};
REG.push(n);return n;}
function mkcard(attrs,fac){var li=mk({attrs:attrs});
 var rs=mk({});rs.className='r';
 var ss=mk({});ss.className='s';if(fac)ss.a['data-factors']=fac;
 var bd=mk({});bd.className='bd';
 li.appendChild(rs);li.appendChild(ss);li.appendChild(bd);return li;}
var cards=[];
__CARDS__
var tabs=[mk({attrs:{'data-prof':'business'}}),mk({attrs:{'data-prof':'materials'}}),mk({attrs:{'data-prof':'eu'}})];
var ol=mk({}),MAIN=mk({}),BODY=mk({});MAIN.appendChild(ol);
var seen=mk({});seen.checked=false;
var app=mk({});app.checked=false;
var q=mk({});q.value='';
var cnt=mk({});cnt.textContent='';
var STORAGE={_d:{'if53seen:j-b':'1'},
 getItem:function(k){return (k in this._d)?this._d[k]:null;},
 setItem:function(k,v){this._d[k]=String(v);},
 removeItem:function(k){delete this._d[k];}};
var window={localStorage:STORAGE,pageYOffset:0,handlers:{},scrolled:0,
 addEventListener:function(ev,fn){(this.handlers[ev]=this.handlers[ev]||[]).push(fn);},
 scrollTo:function(x,y){this.scrolled++;}};
var document={querySelectorAll:function(s){
   if(s==='#tabs button')return tabs;
   if(s==='#list li.c'||s==='li.c[data-jid]')return cards;
   return [];},
 getElementById:function(i){
   if(i==='f-seen')return seen;if(i==='f-app')return app;if(i==='q')return q;
   if(i==='n')return cnt;if(i==='list')return ol;
   for(var r=0;r<REG.length;r++){if(REG[r].id===i)return REG[r];}
   return null;},
 createElement:function(tag){return mk({});},body:BODY,documentElement:{}};
__JS__
function fire(node,ev){(node.handlers[ev]||[]).forEach(function(f){
  f({target:node,preventDefault:function(){},stopPropagation:function(){}});});}
function snap(){return {
 disp:cards.map(function(c){return c.style.display;}),
 count:cnt.textContent,
 empty:(document.getElementById('empty')||{style:{}}).style.display,
 seen:cards.map(function(c){return c.getAttribute('data-seen')||'';}),
 btns:cards.map(function(c){var b=c.querySelector('.seenb');return b?b.className:'none';}),
 titles:cards.map(function(c){var s=c.querySelector('.s');return (s&&s.a['title'])?s.a['title']:'';}),
 ls:Object.keys(STORAGE._d).sort(),
 totop:(document.getElementById('totop')||{style:{}}).style.display};}
var out={};
out.initial=snap();
seen.checked=true;fire(seen,'change');out.seenshow=snap();
seen.checked=false;fire(seen,'change');
app.checked=true;fire(app,'change');out.hideapp=snap();
app.checked=false;fire(app,'change');
q.value='zzzz';fire(q,'input');out.emptystate=snap();
q.value='';fire(q,'input');
var bBtn=cards[1].querySelector('.seenb');fire(bBtn,'click');out.unsee=snap();
fire(bBtn,'click');out.see=snap();
var eBtn=cards[4].querySelector('.seenb');fire(eBtn,'click');
out.twin={a:cards[0].getAttribute('data-seen')||'',e:cards[4].getAttribute('data-seen')||'',
 btnA:(cards[0].querySelector('.seenb')||{}).className,
 btnE:(cards[4].querySelector('.seenb')||{}).className,
 ls:Object.keys(STORAGE._d).sort()};
window.pageYOffset=800;fire(window,'scroll');
out.topShow=document.getElementById('totop').style.display;
window.pageYOffset=100;fire(window,'scroll');
out.topHide=document.getElementById('totop').style.display;
console.log(JSON.stringify(out));
""".replace("__CARDS__", "\n".join(cards_js))


def _node(js: str, harness: str, timeout: int = 30):
    proc = subprocess.run(["node", "-"], input=harness.replace("__JS__", js),
                           capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def test_interactivity_node() -> None:
    section("T5: JS da interatividade em node (localStorage mockado)")
    if shutil.which("node") is None:
        check("node disponível p/ executar o JS", False,
              "[SKIP] node ausente (CI tem node)")
        return

    # Núcleo puro do voltar-ao-topo (padrão f43LazyInit): limite 600px.
    rc, out, err = _node(mp._JS_F53_CORE,
                         "__JS__\nconsole.log(JSON.stringify("
                         "{a:f53Top(599),b:f53Top(600),c:f53Top(601),"
                         "d:f53Top(0)}));")
    check("núcleo f53Top roda em node", rc == 0, err.strip()[:200])
    if rc == 0:
        d = json.loads(out.strip().splitlines()[-1])
        check("f53Top: limiar de 600px (599/600 fora, 601 dentro)",
              d == {"a": False, "b": False, "c": True, "d": False}, str(d))

    # Regressão do FIX F43 (bug latente descoberto pela F53): o wrapper
    # do lazy lia ``window.__F43.state`` mas o estado É ``window.__F43``
    # (plano) — no navegador real o wrapper morria em TypeError
    # silencioso (lazy-render inerte, contador inicial morto). O stack
    # inteiro agora roda; o caminho de fallback (sem IntersectionObserver
    # — o caso do node) revela tudo E a applyProfile inicial preenche o
    # contador no load.
    js43 = (mp._JS_PROFILE + mp._JS_LAZY_CORE
            + (mp._JS_LAZY_IO % (mp.LAZY_INITIAL_CARDS, mp.LAZY_ROOT_MARGIN)))
    prelude = _harness().split("function fire")[0]
    rc, out, err = _node(js43, prelude + "\nconsole.log(JSON.stringify("
                        "{count:cnt.textContent,lazy:cards.map("
                        "function(c){return c.getAttribute('data-lazy')"
                        "||'';})}));\n")
    check("F43-fix: stack abas+lazy roda em node SEM TypeError "
          "(regressão do bug latente)", rc == 0, err.strip()[:200])
    if rc == 0:
        d43 = json.loads(out.strip().splitlines()[-1])
        check("F43-fix: applyProfile INICIAL roda no load (contador)",
              d43["count"] == "5 vagas", str(d43["count"]))
        check("F43-fix: fallback sem IO revela tudo (sem data-lazy)",
              set(d43["lazy"]) == {""}, str(d43["lazy"]))

    js = mp._JS_PROFILE + mp._JS_F53_CORE + mp._JS_F53
    rc, out, err = _node(js, _harness())
    check("JS de interatividade roda em node sem erro", rc == 0,
          err.strip()[:200])
    if rc != 0:
        return
    o = json.loads(out.strip().splitlines()[-1])

    # Item 1 — "já vi": estado do localStorage vira data-seen + botão on,
    # card OCULTO por padrão (o atrito é re-lê-lo), contagem segue a verdade.
    check("carga inicial: vaga vista ganha data-seen=1",
          o["initial"]["seen"] == ["", "1", "", "", ""], str(o["initial"]["seen"]))
    check("carga inicial: botão da vaga vista fica 'on'",
          o["initial"]["btns"][1] == "seenb on", str(o["initial"]["btns"]))
    check("vistas OCULTAS por padrão (display none)",
          o["initial"]["disp"][1] == "none", str(o["initial"]["disp"]))
    check("contador conta só as visíveis (4 de 5)",
          o["initial"]["count"] == "4 vagas", o["initial"]["count"])

    # Toggle "mostrar já vistas": revela (ainda esmaecida pelo CSS).
    check("toggle f-seen: revela a vista (display '')",
          o["seenshow"]["disp"][1] == "" and o["seenshow"]["count"] == "5 vagas",
          str(o["seenshow"]))

    # Item 2 — "esconder aplicadas": filtra por data-ps; 'ignored' fica.
    check("toggle f-app: applied (a) e interview (d) ocultas",
          o["hideapp"]["disp"][0] == "none" and o["hideapp"]["disp"][3] == "none",
          str(o["hideapp"]["disp"]))
    check("toggle f-app: 'ignored' (👁️) PERMANECE visível",
          o["hideapp"]["disp"][2] == "", str(o["hideapp"]["disp"]))
    check("toggle f-app: sem status (b vista revelada?) — filtros empilham: "
          "b continua oculta pelo já-vi",
          o["hideapp"]["disp"][1] == "none"
          and o["hideapp"]["count"] == "1 vagas", str(o["hideapp"]))

    # Item 4 — empty-state da busca.
    check("busca sem resultado: contador 0",
          o["emptystate"]["count"] == "0 vagas", o["emptystate"]["count"])
    check("empty-state visível quando 0 resultados",
          o["emptystate"]["empty"] == "", str(o["emptystate"]["empty"]))
    check("empty-state some quando a busca volta a casar "
          "(snapshot pós-unsee tem 5 visíveis)",
          o["unsee"]["count"] == "5 vagas" and o["unsee"]["empty"] == "none",
          str(o["unsee"]["count"]))

    # Item 1 — clique no botão: persiste no localStorage e re-filtra.
    check("clique desmarca: localStorage limpa o job",
          o["unsee"]["ls"] == [] and o["unsee"]["btns"][1] == "seenb",
          str(o["unsee"]["ls"]))
    check("clique de novo: marca, persiste e oculta de novo",
          o["see"]["ls"] == ["if53seen:j-b"] and o["see"]["disp"][1] == "none"
          and o["see"]["btns"][1] == "seenb on", str(o["see"]))

    # Gêmeos entre seções (mesma vaga na lista e numa seção) sincronizam.
    check("gêmeos: marcar um marca TODOS os cards do mesmo job-id",
          o["twin"]["a"] == "1" and o["twin"]["e"] == "1"
          and o["twin"]["btnA"] == "seenb on"
          and o["twin"]["btnE"] == "seenb on", str(o["twin"]))
    check("gêmeos: UMA chave no localStorage pelo job-id",
          o["twin"]["ls"] == ["if53seen:j-a", "if53seen:j-b"],
          str(o["twin"]["ls"]))

    # Item 3 — tooltip nativo montado a partir do data-factors.
    check("tooltip: title= só nos cards COM data-factors",
          o["initial"]["titles"][0] == "fatores do score: área +2 · tipo +1"
          and o["initial"]["titles"][2] == ""
          and o["initial"]["titles"][3] == "", str(o["initial"]["titles"]))

    # Item 5 — voltar-ao-topo.
    check("voltar-ao-topo: oculto no topo da página",
          o["initial"]["totop"] == "none", str(o["initial"]["totop"]))
    check("voltar-ao-topo: aparece após scroll (800px)",
          o["topShow"] == "", o["topShow"])
    check("voltar-ao-topo: some de volta (100px)",
          o["topHide"] == "none", o["topHide"])


# ---------------------------------------------------------------------------
# T6 — orçamento: chrome, custo por card, caps dos dois regimes
# ---------------------------------------------------------------------------

def test_budget() -> None:
    section("T6: medição de bytes + caps respeitados")
    chrome = (mp._JS_F53_CORE + mp._JS_F53 + mp._CSS_F53).encode("utf-8")
    bar = ("\n<label><input type=\"checkbox\" id=\"f-seen\"> "
           "mostrar já vistas</label>\n<label><input type=\"checkbox\" "
           "id=\"f-app\"> esconder aplicadas</label>").encode("utf-8")
    total_chrome = len(chrome) + len(bar)
    print(f"       chrome F53: JS {len(mp._JS_F53_CORE + mp._JS_F53)} B "
          f"+ CSS {len(mp._CSS_F53)} B + toggles {len(bar)} B "
          f"= {total_chrome} B (fixo, 1× por página)")
    check("chrome F53 (JS+CSS+toggles) < 3,5 KB", total_chrome < 3_500,
          f"{total_chrome}B")

    jobs = make_jobs()
    full = render_full(jobs)
    main_block = full.split('<ol id="list">')[1].split("</ol>")[0]
    attrs = re.findall(r'data-factors="([^"]*)"', main_block)
    per_card = [len((' data-factors="' + a + '"').encode("utf-8"))
                for a in attrs]
    avg = sum(per_card) / len(per_card) if per_card else 0
    print(f"       data-factors: {len(per_card)} cards, média "
          f"{avg:.1f} B/card, max {max(per_card)} B/card")
    check("data-factors em MÉDIA < 80 B/card", avg < 80, f"{avg:.1f}B")
    check("data-factors no pior caso < 100 B/card", max(per_card) < 100,
          f"{max(per_card)}B")

    cap = mp.page_full_cap_bytes(len(jobs))
    size = len(full.encode("utf-8"))
    check("full da fixture <= cap proporcional", size <= cap,
          f"{size}B <= {cap}B")
    legacy = render_legacy(jobs)
    check("legado < cap duro 150KB",
          len(legacy.encode()) < mp.PAGE_HARD_CAP_BYTES)

    # Universo maior (300) — a faixa real de produção: continua no cap.
    big = make_jobs(300, 40)
    big_full = render_full(big)
    big_cap = mp.page_full_cap_bytes(300)
    print(f"       universo 300: página {len(big_full.encode())} B "
          f"| cap {big_cap} B")
    check("universo 300: full <= cap proporcional",
          len(big_full.encode()) <= big_cap,
          f"{len(big_full.encode())}B <= {big_cap}B")

    # A/B de tamanho no full: pós-F53 cresce APENAS o previsto
    # (chrome + data-factors); nada além disso. (Precisa de história git —
    # no CI raso entra no mesmo [SKIP] do T4; medida local no relatório.)
    base = _baseline_render(jobs, full=True)
    if base is None:
        print("  [SKIP] A/B full pré-F53 indisponível (checkout raso do "
              "CI); delta medido na suíte local (relatório §T6)")
        return
    cur = mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        full_list=True, profile_maps=mp._profile_maps(jobs),
        with_snippets=True, lang="pt")
    delta = len(cur.encode("utf-8")) - base[0]
    # chrome F53 = blocos novos (núcleo+JS+CSS+toggles) + a EXTENSÃO do
    # _JS_PROFILE (estado se/ap, condições do cardOk, empty-state,
    # listeners) medida contra o baseline — nada de margem mágica.
    base_profile = _baseline_const("_JS_PROFILE")
    profile_ext = (len(mp._JS_PROFILE) - len(base_profile)
                   if base_profile is not None else 0)
    expected_lo = total_chrome + profile_ext
    expected_hi = expected_lo + sum(per_card) + 200  # margem de esc
    # F60 — as adições da fase (data-fr por card + legenda 🇫🇷 + badge
    # FR) saem do delta antes do orçamento: ele continua verificando
    # APENAS o chrome F53 + extensão do _JS_PROFILE + fatores, como na
    # fase. O delta F60 é medido no PRÓPRIO render (strip cirúrgico),
    # não hardcoded.
    f60_add = len(cur.encode("utf-8")) - len(_strip_f60(cur).encode("utf-8"))
    # F86 — a legenda ⏳/⚠️ ganhou o sinal de tipo ambíguo (delta
    # determinístico, medido no próprio render pelo strip).
    f86_add = len(cur.encode("utf-8")) - len(_strip_f86(cur).encode("utf-8"))
    # F95 — delta da fase (data-nl por card + item 🇳🇱 da legenda; badges
    # F95 não acendem nas fixtures sintéticas), medido pelo strip.
    f95_add = len(cur.encode("utf-8")) - len(_strip_f95(cur).encode("utf-8"))
    delta_net = delta - f60_add - f86_add - f95_add
    print(f"       A/B full: pré {base[0]}B -> pós {len(cur.encode())}B "
          f"(delta {delta:+d}B = F60 {f60_add}B + F86 {f86_add}B + "
          f"F95 {f95_add}B + líquido "
          f"{delta_net:+d}B; previsto chrome {total_chrome}B + "
          f"ext._JS_PROFILE {profile_ext}B + fatores {sum(per_card)}B)")
    check("A/B full: pós > pré (features existem)", delta > 0,
          f"{delta:+d}B")
    check("A/B full: delta dentro do orçamento previsto",
          expected_lo <= delta_net <= expected_hi,
          f"líquido {delta_net:+d}B vs [{expected_lo}..{expected_hi}] "
          f"(F60: +{f60_add}B, F86: +{f86_add}B, F95: +{f95_add}B)")


# ---------------------------------------------------------------------------
# T7 — caminho do publish (from_file, top=PAGE_TOP_FULL)
# ---------------------------------------------------------------------------

def test_publish_path() -> None:
    section("T7: publish (from_file + PUBLIC_TOP) entrega a interatividade")
    jobs = make_jobs()[:12]
    tmpdir = tempfile.mkdtemp(prefix="f53-test-")
    tmp = Path(tmpdir) / "jobs.json"
    tmp.write_text(json.dumps(jobs), encoding="utf-8")
    try:
        html = mp.render_minimal_html_from_file(
            tmp, top=mp.PAGE_TOP_FULL, generated_at=STAMP, lang="pt")
        check("publish liga o full E a interatividade (toggles)",
              'id="f-seen"' in html and 'id="f-app"' in html)
        check("publish: data-factors no card",
              "data-factors=" in html)
        check("publish: JS F53 inline (sem rede, sem libs)",
              "if53seen:" in html and "<script src" not in html)
        check("publish: página dentro do cap proporcional",
              len(html.encode()) <= mp.page_full_cap_bytes(len(jobs)),
              f"{len(html.encode())}B")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> int:
    print("F53 — interatividade vanilla (já-vi, aplicadas, score "
          "on-demand, empty-state, voltar-ao-topo)")
    test_regime_split()
    test_factors_build()
    test_application_state()
    test_nojs_and_legacy_ab()
    test_interactivity_node()
    test_budget()
    test_publish_path()
    print()
    if FAILURES:
        print(f"F53: FALHAS: {len(FAILURES)} de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F53: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
