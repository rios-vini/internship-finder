"""Interface simples do internship-finder: top vagas, filtros e link (#25).

Gera uma pagina HTML unica e auto-contida (CSS inline, sem JS externo/framework)
com as melhores vagas ja ranqueadas — o dono abre o arquivo no browser e, em
~30s, ve o topo do ranking com 1 clique para a vaga.

Decisao de formato (P3 #25): pagina HTML estatica gerada por script, stdlib
pura. Justificativa: (a) o uso real pede URL clicavel ("1 clique para a vaga")
— HTML nativo, terminal exigiria copiar/colar; (b) zero dependencia nova e
zero servidor para manter (``http.server`` exigiria um processo vivo); (c) o
ranking ja vem pronto no ``eligible_jobs.json`` — a interface so FILTRA e
ORDENA o que existe, nao re-ranqueia (AGENTS.md: "Prefer the simplest
implementation"; "Reuse existing dependencies... before adding new packages").

Fontes (os DOIS caminhos funcionam):

- ``--input``: JSON ranqueado (default ``data/eligible_jobs.json`` do CWD),
  saida direta do ``cli --rank`` — contem ``score``/``score_breakdown``.
  Ordenado por score desc (estavel; o score e o Ja calculado, nunca recomputado).
- ``--db``: SQLite ``jobs.db`` (default como fallback ao JSON ausente) — le
  apenas vagas ATIVAS (``active=1``), sem score (o banco nao tem a coluna):
  ordena por ``last_seen`` desc (mais recentes primeiro). O SQLite e a fonte
  VIVA do historico (first_seen/last_seen alimentados diariamente); o JSON e o
  snapshot ranqueado do ultimo run.

Filtros (3 eixos, aplicados sobre a lista JA pronta — nada e re-ranqueado):

- ``--company``: substring case-insensitive no campo empresa;
- ``--keyword``: substring case-insensitive no TITULO;
- ``--country``: mesma spec do CLI (reusa ``parse_country_spec``/
  ``matches_country`` de ``internship_finder.countries``): ISO alpha-2 em
  lista ("de,at,ch"), "europe", "remote" ou "all". Spec invalida -> erro
  claro (exit 2), como o ``--country`` do CLI (P2 #15).

Uso:

    .venv/bin/python scripts/interface.py                    # data/eligible_jobs.json -> /tmp/interface.html
    .venv/bin/python scripts/interface.py --top 10 --company sap --keyword logistik
    .venv/bin/python scripts/interface.py --db data/jobs.db --country europe --output -   # stdout

A pagina inclui um filtro instantaneo no browser (vanilla JS inline, ~15
linhas, sem framework) que oculta linhas por texto — pura apresentacao sobre
o conjunto ja filtrado; a logica testada de filtro/ordenacao e a do script
(flags acima). ``--output -`` imprime o HTML no stdout; ``--top <= 0`` e spec
de pais invalida -> parser.error (exit 2), mesmo padrao das validacoes do CLI.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.countries import matches_country, parse_country_spec  # noqa: E402

DEFAULT_OUTPUT = Path("/tmp/interface.html")

# Colunas exibidas do SQLite. ``raw`` fica de fora de proposito (JSON grande,
# aninhado — a fonte de verdade e o JSON); o SELECT e de LEITURA apenas.
_DB_COLUMNS = [
    "id", "source", "title", "company", "location", "country", "remote",
    "url", "description", "internship", "posted_at", "collected_at",
    "application_deadline", "external_id", "employment_type", "country_iso",
    "first_seen", "last_seen",
]


def load_json(path: Path) -> list[dict]:
    """Le o snapshot ranqueado (``eligible_jobs.json``) como lista de dicts."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"formato inesperado em {path}: esperado lista de vagas")
    return data


