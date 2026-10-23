"""Vitalidade de URL do top exibido (F11) + liveness v2 soft-dead (F20).

O feed da Bundesagentur nunca remove vagas preenchidas (medicao 04/10: vaga
SAP do topo com posted 25/08 retornando 410 Gone; mediana de idade das 502
vagas BA = 49 dias). O ranking continua correto, mas o usuario clica em
anuncios mortos. Este estagio verifica os URLs do topo EXIBIDO antes da
publicacao e devolve o conjunto de ids com link confirmadamente morto.

Regras (spec F11, item 3 + F20, item 2):

- **404/410 = morta** (hard-dead, F11). A vaga desce do top exibido; a
  proxima sobe. Nada e removido do JSON/CSV (data/ e intocavel — sao a base).
- **F20 — soft-dead**: HTTP 200/2xx cujo CORPO evidencia vaga encerrada —
  (i) marcador textual ("this position has been filled", "no longer
  accepting applications", "nicht mehr verfugbar", "Stelle ist besetzt"...
  lista configuravel, case-insensitive); (ii) redirect-para-homepage: a URL
  final apos redirects e a raiz do site de carreiras (path vazio/"("/")
  em vez de pagina de vaga — caso DHL: a URL da vaga redireciona para a
  homepage com 200, mas a pagina REAL da vaga esta 410); (iii) shell SPA
  de board: 200 com tamanho exato assinado (~268.630 bytes do shell
  generico eightfold) OU <title> generico de board sem o id da vaga
  (caso Infineon). Marcada = MESMA semantica do 404/410 (desce do top).
- **403/429/timeout/DNS = bloqueio de bot ou rede**: ignora, nao marca
  nada (marcar por 403 derrubaria vagas vivas de sites com bot-wall).
- **Falha total do estágio** (rede fora: nenhuma resposta HTTP recebida):
  log + devolve conjunto VAZIO — o pipeline nunca derruba por causa do
  check e nunca marca mortas sem evidência.
- **Deadline defensivo**: estourou, devolve o que já foi confirmado
  (mortas observadas com resposta HTTP real) e loga.

F20 — o check passa a GET (os marcadores soft-dead vivem no CORPO; HEAD não
tem corpo). Mesmo custo de timeout curto (~5s), delay sequencial e UA
honesto; o passe continua bounded ao top exibido (o chamador corta).

Hidratação (F20, item 3): o MESMO passe HTTP devolve, para as vagas do
top-N com descrição curta, a descrição completa extraída da página.
Falha de fetch/parse = a descrição original permanece (nunca piora). A
re-avaliação de aplicabilidade (german_level/requires_master da F18) roda
no chamador sobre a descrição hidratada — ver ``refresh_daily``.

F22 (09/10) — hidratação JSON-LD-ONLY: ``parse_job_description`` aceita
SOMENTE JSON-LD schema.org JobPosting (campo ``description``). Os caminhos
``og:description``/``description`` SAÍRAM da hidratação (pendência §5.3 da
F20): boards como KPMG/Thales servem meta GENÉRICA do board que passava no
gate de qualidade (>= 120 chars) e era inútil como descrição da vaga. O
gate (>= 120 chars) passa a valer também para o JSON-LD extraído.

F94 (21/10) — liveness v2: o passe devolve VEREDITO por vaga checada
(``alive | dead | unknown`` em ``stats["verdicts"]``) para o chamador
persistir no registro; ``unknown`` = checou e não deu para determinar
(wall SAML/csod, erro de rede, erro do stub Lidl rdr) — NUNCA morto por
falta de parse. Edge cases de provedor: SAML => unknown +
``manual_check_required``; stub Lidl ``rdr/jump-to-job`` => o veredito é
do ALVO (re-post: vaga fora do feed/eligible mas VIVA no site — pacote
válido não se descarta). ``needs_liveness_recheck``: hook do fluxo de
aplicação — veredito >24h pede re-teste antes do pacote (display/digest,
nunca exclusão).
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from pathlib import Path

__all__ = [
    "LIVENESS_UA", "LIVENESS_TIMEOUT_S", "LIVENESS_DELAY_S",
    "LIVENESS_DEADLINE_S", "LIVENESS_MAX_BYTES", "SOFT_DEAD_MARKERS",
    "FAKE200_MARKERS", "FAKE200_MAX_BODY_CHARS",
    "SPA_SHELL_SIZES", "SPA_SHELL_TITLE_RE", "DEAD_STATUS",
    "SAML_URL_MARKER", "SAML_BODY_MARKERS", "REDIRECT_STUB_RE",
    "LIVENESS_RECHECK_AFTER_H",
    "check_liveness", "check_liveness_v2", "parse_job_description",
    "needs_liveness_recheck",
]

# UA honesto e identificavel (spec: "UA honesto") — nao imita browser.
LIVENESS_UA = "internship-finder-liveness/1.1 (job ranking link check)"

LIVENESS_TIMEOUT_S = 5.0   # timeout por request (spec: curto, ~5s)
LIVENESS_DELAY_S = 0.2    # pausa curta entre requests sequenciais
LIVENESS_DEADLINE_S = 240.0  # teto TOTAL do estagio (50 reqs * ~4.8s pior caso)

# Teto de bytes lidos do corpo por request (soft-dead markers + hidratacao
# vivem no inicio do HTML; 512KB cobre qualquer job page real e protege o
# estagio de corpos gigantes/streams).
LIVENESS_MAX_BYTES = 512 * 1024

# Status que significam "anuncio removido para sempre" (spec F11: 404/410).
DEAD_STATUS = frozenset({404, 410})

# F20 — marcadores de vaga encerrada no CORPO (case-insensitive; lista
# configuravel). Medidos na investigacao 07/10: Deutsche Borse retorna 200
# com "Sorry, this position has been filled" no corpo.
SOFT_DEAD_MARKERS = (
    "this position has been filled",
    "no longer accepting applications",
    "no longer accepting",
    "position is no longer",
    "nicht mehr verfügbar",
    "stelle ist besetzt",
)

# F87 — 200-falso textual de página de empresa (a classe E1 da F76: resposta
# 200 que mente sobre o conteúdo — lá era WAF no lugar do CSV, aqui é aviso
# de vaga preenchida). Caso real (Festo St. Ingbert, 20/10): jobs.festo.com
# responde 200 com "Diese Stelle wurde leider bereits besetzt" — nenhum
# marcador SOFT_DEAD existente casa ("stelle ist besetzt" tem outra ordem de
# palavras). Gate DUPLO anti-falso-positivo:
#   (a) marcador EXPLÍCITO de vaga preenchida (nada de substring genérica);
#   (b) corpo CURTO (len <= FAKE200_MAX_BODY_CHARS): página real de vaga é
#       grande (dezenas~centenas de KB; shell SPA ~268KB já coberto por
#       _is_spa_shell); o aviso de preenchida é uma página mínima. Um
#       "position filled" citado no meio de um anúncio grande e vivo não
#       marca nada.
# "not available" NÃO entra na lista: substring genérica ("item not
# available", geo-block, stub de cookie-wall curto) — falso-positivo em
# página viva; as variantes fortes ("position is no longer", "this position
# has been filled") já são cobertas por SOFT_DEAD_MARKERS.
FAKE200_MARKERS = ("bereits besetzt", "position filled")
FAKE200_MAX_BODY_CHARS = 4096

# ---------------------------------------------------------------------------
# F94 — Liveness v2: estado persistente + edge cases de provedor.
#
# A F87 mata/remove mas não deixa estado CONSULTÁVEL por vaga; aqui o passe
# devolve um VEREDITO por vaga checada (``alive | dead | unknown``) para o
# chamador persistir no registro (``liveness_status`` +
# ``liveness_checked_at``). ``unknown`` = checou e NÃO deu para determinar —
# NUNCA "morto por falta de parse" (a doutrina da F11/F87 vira campo).
#
# Dois edge cases medidos ao vivo (21/10, probes da fase):
#
# - **SAML/csod** (henkel ×4 do registro): a URL da vaga redireciona (3
#   hops) para ``/samldefault.aspx`` com 200 e corpo de 3.6KB
#   ``<title>SAML Authentication Request</title>`` — autenticação na
#   frente do anúncio. Semântica: ``unknown`` +
#   ``manual_check_required`` — o wall PROVA nada sobre a vaga; marcar
#   dead por não conseguir parsear seria exatamente o FP que a F20
#   proíbe. Padrão genérico (URL/corpo), sem hard-code de empresa.
# - **Lidl redirect stub** (``/rdr/jump-to-job/<ref>``): URL ESTÁVEL de
#   apply/ref que redireciona (1 hop medido) para a página REAL da vaga —
#   o veredito vem do ALVO, não do stub. Caso re-post (Ref 753653,
#   registro 21/10): a vaga antiga sai do eligible (re-post ganhou novo
#   requisition id no feed) mas o alvo SEGUE VIVO no site — pacote de
#   candidatura VÁLIDO não pode ser descartado. Stub que responde 404/410
#   ou 500 (ref inexistente: 500 "We'll be right back", 210KB, medido)
#   não prova morte do ANÚNCIO => ``unknown``, nunca dead/remoção F39.
# ---------------------------------------------------------------------------

# SAML: marcador na URL FINAL (path do IdP — ``samldefault.aspx``) OU título/
# corpo curto declarando o request de autenticação (medido henkel.csod.com).
SAML_URL_MARKER = "saml"
SAML_BODY_MARKERS = (
    "saml authentication request",
    "samlrequest",
)
# Corpo que um wall de autenticação pode ter sem deixar de ser wall — o
# check de corpo SAML olha só o início (walls são páginas mínimas; a
# henkel medida tem 3.6KB).
_SAML_BODY_SCAN_CHARS = 8192

# Lidl: URL de redirect estável por REF (apply/manifest). O veredito vem do
# ALVO após o redirect; erros do stub nunca provam morte do anúncio.
REDIRECT_STUB_RE = re.compile(r"/rdr/jump-to-job/(?:[^/?#]+)", re.IGNORECASE)

# F94 item 4 — re-check antes do pacote: veredito mais velho que isso (em
# horas) pede re-teste antes de virar candidatura. Hook do fluxo de
# aplicação (display/digest), NUNCA exclusão.
LIVENESS_RECHECK_AFTER_H = 24

# F20 — assinaturas de shell SPA de board (Infineon/eightfold): tamanho
# EXATO do shell generico servido para vaga morta (268.630 bytes medidos
# 07/10) OU <title> generico de board sem pin da vaga. Sem hard-code de
# empresa: a assinatura e do PADRAO (tamanho exato + title), nao do site.
SPA_SHELL_SIZES = frozenset({268_630})

# <title> genericos de board (job board shell): quando o title NAO carrega
# o titulo/id da vaga, a pagina e um shell, nao um anuncio. Match exato
# (casefold, strip) contra a lista — "Infineon Jobs" casa; "Working Student
# (m/w/d) - Infineon" nao.
SPA_SHELL_TITLE_RE = re.compile(
    r"^(?:jobs(?: at .+)?|careers(?: at .+)?|.+ jobs|job openings"
    r"|work with us|join us|vacancies|stellenangebote|karriere(?: bei .+)?)$",
    re.IGNORECASE,
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_JSON_LD_JOB_RE = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# F22 — gate de qualidade: descrição extraída precisa ter pelo menos
# este número de caracteres para valer como descrição da vaga (o mesmo
# gate que valia para og/meta na F20; agora vale para o JSON-LD). Metas
# genéricas de board e snippets curtos morrem aqui.
_DESCRIPTION_MIN_CHARS = 120


def _soft_dead_in_body(body_text: str) -> str | None:
    """Marcador de vaga encerrada presente no corpo? Devolve o marcador.

    Case-insensitive (o corpo e comparado apos casefold). ``None`` = corpo
    vivo. Pura — testavel offline com strings fixture.
    """
    folded = body_text.casefold()
    for marker in SOFT_DEAD_MARKERS:
        if marker.casefold() in folded:
            return marker
    return None


def _fake_200_in_short_body(body_text: str, body_len: int) -> str | None:
    """F87 — 200-falso textual em corpo CURTO (página de empresa)?

    Caso Festo: HTTP 200 cujo corpo (curto) declara a vaga preenchida
    ("Diese Stelle wurde leider bereits besetzt") — anúncio encerrado por
    trás de um 200. Gate duplo: marcador explícito de FAKE200_MARKERS E
    corpo dentro de FAKE200_MAX_BODY_CHARS (página real de vaga é grande;
    o aviso de preenchida é mínima). Pura — testavel offline com fixture.
    ``None`` = nada marcado por este check.
    """
    if body_len > FAKE200_MAX_BODY_CHARS:
        return None
    folded = body_text.casefold()
    for marker in FAKE200_MARKERS:
        if marker.casefold() in folded:
            return marker
    return None


def _is_spa_shell(body_text: str, body_bytes: int) -> bool:
    """Corpo e um shell generico de board (200 sem anuncio real)?

    Assinatura dupla e FP-safe por combinacao: (a) tamanho EXATO na lista
    de tamanhos de shell conhecidos (medidos; um job page real raramente
    tem exatamente 268.630 bytes); OU (b) <title> generico de board
    (match exato contra o padrao — "Infineon Jobs" casa, "Working Student
    - Infineon" nao). Sem hard-code de empresa.
    """
    if body_bytes in SPA_SHELL_SIZES:
        return True
    m = _TITLE_RE.search(body_text[:4096])
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        if title and SPA_SHELL_TITLE_RE.match(title):
            return True
    return False


def _final_path_is_homepage(final_url: str, original_url: str) -> bool:
    """A URL final apos redirects e a raiz/homepage em vez de pagina de vaga?

    Caso DHL: a URL da vaga redireciona para a homepage do site de
    carreiras com 200. Sinal: path final vazio ou "/" (e o host pode ate
    ser o mesmo). Comparacao por path apenas — query/fragment nao
    caracterizam homepage. A URL ORIGINAL precisa ter path de vaga
    (senao toda vaga publicada na raiz seria marcada — anti-FP).
    """
    try:
        from urllib.parse import urlsplit
        orig = urlsplit(str(original_url or ""))
        final = urlsplit(str(final_url or ""))
    except ValueError:
        return False
    if not final.path or final.path == "/":
        # so e redirect-para-homepage se o original NAO era homepage
        return bool(orig.path) and orig.path != "/"
    return False


def _is_saml_wall(final_url: str, body_text: str) -> str | None:
    """F94 — a resposta é um wall de autenticação SAML (csod/IdP)?

    Caso medido (henkel.csod.com 21/10): a URL da vaga redireciona para
    ``/samldefault.aspx?...`` respondendo 200 com corpo mínimo
    ``<title>SAML Authentication Request</title>``. O wall PROVA nada
    sobre a vaga — o veredito é ``unknown`` + ``manual_check_required``,
    NUNCA dead. Sinal duplo e FP-safe: marcador SAML no PATH da URL final
    OU no corpo (o título/corpo declarando o auth request). Pura.
    """
    from urllib.parse import urlsplit
    try:
        path = urlsplit(str(final_url or "")).path.casefold()
    except ValueError:
        path = ""
    if SAML_URL_MARKER in path:
        return f"url:{path}"
    folded = body_text[:_SAML_BODY_SCAN_CHARS].casefold()
    for marker in SAML_BODY_MARKERS:
        if marker.casefold() in folded:
            return f"body:{marker}"
    return None


def _is_redirect_stub(url: str) -> bool:
    """F94 — a URL é um stub de redirect por REF (Lidl rdr/jump-to-job)?

    Pura. O stub não é a página da vaga: o veredito vem do ALVO após o
    redirect (o opener segue redirects — a resposta que chega aqui É a do
    alvo quando ele existe). Erros do STUB (404/410/5xx, medido: Lidl
    serve 500 "We'll be right back" para ref inexistente) não provam
    morte do anúncio => ``unknown``, nunca dead/F39.
    """
    return bool(REDIRECT_STUB_RE.search(str(url or "")))


def needs_liveness_recheck(job: dict, now=None) -> bool:
    """F94 item 4 — a vaga pede re-teste de liveness antes do pacote?

    Hook DOCUMENTADO para o fluxo de aplicação: quando uma vaga vai virar
    pacote de candidatura (o dono vai investir tempo nela), um veredito
    com mais de ``LIVENESS_RECHECK_AFTER_H`` horas (24) deve ser
    re-testado ANTES — mortes entre avaliação e envio são o padrão
    medido (Simvia/Festo 20/10, GFO 21/10). Semântica display/digest:
    sinal para o fluxo de aplicação, NUNCA exclusão do JSON.

    - Sem estado persistido (vaga nunca checada) => ``True`` — checar
      antes é sempre a resposta honesta.
    - ``liveness_status`` "unknown" => ``True`` sempre: veredito
      inconclusivo não autoriza candidatura sem re-teste manual.
    - ``liveness_checked_at`` ilegível/ausente => ``True`` (defensivo).
    """
    status = str(job.get("liveness_status") or "").strip().lower()
    if status == "unknown":
        return True
    checked_at = str(job.get("liveness_checked_at") or "").strip()
    if not checked_at:
        return True
    if now is None:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
    try:
        from datetime import datetime as _dt
        checked = _dt.fromisoformat(checked_at)
    except ValueError:
        return True
    if checked.tzinfo is None:
        from datetime import timezone as _tz
        checked = checked.replace(tzinfo=_tz.utc)
    if now.tzinfo is None:
        from datetime import timezone as _tz
        now = now.replace(tzinfo=_tz.utc)
    age_h = (now - checked).total_seconds() / 3600.0
    return age_h > LIVENESS_RECHECK_AFTER_H


def _loads_lenient(text: str):
    """F91 — parse JSON-LD tolerante a malformação de board (pura).

    Boards reais (absolventa, medido 21/10: 30/30 páginas) emitem JSON-LD
    ``JobPosting`` com (a) caracteres de controle crus dentro de strings
    (newlines literais — ``json.loads`` estrito rejeita) e (b) escapes
    inválidos (``\\x`` — rejeita mesmo com ``strict=False``). Cascata, do
    mais conservador ao mais reparador:

    1. ``json.loads(text)`` — caminho atual, zero mudança p/ JSON válido;
    2. ``strict=False`` — libera chars de controle dentro de strings;
    3. reparo de escape: backslash NÃO seguido de escape válido vira
       backslash literal (``\\\\``) + ``strict=False`` — o texto que o
       autor da página quis dizer, não uma invenção nossa.

    ``None`` quando nenhum passo parseia (o chamador pula o bloco — mesmo
    comportamento de hoje para lixo real). Estritamente aditivo: bloco
    que parseava continua idêntico; bloco que falhava silenciosamente
    agora parseia (F20/F65/F91 hidratam descrições de absolventa).
    """
    import json as _json
    import re as _re
    try:
        return _json.loads(text)
    except (ValueError, TypeError):
        pass
    try:
        return _json.loads(text, strict=False)
    except (ValueError, TypeError):
        pass
    try:
        repaired = _re.sub(r'\\(?![\\"/bfnrtu])', r"\\\\", text)
        return _json.loads(repaired, strict=False)
    except (ValueError, TypeError):
        return None


def _iter_jsonld_jobpostings(html: str):
    """Percorre os blocos JSON-LD (objeto | array | @graph) e devolve os
    objetos com ``@type`` contendo ``JobPosting``. Pura (o parse é do
    chamador); segue a mesma convenção do ``official_page`` (Fase D).
    F91: o parse usa ``_loads_lenient`` (malformação de board não mata o
    bloco inteiro); os GATES do ``parse_job_description`` seguem intactos.
    """
    for m in _JSON_LD_JOB_RE.finditer(html):
        data = _loads_lenient(m.group(1).strip())
        if data is None:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, list):
                stack.extend(obj)
                continue
            if not isinstance(obj, dict):
                continue
            node = obj.get("@type", "")
            types = node if isinstance(node, list) else [node]
            if any("JobPosting" in str(t) for t in types):
                yield obj
            # @graph: JobPosting pode vir empacotado dentro dele (padrão
            # de boards modernos) — desce um nível (json.loads produz
            # árvore, sem ciclos: a pilha sempre drena).
            graph = obj.get("@graph")
            if isinstance(graph, list):
                stack.extend(g for g in graph if isinstance(g, (dict, list)))


def parse_job_description(html: str) -> str | None:
    """Descrição completa da vaga a partir do HTML da página (F20; pura).

    F22 — JSON-LD-ONLY: a única fonte aceita é o JSON-LD schema.org
    ``JobPosting.description`` (a fonte real da vaga; pendência §5.3 da
    F20 — og:description e meta description saíram da hidratação porque
    boards servem meta GENÉRICA do board que passava no gate e era inútil
    como descrição da vaga). SEM LLM.

    Gates (o chamador só hidrata quando o resultado é maior que a
    descrição original — nunca piora):

    - JSON-LD presente e parseável, com ``@type`` JobPosting (objeto,
      array ou ``@graph``);
    - campo ``description`` string não-vazia;
    - texto limpo com **>= 120 chars** (metas genéricas de board e
      snippets curtos não são descrição de vaga).

    Devolve ``None`` quando nada é extraível (o chamador mantém a
    descrição original). O texto é normalizado (tags stripadas, espaços
    colapsados) e truncado em 16KB (descrição de vaga real é < 16KB;
    protege o JSON de pagas-por-byte gigantes).
    """
    if not html:
        return None
    for obj in _iter_jsonld_jobpostings(html):
        desc = obj.get("description")
        if not isinstance(desc, str):
            continue
        cleaned = _clean_description(desc)
        if len(cleaned) >= _DESCRIPTION_MIN_CHARS:
            return cleaned
    return None


_DESCRIPTION_CAP = 16 * 1024
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_description(text: str) -> str:
    """Normaliza a descricao extraida: strip de tags, espacos colapsados."""
    import html as _html_mod
    cleaned = _html_mod.unescape(text)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    cleaned = re.sub(r" ?\n ?", "\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned[:_DESCRIPTION_CAP]


def check_liveness(
    jobs: list[dict],
    *,
    timeout: float = LIVENESS_TIMEOUT_S,
    delay: float = LIVENESS_DELAY_S,
    deadline_s: float = LIVENESS_DEADLINE_S,
    opener=None,
    log=None,
    return_details: bool = False,
    short_description_limit: int = 500,
):
    """GET nos ``job.url`` (http/https) de ``jobs``; devolve ids mortos.

    F11 (hard-dead 404/410) + F20 (soft-dead por corpo/redirect/shell) +
    F20 (hidratacao de descricao curta no MESMO passe).

    ``return_details=False`` (default, compat F11): devolve apenas o
    ``set`` de ids mortos. ``return_details=True``: devolve a tupla
    ``(dead_ids, {job_id: descricao_hidratada}, stats)`` — usado pelo
    refresh_daily (F20) para aplicar a hidratacao e re-avaliar
    aplicabilidade; ``short_description_limit`` e o limiar de descricao
    curta (spec F20 item 3: ex. 500).

    ``jobs``: lista ORDENADA do topo exibido (o chamador decide o corte —
    refresh_daily passa o top exibido pos regra 2/empresa). Cada job
    contribui no maximo 1 request. ``opener`` injetavel (testes/CI sem
    rede; default ``urllib.request.urlopen``). ``log`` = logging.Logger
    opcional. Best-effort TOTAL: qualquer problema interno devolve um
    conjunto possivelmente vazio — nunca levanta.
    """
    dead, bodies, stats = check_liveness_v2(
        jobs, timeout=timeout, delay=delay, deadline_s=deadline_s,
        opener=opener, log=log, want_bodies=True,
        short_description_limit=short_description_limit,
    )
    if return_details:
        return dead, bodies, stats
    return dead


def check_liveness_v2(
    jobs: list[dict],
    *,
    timeout: float = LIVENESS_TIMEOUT_S,
    delay: float = LIVENESS_DELAY_S,
    deadline_s: float = LIVENESS_DEADLINE_S,
    opener=None,
    log=None,
    want_bodies: bool = True,
    max_bytes: int = LIVENESS_MAX_BYTES,
    short_description_limit: int = 500,
) -> tuple[set[str], dict[str, str], dict]:
    """Estagio completo de vitalidade + hidratacao (F20). Devolve
    ``(dead_ids, {job_id: descricao_hidratada}, estatisticas)``.

    Um UNICO passe GET sequencial por vaga do top exibido: o corpo serve
    ao soft-dead check (i-iii) E a hidratacao de descricao curta.

    - ``dead_ids``: hard-dead (404/410) + soft-dead (marcador de corpo /
      redirect-para-homepage / shell SPA). Mesma semantica F11: desce do
      top exibido; o JSON/CSV ficam intactos.
    - ``bodies``: para vagas VIVAS com descricao curta (< ``short_description_limit``
      chars) e corpo parseavel, a descricao completa extraida (F22: SOMENTE
      JSON-LD JobPosting — og/meta genericos de board nao hidratam mais).
      Vagas mortas nao hidratam (o corpo e de anuncio encerrado);
      fetch/parse falho = ausencia do mapa (a descricao original permanece
      — nunca piora).
    - ``stats``: contadores do passe (attempts/http_responses/net_errors/
      soft_dead/{marker,redirect,shell}/hydrated/hydration_failed/
      duration_s) para o log e o relatorio da fase. F94 acrescenta, por
      vaga CHECADA, o veredito consultável ``verdicts``:
      ``{job_id: {"status": "alive"|"dead"|"unknown", "detail": str}}``
      (+ ``manual_check_required``: lista de ids atrás de wall SAML —
      o chamador persiste ``liveness_status``/``liveness_checked_at`` no
      registro). Edge cases F94: wall SAML => unknown + manual, NUNCA
      dead; stub de redirect (Lidl ``rdr/jump-to-job``) => o veredito é
      do ALVO, e erros do stub (404/410/5xx/rede) => unknown, nunca
      dead (o 404 do STUB não é o 404 do ANÚNCIO). Falha TOTAL de rede:
      ``verdicts`` vazio — o estado anterior do registro permanece
      (nada foi efetivamente checado; a F11 manda não marcar ninguém).

    ``want_bodies=False`` = modo so-vitalidade (o parse de descricao e
    pulado; usado pelo ``check_liveness`` compativel).

    Best-effort TOTAL (nunca levanta; falha total de rede = nada marcado).
    """
    def _info(msg: str, *args) -> None:
        if log is not None:
            log.info(msg, *args)
        else:
            print("liveness: " + (msg % args if args else msg))

    def _warn(msg: str, *args) -> None:
        if log is not None:
            log.warning(msg, *args)
        else:
            print("liveness(WARN): " + (msg % args if args else msg))

    open_url = opener or urllib.request.urlopen
    started = time.monotonic()
    dead: set[str] = set()
    # F39 — separação hard-dead / soft-dead: hard = HTTP 404/410 (DEAD_STATUS,
    # único veredito definitivo — anúncio removido pelo servidor); soft =
    # marcador de corpo / redirect-para-homepage / shell SPA (200, URL viva).
    # O set plano ``dead`` (compat F11/F20) continua contendo os dois; o
    # refresh_daily (F39) usa os conjuntos separados para decidir exclusão.
    hard_dead: set[str] = set()
    hard_dead_status: dict[str, int] = {}
    bodies: dict[str, str] = {}
    attempts = 0
    http_responses = 0  # qualquer resposta HTTP recebida (inclui 404/410)
    net_errors = 0
    soft_dead = 0
    soft_dead_ids: set[str] = set()  # F39: subconjunto soft de ``dead``
    hydrated = 0
    hydration_failed = 0
    short_candidates = 0
    # F94 — veredito consultável por vaga CHECADA (alive|dead|unknown) +
    # ids atrás de wall SAML (manual_check_required). Preservado no
    # registro pelo chamador (refresh_daily) com liveness_checked_at.
    verdicts: dict[str, dict] = {}
    manual_check: set[str] = set()
    try:
        for idx, job in enumerate(jobs):
            jid = str(job.get("id") or "")
            url = str(job.get("url") or "").strip()
            if not jid or not url.lower().startswith(("http://", "https://")):
                continue  # sem id/url verificavel: nao marcavel
            if time.monotonic() - started > deadline_s:
                _warn("deadline de %.0fs atingido apos %d checks; "
                      "seguindo com %d morta(s) confirmada(s)",
                      deadline_s, attempts, len(dead))
                break
            if idx > 0 and delay > 0:
                time.sleep(delay)
            attempts += 1
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": LIVENESS_UA},
            )
            final_url = url
            body_text = ""
            body_len = 0
            try:
                with open_url(req, timeout=timeout) as resp:
                    http_responses += 1
                    final_url = str(getattr(resp, "url", "") or url)
                    # corpo sempre lido: os marcadores soft-dead (F20)
                    # vivem nele. Fake openers de teste podem nao ter
                    # read() — getattr gracioso (corpo vazio = so o
                    # hard-dead 404/410 vale, comportamento F11 puro).
                    read = getattr(resp, "read", None)
                    raw: bytes = read(max_bytes + 1) if callable(read) else b""  # type: ignore[assignment]
                    if not isinstance(raw, (bytes, bytearray)):
                        raw = b""
                    body_len = len(raw)
                    if body_len > max_bytes:
                        body_len = max_bytes  # truncado: marcadores vivem no inicio
                    body_text = raw[:max_bytes].decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                # HTTPError E uma resposta HTTP do servidor (site no ar).
                http_responses += 1
                if exc.code in DEAD_STATUS:
                    if _is_redirect_stub(url):
                        # F94 — o 404/410 é do STUB de redirect, não do
                        # ANÚNCIO: o alvo não foi alcançado => unknown.
                        # Nunca dead/F39 (padrão Lidl re-post: pacote
                        # válido não é descartado por erro do stub).
                        verdicts[jid] = {
                            "status": "unknown",
                            "detail": f"stub http {exc.code}",
                        }
                        _info("unknown %s: stub de redirect respondeu "
                              "HTTP %d — alvo não testável (%s)",
                              jid, exc.code, url)
                    else:
                        dead.add(jid)
                        hard_dead.add(jid)
                        hard_dead_status[jid] = int(exc.code)
                        verdicts[jid] = {
                            "status": "dead",
                            "detail": f"http {exc.code}",
                        }
                        _info("morta %s: %s -> HTTP %d", jid, url, exc.code)
                else:
                    # 403/429/5xx: bloqueio/erro, não morte (F11) —
                    # honesto no registro: checou, não deu para saber.
                    verdicts[jid] = {
                        "status": "unknown",
                        "detail": f"http {exc.code}",
                    }
                continue
            except Exception:  # noqa: BLE001 — timeout/DNS/SSL/bloqueio
                net_errors += 1  # 403/429 chegam como HTTPError; rede nao
                verdicts[jid] = {"status": "unknown", "detail": "network"}
                continue

            # ---- F94 — wall SAML (csod/IdP) ANTES de qualquer check de
            # corpo: autenticação na frente do anúncio PROVA nada sobre a
            # vaga. unknown + manual_check_required, NUNCA dead.
            # F96 — vereditos do caminho 2xx carregam ``final_url`` quando
            # o opener seguiu redirect (alvo ≠ URL original): é o "alvo
            # final" da fila manual-check. Wall/homepage NUNCA viram link
            # direto no consumidor (o final da henkel é a página do IdP).
            extra: dict = (
                {"final_url": final_url} if final_url != url else {})
            saml = _is_saml_wall(final_url, body_text)
            if saml is not None:
                verdicts[jid] = {
                    **extra,
                    "status": "unknown",
                    "detail": f"saml wall ({saml})",
                }
                manual_check.add(jid)
                _info("unknown %s: wall SAML de autenticação (%s) — "
                      "manual_check_required, nunca dead (%s)",
                      jid, saml, url)
                continue

            # ---- soft-dead checks (so respostas 2xx chegam aqui) ----
            marker = _soft_dead_in_body(body_text)
            if marker is not None:
                dead.add(jid)
                soft_dead += 1
                soft_dead_ids.add(jid)
                verdicts[jid] = {
                    **extra, "status": "dead", "detail": f"marker {marker}"}
                _info("soft-dead %s: corpo contem %r (%s)", jid, marker, url)
                continue
            # F87 — 200-falso textual em corpo curto (Festo "bereits
            # besetzt"): mesma semantica soft-dead (desce do top, nunca
            # excluido por este check sozinho — a remocao do JSON segue
            # sendo exclusiva do hard-dead 404/410, F39).
            fake_marker = _fake_200_in_short_body(body_text, body_len)
            if fake_marker is not None:
                dead.add(jid)
                soft_dead += 1
                soft_dead_ids.add(jid)
                verdicts[jid] = {
                    **extra,
                    "status": "dead",
                    "detail": f"fake200 {fake_marker}",
                }
                _info("soft-dead %s: 200-falso textual %r (%s)",
                      jid, fake_marker, url)
                continue
            if _final_path_is_homepage(final_url, url):
                dead.add(jid)
                soft_dead += 1
                soft_dead_ids.add(jid)
                verdicts[jid] = {
                    **extra, "status": "dead", "detail": "redirect homepage"}
                _info("soft-dead %s: redirect para homepage (%s -> %s)",
                      jid, url, final_url)
                continue
            if _is_spa_shell(body_text, body_len):
                dead.add(jid)
                soft_dead += 1
                soft_dead_ids.add(jid)
                verdicts[jid] = {
                    **extra, "status": "dead", "detail": "spa shell"}
                _info("soft-dead %s: shell SPA de board (%d bytes, %s)",
                      jid, body_len, url)
                continue

            # F94 — sobreviveu a todos os checks: viva. Para stub de
            # redirect, este é o veredito DO ALVO (o opener seguiu o
            # redirect — caso Lidl Ref 753653: alvo 200 de 209KB = viva).
            verdicts[jid] = {**extra, "status": "alive", "detail": ""}

            # ---- hidratacao (vaga VIVA com descricao curta) ----
            if want_bodies and jid not in dead:
                current = str(job.get("description") or "")
                if len(current) < short_description_limit:
                    short_candidates += 1
                    desc = parse_job_description(body_text)
                    if desc and len(desc) > len(current):
                        bodies[jid] = desc
                        hydrated += 1
                    else:
                        hydration_failed += 1
    except Exception as exc:  # noqa: BLE001 — estagio nunca derruba o run
        _warn("estagio falhou (%s: %s); seguindo sem novas marcas",
              type(exc).__name__, exc)
        duration = time.monotonic() - started
        stats = {
            "attempts": attempts, "http_responses": http_responses,
            "net_errors": net_errors, "soft_dead": soft_dead,
            "dead": len(dead), "hydrated": hydrated,
            "hydration_failed": hydration_failed,
            "short_candidates": short_candidates,
            "duration_s": round(duration, 1),
            # F39 — separação hard/soft (o chamador decide o destino de cada
            # classe; ausentes em openers/mocks antigos = nada a excluir).
            "hard_dead_ids": set(hard_dead),
            "hard_dead_status": dict(hard_dead_status),
            "soft_dead_ids": set(soft_dead_ids),
            # F94 — vereditos confirmados ATÉ a falha (evidência real
            # observada); o que não chegou a ser checado fica sem estado.
            "verdicts": {k: dict(v) for k, v in verdicts.items()},
            "manual_check_required": sorted(manual_check),
        }
        return dead, bodies, stats
    # Falha TOTAL de rede: nenhuma resposta HTTP de nenhuma tentativa —
    # nao ha evidencia de nada; nao marca ninguem (spec).
    duration = time.monotonic() - started
    if attempts > 0 and http_responses == 0 and net_errors == attempts:
        _warn("falha total de rede (%d/%d tentativas sem resposta HTTP); "
              "NENHUMA vaga marcada, vereditos ANTERIORES do registro "
              "preservados (nada foi efetivamente checado)", net_errors,
              attempts)
        stats = {
            "attempts": attempts, "http_responses": http_responses,
            "net_errors": net_errors, "soft_dead": 0,
            "dead": set(), "hydrated": 0, "hydration_failed": 0,
            "short_candidates": short_candidates,
            "duration_s": round(duration, 1),
            "hard_dead_ids": set(), "hard_dead_status": {},
            "soft_dead_ids": set(),
            # F94 — SEM vereditos: o run não conseguiu checar nada; o
            # estado persistido no registro (runs anteriores) é a última
            # evidência real e permanece intocado (mesma doutrina F11
            # que não marca mortas sem resposta HTTP).
            "verdicts": {},
            "manual_check_required": [],
        }
        return set(), bodies, stats
    alive_n = sum(1 for v in verdicts.values() if v.get("status") == "alive")
    unknown_n = sum(1 for v in verdicts.values() if v.get("status") == "unknown")
    _info("%d checks: %d morta(s) (%d soft), %d hidratada(s), "
          "%d erro(s) de rede ignorado(s); vereditos F94: %d viva(s), "
          "%d unknown (%d wall SAML)",
          attempts, len(dead), soft_dead, hydrated, net_errors,
          alive_n, unknown_n, len(manual_check))
    stats = {
        "attempts": attempts, "http_responses": http_responses,
        "net_errors": net_errors, "soft_dead": soft_dead,
        "dead": len(dead), "hydrated": hydrated,
        "hydration_failed": hydration_failed,
        "short_candidates": short_candidates,
        "duration_s": round(duration, 1),
        "hard_dead_ids": set(hard_dead),
        "hard_dead_status": dict(hard_dead_status),
        "soft_dead_ids": set(soft_dead_ids),
        # F94 — veredito por vaga checada para o chamador persistir no
        # registro (liveness_status/liveness_checked_at/manual_check).
        "verdicts": {k: dict(v) for k, v in verdicts.items()},
        "manual_check_required": sorted(manual_check),
        "alive": alive_n,
        "unknown": unknown_n,
    }
    return dead, bodies, stats


if __name__ == "__main__":  # uso manual: python scripts/url_liveness.py data/eligible_jobs.json
    import json
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/eligible_jobs.json")
    jobs = json.loads(path.read_text(encoding="utf-8"))
    top = jobs[: int(sys.argv[2]) if len(sys.argv) > 2 else 50]
    dead, bodies, stats = check_liveness_v2(top)
    print("dead ids:", sorted(dead))
    print("hydrated:", len(bodies), "| stats:", stats)
