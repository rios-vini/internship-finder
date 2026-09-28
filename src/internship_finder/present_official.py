"""Apresentacao da evidencia da pagina oficial (Fase D2) — view PURA, read-only.

Ponto de CONTATO UNICO entre os produtos (ranking HTML, e futuros digest/
fit) e a evidencia coletada pela Fase D (``official_page.py``): a UI importa
SOMENTE este modulo — nunca lê ``job["official_page"]`` cru. Mesmo padrao
arquitetural do ``enrichment/present.py`` (Fase 3): o view apenas ADICIONA
contexto na apresentacao; nunca decide elegibilidade, nunca altera/cria
score, nunca reordena, nunca exclui vaga, nunca bloqueia publicacao.

O QUE A FASE D PRODUZ (raw) x O QUE A D2 CONSOME (view):

    official_page.status          ok (101)         -> "verificada em <data>"
    official_page.status          not_found (1)    -> "nao foi encontrada"
    official_page.status          redirected/      -> INTERNO (sem UI: status
                                  js_rendered/       tecnico; redirect 200 e
                                  http_error(403)/    bloqueio/JS NAO dizem
                                  empty_content       nada sobre a vaga)
    jsonld.valid_through          13 casos         -> "validThrough do
                                                       JobPosting: <data>"
    jsonld.location_relation      "confirmed" (15) -> "local confirmado pela
                                                       pagina oficial"
    jsonld.location_relation      "conflict" (3)    -> INTERNO (nao confunde o
                                                       usuario; alocacao
                                                       canonica nunca muda)
    jsonld.employment_type        23 casos          -> INTERNO (o enum descreve
                                                       o REGIME do contrato,
                                                       nao a natureza da vaga —
                                                       Fase B; badge induziria
                                                       leitura de autoridade)
    jsonld.salary                 1 (duplica ATS)  -> INTERNO
    jsonld.date_posted            23 (posted_at ok)-> INTERNO
    jsonld.identifier             15               -> INTERNO (evidencia)
    jsonld.description            evidencia         -> INTERNO (0 melhoradas
                                                       na Fase D; o snippet do
                                                       anuncio ja vem do ATS)

REGRA DA ESPECIFICACAO D2 (secoes 4/5): ``validThrough`` e validade da
PAGINA/posting, NUNCA ``application_deadline`` — as duas datas coexistem
rotuladas quando ambas existem (hoje: 0 overlap; 13/13 valid_through sao
de vagas SEM deadline). Data vencida NAO afirma vaga encerrada — apenas a
exibe; a interpretacao fica com o usuario. Nenhum destes dados entra em
score, urgencia, filtro ou ranking.
"""

from __future__ import annotations

# Status de pagina que a UI exibe como FATO de verificacao (spec secao 3).
# ``ok`` = pagina existe e casa com a vaga (classify_page + conteudo);
# ``not_found`` = 404 — fato objetivo de pagina inexistente na verificacao.
# Os demais (redirected/js_rendered/empty_content/http_error/timeout/
# fetch_error) ficam internos: sao status tecnicos do FETCH, nao da vaga.
PAGE_VERIFIED_STATUSES = frozenset({"ok"})
PAGE_NOT_FOUND_STATUSES = frozenset({"not_found"})


def _evidence(job: dict | None) -> dict:
    """``job["official_page"]`` quando e dict com status; {} quando ausente.

    Nunca quebra: job sem ``official_page`` (vaga nao candidata no run,
    snapshot pre-Fase D, caminho SQLite sem JSON) devolve {} e todas as
    funcoes abaixo omitem as linhas — a pagina funciona 100% sem evidencia.
    """
    if not isinstance(job, dict):
        return {}
    op = job.get("official_page")
    return op if isinstance(op, dict) and op.get("status") else {}


def page_status(op: dict | None) -> str | None:
    """Status de verificacao util p/ UI: ``verified`` | ``not_found`` | None.

    Contrato da view (spec secao 3): ``200 OK`` NUNCA vira garantia de que
    a vaga esta aberta — apenas registra o FATO de que a URL foi verificada
    e casou com a vaga na data indicada. Status tecnicos do fetch nao sao
    exibidos.
    """
    status = (op or {}).get("status")
    if status in PAGE_VERIFIED_STATUSES:
        return "verified"
    if status in PAGE_NOT_FOUND_STATUSES:
        return "not_found"
    return None


def checked_date(op: dict | None) -> str | None:
    """Data da verificacao (``checked_at``) como ``YYYY-MM-DD`` ou None.

    ``checked_at`` e ISO com hora; a UI exibe apenas a DATA (quando a
    verificacao ocorreu), no padrao das demais datas do produto.
    """
    text = str((op or {}).get("checked_at") or "").strip()
    return text[:10] if len(text) >= 10 else None


