#!/usr/bin/env python3
"""F96 — Fila manual-check com link DIRETO + id_collision (ITENS 11, 8, 7-typo).

O dono não quer mais "ficar procurando": itens não-avaliáveis (F87) e
borderline ficam espalhados no registro. Este módulo gera o
``data/MANUAL-CHECK.md`` no run diário (estágio do refresh, junto ao
digest) com UMA linha por item: empresa, cargo, **link DIRETO** (o alvo
final, não o redirect — resolve cadeias rdr/jump), motivo
(saml_wall | empty_desc | js_only | cookie_wall | borderline |
external_agreement_gate [F105] | id_collision) e a data
do sighting.

População da fila (spec F96):

- ``not_assessable`` (F87 — campo anotado pelo refresh; a cura da
  hidratação apaga o campo e a linha da fila some no run seguinte);
- ``liveness_status: unknown`` (F94 — checou e não deu para determinar;
  wall SAML ganha ``manual_check_required``);
- ``id_collision`` (F96/ITEM 7-typo — colisão de ID entre empresas
  vivas/mortas: Consultport recruitee "2100111" colidindo com a Simvia
  morta; flag p/ revisão manual, NUNCA remove, NUNCA funde);
- ``external_agreement_gate`` (F105 — o empregador exige o acordo padrão
  DELE assinado pela universidade: J&J Belgium "External agreements
  cannot be accepted"; Danone "3-party internship agreement signed by
  your university"). A vaga segue ELEGÍVEL — o gate é externo e
  resolvível pela universidade do dono — e entra na fila com o motivo
  claro; flag persistida no registro (padrão id_collision).

Doutrina herdada (F87, mantida pela spec F96): a fila é PARALELA —
nenhuma vaga sai do ranking, do Top-5 ou de qualquer superfície. O dono
vê o ⚠️ no card, a linha no digest e agora o arquivo com links prontos.

Decisões de desenho (documentadas no relatório da fase):

- Motivo é o vocabulário da spec (ITEM 8) MAPEADO dos sinais reais:
  F87 ``desc_vazia``→``empty_desc``, ``login_wall``→``saml_wall``,
  ``desc_curta``→``borderline``; F94 unknown com detalhe ``saml …``→
  ``saml_wall``, demais detalhes passam crus (``http 403``, ``network``,
  ``stub http 500``) — mentir motivo inventado é pior que estender o
  vocabulário com o detalhe honesto. ``js_only``/``cookie_wall``
  permanecem no vocabulário SEM produtor hoje (medido: 0 padrões rdr/
  jump/redirect nos 109k registros; SPA shell é classe F94 ``dead``,
  fora da fila por definição).
- ``id_collision`` compara ``(provedor, ats_id)`` — nunca o ID cru:
  ``Simvia|sf_dataset:recruitee:2638996`` e
  ``Consultport|sf_dataset:recruitee:2100111`` vivem no MESMO espaço de
  IDs do recruitee; IDs de provedores distintos não colidem. Empresa é
  normalizada (sufixo parêntese de tenant fora, casefold) para não
  flagar variantes legítimas do MESMO empregador (caso Allegion×
  SimonsVoss medido no caderno F70). Só acende com uma empresa PRESENTE
  no ranking e OUTRA ausente (morta/churn — o caso do doc); par vivo×
  vivo com mesmo ID (RELX×LexisNexis, mesmo grupo) não acende.
- Link direto: wrappers ``?rdr=``/``&rdr=``/``jump`` com alvo
  percent-encoded são desembrulhados OFFLINE (puro, testável); stubs de
  redirect por REF (Lidl ``/rdr/jump-to-job/<ref>``) só resolvem com o
  ``final_url`` que o passe de liveness (F94) já mediu — o campo
  ``liveness_final_url`` entra no registro quando o alvo difere da URL
  original e a vaga está viva. Wall SAML/homepage NUNCA viram link
  direto (o final da henkel é a página do IdP, não a vaga).

Zero rede, best-effort TOTAL: caderno ausente/corrompido => sem
histórico => sem colisões (padrão F70 — degradado nunca derruba o run).
"""
from __future__ import annotations

import datetime
import json
import re
import sqlite3
import unicodedata
import urllib.parse
from pathlib import Path

# ---------------------------------------------------------------------------
# Vocabulário de motivo (ITEM 8/11) + F96
# ---------------------------------------------------------------------------

MOTIVO_SAML_WALL = "saml_wall"
MOTIVO_EMPTY_DESC = "empty_desc"
MOTIVO_JS_ONLY = "js_only"
MOTIVO_COOKIE_WALL = "cookie_wall"
MOTIVO_BORDERLINE = "borderline"
MOTIVO_ID_COLLISION = "id_collision"
# F105 — acordo padrao do empregador assinado pela universidade: gate
# EXTERNO a candidatura (resolvivel pela universidade do dono — ex. J&J
# Belgium: "External agreements cannot be accepted"). A vaga SEGUE
# elegivel e entra na fila com o motivo claro (doutrina F96: a fila e
# PARALELA, nunca exclui).
MOTIVO_EXTERNAL_AGREEMENT_GATE = "external_agreement_gate"

