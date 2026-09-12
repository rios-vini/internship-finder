"""Testes standalone — coverage.py robusto com zero vagas elegiveis.

``eligible_jobs.json = []`` e um estado VALIDO do pipeline: o CLI sai com
exit 1 quando o filtro nao acha vagas (``return 0 if selected else 1`` em
``cli.py``) e a analise de coverage roda logo em seguida sobre o JSON vazio.
Antes da correcao, ``by_company.most_common(1)[0][1]`` lancava ``IndexError``
com o Counter vazio.

Blocos:

1. **Zero eligible** — ``main(jobs=[], eligible=[])`` termina sem ``IndexError``
   (exit 0) e o relatorio e coerente: funil zerado, 0 empresas/0 tenants, top1=0
   (maximo sobre conjunto vazio), percentuais viram ``-`` (indefinidos com total
   zero) e NENHUMA empresa e listada como representada. Inclui a variante
   realista do exit 1: ``jobs`` nao vazio + ``eligible=[]`` (coletou, filtros/
   dedup zeraram) — também nao crasha.
2. **Uma vaga** — entrada minima: caso normal intacto (top1 = 100,0%).
3. **Varias empresas** — vagas distribuídas (3/2/1) e o calculo de top1/top3/
   top5 continua exatamente o ``most_common`` de sempre.
4. **Empresa unica** — todas as vagas da mesma empresa: ``most_common(1)[0][1]``
   continua correto com pelo menos uma entrada.

Nao depende de ``data/`` nem de rede: injeta ``jobs``/``eligible`` direto em
``coverage.main`` (nova assinatura com defaults) e captura o stdout do
relatorio — o artefato verificado e o relatorio impresso.
Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_coverage.py
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# scripts/coverage.py (sys.path insert acima; o pacote PyPI `coverage` NAO
# esta no venv — conferido). O modulo insere src/ e importa filters.sozinho.
import coverage  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILURES.append(name)


def make_job(company: str, n: int, source: str) -> dict:
    """Dict minimo que PASSa a cascata real (tipo estudante + area + DE)."""
    return {
        "id": f"{company}-{n}",
        "source": source,
        "title": "Intern Supply Chain — Stuttgart",
        "company": company,
        "url": f"https://example.com/{company}/{n}",
        "country_iso": "de",
    }


def run_report(jobs: list[dict], eligible: list[dict]) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        rc = coverage.main(jobs=jobs, eligible=eligible)
    return rc, out.getvalue()


def section(lines: list[str], header: str) -> list[str]:
    """Fatia do relatorio entre um cabecalho ``=== X ===`` e o proximo."""
    start = next(i for i, l in enumerate(lines) if l == header)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("===")),
        len(lines),
    )
    return lines[start:end]


def has_line(section_lines: list[str], text: str) -> bool:
    """Alguma linha da secao contem ``text`` (substring; linhas tem prefixo)."""
    return any(text in l for l in section_lines)


def company_rows(section_lines: list[str]) -> list[str]:
    """Linhas de empresa: entre ``bruto:`` e ``contribuicao`` (sem cabecalhos)."""
    start = next(i for i, l in enumerate(section_lines) if l.startswith("  bruto:"))
    end = next(
        i for i, l in enumerate(section_lines) if l.startswith("  contribuicao")
    )
    return [l for l in section_lines[start + 1 : end] if l.strip()]


def company_row(n: int, company: str) -> str:
    """Formato exato da linha de empresa (``f\"    {n:>4}  {company}\"``)."""
    return f"    {n:>4}  {company}"


# ---------------------------------------------------------------------------
# 1. Zero eligible ([]): sem IndexError, metricas coerentes
# ---------------------------------------------------------------------------


def test_zero_eligible() -> None:
    print("== 1. Zero eligible: [] nao lanca IndexError e reporta metricas nulas ==")
    rc, out = run_report([], [])
    check("1a. execucao termina sem IndexError (exit 0)", rc == 0, f"rc={rc}")
    lines = out.splitlines()

    funil = section(lines, "=== Funil (--country de) ===")
    check("1b. funil zerado", has_line(funil, "raw coletadas        : 0")
          and has_line(funil, "eligible (pos-dedup) : 0")
          and has_line(funil, "ranked               : 0"))

    empresas = section(lines, "=== Empresas (eligible) ===")
    check("1c. 0 empresas | 0 tenants (source)",
          has_line(empresas, "0 empresas distintas | 0 tenants (source)"))
    check("1d. top1 = 0 -> percentuais indefinidos viram '-'",
          has_line(empresas, "contribuicao das maiores: top1 - | top3 - | top5 -"),
          "linha esperada nao encontrada")
    check("1e. nenhuma empresa reportada como representada",
          not company_rows(empresas), f"rows={company_rows(empresas)}")

    ats = section(lines, "=== ATS (eligible) ===")
    check("1f. ATS sem linhas",
          not [l for l in ats if l.strip() and not l.startswith("===")], f"{ats}")

    paises = section(lines, "=== Paises (eligible) ===")
    check("1g. paises: 0 vagas, localizacao desconhecida '-'",
          has_line(paises, "None/localizacao desconhecida: 0 (-)"))

    # Variante realista do exit 1 do pipeline: coletou vagas, filtros/dedup
    # zeraram -> eligible_jobs.json = [] e o bruto NAO esta vazio.
    jobs = [make_job(f"C{i}", i, "successfactors:jobs") for i in range(1, 4)]
    rc2, out2 = run_report(jobs, [])
    check("1h. jobs nao vazio + eligible=[] tambem nao crasha (exit 0)",
          rc2 == 0, f"rc={rc2}")
    empresas2 = section(out2.splitlines(), "=== Empresas (eligible) ===")
    check("1i. idem: 0 empresas e nenhuma linha de empresa",
          has_line(empresas2, "0 empresas distintas | 0 tenants (source)")
          and not company_rows(empresas2))


# ---------------------------------------------------------------------------
# 2. Uma vaga (entrada minima): caso normal intacto
# ---------------------------------------------------------------------------


def test_one_job() -> None:
    print("== 2. Uma vaga: caso normal continua exato ==")
    job = make_job("ZF", 1, "successfactors:jobs")
    rc, out = run_report([job], [job])
    check("2a. exit 0", rc == 0, f"rc={rc}")
    lines = out.splitlines()
    empresas = section(lines, "=== Empresas (eligible) ===")
    check("2b. 1 empresa | 1 tenant",
          has_line(empresas, "1 empresas distintas | 1 tenants (source)"))
    rows = company_rows(empresas)
    check("2c. empresa listada com 1 vaga", rows == [company_row(1, "ZF")],
          f"rows={rows}")
    check("2d. top1 = 1 vaga = 100,0%",
          has_line(empresas, "contribuicao das maiores: top1 100.0% | top3 100.0% | top5 100.0%"))
    check("2e. funil coerente (jobs == eligible -> dedup 0)",
          has_line(section(lines, "=== Funil (--country de) ==="), "dedup removidas      : 0"))


# ---------------------------------------------------------------------------
# 3. Varias empresas: distribuicao 3/2/1, calculo atual intacto
# ---------------------------------------------------------------------------


def test_multiple_companies() -> None:
    print("== 3. Varias empresas (3/2/1): top1/top3/top5 = most_common exato ==")
    jobs = [
        make_job("SAP", 1, "successfactors:jobs"),
        make_job("SAP", 2, "successfactors:jobs"),
        make_job("SAP", 3, "successfactors:jobs"),
        make_job("BoschGroup", 1, "successfactors:jobs"),
        make_job("BoschGroup", 2, "successfactors:jobs"),
        make_job("ZF", 1, "smartrecruiters:zf"),
    ]
    rc, out = run_report(jobs, jobs)
    check("3a. exit 0", rc == 0, f"rc={rc}")
    lines = out.splitlines()
    empresas = section(lines, "=== Empresas (eligible) ===")
    check("3b. 3 empresas distintas | 2 tenants (source)",
          has_line(empresas, "3 empresas distintas | 2 tenants (source)"))
    rows = company_rows(empresas)
    counts = [int(re.match(r"\s+(\d+)", l).group(1)) for l in rows]
    check("3c. ordem desc e totais (3 SAP, 2 BoschGroup, 1 ZF)",
          counts == [3, 2, 1], f"counts={counts}")
    check("3d. top1 50.0% | top3 100.0% | top5 100.0%",
          has_line(empresas, "contribuicao das maiores: top1 50.0% | top3 100.0% | top5 100.0%"))
    funil = section(lines, "=== Funil (--country de) ===")
    check("3e. funil coerente (6 eligible, dedup 0)",
          has_line(funil, "eligible (pos-dedup) : 6")
          and has_line(funil, "dedup removidas      : 0"))


# ---------------------------------------------------------------------------
# 4. Empresa unica: most_common(1)[0][1] correto com >= 1 entrada
# ---------------------------------------------------------------------------


def test_single_company() -> None:
    print("== 4. Empresa unica: todas as vagas da mesma empresa ==")
    jobs = [make_job("SAP", i, "successfactors:jobs") for i in range(1, 5)]
    rc, out = run_report(jobs, jobs)
    check("4a. exit 0", rc == 0, f"rc={rc}")
    empresas = section(out.splitlines(), "=== Empresas (eligible) ===")
    check("4b. 1 empresa | 1 tenant",
          has_line(empresas, "1 empresas distintas | 1 tenants (source)"))
    rows = company_rows(empresas)
    check("4c. 4 vagas da mesma empresa, top1 = 4",
          rows == [company_row(4, "SAP")] and
          has_line(empresas, "contribuicao das maiores: top1 100.0% | top3 100.0% | top5 100.0%"),
          f"rows={rows}")


def main() -> int:
    print("== test_coverage: coverage.py com zero vagas elegiveis (e casos normais) ==")
    test_zero_eligible()
    test_one_job()
    test_multiple_companies()
    test_single_company()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())