def valid_through(job: dict | None) -> str | None:
    """``jsonld.valid_through`` como ``YYYY-MM-DD`` ou None.

    Mantem a ORIGEM explicita (JobPosting validThrough da pagina oficial);
    o rotulo final vem do render. NUNCA e promovida a ``application_deadline``
    (spec secao 4): quem chama recebe uma string rotulada pela view.
    """
    op = _evidence(job)
    if (op.get("status") or "") not in PAGE_VERIFIED_STATUSES:
        # validThrough so e evidencia de pagina VERIFICADA (spec Fase D §5:
        # conteudo de redirect nunca vira evidencia).
        return None
    value = (op.get("jsonld") or {}).get("valid_through")
    if isinstance(value, str) and value.strip():
        return value.strip()[:10]
    return None


def location_confirmed(job: dict | None) -> bool:
    """True quando a cidade do JobPosting confirma a localizacao atual.

    (spec secao 5: indicacao discreta de confirmacao; conflito fica interno
    e a localizacao canonica nunca muda por esta via.)
    """
    op = _evidence(job)
    if (op.get("status") or "") not in PAGE_VERIFIED_STATUSES:
        return False
    rel = (op.get("jsonld") or {}).get("location_relation")
    return rel == "confirmed"


def official_view(job: dict | None) -> dict | None:
    """Vaga -> dict de CAMPOS PRONTOS p/ exibicao; None quando nada a exibir.

    Campos: ``status`` ("verified"/"not_found"), ``checked`` (YYYY-MM-DD),
    ``valid_through`` (YYYY-MM-DD), ``location_confirmed`` (bool). Labels
    ficam no render (interface.py), como no par ``present.view``/``_ENR_*``.
    Vagas sem evidencia util devolvem None — o render omite as linhas e o
    HTML fica identico ao anterior para elas (compat com snapshot pre-D2).
    """
    op = _evidence(job)
    if not op:
        return None
    status = page_status(op)
    vthr = valid_through(job)
    loc_ok = location_confirmed(job)
    if status is None and vthr is None and not loc_ok:
        return None
    return {
        "status": status,
        "checked": checked_date(op),
        "valid_through": vthr,
        "location_confirmed": loc_ok,
    }


def view_map(jobs: list[dict]) -> dict[str, dict]:
    """{job_id: view} — vagas sem evidencia util ficam FORA (o render trata
    ausencia como 'sem linha', igual ao enrichment_map)."""
    out: dict[str, dict] = {}
    for job in jobs or []:
        if not isinstance(job, dict):
            continue
        jid = str(job.get("id") or "")
        if not jid:
            continue
        v = official_view(job)
        if v is not None:
            out[jid] = v
    return out


def lines(view_data: dict | None) -> list[dict]:
    """Linhas de fato da evidencia no shape do render existente
    (``{"key": ..., "kind": ..., "detail": ...}``), PT-BR, prontas p/ os
    ``<p class="mut facts">`` de ``_details_html`` (interface.py).

    Ordem (especificacao D2 §2: status da pagina -> validThrough ->
    location): verificada em <data> / pagina nao encontrada na verificacao
    de <data> / JobPosting validThrough: <data> / local confirmado pela
    pagina oficial. ``kind`` e sempre ``"info"`` — nenhum destes dados e
    alerta de candidatura (nao entram em readiness/problems).
    """
    if not view_data:
        return []
    out: list[dict] = []
    status = view_data.get("status")
    checked = view_data.get("checked")
    if status == "verified":
        when = f" em {checked}" if checked else ""
        out.append({
            "key": "op_verified", "kind": "info",
            "detail": f"página oficial verificada{when}",
        })
    elif status == "not_found":
        when = f" em {checked}" if checked else ""
        out.append({
            "key": "op_not_found", "kind": "info",
            "detail": f"página oficial não foi encontrada na verificação{when}",
        })
    vthr = view_data.get("valid_through")
    if vthr:
        out.append({
            "key": "op_valid_through", "kind": "info",
            "detail": f"validThrough do JobPosting (página oficial): {vthr}",
        })
    if view_data.get("location_confirmed"):
        out.append({
            "key": "op_location", "kind": "info",
            "detail": "local confirmado pela página oficial",
        })
    return out


def chip(view_data: dict | None) -> str | None:
    """Chip discreto QUANDO ha fato de verificacao relevante (spec secao 3).

    Apenas ``not_found`` ganha chip VISIVEL (o usuario precisa saber ANTES
    de abrir o link que a pagina pode nao existir mais): "🔗 página não
    encontrada na verificação". Pagina ok NAO ganha chip — 101 de 150
    teriam o mesmo texto informativo; o fato vive na linha de detalhe
    recolhida, sem ruido. Nenhum outro status vira chip.
    """
    if not view_data:
        return None
    if view_data.get("status") == "not_found":
        checked = view_data.get("checked")
        when = f" ({checked})" if checked else ""
        return f"🔗 página não encontrada na verificação{when}"
    return None

