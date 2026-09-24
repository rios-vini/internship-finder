"""Interface do internship-finder: ranking completo, filtros e ordenacao (Fase 3 + 4 + 5 + 6).

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

Fase 4 (segundo perfil): o MESMO conjunto elegivel tambem e classificado pelo
perfil Materials Engineering (``materials_ranking.rank_materials_jobs`` — score
e breakdown proprios, independentes; o score do perfil principal nao muda). A
pagina ganha um seletor de perfil (abas) e UMA tabela por perfil, reusando a
mesma estrutura e o mesmo JS client-side (escopo por tabela ativa). Sem
``materials``, ``render_html`` produz EXATAMENTE a pagina da Fase 3 (compat
com testes/uso direto).

Fase 5 (camada PT-BR): titulo traduzido de forma DETERMINISTICA por glossario
(``ptbr.py`` — modulo novo) como campo SEPARADO ("PT-BR"), com o original
sempre visivel e rotulado ("Original (EN/DE)"); tipo do anuncio e pais em
portugues; o bloco "por que esta vaga?" explica em PT-BR cada componente REAL
do breakdown do perfil ativo (inclusive as penalidades). NAO traduz a
descricao, NAO usa LLM/API/servico externo e NAO altera ranking/score/filtros/
dedup — apenas apresenta melhor o resultado existente.

Fase 6 (Candidate Fit + Application Intelligence + mobile): por vaga, a pagina
mostra SINAIS DE CANDIDATURA (fit), work authorization, deadline classificada
(empregador vs. validade do feed SuccessFactors — regra documentada), possiveis
problemas objetivos, quality flags, readiness e freshness (first/last_seen do
SQLite via ``--db-join``); chips visiveis com deadline/idioma/visto/readiness;
secao "Como este ranking funciona" com os PESOS REAIS das constantes de
ranking.py/materials_ranking.py (nada duplicado); painel de filtros recolhivel
(deadline expirando, work auth, idioma, Top 30, quality flags + contador);
layout mobile em CARDS (tabela vira card <=760px, sem scroll horizontal);
``--ref-date`` fixa a urgencia (determinismo). Nenhum deadline e inventado e
nenhum sinal de visto/idioma e inferido sem evidencia (app_intel.py).

Fontes (os DOIS caminhos funcionam):

- ``--input``: JSON ranqueado (default ``data/eligible_jobs.json`` do CWD),
  saida direta do ``cli --rank`` — contem ``score``/``score_breakdown``.
- ``--db``: SQLite ``jobs.db`` (default como fallback ao JSON ausente) — le
  apenas vagas ATIVAS (``active=1``), sem score (o banco nao tem a coluna):
  ordena por ``last_seen`` desc.

Filtros na GERACAO (3 eixos, aplicados sobre a lista JA pronta):

- ``--company``: substring case-insensitive no campo empresa;
- ``--keyword``: substring case-insensitive no TITULO;
- ``--country``: mesma spec do CLI (reusa ``parse_country_spec``).

Filtros e ordenacao no BROWSER (vanilla JS, sem backend): cada vaga e embutida
como data-attributes na linha da tabela ATIVA (por perfil) e o JS filtra e
ordena sem recarregar — nucleo puro em ``if_filter_sort``/``if_match``/
``if_sorter`` (testado em node). Top 30 recebe badge discreto POR PERFIL; cada
vaga tem "por que este score" com a composicao real do breakdown do perfil
ativo; o botao/titulo leva direto ao anuncio (http/https validado, P2.3).

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

from internship_finder import app_intel  # noqa: E402  (Fase 6: Candidate Fit + Application Intelligence)
from internship_finder import opportunity_intel  # noqa: E402  (Fase 7: Company & Location Intelligence)
from internship_finder.countries import matches_country, parse_country_spec  # noqa: E402
from internship_finder.materials_ranking import rank_materials_jobs  # noqa: E402
from internship_finder import ptbr  # noqa: E402  (Fase 5: camada PT-BR deterministica)

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

# Rotulos PT-BR das componentes REAIS do score_breakdown do perfil principal
# (Fase 5: definidos na camada PT-BR — ptbr.py — junto com os explicadores).
_BREAKDOWN_LABELS = ptbr.BREAKDOWN_LABELS
_BREAKDOWN_ORDER = ptbr.BREAKDOWN_ORDER

# Rotulos das componentes REAIS do breakdown do perfil Materials Engineering
# (materials_ranking.py; nomeada ``materials_breakdown`` na vaga).
_MATERIALS_BREAKDOWN_LABELS = ptbr.MATERIALS_BREAKDOWN_LABELS
_MATERIALS_BREAKDOWN_ORDER = ptbr.MATERIALS_BREAKDOWN_ORDER

# Rotulos dos botoes do seletor de perfil (Fase 4).
PROFILE_LABELS = {
    "biz": "Procurement / Supply Chain",
    "mat": "Materials Engineering",
}


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


def _breakdown_items(
    job: dict, *, breakdown_key: str, order: tuple[str, ...],
) -> list[tuple[str, str, float]]:
    """Componentes reais do breakdown: (label, chave, valor)."""
    b = job.get(breakdown_key) or {}
    if not isinstance(b, dict):
        return []
    out: list[tuple[str, str, float]] = []
    labels = _MATERIALS_BREAKDOWN_LABELS if breakdown_key == "materials_breakdown" \
        else _BREAKDOWN_LABELS
    for key in order:
        if key not in b:
            continue
        try:
            val = float(b[key])
        except (TypeError, ValueError):
            continue
        out.append((labels.get(key, key), key, val))
    return out


def _breakdown_html(job: dict, *, breakdown_key: str, order: tuple[str, ...]) -> str:
    """Bloco 'por que esta vaga': componentes reais, explicados em PT-BR.

    Cada componente do breakdown REAL vira uma linha com rotulo PT-BR, o
    valor REAL (com sinal) e uma barra proporcional (barra = |valor| relativo
    ao maior |valor| da propria vaga — visual so; os numeros sao os
    componentes reais, sem nenhuma conta nova). Abaixo de cada linha, um
    detalhe fixo explica o que a componente mede (Fase 5 — novo). Quando
    existem componentes NEGATIVAS, um cabecalho "o que reduziu a nota" as
    separa (as penalidades REAIS do breakdown; nenhuma penalidade e criada).
    """
    items = _breakdown_items(job, breakdown_key=breakdown_key, order=order)
    if not items:
        return ""
    profile = "biz" if breakdown_key == "score_breakdown" else "mat"
    explains = ptbr.BREAKDOWN_EXPLAIN if profile == "biz" \
        else ptbr.MATERIALS_BREAKDOWN_EXPLAIN
    maxv = max((abs(v) for _, _, v in items), default=0.0)
    rows = ""
    started_neg = False
    for label, key, val in items:
        if val < 0 and not started_neg:
            rows += (
                '<div class="bd-pen">'
                "o que reduziu a nota (penalidades reais do breakdown)"
                "</div>"
            )
            started_neg = True
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
        detail = explains.get(key, "")
        if detail:
            rows += (
                '<div class="bd-x">'
                f"{html.escape(detail)}"
                "</div>"
            )
    total_key = "score" if breakdown_key == "score_breakdown" else \
        breakdown_key.replace("_breakdown", "_score")
    total = job.get(total_key)
    total_txt = f"Total <b>{_fmt_score(total)}</b>" if total is not None else "Total —"
    return f'<div class="bd-body">{rows}<div class="bd-total">{total_txt}</div></div>'


def _details_html(
    job: dict, *, breakdown_key: str, order: tuple[str, ...],
) -> str:
    """Detalhes compactos da vaga (fora da tabela, dentro do <details>).

    Extras factuais do proprio registro (nada inferido): tipo do anuncio
    (rotulo PT-BR quando mapeado — Fase 5), pais em PT-BR, estagio/remoto,
    deadline, "desde" e um trecho curto da descricao ORIGINAL (sem traducao
    automatica; o original permanece e o link do anuncio abre a fonte).
    """
    parts: list[str] = []
    if job.get("employment_type"):
        raw_type = str(job["employment_type"])
        pt_type = ptbr.employment_type_pt(raw_type)
        if pt_type and pt_type.upper() != raw_type.upper():
            parts.append(f"tipo do anúncio: {html.escape(pt_type)} ({html.escape(raw_type)})")
        else:
            parts.append(f"tipo do anúncio: {html.escape(raw_type)}")
    if _fmt_bool(job.get("internship")):
        parts.append("estágio")
    if _fmt_bool(job.get("remote")):
        parts.append("remoto")
    pais = ptbr.country_label(job.get("country_iso"))
    if pais and pais != str(job.get("country_iso") or ""):
        parts.append(f"país: {html.escape(pais)}")
    # Fase 6: deadline classificado pela fonte — valor do empregador vira
    # "candidaturas até"; o valor SuccessFactors e validade do feed da
    # plataforma (fonte) e nao pode ser apresentado como prazo de candidatura.
    # Item 8: prazo textual (Bewerbungsfrist) vira "candidaturas até" com a
    # data do TEXTO (deadline_date já devolve a data classificada).
    deadline_kind_ = app_intel.deadline_kind(job)
    if deadline_kind_ in ("employer", "employer_textual"):
        dl = app_intel.deadline_date(job)
        if dl is not None:
            parts.append(f"candidaturas até {dl.strftime('%d.%m.%Y')}")
    elif deadline_kind_ == "platform_sf" and job.get("application_deadline"):
        parts.append(f"validade do anúncio na fonte: {_fmt_date(job['application_deadline'])}")
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
        desc_snippet = (
            '<p class="mut desc"><span class="tag tag-orig">Original</span> '
            f'<span class="desc-orig">{html.escape(text)}</span></p>'
        )
    # Fase 8 — hint do personal tracker: aponta o comando do tracker com o
    # id CANONICO da vaga (Job.id). Zero dado pessoal aqui (o estado privado
    # mora no banco local); e apenas o caminho para a acao no terminal.
    tracker_id = _attr(str(job.get("id") or ""))
    tracker_hint = (
        '<p class="mut tracker-hint">Acompanhar esta vaga (shortlist, '
        'candidatura, notas — dados privados no VPS): '
        f'<code>scripts/personal_tracker.py mark {tracker_id} '
        '--status interesting</code></p>'
    ) if tracker_id else ""
    return (
        "<details class=\"why\">"
        "<summary>por que esta vaga? (score e penalidades)</summary>"
        f"{_breakdown_html(job, breakdown_key=breakdown_key, order=order)}"
        f"{extras}"
        f"{desc_snippet}"
        f"{tracker_hint}"
        "</details>"
    )


def _added_date(job: dict) -> str:
    """Data exibida na coluna 'desde' (primeira data confiavel do registro)."""
    return _fmt_date(job.get("first_seen") or job.get("posted_at")
                     or job.get("collected_at"))


# ---------------------------------------------------------------------------
# Fase 6 — Application Intelligence (candidatura) por vaga
# ---------------------------------------------------------------------------

_MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez"]


def _fmt_dmy(value) -> str:
    """'2026-09-24T00:00:00'/'2026-09-24' -> '24 set 2026' (PT-BR, ISO-safe)."""
    text = str(value or "")[:10]
    try:
        y, m, d = text.split("-")
        return f"{int(d):02d} {_MONTHS_PT[int(m)-1]} {y}"
    except (ValueError, IndexError):
        return text


def _job_intel(job: dict, ref: date) -> dict:
    """Intel de candidatura de uma vaga (Fase 6) — numero/significado real.

    Tudo derivado de ``app_intel`` (evidencias no anuncio/campos da fonte):
    nivel de alemao, evidencia de ingles, estado de work authorization,
    deadline classificado (employer/platform_sf/none), urgencia e dias
    restantes, problemas objetivos, quality flags e readiness. Nenhum valor
    e inventado; ``None``/ausencia nunca vira numero.
    """
    text = f"{job.get('title') or ''} {job.get('description') or ''}"
    de = app_intel.german_level(text)
    kind = app_intel.deadline_kind(job)
    dl = app_intel.deadline_date(job)
    days = app_intel.days_until(dl, ref) if dl is not None else None
    problems = app_intel.possible_problems(job, ref)
    return {
        "de": de.level if de else "none",
        "en": app_intel.english_evidence(text),
        "wa": app_intel.work_authorization(text)["state"],
        "kind": kind,
        "dl": dl.isoformat() if dl is not None else None,
        "days": days,
        "urgency": app_intel.urgency_color(days) if kind in ("employer", "employer_textual") else None,
        "problems": problems,
        "flags": app_intel.quality_flags(job, ref),
        "ready": app_intel.application_readiness(problems),
    }


_WA_EMOJI = {
    "support": "🟢", "existing_required": "🔴", "no_sponsorship": "🔴",
    "unclear": "🟡", "not_mentioned": "🟡",
}
_WA_CHIP = {
    "support": "visto: suporte", "existing_required": "visto: autorização req.",
    "no_sponsorship": "visto: sem sponsorship", "unclear": "visto: incerto",
    "not_mentioned": "visto: não mencionado",
}
_URGENCY_EMOJI = {"green": "🟢", "yellow": "🟡", "orange": "🟠", "red": "🔴"}


def _chips_html(intel: dict) -> str:
    """Chips compactos SEMPRE visiveis (deadline, idioma, visa, readiness).

    Apenas sinais reais: deadline EMPLOYER (o valor de feed do SuccessFactors
    NAO aparece como deadline — cf. regra documentada), evidencia de ingles,
    exigencia/preferencia de alemao, estado de work authorization e readiness.
    """
    parts: list[str] = []
    if intel["kind"] in ("employer", "employer_textual") and intel["dl"]:
        color = intel["urgency"] or "green"
        emoji = _URGENCY_EMOJI.get(color, "🟢")
        days_txt = f" · {intel['days']} d" if intel["days"] is not None else ""
        parts.append(
            f'<span class="chip c-{color}">{emoji} candidaturas: '
            f'{_fmt_dmy(intel["dl"])}{days_txt}</span>'
        )
    if intel["de"] == "required":
        parts.append('<span class="chip c-bad">🇩🇪 alemão exigido</span>')
    elif intel["de"] == "preferred":
        parts.append('<span class="chip c-warn">🇩🇪 alemão preferido</span>')
    if intel["en"]:
        parts.append('<span class="chip c-en">🇬🇧 inglês</span>')
    parts.append(
        f'<span class="chip c-wa">{_WA_EMOJI.get(intel["wa"], "🟡")} '
        f'{_WA_CHIP.get(intel["wa"], intel["wa"])}</span>'
    )
    if intel["ready"] == "ready":
        parts.append('<span class="chip c-good">✅ pronta p/ revisar</span>')
    else:
        parts.append('<span class="chip c-warn">⚠️ verificar antes</span>')
    return '<div class="chips">' + " ".join(parts) + "</div>"


def _fit_lines_html(job: dict) -> str:
    """Candidate fit: sinais objetivos (app_intel.candidate_fit), PT-BR."""
    lines: list[str] = []
    for s in app_intel.candidate_fit(job):
        label = ptbr.FIT_LABELS.get(s["key"], s["key"])
        if s["key"] == "german" and s.get("detail"):
            label += f': {ptbr.GERMAN_LEVEL_LABELS.get(s["detail"], s["detail"])}'
        if s["key"] == "work_auth" and s.get("detail"):
            label += f': {ptbr.WORK_AUTH_LABELS.get(s["detail"], s["detail"])}'
        icon = {"ok": "✓", "warn": "⚠", "info": "·"}.get(s["kind"], "·")
        lines.append(
            f'<div class="fit-line fit-{s["kind"]}">'
            f"<span class=\"fit-icon\">{icon}</span> {html.escape(label)}</div>"
        )
    return '<div class="fit">' + "".join(lines) + "</div>"


def _problems_html(intel: dict) -> str:
    """Possiveis problemas (apenas com evidencia) + quality flags."""
    block: list[str] = []
    probs = []
    for p in intel["problems"]:
        tpl = ptbr.PROBLEM_TEXTS.get(p["key"], p["key"])
        arg = p.get("detail") or ""
        if p["key"] == "deadline" and "|" in str(arg):
            dl, days = str(arg).split("|", 1)
            arg = f"{_fmt_dmy(dl)}"
            if days not in ("None", ""):
                arg += f" ({days} dias)"
        if p["key"] == "sf_validity_passed" and "|" in str(arg):
            dl, days = str(arg).split("|", 1)
            arg = _fmt_dmy(dl)
        probs.append(f'<div class="prob">{html.escape(tpl.format(arg=arg))}</div>')
    if probs:
        block.append(
            '<div class="sec"><span class="sec-t">Possíveis problemas</span>'
            + "".join(probs) + "</div>"
        )
    flags = []
    for f in intel["flags"]:
        tpl = ptbr.QUALITY_TEXTS.get(f["key"], f["key"])
        arg = f.get("detail") or ""
        flags.append(f'<div class="flag">{html.escape(tpl.format(arg=arg))}</div>')
    if flags:
        block.append(
            '<div class="sec"><span class="sec-t">Quality flags (dados)</span>'
            + "".join(flags) + "</div>"
        )
    return "".join(block)


def _wa_line_html(intel: dict) -> str:
    """Work authorization — estado com emoji (spec 3)."""
    emoji = _WA_EMOJI.get(intel["wa"], "🟡")
    label = ptbr.WORK_AUTH_LABELS.get(intel["wa"], intel["wa"])
    return (
        f'<div class="wa"><span class="fit-icon">{emoji}</span> '
        f"Work authorization — {html.escape(label)}</div>"
    )


def _deadline_line_html(intel: dict) -> str:
    """Deadline de primeira classe; nunca inventada (spec 4/5)."""
    if intel["kind"] in ("employer", "employer_textual") and intel["dl"]:
        color = intel["urgency"] or "green"
        emoji = _URGENCY_EMOJI.get(color, "🟢")
        days_txt = (
            f" · {intel['days']} dias restantes"
            if intel["days"] is not None and intel["days"] >= 0
            else (" · vencida" if intel["days"] is not None else "")
        )
        return (
            f'<div class="wa"><span class="fit-icon">{emoji}</span> '
            f"Deadline: {_fmt_dmy(intel['dl'])}{days_txt} "
            f"<span class=\"mut small\">({ptbr.DEADLINE_KIND_LABELS[intel['kind']]})</span></div>"
        )
    if intel["kind"] == "platform_sf" and intel["dl"]:
        return (
            f'<div class="wa"><span class="fit-icon">🗓️</span> '
            f"Validade do anúncio (fonte): {_fmt_dmy(intel['dl'])} — "
            f"{ptbr.DEADLINE_KIND_LABELS['platform_sf']}</div>"
        )
    return (
        '<div class="wa"><span class="fit-icon">🟡</span> '
        f"Deadline: {ptbr.DEADLINE_KIND_LABELS['none']} "
        "<span class=\"mut small\">(nenhuma data inventada)</span></div>"
    )


def _freshness_html(job: dict) -> str:
    """Freshness: Published / First seen / Last seen (nunca inventa)."""
    parts: list[str] = []
    if job.get("posted_at"):
        parts.append(f"Publicada: {_fmt_dmy(job['posted_at'])}")
    if job.get("first_seen"):
        parts.append(f"Primeira vista: {_fmt_date(job['first_seen'])}")
    if job.get("last_seen"):
        parts.append(f"Última vista: {_fmt_date(job['last_seen'])}")
    if not parts:
        return ""
    return (
        '<div class="sec"><span class="sec-t">Freshness</span><div class="fresh">'
        + " · ".join(html.escape(p) for p in parts)
        + "</div></div>"
    )


# ---------------------------------------------------------------------------
# Fase 7 — Opportunity Intelligence (Company & Location Intelligence)
# ---------------------------------------------------------------------------


def _job_opportunity(job: dict, company_intel_map: dict, loc_map: dict) -> dict:
    """Intel de oportunidade de UMA vaga (Fase 7) — numero/significado real.

    Empresa/custo de vida vem dos arquivos curados (fonte+data); salario,
    modalidade, duracao e cidade vem de EVIDENCIA no proprio anuncio;
    turnover/pathway da entrada curada (nunca estimados).
    """
    entry = opportunity_intel.company_intel_for(job, company_intel_map)
    loc = opportunity_intel.city_and_region(job)
    col = opportunity_intel.cost_of_living(loc.get("city"), loc_map)
    return {
        "company": entry,
        "salary": opportunity_intel.job_salary(job),
        "mode": opportunity_intel.work_mode(job),
        "duration": opportunity_intel.job_duration(job),
        "city": loc.get("city"),
        "region": loc.get("region"),
        "country": loc.get("country"),
        "col": col,
        "pathway": opportunity_intel.pathway_state(entry),
        "pathway_pct": opportunity_intel.pathway_percentage(entry),
        "turnover": opportunity_intel.turnover_summary(entry),
    }


def _opp_map_for(
    jobs: list[dict], materials: list[dict] | None,
    company_intel_map: dict, loc_map: dict,
) -> dict:
    """Opportunity intel UMA vez por vaga (id), reusado nas duas tabelas."""
    out: dict[str, dict] = {}
    for j in list(jobs) + list(materials or []):
        jid = str(j.get("id") or "")
        if jid and jid not in out:
            out[jid] = _job_opportunity(j, company_intel_map, loc_map)
    return out


def _source_list(field_sources: list | None, fallback_text: str | None) -> str:
    """Lista de fontes de um campo (URL valida) ou texto-fallback."""
    if not field_sources:
        return ""
    rows: list[str] = []
    for s in field_sources:
        if not isinstance(s, dict):
            continue
        text = str(s.get("text") or s.get("source") or "")
        url = _safe_url(s.get("url") or s.get("href"))
        checked = str(s.get("checked") or "")
        quality = str(s.get("quality") or "")
        label = html.escape(text) if text else ""
        if url:
            label = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{label or "fonte"}</a>'
        meta = " · ".join(x for x in (quality and ptbr.SOURCE_QUALITY_LABELS.get(quality, quality),
                                      f"verificado em {_fmt_dmy(checked)}" if checked else "") if x)
        rows.append(f'<div class="src">{label} <span class="mut small">{html.escape(meta)}</span></div>' if meta else f'<div class="src">{label}</div>')
    return "<div class=\"srcs\">" + "".join(rows) + "</div>"


def _company_section(opp: dict, entry: dict) -> str:
    """Secao Empresa: dados estruturais da entrada curada (com fontes)."""
    rows: list[str] = []
    for key, label in (("industry", "Setor"), ("size", "Porte"),
                       ("hq", "Sede"), ("international", "Presença internacional"),
                       ("business_areas", "Principais áreas de atuação")):
        value = entry.get(key)
        if value is None or (isinstance(value, (list, dict)) and not value):
            continue
        text = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        rows.append(f'<div class="opp-row"><span class="opp-k">{label}</span>'
                    f'<span class="opp-v">{html.escape(text)}</span></div>')
    out = "".join(rows)
    if not out:
        return ""
    website = _safe_url(entry.get("website"))
    careers = _safe_url(entry.get("careers_url"))
    links = []
    if website:
        links.append(f'<a href="{html.escape(website)}" target="_blank" rel="noopener">site oficial</a>')
    if careers:
        links.append(f'<a href="{html.escape(careers)}" target="_blank" rel="noopener">página de carreiras</a>')
    if links:
        out += '<div class="opp-row"><span class="opp-k">Links</span><span class="opp-v">' \
            + " · ".join(links) + "</span></div>"
    checked = entry.get("checked") or entry.get("refreshed_at")
    note = f'<p class="mut small">Dados de empresa — verificado em {_fmt_dmy(checked)}' \
        if checked else '<p class="mut small">Dados de empresa'
    note += " — informações podem envelhecer; confira a fonte para decisões importantes.</p>"
    return out + note


def _benefits_section(entry: dict) -> str:
    """Beneficios: SO com fonte na entrada curada; senao 'Not mentioned'."""
    benefits = entry.get("benefits") if entry else None
    if not isinstance(benefits, list) or not benefits:
        return '<div class="opp-row opp-em"><span class="opp-v">Not mentioned</span></div>'
    items = ""
    for b in benefits:
        if isinstance(b, str):
            items += f'<div class="opp-row"><span class="opp-v">✓ {html.escape(b)}</span></div>'
        elif isinstance(b, dict) and b.get("name"):
            items += f'<div class="opp-row"><span class="opp-v">✓ {html.escape(str(b["name"]))}</span></div>'
    srcs = _source_list(entry.get("sources_for", {}).get("benefits") or entry.get("sources"), None)
    return (f'<div class="opp-row opp-em"><span class="opp-v">Benefícios com fonte (não '
            f'presumidos por serem comuns):</span></div>{items}{srcs}')


def _career_section(entry: dict) -> str:
    """Carreira/desenvolvimento: evidencias explicitas com fonte."""
    career = entry.get("career_development") if entry else None
    if not isinstance(career, list) or not career:
        return '<div class="opp-row opp-em"><span class="opp-v">Not mentioned</span></div>'
    items = ""
    for c in career:
        if isinstance(c, str):
            items += f'<div class="opp-row"><span class="opp-v">• {html.escape(c)}</span></div>'
        elif isinstance(c, dict) and c.get("text"):
            items += f'<div class="opp-row"><span class="opp-v">• {html.escape(str(c["text"]))}</span></div>'
    srcs = _source_list(entry.get("sources_for", {}).get("career") or entry.get("sources"), None)
    return items + srcs if items else '<div class="opp-row opp-em"><span class="opp-v">Not mentioned</span></div>'


def _pathway_section(opp: dict) -> str:
    """Internship -> Full-time: estado curado; percentual so como dado factual."""
    label = ptbr.PATHWAY_LABELS.get(opp["pathway"], opp["pathway"])
    if opp["pathway"] == "unknown":
        return '<div class="opp-row opp-em"><span class="opp-v">Not disclosed</span></div>'
    rows = f'<div class="opp-row"><span class="opp-k">Caminho declarado</span>' \
           f'<span class="opp-v">{html.escape(label)}</span></div>'
    pct = opp.get("pathway_pct")
    if pct:
        rows += f'<div class="opp-row"><span class="opp-k">Dado oficial</span>' \
                f'<span class="opp-v">{html.escape(str(pct.get("value")))} ' \
                f'— {html.escape(str(pct.get("text") or ""))}</span></div>'
    return rows


def _location_section(opp: dict, job: dict) -> str:
    """Localizacao: cidade/regiao/pais reais + custo de vida contextual."""
    rows: list[str] = []
    if opp["city"]:
        rows.append(f'<div class="opp-row"><span class="opp-k">Cidade</span>'
                    f'<span class="opp-v">{html.escape(opp["city"])}</span></div>')
    if opp["region"]:
        rows.append(f'<div class="opp-row"><span class="opp-k">Região</span>'
                    f'<span class="opp-v">{html.escape(opp["region"])}</span></div>')
    pais = ptbr.country_label(opp["country"]) or opp["country"]
    if pais:
        rows.append(f'<div class="opp-row"><span class="opp-k">País</span>'
                    f'<span class="opp-v">{html.escape(pais)}</span></div>')
    rows.append(f'<div class="opp-row"><span class="opp-k">Work mode</span>'
                f'<span class="opp-v">{html.escape(ptbr.WORK_MODE_LABELS.get(opp["mode"], opp["mode"]))}</span></div>')
    col = opp.get("col")
    if col:
        estim = str(col.get("estimate_monthly") or "")
        rent = str(col.get("rent_1br_center") or "")
        transport = str(col.get("transport_monthly") or "")
        for label, value in (("Custo de vida (estim. mensal, sem aluguel)", estim),
                             ("Aluguel 1 quarto (centro)", rent),
                             ("Transporte público mensal", transport)):
            if value:
                rows.append(f'<div class="opp-row"><span class="opp-k">{label}</span>'
                            f'<span class="opp-v">{html.escape(value)}</span></div>')
        src = col.get("source") or {}
        src_name = src.get("name") if isinstance(src, dict) else col.get("source_name")
        src_url = _safe_url(src.get("url") if isinstance(src, dict) else col.get("source_url"))
        checked = col.get("checked")
        caveat = f'<p class="mut small">Estimativa aproximada — {html.escape(str(src_name or "fonte"))}'
        if src_url:
            caveat += f' (<a href="{html.escape(src_url)}" target="_blank" rel="noopener">fonte</a>)'
        caveat += f', verificada em {_fmt_dmy(checked)}. Valores são contexto, não verdade absoluta'
        if isinstance(col, dict) and col.get("period"):
            caveat += f" — referente a {html.escape(str(col['period']))}"
        caveat += ".</p>"
        rows.append(caveat)
    else:
        rows.append('<div class="opp-row opp-em"><span class="opp-v">Custo de vida — '
                    'Not available (cidade sem dados curados confiáveis)</span></div>')
    return "".join(rows)


def _salary_section(opp: dict) -> str:
    """Salario: apresentado SOMENTE quando citado no anuncio."""
    salary = opp.get("salary")
    if not salary:
        return '<div class="opp-row opp-em"><span class="opp-v">Salary — Not disclosed '
        '(não citado no anúncio; nenhum valor é inventado)</span></div>'

    def euro(v: float) -> str:
        return f"{v:,.0f}".replace(",", ".")

    period = ptbr.SALARY_PERIOD_LABELS.get(salary["period"], salary["period"])
    if salary["min"] == salary["max"]:
        value = f"€{euro(salary['min'])}"
        if period:
            value = f"{value} / {period}"
    else:
        value = f"€{euro(salary['min'])}–€{euro(salary['max'])}"
        if period:
            value = f"{value} / {period}"
    return (f'<div class="opp-row"><span class="opp-k">Salary</span>'
            f'<span class="opp-v">{html.escape(value)}</span></div>'
            '<div class="opp-row opp-em"><span class="opp-v mut small">Source: job posting — citação '
            f'exata: “{html.escape(salary["text"])}”</span></div>')


def _turnover_section(opp: dict) -> str:
    """Turnover: fato registrado COM fonte; nunca vira avaliacao."""
    t = opp.get("turnover")
    if not t:
        return '<div class="opp-row opp-em"><span class="opp-v">Employee turnover — Not available '
        '(sem fonte pública confiável; nenhum dado é inferido)</span></div>'
    rows = f'<div class="opp-row"><span class="opp-k">Dado</span>' \
           f'<span class="opp-v">{html.escape(str(t.get("detail") or ""))}</span></div>'
    if t.get("period"):
        rows += f'<div class="opp-row"><span class="opp-k">Período</span>' \
                f'<span class="opp-v">{html.escape(str(t["period"]))}</span></div>'
    note = ('<p class="mut small">Turnover/layoffs são fatos registrados com fonte e período — '
            'não são usados como avaliação de qualidade da empresa nem do estágio.</p>')
    return rows + note + _source_list([t], '"')


def _sources_section(entry: dict) -> str:
    """Fontes gerais da entrada curada (enunciado: fonte+URL+data+qualidade)."""
    srcs = entry.get("sources") if entry else None
    if not isinstance(srcs, list) or not srcs:
        return '<div class="opp-row opp-em"><span class="opp-v">Not available</span></div>'
    rows = ""
    for s in srcs:
        if not isinstance(s, dict):
            continue
        text = str(s.get("text") or s.get("source") or "")
        url = _safe_url(s.get("url"))
        label = html.escape(text) if text else "fonte"
        if url:
            label = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{label}</a>'
        parts = [label]
        if s.get("quality"):
            parts.append(html.escape(ptbr.SOURCE_QUALITY_LABELS.get(str(s["quality"]), str(s["quality"]))))
        if s.get("checked"):
            parts.append(f"checado em {html.escape(_fmt_dmy(s['checked']))}")
        if s.get("period"):
            parts.append(f"período: {html.escape(str(s['period']))}")
        rows += f'<div class="src">{" · ".join(parts)}</div>'
    return rows or '<div class="opp-row opp-em"><span class="opp-v">Not available</span></div>'


def _opportunity_html(job: dict, opp: dict) -> str:
    """Bloco recolhivel 'Oportunidade' (Company & Location Intelligence).

    Secoes: Empresa / Benefícios / Carreira / Internship→Full-time /
    Localização / Salário / Turnover / Fontes. Tudo fechado por padrão
    (mobile: abre so o que o usuario quer); nenhum score geral de empresa.
    """
    entry = opp.get("company") or {}
    sections = [
        ("Empresa", _company_section(opp, entry)),
        ("Benefícios", _benefits_section(entry)),
        ("Carreira e desenvolvimento", _career_section(entry)),
        ("Internship → Full-time", _pathway_section(opp)),
        ("Localização", _location_section(opp, job)),
        ("Salário", _salary_section(opp)),
        ("Turnover / força de trabalho", _turnover_section(opp)),
        ("Fontes", _sources_section(entry)),
    ]
    body = ""
    for title, content in sections:
        if not content:
            content = '<div class="opp-row opp-em"><span class="opp-v">Not available</span></div>'
        body += (f'<div class="opp-sec"><span class="opp-sec-t">{title}</span>'
                 f'<div class="opp-sec-body">{content}</div></div>')
    chips = []
    if opp.get("salary"):
        chips.append('<span class="chip c-good">💰 salário citado</span>')
    if opp["mode"] in ("hybrid", "remote"):
        chips.append(f'<span class="chip c-{"hybrid" if opp["mode"]=="hybrid" else "good"}">'
                     f'{ptbr.WORK_MODE_LABELS[opp["mode"]]}</span>')
    if entry:
        chips.append('<span class="chip c-en">🏢 empresa: dados c/ fonte</span>')
    chips_html = ('<div class="chips">' + " ".join(chips) + "</div>") if chips else ""
    return f'<details class="opp"><summary>Oportunidade — empresa, localização e desempate</summary>{chips_html}{body}</details>'


def _compare_cell(value: str, tone: str = "") -> str:
    """Celula da tabela de comparacao (dado so; tone = pista visual)."""
    cls = f' class="cmp-{tone}"' if tone else ""
    return f'<td{cls}>{value}</td>'


def _intel_html(job: dict, intel: dict) -> str:
    """Bloco recolhível 'sinais de candidatura e possíveis problemas'."""
    n_prob = len(intel["problems"])
    summary = "sinais de candidatura e possíveis problemas"
    if n_prob:
        summary = f"⚠ sinais de candidatura e possíveis problemas ({n_prob})"
    ready = ptbr.READINESS_LABELS.get(intel["ready"], intel["ready"])
    icon = "✅" if intel["ready"] == "ready" else "⚠️"
    readiness_line = (
        f'<div class="sec"><span class="sec-t">Application readiness</span>'
        f'<div class="fit-line fit-{"ok" if intel["ready"] == "ready" else "warn"}">'
        f"<span class=\"fit-icon\">{icon}</span> {html.escape(ready)} "
        '<span class="mut small">(sinais objetivos do anúncio — não é '
        "garantia de contratação)</span></div></div>"
    )
    return (
        f"<details class=\"intel\"><summary>{summary}</summary>"
        f'{_fit_lines_html(job)}'
        f"{_wa_line_html(intel)}"
        f"{_deadline_line_html(intel)}"
        f"{_problems_html(intel)}"
        f"{readiness_line}"
        f"{_freshness_html(job)}"
        "</details>"
    )


def _how_section() -> str:
    """'Como este ranking funciona' — pesos/regras das CONSTANTES VIVAS.

    Nada duplicado manualmente: cada numero vem do modulo de ranking do
    perfil (ranking.py / materials_ranking.py); a seção alterna por perfil
    via [data-sv] (mesmo mecanismo do seletor de perfil).
    """
    from internship_finder import materials_ranking as mr
    from internship_finder import ranking as rk

    biz_crit = [
        ("área no título (por sinal)", rk.WEIGHT_AREA_TITLE),
        ("competências na descrição (por termo)", rk.WEIGHT_SKILL),
        ("inglês evidenciado no anúncio", rk.WEIGHT_LANG_EN),
        ("tipo de vaga estudantil no título", rk.WEIGHT_TYPE_TITLE),
        ("Alemanha explícita (ISO)", rk.WEIGHT_DE_EXPLICIT),
        ("Berlin (capital)", rk.WEIGHT_DE_CAPITAL),
    ]
    biz_pen = [
        ("alemão exigido (detectado no texto)", rk.PENALTY_LANG_DE_REQUIRED),
        ("alemão preferido (detectado no texto)", rk.PENALTY_LANG_DE_PREFERRED),
        ("senior/director/head no título (sem marcador de estudante)", rk.PENALTY_SENIOR),
        ("manager no título (sem marcador de estudante)", rk.PENALTY_MANAGER),
        ("employment_type FULL_TIME", rk.PENALTY_FULL_TIME),
    ]
    mat_crit = [
        ("materiais no título (por termo)", mr.WEIGHT_MATERIALS_TITLE),
        ("materiais na descrição (corroboração, máx. 1x)", mr.WEIGHT_MATERIALS_DESC),
        ("adjacentes no título (por termo)", mr.WEIGHT_ADJACENT_TITLE),
        ("adjacentes na descrição (corroboração)", mr.WEIGHT_ADJACENT_DESC),
        ("contexto quality/R&D no título (gate técnico)", mr.WEIGHT_CONTEXT_TITLE),
        ("contexto na descrição (corroboração)", mr.WEIGHT_CONTEXT_DESC),
        ("tipo de vaga estudantil no título", mr.WEIGHT_TYPE_TITLE),
        ("Alemanha explícita (ISO)", mr.WEIGHT_DE_EXPLICIT),
        ("Berlin (capital)", mr.WEIGHT_DE_CAPITAL),
    ]
    mat_pen = [
        ("função comercial no título (compras/SCM)", mr.PENALTY_PROCUREMENT),
        ("outras funções não-materiais no título", mr.PENALTY_OTHER_FUNCTION),
    ]

    def crit_rows(rows: list[tuple[str, float]]) -> str:
        return "".join(
            f'<div class="w-row"><span>{html.escape(label)}</span>'
            f'<b>+{value:g}</b></div>'
            for label, value in rows if value > 0
        )

    def pen_rows(rows: list[tuple[str, float]]) -> str:
        return "".join(
            f'<div class="w-row"><span>{html.escape(label)}</span>'
            f'<b>{value:g}</b></div>'
            for label, value in rows if value != 0
        )

    biz_rules = (
        "<li><b>Idioma:</b> inglês mencionado no anúncio é sinal positivo "
        f"(+{rk.WEIGHT_LANG_EN:g}); alemão é avaliado pela EXIGÊNCIA "
        "detectada no texto (exigido/preferido/plus/sem menção) — o idioma "
        "em que o anúncio foi escrito nunca é requisito e ''conter alemão'' "
        "não bonifica.</li>"
        "<li><b>Deadline:</b> nunca inventada; em vagas SuccessFactors o campo "
        "é validade do feed da plataforma (fonte), não prazo do empregador — "
        "não entra em urgência nem em \"vagas expirando\".</li>"
        "<li><b>Work authorization:</b> classificado só por evidência explícita "
        "no anúncio; sem informação o estado é \"não mencionado\".</li>"
        "<li><b>Penalidade de senioridade</b> só sem marcador forte de "
        "estudante no título.</li>"
    )
    mat_rules = (
        "<li><b>Gate técnico:</b> quality/P&amp;D/lab só pontuam com termo de "
        "materiais/adjacente no TÍTULO.</li>"
        "<li>Descrição apenas <b>corrobora</b> (máx. 1x por bloco) — "
        "boilerplate não infla.</li>"
        "<li>Penalidades de função de negócio só no <b>título</b>.</li>"
    )

    def pane(label: str, crit, pen, rules: str) -> str:
        return (
            '<div class="how-pane"><b>' + html.escape(label) + "</b>"
            '<div class="w-group">Critérios (positivos)' + crit_rows(crit) + "</div>"
            '<div class="w-group">Penalidades' + pen_rows(pen) + "</div>"
            '<div class="w-group">Regras relevantes<ul>' + rules + "</ul></div>"
            "</div>"
        )

    return (
        '<details class="how"><summary>Como este ranking funciona — '
        'pesos e regras reais</summary>'
        '<div class="how-body" data-sv="biz">'
        + pane(PROFILE_LABELS["biz"], biz_crit, biz_pen, biz_rules)
        + '</div><div class="how-body" data-sv="mat" hidden>'
        + pane(PROFILE_LABELS["mat"], mat_crit, mat_pen, mat_rules)
        + "</div></details>"
    )


def _row_html(
    rank: int, job: dict, *,
    top_n: int = TOP_N,
    score_key: str = "score",
    breakdown_key: str = "score_breakdown",
    order: tuple[str, ...] = _BREAKDOWN_ORDER,
    intel: dict | None = None,
    ref: date | None = None,
    opp: dict | None = None,
) -> str:
    """Uma linha da tabela (tudo escapado; URL clicavel, abre em nova aba).

    A linha carrega os data-attributes que o JS client-side usa para filtrar
    e ordenar (titulo, empresa, local, tipo, pais, score, posicao, data) —
    dentro da tabela DO PERFIL em questao (``score_key``/``breakdown_key``
    apontam para o score do perfil: ``score``/``score_breakdown`` no perfil
    principal; ``materials_score``/``materials_breakdown`` no Materials).
    Posicao ``rank`` = posicao no ranking do perfil; ``top_n`` primeiras
    recebem o badge "Top 30" e a classe de destaque (so apresentacao).

    Fase 6: ``intel`` (dict do ``_job_intel``) alimenta os data-attributes de
    filtro novos (deadline/dias, work authorization, idioma, flags, top,
    readiness), os chips visiveis e o <details> de sinais de candidatura.
    Quando ausente (chamadas diretas/uso antigo), e computado sob demanda
    com ``ref`` (default: data do snapshot -> ``app_intel.snapshot_ref_date``).

    P2.3: a URL so vira ``href`` apos validar o scheme (somente http/https,
    via ``_safe_url``); scheme rejeitado segue o fluxo de URL vazia — o
    titulo aparece sem link e sem botao. O escaping HTML continua aplicado.
    """
    title = str(job.get("title") or "(sem titulo)")
    title_esc = html.escape(title)
    safe_url = _safe_url(job.get("url"))
    url = html.escape(safe_url or "")
    company = html.escape(str(job.get("company") or "—"))
    location = html.escape(str(job.get("location") or "—"))
    emp_type = job.get("employment_type")
    type_txt = html.escape(str(emp_type)) if emp_type else "—"
    country = html.escape(str(job.get("country_iso") or ""))
    added = _added_date(job)
    added_attr = "" if added == "—" else added
    score = job.get(score_key)
    score_attr = str(score) if isinstance(score, (int, float)) else ""

    # Fase 5 — camada PT-BR: titulo traduzido de forma deterministica (campo
    # separado; o original continua SEMPRE visivel e com tag "Original
    # (idioma)" quando detectado). Nenhuma informacao nova e inventada: a
    # traducao vem do glossario em ptbr.py e o idioma e detectado por
    # marcadores fortes (ptbr.detect_language).
    pt_title = ptbr.title_pt(title)
    lang = ptbr.detect_language(title)
    lang_suffix = f" ({lang.upper()})" if lang else ""
    title_cell = ""
    if pt_title:
        title_cell += (
            '<div class="t-pt"><span class="tag tag-pt">PT-BR</span> '
            f'<span class="t-pt-txt">{html.escape(pt_title)}</span></div>'
        )
    title_cell += (
        f'<div class="t-og"><span class="tag tag-orig">Original{lang_suffix}</span> '
    )
    if safe_url:
        title_cell += f'<a href="{url}" target="_blank" rel="noopener">{title_esc}</a>'
    else:
        title_cell += title_esc
    title_cell += "</div>"
    link = title_cell

    is_top = top_n > 0 and rank <= top_n
    badge = '<span class="badge-top">Top 30</span>' if is_top else ""
    row_class = "top30" if is_top else ""
    open_btn = (
        f'<a class="open" href="{url}" target="_blank" rel="noopener">abrir&nbsp;↗</a>'
        if safe_url else '<span class="mut">—</span>'
    )
    # Fase 6 — Application Intelligence da vaga (computado UMA vez por vaga
    # no render_html e reusado nas duas tabelas; fallback sob demanda aqui).
    if intel is None:
        ref_date = ref or app_intel.snapshot_ref_date([job])
        intel = _job_intel(job, ref_date)
    chips = _chips_html(intel)
    intel_details = _intel_html(job, intel)
    # Fase 7 — Opportunity Intelligence: bloco recolhivel por vaga + data-
    # attributes para o Compare opportunities (sempre dados, nunca vencedor).
    opp_details = _opportunity_html(job, opp) if opp else ""
    # Atributos de dados para o JS client-side (escapados para atributo).
    d_title = _attr(job.get("title") or "")
    d_company = _attr(job.get("company") or "")
    d_location = _attr(job.get("location") or "")
    d_type = _attr(job.get("employment_type") or "")
    d_country = _attr(job.get("country_iso") or "")
    d_date = _attr(added_attr)
    d_deadline = (str(intel["days"]) if intel["days"] is not None
                  and intel["kind"] in ("employer", "employer_textual") else "")
    d_wa = _attr(intel["wa"])
    d_lang = "de-" + intel["de"] if intel["de"] != "none" else ""
    d_en = "1" if intel["en"] else ""
    d_flags = str(len(intel["flags"]))
    d_ready = _attr(intel["ready"])
    d_top = "1" if is_top else ""
    # Fase 7 — atributos de comparacao (valores ENQUANTO dados; nunca vencedor).
    if opp:
        sal = opp.get("salary")
        d_salary = f"{sal['min']:g}" if sal and sal["min"] == sal["max"] else (
            f"{sal['min']:g}-{sal['max']:g}" if sal else "")
        d_salary_period = _attr((sal or {}).get("period") or "") if sal else ""
        dur = opp.get("duration")
        d_duration = f"{dur['min']}-{dur['max']}" if dur else ""
        col = opp.get("col")
        d_cost = str(col.get("estimate_monthly") or "") if col else ""
        d_benefits = "1" if (opp.get("company") or {}).get("benefits") else ""
        d_career = "1" if (opp.get("company") or {}).get("career_development") else ""
        d_has_company = "1" if opp.get("company") else ""
        col = opp.get("col")
        d_transport = str(col.get("transport_monthly") or "") if col else ""
    else:
        d_salary = d_salary_period = d_duration = d_cost = d_benefits = d_career = d_has_company = d_transport = ""
    d_mode = _attr(opp["mode"]) if opp else ""
    d_city = _attr(opp.get("city") or "") if opp else ""
    d_pathway = _attr(opp["pathway"]) if opp else ""
    d_url = _attr(safe_url or "")
    compare_box = (
        '<label class="cmp-pick" title="selecionar para comparar">'
        f'<input type="checkbox" class="cmp-cb" data-cmp-id="{d_title}" '
        f'data-cmp-name="{d_company}" data-cmp-title="{d_title}">'
        "<span>comparar</span></label>"
    ) if opp is not None else ""
    return (
        f'<tr class="{row_class}"'
        f' data-rank="{rank}"'
        f' data-job-id="{_attr(str(job.get("id") or ""))}"'
        f' data-title="{d_title}"'
        f' data-company="{d_company}"'
        f' data-location="{d_location}"'
        f' data-type="{d_type}"'
        f' data-country="{d_country}"'
        f' data-score="{score_attr}"'
        f' data-date="{d_date}"'
        f' data-deadline="{d_deadline}"'
        f' data-wa="{d_wa}"'
        f' data-lang="{d_lang}"'
        f' data-en="{d_en}"'
        f' data-flags="{d_flags}"'
        f' data-ready="{d_ready}"'
        f' data-top="{d_top}"'
        f' data-salary="{d_salary}"'
        f' data-salary-period="{d_salary_period}"'
        f' data-mode="{d_mode}"'
        f' data-city="{d_city}"'
        f' data-cost="{d_cost}"'
        f' data-pathway="{d_pathway}"'
        f' data-duration="{d_duration}"'
        f' data-benefits="{d_benefits}"'
        f' data-career="{d_career}"'
        f' data-has-company="{d_has_company}"'
        f' data-transport="{d_transport}"'
        f' data-url="{d_url}">'
        f'<td class="score" data-label="#">{rank}</td>'
        f'<td class="score" data-label="score">{_fmt_score(score)}</td>'
        f"<td data-label=\"vaga\">{compare_box}{link}{badge}{chips}{intel_details}{opp_details}{_details_html(job, breakdown_key=breakdown_key, order=order)}</td>"
        f'<td data-label="empresa">{company}</td>'
        f'<td class="loc" data-label="local">{location}</td>'
        f'<td data-label="tipo">{type_txt}</td>'
        f'<td class="mut" data-label="desde">{added}</td>'
        f'<td class="act">{open_btn}</td>'
        "</tr>"
    )


def _compute_stats(jobs: list[dict], *, total: int, score_key: str = "score") -> dict:
    """Resumo do topo (estado atual da busca), derivado dos dados reais."""
    companies = len({str(j.get("company") or "") for j in jobs if j.get("company")})
    scores = [
        float(j[score_key]) for j in jobs
        if isinstance(j.get(score_key), (int, float))
    ]
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
  .profiles { display:flex; gap:8px; margin:14px 0 2px; flex-wrap:wrap; }
  .profiles button { font:inherit; font-size:.85rem; padding:7px 14px; border:1px solid var(--line); border-radius:999px; background:var(--card); color:var(--mut); cursor:pointer; }
  .profiles button:hover { border-color:var(--acc); color:var(--acc); }
  .profiles button.active { background:var(--acc); border-color:var(--acc); color:#fff; font-weight:600; }
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
  /* Fase 5: camada PT-BR — titulo derivado + original rotulado */
  .t-pt { font-weight:600; line-height:1.35; }
  .t-og { margin-top:3px; font-size:.85rem; color:#3d4c5c; line-height:1.35; }
  .t-og a { color:var(--acc); }
  .tag { display:inline-block; font-size:.6rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; border:1px solid var(--line); color:var(--mut); border-radius:999px; padding:1px 7px; margin-right:5px; vertical-align:2px; white-space:nowrap; }
  .tag-pt { border-color:var(--acc); color:var(--acc); }
  .tag-orig { background:#eef2f7; padding:1px 6px; }
  .bd-x { grid-column:1 / -1; font-size:.72rem; color:var(--mut); margin:-2px 0 5px; padding-left:2px; }
  .bd-pen { grid-column:1 / -1; font-size:.72rem; font-weight:700; color:#a93226; margin:4px 0 3px; letter-spacing:.02em; }
  .desc-orig { display:inline; }
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
  p.small { font-size:.78rem; }
  footer { margin-top:18px; font-size:.75rem; color:var(--mut); }
  /* ---- Fase 6: chips de candidatura, sinais, "como funciona", filtros ---- */
  .chips { margin:6px 0 2px; display:flex; flex-wrap:wrap; gap:4px; }
  .chip { display:inline-block; font-size:.64rem; font-weight:600; border-radius:999px; padding:2px 8px; border:1px solid var(--line); background:#f4f7fa; color:#33475b; white-space:nowrap; }
  .chip.c-bad { background:#fdecea; border-color:#e6b4ad; color:#a93226; }
  .chip.c-warn { background:#fef7e0; border-color:#ecd9a0; color:#8a6d1c; }
  .chip.c-good, .chip.c-green { background:#eaf7ee; border-color:#bfe3cc; color:#1e7d45; }
  .chip.c-yellow { background:#fef7e0; border-color:#ecd9a0; color:#8a6d1c; }
  .chip.c-orange { background:#fdf0e2; border-color:#f0cfa3; color:#b45f06; }
  .chip.c-red { background:#fdecea; border-color:#e6b4ad; color:#a93226; }
  .chip.c-en { background:#e8f1fc; border-color:#bcd8f5; color:#0b5394; }
  .chip.c-wa { background:#f1f3f6; border-color:#d8dee6; color:#3d4c5c; }
  details.intel { margin-top:4px; }
  details.intel summary { cursor:pointer; color:var(--mut); font-size:.76rem; }
  .fit { margin:4px 0 2px; }
  .fit-line { font-size:.78rem; color:#33475b; padding:1px 0; }
  .fit-icon { display:inline-block; width:16px; text-align:center; }
  .fit-ok .fit-icon { color:#1e7d45; }
  .fit-warn .fit-icon { color:#b45f06; }
  .wa { font-size:.78rem; color:#33475b; margin:3px 0; }
  .sec { margin:6px 0 2px; }
  .sec-t { display:block; font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:var(--mut); margin-bottom:2px; }
  .prob, .flag { font-size:.76rem; color:#33475b; padding:1px 0; }
  .prob::before { content:"⚠ "; color:#b45f06; }
  .flag::before { content:"ⓘ "; color:var(--mut); }
  .fresh { font-size:.76rem; color:var(--mut); }
  details.intel .fit, details.intel .wa, details.intel .sec { border-bottom:1px dashed var(--line); padding:4px 0; }
  details.upd { margin:6px 0 2px; }
  details.upd summary { cursor:pointer; color:var(--mut); font-size:.72rem; }
  details.how { margin:12px 0 4px; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; }
  details.how summary { cursor:pointer; font-weight:600; color:#33475b; font-size:.82rem; }
  .how-body { margin:6px 0 2px; }
  .how-pane b { display:block; margin-bottom:2px; }
  .w-group { font-size:.72rem; color:var(--mut); margin-top:8px; }
  .w-row { display:flex; justify-content:space-between; gap:12px; color:#33475b; font-size:.78rem; padding:1px 0; max-width:600px; }
  .w-row b { font-variant-numeric:tabular-nums; }
  .w-group ul { margin:3px 0 0; padding-left:16px; color:#33475b; font-size:.76rem; max-width:680px; }
  details.filters { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; margin:10px 0 4px; }
  details.filters summary { cursor:pointer; color:#33475b; font-weight:600; font-size:.85rem; }
  .f-badge { background:var(--acc); color:#fff; border-radius:999px; padding:0 7px; margin-left:4px; font-size:.72rem; }
  .fgrid { display:flex; flex-wrap:wrap; gap:10px 18px; margin:8px 0 4px; }
  .fgrid .fld select { max-width:240px; }
  .chk { font-weight:400; }
  /* ---- Fase 7: Opportunity Intelligence + Compare opportunities ---- */
  details.opp { margin-top:5px; border:1px solid var(--line); border-radius:8px; padding:4px 8px; background:#fbfcfe; max-width:640px; }
  details.opp > summary { font-size:.78rem; font-weight:600; color:#33475b; }
  .opp-sec { margin:5px 0 0; padding-top:4px; border-top:1px dashed var(--line); }
  .opp-sec-t { display:block; font-size:.64rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:var(--mut); margin-bottom:2px; }
  .opp-row { display:flex; gap:8px; font-size:.78rem; color:#33475b; padding:1px 0; }
  .opp-k { flex:0 0 auto; min-width:150px; color:var(--mut); }
  .opp-v { flex:1 1 auto; }
  .opp-em .opp-v { color:var(--mut); font-style:italic; }
  .srcs { margin:2px 0 4px; }
  .src { font-size:.74rem; color:#3d4c5c; padding:1px 0; }
  details.opp .srcs .src a, .opp-v a { color:var(--acc); }
  .cmp-pick { float:right; font-size:.66rem; color:var(--mut); margin:0 0 4px 8px; }
  .cmp-pick input { vertical-align:-1px; }
  details.compare { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; margin:10px 0 4px; }
  details.compare summary { cursor:pointer; color:#33475b; font-weight:600; font-size:.85rem; }
  .cmp-bar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin:6px 0 4px; }
  .cmp-bar button { font:inherit; font-size:.82rem; padding:6px 12px; border:1px solid var(--acc); color:var(--acc); border-radius:999px; background:var(--card); cursor:pointer; }
  .cmp-bar button:hover { background:var(--acc); color:#fff; }
  .cmp-out { overflow-x:auto; margin-top:6px; }
  .cmp-out table { border-collapse:collapse; min-width:560px; }
  .cmp-out th, .cmp-out td { border:1px solid var(--line); padding:6px 9px; font-size:.78rem; vertical-align:top; }
  .cmp-out th { background:#eef2f7; font-size:.66rem; text-transform:uppercase; letter-spacing:.04em; color:var(--mut); }
  .cmp-out td.f { color:var(--mut); font-weight:600; white-space:nowrap; }
  .cmp-good { background:#eaf7ee; }
  .cmp-warn { background:#fef7e0; }
  .cmp-bad { background:#fdecea; }
  .cmp-empty { color:var(--mut); font-style:italic; }
  @media (max-width:760px) {
    main { padding:14px 10px 48px; }
    h1 { font-size:1.02rem; line-height:1.25; }
    .src-line { display:none; }
    .stats { display:grid; grid-template-columns:repeat(2,1fr); gap:8px; }
    .stat { min-width:0; padding:8px 10px; }
    .wrap { overflow-x:visible; border:0; background:transparent; }
    table { display:block; }
    thead { display:none; }
    tbody { display:block; }
    tr { display:block; background:var(--card); border:1px solid var(--line); border-radius:12px; margin:0 0 12px; padding:10px 12px 12px; box-shadow:0 1px 2px rgba(28,39,51,.05); }
    tr.top30 { background:#f0f7ff; }
    tr:hover td { background:transparent; }
    td { display:block; border:0; padding:1px 0; }
    td.score { display:inline-block; width:auto; margin-right:10px; font-size:.86rem; }
    td[data-label="vaga"] { margin-top:5px; }
    td[data-label="empresa"] { font-weight:600; font-size:.9rem; }
    td[data-label="empresa"]::before, td[data-label="local"]::before,
    td[data-label="tipo"]::before, td[data-label="desde"]::before { content:attr(data-label) ": "; font-size:.62rem; color:var(--mut); text-transform:uppercase; letter-spacing:.04em; }
    td.loc, td[data-label="tipo"], td[data-label="desde"] { font-size:.78rem; }
    td[data-label="tipo"], td[data-label="desde"] { display:inline-block; margin-right:12px; }
    td.act { margin-top:8px; text-align:right; }
    td.act a.open { display:inline-block; padding:9px 22px; font-size:.85rem; }
    details.intel, details.why { font-size:.9rem; }
    .bd-body { max-width:100%; }
    .toolbar { gap:8px; }
    input#q { flex:1 1 100%; max-width:none; font-size:16px; }
    .fgrid { flex-direction:column; gap:8px; }
    .how-body { padding:6px 2px; }
    details.how { padding:6px 10px; }
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#10151b; --card:#192027; --ink:#e6edf3; --mut:#9aa7b4; --acc:#4da3ff; --line:#2a343e; }
    .badge-top { background:#4da3ff; }
    tr.top30 td { background:rgba(77,163,255,.08); }
    tr.top30:hover td { background:rgba(77,163,255,.12); }
    th { background:#222c36; }
    .bd-body, .how-body { background:#141a21; }
    .chip { background:#222c36; border-color:#33404c; color:#c8d3dd; }
    .chip.c-bad { background:#3b1d1d; border-color:#6e3a33; color:#f0a6a0; }
    .chip.c-warn { background:#3b3317; border-color:#6e5d2e; color:#e8cf8a; }
    .chip.c-good, .chip.c-green { background:#16301f; border-color:#2c5c3e; color:#9fd8b4; }
    .chip.c-red { background:#3b1d1d; border-color:#6e3a33; color:#f0a6a0; }
    td[data-label="empresa"], .t-pt-txt { color:#e6edf3; }
  }
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
  /* Fase 6: deadline confiavel (dias restantes), work authorization,
     idioma, Top 30 e quality flags. Vagas SEM deadline (row.deadline vazio)
     nunca casam o filtro de "expirando". */
  if (st.deadline) {
    var dd = parseFloat(row.deadline);
    if (isNaN(dd) || !(dd <= parseFloat(st.deadline))) return false;
  }
  if (st.wa && row.wa !== st.wa) return false;
  if (st.lang) {
    if (st.lang === 'en') { if (row.en !== '1') return false; }
    else if (st.lang === 'none') { if (row.en === '1' || row.lang) return false; }
    else { if (row.lang !== st.lang) return false; }
  }
  if (st.top30 && row.top !== '1') return false;
  if (st.flags && !((parseFloat(row.flags) || 0) > 0)) return false;
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
  var PROFILES = ['biz', 'mat'];
  var ACTIVE = 'biz';
  function table(p) { return document.getElementById('tbl-' + p); }
  function body(p) { return table(p).querySelector('tbody'); }
  function rows(p) { return Array.prototype.slice.call(body(p).querySelectorAll('tr')); }
  function total(p) {
    var t = parseInt(table(p).getAttribute('data-total'), 10);
    return isNaN(t) ? body(p).rows.length : t;
  }
  function data(p) {
    return rows(p).map(function (tr) {
      var d = tr.dataset;
      return { tr: tr, title: d.title, company: d.company, location: d.location,
               type: d.type, country: d.country, score: d.score,
               rank: d.rank, date: d.date,
               deadline: d.deadline, wa: d.wa, lang: d.lang, en: d.en,
               flags: d.flags, top: d.top, ready: d.ready };
    });
  }
  var ids = ['q', 'f-company', 'f-location', 'f-type', 'f-country', 'f-min-score',
             'f-deadline', 'f-wa', 'f-lang', 'f-top30', 'f-flags',
             'sort', 'count', 'clear', 'f-badge'];
  var els = {};
  ids.forEach(function (id) { els[id] = document.getElementById(id); });
  if (!els.sort || !els.count) return;

  var PICK = {
    'f-company': function (r) { return r.company; },
    'f-location': function (r) { return r.location; },
    'f-type': function (r) { return r.type; },
    'f-country': function (r) { return r.country; }
  };
  var EMPTY_LABEL = { 'f-company': 'todas', 'f-location': 'todos', 'f-type': 'todos', 'f-country': 'todos' };
  function fill(selId, items) {
    var sel = document.getElementById(selId);
    if (!sel) return;
    var seen = [];
    items.forEach(function (r) {
      var v = PICK[selId](r);
      if (v && seen.indexOf(v) === -1) seen.push(v);
    });
    seen.sort(if_cmp_str);
    sel.innerHTML = '';
    var o = document.createElement('option');
    o.value = '';
    o.textContent = EMPTY_LABEL[selId];
    sel.appendChild(o);
    var wrap = sel.closest('.fld');
    if (seen.length < 2) { if (wrap) wrap.style.display = 'none'; return; }
    if (wrap) wrap.style.display = '';
    seen.forEach(function (v) {
      var opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  }
  function state() {
    return {
      q: els.q ? els.q.value : '',
      company: els['f-company'] ? els['f-company'].value : '',
      location: els['f-location'] ? els['f-location'].value : '',
      type: els['f-type'] ? els['f-type'].value : '',
      country: els['f-country'] ? els['f-country'].value : '',
      minScore: els['f-min-score'] ? els['f-min-score'].value : '',
      deadline: els['f-deadline'] ? els['f-deadline'].value : '',
      wa: els['f-wa'] ? els['f-wa'].value : '',
      lang: els['f-lang'] ? els['f-lang'].value : '',
      top30: els['f-top30'] ? els['f-top30'].checked : false,
      flags: els['f-flags'] ? els['f-flags'].checked : false
    };
  }
  function badgeCount() {
    var n = 0;
    if (els.q && els.q.value.trim()) n++;
    ['f-company', 'f-location', 'f-type', 'f-country', 'f-min-score',
     'f-deadline', 'f-wa', 'f-lang'].forEach(function (id) {
      if (els[id] && els[id].value) n++;
    });
    ['f-top30', 'f-flags'].forEach(function (id) {
      if (els[id] && els[id].checked) n++;
    });
    return n;
  }
  function apply() {
    var p = ACTIVE;
    var out = if_filter_sort(data(p), state(), els.sort.value);
    rows(p).forEach(function (tr) { tr.style.display = 'none'; });
    out.forEach(function (r) {
      r.tr.style.display = '';
      body(p).appendChild(r.tr);
    });
    els.count.textContent = out.length + ' de ' + total(p) + ' vagas';
    if (els['f-badge']) {
      var b = badgeCount();
      els['f-badge'].textContent = b ? '(' + b + ')' : '';
    }
  }
  function activate(p) {
    ACTIVE = p;
    PROFILES.forEach(function (x) {
      var w = document.getElementById('wrap-' + x);
      if (w) w.hidden = (x !== p);
      var btn = document.getElementById('btn-' + x);
      if (btn) btn.classList.toggle('active', x === p);
      document.querySelectorAll('[data-sv="' + x + '"]').forEach(function (el) {
        el.hidden = (x !== p);
      });
    });
    var rowsP = data(p);
    fill('f-company', rowsP);
    fill('f-location', rowsP);
    fill('f-type', rowsP);
    fill('f-country', rowsP);
    ['f-company', 'f-location', 'f-type', 'f-country', 'f-deadline', 'f-wa',
     'f-lang'].forEach(function (id) {
      if (els[id]) els[id].value = '';
    });
    if (els['f-top30']) els['f-top30'].checked = false;
    if (els['f-flags']) els['f-flags'].checked = false;
    if (els.q) els.q.value = '';
    if (els['f-min-score']) els['f-min-score'].value = '';
    els.sort.value = 'score-desc';
    apply();
  }
  function wire(id, evt) { if (els[id]) els[id].addEventListener(evt, apply); }
  wire('q', 'input');
  wire('f-min-score', 'input');
  wire('f-company', 'change');
  wire('f-location', 'change');
  wire('f-type', 'change');
  wire('f-country', 'change');
  wire('f-deadline', 'change');
  wire('f-wa', 'change');
  wire('f-lang', 'change');
  wire('f-top30', 'change');
  wire('f-flags', 'change');
  wire('sort', 'change');
  if (els.clear) {
    els.clear.addEventListener('click', function () {
      if (els.q) els.q.value = '';
      if (els['f-min-score']) els['f-min-score'].value = '';
      ['f-company', 'f-location', 'f-type', 'f-country', 'f-deadline', 'f-wa',
       'f-lang'].forEach(function (id) {
        if (els[id]) els[id].value = '';
      });
      if (els['f-top30']) els['f-top30'].checked = false;
      if (els['f-flags']) els['f-flags'].checked = false;
      apply();
    });
  }
  PROFILES.forEach(function (p) {
    var btn = document.getElementById('btn-' + p);
    if (btn) btn.addEventListener('click', function () { activate(p); });
  });
  activate('biz');
})();
/* ==== Fase 7: Compare opportunities (dados; sem vencedor automatico) ==== */
(function () {
  'use strict';
  function allCbs() {
    return Array.prototype.slice.call(document.querySelectorAll('tr .cmp-cb'));
  }
  function checked() { return allCbs().filter(function (cb) { return cb.checked; }); }
  function d(tr) { return tr.dataset; }
  function waLabel(v) {
    var m = { support: 'Suporte/visto mencionado', existing_required: 'Requer autorização existente',
              no_sponsorship: 'Sem sponsorship', unclear: 'Não claro', not_mentioned: 'Não mencionado' };
    return m[v] || v || 'Não mencionado';
  }
  function waTone(v) {
    if (v === 'support') return 'cmp-good';
    if (v === 'existing_required' || v === 'no_sponsorship') return 'cmp-bad';
    if (v === 'unclear') return 'cmp-warn';
    return '';
  }
  function langText(tr) {
    var out = [];
    if (d(tr).en === '1') out.push('Inglês mencionado');
    if (d(tr).lang === 'de-required') out.push('Alemão exigido');
    else if (d(tr).lang === 'de-preferred') out.push('Alemão preferido');
    if (!out.length) out.push('Sem menção a idioma');
    return out.join('; ');
  }
  function deadlineText(tr) {
    var v = d(tr).deadline;
    if (!v || isNaN(parseFloat(v))) return ['Não informado', 'cmp-empty'];
    var n = parseFloat(v);
    var tone = n <= 2 ? 'cmp-bad' : (n <= 7 ? 'cmp-warn' : (n <= 14 ? '' : 'cmp-good'));
    return [n + ' dias', tone];
  }
  function salaryText(tr) {
    var v = d(tr).salary;
    if (!v) return ['Not disclosed', 'cmp-empty'];
    var p = String(v).split('-');
    var label = (p.length === 2 ? '€' + p[0] + '–€' + p[1] : '€' + p[0]);
    var per = d(tr).salaryPeriod;
    return [per ? label + '/' + per : label, 'cmp-good'];
  }
  function modeText(tr) {
    var m = { remote: 'Remoto', hybrid: 'Híbrido', on_site: 'Presencial', not_mentioned: 'Não mencionado' };
    var v = d(tr).mode || 'not_mentioned';
    var tone = (v === 'remote' || v === 'hybrid') ? 'cmp-good' : (v === 'on_site' ? '' : 'cmp-empty');
    return [m[v] || v, tone];
  }
  function durationText(tr) {
    var v = d(tr).duration;
    if (!v) return ['Não informada', 'cmp-empty'];
    var p = String(v).split('-');
    return [(p.length === 2 && p[1] !== p[0] ? p[0] + '–' + p[1] : p[0]) + ' meses', ''];
  }
  function flagText(v, yes, no, tone) {
    return v === '1' ? [yes, tone] : [no, 'cmp-empty'];
  }
  function pathwayText(tr) {
    var m = { explicitly_supported: 'Explicitly supported', evidence_available: 'Evidence available',
              not_mentioned: 'Not mentioned', unknown: 'Unknown' };
    var v = d(tr).pathway || 'unknown';
    var tone = v === 'explicitly_supported' ? 'cmp-good' : (v === 'evidence_available' ? 'cmp-warn' : 'cmp-empty');
    return [m[v] || v, tone];
  }
  function cityText(tr) {
    var c = d(tr).city;
    if (!c) return ['Não informada', 'cmp-empty'];
    var cost = d(tr).cost;
    var t = cost ? ' ~' + cost + '/mês (estim.)' : '';
    return [c + t, cost ? 'cmp-good' : ''];
  }
  function transportText(tr) {
    var v = d(tr).transport;
    return v ? [v + '/mês', ''] : ['Não informado', 'cmp-empty'];
  }
  function titleCell(tr) {
    var url = d(tr).url;
    var t = String(d(tr).title || 'sem título');
    if (t.length > 46) t = t.slice(0, 45) + '…';
    return url ? '<a href="' + url + '" target="_blank" rel="noopener">' + t + '</a>' : t;
  }
  var FACTORS = [
    ['fit', 'Job Fit (score)', function (tr) { return [String(d(tr).score || '—'), '']; }],
    ['ready', 'Candidate Fit (readiness)', function (tr) {
      return d(tr).ready === 'ready' ? ['✅ Pronta p/ revisar', 'cmp-good'] : ['⚠️ Precisa verificação', 'cmp-warn'];
    }],
    ['lang', 'Idioma', function (tr) { return [langText(tr), '']; }],
    ['wa', 'Work authorization', function (tr) { return [waLabel(d(tr).wa), waTone(d(tr).wa)]; }],
    ['deadline', 'Deadline', deadlineText],
    ['role', 'Vaga', function (tr) { return [String(d(tr).company || '—') + ' — ' + titleCell(tr), '']; }],
    ['salary', 'Salário', salaryText],
    ['mode', 'Work mode', modeText],
    ['duration', 'Duração', durationText],
    ['benefits', 'Benefícios (empresa)', function (tr) {
      return flagText(d(tr).benefits, '✓ informados c/ fonte', '?', 'cmp-good');
    }],
    ['career', 'Carreira (desenvolvimento)', function (tr) {
      return flagText(d(tr).career, '✓ evidência c/ fonte', '?', 'cmp-good');
    }],
    ['pathway', 'Internship → Full-time', pathwayText],
    ['city', 'Cidade', cityText],
    ['transport', 'Transporte público', transportText],
  ];
  function render() {
    var cbs = checked().slice(0, 4);
    var out = document.getElementById('cmp-out');
    var sel = document.getElementById('cmp-selected');
    var badge = document.getElementById('cmp-count');
    if (!out) return;
    var n = checked().length;
    if (sel) sel.textContent = n ? (n + (n === 1 ? ' vaga selecionada' : ' vagas selecionadas')
      + (n > 4 ? ' (máx. 4 exibidas)' : '')) : 'nenhuma vaga selecionada';
    if (badge) badge.textContent = n ? '(' + n + ')' : '';
    if (!cbs.length) { out.innerHTML = ''; return; }
    var rows = FACTORS.map(function (f) {
      var cells = cbs.map(function (cb) {
        var tr = cb.closest('tr');
        var res = f[2](tr);
        return '<td class="' + (res[1] || '') + '">' + (res[0] || '—') + '</td>';
      });
      return '<tr><td class="f">' + f[1] + '</td>' + cells.join('') + '</t' + 'r>';
    }).join('');
    var head = '<tr><th>fator</th>' + cbs.map(function (cb) {
      var tr = cb.closest('tr');
      return '<th>' + titleCell(tr) + '<div class="mut" style="font-weight:400;text-transform:none">' +
        String(d(tr).company || '') + '</div></th>';
    }).join('') + '</t' + 'r>';
    out.innerHTML = '<table>' + head + rows + '</table>' +
      '<p class="hint">Valores exibidos como dados (Job Fit/Candidate Fit do pipeline; empresa, benefícios, ' +
      'carreira e pathway dos arquivos curados com fonte; salário/modalidade/duração evidenciados no próprio ' +
      'anúncio). Nenhuma coluna é “melhor” automaticamente — a decisão é sua.</p>';
  }
  function wire(id, evt, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener(evt, fn);
  }
  wire('cmp-show', 'click', function () { render(); });
  wire('cmp-clear', 'click', function () {
    allCbs().forEach(function (cb) { cb.checked = false; });
    render();
  });
  document.addEventListener('change', function (ev) {
    if (ev.target && ev.target.classList && ev.target.classList.contains('cmp-cb')) render();
  });
})();
"""


