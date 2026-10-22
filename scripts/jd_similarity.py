#!/usr/bin/env python3
"""F97 — jd-similarity: reuse | reuse_with_edits | regenerate antes de reusar carta/CV.

Problema (ITEM 10 da delegação; REGISTRO-AVALIACOES 13–18/10): 5 pacotes
Lidl simultâneos (SAP BI, Projete, Int BI, Lieferantenentwicklung,
Preismanagement) — mesmo empregador, JDs irmãos. Risco: carta genérica
"one-size-fits-all" que serve para qualquer vaga Lidl. Critério
career-ops: "could this letter appear in any cover letter for any
company? If yes, rewrite it."

O que faz (offline, determinístico, stdlib pura, SEM LLM):
  1. Tokeniza os JDs (lowercase, ß→ss, [a-zäöü0-9]+, len>=2, sem
     stopwords DE/EN, sem números puros).
  2. Remove o boilerplate do empregador: runs VERBATIM comuns aos dois
     JDs (>= RUN_MIN_TOKENS=6 tokens contíguos idênticos — um diff). O
     template Lidl (Einleitung + Wir bieten) é idêntico palavra a palavra
     nos 5 JDs medidos: ~70% da cobertura de tokens de cada um.
  3. coverage = fração de tokens coberta por esses runs (a MENOR das duas
     direções). JDs essencialmente iguais (re-post, espelho, edição
     menor) => coverage >= 0.90 => ``reuse``.
  4. Jaccard do RESTO (o que sobra depois do boilerplate) => a carta
     precisa citar o conteúdo específico: ``reuse_with_edits`` quando
     >= 0.176, ``regenerate`` abaixo.
  5. ``regenerate`` (e ``reuse_with_edits``) listam os tópicos distintos
     — os tokens de conteúdo que o novo JD tem e o de referência não.

Limiares MEDIOS no Passo 0 (fixtures Lidl ×5, arquivo
``fixtures/f97/``; tabela completa no ``scripts/test_f97.py``):

  par (Controlling International)   J_resto   veredito
  projete  × int_bi                   0.233   reuse_with_edits
  sap_bi   × int_bi                   0.196   reuse_with_edits
  sap_bi   × projete                  0.188   reuse_with_edits
  sap_bi   × preis                    0.165   regenerate   <- spec: divergem
  projete  × liefer                   0.085   regenerate
  coverage dos pares irmãos: 0.66–0.73 (template) | idênticos: 1.000
  -> REUSE_COVERAGE = 0.90 (folga 2.6× sobre o template)
  -> REUSE_WITH_EDITS_JACCARD = 0.176 (média do gap 0.165 | 0.188)

Uso (da raiz do repo):
  # 2+ JDs por arquivo de texto (título na 1ª linha recomendado):
  python3 scripts/jd_similarity.py \\
      --jd-file fixtures/f97/lidl_sap_bi.txt \\
      --jd-file fixtures/f97/lidl_preismanagement.txt

  # por job-id do eligible_jobs.json (vaga fora do snapshot atual?
  # aponte --input para data/archive/<ts>/eligible_jobs.json):
  python3 scripts/jd_similarity.py --job-id "<id-1>" --job-id "<id-2>"

  # --json para saída de máquina; --max-topics N; --run-min N (calibração
  # — mudar invalida os limiares medidos).

Sinais de contexto:
  - Empregadores diferentes (alias F66 + identidade de tokens) => aviso
    ⚠ — reuso de carta ENTRE empresas é fora do escopo (a carta deve ser
    reescrita por princípio). ``--jd-file`` é texto puro sem metadado =>
    sinal ausente (null), nunca aviso falso.
  - JD sem texto (description vazia — ex.: praktikum_info no dataset) =>
    excluído com aviso, NUNCA comparado no escuro.
  - |J_resto - limiar| <= BORDERLINE_BAND => marcado "borderline"
    (banda medida honesta; fronteira é difusa por natureza).

CONTRATO: o veredito é SINAL pro dono, NUNCA gate — a carta é decisão
dele (AGENTS.md). Exit 0 para qualquer veredito; 2 = erro de uso
(args/lookup/JDs insuficientes); 1 = falha inesperada.

Zero rede, zero LLM, zero dependências além da stdlib; data/ intocada.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Constantes de calibração (Passo 0 — fixtures Lidl ×5; ver docstring).
# ---------------------------------------------------------------------------

#: Runs verbatim mais curtos que isto NÃO são boilerplate (r4/r5 medidos
#: quebram a separação trio×cross; r7+ deixam template escapar — grid no
#: relatório da fase). NÃO mudar sem re-medir os limiares.
RUN_MIN_TOKENS = 6

#: Fração de tokens coberta por runs comuns (mínimo das 2 direções) acima
#: da qual os JDs são "o mesmo anúncio" (re-post/espelho/edição menor).
#: Template Lidl mede 0.66–0.73; quase-idêntico 0.997; idêntico 1.000.
REUSE_COVERAGE = 0.90

#: Jaccard do resto (pós-boilerplate) acima do qual a carta da vaga-irmã
#: serve com edições. Gap medido: cross máx 0.165 | trio mín 0.188.
REUSE_WITH_EDITS_JACCARD = 0.176

#: Banda de fronteira: |J - limiar| <= isto => "borderline" no output.
BORDERLINE_BAND = 0.015

#: Mínimo de caracteres de texto para um JD ser comparável.
MIN_JD_CHARS = 40

#: Stopwords DE/EN — lista EXATA usada na medição do Passo 0 (mudar uma
#: palavra aqui deslocamente os limiares medidos; re-medir se editar).
STOPWORDS = frozenset(
    "und oder aber der die das den dem des ein eine einen einem eines "
    "ist sind war waren sein seine seinen ihrem ihrer für mit von zu "
    "zum zur im in an am auf aus bei nach über unter vor durch um als "
    "wie auch noch nur schon sehr mehr viele viel hier dort wir ihr "
    "euch uns unser unsere sie er es man sich nicht kein keine da "
    "dabei damit davon jeweils sowie ob denn the and or for with from "
    "you your our their this that these those will can are was were "
    "be been being have has had do does did not but about into within "
    "across".split()
)

# ---------------------------------------------------------------------------
# Tokenização
# ---------------------------------------------------------------------------


def raw_tokens(text: str) -> list[str]:
    """Tokens crus (lowercase, ß→ss): a base do diff de runs verbatim.

    Números entram (o boilerplate também é feito de números — "1.300");
    são filtrados só na camada de conteúdo.
    """
    return re.findall(r"[a-zäöü0-9]+", str(text).lower().replace("ß", "ss"))


def content_tokens(raw: list[str]) -> list[str]:
    """Tokens de CONTEÚDO: len>=2, sem stopwords DE/EN, sem dígitos puros."""
    return [
        t
        for t in raw
        if len(t) >= 2 and not t.isdigit() and t not in STOPWORDS
    ]


def jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard de conjuntos. Ambos vazios => 1.0 (idênticos por convenção)."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


# ---------------------------------------------------------------------------
# Boilerplate: runs verbatim comuns (diff par a par)
# ---------------------------------------------------------------------------


def strip_common_runs(
    ta: list[str], tb: list[str], run_min: int = RUN_MIN_TOKENS
) -> tuple[list[str], list[str], float]:
    """Cobre com runs contíguos verbatim >= run_min tokens.

    Greedy da esquerda para a direita sobre ``ta``: em cada posição acha o
    MAIOR match partindo dali em ``tb`` (índice invertido por token); run
    >= run_min cobre os dois lados. Devolve (resto_a, resto_b,
    coverage), onde coverage é a MENOR fração coberta das duas direções
    (sameness simétrico: reuso exige que ambos os lados sejam quase
    inteiramente comuns).
    """
    index: dict[str, list[int]] = {}
    for j, tok in enumerate(tb):
        index.setdefault(tok, []).append(j)
    covered_a = [False] * len(ta)
    covered_b = [False] * len(tb)
    i = 0
    while i < len(ta):
        best_len, best_j = 0, -1
        for j in index.get(ta[i], ()):
            length = 0
            while (
                i + length < len(ta)
                and j + length < len(tb)
                and ta[i + length] == tb[j + length]
            ):
                length += 1
            if length > best_len:
                best_len, best_j = length, j
        if best_len >= run_min:
            for k in range(best_len):
                covered_a[i + k] = True
                covered_b[best_j + k] = True
            i += best_len
        else:
            i += 1
    rest_a = [t for t, c in zip(ta, covered_a) if not c]
    rest_b = [t for t, c in zip(tb, covered_b) if not c]
    cov_a = sum(covered_a) / len(ta) if ta else 1.0
    cov_b = sum(covered_b) / len(tb) if tb else 1.0
    return rest_a, rest_b, min(cov_a, cov_b)


# ---------------------------------------------------------------------------
# Veredito
# ---------------------------------------------------------------------------

REUSE = "reuse"
REUSE_WITH_EDITS = "reuse_with_edits"
REGENERATE = "regenerate"


def verdict(coverage: float, j_rest: float) -> tuple[str, bool]:
    """(veredito, borderline). SINAL, nunca gate.

    reuse              coverage >= REUSE_COVERAGE — mesmo anúncio.
    reuse_with_edits   J_resto >= REUSE_WITH_EDITS_JACCARD — irmãos.
    regenerate         abaixo — domínios distintos.
    """
    if coverage >= REUSE_COVERAGE:
        return REUSE, False
    if j_rest >= REUSE_WITH_EDITS_JACCARD:
        return REUSE_WITH_EDITS, abs(j_rest - REUSE_WITH_EDITS_JACCARD) <= BORDERLINE_BAND
    return REGENERATE, abs(j_rest - REUSE_WITH_EDITS_JACCARD) <= BORDERLINE_BAND


#: Filtro extra SÓ na listagem de tópicos (apresentação — o Jaccard usa
#: STOPWORDS congeladas da medição; estas palavras não são citáveis numa
#: carta, então não poluem a lista que o dono lê).
TOPIC_STOPWORDS = STOPWORDS | frozenset(
    "du dich dein deine deinen dem den unser unsere unseres unseren "
    "unterstützt unterstütze unterstützung gestaltest einbringen "
    "mitarbeit erstellung aufbereitung vorbereitung durchführung "
    "betreuung umsetzung bereich sofort februar märz monate monat "
    "woche wochen gerne heute aktuell bestehende bestehenden "
    "verschiedene verschiedenen vielseitige vielseitigen zusammenarbeit "
    "idealerweise".split()
)


def distinctive_topics(
    candidate: list[str], reference: list[str], limit: int = 8
) -> list[str]:
    """Tópicos que a carta do candidato deve citar e o de referência não tem.

    Tokens de conteúdo presentes no candidato e ausentes no de referência,
    ranqueados por frequência no candidato (desc) e posição da 1ª ocorrência
    (asc) — determinístico. ``TOPIC_STOPWORDS`` sai da listagem (palavra
    não-citável); o MÉTRICO continua com STOPWORDS congeladas.
    """
    ref_set = set(reference)
    counts: dict[str, int] = {}
    first_pos: dict[str, int] = {}
    for pos, tok in enumerate(candidate):
        if tok in ref_set or tok in TOPIC_STOPWORDS:
            continue
        counts[tok] = counts.get(tok, 0) + 1
        first_pos.setdefault(tok, pos)
    ranked = sorted(counts, key=lambda t: (-counts[t], first_pos[t], t))
    return ranked[:limit]


# ---------------------------------------------------------------------------
# Empregador (alias F66 fail-closed, local — sem importar src/)
# ---------------------------------------------------------------------------

DEFAULT_ALIASES_PATH = ROOT / "config" / "dedup_company_aliases.json"


def load_company_aliases(path: Path | None = None) -> dict[str, str]:
    """Mapa de aliases F66 (casefold -> canônico). Fail-closed: qualquer
    problema => {} (o sinal de mesmo-empregador degrada, nunca crasha)."""
    target = Path(path) if path is not None else DEFAULT_ALIASES_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    aliases = raw.get("aliases") if isinstance(raw, dict) else None
    if not isinstance(aliases, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in aliases.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        k, v = key.strip(), value.strip()
        if k and v and k.casefold() != v.casefold():
            out[k.casefold()] = v
    return out


def company_key(company: str | None, aliases: dict[str, str]) -> frozenset[str]:
    """Identidade de empresa: alias exato casefold + tokens de [a-z0-9]."""
    text = str(company or "").strip()
    text = aliases.get(text.casefold(), text)
    return frozenset(re.findall(r"[a-z0-9]+", text.casefold()))


def same_employer(
    company_a: str | None, company_b: str | None, aliases: dict[str, str]
) -> bool | None:
    """True/False quando ambos os empregadores são CONHECIDOS; None quando
    algum lado não tem metadado de empresa (--jd-file é texto puro)."""
    if not str(company_a or "").strip() or not str(company_b or "").strip():
        return None
    ka, kb = company_key(company_a, aliases), company_key(company_b, aliases)
    return bool(ka) and ka == kb


# ---------------------------------------------------------------------------
# Documentos de entrada
# ---------------------------------------------------------------------------


@dataclass
class JdDoc:
    label: str
    company: str | None
    title: str | None
    text: str
    raw: list[str] = field(default_factory=list)
    content: list[str] = field(default_factory=list)


def _jd_text(job: dict) -> str:
    """title + description do registro do eligible (description hydratada)."""
    parts = [str(job.get("title") or "").strip()]
    desc = job.get("description")
    if isinstance(desc, str) and desc.strip():
        parts.append(desc.strip())
    return "\n".join(p for p in parts if p)


def load_jobs(path: Path) -> dict[str, dict]:
    """Carrega eligible_jobs.json (lista ou {"jobs": [...]}) por id exato."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("jobs") or []
    if not isinstance(data, list):
        raise ValueError(f"{path}: formato inesperado (esperado lista)")
    return {str(job.get("id")): job for job in data if isinstance(job, dict) and job.get("id")}


