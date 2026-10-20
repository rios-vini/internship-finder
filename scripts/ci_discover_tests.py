#!/usr/bin/env python3
"""Descoberta determinística das suítes do CI (F78, 19/10/2026).

Substitui a linha explícita de array do ``.github/workflows/ci.yml`` —
104 commits a tocaram e 5/5 fases recentes editaram a MESMA linha: o
hotspot serial #1 do repo. A partir da F78 a suíte do CI é descoberta do
filesystem: TODO ``scripts/test_*.py`` roda, em ordem alfabética
(determinística — imune a mtime/ordem de glob), EXCETO SKIP_TESTS.

SKIP_TESTS — exclusões DELIBERADAS, datadas, NUNCA silenciosas (o
conteúdo exato é travado pelo scripts/test_f78.py — mudar esta lista sem
atualizar o teste no MESMO commit = suíte vermelha):

- test_fetch, test_find_company, test_resolver — EXCLUSÃO 05/09 (commit
  6426063, PR #22): eram smokes de rede SEM assertions (prints + fetch
  ao vivo), entraram no CI por engano no PR #21 e foram REMOVIDOS do
  repo e do array na limpeza 05/09. Se um arquivo com um desses nomes
  re-aparecer em scripts/, ele continua FORA do CI com um ::warning
  visível no log — a decisão 05/09 segue valendo até uma re-decisão
  consciente (reverter = tirar o nome de SKIP_TESTS + atualizar o
  test_f78 no mesmo commit).
- manifest_probe.py (probe manual de rede, sem assertions — comentário
  05/09 no ci.yml) NÃO casa com o glob ``test_*.py``; não precisa de
  entrada na skip-list.

Contrato do CLI (usado pelo ci.yml: ``tests=($(python
scripts/ci_discover_tests.py))``): imprime os nomes separados por espaço
na stdout; avisos vão para stderr; exit 1 se a descoberta for VAZIA — o
step do CI roda com ``set +e``, então vazio NUNCA pode virar verde
silencioso (o ci.yml também guarda com ``${#tests[@]}``).

Zero dependências além da stdlib; zero rede; data/ intocada.
"""

from __future__ import annotations

import sys
from pathlib import Path

# EXCLUSÃO 05/09 (commit 6426063, PR #22) — smokes de rede sem
# assertions, removidos do repo E do array na limpeza 05/09.
# Travado no scripts/test_f78.py (C1): mudar aqui = atualizar lá.
SKIP_TESTS: frozenset[str] = frozenset({
    "test_fetch",         # 05/09: smoke de rede (entrara por engano no PR #21)
    "test_find_company",  # 05/09: idem
    "test_resolver",      # 05/09: idem
})


def discover_tests(
    scripts_dir: Path | str | None = None,
    skip: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Nomes (sem .py) de scripts/test_*.py, ordenados, menos o skip.

    Glob NÃO-recursivo (subdirs de scripts/ nunca rodam no CI); ordem =
    sorted() — determinística. Nomes da skip-list com arquivo presente
    são pulados COM aviso visível (stderr) — exclusão nunca silenciosa.
    """
    base = (Path(scripts_dir) if scripts_dir is not None
            else Path(__file__).resolve().parent)
    effective_skip = SKIP_TESTS if skip is None else frozenset(skip)
    names = sorted(p.stem for p in base.glob("test_*.py") if p.is_file())
    skipped_present = sorted(
        n for n in effective_skip if (base / f"{n}.py").is_file())
    if skipped_present:
        print(
            f"::warning::F78 skip-list: {', '.join(skipped_present)} "
            f"existe(m) em {base} e fica(m) FORA do CI — exclusão "
            f"deliberada herdada de 05/09 (commit 6426063, PR #22); ver "
            f"scripts/ci_discover_tests.py. Reverter a decisao = tirar de "
            f"SKIP_TESTS + atualizar o test_f78 no mesmo commit.",
            file=sys.stderr,
        )
    return [n for n in names if n not in effective_skip]


def main(argv: list[str] | None = None) -> int:
    """CLI: [scripts_dir] opcional (testável); imprime nomes; vazio = exit 1."""
    args = sys.argv[1:] if argv is None else argv
    names = discover_tests(args[0] if args else None)
    if not names:
        print(
            "::error::F78 auto-discovery: 0 suítes encontradas — CI aborta "
            "(sem falso-verde; o step roda com set +e)",
            file=sys.stderr,
        )
        return 1
    print(" ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