# F87 (not_assessable) -> vocabulário da spec F96.
F87_MOTIVO_MAP = {
    "desc_vazia": MOTIVO_EMPTY_DESC,
    "login_wall": MOTIVO_SAML_WALL,
    "desc_curta": MOTIVO_BORDERLINE,
}

# Prioridade quando a vaga tem MAIS DE UM sinal (o mais acionável para o
# dono primeiro). ``desc_curta`` (borderline) perde para qualquer detalhe
# de liveness unknown: 584 chars de SAML wall são, antes de tudo, um wall.
# F105: o gate de acordo externo perde para os walls (SAML/desc vazia —
# o problema da máquina vem primeiro) mas vence js_only/cookie_wall (que
# não têm produtor hoje): é o motivo mais acionável da família
# "vaga avaliável, ação é com o dono/universidade".
_MOTIVO_PRIORITY = (
    MOTIVO_ID_COLLISION,
    MOTIVO_SAML_WALL,
    MOTIVO_EMPTY_DESC,
    MOTIVO_EXTERNAL_AGREEMENT_GATE,
    MOTIVO_JS_ONLY,
    MOTIVO_COOKIE_WALL,
)

MANUAL_CHECK_MD_NAME = "MANUAL-CHECK.md"

_LIVENESS_DEAD = "dead"
_LIVENESS_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Motivo por vaga (puro)
# ---------------------------------------------------------------------------


def _unknown_detail(job: dict) -> str:
    """Detalhe do veredito F94 persistido no registro (``liveness_detail``)."""
    return str(job.get("liveness_detail") or "").strip()


def motivo_of(job: dict) -> str | None:
    """Motivo da fila manual-check p/ a vaga (pura; ``None`` = fora da fila).

    Ordem de prioridade (o mais acionável primeiro): ``id_collision`` >
    ``saml_wall`` > ``empty_desc`` > ``external_agreement_gate`` (F105) >
    ``js_only``/``cookie_wall`` > detalhe cru de liveness unknown >
    ``borderline``. Vagas com ``liveness_status: dead`` NÃO entram (a
    máquina julgou: morta — a fila é para o que a máquina NÃO consegue
    julgar).
    """
    if not isinstance(job, dict):
        return None
    status = str(job.get("liveness_status") or "").strip().lower()
    if status == _LIVENESS_DEAD:
        return None
    candidates: list[str] = []
    if str(job.get("id_collision") or "").strip():
        candidates.append(MOTIVO_ID_COLLISION)
    na = str(job.get("not_assessable") or "").strip()
    if na:
        candidates.append(F87_MOTIVO_MAP.get(na, na))
    if str(job.get("external_agreement_gate") or "").strip():
        candidates.append(MOTIVO_EXTERNAL_AGREEMENT_GATE)
    if status == _LIVENESS_UNKNOWN or job.get("manual_check_required"):
        detail = _unknown_detail(job)
        if "saml" in detail.lower():
            candidates.append(MOTIVO_SAML_WALL)
        elif detail:
            candidates.append(detail)
        else:
            candidates.append(_LIVENESS_UNKNOWN)
    if not candidates:
        return None
    for prio in _MOTIVO_PRIORITY:
        if prio in candidates:
            return prio
    # detalhe cru / desconhecido: primeiro da lista (ordem de inserção)
    return candidates[0]


# ---------------------------------------------------------------------------
# Link direto (o alvo final, não o redirect)
# ---------------------------------------------------------------------------

# Wrappers de redirect por query param com alvo absoluto (percent-encoded
# ou cru). Medido 21/10: ZERO ocorrências nos ~109k registros — o wrapper
# existe em feeds terceiros (rdr/jump) e o desembrulho é offline/puro.
_PARAM_REDIRECT_RE = re.compile(
    r"[?&](?:rdr|redirect|url|target|u)=(https?%3A%2F%2F[^&\s#]+|https?://[^&\s#]+)",
    re.IGNORECASE,
)

# Stub de redirect por REF (Lidl ``/rdr/jump-to-job/<ref>`` — F94): NÃO é
# desembrulhável offline (o alvo só existe atrás do HTTP); resolve com o
# ``final_url`` do passe de liveness.
try:  # irmão de diretório no runtime do refresh; isolado p/ uso standalone
    from url_liveness import REDIRECT_STUB_RE  # noqa: F401
except Exception:  # noqa: BLE001 — fallback com a MESMA regex (contrato F94)
    REDIRECT_STUB_RE = re.compile(r"/rdr/jump-to-job/(?:[^/?#]+)", re.IGNORECASE)

_SAML_FINAL_RE = re.compile(r"saml", re.IGNORECASE)