def resolve_job_id(arg: str, jobs: dict[str, dict]) -> dict:
    """Lookup por id EXATO; senão substring ÚNICO (conveniência pro dono)."""
    if arg in jobs:
        return jobs[arg]
    matches = [jid for jid in jobs if arg.casefold() in jid.casefold()]
    if len(matches) == 1:
        return jobs[matches[0]]
    if not matches:
        print(
            f"[jd-similarity] job-id não encontrado: {arg!r} "
            f"({len(jobs)} vagas carregadas; use --input para outro snapshot)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(
        f"[jd-similarity] job-id ambíguo: {arg!r} casa "
        + ", ".join(matches[:3])
        + (f" … ({len(matches)} no total)" if len(matches) > 3 else ""),
        file=sys.stderr,
    )
    raise SystemExit(2)


def build_docs(args: argparse.Namespace) -> tuple[list[JdDoc], list[str]]:
    """Monta os JdDocs a partir de --job-id/--jd-file. Devolve (docs, avisos)."""
    docs: list[JdDoc] = []
    warnings: list[str] = []

    if args.job_id:
        jobs = load_jobs(Path(args.input))
        for jid in args.job_id:
            job = resolve_job_id(jid, jobs)
            docs.append(
                JdDoc(
                    label=str(job.get("id")),
                    company=job.get("company"),
                    title=job.get("title"),
                    text=_jd_text(job),
                )
            )

    for path_str in args.jd_file:
        path = Path(path_str)
        text = path.read_text(encoding="utf-8").strip()
        first_line = text.splitlines()[0].strip() if text else ""
        docs.append(
            JdDoc(
                label=path.stem,
                company=None,
                title=first_line if len(first_line) <= 120 else None,
                text=text,
            )
        )

    # JDs sem texto comparável são excluídos com aviso (nunca no escuro).
    usable: list[JdDoc] = []
    for doc in docs:
        if len(doc.text) < MIN_JD_CHARS:
            warnings.append(
                f"JD sem texto comparável (<{MIN_JD_CHARS} chars), excluído: "
                f"{doc.label} — abrir o anúncio e salvar o JD num arquivo"
            )
            continue
        doc.raw = raw_tokens(doc.text)
        doc.content = content_tokens(doc.raw)
        usable.append(doc)
    return usable, warnings


