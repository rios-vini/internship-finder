"""Interface do internship-finder: ranking completo, filtros e ordenacao (Fase 3).

Gera uma pagina HTML unica e auto-contida (CSS inline, JS vanilla inline, sem
framework e sem dependencia nova) com as vagas ja ranqueadas pelo pipeline. A
pagina publicada em GitHub Pages e a interface principal de consulta: mostra
TODAS as vagas elegiveis (nao so o Top 30), com filtros e ordenacao
client-side, score explicavel e link direto para o anuncio original.

Fase 3 (apresentacao pura): a logica de coleta/filtros/dedup/ranking NAO muda —
esta pagina apenas apresenta o ``eligible_jobs.json`` que o run produziu. Nada
e re-ranqueado; o score exibido e o do pipeline; o ``score_breakdown`` usa os
componentes REAIS do ``ranking.score_job`` (area, skills, language, type,
location, penalties) — nenhum criterio ou peso novo.

Fontes (os DOIS caminhos funcionam):

- ``--input``: JSON ranqueado (default ``data/eligible_jobs.json`` do CWD),
  saida direta do ``cli --rank`` — contem ``score``/``score_breakdown``.
  Ordenado por score desc (estavel; o score e o Ja calculado, nunca recomputado).
- ``--db``: SQLite ``jobs.db`` (default como fallback ao JSON ausente) — le
  apenas vagas ATIVAS (``active=1``), sem score (o banco nao tem a coluna):
  ordena por ``last_seen`` desc (mais recentes primeiro).

Filtros na GERACAO (3 eixos, aplicados sobre a lista JA pronta — mesmo
comportamento das fases anteriores):

- ``--company``: substring case-insensitive no campo empresa;
- ``--keyword``: substring case-insensitive no TITULO;
- ``--country``: mesma spec do CLI (reusa ``parse_country_spec``/
  ``matches_country``): ISO alpha-2 em lista, 'europe', 'remote' ou 'all'.
  Spec invalida -> erro claro (exit 2).

Filtros e ordenacao no BROWSER (Fase 3, vanilla JS, sem backend): a pagina
embute cada vaga como data-attributes na linha da tabela e o JS filtra
(texto/titulo, empresa, local, tipo, pais, score minimo) e ordena (score,
posicao, empresa, titulo, local, data) sem recarregar. Top 30 recebe badge
discreto; cada vaga tem "por que este score" com a composicao real do
breakdown; o botao/titulo leva direto ao anuncio (http/https validado, P2.3).
O nucleo JS puro (``if_filter_sort``/``if_match``/``if_sorter``) e separado
da cola DOM para ser executavel em node nos testes.

Uso:

    .venv/bin/python scripts/interface.py                    # eligible_jobs.json -> /tmp/interface.html
    .venv/bin/python scripts/interface.py --top 10 --company sap --keyword logistik
    .venv/bin/python scripts/interface.py --db data/jobs.db --country europe --output -   # stdout

``--output -`` imprime o HTML no stdout; ``--top <= 0`` e spec de pais
invalida -> parser.error (exit 2), mesmo padrao das validacoes do CLI.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.countries import matches_country, parse_country_spec  # noqa: E402

DEFAULT_OUTPUT = Path("/tmp/interface.html")

# Quantas posicoes recebem o destaque visual "Top 30" (apenas apresentacao;
# o Top 30 do Telegram e definido pelo digest, nao por esta constante).
TOP_N = 30

# Colunas exibidas do SQLite. ``raw`` fica de fora de proposito (JSON grande,
# aninhado — a fonte de verdade e o JSON); o SELECT e de LEITURA apenas.
_DB_COLUMNS = [
    "id", "source", "title", "company", "location", "country", "remote",
    "url", "description", "internship", "posted_at", "collected_at",
    "application_deadline", "external_id", "employment_type", "country_iso",
    "first_seen", "last_seen",
]

# Rotulos PT-BR das componentes REAIS do score_breakdown (ranking.py: area,
# skills, language, type, location, penalties — nenhuma componente inventada).
_BREAKDOWN_LABELS = {
    "area": "Área",
    "skills": "Skills",
    "language": "Idioma",
    "type": "Tipo",
    "location": "Local",
    "penalties": "Penalidades",
}
_BREAKDOWN_ORDER = ("area", "skills", "language", "type", "location", "penalties")


def load_json(path: Path) -> list[dict]:
    """Le o snapshot ranqueado (``eligible_jobs.json``) como lista de dicts."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"formato inesperado em {path}: esperado lista de vagas")
    return data