def load_db(path: Path, *, active_only: bool = True) -> list[dict]:
    """Le as vagas ATIVAS do SQLite (fonte viva do historico), sem score.

    Ordena por ``last_seen`` desc (vagas mais recentes primeiro) + ``id``
    (desempate deterministico). ``active_only=False`` le o banco inteiro
    (uso em testes/auditoria).
    """
    where = "WHERE active = 1 " if active_only else ""
    query = (
        "SELECT " + ", ".join(_DB_COLUMNS) + " FROM jobs " + where
        + "ORDER BY last_seen DESC, id"
    )
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def apply_filters(
    jobs: list[dict],
    *,
    company: str | None = None,
    keyword: str | None = None,
    country: str | None = None,
) -> list[dict]:
    """Filtra a lista JA ranqueada por empresa / palavra no titulo / pais.

    Substrings case-insensitive (empresa e palavra). ``country`` usa a MESMA
    spec do CLI (``parse_country_spec``: ISO, 'europe', 'remote', 'all'; None
    ou 'all' = sem filtro). NaO re-ranqueia: apenas mantem o que casa.
    """
    company_q = (company or "").strip().casefold()
    keyword_q = (keyword or "").strip().casefold()
    spec = parse_country_spec(country) if country is not None else None
    out: list[dict] = []
    for j in jobs:
        if company_q and company_q not in str(j.get("company") or "").casefold():
            continue
        if keyword_q and keyword_q not in str(j.get("title") or "").casefold():
            continue
        if spec is not None and not matches_country(
            j.get("country_iso"), j.get("location"), j.get("remote"), spec
        ):
            continue
        out.append(j)
    return out


def sort_ranked(jobs: list[dict]) -> list[dict]:
    """Ordena pelo score JA existente (nunca recomputa): desc, estavel.

    Vagas sem score (caminho SQLite) ficam no final, na ordem recebida
    (``last_seen`` desc). Empates mantem a ordem de entrada (o JSON ja vem
    ordenado pelo ``rank_jobs`` do pipeline — este sort e defensivo).
    """
    def key(j: dict) -> float:
        s = j.get("score")
        return -float(s) if isinstance(s, (int, float)) else float("inf")

    return sorted(jobs, key=key)


