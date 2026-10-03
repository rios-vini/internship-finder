"""Render minimal da pagina publica (F6) — top-50 do dia, mobile-first.

Substitui o HTML monolitico da interface.py na publicacao: em vez de
embutir TODAS as vagas elegiveis com breakdowns/fit/intel por vaga (9,5 MB
e crescendo a cada run), a pagina publica mostra o TOP-50 do dia com os
campos de decisao rapida — titulo, empresa, local, score, link de
candidatura e badge visa_friendly (F5) — num card compacto por vaga.

Decisoes (spec F6):

- **Mortos removidos**: ``application_deadline`` (F1: validade do FEED,
  nao data real), ``official_page`` (F1: desligado) e os campos de intel
  que dependiam do enrichment LLM (Fase 3, cookie-walled desde F1). Nada
  disso e renderizado.
- **Badge 🛂 visa_friendly PRESERVADA** (F5, mergeada horas antes): lida
  do campo do job (pipeline F5) com fallback re-derivando do
  ``company_intel`` curado (retrocompat de snapshots pre-F5, mesmo
  comportamento da interface.py).
- **Salario quando citado no anuncio** (evidencia textual — nunca
  inventado; mesma regra da interface.py/opportunity_intel).
- **CSS inline minimo, dark mode default** (spec: "dark mode"), sem
  framework; mobile-first com cards. Vanilla JS opcional (filtro
  visa-friendly + busca) cabe em ~1,5 KB — mantido por utilidade real e
  tamanho irrelevante.
- **Ordenacao: score do pipeline, server-side** (a lista ja vem ordenada;
  o sort e defensivo). Nenhum JS de ordenacao.
- **JSON/CSV completos NAO mudam**: sao a base de dados, nao a interface.

A mecanica de deploy e intocada (publish_pages.publish_html atomico,
``check_public_safe``, clone gh-pages, push so do index.html): este
modulo so entrega o CONTEUDO do index.html.
"""

from __future__ import annotations

import html as _html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

__all__ = [
    "PAGE_TOP", "PAGE_TARGET_BYTES", "render_minimal_html",
    "render_minimal_html_from_file",
]

# Quantas vagas a pagina publica mostra (spec F6: top-50 do dia).
PAGE_TOP = 50

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


def _snippet(job: dict, limit: int = 140) -> str:
    """Trecho curto da descricao ORIGINAL (sem traducao/inferencia)."""
    text = " ".join(str(job.get("description") or "").split())
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")


def _card(rank: int, job: dict, *, visa: bool, salary: str,
          snippet: str, apply_href: str | None, job_href: str | None) -> str:
    """Card compacto de uma vaga (mobile-first)."""
    vf = ' <span class="vf" title="Empresa com política de visto (visa_policy: explicit_support ou unclear)">🛂</span>' if visa else ""
    title = _esc(job.get("title") or "(sem título)")
    inner = f'<a class="t" href="{_esc(job_href)}" target="_blank" rel="noopener">{title}</a>{vf}' if job_href else f'<span class="t">{title}</span>{vf}'
    meta_bits = [
        _esc(job.get("company") or "—"),
        _esc(_short_location(job)),
    ]
    if salary:
        meta_bits.append(f'<b class="sal">{_esc(salary)}</b>')
    meta = ' · '.join(meta_bits)
    score = _fmt_score(job.get("score"))
    btn = ""
    if apply_href:
        btn = f'<a class="btn" href="{_esc(apply_href)}" target="_blank" rel="noopener">candidatar-se ↗</a>'
    elif job_href:
        btn = f'<a class="btn" href="{_esc(job_href)}" target="_blank" rel="noopener">abrir vaga ↗</a>'
    snip = f'<p class="d">{_esc(snippet)}</p>' if snippet else ""
    qtext = " ".join(x for x in (job.get("title"), job.get("company"),
                                 job.get("location")) if x)
    return (
        f'<li class="c{" vf-on" if visa else ""}" data-s="{score}"'
        f' data-vf="{1 if visa else 0}"'
        f' data-q="{_esc(qtext)}">'
        f'<span class="r">{rank}</span><span class="s">{score}</span>'
        f'<div class="bd">{inner}<div class="m">{meta}</div>{snip}{btn}</div></li>'
    )