def _stat_block(label: str, biz_value: str, mat_value: str) -> str:
    """Um card do resumo com os dois valores (Fase 4), alternados via [data-sv]."""
    return (
        '<div class="stat"><b>'
        f'<span data-sv="biz">{html.escape(biz_value)}</span>'
        f'<span data-sv="mat" hidden>{html.escape(mat_value)}</span>'
        f"</b><span>{label}</span></div>"
    )


def _stats_html(
    stats: dict, *, mat_stats: dict | None = None,
) -> str:
    """Cards do resumo. Sem ``mat_stats``: formato da Fase 3 (valor unico).

    Com ``mat_stats`` (pagina de dois perfis): cada card leva os valores dos
    dois perfis em spans ``[data-sv]``; o JS mostra o do perfil ativo.
    """
    if mat_stats is None:
        max_score = stats.get("max_score")
        max_txt = _fmt_score(max_score) if max_score is not None else "—"
        return (
            f'<div class="stat"><b>{stats.get("total", 0)}</b><span>vagas elegíveis</span></div>'
            f'<div class="stat"><b>{stats.get("companies", 0)}</b><span>empresas</span></div>'
            f'<div class="stat"><b>{max_txt}</b><span>score máx</span></div>'
            f'<div class="stat"><b>{stats.get("top30", 0)}</b><span>no Top 30</span></div>'
            f'<div class="stat"><b>{html.escape(str(stats.get("updated") or "")[:16].replace("T", " "))}</b><span>dados atualizados</span></div>'
        )
    biz_max = stats.get("max_score")
    mat_max = mat_stats.get("max_score")
    biz_txt = _fmt_score(biz_max) if biz_max is not None else "—"
    mat_txt = _fmt_score(mat_max) if mat_max is not None else "—"
    updated = str(stats.get("updated") or "")[:16].replace("T", " ")
    return (
        _stat_block("vagas elegíveis", str(stats.get("total", 0)), str(mat_stats.get("total", 0)))
        + _stat_block("empresas", str(stats.get("companies", 0)), str(mat_stats.get("companies", 0)))
        + _stat_block("score máx", biz_txt, mat_txt)
        + _stat_block("no Top 30", str(stats.get("top30", 0)), str(mat_stats.get("top30", 0)))
        + _stat_block("dados atualizados", updated, updated)
    )


