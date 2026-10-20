"""Testes F73 — doc-sync D1: drift docs↔código = suíte vermelha (roadmap v5).

A classe de drift docs↔código foi provada 2x (auditoria 11/10 corrigiu
101→110 em docs vivos; o registry foi a 127 e os docstrings de
``dataset_source.py``/``ranking.py`` seguiram citando 101 — a spec F73
fechou a classe). Este contract re-deriva a VERDADE do código vivo e
compara com as afirmações machine-checkable dos docs VIVOS: drift futuro
= suíte vermelha, não revisão manual.

Fontes de verdade (100% OFFLINE, zero rede, ``data/`` intocada):

1. ``len(SEED)`` (registry.py) — contagem de empresas citada nos
   docstrings de dataset_source.py/ranking.py, no header do seed, no
   README (4 menções EN+PT), em ``docs/architecture.md`` e
   ``docs/README-operacional.md`` (2 menções);
2. ``len({ats distintos do SEED})`` — "N ATS platforms" do README
   (3 menções). O avature do override F58 é FONTE MORTA reescrita em
   runtime, não plataforma declarada do registry;
3. ``len(tests=...)`` do ci.yml — "N CI test suites" do README
   (1 menção) + membership de ``test_f73`` no MESMO array;
4. janela medida do refresh do upstream — "~14:30 UTC" (manifest
   storage.stapply.ai/jobhive/v1/manifest.json, generated_at 14:30:04Z,
   medido 19/10/2026; o "~05h UTC" era stale) citada em
   dataset_source.py, direct_fetch.py, collectors/ats_scraper.py e
   README ("refreshed daily ~14:30 UTC", 2 menções). O teste NÃO pode
   re-medir offline: a constante ``MEASURED_UPSTREAM_UTC`` é a âncora —
   re-medir = re-ancorar a constante + os 5 sites no mesmo commit.

INVENTÁRIO é contract: o número de SITES por afirmação é fixo (contado
por regex). Adicionar/remover site de claim = editar este teste no mesmo
commit; site esperado que sumiu = FAIL "menção parseável ausente", nunca
skip silencioso.

NÃO pinados POR DESIGN (alvos móveis externos — re-âncora em re-medição,
não em suíte vermelha): volume do upstream (~5,1M jobs / 80.390
empresas / 63 fontes — conferidos contra stats do manifest 19/10),
contagem de commits e snapshot do funil do README (claims dated),
tau do benchmark (versão congelada v1, +0.651). Registro histórico
DATADO em docstring (ex.: "13.482 brutas" do ranking.py, "101 de 150"
da Fase D no present_official.py) não é claim vivo e fica fora do
escopo.

AGENTS.md (regras P0 operacionais) é deliverable irmão desta fase: seu
contract de tokens P0 entra neste teste no MESMO commit do apêndice.

Uso:  .venv/bin/python scripts/test_f73.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import internship_finder.dataset_source as dataset_source  # noqa: E402
import internship_finder.ranking as ranking  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402

FAILURES: list[str] = []

# Janela medida do refresh diário do upstream (spec F73; manifest
# generated_at 14:30:04Z em 19/10/2026 — o "~05h UTC" era stale).
MEASURED_UPSTREAM_UTC = "14:30"

N_COMPANIES = len(SEED)
N_ATS = len({e.ats for e in SEED if e.ats})

# --- arquivos vivos escaneados (docs/historico/ = registro congelado, fora) ---

README = "README.md"
AGENTS = "AGENTS.md"
HOUR_SRC_FILES = (
    "src/internship_finder/dataset_source.py",
    "src/internship_finder/direct_fetch.py",
    "src/internship_finder/collectors/ats_scraper.py",
)

# --- detectores (puros: mesmos validadores dos arquivos reais e dos controles) ---

_RE_REGISTRY_DS = re.compile(r"(?:registry|lista) de (\d+) empresas")
_RE_SEED_HEADER = re.compile(r"Seed: (\d+) empresas operacionais")
_RE_COMPANIES_EN = re.compile(r"(\d+) companies")
_RE_COMPANIES_PT = re.compile(r"registry de (\d+) empresas")
_RE_COMPANIES_TABLE = re.compile(r"\*\*(\d+) / (\d+)\*\* \| curated companies")
_RE_ARCH = re.compile(r"(\d+) empresas de coleta")
_RE_OPER_1 = re.compile(r"(\d+) empresas operacionais")
_RE_OPER_2 = re.compile(r"(\d+) empresas em codigo")
_RE_ATS_PLATFORMS = re.compile(r"(\d+) ATS platforms")
_RE_CI_SUITES = re.compile(r"\*\*(\d+)\*\* \| CI test suites")
_RE_HOUR_EN = re.compile(r"refreshed daily ~(\d{1,2}:\d{2}) UTC")
_RE_HOUR_SRC = re.compile(r"~(\d{1,2}[:h]\d{2}) UTC")
_RE_STALE_HOUR = re.compile(r"~\s*05[h:]")


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def docstring_registry_violations(docstring: str, expected: int) -> list[str]:
    """Docstrings citam 'registry|lista de N empresas' == len(SEED)."""
    found = [int(n) for n in _RE_REGISTRY_DS.findall(docstring)]
    if not found:
        return ["nenhuma menção parseável 'registry/lista de N empresas' "
                "(reescrita de docstring = atualizar este teste)"]
    return [f"cita {n}, código diz {expected}" for n in found if n != expected]


# --- ci.yml: linha única tests=(...) — regex do procedimento anti-conflito ---

_CI_TEXT = _read(".github/workflows/ci.yml")
_CI_MATCH = re.search(r"^[ \t]*tests=\((.*)\)[ \t]*$", _CI_TEXT, re.M)
CI_TESTS: list[str] = _CI_MATCH.group(1).split() if _CI_MATCH else []


def test_registry_docstrings() -> None:
    print("1. contagem citada nos docstrings == len(registry)")
    for mod, label in ((dataset_source, "dataset_source.py"),
                      (ranking, "ranking.py")):
        v = docstring_registry_violations(mod.__doc__ or "", N_COMPANIES)
        check(f"1. {label}: docstring == {N_COMPANIES} empresas", not v, "; ".join(v))
    m = _RE_SEED_HEADER.search(_read("src/internship_finder/registry.py"))
    check(f"1c. header do SEED diz {N_COMPANIES}",
          bool(m) and int(m.group(1)) == N_COMPANIES,
          f"Seed: {m.group(1) if m else 'AUSENTE'}")
    arch = [int(n) for n in _RE_ARCH.findall(_read("docs/architecture.md"))]
    check(f"1d. docs/architecture.md: {len(arch)} site 'N empresas de coleta' (contrato: 1) == {N_COMPANIES}",
          len(arch) == 1 and arch[0] == N_COMPANIES, f"{arch}")
    oper = _read("docs/README-operacional.md")
    o1 = [int(n) for n in _RE_OPER_1.findall(oper)]
    o2 = [int(n) for n in _RE_OPER_2.findall(oper)]
    check(f"1e. README-operacional: 'N empresas operacionais' x{len(o1)} + 'N empresas em codigo' x{len(o2)} (contrato: 1+1) == {N_COMPANIES}",
          len(o1) == 1 and len(o2) == 1 and o1[0] == N_COMPANIES and o2[0] == N_COMPANIES,
          f"operacionais={o1} codigo={o2}")


def test_readme_counts() -> None:
    print("2. menções parseáveis do README == código vivo")
    readme = _read(README)
    en = [int(n) for n in _RE_COMPANIES_EN.findall(readme)]
    pt = [int(n) for n in _RE_COMPANIES_PT.findall(readme)]
    tbl = _RE_COMPANIES_TABLE.findall(readme)
    sites = en + pt + [int(a) for a, _ in tbl]
    check(f"2a. empresas: {len(sites)} menções (contrato: 4), todas == {N_COMPANIES}",
          len(sites) == 4 and all(n == N_COMPANIES for n in sites),
          f"en={en} pt={pt} tbl={tbl}")
    ats = [int(n) for n in _RE_ATS_PLATFORMS.findall(readme)] + [int(b) for _, b in tbl]
    check(f"2b. ATS platforms: {len(ats)} menções (contrato: 3), todas == {N_ATS} (ATS do SEED)",
          len(ats) == 3 and all(n == N_ATS for n in ats), f"{ats} vs SEED {N_ATS}")
    ci = [int(n) for n in _RE_CI_SUITES.findall(readme)]
    check(f"2c. CI test suites: 1 menção == len(tests=) ({len(CI_TESTS)})",
          len(ci) == 1 and ci[0] == len(CI_TESTS),
          f"readme={ci}, ci.yml={len(CI_TESTS)}")


def test_upstream_hour() -> None:
    print(f"3. claim de horário do upstream == janela medida (~{MEASURED_UPSTREAM_UTC} UTC, 19/10)")
    hours = _RE_HOUR_EN.findall(_read(README))
    check(f"3a. README 'refreshed daily ~HH:MM UTC': {len(hours)} sites (contrato: 2), todos ~{MEASURED_UPSTREAM_UTC}",
          len(hours) == 2 and all(h == MEASURED_UPSTREAM_UTC for h in hours), f"{hours}")
    for rel in HOUR_SRC_FILES:
        hs = _RE_HOUR_SRC.findall(_read(rel))
        check(f"3b. {rel}: {len(hs)} site (contrato: 1) == ~{MEASURED_UPSTREAM_UTC}",
              len(hs) == 1 and hs[0] == MEASURED_UPSTREAM_UTC, f"{hs}")
    living = [README, AGENTS, *HOUR_SRC_FILES]
    living += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md"))
    hits = [(rel, m.group(0)) for rel in living
            for m in _RE_STALE_HOUR.finditer(_read(rel))]
    check("3c. claim stale '~05' ausente de TODO doc vivo (README/AGENTS/src/docs)",
          not hits, f"{hits[:3]}")


def test_ci_membership() -> None:
    print("4. ci.yml: linha tests= parseável + membership")
    check("4a. linha tests=(...) encontrada pelo regex anti-conflito", bool(_CI_MATCH))
    check("4b. test_f73 presente no array", "test_f73" in CI_TESTS)
    check("4c. sem duplicatas no array", len(CI_TESTS) == len(set(CI_TESTS)),
          f"{len(CI_TESTS)} tokens, {len(set(CI_TESTS))} únicos")


def test_negative_controls() -> None:
    print("5. controles negativos: cada detector apanha o drift histórico")
    v = docstring_registry_violations("O registry de 999 empresas vira lista", N_COMPANIES)
    check("5a. docstring '999 empresas' apanhado", bool(v) and "999" in v[0], f"{v}")
    v = docstring_registry_violations("O registry vira componente do ranking", N_COMPANIES)
    check("5b. docstring SEM menção apanhado (nunca skip)", bool(v) and "nenhuma" in v[0], f"{v}")
    stale = (
        'RG["curated registry<br/>126 companies · 15 ATS platforms"]\n'
        "- **Curated registry** — 126 companies across 15 ATS platforms\n"
        "registry de 126 empresas\n"
        "| **126 / 15** | curated companies / ATS platforms |\n"
        "| **67** | CI test suites, all green on every push |\n"
        "refreshed daily ~05:00 UTC\n"
    )
    en = [int(n) for n in _RE_COMPANIES_EN.findall(stale)]
    check("5c. detector de empresas apanha 126 (≠ registry)",
          en == [126, 126] and all(n != N_COMPANIES for n in en), f"{en}")
    ats = [int(n) for n in _RE_ATS_PLATFORMS.findall(stale)] \
        + [int(b) for _, b in _RE_COMPANIES_TABLE.findall(stale)]
    check("5d. detector de ATS apanha 15 (≠ SEED)", 15 in ats and all(n != N_ATS for n in ats), f"{ats}")
    ci = [int(n) for n in _RE_CI_SUITES.findall(stale)]
    check("5e. detector de CI apanha 67 (≠ array)", ci == [67] and 67 != len(CI_TESTS),
          f"{ci} vs {len(CI_TESTS)}")
    hs = _RE_HOUR_EN.findall(stale)
    check("5f. detector de hora apanha 05:00 (≠ janela medida)",
          hs == ["05:00"] and "05:00" != MEASURED_UPSTREAM_UTC, f"{hs}")
    check("5g. detector de stale '~05' apanha o claim antigo", bool(_RE_STALE_HOUR.findall(stale)))
    check("5h. texto sem claims → inventário quebra (não passa em branco)",
          _RE_COMPANIES_EN.findall("nothing numeric here") == [])


def main() -> int:
    test_registry_docstrings()
    print()
    test_readme_counts()
    print()
    test_upstream_hour()
    print()
    test_ci_membership()
    print()
    test_negative_controls()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