_UNWRAP_MAX_HOPS = 5


def _is_homepage_final(url: str) -> bool:
    try:
        path = urllib.parse.urlsplit(str(url or "")).path
    except ValueError:
        return False
    return path.strip() in ("", "/")


def _unwrap_param_redirect(url: str) -> str:
    """Desembrulha cadeias ``?rdr=<alvo>`` (puro; guard de ciclo, ≤5 hops)."""
    seen = {url}
    current = url
    for _ in range(_UNWRAP_MAX_HOPS):
        match = _PARAM_REDIRECT_RE.search(current)
        if not match:
            break
        target = urllib.parse.unquote(match.group(1))
        if not target.lower().startswith(("http://", "https://")):
            break
        if target in seen:
            break  # ciclo: fica na URL corrente, nunca inventa alvo
        seen.add(target)
        current = target
    return current


def resolve_direct_link(url: str, final_url: str | None = None) -> str:
    """Link DIRETO da vaga (puro).

    Ordem: (1) wrapper rdr/jump em query param é desembrulhado offline;
    (2) com ``final_url`` do liveness (vaga viva, alvo ≠ original), o
    alvo vence — resolve stubs rdr/jump-to-job que o HTTP seguiu;
    (3) final que é wall SAML ou homepage NUNCA vira link direto (o
    final da henkel é a página do IdP; a vaga segue sendo a URL csod);
    (4) sem nada disso, a própria URL do registro JÁ É o link direto
    (careersite/csod/absolventa — medido: 0 wrappers nos 109k).
    """
    url = str(url or "").strip()
    if not url:
        return ""
    unwrapped = _unwrap_param_redirect(url)
    if unwrapped != url:
        return unwrapped
    final = str(final_url or "").strip()
    if (
        final
        and final != url
        and final.lower().startswith(("http://", "https://"))
        and not _SAML_FINAL_RE.search(urllib.parse.urlsplit(final).path or "")
        and not _is_homepage_final(final)
    ):
        return final
    return url


# ---------------------------------------------------------------------------
# Preferência por portal oficial (F105) — agregador geobloqueante × portal
# oficial quando AMBOS existem no mesmo ranking
# ---------------------------------------------------------------------------

# Medido 23/10 (registro, abertura do Brasil): o AGREGADOR absolventa.de
# bloqueia geograficamente; o portal OFICIAL Bertelsmann/Arvato
# (jobsearch.createyourowncareer.com) abre normalmente. Doutrina F96: o
# link direto aponta para o ALVO aplicável ao dono (o que abre), não para
# o redirect/agregador. Listas extensíveis POR MEDIDA (nova medição no
# registro -> nova entrada, nunca chute).
GEOBLOCKED_AGGREGATOR_HOSTS = ("absolventa.de",)
OFFICIAL_PORTAL_HOSTS = ("createyourowncareer.com",)

# Metadata de tenant medida (registro 23/10): Bertelsmann/Arvato publica
# as vagas em portal próprio (createyourowncareer.com — multi-empregador:
# ARVATO/Arvato_Systems/RTL/BFS/Bertelsmann_Corporate) e a CANDIDATURA
# roda no SmartRecruiters corporativo (formulário abre do Brasil). O
# portal preference abaixo usa os hosts; este mapa documenta a rota
# completa para o drift-check da doc de providers.
# F108 (23/10/2026) — Wilhelm Fricke (13461829 absolventa): site da empresa
# com certificado EXPIRADO (fora do ar) — canal vivo é absolventa.
# Doutrina F96: link direto do MANUAL-CHECK aponta pro canal VIVO.
TENANT_PORTAL_METADATA = {
    "bertelsmann": {
        "aggregator": "www.absolventa.de (geoblock medido do Brasil)",
        "official_portal": "jobsearch.createyourowncareer.com",
        "apply": "jobs.smartrecruiters.com/Bertelsmann-Jobs/",
    },
    "fricke": {
        "site_morto": "wilhelm-fricke.com (cert expirado 23/10/2026 — fora do ar)",
        "canal_vivo": "absolventa.de (listing 13461829 ATIVO medido)",
        "note": "site oficial morto -> link direto aponta pro canal vivo absolventa (F96)",
    },
}

# O par AGREGADOR × OFICIAL exige prova de MESMA vaga: os labels de
# empresa divergem por construção (o agregador traz "Apply now!", o
# oficial traz o label do tenant — par Arvato medido), então empresa NÃO
# é chave aqui. Prova usada: título normalizado IGUAL + mesmo país +
# overlap de descrição (Jaccard de tokens) — o agregador copia o texto do
# empregador. Calibração (23/10, eligible de produção): o único par misto
# do funil tem Jaccard 0.744; 0.5 é a folga conservadora. Descrição
# vazia/degenerada em qualquer lado => SEM swap (fail-closed, honesto).
_PORTAL_TWIN_MIN_JACCARD = 0.5


