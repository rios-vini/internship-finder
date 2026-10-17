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

F52 (vitrine recruiter — ``vitrine=True`` / ``--vitrine``) adiciona ao
render a primeira impressão profissional para quem chega por link
(Anschreiben/LinkedIn/CV) — SEM atrapalhar o loop diário do dono e SEM
quebrar o contrato de publish (só index.html):

- **Bloco "About this system"** (EN): ``<details>`` FECHADO no topo —
  o resumo de 1 linha fica visível; 2–3 linhas dentro. Os números
  (empresas acompanhadas, vagas elegíveis do dia) são renderizados DO
  BUILD, nunca hardcode. O texto é RASCUNHO revisável pelo dono.
- **Light mode**: ``@media (prefers-color-scheme: light)`` com paleta
  espelhada (tokens pares dark/light, contraste AA). Zero JS — só CSS.
- **``<head>``**: meta description (EN), og:title/og:description/
  og:type/og:url canônico (SEM og:image — publish só empurra
  index.html; arquivo extra é fora de escopo por design).
- **Favicon**: SVG inline data-URI (~200B), zero arquivo extra.

Default ``vitrine=False``: página byte a byte idêntica à pré-F52 (o
publish liga via ``--vitrine`` explícito, fixando o contrato — padrão
F13/F15/F43).

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
    "PAGE_TOP", "PAGE_TOP_FULL", "PAGE_TARGET_BYTES", "COMPANY_MAX_CARDS",
    "NEW_SINCE_SECTION_TOP", "MATERIALS_SECTION_TOP", "EU_SECTION_TOP",
    "GLOSSARY_TERMS",
    "page_full_cap_bytes", "render_minimal_html", "render_minimal_html_from_file",
    "apply_company_cap",
]

# Quantas vagas a pagina publica mostra. F11 T4 fixou top=100 (contrato do
# regime top-N: cap 2/empresa, alvo 100KB, cap duro 150KB). F43 adiciona o
# regime FULL-LIST (``full_list=True`` / ``--full-list``): TODAS as elegiveis
# vivas entram no HTML — o cap acompanha o universo (``page_full_cap_bytes``,
# proporcional) e a degradacao size-aware continua garantindo a entrega.
# PAGE_TOP permanece 100 (regime legado default; testes F11/F20/F36.1).
PAGE_TOP = 100
# F43 — teto do regime full-list ("universo inteiro na pratica"; mesmo valor
# do PUBLIC_TOP do publish — quem pede top explicito < universo cai no regime
# top-N legado da F11, intocado).
PAGE_TOP_FULL = 100_000

# F43 — orcamento da pagina FULL (decisao de produto, ver relatorio F43):
# o cap fixo de 150KB da F6/F11 era dimensionado p/ top-100 (~1KB/card).
# A full-list muda de faixa (~861 cards reais ~ 0,9-1,1MB), entao o cap
# acompanha o universo: CHROME fixo + orcamento por card. O orcamento por
# card (1.400 B) tem ~30% de folga sobre a medicao real de 15/10 (~1.054
# B/card com snippet; ~913 sem) — a degradacao size-aware (sem snippets ->
# corte honesto) continua garantindo a entrega dentro do cap.
FULL_CHROME_BYTES = 12_000
FULL_CARD_BUDGET_BYTES = 1_400

# F43 — lazy-render (IntersectionObserver): N cards renderizados de cara
# (primeira tela + respiro de scroll; o resto entra na viewport em lotes).
# O custo real é DOM/parse, não bytes (página estática, ~1KB/card no HTML
# baixado de uma vez); o IO só adia a REVELAÇÃO — dados já no HTML = busca
# client-side funciona sobre TUDO, inclusive o ainda não revelado.
LAZY_INITIAL_CARDS = 20
LAZY_ROOT_MARGIN = 400        # px de antecipação (revela antes do fold)


def page_full_cap_bytes(total_eligible: int) -> int:
    """Cap duro PROPORCIONAL da pagina full (F43): chrome + N * orcamento.

    Pura e monotona: cresce com o universo (o inverso do cap fixo da F6
    mentiria sobre a full-list). O cap fixo ``PAGE_HARD_CAP_BYTES`` de
    150KB PERMANECE como o contrato do regime top-N legado (top= explicito)
    — os dois regimes coexistem no mesmo render.
    """
    return max(PAGE_HARD_CAP_BYTES,
               FULL_CHROME_BYTES + FULL_CARD_BUDGET_BYTES * max(int(total_eligible), 0))

# Maximo de vagas EXIBIDAS por empresa no top (spec F11 T4 — regra de
# EXIBICAO: nao altera score/ranking/JSON/CSV; o corte e refeito com as
# vagas seguintes da ordem oficial).
COMPANY_MAX_CARDS = 2

# Top da secao 🆕 (spec F11 T1: top 10 por score) e da secao Materials
# (spec F11 T4 opcional: top 10 por materials_score).
NEW_SINCE_SECTION_TOP = 10
MATERIALS_SECTION_TOP = 10
# F36 — seção EU non-DE (terceiro perfil): top 10 por eu_score.
EU_SECTION_TOP = 10

# F20 — orcamento de bytes da secao 🎯 Empresas-alvo (item 4, dobra da
# pendencia F15 — decisao do dono 08/10, opcao (a): ORCAMENTO, o cap de
# PAGE_HARD_CAP_BYTES FICA). A secao entra inteira quando cabe; quando a
# pagina total estoura o cap, e aparada para as RADAR_TOP_N vagas de
# maior prioridade (nova primeiro, score desc, tie-break por id) + linha
# honesta "+X outras vagas de empresas-alvo" com a contagem real.
RADAR_TOP_N = 15

# F36.1 — orcamento de bytes das secoes de perfil 🧪/🇪🇺 (mesma decisao
# F20, mesma familia). O fix do ghost-eu devolve as DUAS secoes a TODAS
# as montagens da cadeia de degradacao; no dia real 14/10 isso somou
# 8,6KB e a pagina (97 eventos radar + 244 novas) voltou a estourar o
# cap por ~0,9KB. Quando o orçamento 🎯 (camada 3) ainda nao basta, as
# secoes de perfil degradam de top-10 para top-5 com header honesto —
# a seção NUNCA sai inteira (o bug original), o cap NUNCA estoura
# (contrato F20/F6) e o header conta a verdade do que está listado.
PROFILE_SECTION_BUDGET_TOP = 5

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


_PERIOD_DISPLAY = {"month": "mês", "monat": "mês", "year": "ano",
                   "jahr": "ano", "hour": "hora", "stunde": "hora",
                   "week": "semana", "woche": "semana", "day": "dia",
                   "tag": "dia"}


def _fmt_eur(value) -> str:
    """F51: valor monetário com separador de milhar alemão (2.280)."""
    try:
        return f"{float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return f"{value}"


def _fmt_salary(salary: dict | None) -> str:
    """Salário citado no anuncio (evidencia textual; nunca inventado).

    F51 item 2: formato compacto alemão ``€2.280/mês`` (milhar com
    ponto; período traduzido para PT quando conhecido — o VALOR e a
    UNIDADE vêm do anúncio, apenas a exibição é localizada).
    """
    if not salary:
        return ""
    period = salary.get("period")
    if period is not None:
        period = _PERIOD_DISPLAY.get(str(period).strip().lower(),
                                     str(period))
    suffix = f"/{period}" if period else ""
    if salary.get("min") is not None and salary.get("max") is not None:
        if float(salary["min"]) == float(salary["max"]):
            return f"€{_fmt_eur(salary['min'])}{suffix}"
        return (f"€{_fmt_eur(salary['min'])}–€{_fmt_eur(salary['max'])}"
                f"{suffix}")
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


# ---------------------------------------------------------------------------
# F14 — badge "já aplicou" (estado pessoal do tracker no card público).
# PRIVACIDADE: o card mostra APENAS o ícone de status (✅/📞/❌/…). Notas,
# contatos, feedback e datas NUNCA entram no HTML — o gate
# ``check_public_safe`` segue bloqueando jobs.db/caminhos privados.
# ---------------------------------------------------------------------------

# Ícone curto por status pessoal (spec F14 §2.1 — "ícones curtos, sem
# notas/contatos"). Status sem ícone (new/interesting/review) = sem
# badge: marcado-antes-de-aplicar não é "já aplicou".
_PERSONAL_STATUS_ICONS: dict[str, str] = {
    "applied": "✅",
    "interview": "📞",
    "offer": "🎉",
    "rejected": "❌",
    "withdrawn": "🚫",
    "ignored": "👁️",
}

# Rótulo title= do span (acessibilidade; fixo por status, sem dado pessoal).
_PERSONAL_STATUS_TITLES: dict[str, str] = {
    "applied": "Você já aplicou a esta vaga (tracker)",
    "interview": "Entrevista marcada/realizada (tracker)",
    "offer": "Oferta recebida (tracker)",
    "rejected": "Candidatura rejeitada (tracker)",
    "withdrawn": "Candidatura retirada (tracker)",
    "ignored": "Vaga ignorada no tracker",
}


def personal_status_icon(status: "str | None") -> str:
    """Ícone do badge para um status pessoal; '' quando não há badge.

    Pura — o mapeamento status→ícone vive em UM lugar só. Status de
    pré-candidatura (new/interesting/review) e status desconhecido não
    geram badge (o card fica idêntico ao de antes).
    """
    if not status:
        return ""
    return _PERSONAL_STATUS_ICONS.get(str(status).strip().lower(), "")


def personal_status_badge(personal_status: "str | None") -> str:
    """Span HTML do badge "já aplicou" (F14 §2.1); '' quando ausente.

    ``personal_status`` = status atual da vaga no banco pessoal (None/''
    ou status de pré-candidatura = sem badge). Pura e sem dado privado:
    o único texto é o ícone + o title fixo do dicionário — nunca
    notas/contatos/feedback/datas.
    """
    icon = personal_status_icon(personal_status)
    if not icon:
        return ""
    status = str(personal_status).strip().lower()
    title = _esc(_PERSONAL_STATUS_TITLES.get(status, "Status no tracker"))
    return f' <span class="pt" title="{title}">{icon}</span>'


def personal_status_map(db_path: Path | str | None) -> dict:
    """Mapa job_id → status pessoal (F14; leitura READ-ONLY do banco).

    Best-effort TOTAL: banco ausente, ilegível, corrompido ou sem o
    schema esperado → ``{}`` (nenhum badge, nenhum erro — a página nunca
    quebra por causa do tracker). NÃO cria o banco quando ausente (o
    render da página pública nunca escreve em ``data/``); usa
    ``sqlite3`` em modo ``mode=ro`` direto — sem passar pelo
    ``personal_tracker.connect`` (que cria diretórios/schema).
    """
    if not db_path:
        return {}
    path = Path(db_path)
    if not path.is_file():
        return {}
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT job_id, status FROM job_status"
            ).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — badge é best-effort, nunca erro
        return {}
    return {str(r[0]): str(r[1]) for r in rows}


# ---------------------------------------------------------------------------
# F15 — badge de qualidade do empregador (Kununu/GPTW) no card.
# MESMO padrão do company_intel da F5 (match exato via mapa normalizado);
# empresa sem entrada = sem badge, sem erro. O badge INFORMA (não reordena
# nada): pesoss do ranking intocados por design. Coexiste com o badge ✅
# da F14 (status pessoal) e com o 🛂 visa_friendly quando todos aplicam.
# ---------------------------------------------------------------------------

def employer_quality_badge(entry: dict | None) -> str:
    """Span HTML do badge ⭐/🏆 de qualidade (F15 §2; F51: compacto).

    ``entry`` = saída de ``employer_quality.quality_for``. F51: texto
    curto SEM sufixo/detalhe ("⭐ 4,0" / "🏆 GPTW") e SEM title= — a
    explicação vive UMA vez na legenda única (details/summary). O span
    com aria-hidden no emoji é montado pelo ``_card``; esta função é a
    ponte pura texto→span para superfícies fora do card. Best-effort:
    falha de import devolve '' (a página nunca quebra).
    """
    if not entry:
        return ""
    try:
        from internship_finder import employer_quality
        text = employer_quality.badge_text(entry)
    except Exception:  # noqa: BLE001 — view best-effort
        return ""
    if not text:
        return ""
    return f' <span class="eq">{_esc(text)}</span>'


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


# F29 — limiar de destaque discreto para vagas antigas (item 3: ">45 dias com
# destaque discreto"). Idade segue no MESMO badge "há Nd" da F11; a partir do
# limiar o texto vira "postada há N dias" (mais explícito) com classe própria.
AGE_STALE_DAYS = 45


def age_badge_text(job: dict, ref: datetime) -> str:
    """F51 item 3: idade em UM formato — 'Nd' (badge); '<1d' no dia.

    F29 compat: o destaque >45d segue existindo, mas pela CLASSE
    ``age-stale`` do chamador (não por texto mais longo — 4 formatos
    convivendo era o problema medido). ``_age_days_text`` mantém o
    contrato pré-F51 "há Nd" para os testes F11.
    """
    dt = _parse_posted_at(job.get("posted_at"))
    if dt is None:
        return ""
    days = (ref - dt).days
    if days < 0:
        return ""
    if days == 0:
        return "<1d"
    return f"{days}d"