def _filters_panel_html(expiring_note: str) -> str:
    """Painel de filtros recolhivel (Fase 6: deadline, visa, idioma, top30,
    quality flags — alem dos eixos existentes). Contador de ativos em #f-badge."""
    return (
        '<details class="filters" id="filters"><summary>Filtros '
        '<span id="f-badge" class="f-badge"></span></summary>'
        '<div class="fgrid">'
        '<span class="fld"><label>empresa</label><select id="f-company">'
        '<option value="">todas</option></select></span>'
        '<span class="fld"><label>local</label><select id="f-location">'
        '<option value="">todos</option></select></span>'
        '<span class="fld"><label>tipo</label><select id="f-type">'
        '<option value="">todos</option></select></span>'
        '<span class="fld"><label>país</label><select id="f-country">'
        '<option value="">todos</option></select></span>'
        '<span class="fld"><label>score mín.</label>'
        '<input id="f-min-score" type="number" min="0" step="0.25" '
        'placeholder="0.0"></span>'
        '<span class="fld"><label>vagas expirando (deadline confiável)</label>'
        '<select id="f-deadline">'
        '<option value="">qualquer</option>'
        '<option value="2">≤ 2 dias</option>'
        '<option value="7">≤ 7 dias</option>'
        '<option value="14">≤ 14 dias</option>'
        "</select></span>"
        '<span class="fld"><label>work authorization</label>'
        '<select id="f-wa">'
        '<option value="">qualquer</option>'
        '<option value="support">suporte mencionado</option>'
        '<option value="existing_required">autorização existente exigida</option>'
        '<option value="no_sponsorship">sem sponsorship</option>'
        '<option value="unclear">não claro</option>'
        '<option value="not_mentioned">não mencionado</option>'
        "</select></span>"
        '<span class="fld"><label>idioma</label>'
        '<select id="f-lang">'
        '<option value="">qualquer</option>'
        '<option value="en">inglês mencionado</option>'
        '<option value="de-required">alemão exigido</option>'
        '<option value="de-preferred">alemão preferido</option>'
        '<option value="none">sem menção a idioma</option>'
        "</select></span>"
        '<span class="fld"><label class="chk"><input type="checkbox" '
        'id="f-top30"> Top 30 (perfil ativo)</label></span>'
        '<span class="fld"><label class="chk"><input type="checkbox" '
        'id="f-flags"> com quality flags</label></span>'
        "</div>"
        f'<p class="hint">{html.escape(expiring_note)}</p>'
        '<button type="button" id="clear">limpar filtros</button>'
        "</details>"
    )


