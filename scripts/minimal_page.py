"""Render minimal da pagina publica (F6; F11 = funil de aplicacao) — top do dia.

Substitui o HTML monolitico da interface.py na publicacao: em vez de
embutir TODAS as vagas elegiveis com breakdowns/fit/intel por vaga (9,5 MB
e crescendo a cada run), a pagina publica mostra o TOP do dia com os
campos de decisao rapida — titulo, empresa, local, score, link de
candidatura e badge visa_friendly (F5) — num card compacto por vaga.

F11 (funil de aplicacao) adiciona ao render:

- **Top-100** (spec F11 T4; era 50 — medicao: 92 KB com 100 vagas reais).
- **data-de por card** (nivel de alemao via ``app_intel.german_level``;
  None -> "none") + badge "🇩🇪 DE exigido" quando required + toggle
  client-side "sem alemão exigido" (mesmo padrao do checkbox 🛂 F5).
- **Regra de EXIBICAO max 2 vagas por empresa** no top (ordem oficial de
  score; a 3a+ ocorrencia da empresa e pulada e o corte e refeito com as
  seguintes). Nao mexe em score nem no JSON/CSV.
- **Seção "🆕 Novas desde ontem"** (diff de IDs contra o snapshot anterior
  do ``data/archive/``): top 10 por score, cards no mesmo formato. Sem
  snapshot usavel a secao e omitida; diff gigante mostra so a contagem.
- **Filtro client-side de pais** (select DE/LU/NL/FI/BE via country_iso)
  e **toggle "só novas de ontem"** (ids do diff; sem diff = toggle oculto).
- **dead_link**: o campo chega do chamador (refresh_daily checa 404/410
  via ``url_liveness.check_liveness`` ANTES de publicar); vagas mortas
  descem do top exibido (a proxima sobe) e ganham badge discreto "🔗
  morta (404/410)" — nunca sao removidas do JSON/CSV (a base de dados).
- **Idade no card** ("há Nd") quando posted_at existe — so display.
- **Seção Materials Engineering** (opcional): top 10 por materials_score
  (``rank_materials_jobs`` — o MESMO ranking proprio do digest), secao
  separada abaixo do ranking principal com header explicando o perfil
  alternativo.

F12 (camada de exibição EN) adiciona ao render — tudo display-only:

- **Linha EN abaixo do título** (``_title_en_line``): tradução DE→EN
  determinística por dicionário (``display_translate.title_en``),
  offline, apenas quando difere do original. O título DE NUNCA é
  substituído.
- **Snippet EN de descrição** (``_snippet_en_fallback``): quando o
  cache ``data/translation_cache.json`` tem tradução para a vaga, o
  resumo exibido é a tradução (marcada "EN · "); sem cache o trecho DE
  como hoje. O cache é runtime (ferramenta on-demand
  ``translate_description.py``), NUNCA escrito pelo cron/pipeline.
- **Rodapé-glossário estático** (``_glossary_html``): 6 termos fixos
  DE→EN, HTML puro, sem JS.

Mortos removidos (F6): ``application_deadline`` (F1: validade do FEED,
nao data real), ``official_page`` (F1: desligado) e os campos de intel do
enrichment LLM (Fase 3, cookie-walled). Nada disso e renderizado. O
badge 🛂 visa_friendly e PRESERVADO (F5) com fallback re-derivado do
``company_intel`` curado (retrocompat snapshots pre-F5).

Salario quando citado no anuncio (evidencia textual — nunca inventado;
mesma regra da interface.py/opportunity_intel). CSS inline minimo, dark
mode default, sem framework; mobile-first com cards. Vanilla JS de
filtro (busca + 🛂 + sem-DE + pais + novas) — mesmo desenho F6.

Ordenacao: score do pipeline, server-side (a lista ja vem ordenada; o
sort e defensivo). Nenhum JS de ordenacao. JSON/CSV completos NAO
mudam: sao a base de dados, nao a interface.

A mecanica de deploy e intocada (publish_pages.publish_html atomico,
``check_public_safe``, clone gh-pages, push so do index.html): este
modulo so entrega o CONTEUDO do index.html.
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

__all__ = [
    "PAGE_TOP", "PAGE_TARGET_BYTES", "COMPANY_MAX_CARDS",
    "NEW_SINCE_SECTION_TOP", "MATERIALS_SECTION_TOP",
    "GLOSSARY_TERMS",
    "render_minimal_html", "render_minimal_html_from_file",
    "apply_company_cap",
]

# Quantas vagas a pagina publica mostra (F6: 50; F11 T4: 100 — o tamanho
# real medido com 100 vagas do snapshot 04/10 e 92 KB, dentro do alvo).
PAGE_TOP = 100

# Maximo de vagas EXIBIDAS por empresa no top (spec F11 T4 — regra de
# EXIBICAO: nao altera score/ranking/JSON/CSV; o corte e refeito com as
# vagas seguintes da ordem oficial).
COMPANY_MAX_CARDS = 2

# Top da secao 🆕 (spec F11 T1: top 10 por score) e da secao Materials
# (spec F11 T4 opcional: top 10 por materials_score).
NEW_SINCE_SECTION_TOP = 10
MATERIALS_SECTION_TOP = 10

# Orcamento de tamanho da pagina (spec: alvo <=100KB, cap duro 150KB
# verificado no teste). O render e' size-aware: se o conteudo real
# estourar o alvo, corta campos decorativos (snippet de descricao)
# antes de cortar vagas.
PAGE_TARGET_BYTES = 100_000
PAGE_HARD_CAP_BYTES = 150_000

# Schemes aceitos em href (mesma regra P2.3 da interface.py — so http/https).
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def _safe_url(value) -> str | None:
    """URL http/https valida para href (mesma regra da interface.py)."""
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


def _esc(value) -> str:
    """Escape HTML total (texto e atributos)."""
    return _html.escape(str(value), quote=True)


def _fmt_score(value) -> str:
    """Score como NN.N (compacto)."""
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_salary(salary: dict | None) -> str:
    """Salario citado no anuncio (evidencia textual; nunca inventado)."""
    if not salary:
        return ""
    period = salary.get("period")
    suffix = f"/{period}" if period else ""
    if salary.get("min") is not None and salary.get("max") is not None:
        if float(salary["min"]) == float(salary["max"]):
            return f"€{salary['min']:g}{suffix}"
        return f"€{salary['min']:g}–€{salary['max']:g}{suffix}"
    return ""


def _visa_friendly(job: dict, company_entry: dict | None) -> bool:
    """Sinal visa_friendly da EMPRESA (F5): campo do pipeline com fallback
    re-derivado do company_intel curado (retrocompat snapshots pre-F5)."""
    if "visa_friendly" in job:
        return bool(job.get("visa_friendly"))
    if company_entry:
        try:
            from internship_finder import opportunity_intel
            return bool(opportunity_intel.visa_friendly(company_entry))
        except Exception:  # noqa: BLE001 — view best-effort
            return False
    return False


def _short_location(job: dict) -> str:
    """Cidade (primeira parte da location), como no digest."""
    loc = str(job.get("location") or "").strip()
    if not loc:
        return "—"
    return loc.split(",", 1)[0].strip() or "—"


# F7: bandeiras dos paises-alvo (custo ~0 — 1 emoji no meta do card).
# Fora da lista: sem bandeira (o filtro de pais continua sendo o corte
# oficial do pipeline; a bandeira e apenas viz).
COUNTRY_FLAGS = {
    "de": "🇩🇪", "lu": "🇱🇺", "nl": "🇳🇱", "fi": "🇫🇮", "be": "🇧🇪",
}


def _country_badge(job: dict) -> str:
    """F7: ISO/bandeira do pais da vaga quando NAO e DE (DE e o default

    visual — a pagina e majoritariamente alema; bandeira so no canal
    secundario LU/NL/FI/BE para destacar a origem). Custo ~0: 2 chars.
    """
    iso = str(job.get("country_iso") or "").strip().lower()
    if not iso or iso == "de":
        return ""
    flag = COUNTRY_FLAGS.get(iso)
    return f" {flag} {iso.upper()}" if flag else f" {iso.upper()}"


def _snippet(job: dict, limit: int = 140) -> str:
    """Trecho curto da descricao ORIGINAL (sem traducao/inferencia)."""
    text = " ".join(str(job.get("description") or "").split())
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")


# F12 T1 — linha EN abaixo do título: deterministica e OFFLINE (dicionario
# display DE->EN em ``display_translate.title_en``; sem rede, sem LLM). O
# título DE NUNCA e substituido — a linha EN so entra quando a traducao
# DIFERE do original (já-EN/fora-do-dicionario nao ganham linha falsa).
def _title_en_line(job: dict) -> str:
    """HTML da linha 'EN: <título traduzido>' (vazio quando não se aplica)."""
    original = job.get("title")
    if not original:
        return ""
    try:
        from internship_finder import display_translate
        translated = display_translate.title_en(original)
    except Exception:  # noqa: BLE001 — view best-effort
        return ""
    if not translated or translated == str(original):
        return ""
    return f'<div class="en">{_esc(f"EN: {translated}")}</div>'


# F12 T2 — snippet de descricao: quando existe traducao em cache para a
# vaga, o resumo exibido é a tradução EN (marcada "EN · ") no lugar do
# trecho DE. Sem cache -> trecho DE como hoje (a pagina nunca promete
# traducao imediata — o cache e preenchido offline pela ferramenta
# on-demand e aparece no render seguinte).
def _snippet_en_fallback(job: dict, cache: dict | None,
                        limit: int = 140) -> tuple[str, bool]:
    """(texto_do_snippet, eh_traducao) — EN em cache prioriza o DE."""
    if cache:
        jid = str(job.get("id") or "")
        if jid:
            try:
                from internship_finder import display_translate
                cached = display_translate.cached_translation(cache, jid)
            except Exception:  # noqa: BLE001 — view best-effort
                cached = None
            if cached:
                text = " ".join(cached.split())
                snip = text[:limit] + ("…" if len(text) > limit else "")
                return snip, True
    return _snippet(job, limit), False


# F12 T4 — rodapé-glossário estático (HTML puro, sem JS, sem rede): os 6
# termos fixos da spec. Vive no fim da página, discreto; idêntico em todo
# render (offline por construção).
GLOSSARY_TERMS = [
    ("Praktikum", "internship"),
    ("Werkstudent", "working student"),
    ("Pflichtpraktikum", "mandatory internship"),
    ("Beschaffung", "procurement"),
    ("Einkauf", "purchasing"),
    ("Logistik", "logistics"),
]


def _glossary_html() -> str:
    parts = " · ".join(
        f"{_esc(de)} = {_esc(en)}" for de, en in GLOSSARY_TERMS
    )
    return (
        '<p class="gloss">Glossário DE→EN: ' + parts + "</p>"
    )


def _german_level_attr(job: dict) -> str:
    """data-de do card: 'required'|'preferred'|'plus'|'none' (F11 T2).

    MESMO detector do fit da interface (app_intel.german_level sobre
    titulo+descricao); None = sem mencao -> 'none'. Best-effort: falha
    de import/parse -> 'none' (nunca derruba o render).
    """
    try:
        from internship_finder import app_intel
        text = f"{job.get('title') or ''} {job.get('description') or ''}"
        gl = app_intel.german_level(text)
        return gl.level if gl is not None else "none"
    except Exception:  # noqa: BLE001 — view best-effort
        return "none"


def _parse_posted_at(value) -> datetime | None:
    """posted_at ISO (com Z ou offset) -> datetime UTC-aware; None em falha."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _age_days_text(job: dict, ref: datetime) -> str:
    """Badge de idade 'há Nd' quando posted_at existe (F11 T3; so display)."""
    dt = _parse_posted_at(job.get("posted_at"))
    if dt is None:
        return ""
    days = (ref - dt).days
    if days < 0:
        return ""  # posted no futuro (clock skew) — nao exibe idade falsa
    if days == 0:
        return "há <1d"
    return f"há {days}d"