def age_is_stale(job: dict, ref: datetime) -> bool:
    """>45 dias desde posted_at (F29 item 3; destaque discreto no card)."""
    dt = _parse_posted_at(job.get("posted_at"))
    if dt is None:
        return False
    days = (ref - dt).days
    return days > AGE_STALE_DAYS


# F29 item 2 — teto de duração do §16e (AufenthG §16e Abs. 2): 6 meses.
# O texto exibido é FRASE JURÍDICA LITERAL (não redigir variação).
SECTION16E_MAX_MONTHS = 6
DURATION_FLAG_TEXT = "duração N meses — acima do teto §16e (6 meses)"


def duration_flag_text(job: dict) -> str:
    """F29 item 2: duração citada > 6 meses excede o teto do §16e.

    Usa ``opportunity_intel.job_duration`` (detector existente — meses
    citados no anúncio; NUNCA derivado de datas). ``min`` da faixa é o que
    decide: "6–12 Monate" começa DENTRO do teto (a vaga pode terminar em
    6 — sinal honesto é não flagar); "7 Monate" ou mais = flag. Sem
    duração citada = sem flag (silêncio; a maioria dos anúncios não cita).
    INFORMATIVO: badge no card, nunca exclusão.
    """
    try:
        from internship_finder import opportunity_intel
        dur = opportunity_intel.job_duration(job)
    except Exception:  # noqa: BLE001 — display best-effort
        return ""
    if not dur:
        return ""
    months = int(dur.get("min") or 0)
    if months <= SECTION16E_MAX_MONTHS:
        return ""
    return DURATION_FLAG_TEXT.replace("N", str(months))


# F29 item 4a — red-flag determinística: anúncio exige matrícula ativa em
# universidade alemã. Padrões DE/EN conforme o card; match em título +
# descrição, case-insensitive. INFORMATIVO (badge), nunca exclusão.
_ENROLLMENT_PATTERNS = (
    "einschreibung an einer deutschen hochschule",
    "studium an einer deutschen hochschule",
    "einschreibung an einer universität",
    "studium an einer universität in deutschland",
    "enrolled at a german university",
    "enrollment at a german university",
    "matriculated at a german university",
)
ENROLLMENT_FLAG_TEXT = "exige matrícula em universidade alemã"


def enrollment_flag(job: dict) -> str:
    """F29 item 4a: badge quando o anúncio exige matrícula em Hochschule DE.

    O dono é aluno de universidade BRASILEIRA — a exigência de
    Einschreibung/Studium an einer deutschen Hochschule (ou enrolled at a
    German university) é incompatível com o perfil e o anúncio raramente
    declara isso no título; por isso o texto varre título E descrição.
    """
    text = " ".join(
        str(x or "") for x in (job.get("title"), job.get("description")))
    if not text.strip():
        return ""
    low = text.casefold()
    for pattern in _ENROLLMENT_PATTERNS:
        if pattern in low:
            return ENROLLMENT_FLAG_TEXT
    return ""


# F29 item 4b — red-flag honesta: remuneração não citada no anúncio.
SALARY_UNSPECIFIED_TEXT = "remuneração não citada"


def salary_unspecified_flag(job: dict) -> str:
    """F29 item 4b: badge quando o anúncio NÃO cita salário.

    Honesto e sem acusação: apenas informa que o anúncio não declara
    remuneração (a norma alemã para Pflichtpraktikum não obriga). Quando
    ``job_salary`` detecta um valor, NENHUM badge (a estimativa F29 pode
    aparecer como linha própria — campos separados, nunca fundidos).
    """
    try:
        from internship_finder import opportunity_intel
        if opportunity_intel.job_salary(job) is not None:
            return ""
    except Exception:  # noqa: BLE001 — display best-effort
        return ""
    return SALARY_UNSPECIFIED_TEXT


# F29 item 7 — frases jurídicas LITERAIS do §16e (definidas UMA vez; o
# teste faz assert de substring contra ESTES textos; em qualquer
# superfície que as exiba — NÃO redigir variações).
LEGAL_DURATION_PHRASE = "§16e: duração máxima 6 meses (AufenthG §16e Abs. 2)."
LEGAL_ZUSTIMMUNG_PHRASE = (
    "Praktikum sob §16e NÃO exige Zustimmung da Bundesagentur für Arbeit "
    "(BeschV §15 Nr. 1) — confirmar procedimento atualizado com "
    "consulado/Ausländerbehörde."
)


def _tracked_companies_count() -> "int | None":
    """F52 — nº de empresas acompanhadas pelo registry (DO BUILD, nunca
    hardcode). Best-effort total: import falha (pacote ausente em uso
    manual standalone) -> None -> o about omite o número, nunca quebra.
    """
    try:
        from internship_finder.registry import CompanyRegistry
        return len(CompanyRegistry().entries)
    except Exception:  # noqa: BLE001 — vitrine é best-effort, nunca erro
        return None


def _about_html(tracked_companies: "int | None", total_eligible: int) -> str:
    """F52 — bloco "About this system" (EN), <details> FECHADO no topo.

    Custo vertical para o dono: 1 linha (o summary). Os números vêm DO
    BUILD (registry via ``_tracked_companies_count``, elegíveis do dia do
    ``total_eligible`` — parâmetro que o chamador já passava); texto é
    rascunho revisável (ver relatório da fase). Pura e offline.
    """
    if tracked_companies is not None:
        sources = (f"a 5M+ job-posting dataset plus {tracked_companies} "
                   f"tracked employer career pages")
    else:
        sources = "a 5M+ job-posting dataset and tracked employer career pages"
    return (
        '<details class="about">'
        f'<summary>{_ABOUT_SUMMARY}</summary>'
        '<p>This page is my own daily job-ranking system: an automated '
        f'pipeline that scans {sources}, scores each role for fit '
        '(procurement / supply chain), employer quality and visa policy, '
        f'and republishes this list every morning — {total_eligible} '
        f'eligible role{"s" if total_eligible != 1 else ""} today. '
        f'<a href="{REPO_URL}">Source code on GitHub</a>.</p>'
        '</details>'
    )


def _legal_footer_html() -> str:
    """F29 item 7: rodapé com as frases jurídicas LITERAIS do §16e.

    Estáticas, offline, sempre presentes na página pública (a estimativa
    de duração e o countdown do visto vivem nelas).
    """
    return (
        '<p class="legal">ℹ️ '
        + _esc(LEGAL_DURATION_PHRASE)
        + " "
        + _esc(LEGAL_ZUSTIMMUNG_PHRASE)
        + "</p>"
    )


# ---------------------------------------------------------------------------
# F51 — LEGENDA ÚNICA (details/summary, ZERO JS, custo constante na página).
# Cada badge/símbolo do card passa a ser explicado UMA vez aqui; os title=
# por badge (custo ~6,4KB/89 badges, decisão documentada da F15) saem do
# card. Fecha por padrão; <summary> é focusable (acessibilidade nativa).
# ---------------------------------------------------------------------------

def _legend_html() -> str:
    """F51: <details> com o significado dos badges, do *, do §16e,
    glossário DE→EN, seções de perfil e score — a semântica GLOBAL da
    página em um bloco único, estático e offline (custo fixo ~2,5KB)."""
    items = [
        "<dt><span aria-hidden=\"true\">🛂</span> política de visto</dt>"
        "<dd>empresa com política de visto declarada (visa_policy: "
        "explicit_support ou unclear)</dd>",
        "<dt><span aria-hidden=\"true\">🇩🇪</span> alemão exigido</dt>"
        "<dd>anúncio exige alemão (german_level: required)</dd>",
        "<dt><span aria-hidden=\"true\">🚫</span> inaplicável</dt>"
        "<dd>a descrição completa (hidratada do site) revelou requisito "
        "de alemão ou mestrado — vaga fora do seu perfil, sai do top</dd>",
        "<dt>⭐ N,N</dt>"
        "<dd>nota média dos funcionários no portal Kununu (ex.: ⭐ 4,0)</dd>",
        "<dt>🏆 GPTW</dt>"
        "<dd>prêmio Great Place to Work (ano no mapa curado "
        "config/employer_quality.json)</dd>",
        "<dt><span aria-hidden=\"true\">🆕</span> nova</dt>"
        "<dd>vaga que não existia no snapshot de ontem</dd>",
        "<dt><span aria-hidden=\"true\">✅</span> já aplicou</dt>"
        "<dd>status do seu tracker pessoal (✅ aplicou · 📞 entrevista · "
        "🎉 oferta · ❌ rejeitada · 🚫 retirada · 👁️ ignorada)</dd>",
        "<dt><span aria-hidden=\"true\">🔗</span> morta</dt>"
        "<dd>URL retornou 404/410 no check de vitalidade — vaga "
        "provavelmente preenchida/removida</dd>",
        "<dt>⏳ / ⚠️</dt>"
        "<dd>sinais informativos do §16e: duração citada acima do teto de "
        "6 meses / anúncio exige matrícula ativa em universidade alemã</dd>",
        "<dt>*</dt>"
        "<dd>estimativa de mercado: salário NÃO citado no anúncio, "
        "estimado por categoria do título (praktikum.info, kununu/Indeed; "
        "curado 2026/10). O valor SEM citado no anúncio é o real</dd>",
        "<dt>Nd</dt>"
        "<dd>idade da vaga em dias desde posted_at (>45d destacada)</dd>",
        "<dt>score</dt>"
        "<dd>fit do título + qualidade do empregador + política de visto "
        "− decaimento por idade; abas 💼/🧪/🇪🇺 reordenam por perfis com "
        "pesos distintos (materials/EU: ver docs/f36_non_de_profile.md)</dd>",
        "<dt>EN:</dt>"
        "<dd>linha de tradução offline do título (dicionário DE→EN; o "
        "original DE nunca é substituído)</dd>",
    ]
    gloss = " · ".join(f"{_esc(de)} = {_esc(en)}" for de, en in GLOSSARY_TERMS)
    return (
        '<details class="legend"><summary>ℹ️ Legenda</summary>'
        "<dl>" + "".join(items) + "</dl>"
        f"<p>Glossário DE→EN: {gloss}</p>"
        '<p>' + _esc(LEGAL_DURATION_PHRASE) + " "
        + _esc(LEGAL_ZUSTIMMUNG_PHRASE) + "</p>"
        "</details>"
    )


