#!/usr/bin/env python3
"""F96 — Fila manual-check com link DIRETO + id_collision (ITENS 11, 8, 7-typo).

O dono não quer mais "ficar procurando": itens não-avaliáveis (F87) e
borderline ficam espalhados no registro. Este módulo gera o
``data/MANUAL-CHECK.md`` no run diário (estágio do refresh, junto ao
digest) com UMA linha por item: empresa, cargo, **link DIRETO** (o alvo
final, não o redirect — resolve cadeias rdr/jump), motivo
(saml_wall | empty_desc | js_only | cookie_wall | borderline) e a data
do sighting.

População da fila (spec F96):

- ``not_assessable`` (F87 — campo anotado pelo refresh; a cura da
  hidratação apaga o campo e a linha da fila some no run seguinte);
- ``liveness_status: unknown`` (F94 — checou e não deu para determinar;
  wall SAML ganha ``manual_check_required``);
- ``id_collision`` (F96/ITEM 7-typo — colisão de ID entre empresas
  vivas/mortas: Consultport recruitee "2100111" colidindo com a Simvia
  morta; flag p/ revisão manual, NUNCA remove, NUNCA funde).

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

# F87 (not_assessable) -> vocabulário da spec F96.
F87_MOTIVO_MAP = {
    "desc_vazia": MOTIVO_EMPTY_DESC,
    "login_wall": MOTIVO_SAML_WALL,
    "desc_curta": MOTIVO_BORDERLINE,
}

# Prioridade quando a vaga tem MAIS DE UM sinal (o mais acionável para o
# dono primeiro). ``desc_curta`` (borderline) perde para qualquer detalhe
# de liveness unknown: 584 chars de SAML wall são, antes de tudo, um wall.
_MOTIVO_PRIORITY = (
    MOTIVO_ID_COLLISION,
    MOTIVO_SAML_WALL,
    MOTIVO_EMPTY_DESC,
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
    ``saml_wall`` > ``empty_desc`` > ``js_only``/``cookie_wall`` >
    detalhe cru de liveness unknown > ``borderline``. Vagas com
    ``liveness_status: dead`` NÃO entram (a máquina julgou: morta — a
    fila é para o que a máquina NÃO consegue julgar).
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
    quando o liveness resolveu redirect).
    """
    rows: list[dict] = []
    for job in ranking:
        if not isinstance(job, dict):
            continue
        motivo = motivo_of(job)
        if not motivo:
            continue
        original = str(job.get("url") or "")
        direct = resolve_direct_link(
            original, job.get("liveness_final_url"))
        rows.append({
            "id": str(job.get("id") or ""),
            "company": str(job.get("company") or "?"),
            "title": str(job.get("title") or "?"),
            "motivo": motivo,
            "url": direct,
            "resolved": bool(direct) and direct != original.strip(),
            "date": str(job.get("liveness_checked_at") or "")[:10] or None,
        })
    rows.sort(key=lambda r: (r["company"].casefold(), r["title"].casefold()))
    return rows


def write_manual_check_md(path, rows: list[dict], generated_at: str) -> Path:
    """Escreve o MANUAL-CHECK.md (fila PARALELA — nada sai do ranking)."""
    path = Path(path)
    prev_dates = _read_previous_dates(path)
    lines = [
        f"# Manual check — {len(rows)} item(ns)",
        "",
        f"_Gerado em {generated_at} UTC (run diário, F96). Fila PARALELA: "
        "nenhuma vaga sai do ranking/Top-5 (doutrina F87)._",
        "",
    ]
    if not rows:
        lines.append("_Fila vazia — nenhum item não-avaliável/borderline/colisão._")
    for row in rows:
        jid = row["id"]
        date = row.get("date") or None
        prev = prev_dates.get(jid)
        if prev and (date is None or prev < date):
            date = prev  # sighting original sobrevive à reescrita do run
        if not date:
            date = str(generated_at)[:10]
        suffix = ""
        if row.get("resolved"):
            suffix = " _(link direto: alvo final)_"
        lines.append(
            f"- **{row['company']}** — {row['title']} — "
            f"[abrir]({row['url']}) — motivo: {row['motivo']} — "
            f"visto: {date} <!-- id:{jid} -->{suffix}"
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
    nem muda) quando acende; (3) escreve o arquivo com uma linha por
    item (carry-forward da data de sighting do arquivo anterior).

    ``generated_at`` ISO UTC (default: agora). ``seen_db_path`` default
    ``<data_dir>/dataset_seen.db``. Devolve contadores para o log::

        {"ranking", "rows", "path", "collisions": {...}}
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
    persist_error = None
    if collisions["flagged"]:
        try:
            from internship_finder.cli import _write_json_atomic
            _write_json_atomic(ranking, eligible_path)
        except Exception as exc:  # noqa: BLE001 — persistência best-effort
            persist_error = f"{type(exc).__name__}: {exc}"
    rows = build_manual_check_rows(ranking)
    out_path = write_manual_check_md(
        data_dir / MANUAL_CHECK_MD_NAME, rows, now)
    return {
        "ranking": len(ranking),
        "rows": len(rows),
        "path": str(out_path),
        "collisions": collisions,
        "persist_error": persist_error,
    }
