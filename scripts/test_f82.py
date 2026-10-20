#!/usr/bin/env python3
"""Suite F82 — contrato yaml do ci.yml: gatilhos + concurrency (test_f82).

F82 (20/10): a fase cujo OBJETO era o próprio ``.github/workflows/ci.yml``
(exceção documentada à regra "este arquivo não é editado por fase").
A política de gatilhos e a higiene de fila passam a ser CONTRATO:

1. GATILHO push: SÓ ``[main]`` — cada head de PR roda 1x. O evento
   ``pull_request`` (synchronize) já cobre todo push numa branch com PR
   aberto; o gatilho push em ``"feature/*"`` rodava cada head 2x
   (19/10: 30 runs, ~37% redundantes). Trade-off aceito no lançamento:
   branch SEM PR perde o sinal de push (convenção do repo = PR por
   fase; branch protection sem required contexts). Reverter = decisão
   consciente: editar a política aqui junto;
2. ``pull_request`` PRESENTE — é o evento que valida o head do PR;
3. ``concurrency`` no nível do workflow: ``group`` por workflow+ref e
   ``cancel-in-progress: true`` — run superseded na MESMA ref é
   cancelado (refs de PR ``refs/pull/N/merge`` ≠ refs de push: nunca
   colidem entre si).

CONTROLES NEGATIVOS (nunca falso-verde): o MESMO detector é aplicado a
cópias mutadas do ci.yml real (in-memory — zero disco/rede):
concurrency ausente = violação; ``"feature/*"`` de volta ao push =
violação; ``cancel-in-progress: false`` = violação; ``group`` fixo
(fora da forma por-ref) = violação; ``pull_request`` ausente =
violação. O arquivo real tem que cumprir TODOS para passar.

GOTCHA travado: em YAML 1.1 (PyYAML) a chave nua ``on:`` parseia como
booleana ``True`` — o detector localiza a chave certa (True OU "on")
antes de afirmar qualquer coisa sobre gatilhos.

100% OFFLINE (yaml.safe_load do arquivo real + mutações in-memory;
zero rede; ``data/`` intocada).

Uso:  python scripts/test_f82.py   (exit 0 = verde)
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"

# Política F82 (default do lançamento 20/10 — sem override "manter
# push feature/*"). Mudar a política = editar AQUI + o ci.yml no mesmo commit.
EXPECTED_PUSH_BRANCHES = ["main"]
EXPECTED_GROUP = "${{ github.workflow }}-${{ github.ref }}"

FAILURES: list[str] = []
N = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def section(name: str) -> None:
    print(f"\n== {name} ==")


def _on_key(doc: dict) -> object | None:
    """Chave do bloco de gatilhos (YAML 1.1: ``on:`` nua parseia como True)."""
    if True in doc:
        return True
    if "on" in doc:
        return "on"
    return None


def violations(doc: dict) -> list[str]:
    """Contrato F82 do ci.yml — lista de violações (vazia = cumprido)."""
    v: list[str] = []
    key = _on_key(doc)
    if key is None:
        return ["bloco de gatilhos (on:) ausente"]
    on = doc.get(key) or {}

    # ``pull_request:`` nua (valor None) é o default "all types" do
    # Actions — o contrato é a PRESENÇA da chave, não o valor.
    if "push" not in on:
        v.append("gatilho push ausente (main ficaria sem CI no push)")
    else:
        branches = (on["push"] or {}).get("branches")
        if branches != EXPECTED_PUSH_BRANCHES:
            v.append(
                f"push.branches {branches!r} != {EXPECTED_PUSH_BRANCHES!r} "
                "(política F82: só main — head de PR roda 1x via pull_request)"
            )

    if "pull_request" not in on:
        v.append("gatilho pull_request ausente (head de PR ficaria sem CI)")

    conc = doc.get("concurrency")
    if not isinstance(conc, dict):
        v.append(
            "bloco concurrency ausente (fila sem higiene: runs superseded acumulam)"
        )
    else:
        if conc.get("group") != EXPECTED_GROUP:
            v.append(
                f"concurrency.group {conc.get('group')!r} != por-ref "
                f"{EXPECTED_GROUP!r} (group fora da forma por-ref pode "
                "cancelar runs de OUTRAS refs)"
            )
        if conc.get("cancel-in-progress") is not True:
            v.append(
                "concurrency.cancel-in-progress não é true "
                "(runs superseded não são cancelados)"
            )
    return v


def main() -> int:
    print("F82 — contrato yaml do ci.yml: gatilhos + concurrency")
    raw = CI_YML.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)

    section("A — ci.yml real cumpre o contrato")
    check("A1. yaml.safe_load válido (dict com jobs)", isinstance(doc, dict) and "jobs" in doc)
    check("A2. gotcha YAML 1.1: bloco de gatilhos localizado (on: parseia como True)",
          _on_key(doc) is not None)
    v_real = violations(doc)
    check("A3. zero violações no arquivo real", not v_real, "; ".join(v_real))

    section("B — controles negativos: mutações do arquivo real são apanhadas")

    def _del_concurrency(m: dict) -> None:
        m.pop("concurrency", None)

    def _feature_back(m: dict) -> None:
        m[_on_key(m)]["push"]["branches"] = ["main", "feature/*"]

    def _cancel_false(m: dict) -> None:
        m["concurrency"]["cancel-in-progress"] = False

    def _group_fixed(m: dict) -> None:
        m["concurrency"]["group"] = "ci"

    def _del_pr(m: dict) -> None:
        m[_on_key(m)].pop("pull_request", None)

    for label, mutate, frag in [
        ("B1. sem bloco concurrency", _del_concurrency, "concurrency"),
        ("B2. \"feature/*\" de volta ao gatilho push", _feature_back, "push.branches"),
        ("B3. cancel-in-progress: false", _cancel_false, "cancel-in-progress"),
        ("B4. group fixo (não por-ref)", _group_fixed, "por-ref"),
        ("B5. sem gatilho pull_request", _del_pr, "pull_request"),
    ]:
        m = copy.deepcopy(doc)
        mutate(m)
        v = violations(m)
        hit = any(frag in msg for msg in v)
        check(label, bool(v) and hit, "; ".join(v))

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"F82: {len(FAILURES)} de {N} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"F82: TUDO OK — {N} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