def radar_budget_sort_key(job: dict) -> tuple:
    """Prioridade do orcamento 🎯 (F20; pura, deterministica).

    Ordem de prioridade da spec (item 4): (1) vagas NOVAS primeiro —
    todos os eventos do radar sao novos por construcao (``radar_events``
    e o diff de novas), entao o desempate efetivo comeca aqui;
    (2) score DESC; (3) tie-break deterministico por id (invertido para
    manter a ordem estavel do dataset no empate total de score).
    """
    try:
        score = float(job.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return (-score, str(job.get("id") or ""))


def apply_radar_budget(
    watchlist_events: list[dict] | None,
    *, limit: int = RADAR_TOP_N,
) -> tuple[list[dict] | None, int]:
    """Apara a lista de eventos 🎯 para o orcamento de bytes (F20; pura).

    Devolve ``(eventos_aparados, n_omitidas)``. Sem orcamento apertado
    (len <= limit) a lista entra INTEIRA e n_omitidas = 0 (a linha
    \"+X outras\" so existe quando algo e aparado — nada de linha extra
    nem aviso quando nada e cortado, spec item 4). Ordenacao interna
    preserva a ordem oficial do radar (nao reordena nada na exibicao);
    apenas SELECIONA os N de maior prioridade.
    """
    if watchlist_events is None or len(watchlist_events) <= limit:
        return watchlist_events, 0
    ranked = sorted(
        enumerate(watchlist_events),
        key=lambda pair: (radar_budget_sort_key(pair[1]), pair[0]),
    )
    kept_idx = sorted(i for i, _ in ranked[:limit])
    return [watchlist_events[i] for i in kept_idx], len(watchlist_events) - limit


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
          en_title_html: str = "", snippet_is_en: bool = False,
          personal_status: str | None = None,
          quality_entry: dict | None = None,
          inapplicable: bool = False,
          salary_estimate: str = "",
          age_stale: bool = False,
          duration_flag: str = "",
          enrollment_red_flag: str = "",
          profile_scores: dict | None = None,
          profile_ranks: dict | None = None,
          profile_attrs: bool = False) -> str:
    """Card compacto de uma vaga (mobile-first) com atributos F11.

    F12: ``en_title_html`` = linha EN abaixo do título (HTML pronto, vazio
    quando não se aplica); ``snippet_is_en`` marca o snippet como tradução
    (classe ``en`` + prefixo honesto "EN · ").

    F13: ``data-ws``/``data-data`` = flags de título para os toggles
    client-side (mesma regra casefold do JS; medição F13: 972 títulos
    contêm "werkstudent", o campo ``employment_type`` tem 0 ocorrências —
    por isso o filtro é por TÍTULO, como o f-de por german_level).

    F14: ``personal_status`` = status do tracker pessoal (None/'' =
    sem badge — vaga não marcada). O badge é APENAS o ícone curto
    (✅/📞/❌/…) com title fixo; nenhum dado privado no HTML.

    F15: ``quality_entry`` = entrada do mapa de qualidade do empregador
    (Kununu/GPTW; None = sem badge, silêncio gracioso). O badge ⭐/🏆
    COEXISTE com o ✅ da F14 e o 🛂 da F5 — são sinais independentes.

    F29 (sinais de candidatura, INFORMATIVOS — nunca exclusão):
    ``salary_estimate`` = linha "estimativa de mercado: ~X (fonte, data)"
    do benchmark curado, CAMPO SEPARADO do ``salary`` detectado (quando o
    anúncio cita salário, o chamador passa '' — nunca ambos no card);
    ``age_stale`` = classe discreta para >45 dias; ``duration_flag`` =
    "duração N meses — acima do teto §16e (6 meses)" quando citada >6;
    ``enrollment_red_flag`` = badge "exige matrícula em universidade
    alemã" (padrões DE/EN no título/descrição).
    """
    # F51 — texto do badge de qualidade (compacto: "⭐ 4,0"/"🏆 GPTW")
    # computado UMA vez; a explicação vive na legenda única.
    quality_text = ""
    if quality_entry is not None:
        try:
            from internship_finder import employer_quality
            quality_text = employer_quality.badge_text(quality_entry)
        except Exception:  # noqa: BLE001 — view best-effort
            quality_text = ""
    # F51 item 7 — ordem FIXA: 🛂 → 🇩🇪/🚫 → ⭐/🏆 → 🆕 → sinais F29 →
    # ✅(pessoal) → 🔗. Emojis com aria-hidden="true": o leitor de tela lê
    # o texto VISÍVEL do badge (🇩🇪, 🚫, 🏆, ⭐ 4,0, 🔗); a semântica
    # completa de cada um vive UMA vez na legenda (details/summary
    # focusable). Os title= saíram dos badges (custo por card) — a
    # explicação é a legenda única.
    badge_bits = []
    if visa:
        badge_bits.append(
            '<span class="vf"><span aria-hidden="true">🛂</span></span>')
    if de_level == "required":
        badge_bits.append(
            ' <span class="de"><span aria-hidden="true">🇩🇪</span></span>')
    if inapplicable:
        badge_bits.append(
            ' <span class="dead"><span aria-hidden="true">🚫</span></span>')
    if quality_text:
        badge_bits.append(f' <span class="eq">{quality_text}</span>')
    if is_new:
        badge_bits.append(' <span class="newb"><span aria-hidden="true">🆕</span></span>')
    if duration_flag:
        badge_bits.append(f' <span class="dur">⏳ {_esc(duration_flag)}</span>')
    if enrollment_red_flag:
        badge_bits.append(
            f' <span class="flag">⚠️ {_esc(enrollment_red_flag)}</span>')
    badge_bits.append(personal_status_badge(personal_status))
    if dead:
        badge_bits.append(
            ' <span class="dead"><span aria-hidden="true">🔗</span></span>')
    vf = "".join(badge_bits)
    title = _esc(job.get("title") or "(sem título)")
    inner = f'<a class="t" href="{_esc(job_href)}" target="_blank" rel="noopener">{title}</a>{vf}' if job_href else f'<span class="t">{title}</span>{vf}'
    meta_bits = [
        _esc(job.get("company") or "—"),
        _esc(_short_location(job) + _country_badge(job)),
    ]
    if salary:
        meta_bits.append(f'<b class="sal">{_esc(salary)}</b>')
    elif salary_estimate:
        # F29: estimativa SEMPRE rotulada; campo SEPARADO do salário
        # detectado (nunca ambos — o elif garante na raiz).
        meta_bits.append(f'<span class="est">{_esc(salary_estimate)}</span>')
    elif salary_unspecified_flag(job):
        meta_bits.append(f'<span class="nsal">{_esc(SALARY_UNSPECIFIED_TEXT)}</span>')
    if age:
        age_cls = "age age-stale" if age_stale else "age"
        meta_bits.append(f'<span class="{age_cls}">{_esc(age)}</span>')
    meta = ' · '.join(meta_bits)
    score = _fmt_score(score_override if score_override is not None
                      else job.get("score"))
    btn = ""
    if apply_href and apply_href != job_href:
        btn = f'<a class="btn" href="{_esc(apply_href)}" target="_blank" rel="noopener">candidatar-se ↗</a>'
    elif job_href and not apply_href:
        btn = f'<a class="btn" href="{_esc(job_href)}" target="_blank" rel="noopener">abrir vaga ↗</a>'
    if snippet and snippet_is_en:
        snip = f'<p class="d en">{_esc("EN · " + snippet)}</p>'
    elif snippet:
        snip = f'<p class="d">{_esc(snippet)}</p>'
    else:
        snip = ""
    qtext = " ".join(x for x in (job.get("title"), job.get("company"),
                                 job.get("location")) if x)
    # F43 — data-attrs de perfil: scores/ranks das abas business/materials/EU
    # computados NO BUILD (função pura), consumidos client-side. Profile
    # business = o score/rank exibidos (coluna .s/.r da lista principal) —
    # não duplica bytes.
    ps = profile_scores or {}
    pr = profile_ranks or {}
    prof_bits = []
    if profile_attrs:
        # F43 — identidade do card (lazy-render + abas/ordenação client-side)
        # e o rank do perfil business (a coluna .r exibida). Só no regime
        # full: o regime top-N legado NÃO ganha bytes novos (A/B byte-id).
        prof_bits.append(
            f' data-jid="{_esc(str(job.get("id") or ""))}" data-r="{rank}"')
    for key, s_attr, r_attr in (("materials", "data-mat", "data-matr"),
                                ("eu", "data-eu", "data-eur")):
        val = ps.get(key)
        if val is None:
            continue
        rank_v = pr.get(key)
        prof_bits.append(
            f' {s_attr}="{_fmt_score(val)}"')
        if rank_v is not None:
            prof_bits.append(f' {r_attr}="{rank_v}"')
    prof_html = "".join(prof_bits)
    return (
        f'<li class="c{" vf-on" if visa else ""}{" dead-on" if dead else ""}"'
        f' data-s="{score}"'
        f' data-vf="{1 if visa else 0}"'
        f' data-de="{_esc(de_level)}"'
        f' data-iso="{_esc(str(job.get("country_iso") or "").strip().lower())}"'
        f' data-new="{1 if is_new else 0}"'
        f' data-ws="{1 if is_werkstudent_title(job) else 0}"'
        f' data-data="{1 if is_data_bi_title(job) else 0}"'
        f' data-ia="{1 if inapplicable else 0}"'
        f'{prof_html}'
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
.pt{font-size:.72rem}
.eq{font-size:.72rem;color:#e8d9a0}
.radar-more{color:#9aa7b4;font-size:.78rem;font-weight:400}
.spot{margin:2px 0 0;padding:0 0 0 18px;color:#c8d3dd;font-size:.8rem}
.spot li{margin:2px 0}
.age{font-size:.78rem;color:#9aa7b4}
.age-stale{color:#d9a05b}
.est{font-size:.78rem;color:#9fb3c8}
.nsal{font-size:.78rem;color:#7d8a97}
.dur{font-size:.72rem;color:#e8b08a}
.flag{font-size:.72rem;color:#d9a05b}
.legal{color:#7d8a97;font-size:.72rem;margin:8px 0 0;line-height:1.5}
.m{color:#9aa7b4;font-size:.82rem;margin-top:2px}
.m .sal{color:#e8cf8a;font-weight:600}
.d{color:#8b98a5;font-size:.8rem;margin:5px 0 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.d.en{color:#8fb8d8}
.en{color:#9fb3c8;font-size:.78rem;margin:1px 0 0}
.gloss{color:#7d8a97;font-size:.72rem;margin:6px 0 0;line-height:1.5}
.btn{display:inline-block;margin-top:7px;padding:6px 14px;border:1px solid #1c7a4a;color:#9fd8b4;border-radius:999px;font-size:.82rem;text-decoration:none}
.btn:hover{background:#1c7a4a;color:#10151b}
.f{color:#9aa7b4;font-size:.72rem;margin:10px 0 0}
.legend{margin:0 0 12px;color:#9aa7b4;font-size:.78rem}
.legend summary{cursor:pointer;color:#c8d3dd;font-size:.82rem;padding:4px 0;list-style:none}
.legend summary:hover{color:#e6edf3}
.legend dl{margin:6px 0 0}
.legend dt{color:#c8d3dd;font-weight:600;margin-top:6px}
.legend dd{margin:0 0 0 0;color:#9aa7b4}
.legend p{margin:8px 0 0}
@media(min-width:640px){main{padding:24px 20px 56px}h1{font-size:1.25rem}}
"""

# F43 — CSS do regime full (tabs por perfil + lazy-render + contador). Vive
# SEPARADO de ``_CSS`` e só entra na página do regime full: o regime top-N
# legado segue byte a byte o mesmo HTML (contrato do A/B F43).
_CSS_F43 = """#tabs{display:flex;gap:6px;margin:0 0 12px;flex-wrap:wrap}
#tabs button{padding:7px 12px;border:1px solid #2a343e;border-radius:999px;background:#192027;color:#c8d3dd;font-size:.82rem;cursor:pointer}
#tabs button:hover{background:#1b2733}
#tabs button.on{border-color:#4da3ff;color:#e6edf3;background:#1b2733}
.count{display:inline-block;font-size:.78rem;color:#9aa7b4;margin:0 0 8px}
li.c[data-lazy="1"]{content-visibility:auto;contain-intrinsic-size:auto 110px}
"""

# F52 — vitrine recruiter. Página canônica do GitHub Pages (verificada ao
# vivo 16/10: 200 OK) — usada no og:url e no link "Source code on GitHub"
# do bloco about. O repo é público: o link funciona para o recruiter.
SITE_URL = "https://rios-vini.github.io/internship-finder/"
REPO_URL = "https://github.com/rios-vini/internship-finder"

# F52 — favicon: SVG inline data-URI (~200B), ZERO arquivo extra (o
# publish empurra só index.html para a gh-pages — contrato intocado).
# Marcador "VR" do ranking em verde-score sobre o painel escuro do site.
_FAVICON_HREF = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' "
    "fill='%2310151b'/%3E%3Ctext x='16' y='22' font-family='Arial, "
    "sans-serif' font-size='13' font-weight='bold' fill='%239fd8b4' "
    "text-anchor='middle'%3EVR%3C/text%3E%3C/svg%3E"
)

# F52 — rascunho do about (dono revisa claims antes do merge; texto
# final vai no relatório). Números NUNCA aqui — vêm do build.
_ABOUT_SUMMARY = (
    "Built and updated daily by Vinicius Rios — about this system"
)

# F52 — CSS do bloco about + light mode. Tokens pares dark/light: o
# dark é o default (regime do dono intocado); o light espelha a paleta
# sob @media(prefers-color-scheme: light) — zero JS.
_CSS_F52 = """details.about{margin:0 0 12px;font-size:.82rem}
details.about summary{color:#9fb3c8;cursor:pointer;padding:2px 0}
details.about p{margin:6px 0 2px;color:#9aa7b4;line-height:1.5}
details.about a{color:#4da3ff}
@media(prefers-color-scheme:light){
body{background:#ffffff;color:#1f2328}
main a{color:#0969da}
h2{color:#383f47}
.p,.p2{color:#5b6570}
.r{color:#5b6570}
.t{color:#1f2328}
a.t:visited{color:#383f47}
.m{color:#5b6570}
.d{color:#454c54}
.d.en{color:#1a5da8}
.en{color:#1a5da8}
.age{color:#5b6570}
.est{color:#3d5a78}
.nsal{color:#6b7480}
.gloss,.f,.legal{color:#6b7480}
.spot{color:#383f47}
.radar-more{color:#5b6570}
.bar input[type=search]{background:#f4f6f8;border-color:#c6ccd2;color:#1f2328}
.bar select{background:#f4f6f8;border-color:#c6ccd2;color:#1f2328}
.bar input[type=checkbox]{accent-color:#0969da}
li.c{border-bottom-color:#e6e9ec}
.s{color:#116326}
.vf{color:#116326}
.de{color:#7a5d00}
.dead{color:#a12622}
.newb{color:#116326}
.pt{color:#116326}
.eq{color:#7a5d00}
.age-stale{color:#954f04}
.dur{color:#954f04}
.flag{color:#954f04}
.btn{border-color:#116326;color:#116326}
.btn:hover{background:#116326;color:#ffffff}
details.about summary{color:#3d5a78}
details.about p{color:#5b6570}
details.about a{color:#0969da}
}
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

# F43 — JS da página full-list: abas por perfil (business/materials/EU) +
# busca/filtros sobre a LISTA ÚNICA (o input ``#q`` já existia; aqui ele
# passa a governar a lista inteira, inclusive cards fora da viewport) +
# lazy-render. O NÚCLEO puro do lazy (``f43LazyInit``) é executado em node
# pelo test_f43; o wrapper com IntersectionObserver real fica em
# _JS_LAZY_IO — não-testável offline (sem DOM/viewport no node).
_JS_PROFILE = """(function(){var tabs=document.querySelectorAll('#tabs button'),lis=document.querySelectorAll('#list li.c');if(!tabs.length)return;
var q=document.getElementById('q'),vf=document.getElementById('f-vf'),de=document.getElementById('f-de'),co=document.getElementById('f-country'),nw=document.getElementById('f-new'),ws=document.getElementById('f-ws'),da=document.getElementById('f-data');
var state={q:'',vf:false,de:false,iso:'',nw:false,ws:false,da:false,prof:'business',vis:{}};
function syncFilters(){state.q=q?q.value.trim().toLowerCase():'';state.vf=!!(vf&&vf.checked);state.de=!!(de&&de.checked);state.iso=co?co.value:'';state.nw=!!(nw&&nw.checked);state.ws=!!(ws&&ws.checked);state.da=!!(da&&da.checked);}
function cardOk(li){var ok=!state.q||li.getAttribute('data-q').toLowerCase().indexOf(state.q)>-1;
if(state.vf)ok=ok&&li.getAttribute('data-vf')==='1';
if(state.de)ok=ok&&li.getAttribute('data-de')!=='required';
if(state.iso)ok=ok&&li.getAttribute('data-iso')===state.iso;
if(state.nw)ok=ok&&li.getAttribute('data-new')==='1';
if(state.ws)ok=ok&&li.getAttribute('data-ws')!=='1';
if(state.da)ok=ok&&li.getAttribute('data-data')==='1';
return ok;}
function applyProfile(p){state.prof=p;var boxes=[];
for(var i=0;i<lis.length;i++){var li=lis[i],jid=li.getAttribute('data-jid');
var r=li.getAttribute('data-r'),s=li.getAttribute('data-s');
if(p==='materials'){r=li.getAttribute('data-matr');s=li.getAttribute('data-mat');}
if(p==='eu'){r=li.getAttribute('data-eur');s=li.getAttribute('data-eu');}
var has=(p==='business')||(s!==null&&s!=='');
var sc=(s!==null&&s!=='')?parseFloat(s):0;
boxes.push([sc,r,li,has&&cardOk(li),jid]);}
boxes.sort(function(a,b){if(b[0]-a[0])return b[0]-a[0];var ra=parseInt(a[1],10)||0,rb=parseInt(b[1],10)||0;if(rb-ra)return rb-ra;return a[4]<b[4]?-1:(a[4]>b[4]?1:0);});
var ol=document.getElementById('list');
for(var j=0;j<boxes.length;j++){ol.appendChild(boxes[j][2]);boxes[j][2].style.display=boxes[j][3]?'':'none';}
for(var m=0;m<tabs.length;m++){var on=tabs[m].getAttribute('data-prof')===p;tabs[m].className=on?'on':'';tabs[m].setAttribute('aria-selected',on?'true':'false');}
var cnt=0;for(var n2=0;n2<boxes.length;n2++)if(boxes[n2][3])cnt++;
var el=document.getElementById('n');if(el)el.textContent=cnt+' vagas';}
function onFilter(){syncFilters();applyProfile(state.prof);}
for(var t=0;t<tabs.length;t++){tabs[t].addEventListener('click',function(ev){var el=ev.target;while(el&&!el.getAttribute('data-prof'))el=el.parentNode;if(el)applyProfile(el.getAttribute('data-prof'));});}
if(q)q.addEventListener('input',onFilter);
if(vf)vf.addEventListener('change',onFilter);
if(de)de.addEventListener('change',onFilter);
if(co)co.addEventListener('change',onFilter);
if(nw)nw.addEventListener('change',onFilter);
if(ws)ws.addEventListener('change',onFilter);
if(da)da.addEventListener('change',onFilter);
window.__F43=state;window.__F43apply=applyProfile;window.__F43cardOk=cardOk;window.__F43sync=syncFilters;})();
"""

# F43 — lazy-render: NÚCLEO PURO, função nomeada ``f43LazyInit(all, n)`` —
# dado o conjunto de cards da lista única (na ordem do documento = ordem do
# ranking) e o nº de cards "eager" (primeira tela + respiro), devolve o mapa
# ``{jid: '1'|'0'}`` da revelação inicial. É ESTA a função executada em node
# pelo test_f43 (o wrapper de IO é só o consumidor dela no navegador).
_JS_LAZY_CORE = """function f43LazyInit(all,n){var out={};for(var i=0;i<all.length;i++){var jid=all[i].getAttribute('data-jid');if(jid!==null&&jid!=='')out[jid]=i<n?'1':'0';}return out;}
"""

# F43 — wrapper REAL do IntersectionObserver (runtime do navegador; sem IO
# suportado — ou sem o núcleo — revela TUDO: a página nunca fica vazia).
# O card CONTINUA no DOM e no fluxo (a busca/abas operam sobre a lista
# inteira, revelado ou não); o IO só controla o atributo ``data-lazy``, cujo
# CSS (``content-visibility:auto``) faz o browser PULAR layout/paint do que
# está fora da viewport — o custo real é DOM/paint, não bytes.
_JS_LAZY_IO = """(function(){var N=%d,R=%d,lis=document.querySelectorAll('#list li.c');
if(!window.__F43||typeof f43LazyInit!=='function')return;
var state=window.__F43.state,init=f43LazyInit(lis,N),k;
for(k in init)state.vis[k]=init[k];
for(var i=0;i<lis.length;i++){if(state.vis[lis[i].getAttribute('data-jid')]==='0')lis[i].setAttribute('data-lazy','1');}
if(!('IntersectionObserver' in window)){for(var j=0;j<lis.length;j++){state.vis[lis[j].getAttribute('data-jid')]='1';lis[j].removeAttribute('data-lazy');}if(window.__F43apply)window.__F43apply(state.prof);return;}
var io=new IntersectionObserver(function(entries){var hit=0;for(var e=0;e<entries.length;e++){var t=entries[e].target;if(entries[e].isIntersecting){state.vis[t.getAttribute('data-jid')]='1';t.removeAttribute('data-lazy');io.unobserve(t);hit++;}}},{rootMargin:R+'px'});
for(var m=0;m<lis.length;m++){if(lis[m].getAttribute('data-lazy')==='1')io.observe(lis[m]);}
if(window.__F43apply)window.__F43apply(state.prof);})();
"""


def _cards_section(jobs: list[dict], *, company_intel_map: dict | None,
                    new_ids: set[str] | None, dead_ids: set[str] | None,
                    ref: datetime, company_entry_cache: dict,
                    rank_start: int = 1, score_key: str = "score",
                    with_snippet: bool = True,
                    translation_cache: dict | None = None,
                    personal_statuses: dict | None = None,
                    quality_map: dict | None = None,
                    inapplicable_ids: set[str] | None = None,
                    salary_benchmark_map: dict | None = None,
                    profile_maps: dict | None = None,
                    skip_ids: set[str] | None = None,
                    display_aliases: dict | None = None) -> list[str]:
    """Cards de uma lista JA CORTADA (mesmo formato para todas as secoes).

    ``score_key``: campo exibido na coluna de score — "score" (perfil
    principal / secoes de novas) ou "materials_score" (secao Materials,
    que e um ranking PROPRIO; exibir o score do perfil principal la
    seria desinformacao). ``with_snippet``: False = sem o resumo de
    descricao (degradacao size-aware — campo decorativo).

    F43: ``profile_maps`` = {"scores": {id: {"materials": x, "eu": y}},
    "ranks": {id: {"materials": n, "eu": m}}} — data-attrs das abas por
    perfil (None = sem abas, cards idênticos ao pré-F43).
    ``skip_ids``: ids já exibidos na LISTA ÚNICA full (F43: a seção 🧪/🇪🇺
    vira atalho de DESTAQUE top-10, não duplicata — a full-list é a fonte
    da verdade por construção; None = comportamento pré-F43, byte a byte).

    F12: ``translation_cache`` (dict, default None = sem cache) faz o
    snippet da descricao usar a traducao EN em cache quando existir —
    marcada como tradução ("EN · "). Best-effort: sem entrada, snippet
    DE como hoje. A linha EN do título é independente (offline).

    F15: ``quality_map`` = mapa normalizado do employer_quality (None = 
    sem badge em nenhum card, comportamento pré-F15). Lookup exato por
    empresa com cache por vaga (mesma mecânica do company_intel_map).

    F20: ``inapplicable_ids`` = ids demovidos pela re-avaliação pós-
    hidratação (F18 sobre a descrição completa). O badge "🚫 inaplicável"
    é honesto (NUNCA o "🔗 morta" — a URL está viva).

    F29: ``salary_benchmark_map`` = benchmark salarial curado (None =
    sem estimativa — página igual à pré-F29). Por vaga, deriva (tudo
    determinístico, offline): estimativa rotulada quando o anúncio não
    cita salário E a categoria é derivável do título; badge de idade
    ">45 dias" com classe própria; flag de duração >6 meses (§16e) e
    red-flag de matrícula em universidade alemã. INFORMATIVO: nenhum
    sinal altera score/ordem/ids — só o card.

    F54 (higiene de display): ``display_aliases`` = mapa curado
    {company original → nome de exibição} (config/display_aliases.json;
    None/{} = sem aliases — o sanitizer mojibake permanece ativo). O
    card é renderizado da VIEW higienizada (cópia rasa: mojibake
    corrigido em title/company/location + alias na company); o match de
    intel/badges continua pelo job ORIGINAL — o alias nunca contamina o
    pipeline. Ambíguos ficam ORIGINAIS por design (regra de honestidade).
    """
    rows: list[str] = []
    new_ids = new_ids or set()
    dead_ids = dead_ids or set()
    inapplicable_ids = inapplicable_ids or set()
    personal_statuses = personal_statuses or {}
    profile_scores_map = (profile_maps or {}).get("scores") or {}
    profile_ranks_map = (profile_maps or {}).get("ranks") or {}
    profile_attrs = profile_maps is not None
    skip_ids = skip_ids or set()
    for i, job in enumerate(jobs, rank_start):
        jid = str(job.get("id") or "")
        if jid in skip_ids:
            continue  # F43 — já exibido na lista única; seção = atalho
        # F54 — VIEW de display (cópia rasa): mojibake corrigido em
        # title/company/location + alias de empresa. O job ORIGINAL
        # segue para intel/quality/salary (match por string exata do
        # dataset — alias/mojibake NÃO podem contaminar o pipeline).
        # Import lazy + best-effort: sem o pacote (fixtures de publish
        # que copiam só o minimal_page), render igual ao pré-F54.
        dview = job
        try:
            from internship_finder import display_hygiene
            dview = display_hygiene.display_job_view(job, display_aliases or {})
        except Exception:  # noqa: BLE001 — view best-effort, nunca erro
            dview = job
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
        # F15 — entrada de qualidade do empregador (match exato; silêncio
        # gracioso: mapa ausente/empresa não mapeada = None = sem badge).
        q_entry = None
        if quality_map is not None:
            try:
                from internship_finder import employer_quality
                q_entry = employer_quality.quality_for(job, quality_map)
            except Exception:  # noqa: BLE001 — view best-effort
                q_entry = None
        visa = _visa_friendly(job, entry)
        try:
            from internship_finder import opportunity_intel
            salary = _fmt_salary(opportunity_intel.job_salary(job))
        except Exception:  # noqa: BLE001
            salary = ""
        # F29 — estimativa de mercado: CAMPO SEPARADO do salário detectado.
        # salary_estimate_for_job já devolve '' quando job_salary existe
        # (contrato: nunca ambos no card); benchmark ausente = ''.
        salary_est = ""
        if salary_benchmark_map is not None:
            try:
                from internship_finder import salary_benchmark
                salary_est = salary_benchmark.salary_estimate_for_job(
                    job, salary_benchmark_map, compact=True)
            except Exception:  # noqa: BLE001 — display best-effort
                salary_est = ""
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
            i, dview, visa=visa, salary=salary,
            snippet=snippet, snippet_is_en=snippet_is_en,
            apply_href=apply_href, job_href=job_href,
            de_level=_german_level_attr(job),
            age=age_badge_text(job, ref), age_stale=age_is_stale(job, ref),
            dead=jid in dead_ids, is_new=jid in new_ids,
            score_override=(job.get(score_key)
                            if score_key != "score" else None),
            en_title_html=_title_en_line(dview),
            personal_status=personal_statuses.get(jid),
            quality_entry=q_entry,
            inapplicable=jid in inapplicable_ids,
            salary_estimate=salary_est,
            duration_flag=duration_flag_text(job),
            enrollment_red_flag=enrollment_flag(job),
            profile_scores=(profile_scores_map.get(jid) or {}) if profile_attrs
            else None,
            profile_ranks=(profile_ranks_map.get(jid) or {}) if profile_attrs
            else None,
            profile_attrs=profile_attrs,
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
    eu: list[dict] | None = None,
    with_snippets: bool = True,
    translation_cache: dict | None = None,
    watchlist_events: list[dict] | None = None,
    tracker_db: Path | str | None = None,
    quality_map: dict | None = None,
    sweet_spot_rows: list[dict] | None = None,
    radar_limit: int | None = None,
    profile_limit: int | None = None,
    inapplicable_ids: set[str] | None = None,
    salary_benchmark_map: dict | None = None,
    now_ref: "datetime | None" = None,
    profile_maps: dict | None = None,
    full_list: bool = False,
    full_limit: int | None = None,
    vitrine: bool = False,
    display_aliases: dict | None = None,
) -> str:
    """HTML minimo do top do dia (self-contained; ~90-100 KB tipico).

    F36 (fix de bomba-relógio da F29): ``now_ref`` permite fixar o
    instante de referência dos badges de idade ("postada há N dias") —
    default None = ``datetime.now`` (produção inalterada). Testes
    clock-dependent (test_f29 C1/C3b) passam o ref declarado em vez de
    depender da data de execução.

    ``jobs``: lista JA ordenada pelo score do pipeline (ordem oficial). A
    pagina nao re-ranqueia nada — apenas enumera o topo. ``total_eligible``
    e o tamanho do conjunto elegivel inteiro (o rodape informa que a
    pagina mostra o top-N e o resto vive no JSON/CSV completos).

    F11: ``new_since_ids`` = ids novos vs o snapshot anterior (secao 🆕 +
    data-new + toggle); None/'' = sem diff (secao/toggle ausentes).
    ``dead_link_ids`` = ids com URL 410/404 confirmado (badge + descem do
    topo exibido). F20: ``inapplicable_ids`` = ids demovidos pela
    re-avaliacao POS-HIDRATACAO (german_level/requires_master da F18
    revelou inaplicabilidade na descricao hidratada) — descem do topo
    topo exibido como o dead_link, com marcador PROPRIO e honesto ("saida do
    top: alemão exigido/mestrado revelado pela descrição completa" — NUNCA
    o badge "🔗 morta", que seria desinformativo: a vaga existe e a URL está
    viva). ``materials`` = ranking materials JA computado e cortado pelo
    chamador (secao opcional); None = sem secao. F36: ``eu`` = ranking EU
    non-DE JA computado e cortado pelo chamador (mesmo padrao do materials);
    None = sem secao.

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

    F14: ``tracker_db`` = banco pessoal do tracker (read-only; None/''
    = sem badge). O card ganha o badge discreto "já aplicou" (✅/📞/❌/)
    para vagas marcadas — APENAS o ícone + title fixo, nunca
    notas/contatos. Banco ausente/corrompido = nenhum badge, nenhum
    erro (best-effort; ``personal_status_map``).

    F15: ``quality_map`` = mapa normalizado de employer_quality (None =
    sem badge ⭐/🏆, página idêntica à pré-F15). ``sweet_spot_rows`` =
    saída de ``employer_quality.sweet_spot_companies`` (cruzamento
    volume × qualidade × visa_friendly derivado NO BUILD; None/[] = 
    seção "⭐ Ponto ótimo" ausente). O cap de 150KB permanece o limite
    duro: se a seção não couber, o chamador pode omiti-la (pendência
    documentada — nunca estourar o cap).

    F29 (sinais de candidatura — INFORMATIVOS): ``salary_benchmark_map``
    = benchmark curado (None = sinais salariais ausentes, página igual
    pré-F29). Estimativa de mercado ROTULADA (campo separado do salário
    detectado), badge de idade >45d, flag duração §16e e red-flags
    determinísticas por card + rodapé com as frases jurídicas LITERAIS.
    Nada disto altera score/ordem/ids.

    Size-aware (contrato da docstring desde a F6, agora real): com
    ``with_snippets=True`` o render e' montado com snippets; o chamador
    ``render_size_aware`` remonta sem snippets (campo DECORATIVO) quando
    o resultado estoura o alvo de bytes — nunca vagas a menos.

    F54 (higiene de display): ``display_aliases`` = mapa curado
    {company original → nome de exibição} (None = sem aliases; o
    sanitizer mojibake é SEMPRE ativo nos campos display). Aplicado no
    ponto ÚNICO ``_cards_section`` — vale para o topo, 🆕, 🎯, 🧪, 🇪🇺
    e o regime full-list (ambos os regimes da spec). Display-only: o
    dataset e o match de intel seguem pelo job original.

    F43 (full-list): ``full_list=True`` muda o corte do ranking principal
    de "top-N + cap 2/empresa" para "universo inteiro" (mortas continuam
    fora — a URL está morta; o corte honesto "mostrando X de N" conta a
    verdade). O cap passa a ser o PROPORCIONAL ``page_full_cap_bytes``
    (chrome + N * orcamento/card) decidido no ``render_size_aware``.
    ``profile_maps`` = data-attrs das abas (scores/ranks materials/EU por
    vaga, computados no build). Default ``full_list=False`` = regime
    top-N legado da F11 byte a byte.

    F52 (vitrine recruiter): ``vitrine=True`` liga o bloco "About this
    system" (EN, <details> fechado no topo, números do build), light
    mode via prefers-color-scheme (CSS puro), meta description + OG no
    <head> (sem og:image — contrato de publish: só index.html) e favicon
    SVG inline data-URI. Default ``False`` = página byte a byte a
    pré-F52 (o publish liga via ``--vitrine`` explícito).
    """
    ref = now_ref or datetime.now(UTC)
    dead_ids = set(dead_link_ids or set())
    # F20 — inaplicaveis-apos-hidratacao: saem do top exibido (mesma
    # mecanica do dead_link) mas NAO ganham o badge "🔗 morta" (a URL
    # esta viva; o que mudou e a aplicabilidade revelada pela descricao
    # completa). O corte usa os DOIS conjuntos; o badge usa SO o dead.
    inapplicable = set(inapplicable_ids or set())
    excluded = dead_ids | inapplicable
    # F14 — mapa job_id → status pessoal (uma leitura read-only; banco
    # ausente/corrompido = {} = nenhum badge, a página nunca quebra).
    p_statuses = personal_status_map(tracker_db)
    # F11 T3: vagas mortas descem do top exibido (a seguinte sobe) — o
    # corte com a regra 2/empresa percorre a lista JA sem as mortas.
    # Regra de exibicao; o JSON/CSV (base de dados) e intocavel.
    alive = [j for j in jobs if str(j.get("id") or "") not in excluded]
    # F43 — regime full-list: a lista única passa a ser o UNIVERSO inteiro
    # de vagas vivas (sem corte top-N, sem cap 2/empresa — cap/empresa é
    # regra de EXIBIÇÃO do regime top-N e causava ~20 ausências ocultas no
    # top-100; no universo completo ele deixaria de ser top-list e viraria
    # subamostra — efeito DOCUMENTADO no relatório F43 §cap-empresa). As
    # seções 🧪/🇪🇺 PERMANECEM (contrato "seções intactas" do A/B): a full-
    # list mata os buracos POR CONSTRUÇÃO (toda vaga viva está na lista
    # única; as seções 🧪/🇪🇺 seguem como DESTAQUE do perfil top-10 —
    # mesmos cards do legado, coluna de score própria — e só deduplicam
    # contra a lista quando ela foi cortada pelo orçamento (``full_limit``;
    # ver ``skip_ids`` nas seções). Regime legado (top-N): corte top +
    # cap 2/empresa da F11, intocado.
    if full_list:
        shown = list(alive)
        # F43 — corte de GARANTIA: só o último recurso do orçamento
        # (``render_size_aware``) passa ``full_limit``; o corte é sempre o
        # PREFIXO do ranking (nunca uma subamostra arbitrária) e a contagem
        # do rodapé conta a verdade (ver ``shown_note``).
        if full_limit is not None:
            shown = shown[:max(int(full_limit), 0)]
    else:
        shown = apply_company_cap(alive, limit=top)
    # F43 — ids da lista única (fonte do dedupe das seções no caso cortado).
    shown_ids = {str(j.get("id") or "") for j in shown}
    new_ids = set(new_since_ids or set())
    entry_cache: dict = {}
    body = "\n".join(_cards_section(
        shown, company_intel_map=company_intel_map, new_ids=new_ids,
        dead_ids=dead_ids, ref=ref, company_entry_cache=entry_cache,
        with_snippet=with_snippets, translation_cache=translation_cache,
        personal_statuses=p_statuses,
        quality_map=quality_map,
        inapplicable_ids=inapplicable,
        salary_benchmark_map=salary_benchmark_map,
        profile_maps=profile_maps,
        display_aliases=display_aliases,
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
            personal_statuses=p_statuses,
            quality_map=quality_map,
            salary_benchmark_map=salary_benchmark_map,
            profile_maps=profile_maps if full_list else None,
            display_aliases=display_aliases,
        ))
        new_section = (
            f'<h2>🆕 Novas desde ontem — {len(new_ids)} nova(s){extra}</h2>'
            f'{new_cards}'
        )

    # Seção 🎯 Empresas-alvo (F13) — vagas novas de ontem em empresas da
    # watchlist. Cards na ordem oficial (o radar NÃO reordena nada); TODOS
    # os eventos entram aqui QUANDO O ORÇAMENTO PERMITE (o digest lista 5
    # e promete "ver página"). F20 (item 4): quando a página inteira não
    # cabe no cap, o chamador (``render_size_aware``) remonta com a 🎯
    # aparada p/ top-N de prioridade (``radar_limit``) + linha honesta
    # "+X outras vagas de empresas-alvo" (contagem real; SEM linha extra
    # e SEM aviso quando nada é aparado).
    # Igual ao digest: um evento pode aparecer na 🆕 E aqui (seções com
    # critérios diferentes — 🆕 é "nova", 🎯 é "nova E alvo"; a página
    # espelha essa semântica, sem dedup entre seções).
    # Exibição pura: zero impacto em score/ranking/JSON/CSV.
    watch_section = ""
    radar_omitted = 0
    if watchlist_events:
        wl_cards_jobs = list(watchlist_events)
        if radar_limit is not None and len(wl_cards_jobs) > radar_limit:
            wl_cards_jobs, radar_omitted = apply_radar_budget(
                wl_cards_jobs, limit=radar_limit)
        wl_cards_jobs = list(wl_cards_jobs)  # type: ignore[arg-type]
        wl_cards = "\n".join(_cards_section(
            wl_cards_jobs, company_intel_map=company_intel_map,
            new_ids=new_ids, dead_ids=dead_ids, ref=ref,
            company_entry_cache=entry_cache, rank_start=1,
            score_key="score", with_snippet=with_snippets,
            translation_cache=translation_cache,
            personal_statuses=p_statuses,
            quality_map=quality_map,
            salary_benchmark_map=salary_benchmark_map,
            profile_maps=profile_maps if full_list else None,
            display_aliases=display_aliases,
        ))
        total_line = f'{len(watchlist_events)} nova(s) nas empresas que você acompanha'
        if radar_omitted:
            extra_radar = (f' <span class="radar-more">+{radar_omitted} outras '
                           f'vagas de empresas-alvo</span>')
        else:
            extra_radar = ""
        watch_section = (
            f'<h2>🎯 Empresas-alvo — {total_line}{extra_radar}</h2>'
            f'{wl_cards}'
        )

    # Seção ⭐ Ponto ótimo (F15 §4) — cruzamento volume × qualidade ×
    # visa_friendly derivado NO BUILD (zero HTTP; dados locais + mapas
    # curados versionados). Estática: 1 linha por empresa, sem cards —
    # lista as "empresas grandes com boa qualidade de trabalho" (a
    # pergunta do dono que o ranking não responde). Formatação direta
    # dos rows (pura; mesma forma do sweet_spot_lines do módulo).
    sweet_section = ""
    if sweet_spot_rows:
        lines = []

        # F54.1 — o painel usa OUTRA fonte de nomes (sweet_spot_rows
        # derivadas do dataset inteiro, fora do _cards_section): sem
        # aliasing, os crus ("careers.dhl.com", "careers.bcg.com")
        # escapavam para o texto visível. PONTO ÚNICO (spec F54.1 item
        # 1 — não reimplementar): o nome passa pela MESMA
        # display_job_view dos cards (sanitizer mojibake + alias EXATO;
        # incerto → original). Import lazy + best-effort: sem o pacote,
        # nome ORIGINAL (mesmo regime do _cards_section). O row nunca é
        # mutado (display-only; digest/pipeline seguem pela string crua).
        def _panel_display(raw) -> str:
            try:
                from internship_finder import display_hygiene
                view = display_hygiene.display_job_view(
                    {"company": raw}, display_aliases or {})
                return str(view.get("company") or "")
            except Exception:  # noqa: BLE001 — display best-effort
                return str(raw or "")

        for r in sweet_spot_rows:
            if r.get("gptw_award") and r.get("kununu_score") is None:
                quality = f"🏆 GPTW {int(r['gptw_award'])}"
            elif r.get("gptw_award"):
                quality = (f"⭐ {r['kununu_score']:.1f}".replace(".", ",")
                           + f" · 🏆 GPTW {int(r['gptw_award'])}")
            elif r.get("kununu_score") is not None:
                quality = f"⭐ {r['kununu_score']:.1f}".replace(".", ",") + " · Kununu"
            else:
                continue
            n = r["eligible"]
            lines.append(
                f"{_panel_display(r.get('company'))} · {quality} · "
                f"{n} vaga{'s' if n != 1 else ''} eligible")
        if lines:
            sweet_section = (
                '<h2>⭐ Ponto ótimo — empresas grandes com boa qualidade '
                'de trabalho e 🛂</h2>'
                '<p class="p2">Cruzamento volume × qualidade (Kununu ≥ 4,0 '
                'ou GPTW) × política de visto — derivado no build, mapa '
                'curado em config/employer_quality.json; critérios na '
                'legenda.</p>'
                + '<ul class="spot">' + "".join(
                    f"<li>{_esc(l)}</li>" for l in lines) + "</ul>"
            )

    # F43 — comentário do bloco 🧪 atualizado (o corte em si é o original
    # da F36.1; no full o dedupe tira as duplicatas da lista única).
    # Seção Materials — perfil alternativo, ranking proprio (digest ja
    # usa o MESMO rank_materials_jobs); top 10 por materials_score.
    # F36.1 — ``profile_limit``: orçamento da camada 3 (espelho F20 do
    # radar): degrada a lista para top-N com header HONESTO (conta o que
    # está listado) quando a página estoura o cap. None = inteira.
    # F43 — full-list: cards que já estão na lista única são PULADOS
    # (``skip_ids``): a seção vira atalho de DESTAQUE do top materials
    # (toda vaga já está na lista, ordenável pela ABA 🧪). Regime legado:
    # comportamento pré-F43 byte a byte (skip_ids vazio).
    materials_section = ""
    if materials:
        mat_list = materials[:profile_limit] if profile_limit else materials
        mat_cards = "\n".join(_cards_section(
            mat_list, company_intel_map=company_intel_map,
            new_ids=new_ids, dead_ids=dead_ids, ref=ref,
            company_entry_cache=entry_cache, rank_start=1,
            score_key="materials_score", with_snippet=with_snippets,
            translation_cache=translation_cache,
            personal_statuses=p_statuses,
            inapplicable_ids=inapplicable,
            salary_benchmark_map=salary_benchmark_map,
            profile_maps=profile_maps if full_list else None,
            display_aliases=display_aliases,
            skip_ids=(shown_ids if (full_list and full_limit is not None)
                      else None),
        ))
        mat_header = "top 10"
        mat_note = (
            '<p class="p2">Ranking próprio para Materials Engineering '
            '(pesos distintos dos de Supply Chain; ver '
            'docs/f36_non_de_profile.md). Score à esquerda: perfil '
            'Materials — os detalhes vivem na legenda.</p>')
        if full_list:
            # F43 — a lista única é a FONTE DA VERDADE (universo inteiro);
            # a seção segue como DESTAQUE do perfil (os mesmos top-10 do
            # legado, coluna de score própria) e aponta para a aba 🧪, que
            # reordena a lista COMPLETA por este perfil. Quando a lista
            # única foi CORTADA pelo orçamento (``full_limit``), o atalho
            # passa a mostrar só o que o corte deixou de fora (dedupe).
            if full_limit is not None:
                mat_header = f"destaques fora do top {len(shown_ids)}"
                mat_note = (
                    '<p class="p2">Ranking próprio para Materials Engineering '
                    '(pesos distintos dos de Supply Chain). A lista completa '
                    'está acima — use a aba 🧪 para reordená-la por este '
                    'perfil; aqui ficam só os destaques que o top principal '
                    'não mostra.</p>')
            else:
                mat_header = "destaques do perfil 🧪"
                mat_note = (
                    '<p class="p2">Ranking próprio para Materials Engineering '
                    '(pesos distintos dos de Supply Chain, coluna à esquerda). '
                    'A lista completa está acima — use a aba 🧪 para '
                    'reordená-la INTEIRA por este perfil; aqui ficam os 10 '
                    'destaques do perfil.</p>')
        if profile_limit and len(materials) > len(mat_list):
            mat_header = (
                f"top {len(mat_list)} de {len(materials)} — orçamento de página do dia")
            mat_note = (
                '<p class="p2">Ranking próprio para Materials Engineering '
                '(mesmas vagas elegíveis, pesos distintos dos de Supply '
                'Chain). O score à esquerda é o do perfil Materials. '
                'Página cheia hoje: o restante do top 10 está no JSON/CSV '
                'completos.</p>')
        materials_section = (
            f'<h2>🧪 Materials Engineering — {mat_header} (perfil alternativo)</h2>'
            + mat_note
            + mat_cards
        )

    # F36 — Seção EU non-DE: terceiro perfil (canal secundário F7), mesmo
    # padrão da seção Materials; top 10 por eu_score. F36.1 — o mesmo
    # ``profile_limit`` da 🧪 (mesma família de orçamento).
    eu_section = ""
    if eu:
        eu_list = eu[:profile_limit] if profile_limit else eu
        eu_cards = "\n".join(_cards_section(
            eu_list, company_intel_map=company_intel_map,
            new_ids=new_ids, dead_ids=dead_ids, ref=ref,
            company_entry_cache=entry_cache, rank_start=1,
            score_key="eu_score", with_snippet=with_snippets,
            translation_cache=translation_cache,
            personal_statuses=p_statuses,
            inapplicable_ids=inapplicable,
            salary_benchmark_map=salary_benchmark_map,
            profile_maps=profile_maps if full_list else None,
            display_aliases=display_aliases,
            skip_ids=(shown_ids if (full_list and full_limit is not None)
                      else None),
        ))
        eu_header = "top 10"
        eu_note = (
            '<p class="p2">Ranking próprio para o canal secundário '
            '(NL/BE/LU/FI — pesos calibrados no estrato; ver '
            'docs/f36_non_de_profile.md). Score à esquerda: perfil EU '
            '— os detalhes vivem na legenda.</p>')
        if full_list:
            # F43 — mesmo contrato do destaque 🧪 (aba 🇪🇺 reordena a lista
            # completa por eu_score; dedupe só no caso cortado).
            if full_limit is not None:
                eu_header = f"destaques fora do top {len(shown_ids)}"
                eu_note = (
                    '<p class="p2">Ranking próprio para o canal secundário '
                    '(NL/BE/LU/FI — países-alvo do plano, pesos calibrados no '
                    'estrato; ver docs/f36_non_de_profile.md). A lista completa '
                    'está acima — use a aba 🇪🇺 para reordená-la por este '
                    'perfil; aqui ficam só os destaques que o top principal '
                    'não mostra.</p>')
            else:
                eu_header = "destaques do perfil 🇪🇺"
                eu_note = (
                    '<p class="p2">Ranking próprio para o canal secundário '
                    '(NL/BE/LU/FI — países-alvo do plano, pesos calibrados no '
                    'estrato; ver docs/f36_non_de_profile.md). A lista completa '
                    'está acima — use a aba 🇪🇺 para reordená-la INTEIRA por '
                    'este perfil; aqui ficam os 10 destaques do perfil.</p>')
        if profile_limit and len(eu) > len(eu_list):
            eu_header = (
                f"top {len(eu_list)} de {len(eu)} — orçamento de página do dia")
            eu_note = (
                '<p class="p2">Ranking próprio para o canal secundário '
                '(NL/BE/LU/FI — países-alvo do plano, pesos calibrados no '
                'estrato; ver docs/f36_non_de_profile.md). O score à esquerda '
                'é o do perfil EU. Página cheia hoje: o restante do top 10 '
                'está no JSON/CSV completos.</p>')
        eu_section = (
            f'<h2>🇪🇺 Fora da Alemanha — {eu_header} (perfil EU non-DE)</h2>'
            + eu_note
            + eu_cards
        )

    # F43 — footer honesto por regime: full-list = "todas as N" (a página
    # É o universo); legado = "Top N de N" + cap 2/empresa (se aplicou).
    if full_list:
        if full_limit is not None and len(shown) < len(alive):
            shown_note = (f"mostrando {len(shown)} de {len(alive)} vagas "
                          f"elegíveis (orçamento de página do dia)")
        else:
            shown_note = f"todas as {len(shown)} vagas elegíveis"
    else:
        # F43: o regime top-N legado mantém o rodapé EXATO da F11 (a
        # contagem honesta com "mostrando X de Y" é do regime full).
        shown_note = f"Top {len(shown)} de {total_eligible} vagas elegíveis"
    footer_note = (
        f"{shown_note} · {n_vf} com 🛂 "
        "(empresa com política de visto) · ranking, JSON e CSV completos "
        "são gerados pelo pipeline no VPS"
    )
    # F51 — glossário e frases §16e vivem DENTRO da legenda única (zero
    # duplicação de rodapé; o custo é fixo, não por card).
    # Select de pais SEM bandeiras: o contrato da F7 e "DE e o default visual
    # — bandeira so no canal secundario"; o select e um controle, nao um
    # card (e o emoji DE no select poluiria o documento inteiro).
    country_opts = "".join(
        f'<option value="{iso}">{iso.upper()}</option>'
        for iso in COUNTRY_FLAGS
    )
    # F43 — abas por perfil (regime full): a lista única reordenável por
    # business/materials/EU. Default business (= ordem do ranking oficial).
    # O contador "#n" é DOM-latente desde a F6 (o _JS original referencia
    # getElementById('n') com guard if(n) e o span nunca existiu); no regime
    # full ele ganha vida: o _JS_PROFILE escreva a contagem visível da aba
    # ativa + filtros + lazy-state (o _JS legado continua contando nos
    # bastidores, mas o span agora é do _JS_PROFILE — o primeiro que rodar
    # por último vence; no full o _JS_PROFILE roda DEPOIS).
    tabs_html = ""
    extra_js = ""
    if full_list:
        tabs_html = (
            '<span id="n" class="count" aria-live="polite"></span>\n'
            '<div id="tabs" role="tablist">'
            '<button type="button" class="on" data-prof="business"'
            ' aria-selected="true">💼 Business</button>'
            '<button type="button" data-prof="materials"'
            ' aria-selected="false">🧪 Materials</button>'
            '<button type="button" data-prof="eu"'
            ' aria-selected="false">🇪🇺 EU non-DE</button>'
            '</div>'
        )
        extra_js = (
            _JS_LAZY_CORE + _JS_PROFILE
            + _JS_LAZY_IO % (LAZY_INITIAL_CARDS, LAZY_ROOT_MARGIN)
        )
    _css_f43 = _CSS_F43 if full_list else ""
    # F43 — o bloco JS extra (núcleo lazy + abas) só existe no regime full;
    # na página legada o HTML segue byte a byte o da F11 (nenhuma tag vazia).
    _script_f43 = f"<script>{extra_js}</script>" if extra_js else ""
    page_title = (
        f"Internship Finder — todas as {len(shown)} vagas do dia"
        if full_list else f"Internship Finder — top {len(shown)} do dia"
    )
    h1_title = (
        "Internship Finder — todas as vagas do dia"
        if full_list else "Internship Finder — top do dia"
    )
    # F52 — vitrine recruiter (default OFF: nada disto existe na página
    # legada — byte a byte pré-F52). Head: meta description + OG (sem
    # og:image) + favicon data-URI + color-scheme honesto (dark default +
    # light via media query). Corpo: bloco about com números DO BUILD.
    _meta_f52 = ""
    _about = ""
    _css_f52 = ""
    if vitrine:
        _meta_f52 = (
            '\n<meta name="description" content="Daily-updated ranking of '
            'internship and working-student jobs in procurement and supply '
            'chain (Germany and target EU countries), automatically scored '
            'for role fit, employer quality and visa policy.">'
            f'\n<meta property="og:title" content="{page_title}">'
            '\n<meta property="og:description" content="Daily-updated '
            'ranking of internship and working-student jobs in procurement '
            'and supply chain, automatically scored for role fit, employer '
            'quality and visa policy.">'
            '\n<meta property="og:type" content="website">'
            f'\n<meta property="og:url" content="{SITE_URL}">'
            f'\n<link rel="icon" href="{_FAVICON_HREF}" type="image/svg+xml">'
        )
        # O \n inicial vive NO VALOR (não na linha do template): com
        # vitrine=False o HTML é byte a byte o pré-F52 (nenhuma linha
        # vazia fantasma no <head>/corpo).
        _about = "\n" + _about_html(_tracked_companies_count(),
                                    total_eligible)
        _css_f52 = _CSS_F52
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="{'dark light' if vitrine else 'dark'}">
<title>{page_title}</title>{_meta_f52}
<style>{_CSS}{_css_f43}{_css_f52}</style>
</head>
<body>
<main>
<h1>{h1_title}</h1>{_about}
<p class="p">{_esc(generated_at)} UTC · ordenado pelo score do pipeline · 🛂 = empresa com política de visto</p>
<div class="bar">
<input id="q" type="search" placeholder="Buscar título, empresa, local…">
<label><input type="checkbox" id="f-vf"> 🛂 só visa friendly</label>
<label><input type="checkbox" id="f-de"> sem alemão exigido</label>
<select id="f-country"><option value="">todos os países</option>{country_opts}</select>
{'<label><input type="checkbox" id="f-new"> só novas de ontem</label>' if new_ids else ''}
<label><input type="checkbox" id="f-ws"> sem Werkstudent</label>
<label><input type="checkbox" id="f-data"> Data/BI</label>
</div>{tabs_html}
{_legend_html()}
<ol id="list">
{body}
</ol>
{new_section}
{watch_section}
{materials_section}
{eu_section}
{sweet_section}
<p class="f">{_esc(footer_note)}</p>
</main>
<script>{_JS}</script>{_script_f43}
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
    eu: list[dict] | None = None,
    translation_cache: dict | None = None,
    watchlist_events: list[dict] | None = None,
    tracker_db: Path | str | None = None,
    quality_map: dict | None = None,
    sweet_spot_rows: list[dict] | None = None,
    inapplicable_ids: set[str] | None = None,
    salary_benchmark_map: dict | None = None,
    full_list: bool = False,
    profile_maps: dict | None = None,
    vitrine: bool = False,
    display_aliases: dict | None = None,
) -> str:
    """``render_minimal_html`` com degradacao progressiva de tamanho (F11+F20).

    Cadeia de degradacao em ORDEM (o cap duro ``PAGE_HARD_CAP_BYTES`` NUNCA
    estoura por causa de campos decorativos; o alvo de ``PAGE_TARGET_BYTES``
    continua o gatilho da remontagem sem snippets — campo DECORATIVO):

    1. render COM snippets + 🎯 inteira + ⭐ (o estado ideal);
    2. > alvo 100KB: remonta SEM snippets (F11 — decorativo);
    3. > cap 150KB (F20, item 4): remonta com a 🎯 aparada p/ top
       ``RADAR_TOP_N`` de prioridade (score desc, tie-break id) + linha
       honesta "+X outras vagas de empresas-alvo". O orçamento vale COM
       OU SEM rows ⭐ (a página pré-F15 já estourava o cap sozinha);
    4. se MESMO aparada > cap: o gate ⭐ (F15) dispara no chamador
       (``render_minimal_html_from_file``) como ÚLTIMO recurso — aviso
       verbatim preservado.

    F12: o snippet remontado sem snippets tambem perde a traducao EN
    (ela vive no snippet) — a linha EN do título e o glossário permanecem
    (nao sao campos decorativos). ``translation_cache`` e passado ao
    render em todas as montagens (best-effort).

    F13: ``watchlist_events`` repassado as montagens (a secao 🎯 nao e
    campo decorativo — sobrevive a remontagem sem snippets; na degradacao
    F20 e aparada, nunca dropada inteira).

    F14: ``tracker_db`` repassado as montagens (o badge "já aplicou"
    tambem sobrevive — nao e campo decorativo).

    F15: ``quality_map``/``sweet_spot_rows`` repassados as montagens (o
    badge ⭐/🏆 e a seção Ponto ótimo NÃO são decorativos).

    F29: ``salary_benchmark_map`` repassado as montagens (estimativa
    rotulada, badges de idade/duração/red-flags e rodapé jurídico NÃO
    são decorativos — sobrevivem à remontagem).

    F36.1 (bug de produção 14/10): TODA montagem desta cadeia repassa
    TODAS as seções de perfil — a 3ª (orçamento 🎯) esquecia ``eu=`` e a
    seção 🇪🇺 Fora da Alemanha sumia silenciosamente exatamente nos
    dias de página estourada (best-effort por design = zero erro no
    log). Regressão garantida por scripts/test_f36_1.py com fixture que
    ESTOURA o cap (página pequena nunca exercita degradação).

    F54: ``display_aliases`` repassado a TODAS as montagens desta
    cadeia (lição F36.1 — nenhuma degradação pode perder a higiene de
    display; sanitizer + aliases sobrevivem a remontagens).
    """
    # F43 — orçamento por REGIME: o top-N legado mantém alvo 100KB + cap duro
    # 150KB (F11, intocado); a full-list troca por UM valor só — o cap
    # proporcional ao universo (``page_full_cap_bytes``): com ~900 cards o
    # cap fixo de 150KB mentiria sobre a página. ``target`` = ``hard_cap``
    # no full (não há "alvo macio" a perseguir: a entrega É a lista inteira,
    # e o snippet é o primeiro campo decorativo a cair).
    hard_cap = (page_full_cap_bytes(total_eligible) if full_list
                else PAGE_HARD_CAP_BYTES)
    target = hard_cap if full_list else PAGE_TARGET_BYTES
    html = render_minimal_html(
        jobs, total_eligible=total_eligible, generated_at=generated_at,
        top=top, company_intel_map=company_intel_map,
        new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
        materials=materials, eu=eu, with_snippets=True,
        translation_cache=translation_cache,
        watchlist_events=watchlist_events,
        tracker_db=tracker_db,
        quality_map=quality_map, sweet_spot_rows=sweet_spot_rows,
        inapplicable_ids=inapplicable_ids,
        salary_benchmark_map=salary_benchmark_map,
        full_list=full_list, profile_maps=profile_maps,
        vitrine=vitrine,
        display_aliases=display_aliases,
    )
    if len(html.encode("utf-8")) > target:
        html = render_minimal_html(
            jobs, total_eligible=total_eligible, generated_at=generated_at,
            top=top, company_intel_map=company_intel_map,
            new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
            materials=materials, eu=eu, with_snippets=False,
            translation_cache=translation_cache,
            watchlist_events=watchlist_events,
            tracker_db=tracker_db,
            quality_map=quality_map, sweet_spot_rows=sweet_spot_rows,
            inapplicable_ids=inapplicable_ids,
            salary_benchmark_map=salary_benchmark_map,
            full_list=full_list, profile_maps=profile_maps,
            vitrine=vitrine,
            display_aliases=display_aliases,
        )
    # F20 (item 4) — orçamento 🎯: só quando a montagem mais enxuta AINDA
    # estoura o cap duro. A 🎯 é aparada (top RADAR_TOP_N por prioridade)
    # ANTES do gate ⭐ da F15 — inverte a pendência: a seção de valor
    # entra, a lista longa degrada honestamente.
    if watchlist_events and len(watchlist_events) > RADAR_TOP_N \
            and len(html.encode("utf-8")) > hard_cap:
        html = render_minimal_html(
            jobs, total_eligible=total_eligible, generated_at=generated_at,
            top=top, company_intel_map=company_intel_map,
            new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
            materials=materials, eu=eu, with_snippets=False,
            translation_cache=translation_cache,
            watchlist_events=watchlist_events,
            tracker_db=tracker_db,
            quality_map=quality_map, sweet_spot_rows=sweet_spot_rows,
            radar_limit=RADAR_TOP_N,
            inapplicable_ids=inapplicable_ids,
            salary_benchmark_map=salary_benchmark_map,
            full_list=full_list, profile_maps=profile_maps,
            vitrine=vitrine,
            display_aliases=display_aliases,
        )
        print(f"pages: orçamento 🎯 ativo — seção aparada p/ top-{RADAR_TOP_N} "
              f"de {len(watchlist_events)} eventos; página agora "
              f"{len(html.encode('utf-8'))} bytes (cap "
              f"{PAGE_HARD_CAP_BYTES})")
        # F36.1 — orçamento de perfil (3-b): o fix ghost-eu devolve 🧪/🇪🇺
        # a esta montagem; no dia real 14/10 a página voltou a estourar
        # por ~0,9KB. Mesma família F20: degrada as seções de perfil para
        # top-PROFILE_SECTION_BUDGET_TOP com header honesto (a seção NUNCA
        # sai inteira — o bug original — e o cap NUNCA estoura).
        if len(html.encode("utf-8")) > hard_cap \
                and (materials or eu):
            html = render_minimal_html(
                jobs, total_eligible=total_eligible, generated_at=generated_at,
                top=top, company_intel_map=company_intel_map,
                new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
                materials=materials, eu=eu, with_snippets=False,
                translation_cache=translation_cache,
                watchlist_events=watchlist_events,
                tracker_db=tracker_db,
                quality_map=quality_map, sweet_spot_rows=sweet_spot_rows,
                radar_limit=RADAR_TOP_N,
                profile_limit=PROFILE_SECTION_BUDGET_TOP,
                inapplicable_ids=inapplicable_ids,
                salary_benchmark_map=salary_benchmark_map,
                full_list=full_list, profile_maps=profile_maps,
                vitrine=vitrine,
                display_aliases=display_aliases,
            )
            print(f"pages: orçamento 🧪/🇪🇺 ativo — seções de perfil "
                  f"degradadas p/ top-{PROFILE_SECTION_BUDGET_TOP} "
                  f"(header honesto); página agora "
                  f"{len(html.encode('utf-8'))} bytes (cap "
                  f"{hard_cap})")
    # F43 — última garantia do regime FULL: se nem a montagem sem snippets
    # coube no cap proporcional, corta a lista no MAIOR prefixo do ranking
    # que caiba (busca binária sobre o nº de cards; cada tentativa mede a
    # página INTEIRA, já com as seções-atalho) e o rodapé conta a verdade
    # ("mostrando X de Y"). O cap proporcional tem folga de projeto
    # (~1,4 KB/card vs ~1,0 KB/card medido no universo real): este caminho
    # é a GARANTIA de entrega, não o comportamento normal.
    if full_list and len(html.encode("utf-8")) > hard_cap:
        excluded = {str(x) for x in (dead_link_ids or set())}
        excluded |= {str(x) for x in (inapplicable_ids or set())}
        universe = [j for j in jobs if str(j.get("id") or "") not in excluded]
        best: str | None = None
        best_n = 0
        lo, hi = 1, len(universe)
        while lo <= hi:
            mid = (lo + hi) // 2
            trial = render_minimal_html(
                jobs, total_eligible=total_eligible, generated_at=generated_at,
                top=top, company_intel_map=company_intel_map,
                new_since_ids=new_since_ids, dead_link_ids=dead_link_ids,
                materials=materials, eu=eu, with_snippets=False,
                translation_cache=translation_cache,
                watchlist_events=watchlist_events,
                tracker_db=tracker_db,
                quality_map=quality_map, sweet_spot_rows=sweet_spot_rows,
                inapplicable_ids=inapplicable_ids,
                salary_benchmark_map=salary_benchmark_map,
                full_list=True, profile_maps=profile_maps, full_limit=mid,
                vitrine=vitrine,
                display_aliases=display_aliases,
            )
            if len(trial.encode("utf-8")) <= hard_cap:
                best, best_n, lo = trial, mid, mid + 1
            else:
                hi = mid - 1
        if best is not None:
            html = best
            print(f"pages: orçamento FULL ativo — lista cortada em {best_n} "
                  f"de {len(universe)} vagas (rodapé honesto); página agora "
                  f"{len(html.encode('utf-8'))} bytes (cap {hard_cap})")
        else:
            print(f"pages: ATENÇÃO — nem 1 card cabe no cap FULL ({hard_cap} "
                  f"bytes); página medida {len(html.encode('utf-8'))} bytes")
    return html


def _profile_maps(jobs: list[dict]) -> dict:
    """F43 — scores/ranks dos perfis alternativos, por vaga (BUILD, puro).

    REUSA os rankings do pipeline (``rank_materials_jobs`` /
    ``rank_eu_stratum``) — nenhuma regra de score nasce aqui: o ``rank`` é
    a posição na lista ordenada do próprio perfil (1-based, o mesmo número
    que a seção-atalho exibe) e o score é o campo do perfil
    (``materials_score`` / ``eu_score``). Zero rede, zero mutação da
    entrada (ambas as funções devolvem lista nova).

    Semântica do estrato EU: ``rank_eu_stratum`` corta o estrato não-DE
    (é o que a seção 🇪🇺 promete) — vagas fora do estrato NÃO recebem
    ``data-eu`` e, na aba 🇪🇺, ficam fora (é informação, não filtro
    silencioso: o score EU de uma vaga DE/fora do estrato não é do canal).

    Best-effort: qualquer falha -> perfil ausente (a aba correspondente
    apenas não esconde nada — nunca derruba o render).
    """
    scores: dict = {}
    ranks: dict = {}
    try:
        from internship_finder.materials_ranking import rank_materials_jobs
        for i, j in enumerate(rank_materials_jobs(jobs), 1):
            jid = str(j.get("id") or "")
            if not jid or j.get("materials_score") is None:
                continue
            scores.setdefault(jid, {})["materials"] = j["materials_score"]
            ranks.setdefault(jid, {})["materials"] = i
    except Exception:  # noqa: BLE001 — aba opcional, nunca erro
        pass
    try:
        from internship_finder.eu_ranking import rank_eu_stratum
        for i, j in enumerate(rank_eu_stratum(jobs), 1):
            jid = str(j.get("id") or "")
            if not jid or j.get("eu_score") is None:
                continue
            scores.setdefault(jid, {})["eu"] = j["eu_score"]
            ranks.setdefault(jid, {})["eu"] = i
    except Exception:  # noqa: BLE001 — aba opcional, nunca erro
        pass
    return {"scores": scores, "ranks": ranks}


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
    include_eu: bool = True,
    translation_cache_path: Path | str | None = None,
    watchlist_path: Path | str | None = None,
    tracker_db: Path | str | None = None,
    employer_quality_path: Path | str | None = None,
    inapplicable_ids: set[str] | None = None,
    salary_benchmark_path: Path | str | None = None,
    full_list: bool = False,
    generated_at: str | None = None,
    vitrine: bool = False,
    display_aliases_path: Path | str | None = None,
) -> str:
    """Le o eligible_jobs.json e devolve o HTML minimo do topo.

    F39-followup: ``generated_at`` fixa o carimbo do rodape ("<date> UTC")
    quando dado; default None = ``datetime.now`` (producao inalterada).
    Testes byte-identity (test_f15 T6) passam o valor declarado em vez
    de dois renders independentes cruzarem uma borda de minuto. Mesmo
    padrao do ``now_ref`` da F36.

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

    F14: ``tracker_db`` = banco pessoal (default None = sem badge);
    lido READ-ONLY por ``personal_status_map`` — ausente/corrompido = 
    nenhum badge, nunca erro. NUNCA criado pelo render.

    F15: ``employer_quality_path`` = ``config/employer_quality.json``
    (default None = sem badge ⭐/🏆 e sem seção Ponto ótimo — página
    byte a byte a pré-F15). O mapa e lido UMA vez; o cruzamento "ponto
    ótimo" (volume × qualidade × visa_friendly) e derivado AQUI, no
    build, com ZERO HTTP (dados locais + mapas curados versionados).
    Best-effort: mapa ausente/corrompido -> sem badge/secao, nunca erro.
    A seção só é montada se couber no cap duro de ``PAGE_HARD_CAP_BYTES``
    (medida ANTES de devolver; se não couber, é omitida e o tamanho medido
    segue no log do chamador — nunca estoura o cap).

    F29: ``salary_benchmark_path`` = ``config/salary_benchmark.json``
    (default None = sem estimativa de mercado e sinais dependentes do
    benchmark — página byte a byte a pré-F29). Loader tolerante:
    ausente/corrompido -> mapa vazio -> sem estimativa em qualquer card,
    nunca erro. Os sinais independentes do benchmark (idade, duração
    §16e, red-flags, rodapé jurídico) permanecem.

    F54: ``display_aliases_path`` = ``config/display_aliases.json``
    (default None = sem aliases; o sanitizer mojibake permanece ativo).
    Loader tolerante: ausente/corrompido -> {} -> cards com higienização
    de mojibake e nomes ORIGINAIS de empresa, nunca erro.
    """
    with path.open(encoding="utf-8") as fh:
        jobs = json.load(fh)
    if not isinstance(jobs, list):
        raise ValueError(f"formato inesperado em {path}: esperado lista de vagas")
    generated = (generated_at if generated_at is not None
                 else datetime.now(UTC).strftime("%Y-%m-%d %H:%M"))

    # F43 — REGIME: full-list explícito (``full_list=True`` /
    # ``--full-list``) OU pedido de "todas as vagas" (``top >=
    # PAGE_TOP_FULL`` — é o que o publish pede desde a F6 via
    # ``PUBLIC_TOP``: quem pede o universo com um ``top`` explícito menor
    # continua no regime top-N legado da F11, intocado). No full, os
    # data-attrs de perfil (abas 🧪/🇪🇺) são computados AQUI, no build.
    full = bool(full_list) or top >= PAGE_TOP_FULL
    profile_maps = _profile_maps(jobs) if full else None

    # F15 — mapa de qualidade do empregador + cruzamento ponto ótimo
    # (derivado NO BUILD; zero HTTP — só o dataset local e os arquivos
    # curados versionados). Best-effort total: falha = sem F15.
    quality_map: dict | None = None
    sweet_spot_rows: list[dict] | None = None
    if employer_quality_path is not None:
        try:
            from internship_finder import employer_quality
            quality_map = employer_quality.load_employer_quality(
                employer_quality_path)
            if quality_map:
                sweet_spot_rows = employer_quality.sweet_spot_companies(
                    jobs, quality_map, company_intel_map)
        except Exception:  # noqa: BLE001 — F15 é best-effort, nunca erro
            quality_map = None
            sweet_spot_rows = None

    # F29 — benchmark salarial curado (ESTIMATIVA DE MERCADO, rotulada,
    # campo separado do salário detectado). Loader tolerante: ausente/
    # corrompido -> {} -> sem estimativa, nunca erro.
    salary_benchmark_map: dict | None = None
    if salary_benchmark_path is not None:
        try:
            from internship_finder import salary_benchmark
            salary_benchmark_map = salary_benchmark.load_salary_benchmark(
                salary_benchmark_path)
        except Exception:  # noqa: BLE001 — F29 é best-effort, nunca erro
            salary_benchmark_map = None

    translation_cache: dict = {}
    if translation_cache_path:
        try:
            from internship_finder import display_translate
            translation_cache = display_translate.load_translation_cache(
                translation_cache_path)
        except Exception:  # noqa: BLE001 — cache e best-effort, nunca erro
            translation_cache = {}

    # F54 — aliases de display de empresa (config/display_aliases.json).
    # Loader tolerante: ausente/corrompido -> {} (higiene de mojibake
    # permanece; nomes de empresa ficam ORIGINAIS), nunca erro.
    display_aliases: dict = {}
    if display_aliases_path:
        try:
            from internship_finder import display_hygiene
            display_aliases = display_hygiene.load_display_aliases(
                display_aliases_path)
        except Exception:  # noqa: BLE001 — F54 é best-effort, nunca erro
            display_aliases = {}

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

    # F36 — seção EU non-DE: terceiro perfil (canal secundário F7), mesmo
    # padrão da seção Materials; top 10 por eu_score SOBRE O ESTRATO não-DE
    # (a seção "Fora da Alemanha" só promete vagas fora da DE).
    eu: list[dict] | None = None
    if include_eu:
        try:
            from internship_finder.eu_ranking import rank_eu_stratum
            eu = rank_eu_stratum(jobs)[:EU_SECTION_TOP]
        except Exception:  # noqa: BLE001 — seção opcional nunca derruba
            eu = None

    html = render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=generated,
        top=top, company_intel_map=company_intel_map,
        new_since_ids=new_ids, dead_link_ids=dead_link_ids,
        materials=materials, eu=eu,
        translation_cache=translation_cache,
        watchlist_events=watchlist_events,
        tracker_db=tracker_db,
        quality_map=quality_map, sweet_spot_rows=sweet_spot_rows,
        inapplicable_ids=inapplicable_ids,
        salary_benchmark_map=salary_benchmark_map,
        full_list=full, profile_maps=profile_maps,
        vitrine=vitrine,
        display_aliases=display_aliases,
    )
    # F15 §4 — a seção Ponto ótimo só permanece se a página COM ela
    # couber no cap duro (150KB); a MEDIÇÃO é no render FINAL (com todas
    # as seções do dia — 🆕/🎯/🧪 — contextos reais). Estourou: remonta
    # uma vez sem a seção (o badge ⭐ nos cards PERMANECE) e reporta a
    # pendência com o tamanho medido. Nunca estoura o cap por causa
    # da seção.
    hard_cap = (page_full_cap_bytes(len(jobs)) if full
                else PAGE_HARD_CAP_BYTES)
    if sweet_spot_rows and len(html.encode("utf-8")) > hard_cap:
        size_with = len(html.encode("utf-8"))
        html = render_size_aware(
            jobs, total_eligible=len(jobs), generated_at=generated,
            top=top, company_intel_map=company_intel_map,
            new_since_ids=new_ids, dead_link_ids=dead_link_ids,
            materials=materials, eu=eu,
            translation_cache=translation_cache,
            watchlist_events=watchlist_events,
            tracker_db=tracker_db,
            quality_map=quality_map, sweet_spot_rows=None,
            inapplicable_ids=inapplicable_ids,
            salary_benchmark_map=salary_benchmark_map,
            full_list=full, profile_maps=profile_maps,
            vitrine=vitrine,
            display_aliases=display_aliases,
        )
        print(f"pages: seção ⭐ Ponto ótimo OMITIDA — página com ela "
              f"({size_with} bytes) estoura o cap de {hard_cap} "
              f"bytes; publicada sem a seção "
              f"({len(html.encode('utf-8'))} bytes)")
    return html


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
    parser.add_argument("--inapplicable-list", default=None, metavar="PATH",
                        help="F20: arquivo com ids de vagas inaplicaveis "
                        "(re-avaliacao pós-hidratação F18), um por linha; "
                        "descem do top com badge próprio (nunca o de morta)")
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
    parser.add_argument("--tracker-db", default="data/personal/jobs_personal.db",
                        metavar="PATH",
                        help="banco pessoal do tracker (F14; lido em "
                             "modo read-only p/ o badge 'já aplicou'; "
                             "default data/personal/jobs_personal.db do "
                             "repo; '' desliga o badge)")
    parser.add_argument("--employer-quality", default="config/employer_quality.json",
                        metavar="PATH",
                        help="mapa curado de qualidade do empregador "
                             "(F15; default config/employer_quality.json "
                             "do repo; '' desliga badge ⭐/🏆 e a seção "
                             "Ponto ótimo)")
    parser.add_argument("--salary-benchmark", default="config/salary_benchmark.json",
                        metavar="PATH",
                        help="benchmark salarial curado (F29; default "
                             "config/salary_benchmark.json do repo; '' "
                             "desliga a estimativa de mercado rotulada)")
    parser.add_argument("--display-aliases", default="config/display_aliases.json",
                        metavar="PATH",
                        help="aliases de display de empresa (F54; "
                             "default config/display_aliases.json do "
                             "repo; '' desliga — o sanitizer mojibake "
                             "permanece ativo em qualquer caso)")
    parser.add_argument("--full-list", dest="full_list", action="store_true",
                        help="F43: regime FULL-LIST — TODAS as vagas "
                             "elegiveis na pagina unica (sem corte top-N e "
                             "sem cap 2/empresa, que sao regras de EXIBICAO "
                             "do top), com abas por perfil + lazy-render; o "
                             "cap passa a ser proporcional ao universo. "
                             "Default: regime top-N legado da F11 (intacto).")
    parser.add_argument("--no-eu", dest="include_eu", action="store_false",
                        help="desliga a seção EU non-DE (F36; ligada por "
                             "default)")
    parser.add_argument("--vitrine", dest="vitrine", action="store_true",
                        help="F52: vitrine recruiter — bloco About this "
                             "system (EN) no topo, light mode via "
                             "prefers-color-scheme, meta description + OG "
                             "no head e favicon data-URI. Default: OFF "
                             "(página byte a byte a pré-F52).")
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
    inapplicable_ids: set[str] = set()
    if args.inapplicable_list:
        ip = Path(args.inapplicable_list)
        if ip.exists():
            inapplicable_ids = {line.strip() for line in
                                ip.read_text(encoding="utf-8").splitlines()
                                if line.strip()}

    archive_root = Path(args.archive) if args.archive else None
    translation_cache_path = (
        Path(args.translation_cache) if args.translation_cache else None
    )
    watchlist_path = Path(args.watchlist) if args.watchlist else None
    tracker_db = Path(args.tracker_db) if args.tracker_db else None
    employer_quality_path = (
        Path(args.employer_quality) if args.employer_quality else None
    )
    salary_benchmark_path = (
        Path(args.salary_benchmark) if args.salary_benchmark else None
    )
    display_aliases_path = (
        Path(args.display_aliases) if args.display_aliases else None
    )
    page = render_minimal_html_from_file(
        Path(args.input), top=args.top, company_intel_map=company_intel_map,
        archive_root=archive_root, dead_link_ids=dead_ids,
        translation_cache_path=translation_cache_path,
        watchlist_path=watchlist_path,
        tracker_db=tracker_db,
        employer_quality_path=employer_quality_path,
        inapplicable_ids=inapplicable_ids,
        salary_benchmark_path=salary_benchmark_path,
        include_eu=args.include_eu,
        full_list=args.full_list,
        vitrine=args.vitrine,
        display_aliases_path=display_aliases_path,
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