# ---------------------------------------------------------------------------
# Comparação par a par
# ---------------------------------------------------------------------------


def compare_pair(
    doc_a: JdDoc, doc_b: JdDoc, aliases: dict[str, str], max_topics: int,
    run_min: int = RUN_MIN_TOKENS,
) -> dict:
    rest_a, rest_b, coverage = strip_common_runs(doc_a.raw, doc_b.raw, run_min)
    cont_a, cont_b = content_tokens(rest_a), content_tokens(rest_b)
    j_rest = jaccard(cont_a, cont_b)
    verdict_str, borderline = verdict(coverage, j_rest)
    same = same_employer(doc_a.company, doc_b.company, aliases)
    return {
        "a": doc_a.label,
        "b": doc_b.label,
        "company_a": doc_a.company,
        "company_b": doc_b.company,
        "same_employer": same,
        "coverage": round(coverage, 4),
        "jaccard_rest": round(j_rest, 4),
        "run_min_tokens": RUN_MIN_TOKENS,
        "verdict": verdict_str,
        "borderline": borderline,
        "topics_for_b": distinctive_topics(cont_b, cont_a, max_topics),
        "topics_for_a": distinctive_topics(cont_a, cont_b, max_topics),
    }


def compare_all(
    docs: list[JdDoc], aliases: dict[str, str], max_topics: int,
    run_min: int = RUN_MIN_TOKENS,
) -> list[dict]:
    pairs: list[dict] = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            pairs.append(
                compare_pair(docs[i], docs[j], aliases, max_topics, run_min)
            )
    return sorted(pairs, key=lambda p: (p["a"], p["b"]))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jd_similarity.py",
        description=(
            "F97 — compara 2+ JDs do MESMO empregador antes de reusar "
            "carta/CV: reuse | reuse_with_edits | regenerate (sinal, nunca gate)."
        ),
    )
    parser.add_argument(
        "--input",
        default="data/eligible_jobs.json",
        help="eligible_jobs.json (default) — ou um snapshot data/archive/<ts>/ (JSON, lido apenas)",
    )
    parser.add_argument(
        "--job-id",
        action="append",
        default=[],
        metavar="ID",
        help="id da vaga no --input (exato ou substring único); repetível",
    )
    parser.add_argument(
        "--jd-file",
        action="append",
        default=[],
        metavar="PATH",
        help="arquivo de texto com o JD (título na 1ª linha recomendado); repetível",
    )
    parser.add_argument(
        "--aliases",
        default=None,
        help="mapa de aliases de empresa (default: config/dedup_company_aliases.json)",
    )
    parser.add_argument(
        "--max-topics",
        type=int,
        default=8,
        help="máximo de tópicos distintos listados por lado (default 8)",
    )
    parser.add_argument(
        "--run-min",
        type=int,
        default=RUN_MIN_TOKENS,
        help=(
            "tamanho mínimo do run verbatim = boilerplate "
            "(CALIBRAÇÃO: mudar invalida os limiares medidos)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="saída JSON de máquina (stdout)",
    )
    return parser


def _fmt_pair(pair: dict) -> str:
    lines = []
    same = "  ⚠ empregadores diferentes" if pair["same_employer"] is False else ""
    bord = "  [borderline]" if pair["borderline"] else ""
    lines.append(
        f"{pair['a']}  ×  {pair['b']}: {pair['verdict']}{bord}{same}"
    )
    lines.append(
        f"    coverage={pair['coverage']:.3f}  J_resto={pair['jaccard_rest']:.3f}"
    )
    if pair["topics_for_b"]:
        lines.append(
            f"    tópicos que a carta p/ '{pair['b']}' deve citar: "
            + ", ".join(pair["topics_for_b"])
        )
    if pair["topics_for_a"]:
        lines.append(
            f"    tópicos exclusivos de '{pair['a']}': "
            + ", ".join(pair["topics_for_a"])
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if len(args.job_id) + len(args.jd_file) < 2:
        print(
            "[jd-similarity] informe 2+ JDs: --job-id (eligible) e/ou --jd-file (texto)",
            file=sys.stderr,
        )
        return 2

    try:
        docs, warnings = build_docs(args)
    except (OSError, ValueError) as exc:
        print(f"[jd-similarity] {exc}", file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"[aviso] {warning}", file=sys.stderr)

    if len(docs) < 2:
        print(
            "[jd-similarity] JDs comparáveis insuficientes (precisa de 2+ com texto)",
            file=sys.stderr,
        )
        return 2

    aliases = load_company_aliases(
        Path(args.aliases) if args.aliases else None
    )
    pairs = compare_all(docs, aliases, args.max_topics, args.run_min)

    counts: dict[str, int] = {}
    for pair in pairs:
        counts[pair["verdict"]] = counts.get(pair["verdict"], 0) + 1

    if args.json:
        print(
            json.dumps(
                {
                    "docs": [
                        {
                            "label": d.label,
                            "company": d.company,
                            "title": d.title,
                            "chars": len(d.text),
                        }
                        for d in docs
                    ],
                    "thresholds": {
                        "reuse_coverage": REUSE_COVERAGE,
                        "reuse_with_edits_jaccard": REUSE_WITH_EDITS_JACCARD,
                        "run_min_tokens": args.run_min,
                    },
                    "pairs": pairs,
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0

    print(
        f"F97 jd-similarity — {len(docs)} JDs, {len(pairs)} par(es) "
        f"(limiar reuse_with_edits J>={REUSE_WITH_EDITS_JACCARD}; "
        f"reuse coverage>={REUSE_COVERAGE}; veredito = SINAL, nunca gate)"
    )
    for pair in pairs:
        print(_fmt_pair(pair))
    summary = ", ".join(f"{v}× {k}" for k, v in sorted(counts.items()))
    print(f"resumo: {summary or 'nenhum par'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