def load_db(path: Path, *, active_only: bool = True) -> list[dict]:
    """Le as vagas ATIVAS do SQLite (fonte viva do historico), sem score.

    Ordena por ``last_seen`` desc (vagas mais recentes primeiro) + ``id``
    (desempate deterministico). ``active_only=False`` le o banco inteiro
    (uso em testes/auditoria).
    """
    where = "WHERE active = 1 " if active_only else ""
    query = (
        "SELECT " + ", ".join(_DB_COLUMNS) + " FROM jobs " + where
        + "ORDER BY last_seen DESC, id"
    )
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def apply_filters(
    jobs: list[dict],
    *,
    company: str | None = None,
    keyword: str | None = None,
    country: str | None = None,
) -> list[dict]:
    """Filtra a lista JA ranqueada por empresa / palavra no titulo / pais.

    Substrings case-insensitive (empresa e palavra). ``country`` usa a MESMA
    spec do CLI (``parse_country_spec``: ISO, 'europe', 'remote', 'all'; None
    ou 'all' = sem filtro). NaO re-ranqueia: apenas mantem o que casa.
    """
    company_q = (company or "").strip().casefold()
    keyword_q = (keyword or "").strip().casefold()
    spec = parse_country_spec(country) if country is not None else None
    out: list[dict] = []
    for j in jobs:
        if company_q and company_q not in str(j.get("company") or "").casefold():
            continue
        if keyword_q and keyword_q not in str(j.get("title") or "").casefold():
            continue
        if spec is not None and not matches_country(
            j.get("country_iso"), j.get("location"), j.get("remote"), spec
        ):
            continue
        out.append(j)
    return out


def sort_ranked(jobs: list[dict]) -> list[dict]:
    """Ordena pelo score JA existente (nunca recomputa): desc, estavel.

    Vagas sem score (caminho SQLite) ficam no final, na ordem recebida
    (``last_seen`` desc). Empates mantem a ordem de entrada (o JSON ja vem
    ordenado pelo ``rank_jobs`` do pipeline — este sort e defensivo).
    """
    def key(j: dict) -> float:
        s = j.get("score")
        return -float(s) if isinstance(s, (int, float)) else float("inf")

    return sorted(jobs, key=key)