def _url_host(url: str) -> str:
    """Host da URL (sem www., casefold); '' quando não parseável."""
    try:
        netloc = urllib.parse.urlsplit(str(url or "")).netloc
    except ValueError:
        return ""
    return netloc.removeprefix("www.").casefold()


def _host_matches(url: str, hosts: tuple[str, ...]) -> bool:
    host = _url_host(url)
    return bool(host) and any(
        host == h or host.endswith("." + h) for h in hosts
    )


def _twin_title_key(title: str) -> str:
    """Chave de título p/ o par agregador×oficial (F105, LOCAL).

    Aproximação deliberada e documentada do ``dedup.normalize_title``
    (este módulo se mantém standalone — o refresh tem src/ importável,
    o teste também): acentos fora, casefold, tokens alfanuméricos em
    ordem. O par real (Arvato) tem título idêntico; a prova de MESMA
    vaga fica por conta do overlap de descrição (sinal forte).
    """
    norm = unicodedata.normalize("NFKD", str(title or "")).encode(
        "ascii", "ignore").decode()
    return " ".join(sorted(re.findall(r"[a-z0-9]+", norm.casefold())))


def _desc_tokens(text: str) -> set[str]:
    """Tokens de palavra (≥3 chars, ascii-folded) da descrição."""
    norm = unicodedata.normalize("NFKD", str(text or "")).encode(
        "ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z]{3,}", norm.casefold())}


def _desc_jaccard(a: str, b: str) -> float | None:
    """Jaccard dos tokens das duas descrições; None quando degenerado."""
    ta, tb = _desc_tokens(a), _desc_tokens(b)
    if not ta or not tb:
        return None
    return len(ta & tb) / len(ta | tb)


def official_portal_twin_url(job: dict, ranking: list) -> str:
    """URL do portal oficial do gêmeo agregador (pura; ``''`` = sem swap).

    Dispara SÓ quando a URL da vaga está num agregador geobloqueante E
    existe, no MESMO ranking, um registro no portal oficial com o MESMO
    título normalizado, MESMO país e overlap de descrição >=
    ``_PORTAL_TWIN_MIN_JACCARD``. Sem prova de mesma vaga => sem swap
    (o link direto fica na URL do registro — nunca inventa alvo).
    """
    url = str(job.get("url") or "").strip() if isinstance(job, dict) else ""
    if not url or not _host_matches(url, GEOBLOCKED_AGGREGATOR_HOSTS):
        return ""
    title = _twin_title_key(job.get("title") or "")
    country = str(job.get("country_iso") or "").strip().casefold()
    if not title or not country:
        return ""
    desc = str(job.get("description") or "")
    best: tuple[float, str] | None = None
    for other in ranking:
        if not isinstance(other, dict) or other is job:
            continue
        other_url = str(other.get("url") or "").strip()
        if not _host_matches(other_url, OFFICIAL_PORTAL_HOSTS):
            continue
        if _twin_title_key(other.get("title") or "") != title:
            continue
        if str(other.get("country_iso") or "").strip().casefold() != country:
            continue
        overlap = _desc_jaccard(desc, str(other.get("description") or ""))
        if overlap is None or overlap < _PORTAL_TWIN_MIN_JACCARD:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, other_url)
    return best[1] if best else ""


# ---------------------------------------------------------------------------
# F119 — Dead-mirror rescue: BA 410 com original vivo
# Linha informativa display-only no MANUAL-CHECK (NUNCA ressuscita)
# Reusa a MESMA lógica de gêmeos do F105 (_twin_title_key, _desc_jaccard,
# _PORTAL_TWIN_MIN_JACCARD) — sem máquina nova.
# ---------------------------------------------------------------------------

# Fonte do espelho BA (dataset:bundesagentur / direct:bundesagentur)
BA_MIRROR_SOURCES = ("sf_dataset:bundesagentur", "direct:bundesagentur")


def _is_ba_mirror(job: dict) -> bool:
    """Verifica se a vaga é do espelho BA (dataset:bundesagentur ou direct:bundesagentur)."""
    source = str(job.get("source") or "")
    return any(source.startswith(s) for s in BA_MIRROR_SOURCES)


