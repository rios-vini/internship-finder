#!/usr/bin/env python3
"""Cobertura dos campos estruturados do ``raw`` (Fase B) — metricas offline.

Le o snapshot ranqueado (default ``data/eligible_jobs.json`` do CWD) e
imprime TODAS as metricas obrigatorias da spec §11 da Fase B:

    DEPARTMENT / EMPLOYMENT TYPE / REMOTE / COMMITMENT / APPLY URL /
    REQUISITION ID / GLOBAL ID

mais a analise de ``requisition_id`` (unicos, duplicados por tenant,
mirrors DE/EN, falsos positivos) e ``global_id`` (cobertura, unicidade,
colisoes, relacao com o id atual). Ferramenta MANUAL de diagnostico —
NAO faz parte do array do CI (mesma precedencia de
``enrichment_coverage.py``): nada de rede, nada de escrita fora de
stdout (arquivoauxiliar so em /tmp se --json for passado).

Fonte: ``internship_finder.structured_fields`` (acessores puros da Fase
B). ATS por vaga = ``job["source"].split(":")[0]``.

Uso:
    .venv/bin/python scripts/structured_fields_coverage.py
    .venv/bin/python scripts/structured_fields_coverage.py --input data/eligible_jobs.json
    .venv/bin/python scripts/structured_fields_coverage.py --json /tmp/cov.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.structured_fields import (  # noqa: E402
    apply_url,
    commitment_label,
    department,
    employment_type_enum,
    employment_type_relation,
    global_id,
    is_remote_flag,
    remote_relation,
    requisition_id,
)

DEFAULT_INPUT = Path("data/eligible_jobs.json")


def ats_of(job: dict) -> str:
    """ATS da vaga: primeiro segmento do ``source`` (``ats:slug``)."""
    return str(job.get("source") or "?").split(":")[0]


def tenant_of(job: dict) -> str:
    """Tenant completo (``ats:slug``) — escopo da analise de duplicidade."""
    return str(job.get("source") or "?")


def pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.1f}%" if total else "n/a"


def coverage_by_ats(jobs: list[dict], has) -> dict[str, tuple[int, int]]:
    """``{ats: (com campo, total)}`` para um acessor booleano ``has``."""
    per: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for j in jobs:
        ats = ats_of(j)
        n, t = per[ats]
        per[ats] = (n + (1 if has(j) else 0), t + 1)
    return dict(sorted(per.items()))


def print_ats_table(field: str, per: dict[str, tuple[int, int]]) -> None:
    print(f"  cobertura por ATS ({field}):")
    for ats, (n, t) in per.items():
        bar = "#" * int(round(20 * n / t)) if t else ""
        print(f"    {ats:<18} {n:>4}/{t:<4} {pct(n, t):>6}  {bar}")


def analyze(jobs: list[dict]) -> dict:
    """Todas as metricas da spec §11 em um dict (para --json)."""
    total = len(jobs)
    out: dict = {"eligible_total": total}

    # -- DEPARTMENT --------------------------------------------------------
    dep_jobs = [j for j in jobs if department(j)]
    out["department"] = {
        "com": len(dep_jobs),
        "cobertura_pct": round(100.0 * len(dep_jobs) / total, 1) if total else 0,
        "por_ats": {a: n for a, (n, t) in
                    coverage_by_ats(jobs, department).items()},
        "valores_distintos": len({department(j) for j in dep_jobs}),
    }

    # -- EMPLOYMENT TYPE ---------------------------------------------------
    et_jobs = [j for j in jobs if employment_type_enum(j)]
    et_vals = Counter(employment_type_enum(j) for j in et_jobs)
    rel = Counter(employment_type_relation(j) for j in jobs)
    out["employment_type"] = {
        "com_valor": len(et_jobs),
        "valores": dict(et_vals),
        "intern": et_vals.get("INTERN", 0),
        "full_time": et_vals.get("FULL_TIME", 0),
        "outros": {k: v for k, v in et_vals.items()
                   if k not in ("INTERN", "FULL_TIME")},
        "missing": rel.get("missing", 0),
        "match": rel.get("match", 0),
        "conflict": rel.get("conflict", 0),
        "por_ats": {a: n for a, (n, t) in
                    coverage_by_ats(jobs, employment_type_enum).items()},
    }

    # -- REMOTE ------------------------------------------------------------
    rem_true = sum(1 for j in jobs if is_remote_flag(j) is True)
    rem_false = sum(1 for j in jobs if is_remote_flag(j) is False)
    rrel = Counter(remote_relation(j) for j in jobs)
    out["remote"] = {
        "com_valor": rem_true + rem_false,
        "true": rem_true,
        "false": rem_false,
        "missing": rrel.get("missing", 0),
        "match": rrel.get("match", 0),
        "conflict": rrel.get("conflict", 0),
        "por_ats": {a: n for a, (n, t) in
                    coverage_by_ats(jobs, lambda j: is_remote_flag(j) is not None).items()},
    }

    # -- COMMITMENT --------------------------------------------------------
    com_jobs = [j for j in jobs if commitment_label(j)]
    com_vals = Counter(commitment_label(j) for j in com_jobs)
    # Sobreposicao com o label canonico (cadeia de fallback do adapter):
    # commitment e ORIGEM de Job.employment_type nos ATS que o preenchem.
    com_same_canonical = sum(
        1 for j in com_jobs
        if str(j.get("employment_type") or "").strip().upper()
        == commitment_label(j).strip().upper().replace(" ", "_").replace("-", "_")
    )
    out["commitment"] = {
        "cobertura": len(com_jobs),
        "valores_distintos": dict(com_vals),
        "igual_ao_label_canonico": com_same_canonical,
    }

    # -- APPLY URL ---------------------------------------------------------
    ap_jobs = [j for j in jobs if apply_url(j)]
    ap_diff = [j for j in ap_jobs if apply_url(j) != str(j.get("url") or "")]
    out["apply_url"] = {
        "com_valor": len(ap_jobs),
        "diferente_de_job_url": len(ap_diff),
        "igual_a_job_url": len(ap_jobs) - len(ap_diff),
        "por_ats": {a: n for a, (n, t) in
                    coverage_by_ats(jobs, apply_url).items()},
    }

    # -- REQUISITION ID ----------------------------------------------------
    req_jobs = [j for j in jobs if requisition_id(j)]
    by_tenant: dict[str, list[dict]] = defaultdict(list)
    for j in req_jobs:
        by_tenant[tenant_of(j)].append(j)
    dup_values: list[dict] = []
    n_dup_jobs = 0
    for tenant, lst in sorted(by_tenant.items()):
        seen: dict[str, list[dict]] = defaultdict(list)
        for j in lst:
            seen[requisition_id(j)].append(j)
        for req, group in seen.items():
            if len(group) > 1:
                n_dup_jobs += len(group)
                dup_values.append({
                    "tenant": tenant,
                    "requisition_id": req,
                    "jobs": [{"id": g.get("id"), "title": g.get("title"),
                              "company": g.get("company")} for g in group],
                })
    # requisition_id em multiplos jobs (qualquer escopo)
    by_req_all: dict[str, list[dict]] = defaultdict(list)
    for j in req_jobs:
        by_req_all[requisition_id(j)].append(j)
    multi = {r: lst for r, lst in by_req_all.items() if len(lst) > 1}
    # Pares candidatos a mirror DE/EN: mesmo req_id no mesmo tenant com
    # titulos cuja diferenca e essencialmente o idioma. Heuristica leve e
    # apenas para o relatorio: mesmo tenant + mesmo req_id + um titulo
    # com marcador DE e outro com marcador EN da mesma raiz.
    mirror_candidates = []
    false_positives = []
    for entry in dup_values:
        group = entry["jobs"]
        titles = [str(g["title"] or "") for g in group]
        # mirror DE/EN: um titulo DE (Praktikum/Pflichtpraktikum/Werkstudent)
        # e um EN (Internship/Mandatory Internship/Working Student) no mesmo
        # par de req_id — par DE/EN legitimo reutilizado pelo empregador.
        de_marks = [bool(re.search(
            r"praktikum|werkstudent|praktikant", t, re.I)) for t in titles]
        en_marks = [bool(re.search(
            r"internship|working student|intern\b", t, re.I)) for t in titles]
        if any(de_marks) and any(en_marks):
            mirror_candidates.append(entry)
        else:
            false_positives.append(entry)
    # Sobreposicao com external_id (cadeia de fallback do adapter: req_id
    # alimenta external_id em alguns ATS — 29/119 no snapshot 26/09).
    req_eq_ext = sum(1 for j in req_jobs
                     if requisition_id(j) == str(j.get("external_id") or ""))
    out["requisition_id"] = {
        "cobertura": len(req_jobs),
        "unicos": len({requisition_id(j) for j in req_jobs}),
        "duplicados_por_tenant": len(dup_values),
        "jobs_afetados_por_dup": n_dup_jobs,
        "em_multiplos_jobs_total": sum(len(v) for v in multi.values()),
        "igual_ao_external_id": req_eq_ext,
        "por_ats": {a: n for a, (n, t) in
                    coverage_by_ats(jobs, requisition_id).items()},
        "pares_duplicados": dup_values,
        "mirrors_de_en_candidatos": [
            e["requisition_id"] for e in mirror_candidates],
        "falsos_positivos_provaveis": [
            e["requisition_id"] for e in false_positives],
    }

    # -- GLOBAL ID ---------------------------------------------------------
    gid_jobs = [j for j in jobs if global_id(j)]
    gids = [global_id(j) for j in gid_jobs]
    gid_count = Counter(gids)
    collisions = {g: n for g, n in gid_count.items() if n > 1}
    # Relacao com o id atual: global_id = "{ats_type}:{ats_id}"; o id do
    # projeto = "<company>|<source>:<external_id>". O prefixo ats_type
    # deve casar com o primeiro segmento do source.
    prefix_match = sum(
        1 for j in gid_jobs
        if global_id(j).split(":")[0] == ats_of(j)
    )
    out["global_id"] = {
        "cobertura": len(gid_jobs),
        "unicos": len(set(gids)),
        "colisoes": len(collisions),
        "prefixo_casa_com_source": prefix_match,
        "colisoes_detalhe": collisions,
    }
    return out


def print_report(jobs: list[dict], m: dict) -> None:
    total = m["eligible_total"]
    print("=" * 72)
    print(f"FASE B — CAMPOS ESTRUTURADOS DO raw (ats-scrapers 0.3.0)")
    print(f"snapshot: {total} vagas eligible")
    print("=" * 72)

    d = m["department"]
    print(f"\nDEPARTMENT: {d['com']}/{total} ({pct(d['com'], total)}) "
          f"— {d['valores_distintos']} valores distintos")
    print_ats_table("department", coverage_by_ats(jobs, department))

    e = m["employment_type"]
    print(f"\nEMPLOYMENT TYPE: com valor {e['com_valor']}/{total} "
          f"({pct(e['com_valor'], total)}) | missing {e['missing']}")
    print(f"  INTERN: {e['intern']} | FULL_TIME: {e['full_time']} | "
          f"outros: {e['outros']}")
    print(f"  relation (enum x classificacao atual): "
          f"match {e['match']} | conflict {e['conflict']} | missing {e['missing']}")
    print_ats_table("employment_type", coverage_by_ats(jobs, employment_type_enum))

    r = m["remote"]
    print(f"\nREMOTE: com valor {r['com_valor']}/{total} "
          f"({pct(r['com_valor'], total)}) | true {r['true']} | "
          f"false {r['false']} | missing {r['missing']}")
    print(f"  relation (flag x sinal textual): match {r['match']} | "
          f"conflict {r['conflict']}")
    print_ats_table("is_remote",
                    coverage_by_ats(jobs, lambda j: is_remote_flag(j) is not None))

    c = m["commitment"]
    print(f"\nCOMMITMENT: cobertura {c['cobertura']}/{total} "
          f"({pct(c['cobertura'], total)})")
    print(f"  valores distintos: {c['valores_distintos']}")
    print(f"  igual ao label canonico (origem via adapter): "
          f"{c['igual_ao_label_canonico']}/{c['cobertura']}")

    a = m["apply_url"]
    print(f"\nAPPLY URL: cobertura {a['com_valor']}/{total} "
          f"({pct(a['com_valor'], total)})")
    print(f"  apply_url != job.url: {a['diferente_de_job_url']} | "
          f"igual (nao renderiza segundo botao): {a['igual_a_job_url']}")
    print_ats_table("apply_url", coverage_by_ats(jobs, apply_url))

    q = m["requisition_id"]
    print(f"\nREQUISITION ID: cobertura {q['cobertura']}/{total} "
          f"({pct(q['cobertura'], total)}) | unicos {q['unicos']}")
    print(f"  igual ao external_id atual (origem via adapter): "
          f"{q['igual_ao_external_id']}/{q['cobertura']}")
    print(f"  duplicados dentro do mesmo tenant: {q['duplicados_por_tenant']} "
          f"valores ({q['jobs_afetados_por_dup']} jobs afetados)")
    for entry in q["pares_duplicados"]:
        print(f"    DUP {entry['tenant']} req={entry['requisition_id']}")
        for g in entry["jobs"]:
            print(f"        - {g['title']}")
    print(f"  candidatos a mirror DE/EN: "
          f"{q['mirrors_de_en_candidatos']}")
    print(f"  falsos positivos provaveis (titulos distintos, mesmo req): "
          f"{q['falsos_positivos_provaveis']}")

    g = m["global_id"]
    print(f"\nGLOBAL ID: cobertura {g['cobertura']}/{total} "
          f"({pct(g['cobertura'], total)}) | unicos {g['unicos']} | "
          f"colisoes {g['colisoes']}")
    print(f"  prefixo ats_type casa com source: "
          f"{g['prefixo_casa_com_source']}/{g['cobertura']}")
    if g["colisoes_detalhe"]:
        print(f"  colisoes: {g['colisoes_detalhe']}")

    print("\n" + "=" * 72)
    print("NOTA: eligible/scores/ranking NAO mudam nesta fase (nenhum campo")
    print("entra em filtro/score/dedup — display e metrica apenas).")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Metricas de cobertura dos campos estruturados do raw "
                    "(Fase B) sobre o snapshot eligible.",
    )
    parser.add_argument(
        "--input", default=str(DEFAULT_INPUT),
        help=f"Snapshot ranqueado (default: {DEFAULT_INPUT} do CWD)",
    )
    parser.add_argument(
        "--json", default=None, metavar="PATH",
        help="Escreve tambem as metricas em JSON (use /tmp/...; default: nao escreve)",
    )
    args = parser.parse_args(argv)
    path = Path(args.input)
    if not path.exists():
        print(f"ERRO: snapshot nao encontrado: {path}", file=sys.stderr)
        return 2
    jobs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(jobs, list):
        print("ERRO: formato inesperado (esperado lista de vagas)", file=sys.stderr)
        return 2
    m = analyze(jobs)
    print_report(jobs, m)
    if args.json:
        Path(args.json).write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nmetricas JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