def _expiring_note(jobs: list[dict], ref: date) -> str:
    """Resumo 'vagas expirando' — SOMENTE deadline confiavel do empregador.

    Validade de feed do SuccessFactors NAO conta (nao e prazo — regra
    documentada); sem deadline tambem nao aparece como 'expirando' (spec 6).
    """
    known = 0
    expiring7 = 0
    seen: set[str] = set()
    for j in jobs:
        jid = str(j.get("id") or "")
        if jid in seen:
            continue
        seen.add(jid)
        if app_intel.deadline_kind(j) in ("employer", "employer_textual"):
            known += 1
            dl = app_intel.deadline_date(j)
            days = app_intel.days_until(dl, ref) if dl is not None else None
            if days is not None and days <= 7:
                expiring7 += 1
    return (
        f"Vagas expirando: {expiring7} com deadline confirmado em até 7 dias "
        f"(de {known} com deadline do empregador; {len(seen) - known} sem "
        "deadline confirmado não entram neste filtro)."
    )


def _intel_map_for(jobs: list[dict], materials: list[dict] | None, ref: date) -> dict:
    """Intel de candidatura UMA vez por vaga (id), reusado nas duas tabelas."""
    out: dict[str, dict] = {}
    for j in list(jobs) + list(materials or []):
        jid = str(j.get("id") or "")
        if jid and jid not in out:
            out[jid] = _job_intel(j, ref)
    return out


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
    materials: list[dict] | None = None,
    materials_rank_map: dict[str, int] | None = None,
    materials_stats: dict | None = None,
    ref_date: date | None = None,
    intel_map: dict[str, dict] | None = None,
    show_how: bool = True,
    company_intel_map: dict[str, dict] | None = None,
    loc_map: dict[str, dict] | None = None,
    opp_map: dict[str, dict] | None = None,
) -> str:
    """Pagina auto-contida (CSS inline, JS vanilla inline, zero external).

    ``jobs`` sao as linhas exibidas do PERFIL PRINCIPAL (ja
    filtradas/cortadas pelo CLI); ``total`` e o total do conjunto filtrado
    (contador e resumo). ``stats`` e o resumo do topo (derivado do conjunto
    inteiro pelo ``main``); quando ausente, e derivado de ``jobs``.
    ``rank_map`` mapeia id -> posicao no ranking do pipeline; sem ele, a
    posicao exibida e a posicao na lista passada.

    Fase 4: com ``materials`` (lista do MESMO conjunto ranqueada pelo perfil
    Materials — ver ``materials_ranking.rank_materials_jobs``), a pagina ganha
    o seletor de perfil e a segunda tabela (posicoes, scores e breakdowns
    PROPRIOS do perfil Materials). ``materials_rank_map``/``materials_stats``
    espelham ``rank_map``/``stats`` para o segundo perfil. Sem ``materials``,
    o HTML e EXATAMENTE o da Fase 3 (compatibilidade preservada).

    Fase 6: ``ref_date`` (data do run; default = max(collected_at) do
    snapshot) fixa a urgencia; ``intel_map`` (py id -> ``_job_intel``)
    alimenta filtros/chips/sinais; ``show_how`` liga a secao 'Como este
    ranking funciona' (pesos REAIS das constantes).
    """
    if stats is None:
        stats = _compute_stats(jobs, total=total)
    all_jobs = list(jobs) + list(materials or [])
    if ref_date is None:
        ref_date = app_intel.snapshot_ref_date(all_jobs or jobs)
    if intel_map is None:
        intel_map = _intel_map_for(jobs, materials, ref_date)
    if company_intel_map is None:
        company_intel_map = opportunity_intel.load_company_intel()
    if loc_map is None:
        loc_map = opportunity_intel.load_location_intel()
    if opp_map is None:
        opp_map = _opp_map_for(jobs, materials, company_intel_map, loc_map)
    rows: list[str] = []
    for i, j in enumerate(jobs, 1):
        rank = i
        if rank_map is not None and j.get("id") is not None:
            rank = rank_map.get(str(j.get("id")), i)
        rows.append(_row_html(
            rank, j, top_n=top_n,
            intel=intel_map.get(str(j.get("id"))),
            ref=ref_date,
            opp=opp_map.get(str(j.get("id"))),
        ))
    rows_html = "\n".join(rows)

    mat_rows_html = ""
    if materials is not None:
        mat_rows: list[str] = []
        for i, j in enumerate(materials, 1):
            rank = i
            if materials_rank_map is not None and j.get("id") is not None:
                rank = materials_rank_map.get(str(j.get("id")), i)
            mat_rows.append(_row_html(
                rank, j, top_n=top_n,
                score_key="materials_score",
                breakdown_key="materials_breakdown",
                order=_MATERIALS_BREAKDOWN_ORDER,
                intel=intel_map.get(str(j.get("id"))),
                ref=ref_date,
                opp=opp_map.get(str(j.get("id"))),
            ))
        mat_rows_html = "\n".join(mat_rows)

    chips = ""
    if filters_desc:
        chips = '<div class="meta">' + "".join(
            f'<span class="chip">{html.escape(f)}</span>' for f in filters_desc
        ) + "</div>"
    shown = len(jobs)

    table_head = (
        "<thead><tr><th>#</th><th>score</th><th>vaga</th><th>empresa</th>"
        "<th>local</th><th>tipo</th><th>desde</th><th></th></tr></thead>"
    )

    order_note = (
        "ordem: score (ranking do pipeline)"
        if jobs and jobs[0].get("score") is not None
        else "ordem: mais recentes (last_seen)"
    )
    how_html = _how_section() if show_how else ""
    filters_html = _filters_panel_html(_expiring_note(all_jobs, ref_date))

    pane_biz = f"Perfil: {PROFILE_LABELS['biz']} — {order_note}"
    pane_mat = (
        f"Perfil: {PROFILE_LABELS['mat']} — ordem: scores e posições próprios "
        "(materials_score; ranking independente do principal)"
    )

    profiles_html = ""
    if materials is not None:
        profiles_html = (
            '<div class="profiles">'
            f'<button type="button" id="btn-biz" class="active">{PROFILE_LABELS["biz"]}</button>'
            f'<button type="button" id="btn-mat">{PROFILE_LABELS["mat"]}</button>'
            "</div>"
        )
    mat_wrap = ""
    if materials is not None:
        mat_wrap = (
            '<div class="wrap" id="wrap-mat" hidden>'
            '<table id="tbl-mat" data-total="' + str(total) + '">'
            + table_head + "<tbody>" + mat_rows_html + "</tbody></table></div>"
        )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Internship Finder — ranking de vagas elegíveis{(' (2 perfis)' if materials is not None else '')}</title>