def _fmt_score(value) -> str:
    """Score como ``NN.NN``; ausente (SQLite) -> '—'."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_date(value) -> str:
    """Primeiros 10 chars de um timestamp ISO (parte de data) ou '—'."""
    if not value:
        return "—"
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text


def _fmt_bool(value) -> str | None:
    """True/1 -> 'sim'; False/0/None -> None (nao exibe)."""
    if isinstance(value, (bool, int)) and value:
        return "sim"
    return None


# P2.3: schemes aceitos em ``href`` — navegadores executam javascript:/data:/
# no contexto da pagina; aqui so link http/https vira ``<a href>``.
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def _safe_url(value) -> str | None:
    """URL aceitavel para ``href``: somente scheme http/https (nao prefixo).

    Rejeita (retorna ``None``) qualquer outro scheme — javascript:, data:,
    file:, ftp:, mailto:, tel:... — alem de ausencia de scheme (URL relativa)
    e URLs malformadas que o parser rejeita. Comparacao de scheme sem
    diferenciar maiusculas. Nao valida a URL alem do scheme: o destino
    continua passando pelo ``html.escape`` existente (validar scheme ->
    escape -> gerar href).
    """
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        scheme = urlsplit(text).scheme
    except ValueError:
        return None
    return text if scheme.casefold() in _ALLOWED_URL_SCHEMES else None


def _attr(value) -> str:
    """Valor seguro para ATRIBUTO HTML (escape total, com aspas)."""
    return html.escape(str(value), quote=True)


def _breakdown_items(job: dict) -> list[tuple[str, str, float]]:
    """Componentes reais do ``score_breakdown``: (label, chave, valor)."""
    b = job.get("score_breakdown") or {}
    if not isinstance(b, dict):
        return []
    out: list[tuple[str, str, float]] = []
    for key in _BREAKDOWN_ORDER:
        if key not in b:
            continue
        try:
            val = float(b[key])
        except (TypeError, ValueError):
            continue
        out.append((_BREAKDOWN_LABELS.get(key, key), key, val))
    return out


def _breakdown_html(job: dict) -> str:
    """Bloco 'por que este score': componentes com barra proporcional + total.

    Barra = |valor| relativo ao maior |valor| da propria vaga (visual so;
    os numeros exibidos sao os componentes reais, sem nenhuma conta nova).
    """
    items = _breakdown_items(job)
    if not items:
        return ""
    maxv = max((abs(v) for _, _, v in items), default=0.0)
    rows = ""
    for label, _key, val in items:
        sign = "+" if val >= 0 else ""
        width = (abs(val) / maxv * 100) if maxv > 0 else 0
        neg = ' class="bd-neg"' if val < 0 else ""
        rows += (
            '<div class="bd">'
            f'<span class="bd-l">{html.escape(label)}</span>'
            f'<span class="bd-v">{sign}{val:.2f}</span>'
            f'<span class="bd-bar"><i{neg} style="width:{width:.0f}%"></i></span>'
            "</div>"
        )
    total = job.get("score")
    total_txt = f"Total <b>{_fmt_score(total)}</b>" if total is not None else "Total —"
    return f'<div class="bd-body">{rows}<div class="bd-total">{total_txt}</div></div>'


def _details_html(job: dict) -> str:
    """Detalhes compactos da vaga (fora da tabela, dentro do <details>).

    Extras factuais do proprio registro (nada inferido): tipo do anuncio,
    estagio/remoto, deadline, "desde" e um trecho curto da descricao.
    """
    parts: list[str] = []
    if job.get("employment_type"):
        parts.append(f"tipo do anúncio: {html.escape(str(job['employment_type']))}")
    if _fmt_bool(job.get("internship")):
        parts.append("estágio")
    if _fmt_bool(job.get("remote")):
        parts.append("remoto")
    if job.get("application_deadline"):
        parts.append(f"candidaturas até {_fmt_date(job['application_deadline'])}")
    added = _fmt_date(job.get("first_seen") or job.get("posted_at")
                      or job.get("collected_at"))
    if added != "—":
        parts.append(f"desde {added}")
    extras = ""
    if parts:
        extras = '<p class="mut facts">' + " · ".join(parts) + "</p>"
    desc = job.get("description")
    desc_snippet = ""
    if desc:
        text = " ".join(str(desc).split())
        if len(text) > 300:
            text = text[:300] + "…"
        desc_snippet = f'<p class="mut desc">{html.escape(text)}</p>'
    return (
        "<details class=\"why\">"
        "<summary>por que este score</summary>"
        f"{_breakdown_html(job)}"
        f"{extras}"
        f"{desc_snippet}"
        "</details>"
    )


def _added_date(job: dict) -> str:
    """Data exibida na coluna 'desde' (primeira data confiavel do registro)."""
    return _fmt_date(job.get("first_seen") or job.get("posted_at")
                     or job.get("collected_at"))


def _row_html(rank: int, job: dict, *, top_n: int = TOP_N) -> str:
    """Uma linha da tabela (tudo escapado; URL clicavel, abre em nova aba).

    A linha carrega os data-attributes que o JS client-side usa para filtrar
    e ordenar (titulo, empresa, local, tipo, pais, score, posicao, data).
    Posicao ``rank`` = posicao no ranking do pipeline; ``top_n`` primeiras
    recebem o badge "Top 30" e a classe de destaque (so apresentacao).

    P2.3: a URL so vira ``href`` apos validar o scheme (somente http/https,
    via ``_safe_url``); scheme rejeitado segue o fluxo de URL vazia — o
    titulo aparece sem link e sem botao. O escaping HTML continua aplicado
    depois da validacao (validar scheme -> escape -> gerar href).
    """
    title = html.escape(str(job.get("title") or "(sem titulo)"))
    safe_url = _safe_url(job.get("url"))
    url = html.escape(safe_url or "")
    company = html.escape(str(job.get("company") or "—"))
    location = html.escape(str(job.get("location") or "—"))
    emp_type = job.get("employment_type")
    type_txt = html.escape(str(emp_type)) if emp_type else "—"
    country = html.escape(str(job.get("country_iso") or ""))
    added = _added_date(job)
    added_attr = "" if added == "—" else added
    score = job.get("score")
    score_attr = str(score) if isinstance(score, (int, float)) else ""

    is_top = top_n > 0 and rank <= top_n
    badge = '<span class="badge-top">Top 30</span>' if is_top else ""
    row_class = "top30" if is_top else ""
    link = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if safe_url else title
    open_btn = (
        f'<a class="open" href="{url}" target="_blank" rel="noopener">abrir&nbsp;↗</a>'
        if safe_url else '<span class="mut">—</span>'
    )
    # Atributos de dados para o JS client-side (escapados para atributo).
    d_title = _attr(job.get("title") or "")
    d_company = _attr(job.get("company") or "")
    d_location = _attr(job.get("location") or "")
    d_type = _attr(job.get("employment_type") or "")
    d_country = _attr(job.get("country_iso") or "")
    d_date = _attr(added_attr)
    return (
        f'<tr class="{row_class}"'
        f' data-rank="{rank}"'
        f' data-title="{d_title}"'
        f' data-company="{d_company}"'
        f' data-location="{d_location}"'
        f' data-type="{d_type}"'
        f' data-country="{d_country}"'
        f' data-score="{score_attr}"'
        f' data-date="{d_date}">'
        f'<td class="score">{rank}</td>'
        f'<td class="score">{_fmt_score(score)}</td>'
        f"<td>{link}{badge}{_details_html(job)}</td>"
        f"<td>{company}</td>"
        f'<td class="loc">{location}</td>'
        f"<td>{type_txt}</td>"
        f'<td class="mut">{added}</td>'
        f'<td class="act">{open_btn}</td>'
        "</tr>"
    )


def _compute_stats(jobs: list[dict], *, total: int) -> dict:
    """Resumo do topo (estado atual da busca), derivado dos dados reais."""
    companies = len({str(j.get("company") or "") for j in jobs if j.get("company")})
    scores = [float(j["score"]) for j in jobs if isinstance(j.get("score"), (int, float))]
    max_score = max(scores) if scores else None
    updated = ""
    for j in jobs:
        ts = str(j.get("collected_at") or "")
        if ts and (not updated or ts > updated):
            updated = ts
    return {
        "total": total,
        "companies": companies,
        "max_score": max_score,
        "top30": min(TOP_N, total),
        "updated": updated,
    }


# ---------------------------------------------------------------------------
# Pagina: CSS e JS embutidos (auto-contidos, zero dependencia externa).
# ---------------------------------------------------------------------------

_CSS = """
  :root { --bg:#f6f7f9; --card:#fff; --ink:#1c2733; --mut:#5c6b7a; --acc:#0b6bcb; --line:#e3e8ee; }
  * { box-sizing:border-box; }
  body { margin:0; font:16px/1.45 -apple-system,"Segoe UI",Roboto,Arial,sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:1180px; margin:0 auto; padding:24px 16px 64px; }
  h1 { font-size:1.35rem; margin:0 0 4px; }
  header p { color:var(--mut); margin:2px 0; font-size:.9rem; }
  .stats { display:flex; flex-wrap:wrap; gap:10px; margin:14px 0 4px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 14px; min-width:120px; }
  .stat b { display:block; font-size:1.05rem; font-variant-numeric:tabular-nums; }
  .stat span { font-size:.72rem; color:var(--mut); text-transform:uppercase; letter-spacing:.04em; }
  .meta { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0 6px; }
  .chip { background:#e8eef5; border-radius:999px; padding:3px 10px; font-size:.78rem; color:#33475b; }
  .toolbar { margin:14px 0 4px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  .toolbar select, .toolbar input, .toolbar button { font:inherit; font-size:.9rem; }
  input#q { flex:1 1 260px; max-width:430px; padding:8px 12px; border:1px solid var(--line); border-radius:8px; }
  input#f-min-score { width:110px; padding:8px 10px; border:1px solid var(--line); border-radius:8px; }
  select { padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:var(--card); }
  .fld { display:inline-flex; align-items:center; gap:6px; }
  .fld label { font-size:.78rem; color:var(--mut); }
  button#clear { padding:8px 12px; border:1px solid var(--line); border-radius:8px; background:var(--card); cursor:pointer; color:var(--mut); }
  button#clear:hover { color:var(--ink); }
  .hint { font-size:.8rem; color:var(--mut); }
  .wrap { overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--card); }
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { background:#eef2f7; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:var(--mut); position:sticky; top:0; z-index:1; }
  tbody tr:last-child td { border-bottom:0; }
  tbody tr:hover td { background:#f4f8fc; }
  tr.top30 td { background:#f0f7ff; }
  tr.top30:hover td { background:#e8f2fc; }
  td.score { font-variant-numeric:tabular-nums; font-weight:600; white-space:nowrap; width:64px; }
  a { color:var(--acc); text-decoration:none; }
  a:hover { text-decoration:underline; }
  .badge-top { display:inline-block; font-size:.66rem; font-weight:700; background:#0b6bcb; color:#fff; border-radius:999px; padding:1px 8px; margin-left:6px; vertical-align:20%; letter-spacing:.03em; }
  a.open { display:inline-block; white-space:nowrap; font-size:.78rem; border:1px solid var(--acc); color:var(--acc); border-radius:999px; padding:3px 10px; }
  a.open:hover { background:var(--acc); color:#fff; text-decoration:none; }
  details.why { margin-top:5px; }
  summary { cursor:pointer; color:var(--mut); font-size:.78rem; }
  .bd-body { margin:6px 0 2px; padding:8px 10px; background:#f6f9fc; border:1px solid var(--line); border-radius:8px; max-width:560px; display:grid; grid-template-columns:auto auto 1fr; gap:4px 12px; align-items:center; }
  .bd { display:contents; }
  .bd-l { font-size:.76rem; color:var(--mut); }
  .bd-v { font-size:.78rem; font-variant-numeric:tabular-nums; text-align:right; font-weight:600; }
  .bd-bar { background:#e3e8ee; border-radius:999px; height:6px; overflow:hidden; }
  .bd-bar i { display:block; height:100%; background:var(--acc); border-radius:999px; }
  .bd-bar i.bd-neg { background:#c0392b; }
  .bd-total { margin-top:6px; font-size:.78rem; color:#33475b; }
  .mut { color:var(--mut); }
  .loc { font-size:.85rem; color:#3d4c5c; }
  p.facts, p.desc { margin:6px 0 0; font-size:.82rem; color:#3d4c5c; max-width:680px; }
  footer { margin-top:18px; font-size:.75rem; color:var(--mut); }
  @media (max-width:760px) { th:nth-child(5),td:nth-child(5),th:nth-child(7),td:nth-child(7) { display:none; } }
"""

# Nucleo puro + cola DOM. O marcador ``/* ==== DOM glue`` separa o nucleo
# (funcoes testaveis em node) da cola que le o DOM — os testes extraem o
# texto ate o marcador e executam em node sem browser.
_JS = """
/* ==== nucleo puro (testes node extraem ate o marcador de DOM glue) ==== */
function if_cmp_num(a, b) { return (parseFloat(a) || 0) - (parseFloat(b) || 0); }
function if_cmp_str(a, b) {
  var x = String(a || '').toLowerCase(), y = String(b || '').toLowerCase();
  if (x < y) return -1;
  if (x > y) return 1;
  return 0;
}
function if_match(row, st) {
  if (!row) return false;
  var term = String(st.q || '').trim().toLowerCase();
  if (term) {
    var hay = ((row.title || '') + ' ' + (row.company || '') + ' ' + (row.location || '')).toLowerCase();
    if (hay.indexOf(term) === -1) return false;
  }
  if (st.company && row.company !== st.company) return false;
  if (st.location && row.location !== st.location) return false;
  if (st.type && row.type !== st.type) return false;
  if (st.country && row.country !== st.country) return false;
  var ms = parseFloat(st.minScore);
  if (!isNaN(ms)) {
    var sc = parseFloat(row.score);
    if (isNaN(sc) || sc < ms) return false;
  }
  return true;
}
function if_sorter(key) {
  var defaults = function (a, b) { return if_cmp_num(b.score, a.score) || if_cmp_str(a.title, b.title); };
  var tie = function (a, b) { return if_cmp_num(a.rank, b.rank); };
  switch (key) {
    case 'rank': return function (a, b) { return if_cmp_num(a.rank, b.rank); };
    case 'company': return function (a, b) { return if_cmp_str(a.company, b.company) || tie(a, b); };
    case 'title': return function (a, b) { return if_cmp_str(a.title, b.title) || tie(a, b); };
    case 'location': return function (a, b) { return if_cmp_str(a.location, b.location) || tie(a, b); };
    case 'date':
      return function (a, b) {
        var da = String(a.date || ''), db = String(b.date || '');
        if (!da && !db) return tie(a, b);
        if (!da) return 1;
        if (!db) return -1;
        if (da === db) return tie(a, b);
        return da > db ? -1 : 1;
      };
    case 'score': return function (a, b) { return if_cmp_num(a.score, b.score) || if_cmp_str(a.title, b.title); };
    case 'score-desc': return defaults;
  }
  return defaults;
}
function if_filter_sort(rows, st, sortKey) {
  return rows.filter(function (r) { return if_match(r, st); }).sort(if_sorter(sortKey));
}
/* ==== DOM glue (nao faz parte do nucleo puro) ==== */
(function () {
  'use strict';
  var body = document.querySelector('tbody');
  if (!body || !body.rows.length) return;
  var rows = Array.prototype.slice.call(body.querySelectorAll('tr'));
  var TOTAL = parseInt(document.body.getAttribute('data-total') || String(rows.length), 10);
  var data = rows.map(function (tr) {
    var d = tr.dataset;
    return { tr: tr, title: d.title, company: d.company, location: d.location,
             type: d.type, country: d.country, score: d.score,
             rank: d.rank, date: d.date };
  });
  var ids = ['q', 'f-company', 'f-location', 'f-type', 'f-country', 'f-min-score', 'sort', 'count', 'clear'];
  var els = {};
  ids.forEach(function (id) { els[id] = document.getElementById(id); });
  if (!els.sort || !els.count) return;

  function fill(selId, pick) {
    var sel = document.getElementById(selId);
    if (!sel) return;
    var seen = [];
    rows.forEach(function (tr) {
      var v = pick(tr.dataset);
      if (v && seen.indexOf(v) === -1) seen.push(v);
    });
    seen.sort(if_cmp_str);
    if (seen.length < 2) { var wrap = sel.closest('.fld'); if (wrap) wrap.style.display = 'none'; return; }
    seen.forEach(function (v) {
      var o = document.createElement('option');
      o.value = v;
      o.textContent = v;
      sel.appendChild(o);
    });
  }
  fill('f-company', function (d) { return d.company; });
  fill('f-location', function (d) { return d.location; });
  fill('f-type', function (d) { return d.type; });
  fill('f-country', function (d) { return d.country; });

  function state() {
    return {
      q: els.q ? els.q.value : '',
      company: els['f-company'] ? els['f-company'].value : '',
      location: els['f-location'] ? els['f-location'].value : '',
      type: els['f-type'] ? els['f-type'].value : '',
      country: els['f-country'] ? els['f-country'].value : '',
      minScore: els['f-min-score'] ? els['f-min-score'].value : ''
    };
  }
  function apply() {
    var out = if_filter_sort(data, state(), els.sort.value);
    var shown = 0;
    var visible = {};
    out.forEach(function (r) {
      r.tr.style.display = '';
      body.appendChild(r.tr);
      visible[r.tr] = true;
      shown++;
    });
    data.forEach(function (r) {
      if (!visible[r.tr]) r.tr.style.display = 'none';
    });
    els.count.textContent = shown + ' de ' + TOTAL + ' vagas';
  }
  function wire(id, evt) { if (els[id]) els[id].addEventListener(evt, apply); }
  wire('q', 'input');
  wire('f-min-score', 'input');
  wire('f-company', 'change');
  wire('f-location', 'change');
  wire('f-type', 'change');
  wire('f-country', 'change');
  wire('sort', 'change');
  if (els.clear) {
    els.clear.addEventListener('click', function () {
      if (els.q) els.q.value = '';
      if (els['f-min-score']) els['f-min-score'].value = '';
      ['f-company', 'f-location', 'f-type', 'f-country'].forEach(function (id) {
        if (els[id]) els[id].value = '';
      });
      apply();
    });
  }
  apply();
})();
"""


def render_html(
    jobs: list[dict],
    *,
    total: int,
    source_label: str,
    filters_desc: list[str],
    generated_at: str,
    stats: dict | None = None,
    top_n: int = TOP_N,
    rank_map: dict[str, int] | None = None,
) -> str:
    """Pagina auto-contida (CSS inline, JS vanilla inline, zero external).

    ``jobs`` sao as linhas exibidas (ja filtradas/cortadas pelo CLI); ``total``
    e o total do conjunto filtrado (usado no contador e no resumo). ``stats``
    e o resumo do topo (derivado do conjunto inteiro pelo ``main``); quando
    ausente, e derivado de ``jobs`` (uso direto/testes). ``rank_map`` mapeia
    id -> posicao no ranking do pipeline; sem ele, a posicao exibida e a
    posicao na lista passada (uso local/testes).
    """
    if stats is None:
        stats = _compute_stats(jobs, total=total)
    rows: list[str] = []
    for i, j in enumerate(jobs, 1):
        rank = i
        if rank_map is not None and j.get("id") is not None:
            rank = rank_map.get(str(j.get("id")), i)
        rows.append(_row_html(rank, j, top_n=top_n))
    rows_html = "\n".join(rows)
    order_note = (
        "ordem: score (ranking do pipeline)" if jobs and jobs[0].get("score") is not None
        else "ordem: mais recentes (last_seen)"
    )
    chips = ""
    if filters_desc:
        chips = '<div class="meta">' + "".join(
            f'<span class="chip">{html.escape(f)}</span>' for f in filters_desc
        ) + "</div>"
    shown = len(jobs)
    max_score_txt = _fmt_score(stats.get("max_score")) if stats.get("max_score") is not None else "—"
    updated = stats.get("updated") or generated_at
    updated_txt = str(updated)[:16].replace("T", " ")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Internship Finder — ranking de vagas elegíveis</title>
<style>
{_CSS}
</style>
</head>
<body data-total="{total}">
<main>
  <header>
    <h1>Internship Finder — ranking de vagas elegíveis</h1>
    <p>{html.escape(source_label)} · gerado em {html.escape(generated_at)} UTC · {html.escape(order_note)}</p>
  </header>
  <div class="stats">
    <div class="stat"><b>{stats.get("total", 0)}</b><span>vagas elegíveis</span></div>
    <div class="stat"><b>{stats.get("companies", 0)}</b><span>empresas</span></div>
    <div class="stat"><b>{max_score_txt}</b><span>score máx</span></div>
    <div class="stat"><b>{stats.get("top30", 0)}</b><span>no Top 30</span></div>
    <div class="stat"><b>{html.escape(updated_txt)}</b><span>dados atualizados</span></div>
  </div>
  {chips}
  <div class="toolbar">
    <input id="q" type="search" placeholder="Buscar por título, empresa ou local…">
    <input id="f-min-score" type="number" min="0" step="0.25" placeholder="score mín.">
    <select id="sort" title="Ordenação">
      <option value="score-desc">ordenar: score (padrão)</option>
      <option value="rank">posição no ranking</option>
      <option value="company">empresa (A→Z)</option>
      <option value="title">título (A→Z)</option>
      <option value="location">local (A→Z)</option>
      <option value="date">data (mais recentes)</option>
    </select>
    <span class="hint" id="count">{shown} de {total} vagas</span>
  </div>
  <div class="toolbar">
    <span class="fld"><label>empresa</label><select id="f-company"><option value="">todas</option></select></span>
    <span class="fld"><label>local</label><select id="f-location"><option value="">todos</option></select></span>
    <span class="fld"><label>tipo</label><select id="f-type"><option value="">todos</option></select></span>
    <span class="fld"><label>país</label><select id="f-country"><option value="">todos</option></select></span>
    <button type="button" id="clear">limpar filtros</button>
  </div>
  <div class="wrap">
  <table>
    <thead><tr><th>#</th><th>score</th><th>vaga</th><th>empresa</th><th>local</th><th>tipo</th><th>desde</th><th></th></tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
  </div>
  <footer>Filtros e ordenação são client-side (JS embutido, sem backend). O ranking, o score e o score_breakdown são os do pipeline — esta página não re-ranqueia nada. Filtros --company/--keyword/--country (se usados) já foram aplicados na geração.</footer>
</main>
<script>
{_JS}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Interface Fase 3: ranking completo com filtros/ordenação "
        "client-side e score explicável — gera HTML estático.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default=None,
        help="JSON ranqueado (default: data/eligible_jobs.json do CWD; se "
        "ausente, cai para o default de --db, data/jobs.db)",
    )
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="SQLite jobs.db (vagas ATIVAS, sem score, ordenadas por "
        "last_seen). Informe --input OU --db, nao ambos.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Maximo de vagas exibidas (default: 25; <= 0 -> erro; a "
        "publicacao em GitHub Pages usa um valor alto = todas)",
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Filtra por empresa (substring, sem diferenciar maiusculas)",
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help="Filtra por palavra no TITULO (substring, sem diferenciar maiusculas)",
    )
    parser.add_argument(
        "--country",
        default=None,
        help="Filtra por pais na spec do CLI: ISO alpha-2 em lista (ex.: "
        "'de,at,ch'), 'europe', 'remote' ou 'all' (default: sem filtro)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=f"Onde gravar o HTML (default: {DEFAULT_OUTPUT}; '-' = stdout)",
    )
    args = parser.parse_args(argv)

    if args.top <= 0:
        parser.error("--top deve ser > 0")

    # Spec de pais validada cedo (mesma regra do CLI --country, P2 #15).
    if args.country is not None:
        try:
            parse_country_spec(args.country)
        except ValueError as exc:
            parser.error(str(exc))

    if args.input and args.db:
        parser.error("informe apenas um: --input (JSON ranqueado) ou --db (SQLite)")

    input_path = Path(args.input) if args.input else None
    db_path = Path(args.db) if args.db else None

    # Default: arquivos de data/ do CWD, com fallback claro se ausentes.
    if input_path is None and db_path is None:
        candidate_json = Path("data/eligible_jobs.json")
        candidate_db = Path("data/jobs.db")
        if candidate_json.exists():
            input_path = candidate_json
        elif candidate_db.exists():
            db_path = candidate_db
        else:
            parser.error(
                "nada em data/: faltam data/eligible_jobs.json e data/jobs.db — "
                "colete antes (python -m internship_finder.cli --registry) ou "
                "passe --input/--db explicitos"
            )

    if input_path is not None:
        if not input_path.exists():
            parser.error(f"--input nao encontrado: {input_path}")
        jobs = load_json(input_path)
        source_label = f"{input_path} ({len(jobs)} vagas ranqueadas)"
        jobs = sort_ranked(jobs)
    else:
        if not db_path.exists():
            parser.error(f"--db nao encontrado: {db_path}")
        jobs = load_db(db_path)
        source_label = f"{db_path} ({len(jobs)} vagas ativas)"

    # Posicao no ranking do pipeline (independente de filtros do CLI): o mapa
    # e construido sobre a lista completa ordenada por score.
    rank_map = {}
    for i, j in enumerate(jobs, 1):
        if j.get("id") is not None:
            rank_map[str(j.get("id"))] = i

    filtered = apply_filters(
        jobs, company=args.company, keyword=args.keyword, country=args.country
    )
    top_jobs = filtered[: args.top]

    filters_desc: list[str] = []
    if args.company:
        filters_desc.append(f"empresa contem '{args.company}'")
    if args.keyword:
        filters_desc.append(f"palavra no titulo: '{args.keyword}'")
    if args.country:
        filters_desc.append(f"pais: {args.country}")

    page = render_html(
        top_jobs,
        total=len(filtered),
        source_label=source_label,
        filters_desc=filters_desc,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        stats=_compute_stats(filtered, total=len(filtered)),
        rank_map=rank_map,
    )

    out = "-" if args.output == "-" else Path(args.output or DEFAULT_OUTPUT)
    if out == "-":
        sys.stdout.write(page)
    else:
        out.write_text(page, encoding="utf-8")
        print(f"interface gerada: {out.resolve()} ({len(top_jobs)} de {len(filtered)} vagas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())