def ba_mirror_twin_url(job: dict, ranking: list) -> str:
    """URL do portal oficial VIVO do gêmeo do espelho BA morto (pura; ``''`` = sem twin).

    Dispara SÓ quando:
    - A vaga tem ``liveness_status == 'dead'`` E é do espelho BA;
    - Existe, no MESMO ranking, um registro VIVO (``liveness_status == 'alive'``)
      com o MESMO título normalizado, MESMO país e overlap de descrição >=
      ``_PORTAL_TWIN_MIN_JACCARD`` (0.5, mesma calibração F105).

    Sem prova de mesma vaga => ``''`` (nunca inventa alvo).
    A vaga-fonte PERMANECE dead; o link é SÓ informativo no MANUAL-CHECK.
    """
    if not isinstance(job, dict):
        return ""
    if str(job.get("liveness_status") or "").strip().lower() != "dead":
        return ""
    if not _is_ba_mirror(job):
        return ""
    title = _twin_title_key(job.get("title") or "")
    country = str(job.get("country_iso") or "").strip().casefold()
    if not title or not country:
        return ""
    desc = str(job.get("description") or "")
    best: tuple[float, str] | None = None
    for other in ranking:
        if not isinstance(other, dict) or other is job:
            continue
        if str(other.get("liveness_status") or "").strip().lower() != "alive":
            continue
        if _twin_title_key(other.get("title") or "") != title:
            continue
        if str(other.get("country_iso") or "").strip().casefold() != country:
            continue
        overlap = _desc_jaccard(desc, str(other.get("description") or ""))
        if overlap is None or overlap < _PORTAL_TWIN_MIN_JACCARD:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, str(other.get("url") or "").strip())
    return best[1] if best else ""


# ---------------------------------------------------------------------------
# id_collision (ITEM 7-typo) — validação de ID plausível por provedor
# ---------------------------------------------------------------------------

# Shapes MEDIDAS no caderno F70 (23.805 keys, 22/10): recruitee é
# numérico — 7 dígitos dominante (237) e 6 dígitos (9); o doc fixa
# "recruitee IDs são 7 dígitos". Provedor sem shape medida => sem
# checagem (``None``) — nunca bloqueia comparação por ignorância.
_PROVIDER_ID_PATTERNS = {
    "sf_dataset:recruitee": re.compile(r"\d{6,7}\Z"),
}


def _norm_company(name: str) -> str:
    """Empresa normalizada p/ comparação: sufixo parêntese fora + casefold.

    ``Allegion (careers SimonsVoss English)`` == ``Allegion`` (variantes
    de tenant do MESMO empregador — medido no caderno F70; flagar seria
    falso positivo).
    """
    return re.sub(r"\s*\([^)]*\)", "", str(name or "")).strip().casefold()


def _parse_job_id(job_id: str) -> tuple[str, str, str] | None:
    """``<empresa>|<provedor>:<ats_id>`` => (empresa, provedor, ats_id).

    O provedor é tudo ANTES do último ``:`` (``sf_dataset:recruitee``,
    ``cornerstone:henkel``) — IDs só colidem DENTRO do mesmo espaço de
    provedor. Malformado => ``None``.
    """
    jid = str(job_id or "").strip()
    if "|" not in jid:
        return None
    company, _, source = jid.partition("|")
    if ":" not in source:
        return None
    provider, _, ats_id = source.rpartition(":")
    if not provider or not ats_id:
        return None
    return company, provider, ats_id


def provider_id_plausible(provider: str, ats_id: str) -> bool | None:
    """ID numérico plausível para o provedor (pura).

    ``True``/``False`` quando o provedor tem shape medida; ``None`` quando
    não há shape (sem checagem — a ausência de evidência nunca flaga).
    """
    pattern = _PROVIDER_ID_PATTERNS.get(str(provider or "").strip())
    if pattern is None:
        return None
    return bool(pattern.fullmatch(str(ats_id or "").strip()))


def load_id_history(db_path) -> dict[tuple[str, str], dict[str, str]]:
    """Mapa ``(provedor, ats_id)`` -> {empresa_normalizada: empresa_original}.

    Fonte: caderno F70 (``dataset_seen.db`` — todo ``job_id`` histórico).
    Best-effort: DB ausente/corrompido/vazio => ``{}`` — sem histórico a
    comparação de colisão não acende (padrão F70: caderno degradado
    NUNCA derruba o run). Só leitura (``mode=ro``).
    """
    path = str(db_path or "").strip()
    if not path:
        return {}
    try:
        con = sqlite3.connect(f"file:{urllib.parse.quote(path)}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT DISTINCT job_id FROM dataset_seen"
            ).fetchall()
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — best-effort TOTAL (F70)
        return {}
    history: dict[tuple[str, str], dict[str, str]] = {}
    for (raw,) in rows:
        parsed = _parse_job_id(str(raw or ""))
        if parsed is None:
            continue
        company, provider, ats_id = parsed
        normalized = _norm_company(company)
        if not normalized:
            continue
        # valor = empresa ORIGINAL (display do flag legível — "Simvia");
        # chave = normalizada (comparação de identidade)
        history.setdefault((provider, ats_id), {}).setdefault(
            normalized, company.strip())
    return history


