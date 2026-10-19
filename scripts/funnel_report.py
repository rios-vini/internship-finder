"""F45 — Funil de candidaturas com MOTIVO DE MORTE + sazonalidade: relatório OFFLINE (padrão F28/F44).

Relatório determinístico, offline (zero HTTP, zero LLM), stdout + exit-code,
sobre o pipeline do dia e o loop de candidaturas do dono. SÓ LÊ — nunca
escreve em ``data/`` (medições em cópia; produção é intocável).

FONTES (as três verdades já existentes — nenhuma fonte nova):

1. ``data/collection_metrics.jsonl`` — record ``type: run`` por run do cron:
   ``total_collected``/``filtered``/``dedup_removed``/``eligible`` +
   contadores ``applicability_excluded_<motivo>`` (F37/F37.2/F37.3). É o
   funil do PIPELINE com os MOTIVOS DE MORTE por etapa.
2. ``data/personal/application_events.jsonl`` (F41 — event log append-only
   das candidaturas) — lido pela MESMA API do módulo ``application_log``
   (``read_events`` + ``rebuild_status``; nunca reparseado aqui — uma
   fonte de verdade só). É a cauda do funil: applied -> screening ->
   interview -> offer, com as mortes rejected/withdrawn.
3. ``data/eligible_jobs.json`` — o ranking vivo: dá "ranked"/"best" (Top
   N por score) e o TEXTO (título+descrição) que o parser puro de
   sazonalidade (``scripts/seasonality.py``) transforma no calendário.

FUNIL (etapas e mortes — nomes dos CAMPOS REAIS do record run):

    collected (total_collected)
      └─ morte: fora do recorte de estágio/país/tipo (collected - filtered)
    filtered (filtered)
      ├─ morte: duplicata (dedup_removed)
      ├─ morte: inaplicável POR MOTIVO (applicability_excluded_* — o
      │         death-reason breakdown, ex.: german_required 1.189)
      └─ morte: outros/não-contabilizado (residual — quando a aritmética
                não fecha; NUNCA é assert: o pipeline pode ganhar etapas)
    eligible (eligible)
    ranked  = todos os elegíveis ganham score (o ranking É o eligible ordenado)
    best    = Top N por score (corte de exibição/enrichment, default 30)
    [superfície viva = len(eligible_jobs.json) — pode DIFFERIR do eligible
     do run: remoção de 🔗 morta (F39) e inaplicáveis pós-hidratação (F25)
     acontecem DEPOIS do record; o relatório mostra os DOIS, sem fundir]

"SEMANAL": o funil é o do ÚLTIMO run (estado atual do pipeline); o caráter
semanal vem do TREND — eligible de hoje vs o run de 7 corridas atrás
(janela ``week_window``; menos de 7 records = campo ausente, nunca inventado).

DETERMINISMO: nenhuma dependência de rede ou relógio — a data do "último
run" vem do próprio record (``run_id``/``timestamp``), o trend usa só
records. Mesma entrada = mesmo relatório byte a byte.

Uso::

    python scripts/funnel_report.py \\
        --metrics data/collection_metrics.jsonl \\
        --events data/personal/application_events.jsonl \\
        --eligible data/eligible_jobs.json [--best 30] [--json]

Exit: 0 = relatório com dados; 1 = nenhuma fonte legível (nada a reportar).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seasonality  # noqa: E402 — parser puro da F45

DEFAULT_METRICS = "data/collection_metrics.jsonl"
DEFAULT_EVENTS = "data/personal/application_events.jsonl"
DEFAULT_ELIGIBLE = "data/eligible_jobs.json"

# "best" = Top 30 por score (o corte que o digest/enrichment/página de
# qualidade usam — DIGEST_TOP do ranking_digest; nunca redefinir aqui a
# sós: os dois default seguem iguais).
BEST_TOP = 30

# Janela do trend semanal: 7 runs diários do cron.
WEEK_WINDOW = 7

# Rótulos pt-BR dos motivos de morte (contadores do mecanismo F37+).
# Chave = sufixo do contador ``applicability_excluded_<key>``; motivo
# desconhecido (fase futura) exibe a chave crua — nunca quebra.
DEATH_LABELS = {
    "german_required": "alemão exigido",
    "visa_blocked": "visto bloqueado",
    "thesis_title": "tese no título",
    "werkstudent_puro": "werkstudent puro",
    "master_required": "mestrado exigido",
    "eu_citizenship_required": "cidadania UE exigida",
    "nl_enrolment_required": "matrícula NL exigida",
    "phd_position": "posição de doutorado",
    "duration_over_6m": "duração > 6 meses",
    "full_time_permanent": "tempo integral permanente",
    "erasmus_program": "programa Erasmus+",
    "spontaneous_pool": "pool espontâneo",
}

# Ordem de exibição dos desfechos do log F41 (schema da fase).
EVENT_ORDER = ("applied", "screening", "interview", "offer",
               "rejected", "withdrawn", "note")

_EVENT_LABELS = {
    "applied": "aplicadas", "screening": "triagem", "interview": "entrevista",
    "offer": "oferta", "rejected": "rejeitadas", "withdrawn": "desistiu",
    "note": "notas",
}


def death_label(key: str) -> str:
    """Rótulo pt-BR de um motivo de morte (chave crua como fallback)."""
    return DEATH_LABELS.get(key, key)


# ---------------------------------------------------------------------------
# Loaders (defensivos — arquivo ausente/corrompido nunca derruba o chamador)
# ---------------------------------------------------------------------------


def load_run_records(metrics_path: str | Path) -> list[dict]:
    """Records ``type: run`` do JSONL de métricas, na ordem do arquivo
    (append = cronológico). Linha vazia/corrompida é ignorada."""
    path = Path(metrics_path)
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — leitura defensiva
        return []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "run":
            out.append(obj)
    return out


def load_eligible_jobs(eligible_path: str | Path) -> list[dict]:
    """Lista de vagas do ranking (lista de dicts; formatos tolerantes)."""
    path = Path(eligible_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, list):
        return [j for j in data if isinstance(j, dict)]
    return []


def load_events(events_path: str | Path) -> list[dict]:
    """Eventos do log F41 via a MESMA API do ``application_log`` (uma fonte
    de verdade; import falho -> [] — o funil segue sem a cauda pessoal)."""
    try:
        import application_log
        return application_log.read_events(events_path)
    except Exception:  # noqa: BLE001 — cauda pessoal é best-effort
        return []


# ---------------------------------------------------------------------------
# Funil do pipeline (record run -> etapas + motivos de morte)
# ---------------------------------------------------------------------------


def pipeline_funnel(run: dict) -> dict:
    """Funil de UM record ``type: run``: etapas + mortes por motivo.

    A identidade aritmética (filtered - dedup - inaplicáveis = eligible)
    é VERIFICADA, nunca afirmada: quando não fecha, a diferença vira a
    morte "residual" (pipeline pode ganhar etapas; o relatório é honesto
    com o que o record diz).
    """
    collected = run.get("total_collected")
    filtered = run.get("filtered")
    dedup_raw = run.get("dedup_removed")
    dedup = (dedup_raw if isinstance(dedup_raw, int)
             and not isinstance(dedup_raw, bool) else 0)
    eligible = run.get("eligible")
    reasons: dict[str, int] = {}
    prefix = "applicability_excluded_"
    for key, value in run.items():
        if isinstance(key, str) and key.startswith(prefix) \
                and isinstance(value, int) and not isinstance(value, bool):
            reasons[key[len(prefix):]] = value
    reasons_total = sum(reasons.values())

    def _is_count(x: object) -> bool:
        return isinstance(x, int) and not isinstance(x, bool)

    out_of_scope = (collected - filtered) if (
        _is_count(collected) and _is_count(filtered)) else None
    residual = None
    if isinstance(filtered, int) and isinstance(eligible, int):
        residual = int(filtered) - dedup - reasons_total - int(eligible)
        if residual == 0:
            residual = None
    return {
        "run_id": run.get("run_id"),
        "timestamp": run.get("timestamp"),
        "collected": collected,
        "filtered": filtered,
        "out_of_scope": out_of_scope,
        "dedup_removed": dedup,
        "applicability": {"total": reasons_total, "reasons": reasons},
        "residual": residual,
        "eligible": eligible,
    }


def weekly_trend(run_records: list[dict], *, window: int = WEEK_WINDOW) -> dict | None:
    """Eligible do último run vs o run de ``window`` corridas atrás.

    Records em ordem cronológica (append); menos de ``window`` records =
    None (campo ausente — nunca inventado).
    """
    if len(run_records) < window:
        return None
    last = run_records[-1].get("eligible")
    then = run_records[-window].get("eligible")
    if not isinstance(last, int) or not isinstance(then, int):
        return None
    return {"eligible_last": last, "eligible_then": then,
            "delta": last - then, "window": window}


# ---------------------------------------------------------------------------
# Cauda pessoal (event log F41) — desfechos das candidaturas
# ---------------------------------------------------------------------------


def application_funnel(events: list[dict]) -> dict | None:
    """Contagens por desfecho + status final por vaga (rebuild_status F41).

    None quando não há eventos (log ausente/ainda vazio — a cauda do
    funil simplesmente não existe ainda).
    """
    if not events:
        return None
    by_type: dict[str, int] = {}
    jobs: set[str] = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        et = str(ev.get("event_type") or "?")
        by_type[et] = by_type.get(et, 0) + 1
        jid = str(ev.get("job_id") or "")
        if jid:
            jobs.add(jid)
    status_counts: dict[str, int] = {}
    try:
        import application_log
        rebuilt = application_log.rebuild_status(events)
    except Exception:  # noqa: BLE001 — status é derivado, best-effort
        rebuilt = {}
    for rec in rebuilt.values():
        st = rec.get("status") or "unknown"
        status_counts[st] = status_counts.get(st, 0) + 1
    return {
        "events": len(events),
        "jobs": len(jobs),
        "by_type": {k: by_type[k] for k in sorted(by_type)},
        "status_counts": {k: status_counts[k] for k in sorted(status_counts)},
    }


# ---------------------------------------------------------------------------
# Sazonalidade (ranking vivo -> calendário de janelas de início)
# ---------------------------------------------------------------------------


def seasonality_summary(jobs: list[dict]) -> dict:
    """Calendário = hit canônico por vaga (título + descrição), agregado
    por rótulo. ``scanned``/``with_window`` carregam as contagens.

    F62: a composição do texto vive em ``seasonality.job_window_text``
    (FONTE ÚNICA — o badge da página varre o MESMO texto)."""
    texts = [seasonality.job_window_text(j) for j in jobs]
    calendar = seasonality.seasonality_calendar(texts)
    return {
        "scanned": len(jobs),
        "with_window": sum(n for _, n in calendar),
        "calendar": [{"label": label, "count": n} for label, n in calendar],
    }


# ---------------------------------------------------------------------------
# Relatório completo
# ---------------------------------------------------------------------------


def build_report(metrics_path: str | Path = DEFAULT_METRICS,
                 events_path: str | Path = DEFAULT_EVENTS,
                 eligible_path: str | Path = DEFAULT_ELIGIBLE, *,
                 best_top: int = BEST_TOP,
                 week_window: int = WEEK_WINDOW) -> dict | None:
    """Monta o relatório (todas as fontes são OPCIONAIS/defensivas).

    None quando NENHUMA fonte legível (sem record run E sem eligible E
    sem eventos — nada a reportar).
    """
    runs = load_run_records(metrics_path)
    jobs = load_eligible_jobs(eligible_path)
    events = load_events(events_path)

    funnel = pipeline_funnel(runs[-1]) if runs else None
    if funnel is None and not jobs and not events:
        return None

    ranked = len(jobs) if jobs else None
    best = min(best_top, len(jobs)) if jobs else None
    return {
        "funnel": funnel,
        "trend": weekly_trend(runs, window=week_window),
        "surface": len(jobs),
        "ranked": ranked,
        "best": best,
        "best_top": best_top,
        "application": application_funnel(events),
        "seasonality": seasonality_summary(jobs),
    }


def _fmt_int(value: int | None) -> str:
    return "—" if value is None else f"{value:,}".replace(",", ".")


def format_report(report: dict | None, *, max_reasons: int = 12,
                  max_windows: int = 10) -> list[str]:
    """Linhas de texto do relatório (stdout). Pura sobre ``report``
    (None -> "(sem dados)", nunca lança)."""
    if not report:
        return ["(sem dados)"]
    lines: list[str] = ["== Funil de candidaturas (F45) =="]
    fun = report.get("funnel")
    if fun:
        run_day = str(fun.get("run_id") or "")[:10] or "?"
        lines.append(f"último run: {run_day}")
        lines.append(f"  collected:   {_fmt_int(fun.get('collected'))} (brutas)")
        if fun.get("out_of_scope") is not None:
            lines.append(f"  ├─ morte 'fora do recorte' (estágio/país/tipo): "
                         f"-{_fmt_int(fun['out_of_scope'])}")
        lines.append(f"  filtered:    {_fmt_int(fun.get('filtered'))} (pós-filtro)")
        if fun.get("dedup_removed"):
            lines.append(f"  ├─ morte 'duplicata': -{_fmt_int(fun.get('dedup_removed'))}")
        app = fun.get("applicability") or {}
        reasons = app.get("reasons") or {}
        if app.get("total"):
            lines.append(f"  ├─ morte 'inaplicável': -{_fmt_int(app['total'])} "
                         f"({len(reasons)} motivos)")
            for key, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:max_reasons]:
                lines.append(f"  │    {death_label(key)} ({key}): {_fmt_int(n)}")
            if len(reasons) > max_reasons:
                lines.append(f"  │    (+{len(reasons) - max_reasons} outros motivos)")
        if fun.get("residual"):
            lines.append(f"  ├─ morte 'residual' (não contabilizada): "
                         f"{_fmt_int(fun['residual'])}")
        lines.append(f"  eligible:    {_fmt_int(fun.get('eligible'))}")
    if report.get("ranked") is not None:
        lines.append(f"  ranked:      {_fmt_int(report.get('ranked'))} "
                     f"(superfície viva; pode diferir do eligible do run — "
                     f"F39/F25 removem depois)")
        lines.append(f"  best:        {_fmt_int(report.get('best'))} "
                     f"(Top {report.get('best_top')} por score)")
    trend = report.get("trend")
    if trend:
        d = int(trend["delta"])
        delta_txt = f"+{_fmt_int(d)}" if d > 0 else (
            _fmt_int(d) if d < 0 else "±0")
        lines.append(f"  trend:       {_fmt_int(trend['eligible_last'])} hoje vs "
                     f"{_fmt_int(trend['eligible_then'])} há {trend['window']} runs "
                     f"({delta_txt})")
    app_fun = report.get("application")
    if app_fun:
        parts = ", ".join(
            f"{_EVENT_LABELS.get(et, et)} {n}"
            for et, n in sorted(app_fun.get("by_type", {}).items(),
                                key=lambda kv: (EVENT_ORDER.index(kv[0])
                                                if kv[0] in EVENT_ORDER else 99, kv[0])))
        lines.append(f"  candidaturas: {app_fun['events']} eventos · "
                     f"{app_fun['jobs']} vagas — {parts}")
        if app_fun.get("status_counts"):
            status_txt = ", ".join(f"{k} {v}" for k, v in
                                   sorted(app_fun["status_counts"].items()))
            lines.append(f"  status final: {status_txt}")
    else:
        lines.append("  candidaturas: (log F41 vazio/ausente — cauda do "
                     "funil ainda sem eventos)")
    sea = report.get("seasonality") or {}
    cal = sea.get("calendar") or []
    lines.append(f"  sazonalidade: {sea.get('with_window', 0)} de "
                 f"{sea.get('scanned', 0)} vagas com janela de início detectada")
    for item in cal[:max_windows]:
        lines.append(f"    {item['count']:4d}  {item['label']}")
    if len(cal) > max_windows:
        lines.append(f"    (+{len(cal) - max_windows} outras janelas)")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Funil de candidaturas com motivo de morte + calendário "
                    "de sazonalidade (offline, determinístico; padrão F44).")
    parser.add_argument("--metrics", default=DEFAULT_METRICS,
                        help=f"JSONL de métricas (default: {DEFAULT_METRICS})")
    parser.add_argument("--events", default=DEFAULT_EVENTS,
                        help=f"event log F41 (default: {DEFAULT_EVENTS})")
    parser.add_argument("--eligible", default=DEFAULT_ELIGIBLE,
                        help=f"ranking vivo (default: {DEFAULT_ELIGIBLE})")
    parser.add_argument("--best", type=int, default=BEST_TOP,
                        help=f"corte 'best' por score (default: {BEST_TOP})")
    parser.add_argument("--json", action="store_true",
                        help="saída estruturada (1 objeto JSON)")
    args = parser.parse_args(argv)

    report = build_report(args.metrics, args.events, args.eligible,
                          best_top=args.best)
    if report is None:
        print("funil: nenhuma fonte legível (metrics/events/eligible)")
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print("\n".join(format_report(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