def apply_company_cap(jobs: list[dict], *, limit: int = PAGE_TOP,
                      max_per_company: int = COMPANY_MAX_CARDS) -> list[dict]:
    """Corte do top exibido com max N vagas por empresa (F11 T4; pura).

    Percorre a ordem oficial (ja ordenada por score): a 1a e 2a vagas de
    cada empresa entram, a 3a+ e pulada e a vaga seguinte do ranking
    preenche a vaga. Regra de EXIBICAO — nao altera scores, nao reordena
    o que entrou, nao toca o JSON/CSV. Deterministica.
    """
    shown: list[dict] = []
    counts: dict[str, int] = {}
    for job in jobs:
        if len(shown) >= limit:
            break
        company = str(job.get("company") or "").strip().casefold() or "—"
        if counts.get(company, 0) >= max_per_company:
            continue
        counts[company] = counts.get(company, 0) + 1
        shown.append(job)
    return shown


# F13 — flags de TITULO para os toggles client-side (puras; casefold). O
# ``employment_type`` NAO serve para Werkstudent: medido 06/10, 0
# ocorrências no campo vs 972 títulos contendo "werkstudent" — o filtro é
# por TÍTULO, mesmo padrão do f-de (german_level) e f-vf (visa_friendly).
# data/BI: keywords por PALAVRA INTEIRA ("bi" como substring casaria
# "Elektromobilität"/"E-Mobility" — 47 FPs medidos no dataset real; com
# \b casam 441 títulos hoje, sem FP).
_DATA_BI_KEYWORDS = (
    "data", "bi", "business intelligence", "analytics", "analyst",
    "tableau", "power bi", "sql", "dashboard", "reporting",
)
_DATA_BI_RE = re.compile(
    "|".join(
        (rf"\b{re.escape(k)}\b" if " " not in k else re.escape(k))
        for k in _DATA_BI_KEYWORDS
    )
)