def detect_id_collisions(ranking: list, history: dict | None = None) -> dict:
    """Flag ``id_collision`` nas vagas do ranking (in place) + contadores.

    Acende quando o MESMO ``(provedor, ats_id)`` aparece com ≥2 empresas
    DISTINTAS (normalizadas) e PEL MENOS uma está ausente do ranking
    atual (morta/churn — o caso Consultport×Simvia do doc) enquanto outra
    está presente (a flagada). NUNCA remove, NUNCA funde: a flag é
    sinal para revisão manual na fila. Par vivo×vivo com mesmo ID (mesmo
    grupo corporativo — RELX×LexisNexis medido) NÃO acende.

    Devolve ``{"checked", "implausible", "flagged", "collisions"}``.
    """
    history = history or {}
    present_comps: dict[tuple[str, str], set[str]] = {}
    jobs_by_key: dict[tuple[str, str], list[dict]] = {}
    checked = implausible = 0
    for job in ranking:
        if not isinstance(job, dict):
            continue
        parsed = _parse_job_id(str(job.get("id") or ""))
        if parsed is None:
            continue
        checked += 1
        company, provider, ats_id = parsed
        if provider_id_plausible(provider, ats_id) is False:
            implausible += 1  # ID fora do shape do provedor: fora da comparação
            continue
        key = (provider, ats_id)
        present_comps.setdefault(key, set()).add(_norm_company(str(company)))
        jobs_by_key.setdefault(key, []).append(job)
    ranking_comps = {
        _norm_company(str(j.get("company") or ""))
        for j in ranking
        if isinstance(j, dict)
    }
    flagged = 0
    collisions: list[dict] = []
    for key, comps in present_comps.items():
        hist: dict[str, str] = history.get(key) or {}
        hist_comps = set(hist)
        all_comps = comps | hist_comps
        absent = {c for c in all_comps if c and c not in ranking_comps}
        if len(all_comps) < 2 or not absent:
            continue
        # display legível: original do caderno/quando conhecida, norm senão
        display: dict[str, str] = {}
        for job in jobs_by_key.get(key, []):
            raw = str(job.get("company") or "").strip()
            display[_norm_company(raw)] = raw
        for norm, original in hist.items():
            display.setdefault(norm, original)
        others = sorted(display.get(c, c) for c in absent)
        provider, ats_id = key
        for job in jobs_by_key.get(key, []):
            job["id_collision"] = "; ".join(others)
            flagged += 1
            collisions.append({
                "job_id": str(job.get("id") or ""),
                "company": str(job.get("company") or ""),
                "provider_id": f"{provider}:{ats_id}",
                "collides_with": others,
            })
    return {
        "checked": checked,
        "implausible": implausible,
        "flagged": flagged,
        "collisions": collisions,
    }


# ---------------------------------------------------------------------------
# external_agreement_gate (F105) — acordo padrão assinado pela universidade
# ---------------------------------------------------------------------------

# Família medida no corpus INTEIRO (jobs.json ~109k + eligible, 23/10): os
# 2 padrões apanham EXATAMENTE a família do gate externo — J&J Belgium ×2
# ("External agreements cannot be accepted", verbatim R-106104/R-102271) e
# Danone icims ×5 ("3-party internship agreement signed by your
# university"). A família de MATRÍCULA local (Continental "Studium an
# einer deutschen Hochschule", Avery "Currently enrolled at a Dutch
# university") NÃO acende — é outra classe (exclusão F99 / F106); menções
# genéricas de acordo (Deutsche Börse "can provide an internship
# agreement", boilerplate ×90) também não — sem "external agreements"
# negado nem "signed by your university", não há gate.
_EXTERNAL_AGREEMENT_RES = (
    # J&J Belgium: o empregador SÓ aceita o acordo padrão DELE assinado
    # pela universidade — acordos externos não são aceitos.
    re.compile(
        r"external\s+agreements?\s+(?:cannot|can(?:no)?t|can't)\s+be\s+accepted",
        re.IGNORECASE,
    ),
    # Família do acordo assinado pela universidade (Danone): "it is
    # mandatory to provide a 3-party internship agreement signed by your
    # university".
    re.compile(
        r"agreement[^.\n]{0,80}?signed\s+by\s+(?:your|the)\s+(?:university|school)",
        re.IGNORECASE,
    ),
)


def detect_external_agreement_gates(ranking: list) -> dict:
    """Flag ``external_agreement_gate`` nas vagas do ranking (in place).

    O gate é EXTERNO à candidatura: a vaga SEGUE elegível (score/ordem
    intactos — doutrina F96/F87) e entra na fila manual-check com o motivo
    claro, porque a resolução (universidade assinar o acordo padrão do
    empregador) é ação do dono, não da máquina. NUNCA remove, NUNCA
    exclui. O valor do flag é o TRECHO-ÂNCORA (evidência legível na
    fila). Devolve ``{"checked", "flagged", "gates"}``.
    """
    flagged = 0
    checked = 0
    gates: list[dict] = []
    for job in ranking:
        if not isinstance(job, dict):
            continue
        desc = str(job.get("description") or "")
        if not desc:
            continue
        checked += 1
        anchor = None
        for pattern in _EXTERNAL_AGREEMENT_RES:
            match = pattern.search(desc)
            if match:
                anchor = match.group(0)
                break
        if anchor is None:
            continue
        job["external_agreement_gate"] = anchor
        flagged += 1
        gates.append({
            "job_id": str(job.get("id") or ""),
            "company": str(job.get("company") or ""),
            "anchor": anchor,
        })
    return {"checked": checked, "flagged": flagged, "gates": gates}