<style>
{_CSS}
</style>
</head>
<body data-total="{total}">
<main>
  <header>
    <h1>Internship Finder — ranking de vagas elegíveis</h1>
    <details class="upd"><summary>Informações da atualização</summary>
      <p class="mut small">{html.escape(source_label)} · gerado em {html.escape(generated_at)} UTC · {html.escape(order_note)}</p>
      <p class="mut small">PT-BR: títulos, tipos, país e explicações em português por glossário determinístico (sem traduzir a descrição); o original permanece em &quot;Original&quot; e o anúncio abre na fonte. Score = relevância ao perfil; sinais de candidatura (idioma exigido, work authorization, deadline, problemas) aparecem por vaga e NÃO entram no score de relevância.</p>
    </details>
    <p class="pane src-line"><span data-sv="biz">{html.escape(pane_biz)}</span><span data-sv="mat" hidden>{html.escape(pane_mat)}</span></p>
  </header>
  {profiles_html}
  {how_html}
  <div class="stats">
    {_stats_html(stats, mat_stats=materials_stats)}
  </div>
  {chips}
  {filters_html}
  <details class="compare" id="compare"><summary>Compare opportunities — selecione vagas para ver fatores de desempate <span id="cmp-count" class="f-badge"></span></summary>
    <p class="hint">Marque “comparar” em duas ou mais vagas. A tabela mostra <b>dados</b> (fit, candidatura, vaga, empresa, localização) — não escolhe vencedor por você.</p>
    <div class="cmp-bar" id="cmp-bar">
      <span class="mut small" id="cmp-selected">nenhuma vaga selecionada</span>
      <button type="button" id="cmp-show">comparar selecionadas</button>
      <button type="button" id="cmp-clear">limpar</button>
    </div>
    <div class="cmp-out" id="cmp-out"></div>
  </details>
  <div class="toolbar">
    <input id="q" type="search" placeholder="Buscar por título, empresa ou local…">
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
  <div class="wrap" id="wrap-biz">
  <table id="tbl-biz" data-total="{total}">
{table_head}
    <tbody>
{rows_html}
    </tbody>
  </table>
  </div>
  {mat_wrap}
  <footer>Filtros e ordenação são client-side (JS embutido, sem backend). O score e o score_breakdown exibidos são os do perfil ativo (principal: pipeline; Materials Engineering: materials_score/materials_breakdown próprios). Sinais de candidatura (Candidate Fit / problemas / work authorization / deadline) são objetivos, extraídos do anúncio — nunca inventados; deadline SuccessFactors é validade de feed (fonte), não entra em urgência. Opportunity Intelligence (empresa, benefícios, carreira, Internship→Full-time, turnover, custo de vida) vem de arquivos curados com fonte+data+qualidade (company_intel/) e de evidências do próprio anúncio (salário, modalidade, duração, cidade) — camada de desempate, NUNCA entra no score de relevância; nenhum score de empresa é calculado. Filtros --company/--keyword/--country (se usados) já foram aplicados na geração.</footer>