def is_werkstudent_title(job: dict) -> bool:
    """Título menciona Werkstudent (casefold; F13 toggle f-ws)."""
    return "werkstudent" in str(job.get("title") or "").casefold()


def is_data_bi_title(job: dict) -> bool:
    """Título casa keywords de data/BI (palavra inteira; F13 toggle f-data)."""
    return bool(_DATA_BI_RE.search(str(job.get("title") or "").casefold()))


def _card(rank: int, job: dict, *, visa: bool, salary: str,
          snippet: str, apply_href: str | None, job_href: str | None,
          de_level: str, age: str, dead: bool = False,
          is_new: bool = False, score_override=None,
          en_title_html: str = "", snippet_is_en: bool = False) -> str:
    """Card compacto de uma vaga (mobile-first) com atributos F11.

    F12: ``en_title_html`` = linha EN abaixo do título (HTML pronto, vazio
    quando não se aplica); ``snippet_is_en`` marca o snippet como tradução
    (classe ``en`` + prefixo honesto "EN · ").

    F13: ``data-ws``/``data-data`` = flags de título para os toggles
    client-side (mesma regra casefold do JS; medição F13: 972 títulos
    contêm "werkstudent", o campo ``employment_type`` tem 0 ocorrências —
    por isso o filtro é por TÍTULO, como o f-de por german_level).
    """
    vf = ' <span class="vf" title="Empresa com política de visto (visa_policy: explicit_support ou unclear)">🛂</span>' if visa else ""
    if de_level == "required":
        vf += ' <span class="de" title="Anúncio exige alemão (german_level: required)">🇩🇪 DE exigido</span>'
    if dead:
        vf += ' <span class="dead" title="URL retornou 404/410 no check de vitalidade — a vaga provavelmente foi preenchida/removida">🔗 morta</span>'
    if is_new:
        vf += ' <span class="newb">🆕</span>'
    title = _esc(job.get("title") or "(sem título)")
    inner = f'<a class="t" href="{_esc(job_href)}" target="_blank" rel="noopener">{title}</a>{vf}' if job_href else f'<span class="t">{title}</span>{vf}'
    meta_bits = [
        _esc(job.get("company") or "—"),
        _esc(_short_location(job) + _country_badge(job)),
    ]
    if salary:
        meta_bits.append(f'<b class="sal">{_esc(salary)}</b>')
    if age:
        meta_bits.append(f'<span class="age">{_esc(age)}</span>')
    meta = ' · '.join(meta_bits)
    score = _fmt_score(score_override if score_override is not None
                      else job.get("score"))
    btn = ""
    if apply_href:
        btn = f'<a class="btn" href="{_esc(apply_href)}" target="_blank" rel="noopener">candidatar-se ↗</a>'
    elif job_href:
        btn = f'<a class="btn" href="{_esc(job_href)}" target="_blank" rel="noopener">abrir vaga ↗</a>'
    if snippet and snippet_is_en:
        snip = f'<p class="d en">{_esc("EN · " + snippet)}</p>'
    elif snippet:
        snip = f'<p class="d">{_esc(snippet)}</p>'
    else:
        snip = ""
    qtext = " ".join(x for x in (job.get("title"), job.get("company"),
                                 job.get("location")) if x)
    return (
        f'<li class="c{" vf-on" if visa else ""}{" dead-on" if dead else ""}"'
        f' data-s="{score}"'
        f' data-vf="{1 if visa else 0}"'
        f' data-de="{_esc(de_level)}"'
        f' data-iso="{_esc(str(job.get("country_iso") or "").strip().lower())}"'
        f' data-new="{1 if is_new else 0}"'
        f' data-ws="{1 if is_werkstudent_title(job) else 0}"'
        f' data-data="{1 if is_data_bi_title(job) else 0}"'
        f' data-q="{_esc(qtext)}">'
        f'<span class="r">{rank}</span><span class="s">{score}</span>'
        f'<div class="bd">{inner}{en_title_html}<div class="m">{meta}</div>{snip}{btn}</div></li>'
    )