def _fmt_score(value) -> str:
    """Score como ``NN.NN``; ausente (SQLite) -> '—'."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_date(value) -> str:
    """Primeiros 10 chars de um timestamp ISO (parte de data) ou '—'."""
    if not value:
        return "—"
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text


def _fmt_bool(value) -> str | None:
    """True/1 -> 'sim'; False/0/None -> None (nao exibe)."""
    if isinstance(value, (bool, int)) and value:
        return "sim"
    return None


# P2.3: schemes aceitos em ``href`` — navegadores executam javascript:/data:/
# no contexto da pagina; aqui so link http/https vira ``<a href>``.
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def _safe_url(value) -> str | None:
    """URL aceitavel para ``href``: somente scheme http/https (nao prefixo).

    Rejeita (retorna ``None``) qualquer outro scheme — javascript:, data:,
    file:, ftp:, mailto:, tel:... — alem de ausencia de scheme (URL relativa)
    e URLs malformadas que o parser rejeita. Comparacao de scheme sem
    diferenciar maiusculas. Nao valida a URL alem do scheme: o destino
    continua passando pelo ``html.escape`` existente (validar scheme ->
    escape -> gerar href).
    """
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


def _breakdown_badges(job: dict) -> str:
    """Badges do ``score_breakdown`` (explica o porque do topo) + extras."""
    parts: list[str] = []
    b = job.get("score_breakdown") or {}
    if isinstance(b, dict):
        labels = {
            "area": "area", "skills": "skills", "language": "idioma",
            "type": "tipo", "location": "local", "penalties": "penal",
        }
        for key in ("area", "skills", "language", "type", "location", "penalties"):
            if key in b:
                try:
                    val = float(b[key])
                except (TypeError, ValueError):
                    parts.append(f"{labels.get(key, key)} {html.escape(str(b[key]))}")
                    continue
                sign = "+" if val >= 0 else ""
                parts.append(f"{labels.get(key, key)} {sign}{val:.1f}")
    if job.get("employment_type"):
        parts.append(f"tipo: {html.escape(str(job['employment_type']))}")
    internship = _fmt_bool(job.get("internship"))
    if internship:
        parts.append("estagio")
    if _fmt_bool(job.get("remote")):
        parts.append("remoto")
    if job.get("application_deadline"):
        parts.append(f"ate {_fmt_date(job['application_deadline'])}")
    return "".join(f'<span class="bdg">{p}</span>' for p in parts)


def _row_html(rank: int, job: dict) -> str:
    """Uma linha da tabela (tudo escapado; URL clicavel, abre em nova aba).

    P2.3: a URL so vira ``href`` apos validar o scheme (somente http/https,
    via ``_safe_url``); scheme rejeitado segue o fluxo de URL vazia — o
    titulo aparece sem link. O escaping HTML continua aplicado depois da
    validacao (validar scheme -> escape -> gerar href).
    """
    title = html.escape(str(job.get("title") or "(sem titulo)"))
    url = html.escape(_safe_url(job.get("url")) or "")
    company = html.escape(str(job.get("company") or "—"))
    location = html.escape(str(job.get("location") or "—"))
    country = html.escape(str(job.get("country_iso") or "—"))
    added = _fmt_date(job.get("first_seen") or job.get("posted_at")
                      or job.get("collected_at"))
    desc = job.get("description")
    desc_snippet = ""
    if desc:
        text = " ".join(str(desc).split())
        if len(text) > 300:
            text = text[:300] + "…"
        desc_snippet = html.escape(text)
    link = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
    details = (
        f'<details><summary>porque deste topo</summary>'
        f'{_breakdown_badges(job)}'
        + (f'<p class="mut desc">{desc_snippet}</p>' if desc_snippet else "")
        + "</details>"
    )
    return (
        "<tr>"
        f'<td class="score">{rank}</td>'
        f'<td class="score">{_fmt_score(job.get("score"))}</td>'
        f"<td>{link}{details}</td>"
        f"<td>{company}</td>"
        f'<td class="loc">{location}</td>'
        f"<td>{country}</td>"
        f'<td class="mut">{added}</td>'
        "</tr>"
    )


def render_html(
    jobs: list[dict],
    *,
    total: int,
    source_label: str,
    filters_desc: list[str],
    generated_at: str,
) -> str:
    """Pagina auto-contida (CSS inline, JS vanilla inline, zero external)."""
    rows = "\n".join(_row_html(i, j) for i, j in enumerate(jobs, 1))
    order_note = (
        "ordem: score (ranking do pipeline)" if jobs and jobs[0].get("score") is not None
        else "ordem: mais recentes (last_seen)"
    )
    chips = ""
    if filters_desc:
        chips = '<div class="meta">' + "".join(
            f'<span class="chip">{html.escape(f)}</span>' for f in filters_desc
        ) + "</div>"
    shown = len(jobs)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Internship Finder — vagas em destaque</title>
<style>
  :root {{ --bg:#f6f7f9; --card:#fff; --ink:#1c2733; --mut:#5c6b7a; --acc:#0b6bcb; --line:#e3e8ee; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:16px/1.45 -apple-system,"Segoe UI",Roboto,Arial,sans-serif; background:var(--bg); color:var(--ink); }}
  main {{ max-width:1080px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:1.35rem; margin:0 0 4px; }}
  header p {{ color:var(--mut); margin:2px 0; font-size:.9rem; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0 6px; }}
  .chip {{ background:#e8eef5; border-radius:999px; padding:3px 10px; font-size:.78rem; color:#33475b; }}
  .toolbar {{ margin:14px 0; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
  input#q {{ flex:1 1 260px; max-width:430px; padding:9px 12px; font-size:.95rem; border:1px solid var(--line); border-radius:8px; }}
  .hint {{ font-size:.8rem; color:var(--mut); }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ background:#eef2f7; font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:var(--mut); }}
  tbody tr:last-child td {{ border-bottom:0; }}
  td.score {{ font-variant-numeric:tabular-nums; font-weight:600; white-space:nowrap; width:52px; }}
  a {{ color:var(--acc); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
  details {{ margin-top:4px; }} summary {{ cursor:pointer; color:var(--mut); font-size:.78rem; }}
  .bdg {{ display:inline-block; font-size:.72rem; background:#f0f4f9; border:1px solid var(--line); border-radius:6px; padding:1px 6px; margin:2px 3px 0 0; color:#33475b; }}
  p.desc {{ margin:6px 0 0; font-size:.82rem; color:#3d4c5c; }}
  .mut {{ color:var(--mut); }} .loc {{ font-size:.85rem; color:#3d4c5c; }}
  footer {{ margin-top:18px; font-size:.75rem; color:var(--mut); }}
  @media (max-width:680px) {{ td:nth-child(5),th:nth-child(5) {{ display:none; }} }}
</style>
</head>
<body>
<main>
  <header>
    <h1>Internship Finder — vagas em destaque</h1>
    <p>{html.escape(source_label)} · gerado em {html.escape(generated_at)} UTC · {html.escape(order_note)}</p>
  </header>
  {chips}
  <div class="toolbar">
    <input id="q" type="search" placeholder="Filtrar por titulo, empresa ou local… (no browser)">
    <span class="hint" id="count">{shown} de {total} vagas</span>
  </div>
  <table>
    <thead><tr><th>#</th><th>score</th><th>vaga</th><th>empresa</th><th>local</th><th>pais</th><th>desde</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <footer>Filtros --company/--keyword/--country sao aplicados na geracao; o campo acima so oculta linhas no browser.</footer>
</main>
<script>
(function () {{
  var q = document.getElementById('q');
  if (!q) {{ return; }}
  var rows = Array.prototype.slice.call(document.querySelectorAll('tbody tr'));
  var counter = document.getElementById('count');
  q.addEventListener('input', function () {{
    var term = q.value.trim().toLowerCase();
    var shown = 0;
    for (var i = 0; i < rows.length; i++) {{
      var hit = rows[i].textContent.toLowerCase().indexOf(term) !== -1;
      rows[i].style.display = hit ? '' : 'none';
      if (hit) {{ shown++; }}
    }}
    if (counter) {{ counter.textContent = term ? shown + ' de ' + rows.length + ' vagas' : rows.length + ' vagas'; }}
  }});
}})();
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Interface simples: top vagas ranqueadas com filtros "
        "(empresa/palavra/pais) e URL clicavel — gera HTML estatico.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default=None,
        help="JSON ranqueado (default: data/eligible_jobs.json do CWD; se "
        "ausente, cai para o default de --db, data/jobs.db)",
    )
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="SQLite jobs.db (vagas ATIVAS, sem score, ordenadas por "
        "last_seen). Informe --input OU --db, nao ambos.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Maximo de vagas exibidas (default: 25; <= 0 -> erro)",
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Filtra por empresa (substring, sem diferenciar maiusculas)",
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help="Filtra por palavra no TITULO (substring, sem diferenciar maiusculas)",
    )
    parser.add_argument(
        "--country",
        default=None,
        help="Filtra por pais na spec do CLI: ISO alpha-2 em lista (ex.: "
        "'de,at,ch'), 'europe', 'remote' ou 'all' (default: sem filtro)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=f"Onde gravar o HTML (default: {DEFAULT_OUTPUT}; '-' = stdout)",
    )
    args = parser.parse_args(argv)

    if args.top <= 0:
        parser.error("--top deve ser > 0")

    # Spec de pais validada cedo (mesma regra do CLI --country, P2 #15).
    if args.country is not None:
        try:
            parse_country_spec(args.country)
        except ValueError as exc:
            parser.error(str(exc))

    if args.input and args.db:
        parser.error("informe apenas um: --input (JSON ranqueado) ou --db (SQLite)")

    input_path = Path(args.input) if args.input else None
    db_path = Path(args.db) if args.db else None

    # Default: arquivos de data/ do CWD, com fallback claro se ausentes.
    if input_path is None and db_path is None:
        candidate_json = Path("data/eligible_jobs.json")
        candidate_db = Path("data/jobs.db")
        if candidate_json.exists():
            input_path = candidate_json
        elif candidate_db.exists():
            db_path = candidate_db
        else:
            parser.error(
                "nada em data/: faltam data/eligible_jobs.json e data/jobs.db — "
                "colete antes (python -m internship_finder.cli --registry) ou "
                "passe --input/--db explicitos"
            )

    if input_path is not None:
        if not input_path.exists():
            parser.error(f"--input nao encontrado: {input_path}")
        jobs = load_json(input_path)
        source_label = f"{input_path} ({len(jobs)} vagas ranqueadas)"
        jobs = sort_ranked(jobs)
    else:
        if not db_path.exists():
            parser.error(f"--db nao encontrado: {db_path}")
        jobs = load_db(db_path)
        source_label = f"{db_path} ({len(jobs)} vagas ativas)"

    filtered = apply_filters(
        jobs, company=args.company, keyword=args.keyword, country=args.country
    )
    top_jobs = filtered[: args.top]

    filters_desc: list[str] = []
    if args.company:
        filters_desc.append(f"empresa contem '{args.company}'")
    if args.keyword:
        filters_desc.append(f"palavra no titulo: '{args.keyword}'")
    if args.country:
        filters_desc.append(f"pais: {args.country}")

    page = render_html(
        top_jobs,
        total=len(filtered),
        source_label=source_label,
        filters_desc=filters_desc,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    out = "-" if args.output == "-" else Path(args.output or DEFAULT_OUTPUT)
    if out == "-":
        sys.stdout.write(page)
    else:
        out.write_text(page, encoding="utf-8")
        print(f"interface gerada: {out.resolve()} ({len(top_jobs)} de {len(filtered)} vagas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