</main>
<script>
{_JS}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Interface Fase 3/4: ranking completo com filtros/ordenação "
        "client-side, score explicável e segundo perfil Materials Engineering — "
        "gera HTML estático.",
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
        help="Maximo de vagas exibidas por perfil (default: 25; <= 0 -> erro; "
        "a publicacao em GitHub Pages usa um valor alto = todas)",
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
    parser.add_argument(
        "--ref-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Data de referencia para urgencia/deadline (default: data do "
        "run, max(collected_at) do snapshot) — determinismo em testes",
    )
    parser.add_argument(
        "--db-join",
        default="data/jobs.db",
        metavar="PATH",
        help="SQLite jobs.db para Freshness (first_seen/last_seen) no caminho "
        "--input; arquivo ausente nao e erro, apenas omite a juncao "
        "(default: data/jobs.db)",
    )
    parser.add_argument(
        "--company-intel",
        default=None,
        metavar="PATH",
        help="JSON curado de Company Intelligence (default: "
        "company_intel/company_intelligence.json; ausente = secoes "
        "Not available, sem quebrar a pagina)",
    )
    parser.add_argument(
        "--location-intel",
        default=None,
        metavar="PATH",
        help="JSON curado de custo de vida por cidade (default: "
        "company_intel/location_intel.json; ausente = Not available)",
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
        # Fase 6 — Freshness: junta first_seen/last_seen do SQLite (historico
        # da fonte viva) quando disponivel; nunca inventa nem derruba.
        if args.db_join:
            join_path = Path(args.db_join)
            if join_path.exists():
                try:
                    conn = sqlite3.connect(str(join_path))
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT id, first_seen, last_seen FROM jobs"
                    ).fetchall()
                    conn.close()
                except sqlite3.Error:
                    rows = []
                seen = {str(r["id"]): r for r in rows}
                for j in jobs:
                    r = seen.get(str(j.get("id")))
                    if r is not None:
                        j.setdefault("first_seen", r["first_seen"] or j.get("first_seen"))
                        j.setdefault("last_seen", r["last_seen"] or j.get("last_seen"))
    else:
        if not db_path.exists():
            parser.error(f"--db nao encontrado: {db_path}")
        jobs = load_db(db_path)
        source_label = f"{db_path} ({len(jobs)} vagas ativas)"

    # Fase 6 — data de referencia do run (urgencia deterministica por run).
    try:
        ref_date = app_intel.parse_ref_date(args.ref_date)
    except ValueError:
        parser.error(f"--ref-date invalido: {args.ref_date} (use YYYY-MM-DD)")
    if args.ref_date is None:
        ref_date = app_intel.snapshot_ref_date(jobs)

    # Posicao no ranking do pipeline (independente de filtros do CLI): o mapa
    # e construido sobre a lista completa ordenada por score.
    rank_map = {}
    for i, j in enumerate(jobs, 1):
        if j.get("id") is not None:
            rank_map[str(j.get("id"))] = i

    # Fase 4: o MESMO conjunto tambem e ranqueado pelo perfil Materials
    # (score/breakdown proprios; o score do principal nao muda). Filtros do
    # CLI sao ortogonais ao score: aplicam-se igualmente aos dois rankings.
    materials_ranked = rank_materials_jobs(jobs)
    materials_rank_map = {}
    for i, j in enumerate(materials_ranked, 1):
        if j.get("id") is not None:
            materials_rank_map[str(j.get("id"))] = i

    filtered = apply_filters(
        jobs, company=args.company, keyword=args.keyword, country=args.country
    )
    materials_filtered = apply_filters(
        materials_ranked,
        company=args.company, keyword=args.keyword, country=args.country,
    )
    top_jobs = filtered[: args.top]
    mat_top_jobs = materials_filtered[: args.top]

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
        materials=mat_top_jobs,
        materials_rank_map=materials_rank_map,
        materials_stats=_compute_stats(
            materials_filtered, total=len(materials_filtered),
            score_key="materials_score",
        ),
        ref_date=ref_date,
        # Fase 7 — Company & Location Intelligence (arquivos curados; ausencia
        # nunca quebra a pagina — secoes viram Not available).
        company_intel_map=opportunity_intel.load_company_intel(args.company_intel),
        loc_map=opportunity_intel.load_location_intel(args.location_intel),
    )

    out = "-" if args.output == "-" else Path(args.output or DEFAULT_OUTPUT)
    if out == "-":
        sys.stdout.write(page)
    else:
        out.write_text(page, encoding="utf-8")
        print(
            f"interface gerada: {out.resolve()} "
            f"(business {len(top_jobs)}/{len(filtered)} · materials "
            f"{len(mat_top_jobs)}/{len(materials_filtered)} vagas)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())