_CSS = """body{margin:0;background:#10151b;color:#e6edf3;font:16px/1.45 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px 14px 40px}
h1{font-size:1.05rem;margin:0 0 2px}
h2{font-size:.95rem;margin:26px 0 4px;color:#c8d3dd}
.p{color:#9aa7b4;font-size:.8rem;margin:2px 0 12px}
.p2{color:#9aa7b4;font-size:.78rem;margin:0 0 10px}
.bar{display:flex;gap:8px;margin:0 0 14px;flex-wrap:wrap;align-items:center}
.bar input[type=search]{flex:1 1 160px;min-width:0;padding:8px 12px;border:1px solid #2a343e;border-radius:8px;background:#192027;color:#e6edf3;font-size:16px}
.bar input[type=checkbox]{accent-color:#4da3ff}
.bar label{font-size:.82rem;color:#9aa7b4;white-space:nowrap}
.bar select{padding:7px 10px;border:1px solid #2a343e;border-radius:8px;background:#192027;color:#e6edf3;font-size:.85rem}
ol{list-style:none;margin:0;padding:0}
li.c{display:flex;gap:10px;padding:12px 10px;border-bottom:1px solid #2a343e}
.r{flex:0 0 24px;color:#9aa7b4;font-size:.75rem;font-variant-numeric:tabular-nums;padding-top:3px}
.s{flex:0 0 34px;font-weight:700;font-size:.95rem;font-variant-numeric:tabular-nums;color:#9fd8b4;padding-top:1px}
.bd{flex:1;min-width:0}
.t{font-weight:600;color:#e6edf3;text-decoration:none}
a.t:visited{color:#c8d3dd}
a.t:hover{text-decoration:underline}
.vf{font-size:.8rem}
.de{font-size:.72rem;color:#e8cf8a}
.dead{font-size:.72rem;color:#d98282}
.newb{font-size:.72rem}
.age{font-size:.78rem;color:#9aa7b4}
.m{color:#9aa7b4;font-size:.82rem;margin-top:2px}
.m .sal{color:#e8cf8a;font-weight:600}
.d{color:#8b98a5;font-size:.8rem;margin:5px 0 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.d.en{color:#8fb8d8}
.en{color:#9fb3c8;font-size:.78rem;margin:1px 0 0}
.gloss{color:#7d8a97;font-size:.72rem;margin:6px 0 0;line-height:1.5}
.btn{display:inline-block;margin-top:7px;padding:6px 14px;border:1px solid #1c7a4a;color:#9fd8b4;border-radius:999px;font-size:.82rem;text-decoration:none}
.btn:hover{background:#1c7a4a;color:#10151b}
.f{color:#9aa7b4;font-size:.72rem;margin:10px 0 0}
@media(min-width:640px){main{padding:24px 20px 56px}h1{font-size:1.25rem}}
"""

_JS = """(function(){var q=document.getElementById('q'),vf=document.getElementById('f-vf'),n=document.getElementById('n'),de=document.getElementById('f-de'),co=document.getElementById('f-country'),nw=document.getElementById('f-new'),ws=document.getElementById('f-ws'),da=document.getElementById('f-data');
if(!q)return;function f(){var t=q.value.trim().toLowerCase(),v=vf&&vf.checked,d=de&&de.checked,iso=co&&co.value,nwv=nw&&nw.checked,wsv=ws&&ws.checked,dav=da&&da.checked,c=0;
document.querySelectorAll('li.c').forEach(function(li){var ok=!t||li.getAttribute('data-q').toLowerCase().indexOf(t)>-1;
if(v)ok=ok&&li.getAttribute('data-vf')==='1';
if(d)ok=ok&&li.getAttribute('data-de')!=='required';
if(iso)ok=ok&&li.getAttribute('data-iso')===iso;
if(nwv)ok=ok&&li.getAttribute('data-new')==='1';
if(wsv)ok=ok&&li.getAttribute('data-ws')!=='1';
if(dav)ok=ok&&li.getAttribute('data-data')==='1';
li.style.display=ok?'':'none';if(ok)c++;});if(n)n.textContent=c;}q.addEventListener('input',f);if(vf)vf.addEventListener('change',f);if(de)de.addEventListener('change',f);if(co)co.addEventListener('change',f);if(nw)nw.addEventListener('change',f);if(ws)ws.addEventListener('change',f);if(da)da.addEventListener('change',f);})();
"""


