#!/usr/bin/env python3
"""F78 — CI auto-discovery: descoberta determinística + skip-list explícita.

Mata a classe de conflito serial da linha de array do ci.yml (104
commits a tocaram; 5/5 fases recentes editaram a MESMA linha). Passo 0
arqueológico (relatório F78): a lista explícita do P1 (7b88f76, 01/09)
NUNCA teve intenção de ordenação/isolamento — cada suíte é processo
standalone e a ordem do array era cronologia de append. Pré-swap
validado: array 109 == disco 109, DIFF VAZIO (zero mudança em QUAIS
testes rodam; a ordem alfabética nova foi provada inofensiva rodando a
suíte completa local).

Contrato novo travado aqui:
1. ci_discover_tests.discover_tests(): TODO scripts/test_*.py (glob
   NÃO-recursivo), ordem alfabética determinística, menos SKIP_TESTS.
2. SKIP_TESTS é EXPLÍCITA, datada (herda a EXCLUSÃO 05/09 — commit
   6426063: test_fetch/test_find_company/test_resolver, smokes de rede
   sem assertions) e TRAVADA: o conteúdo exato é assertado (C1) —
   mudar a skip-list sem este teste = vermelho (nunca silenciosa).
3. ci.yml invoca o módulo; suíte descoberta VAZIA = exit 1 do CLI +
   guarda no ci.yml (o step roda com set +e: nunca falso-verde).
4. Anti-regressão: nenhuma suíte antiga parseia mais a linha morta.

ZERO rede; data/ intocada; fixtures de árvore em tmp.
"""

import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ (explícito p/ importação indireta)

import ci_discover_tests

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CI_YML = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _make_tree(files: dict) -> Path:
    tree = Path(tempfile.mkdtemp(prefix="f78_tree_"))
    for rel, content in files.items():
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tree


def group_a_arvore_real() -> None:
    print("A. árvore real — descoberta do repositório")
    names = ci_discover_tests.discover_tests()
    check("A1 descoberta não-vazia e RELATIVA (>= 110: 109 pré-F78 + test_f78)",
          len(names) >= 110, f"{len(names)} suítes")
    check("A2 test_f78 presente na suíte descoberta (a própria suíte roda no CI)",
          "test_f78" in names)
    check("A3 determinística: duas chamadas idênticas",
          names == ci_discover_tests.discover_tests())
    check("A4 ordem alfabética (sorted)", names == sorted(names))
    check("A5 sem duplicatas", len(names) == len(set(names)),
          f"{len(names)} nomes, {len(set(names))} únicos")
    check("A6 todo nome descoberto tem arquivo",
          all((SCRIPTS / f"{n}.py").is_file() for n in names))
    check("A7 exclusões 05/09 seguem SEM arquivo no repo (removidas no 6426063)",
          not any((SCRIPTS / f"{n}.py").exists()
                  for n in ci_discover_tests.SKIP_TESTS))


def group_b_fixtures() -> None:
    print("B. fixtures de árvore — glob, ordem, skip, CLI")
    # B1: criação em ordem INVERSA à alfabética (mtime não pode influenciar);
    # não-testes (helpers, manifest_probe, testX sem underscore) e subdir fora.
    tree = _make_tree({
        "test_b.py": "# suite b",
        "helpers.py": "# modulo auxiliar (nao-suite)",
        "manifest_probe.py": "# probe manual 05/09 (nao-suite)",
        "testX.py": "# SEM underline: o glob test_*.py nao casa",
        "sub/test_d.py": "# subdir: glob NAO-recursivo",
        "test_a.py": "# suite a (criada por ultimo; a ordem e alfabetica)",
    })
    try:
        got = ci_discover_tests.discover_tests(tree)
        check("B1 descobre só test_*.py do nível, ordem alfabética",
              got == ["test_a", "test_b"], str(got))
        check("B1b manifest_probe/helpers/testX/subdir fora da descoberta",
              all(n not in got for n in
                  ("manifest_probe", "helpers", "testX", "sub", "test_d")))
    finally:
        shutil.rmtree(tree)

    # B2: arquivo com nome da skip-list re-aparece → excluído + warning.
    tree = _make_tree({"test_fetch.py": "# voltou do passado?",
                       "test_x.py": "# suite regular"})
    try:
        got = ci_discover_tests.discover_tests(tree)
        check("B2 skip-list exclui test_fetch (exclusão 05/09 herdada)",
              got == ["test_x"], str(got))
        err = StringIO()
        with redirect_stderr(err):
            ci_discover_tests.discover_tests(tree)
        check("B2b exclusão NUNCA silenciosa: ::warning com nome + decisão 05/09",
              "::warning" in err.getvalue() and "test_fetch" in err.getvalue()
              and "05/09" in err.getvalue())
    finally:
        shutil.rmtree(tree)

    # B3: skip paramétrico (sem tocar o SKIP_TESTS global) + árvore vazia.
    tree = _make_tree({"test_a.py": "x", "test_b.py": "x", "test_c.py": "x"})
    empty = Path(tempfile.mkdtemp(prefix="f78_empty_"))
    try:
        check("B3 skip paramétrico: discover_tests(tree, {'test_b'})",
              ci_discover_tests.discover_tests(tree, {"test_b"})
              == ["test_a", "test_c"])
        check("B3b árvore vazia → [] (função degrada sem crash)",
              ci_discover_tests.discover_tests(empty) == [])
    finally:
        shutil.rmtree(tree)
        shutil.rmtree(empty)

    # B4/B5: contrato do CLI (é dele que o ci.yml depende).
    empty_cli = Path(tempfile.mkdtemp(prefix="f78_cli_empty_"))
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "ci_discover_tests.py"),
             str(empty_cli)],
            capture_output=True, text=True, cwd=str(ROOT))
        check("B4 CLI em árvore VAZIA: exit 1 + ::error no stderr (nunca falso-verde)",
              r.returncode == 1 and "::error" in r.stderr, f"rc={r.returncode}")
    finally:
        shutil.rmtree(empty_cli)
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "ci_discover_tests.py")],
        capture_output=True, text=True, cwd=str(ROOT))
    check("B5 CLI na árvore real: exit 0 + stdout == descoberta",
          r.returncode == 0
          and r.stdout.split() == ci_discover_tests.discover_tests(),
          f"rc={r.returncode}, n={len(r.stdout.split())}")


