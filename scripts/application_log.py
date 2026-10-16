#!/usr/bin/env python3
"""F41 — Event log de candidaturas (append-only) + ingest offline + view.

GROUND TRUTH do loop de candidaturas do dono: os DESFECHOS (applied,
screening, interview, offer, rejected, withdrawn, note) em um arquivo
JSONL append-only — ``data/personal/application_events.jsonl``.

``data/`` é gitignored: o log vive em ``data/personal/`` (pessoal, NUNCA
versionado/publicado), exatamente como o ``jobs_personal.db`` da Fase 8.

--------------------------------------------------------------------------
SCHEMA DO LOG (F41 — fixo; uma linha JSON por evento)
--------------------------------------------------------------------------
    {"message_id": str, "ts": str, "job_id": str,
     "company": str, "event_type": str, "source": str}

Campos:
  - message_id : chave de IDEMPOTÊNCIA (id da mensagem de origem; ``cli:...``
                 para eventos criados pela CLI do tracker). Replay do MESMO
                 dump = no-op (nenhuma linha duplicada).
  - ts         : timestamp ISO-8601 do evento (``YYYY-MM-DDTHH:MM:SSZ``;
                 data pura é normalizada para ``T00:00:00Z``).
  - job_id     : id canônico da vaga (``<company>|<source>:<external_id>``),
                 a MESMA chave do ranking/coleta (nunca title+company).
  - company    : empresa derivada do eligible quando o job_id casa.
  - event_type : ∈ {applied, screening, interview, offer, rejected,
                 withdrawn, note}.
  - source     : origem do evento (``telegram`` no dump; ``cli`` na CLI).

APPEND-ONLY: NUNCA reescreve linhas. Escrita via append + flush + fsync
(cada linha é um evento; sem reescrita do arquivo existente). Duplo-clique,
handler fora de ordem ou replay não corrompem o log.

--------------------------------------------------------------------------
SCHEMA DO DUMP DE ENTRADA (ingest offline — manual, flag-gated)
--------------------------------------------------------------------------
    {
      "dump_version": 1,
      "generated_at": "2026-10-15T23:00:00Z",   # opcional
      "messages": [
        {"message_id": "tg:501",
         "date": "2026-10-15T12:34:56Z",
         "job_id": "BMW AG|successfactors:jobs:111",  # opcional
         "company": "BMW AG",                         # opcional
         "text": "apliquei, cv enviado pelo portal",  # mapeia event_type
         "event_type": "applied",                     # opcional (vence texto)
         "source": "telegram"}                        # opcional (default)
      ]
    }

Resolução do ``job_id`` (nesta ordem): (1) um id canônico CONHECIDO
presente no ``text``; (2) o campo ``job_id`` da mensagem; (3) a empresa
citada no ``text`` casando com exatamente um job do eligible. Empresa é
derivada do eligible quando o job casa.

DECISÃO job_id desconhecido (documentada):
  - job_id INFORMADO mas ausente do eligible → evento ACEITO (unmatched;
    a empresa vem do campo ``company`` da mensagem, senão vazio). O log é
    a verdade pessoal e o snapshot do eligible muda a cada dia.
  - mensagem SEM nenhum job_id resolvível → SKIPADA (não vira evento),
    contada em ``skipped`` no sumário do ingest. Um desfecho sem vaga não
    serve ao benchmark e poluiria o log.

ZERO REDE: o ingest só lê um arquivo local. Não há listener/bot em tempo
real nesta fase (fora de escopo).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_LOG = Path("data/personal/application_events.jsonl")

# Tipos de evento do log (F41).
EVENT_TYPES = (
    "applied", "screening", "interview", "offer", "rejected", "withdrawn", "note",
)

# log event_type -> status do tracker (view derivada). ``note`` NÃO carrega
# status (não altera a view de status).
STATUS_BY_EVENT = {
    "applied": "applied",
    "screening": "review",       # triagem = em análise
    "interview": "interview",
    "offer": "offer",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
}

# event_type COM status (exclui ``note``).
STATUS_EVENT_TYPES = tuple(STATUS_BY_EVENT)

# Palavras-chave (DE/EN/PT) -> event_type. Ordem importa: desfechos
# específicos ANTES do genérico (applied por último entre os "fortes").
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("offer", ("offer", "oferta", "zusage", "angebot", "contratad", "contrataram")),
    ("rejected", ("rejected", "rejeit", "absage", "recus", "negaram",
                  "unfortunately", "não seguiremos", "nao seguiremos")),
    ("withdrawn", ("withdrawn", "desisti", "retirei", "cancelei", "withdraw")),
    ("interview", ("interview", "entrevista", "gespräch", "gespraech",
                   "vorstellungsgespräch", "vorstellungsgespraech")),
    ("screening", ("screening", "triagem", "recruiter", "primeiro contato",
                   "phone screen", "telefonscreening")),
    ("applied", ("applied", "apliquei", "candidatei", "beworben", "enviei cv",
                 "submeti", "candidatura enviada", "me candidatei")),
)


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_ts(value: object) -> str:
    """Normaliza ``ts`` para ISO-8601 ordenável lexicograficamente.

    Data pura (``YYYY-MM-DD``) vira ``YYYY-MM-DD`` + ``T00:00:00Z`` — assim a
    ordenação (ts, message_id) do rebuild é estável entre formatos.
    """
    if value is None:
        return utcnow_iso()
    s = str(value).strip()
    if not s:
        return utcnow_iso()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s}T00:00:00Z"
    return s


def _norm(value: object) -> str:
    return " ".join(str(value).lower().split())


# ------------------------------------------------------------------ leitura


def read_events(log_path: Path | str = DEFAULT_LOG) -> list[dict]:
    """Lê o log JSONL. Linha vazia/corrompida é ignorada (fail-soft)."""
    path = Path(log_path)
    if not path.exists():
        return []
    out: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def existing_message_ids(log_path: Path | str = DEFAULT_LOG) -> set[str]:
    """Conjunto de ``message_id`` já presentes no log (idempotência)."""
    ids: set[str] = set()
    for ev in read_events(log_path):
        mid = ev.get("message_id")
        if mid is not None:
            ids.add(str(mid))
    return ids


# ------------------------------------------------------------------- escrita


def append_events(log_path: Path | str, events: list[dict], *,
                  skip_existing: bool = True) -> dict:
    """Appenda eventos ao log — NUNCA reescreve linhas existentes.

    Idempotência por ``message_id``: eventos cujo id já está no log (ou
    repetido no MESMO lote) são descartados. Escrita atômica por
    append + flush + fsync (cada linha é um evento; o arquivo histórico é
    aberto em modo ``a`` e não é truncado nem reescrito).

    Retorna ``{"appended": int, "skipped_duplicates": int}``.
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_message_ids(path) if skip_existing else set()
    to_write: list[dict] = []
    skipped = 0
    for ev in events:
        mid = ev.get("message_id")
        if mid is None:
            continue
        mid = str(mid)
        if skip_existing and mid in seen:
            skipped += 1
            continue
        seen.add(mid)
        to_write.append(ev)
    if not to_write:
        return {"appended": 0, "skipped_duplicates": skipped}
    payload = "".join(
        json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n"
        for ev in to_write
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    return {"appended": len(to_write), "skipped_duplicates": skipped}


# -------------------------------------------------------------------- ingest


def _map_event_type(text: str, explicit: object) -> str:
    if isinstance(explicit, str) and explicit in EVENT_TYPES:
        return explicit
    low = _norm(text)
    for et, kws in _KEYWORDS:
        for kw in kws:
            if kw in low:
                return et
    return "note"  # nenhum desfecho reconhecido -> nota (catch-all seguro)


def _find_known_id(text: str, by_id: dict[str, dict]) -> str | None:
    """Primeiro id canônico CONHECIDO que aparece como substring do texto."""
    for jid in by_id:
        if jid and jid in text:
            return jid
    return None


def _match_by_company(text: str, by_company: dict[str, list[dict]]) -> dict | None:
    """Casa a empresa citada no texto quando exatamente 1 job é afetado."""
    low = _norm(text)
    hits: dict[str, dict] = {}
    for cname, jobs in by_company.items():
        if cname and cname in low:
            for j in jobs:
                if j.get("id"):
                    hits[str(j["id"])] = j
    if len(hits) == 1:
        return next(iter(hits.values()))
    return None


def _parse(mensagens: list[dict], eligible: list[dict] | None) -> tuple[list[dict], dict]:
    """Núcleo do parse (puro). Retorna (eventos, sumário)."""
    jobs = [j for j in (eligible or []) if isinstance(j, dict)]
    by_id = {str(j.get("id")): j for j in jobs if j.get("id")}
    by_company: dict[str, list[dict]] = {}
    for j in jobs:
        if j.get("company"):
            by_company.setdefault(_norm(j["company"]), []).append(j)

    events: list[dict] = []
    matched = unmatched = skipped = 0
    for m in mensagens or []:
        if not isinstance(m, dict):
            skipped += 1
            continue
        mid = m.get("message_id")
        if mid is None:
            skipped += 1
            continue
        mid = str(mid)
        text = str(m.get("text") or "")
        job_id: str | None = None
        # (1) id canônico conhecido no texto
        job_id = _find_known_id(text, by_id)
        # (2) campo job_id explícito
        if job_id is None and m.get("job_id") is not None:
            job_id = str(m["job_id"])
        # (3) empresa citada casando 1 job do eligible
        if job_id is None:
            hit = _match_by_company(text, by_company)
            if hit is not None:
                job_id = str(hit.get("id"))
        # sem vaga -> mensagem SKIPADA (decisão F41)
        if job_id is None:
            skipped += 1
            continue
        job = by_id.get(job_id)
        if job is not None:
            company = str(job.get("company") or "")
            matched += 1
        else:
            company = str(m.get("company") or "")
            unmatched += 1
        events.append({
            "message_id": mid,
            "ts": normalize_ts(m.get("date") or m.get("ts")),
            "job_id": job_id,
            "company": company,
            "event_type": _map_event_type(text, m.get("event_type")),
            "source": str(m.get("source") or "telegram"),
        })
    summary = {
        "messages": len(mensagens or []),
        "events": len(events),
        "matched": matched,
        "unmatched": unmatched,
        "skipped": skipped,
    }
    return events, summary


def parse_mensagens(mensagens: list[dict],
                    eligible: list[dict] | None = None) -> list[dict]:
    """Função PURA: dump de mensagens -> lista de eventos append-ready.

    ``mensagens`` = a lista ``messages`` do dump (ver schema no topo).
    ``eligible``  = o JSON de vagas elegíveis (``eligible_jobs.json``) usado
    para RESOLVER o ``job_id`` e DERIVAR a empresa. Offline, zero rede.
    """
    events, _ = _parse(mensagens, eligible)
    return events


def parse_report(mensagens: list[dict],
                 eligible: list[dict] | None = None) -> dict:
    """Como ``parse_mensagens`` mas devolve também o sumário do ingest."""
    events, summary = _parse(mensagens, eligible)
    return {"events": events, **summary}


def load_dump(path: Path | str) -> list[dict]:
    """Carrega o dump de mensagens (JSON) e devolve a lista ``messages``."""
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(obj, dict):
        msgs = obj.get("messages") or []
    elif isinstance(obj, list):
        msgs = obj
    else:
        msgs = []
    return [m for m in msgs if isinstance(m, dict)]


def ingest_dump(dump: object, *, eligible: list[dict] | None = None,
                log_path: Path | str = DEFAULT_LOG) -> dict:
    """Ingest idempotente: parse do dump + append no log (replay = no-op)."""
    if isinstance(dump, dict):
        msgs = dump.get("messages") or []
    elif isinstance(dump, list):
        msgs = dump
    else:
        msgs = []
    msgs = [m for m in msgs if isinstance(m, dict)]
    events, summary = _parse(msgs, eligible)
    res = append_events(log_path, events)
    return {**summary, **res}


# ---------------------------------------------------------------------- view


def rebuild_status(events: list[dict]) -> dict[str, dict]:
    """PURA/DETERMINÍSTICA: reconstrói o status a partir do log.

    ``status = último evento COM status por job_id`` (ordenação estável por
    ``(ts, message_id)`` — eventos fora de ordem geram o MESMO estado final).
    ``note`` não carrega status (não altera a view). Retorna dict ordenado
    por ``job_id``.
    """
    ordered = sorted(
        (e for e in events if isinstance(e, dict)),
        key=lambda e: (str(e.get("ts") or ""), str(e.get("message_id") or "")),
    )
    out: dict[str, dict] = {}
    for ev in ordered:
        jid = str(ev.get("job_id") or "")
        if not jid:
            continue
        et = str(ev.get("event_type") or "")
        rec = out.setdefault(jid, {
            "job_id": jid, "status": None, "last_event_type": None,
            "last_ts": None, "last_status_ts": None, "company": "",
            "n_events": 0,
        })
        rec["n_events"] += 1
        rec["last_event_type"] = et
        rec["last_ts"] = str(ev.get("ts") or "")
        if ev.get("company"):
            rec["company"] = str(ev["company"])
        status = STATUS_BY_EVENT.get(et)
        if status is not None:
            rec["status"] = status
            rec["last_status_ts"] = str(ev.get("ts") or "")
    return {jid: out[jid] for jid in sorted(out)}


if __name__ == "__main__":  # pragma: no cover - smoke manual
    import argparse

    ap = argparse.ArgumentParser(description="F41 — event log de candidaturas (leitura)")
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--rebuild", action="store_true",
                    help="imprime o status derivado (view) do log")
    a = ap.parse_args()
    evs = read_events(a.log)
    print(f"log: {a.log} -> {len(evs)} eventos")
    if a.rebuild:
        for jid, rec in rebuild_status(evs).items():
            print(f"  {jid}\t{rec['status']}\t(ult: {rec['last_event_type']} @ {rec['last_ts']})")