def _cards_section(jobs: list[dict], *, company_intel_map: dict | None,
                    new_ids: set[str] | None, dead_ids: set[str] | None,
                    ref: datetime, company_entry_cache: dict,
                    rank_start: int = 1, score_key: str = "score",
                    with_snippet: bool = True,
                    translation_cache: dict | None = None) -> list[str]:
    """Cards de uma lista JA CORTADA (mesmo formato para todas as secoes).

    ``score_key``: campo exibido na coluna de score — "score" (perfil
    principal / secoes de novas) ou "materials_score" (secao Materials,
    que e um ranking PROPRIO; exibir o score do perfil principal la
    seria desinformacao). ``with_snippet``: False = sem o resumo de
    descricao (degradacao size-aware — campo decorativo).

    F12: ``translation_cache`` (dict, default None = sem cache) faz o
    snippet da descricao usar a traducao EN em cache quando existir —
    marcada como tradução ("EN · "). Best-effort: sem entrada, snippet
    DE como hoje. A linha EN do título é independente (offline).
    """
    rows: list[str] = []
    new_ids = new_ids or set()
    dead_ids = dead_ids or set()
    for i, job in enumerate(jobs, rank_start):
        jid = str(job.get("id") or "")
        entry = None
        if company_intel_map is not None:
            if jid in company_entry_cache:
                entry = company_entry_cache[jid]
            else:
                try:
                    from internship_finder import opportunity_intel
                    entry = opportunity_intel.company_intel_for(job, company_intel_map)
                except Exception:  # noqa: BLE001 — view best-effort
                    entry = None
                company_entry_cache[jid] = entry
        visa = _visa_friendly(job, entry)
        try:
            from internship_finder import opportunity_intel
            salary = _fmt_salary(opportunity_intel.job_salary(job))
        except Exception:  # noqa: BLE001
            salary = ""
        job_href = _safe_url(job.get("url"))
        raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}
        # Botão honesto: "candidatar-se" SOMENTE com raw.apply_url real;
        # sem ele, o botão é "abrir vaga" (job.url). Nenhum rótulo de ação
        # direta aponta para uma URL que não é de candidatura.
        apply_href = _safe_url(raw.get("apply_url"))
        if with_snippet:
            snippet, snippet_is_en = _snippet_en_fallback(job, translation_cache)
        else:
            snippet, snippet_is_en = "", False
        rows.append(_card(
            i, job, visa=visa, salary=salary,
            snippet=snippet, snippet_is_en=snippet_is_en,
            apply_href=apply_href, job_href=job_href,
            de_level=_german_level_attr(job), age=_age_days_text(job, ref),
            dead=jid in dead_ids, is_new=jid in new_ids,
            score_override=(job.get(score_key)
                            if score_key != "score" else None),
            en_title_html=_title_en_line(job),
        ))
    return rows