_CSS = """body{margin:0;background:#10151b;color:#e6edf3;font:16px/1.45 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px 14px 40px}
h1{font-size:1.05rem;margin:0 0 2px}
.p{color:#9aa7b4;font-size:.8rem;margin:2px 0 12px}
.bar{display:flex;gap:8px;margin:0 0 14px;flex-wrap:wrap;align-items:center}
.bar input[type=search]{flex:1 1 160px;min-width:0;padding:8px 12px;border:1px solid #2a343e;border-radius:8px;background:#192027;color:#e6edf3;font-size:16px}
.bar input[type=checkbox]{accent-color:#4da3ff}
.bar label{font-size:.82rem;color:#9aa7b4;white-space:nowrap}
ol{list-style:none;margin:0;padding:0}
li.c{display:flex;gap:10px;padding:12px 10px;border-bottom:1px solid #2a343e}
.r{flex:0 0 24px;color:#9aa7b4;font-size:.75rem;font-variant-numeric:tabular-nums;padding-top:3px}
.s{flex:0 0 34px;font-weight:700;font-size:.95rem;font-variant-numeric:tabular-nums;color:#9fd8b4;padding-top:1px}
.bd{flex:1;min-width:0}
.t{font-weight:600;color:#e6edf3;text-decoration:none}
a.t:visited{color:#c8d3dd}
a.t:hover{text-decoration:underline}
.vf{font-size:.8rem}
.m{color:#9aa7b4;font-size:.82rem;margin-top:2px}
.m .sal{color:#e8cf8a;font-weight:600}
.d{color:#8b98a5;font-size:.8rem;margin:5px 0 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.btn{display:inline-block;margin-top:7px;padding:6px 14px;border:1px solid #1c7a4a;color:#9fd8b4;border-radius:999px;font-size:.82rem;text-decoration:none}
.btn:hover{background:#1c7a4a;color:#10151b}
.f{color:#9aa7b4;font-size:.72rem;margin:10px 0 0}
@media(min-width:640px){main{padding:24px 20px 56px}h1{font-size:1.25rem}}
"""

_JS = """(function(){var q=document.getElementById('q'),vf=document.getElementById('f-vf'),n=document.getElementById('n');
if(!q)return;function f(){var t=q.value.trim().toLowerCase(),v=vf&&vf.checked,c=0;
document.querySelectorAll('li.c').forEach(function(li){var ok=!t||li.getAttribute('data-q').toLowerCase().indexOf(t)>-1;
if(v)ok=ok&&li.getAttribute('data-vf')==='1';li.style.display=ok?'':'none';if(ok)c++;});
if(n)n.textContent=c;}q.addEventListener('input',f);if(vf)vf.addEventListener('change',f);})();
"""


def render_minimal_html(
    jobs: list[dict],
    *,
    total_eligible: int,
    generated_at: str,
    top: int = PAGE_TOP,
    company_intel_map: dict | None = None,
) -> str:
    """HTML minimo do top-N do dia (self-contained; ~10-40 KB tipico).

    ``jobs``: lista JA ordenada pelo score do pipeline (ordem oficial). A
    pagina nao re-ranqueia nada — apenas enumera o topo. ``total_eligible``
    e o tamanho do conjunto elegivel inteiro (o rodape informa que a
    pagina mostra o top-N e o resto vive no JSON/CSV completos).
    """
    shown = list(jobs[:top])
    rows: list[str] = []
    for i, job in enumerate(shown, 1):
        entry = None
        if company_intel_map is not None:
            try:
                from internship_finder import opportunity_intel
                entry = opportunity_intel.company_intel_for(job, company_intel_map)
            except Exception:  # noqa: BLE001 — view best-effort
                entry = None
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
        rows.append(_card(
            i, job, visa=visa, salary=salary,
            snippet=_snippet(job), apply_href=apply_href, job_href=job_href,
        ))
    body = "\n".join(rows)
    n_vf = sum(1 for r in rows if 'vf-on' in r)
    footer_note = (
        f"Top {len(shown)} de {total_eligible} vagas elegíveis · {n_vf} com 🛂 "
        "(empresa com política de visto) · ranking, JSON e CSV completos "
        "são gerados pelo pipeline no VPS"
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
</div>
<ol id="list">
{body}
</ol>
<p class="f">{_esc(footer_note)}</p>
</main>
<script>{_JS}</script>
</body>
</html>
"""


def render_minimal_html_from_file(path: Path, *, top: int = PAGE_TOP,
                                  company_intel_map: dict | None = None) -> str:
    """Le o eligible_jobs.json e devolve o HTML minimo do topo."""
    with path.open(encoding="utf-8") as fh:
        jobs = json.load(fh)
    if not isinstance(jobs, list):
        raise ValueError(f"formato inesperado em {path}: esperado lista de vagas")
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    return render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at=generated,
        top=top, company_intel_map=company_intel_map,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI (mesmo contrato da interface.py: --input/--top/--output).

    Chamado pelo ``publish_pages.render_ranking_html`` como subprocesso com
    ``--input`` RELATIVO (cwd = raiz do repo): nenhum caminho absoluto da
    VPS entra na pagina. ``--output -`` imprime no stdout (uso manual).
    """
    import argparse

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    parser = argparse.ArgumentParser(
        description="Render minimo da pagina publica (F6): top do dia, "
                    "mobile-first, dark, self-contained.",
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
    page = render_minimal_html_from_file(
        Path(args.input), top=args.top, company_intel_map=company_intel_map,
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