def group_c_skiplist() -> None:
    print("C. skip-list explícita — conteúdo travado (nunca silenciosa)")
    expected = frozenset({"test_fetch", "test_find_company", "test_resolver"})
    check("C1 SKIP_TESTS == exatamente os 3 nomes da exclusão 05/09 (drift = vermelho)",
          ci_discover_tests.SKIP_TESTS == expected,
          str(sorted(ci_discover_tests.SKIP_TESTS)))
    src = (SCRIPTS / "ci_discover_tests.py").read_text(encoding="utf-8")
    check("C2 decisão datada e citada no módulo (05/09 + commit 6426063 + PR #21)",
          "05/09" in src and "6426063" in src and "#21" in src)
    check("C3 controle negativo: lista mutada é apanhada pela comparação exata",
          (ci_discover_tests.SKIP_TESTS | {"test_extra"}) != expected
          and (ci_discover_tests.SKIP_TESTS - {"test_fetch"}) != expected)


def group_d_ciyml() -> None:
    print("D. ci.yml pós-swap — linha literal morta, invocação e guarda")
    import re
    # A linha nova é "tests=($(" — lista literal começaria com letra [a-z].
    check("D1 array literal MORREU: nenhum tests=( com lista de nomes no ci.yml",
          re.search(r"^[ \t]*tests=\([a-z]", CI_YML, re.M) is None)
    check("D2 ci.yml invoca scripts/ci_discover_tests.py",
          "scripts/ci_discover_tests.py" in CI_YML)
    check("D3 guarda de vazio presente (${#tests[@]} + exit 1 — nunca falso-verde)",
          "${#tests[@]}" in CI_YML and "exit 1" in CI_YML)

    # D4: bash -n do bloco run do step de testes (extraído + dedent; offline).
    lines = CI_YML.splitlines()
    i = next(idx for idx, l in enumerate(lines) if l.strip() == "set +e")
    base_indent = len(lines[i]) - len(lines[i].lstrip())
    block: list[str] = []
    for l in lines[i:]:
        if l.strip() and (len(l) - len(l.lstrip())) < base_indent:
            break
        block.append(l[base_indent:] if l.strip() else "")
    bash = shutil.which("bash")
    if not bash:
        print("  [SKIP] D4 bash ausente neste ambiente")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                      encoding="utf-8") as fh:
        fh.write("\n".join(block))
        script_path = fh.name
    try:
        r = subprocess.run([bash, "-n", script_path],
                           capture_output=True, text=True)
        check("D4 bloco run do step de testes passa bash -n (sintaxe)",
              r.returncode == 0, r.stderr.strip()[:200])
    finally:
        Path(script_path).unlink(missing_ok=True)


def group_e_consumidores() -> None:
    print("E. anti-regressão — nenhum consumidor antigo parseia a linha morta")
    import re
    pat = re.compile(r"tests=\\?\(")  # pega "tests=(" e "tests=\(" dos regex antigos
    offenders = []
    for p in sorted(SCRIPTS.glob("test_*.py")):
        if p.name == "test_f78.py":
            continue  # este arquivo cita o padrão para travá-lo (D1)
        if pat.search(p.read_text(encoding="utf-8")):
            offenders.append(p.name)
    check("E1 nenhuma suíte parseia a linha morta (todas migradas p/ descoberta)",
          offenders == [], str(offenders))


def main() -> int:
    group_a_arvore_real()
    print()
    group_b_fixtures()
    print()
    group_c_skiplist()
    print()
    group_d_ciyml()
    print()
    group_e_consumidores()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