def render_minimal_html(
    jobs: list[dict],
    *,
    total_eligible: int,
    generated_at: str,
    top: int = PAGE_TOP,
    company_intel_map: dict | None = None,
    new_since_ids: set[str] | None = None,
    dead_link_ids: set[str] | None = None,
    materials: list[dict] | None = None,
    with_snippets: bool = True,
    translation_cache: dict | None = None,
    watchlist_events: list[dict] | None = None,
) -> str:
    """HTML minimo do top do dia (self-contained; ~90-100 KB tipico).

    ``jobs``: lista JA ordenada pelo score do pipeline (ordem oficial). A
    pagina nao re-ranqueia nada — apenas enumera o topo. ``total_eligible``
    e o tamanho do conjunto elegivel inteiro (o rodape informa que a
    pagina mostra o top-N e o resto vive no JSON/CSV completos).

    F11: ``new_since_ids`` = ids novos vs o snapshot anterior (secao 🆕 +
    data-new + toggle); None/'' = sem diff (secao/toggle ausentes).
    ``dead_link_ids`` = ids com URL 410/404 confirmado (badge + descem do
    topo exibido). ``materials`` = ranking materials JA computado e
    cortado pelo chamador (secao opcional); None = sem secao.

    F12: ``translation_cache`` = cache de traducoes de descricao
    (``display_translate.load_translation_cache``; default None = sem
    cache, snippet DE como hoje). Best-effort e display-only: afeta SO o
    snippet exibido, nunca o JSON/CSV. A linha EN do título e o glossário
    do rodapé sao OFFLINE (sempre presentes).

    F13: ``watchlist_events`` = vagas novas de ontem em empresas da
    watchlist (saida de ``ranking_digest.radar_events``; None = sem
    watchlist/radar -> secao 🎯 ausente). Seção equivalente à do digest,
    com cards (todos os eventos, não só o top-5 — o "+N outras" do
    digest promete "ver página"). Regra de EXIBIÇÃO: eventos já
    exibidos na seção 🆕 não são duplicados aqui.

    Size-aware (contrato da docstring desde a F6, agora real): com
    ``with_snippets=True`` o render e' montado com snippets; o chamador
    ``render_size_aware`` remonta sem snippets (campo DECORATIVO) quando
    o resultado estoura o alvo de bytes — nunca vagas a menos.
    """
    ref = datetime.now(UTC)
    dead_ids = set(dead_link_ids or set())
    # F11 T3: vagas mortas descem do top exibido (a seguinte sobe) — o
    # corte com a regra 2/empresa percorre a lista JA sem as mortas.
    # Regra de exibicao; o JSON/CSV (base de dados) e intocavel.
    alive = [j for j in jobs if str(j.get("id") or "") not in dead_ids]
    shown = apply_company_cap(alive, limit=top)
    new_ids = set(new_since_ids or set())
    entry_cache: dict = {}
    body = "\n".join(_cards_section(
        shown, company_intel_map=company_intel_map, new_ids=new_ids,
        dead_ids=dead_ids, ref=ref, company_entry_cache=entry_cache,
        with_snippet=with_snippets, translation_cache=translation_cache,
    ))
    n_vf = sum(1 for j in shown if _visa_friendly(
        j, entry_cache.get(str(j.get("id") or ""))))

    # Seção 🆕 — top 10 por score ENTRE as novas (a ordem oficial ja e
    # por score; sem snapshot usavel a secao e omitida, sem erro).
    new_section = ""
    if new_ids:
        new_jobs = [j for j in alive if str(j.get("id") or "") in new_ids]
        new_section_jobs = new_jobs[:NEW_SINCE_SECTION_TOP]
        if len(new_ids) > len(new_section_jobs):
            extra = f" (+{len(new_ids) - len(new_section_jobs)} outras novas)"
        else:
            extra = ""
        new_cards = "\n".join(_cards_section(
            new_section_jobs, company_intel_map=company_intel_map,
            new_ids=new_ids, dead_ids=dead_ids, ref=ref,
            company_entry_cache=entry_cache, rank_start=1,
            score_key="score", with_snippet=with_snippets,
            translation_cache=translation_cache,
        ))
        new_section = (
            f'<h2>🆕 Novas desde ontem — {len(new_ids)} nova(s){extra}</h2>'
            f'{new_cards}'
        )

    # Seção 🎯 Empresas-alvo (F13) — vagas novas de ontem em empresas da
    # watchlist. Cards na ordem oficial (o radar NÃO reordena nada); TODOS
    # os eventos entram aqui (o digest lista 5 e promete "ver página").
    # Igual ao digest: um evento pode aparecer na 🆕 E aqui (seções com
    # critérios diferentes — 🆕 é "nova", 🎯 é "nova E alvo"; a página
    # espelha essa semântica, sem dedup entre seções).
    # Exibição pura: zero impacto em score/ranking/JSON/CSV.
    watch_section = ""
    if watchlist_events:
        wl_cards_jobs = list(watchlist_events)
        wl_cards = "\n".join(_cards_section(
            wl_cards_jobs, company_intel_map=company_intel_map,
            new_ids=new_ids, dead_ids=dead_ids, ref=ref,
            company_entry_cache=entry_cache, rank_start=1,
            score_key="score", with_snippet=with_snippets,
            translation_cache=translation_cache,
        ))
        watch_section = (
            f'<h2>🎯 Empresas-alvo — {len(wl_cards_jobs)} nova(s) nas '
            f'empresas que você acompanha</h2>'
            f'{wl_cards}'
        )

    # Seção Materials — perfil alternativo, ranking proprio (digest ja
    # usa o MESMO rank_materials_jobs); top 10 por materials_score.
    materials_section = ""
    if materials:
        mat_cards = "\n".join(_cards_section(
            materials, company_intel_map=company_intel_map,
            new_ids=new_ids, dead_ids=dead_ids, ref=ref,
            company_entry_cache=entry_cache, rank_start=1,
            score_key="materials_score", with_snippet=with_snippets,
            translation_cache=translation_cache,
        ))
        materials_section = (
            '<h2>🧪 Materials Engineering — top 10 (perfil alternativo)</h2>'
            '<p class="p2">Ranking próprio para Materials Engineering '
            '(mesmas vagas elegíveis, pesos distintos dos de Supply '
            'Chain). O score à esquerda é o do perfil Materials.</p>'
            + mat_cards
        )

    footer_note = (
        f"Top {len(shown)} de {total_eligible} vagas elegíveis · {n_vf} com 🛂 "
        "(empresa com política de visto) · ranking, JSON e CSV completos "
        "são gerados pelo pipeline no VPS"
    )
    # F12 T4 — rodapé-glossário estático (offline; sempre presente).
    glossary = _glossary_html()
    # Select de pais SEM bandeiras: o contrato da F7 e "DE e o default visual
    # — bandeira so no canal secundario"; o select e um controle, nao um
    # card (e o emoji DE no select poluiria o documento inteiro).
    country_opts = "".join(
        f'<option value="{iso}">{iso.upper()}</option>'
        for iso in COUNTRY_FLAGS
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Internship Finder — top {len(shown)} do dia</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>Internship Finder — top do dia</h1>
<p class="p">{_esc(generated_at)} UTC · ordenado pelo score do pipeline · 🛂 = empresa com política de visto</p>
<div class="bar">
<input id="q" type="search" placeholder="Buscar título, empresa, local…">
<label><input type="checkbox" id="f-vf"> 🛂 só visa friendly</label>
<label><input type="checkbox" id="f-de"> sem alemão exigido</label>
<select id="f-country"><option value="">todos os países</option>{country_opts}</select>
{'<label><input type="checkbox" id="f-new"> só novas de ontem</label>' if new_ids else ''}
<label><input type="checkbox" id="f-ws"> sem Werkstudent</label>
<label><input type="checkbox" id="f-data"> Data/BI</label>
</div>
<ol id="list">
{body}
</ol>
{new_section}
{watch_section}
{materials_section}
<p class="f">{_esc(footer_note)}</p>
{glossary}
</main>
<script>{_JS}</script>
</body>
</html>
"""


def render_size_aware(
    jobs: list[dict],
    *,
    total_eligible: int,
    generated_at: str,
    top: int = PAGE_TOP,
    company_intel_map: dict | None = None,
    new_since_ids: set[str] | None = None,
    dead_link_ids: set[str] | None = None,
    materials: list[dict] | None = None,
    translation_cache: dict | None = None,
    watchlist_events: list[dict] | None = None,
) -> str:
    """``render_minimal_html`` com degradacao progressiva de tamanho (F11).

    O snippet de descricao e o campo DECORATIVO do card (resumo de 140
    chars; o botao abre o anuncio completo). Se o render COM snippets
    estoura ``PAGE_TARGET_BYTES``, remonta SEM snippets — nunca corta
    vagas a menos e nunca estoura o cap duro (assert do teste).

    F12: o snippet remontado sem snippets tambem perde a traducao EN
    (ela vive no snippet) — a linha EN do título e o glossário permanecem
    (nao sao campos decorativos). ``translation_cache`` e passado ao
    render em ambas as montagens (best-effort).

    F13: ``watchlist_events`` repassado as duas montagens (a secao 🎯
    nao e campo decorativo — sobrevive a remontagem sem snippets).
    """
    html = render_minimal_html(
        jobs, total_eligible=total_eligible, generated_at=generated_at,
        top=top, company_intel_map=company_intel_map,
        new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
        materials=materials, with_snippets=True,
        translation_cache=translation_cache,
        watchlist_events=watchlist_events,
    )
    if len(html.encode("utf-8")) > PAGE_TARGET_BYTES:
        html = render_minimal_html(
            jobs, total_eligible=total_eligible, generated_at=generated_at,
            top=top, company_intel_map=company_intel_map,
            new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
            materials=materials, with_snippets=False,
            translation_cache=translation_cache,
            watchlist_events=watchlist_events,
        )
    return html


def _previous_snapshot(archive_root: Path) -> list[dict] | None:
    """Snapshot anterior do archive via ``ranking_digest`` (REUSO da
    mecanica — mesma selecao do digest; nao duplicada aqui).

    Devolve o ranking anterior (lista, possivelmente vazia = estado
    real) ou ``None`` (sem snapshot usavel: ausente/corrompido) — o
    chamador omite a secao 🆕. Import lazy: em repos de fixture sem
    scripts/ranking_digest.py (testes de publish) o diff simplesmente
    nao monta, sem erro.
    """
    try:
        import ranking_digest  # scripts/ vive no sys.path do subprocesso
        prev_path = ranking_digest._latest_archive_eligible(archive_root)
        if not prev_path:
            return None
        return ranking_digest.load_ranking_or_none(prev_path)
    except Exception:  # noqa: BLE001 — diff e best-effort, nunca erro
        return None


def render_minimal_html_from_file(
    path: Path, *, top: int = PAGE_TOP,
    company_intel_map: dict | None = None,
    archive_root: Path | None = None,
    dead_link_ids: set[str] | None = None,
    include_materials: bool = True,
    translation_cache_path: Path | str | None = None,
    watchlist_path: Path | str | None = None,
) -> str:
    """Le o eligible_jobs.json e devolve o HTML minimo do topo.

    F11: computa o diff de IDs contra o snapshot anterior do
    ``data/archive/`` (maior timestamp < agora; mecanica reutilizada do
    ranking_digest) quando ``archive_root`` e dado. Best-effort: snapshot
    corrompido/ausente -> secao 🆕 omitida (nunca erro).

    F12: ``translation_cache_path`` = cache de traducoes de descricao
    (default None = desligado; o CLI passa ``data/translation_cache.json``).
    Best-effort: ausente/corrompido -> cache vazio, snippet DE como hoje.

    F13: ``watchlist_path`` = ``config/company_watchlist.json`` (default
    None = sem secao 🎯). O radar REUSA o mesmo diff de IDs da secao 🆕
    (uma unica leitura do snapshot) e cruza com a watchlist — sem coletor
    novo, sem HTTP. Best-effort: watchlist ausente/corrompida ou falha
    qualquer -> secao 🎯 omitida, nunca erro.
    """
    with path.open(encoding="utf-8") as fh:
        jobs = json.load(fh)
    if not isinstance(jobs, list):
        raise ValueError(f"formato inesperado em {path}: esperado lista de vagas")
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    translation_cache: dict = {}
    if translation_cache_path:
        try:
            from internship_finder import display_translate
            translation_cache = display_translate.load_translation_cache(
                translation_cache_path)
        except Exception:  # noqa: BLE001 — cache e best-effort, nunca erro
            translation_cache = {}

    new_ids: set[str] | None = None
    watchlist_events: list[dict] | None = None
    if archive_root is not None:
        prev = _previous_snapshot(archive_root)
        if prev is not None:
            cur_ids = {str(j.get("id")) for j in jobs
                       if isinstance(j, dict) and j.get("id")}
            new_ids = cur_ids - {str(j.get("id")) for j in prev}
            # F13 — radar: cruza o MESMO diff com a watchlist (best-effort;
            # reuso integral do ranking_digest — nenhuma logica duplicada).
            if watchlist_path and new_ids:
                try:
                    import ranking_digest as _rg
                    wl = _rg.load_watchlist(watchlist_path)
                    if wl:
                        diff = _rg.new_since_previous(
                            jobs if isinstance(jobs, list) else [],
                            prev)
                        watchlist_events = _rg.radar_events(diff, jobs, wl)
                except Exception:  # noqa: BLE001 — radar nunca derruba render
                    watchlist_events = None

    materials: list[dict] | None = None
    if include_materials:
        try:
            from internship_finder.materials_ranking import rank_materials_jobs
            materials = rank_materials_jobs(jobs)[:MATERIALS_SECTION_TOP]
        except Exception:  # noqa: BLE001 — secao opcional nunca derruba
            materials = None

    return render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=generated,
        top=top, company_intel_map=company_intel_map,
        new_since_ids=new_ids, dead_link_ids=dead_link_ids,
        materials=materials, translation_cache=translation_cache,
        watchlist_events=watchlist_events,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI (mesmo contrato da interface.py: --input/--top/--output).

    Chamado pelo ``publish_pages.render_ranking_html`` como subprocesso com
    ``--input`` RELATIVO (cwd = raiz do repo): nenhum caminho absoluto da
    VPS entra na pagina. ``--output -`` imprime no stdout (uso manual).

    F11: ``--archive DIR`` habilita o diff de IDs contra o snapshot anterior
    (default: data/archive do repo — o publish repassa o caminho relativo).
    ``--dead-list FILE`` recebe os ids mortos apurados pelo estagio de
    vitalidade do refresh (um id por linha; ausente = nenhuma marca).

    F12: ``--translation-cache PATH`` habilita o snippet EN das descricoes
    com traducao em cache (default: data/translation_cache.json; '' desliga).
    Best-effort: arquivo ausente/corrompido = snippet DE como hoje. A
    ferramenta que PREENCHE o cache e ``scripts/translate_description.py``
    (on-demand, fora do cron); este render so LE.
    """
    import argparse

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    parser = argparse.ArgumentParser(
        description="Render minimo da pagina publica (F6/F11/F12): top do "
                    "dia, mobile-first, dark, self-contained.",
    )
    parser.add_argument("--input", default="data/eligible_jobs.json",
                        metavar="PATH", help="JSON ranqueado do run")
    parser.add_argument("--top", type=int, default=PAGE_TOP, metavar="N",
                        help=f"maximo de vagas (default {PAGE_TOP})")
    parser.add_argument("--output", default="-", metavar="PATH",
                        help="arquivo de saida ('-' = stdout)")
    parser.add_argument("--company-intel", default=None, metavar="PATH",
                        help="JSON curado de company intel (default: "
                             "company_intel/company_intelligence.json do "
                             "repo; ausente = sem fallback do badge)")
    parser.add_argument("--archive", default="data/archive", metavar="DIR",
                        help="raiz do archive de snapshots para o diff de "
                             "novas-de-ontem ('' desliga a seção 🆕)")
    parser.add_argument("--dead-list", default=None, metavar="PATH",
                        help="arquivo com ids de vagas mortas (404/410), "
                             "um por linha (estagio url_liveness)")
    parser.add_argument("--translation-cache", default="data/translation_cache.json",
                        metavar="PATH",
                        help="cache de traducoes EN de descricao "
                             "(data/translation_cache.json da F12; '' "
                             "desliga o snippet EN)")
    parser.add_argument("--watchlist", default="config/company_watchlist.json",
                        metavar="PATH",
                        help="watchlist de empresas-alvo (F13; default "
                             "config/company_watchlist.json do repo; '' "
                             "desliga a seção 🎯)")
    args = parser.parse_args(argv)

    if args.top <= 0:
        parser.error("--top deve ser > 0")

    from internship_finder import opportunity_intel
    intel_path = (
        Path(args.company_intel) if args.company_intel
        else Path(__file__).resolve().parent.parent / "company_intel"
        / "company_intelligence.json"
    )
    company_intel_map = (
        opportunity_intel.load_company_intel(intel_path)
        if intel_path.exists() else None
    )

    dead_ids: set[str] = set()
    if args.dead_list:
        dp = Path(args.dead_list)
        if dp.exists():
            dead_ids = {line.strip() for line in
                        dp.read_text(encoding="utf-8").splitlines()
                        if line.strip()}

    archive_root = Path(args.archive) if args.archive else None
    translation_cache_path = (
        Path(args.translation_cache) if args.translation_cache else None
    )
    watchlist_path = Path(args.watchlist) if args.watchlist else None
    page = render_minimal_html_from_file(
        Path(args.input), top=args.top, company_intel_map=company_intel_map,
        archive_root=archive_root, dead_link_ids=dead_ids,
        translation_cache_path=translation_cache_path,
        watchlist_path=watchlist_path,
    )
    if args.output == "-":
        sys.stdout.write(page)
    else:
        out = Path(args.output)
        if out.parent != Path(""):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        print(f"pagina minima gerada: {out.resolve()} "
              f"({len(page.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