# ---------------------------------------------------------------------------
# MANUAL-CHECK.md — geração e carry-forward da data de sighting
# ---------------------------------------------------------------------------

_PREV_ROW_RE = re.compile(
    r"<!--\s*id:(?P<id>[^>]+?)\s*-->.*?visto:\s*(?P<date>\d{4}-\d{2}-\d{2})",
    re.DOTALL,
)


def _read_previous_dates(path: Path) -> dict[str, str]:
    """``id -> sighting mais antigo`` do MANUAL-CHECK.md anterior (best-effort).

    O arquivo é reescrito TODO run; a DATA DE SIGHTING original (ITEM 11)
    sobrevive pelo carry-forward do próprio arquivo — um item que anda há
    3 dias na fila mostra 3 dias, não "hoje". Corrompido/ausente => ``{}``.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — best-effort
        return {}
    dates: dict[str, str] = {}
    for match in _PREV_ROW_RE.finditer(text):
        jid = match.group("id").strip()
        date = match.group("date")
        if not jid or not date:
            continue
        prev = dates.get(jid)
        if prev is None or date < prev:
            dates[jid] = date
    return dates


def build_manual_check_rows(ranking: list) -> list[dict]:
    """Linhas da fila (puras): uma por item não-avaliável/borderline/colisão.

    Ordenado por empresa (casefold) — o dono varre em ordem estável entre
    runs. ``url`` já é o link DIRETO (alvo final via ``liveness_final_url``
    quando o liveness resolveu redirect); F105: quando a URL do registro é
    de agregador geobloqueante e o gêmeo no portal oficial existe no
    MESMO ranking, o link vira o do portal (``portal_oficial=True``).
    F119: linhas informativas para vagas dead do espelho BA com gêmeo vivo
    (``f119_mirror_dead=True``, ``twin_url`` preenchido) — display-only,
    NÃO entram na fila por motivo, liveness_status PERMANECE dead.
    """
    rows: list[dict] = []
    # 1) Fila regular (motivo não-avaliável/borderline/colisão/gate)
    for job in ranking:
        if not isinstance(job, dict):
            continue
        motivo = motivo_of(job)
        if not motivo:
            continue
        original = str(job.get("url") or "")
        direct = resolve_direct_link(
            original, job.get("liveness_final_url"))
        portal_oficial = False
        twin = official_portal_twin_url(job, ranking)
        if twin and twin != direct:
            direct = twin
            portal_oficial = True
        rows.append({
            "id": str(job.get("id") or ""),
            "company": str(job.get("company") or "?"),
            "title": str(job.get("title") or "?"),
            "motivo": motivo,
            # F105 — evidência do gate (trecho-âncora) na linha do dono
            "gate_anchor": str(job.get("external_agreement_gate") or "").strip(),
            "url": direct,
            "resolved": bool(direct) and direct != original.strip(),
            "portal_oficial": portal_oficial,
            "date": str(job.get("liveness_checked_at") or "")[:10] or None,
        })
    # 2) F119 — linhas informativas: dead BA mirror com gêmeo vivo
    for job in ranking:
        if not isinstance(job, dict):
            continue
        twin = ba_mirror_twin_url(job, ranking)
        if not twin:
            continue
        rows.append({
            "id": str(job.get("id") or ""),
            "company": str(job.get("company") or "?"),
            "title": str(job.get("title") or "?"),
            "motivo": None,  # NÃO é item da fila — linha informativa
            "gate_anchor": "",
            "url": twin,
            "resolved": False,
            "portal_oficial": False,
            "date": str(job.get("liveness_checked_at") or "")[:10] or None,
            "f119_mirror_dead": True,
            "twin_url": twin,
        })
    rows.sort(key=lambda r: (r["company"].casefold(), r["title"].casefold()))
    return rows


def write_manual_check_md(path, rows: list[dict], generated_at: str) -> Path:
    """Escreve o MANUAL-CHECK.md (fila PARALELA — nada sai do ranking)."""
    path = Path(path)
    prev_dates = _read_previous_dates(path)
    # Separar linhas da fila regular vs linhas informativas F119
    queue_rows = [r for r in rows if not r.get("f119_mirror_dead")]
    f119_rows = [r for r in rows if r.get("f119_mirror_dead")]
    lines = [
        f"# Manual check — {len(queue_rows)} item(ns) na fila",
        "",
        f"_Gerado em {generated_at} UTC (run diário, F96). Fila PARALELA: "
        "nenhuma vaga sai do ranking/Top-5 (doutrina F87)._",
        "",
    ]
    if not queue_rows and not f119_rows:
        lines.append("_Fila vazia — nenhum item não-avaliável/borderline/colisão._")
    # Linhas da fila regular
    for row in queue_rows:
        jid = row["id"]
        date = row.get("date") or None
        prev = prev_dates.get(jid)
        if prev and (date is None or prev < date):
            date = prev  # sighting original sobrevive à reescrita do run
        if not date:
            date = str(generated_at)[:10]
        motivo_txt = str(row["motivo"])
        anchor = str(row.get("gate_anchor") or "").strip()
        if anchor:
            motivo_txt += f' — “{anchor}”'
        suffix = ""
        if row.get("portal_oficial"):
            suffix = " _(link direto: portal oficial — agregador geobloqueado)_"
        elif row.get("resolved"):
            suffix = " _(link direto: alvo final)_"
        lines.append(
            f"- **{row['company']}** — {row['title']} — "
            f"[abrir]({row['url']}) — motivo: {motivo_txt} — "
            f"visto: {date} <!-- id:{jid} -->{suffix}"
        )
    # F119 — linhas informativas: dead BA mirror com gêmeo vivo
    if f119_rows:
        lines.append("")
        lines.append("## ⚠ Espelho BA morto — original vivo (F119, display-only)")
        lines.append("")
        lines.append("_Estas vagas têm ``liveness_status=dead`` no espelho BA (410), mas o "
                       "portal oficial está VIVO. O status **não muda** — a linha é só informativa._")
        lines.append("")
        for row in f119_rows:
            jid = row["id"]
            date = row.get("date") or None
            prev = prev_dates.get(jid)
            if prev and (date is None or prev < date):
                date = prev
            if not date:
                date = str(generated_at)[:10]
            twin_url = row.get("twin_url") or row.get("url")
            lines.append(
                f"- **{row['company']}** — {row['title']} — "
                f"⚠ mirror morto — original vivo: [abrir]({twin_url}) — "
                f"visto: {date} <!-- id:{jid} -->"
            )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orquestrador — chamado pelo refresh diário (junto ao digest)
# ---------------------------------------------------------------------------


def generate_manual_check(
    data_dir,
    generated_at: str | None = None,
    seen_db_path=None,
) -> dict:
    """Gera o MANUAL-CHECK.md do run (LOCAL, zero rede, best-effort caller).

    Passos: (1) carrega o ranking FINAL persistido
    (``data/eligible_jobs.json`` — todos os annotators F87/F94 já
    rodaram); (2) ``detect_id_collisions`` contra o caderno F70 — e
    PERSISTE o flag no registro (padrão F87/F94, campo JSON-only, o CSV
    nem muda) quando acende; (2b, F105) ``detect_external_agreement_gates``
    — mesmo padrão de flag persistida, motivo ``external_agreement_gate``
    (gate externo à candidatura, a vaga segue elegível); (3) escreve o
    arquivo com uma linha por item (carry-forward da data de sighting do
    arquivo anterior).

    ``generated_at`` ISO UTC (default: agora). ``seen_db_path`` default
    ``<data_dir>/dataset_seen.db``. Devolve contadores para o log::

        {"ranking", "rows", "path", "collisions": {...},
         "gates": {...}, "persist_error"}
    """
    data_dir = Path(data_dir)
    now = str(generated_at or datetime.datetime.now(
        datetime.timezone.utc).isoformat())
    eligible_path = data_dir / "eligible_jobs.json"
    ranking: list = []
    try:
        loaded = json.loads(eligible_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            ranking = loaded
    except Exception:  # noqa: BLE001 — sem ranking legível: fila vazia honesta
        ranking = []
    if seen_db_path is None:
        seen_db_path = data_dir / "dataset_seen.db"
    collisions = detect_id_collisions(ranking, load_id_history(seen_db_path))
    gates = detect_external_agreement_gates(ranking)
    persist_error = None
    if collisions["flagged"] or gates["flagged"]:
        try:
            from internship_finder.cli import _write_json_atomic
            _write_json_atomic(ranking, eligible_path)
        except Exception as exc:  # noqa: BLE001 — persistência best-effort
            persist_error = f"{type(exc).__name__}: {exc}"
    rows = build_manual_check_rows(ranking)
    # F119 stats
    f119_rows = [r for r in rows if r.get("f119_mirror_dead")]
    f119_count = len(f119_rows)
    f119_pairs = [
        {"dead_id": r["id"], "dead_company": r["company"], "dead_title": r["title"],
         "alive_url": r.get("twin_url") or r.get("url")}
        for r in f119_rows
    ]
    out_path = write_manual_check_md(
        data_dir / MANUAL_CHECK_MD_NAME, rows, now)
    return {
        "ranking": len(ranking),
        "rows": len([r for r in rows if not r.get("f119_mirror_dead")]),
        "path": str(out_path),
        "collisions": collisions,
        "gates": gates,
        "persist_error": persist_error,
        # F119
        "f119_mirror_dead": {
            "count": f119_count,
            "pairs": f119_pairs,
        },
    }
