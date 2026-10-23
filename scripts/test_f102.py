#!/usr/bin/env python3
"""F102 — swap do MODEL default: z-ai/glm-5.3 -> nvidia/nemotron-3-ultra-550b-a55b.

Motivo (evidencia nova, regra "NAO reabrir sem evidencia nova" do llm.py):
header ``deprecation: 2026-10-28T08:00:00Z`` em TODA resposta do glm-5.3
(aposentadoria POR MODELO; flash sem o header). A/B head-to-head 23/10
em codigo de producao: 96% respostas identicas, 5 divergencias reais
(nemotron 4x1), zero alucinacao, latencia empate. Evidencia:
``~/.hermes/handoff/nvidia-deprecao-ab/``.

Contrato vivo (offline, zero rede):
1. MODEL default = nemotron-3-ultra SEM env; a env
   ``INTERNSHIP_FINDER_ENRICHMENT_MODEL`` sobrescreve (precedencia F50.1
   preservada — rollback documentado ate 28/10 08:00Z).
2. Doc-sync do llm.py: __doc__ documenta o modelo VIVO, a data de
   deprecacao do glm-5.3 e o caminho da evidencia (padrao F73 aplicado
   ao modulo).
3. Pinos literais dos testes vizinhos ACOMPANHAM o MODEL (parametrico:
   ``llm.MODEL`` == literal em test_enrichment.py e test_f12.py — o
   proximo swap atualiza os tres juntos; grep pelo VALOR, nao string
   congelada — licao F73/F94).
4. Superficie vizinha intacta: build_prompt segue montando
   company/title no prompt.
5. README: contagem de suítes == descoberta (contrato global e do
   test_f73; aqui e sanity local do PR).

Uso:  .venv/bin/python scripts/test_f102.py   (ou bash scripts/test_f102.py)
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.enrichment import llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NEW_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def main() -> int:
    section("A: MODEL default + precedencia da env (F50.1 preservada)")
    check("A1. MODEL default = nemotron-3-ultra (sem env)",
          llm.MODEL == NEW_MODEL, detail=llm.MODEL)
    check("A2. MODEL_ENV e a env documentada de override",
          llm.MODEL_ENV == "INTERNSHIP_FINDER_ENRICHMENT_MODEL")
    check("A3. env ausente no shell do CI (contrato: key/model so de env)",
          "INTERNSHIP_FINDER_ENRICHMENT_MODEL" not in os.environ)

    os.environ[llm.MODEL_ENV] = "z-ai/glm-5.3"  # rollback simulado
    reloaded = importlib.reload(llm)
    check("A4. env sobrescreve o default (rollback ate 28/10)",
          reloaded.MODEL == "z-ai/glm-5.3", detail=reloaded.MODEL)
    del os.environ[llm.MODEL_ENV]
    importlib.reload(llm)
    check("A5. sem env, default volta ao nemotron",
          llm.MODEL == NEW_MODEL, detail=llm.MODEL)

    section("B: doc-sync do llm.py (padrao F73 no modulo)")
    doc = llm.__doc__ or ""
    check("B1. __doc__ cita o modelo VIVO", NEW_MODEL in doc)
    check("B2. __doc__ ancora a data de deprecação do glm-5.3",
          "2026-10-28T08:00:00Z" in doc)
    check("B3. __doc__ aponta a evidencia A/B",
          "nvidia-deprecao-ab" in doc)
    check("B4. __doc__ preserva o fato historico F50.1 (calibracao low)",
          "19/10/2026" in doc and 'reasoning_effort="low"' in doc)

    section("C: pinos literais vizinhos acompanham o MODEL (parametrico)")
    te = (ROOT / "scripts" / "test_enrichment.py").read_text(encoding="utf-8")
    tf12 = (ROOT / "scripts" / "test_f12.py").read_text(encoding="utf-8")
    check("C1. test_enrichment pina o literal == llm.MODEL",
          f'"{llm.MODEL}"' in te)
    check("C2. test_f12 pina o literal == llm.MODEL",
          f'"{llm.MODEL}"' in tf12)
    check("C3. nenhum pino ORFAO do glm-5.3 como default em src/",
          'or "z-ai/glm-5.3"' not in
          (ROOT / "src" / "internship_finder" / "enrichment" / "llm.py")
          .read_text(encoding="utf-8"))

    section("D: superficie vizinha intacta")
    p = llm.build_prompt("ACME Corp", "Praktikum Einkauf", "conteudo")
    check("D1. build_prompt ancora company/title",
          "ACME Corp" in p and "Praktikum Einkauf" in p)

    section("E: README == descoberta (sanity local do contrato F73)")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"\| \*\*(\d+)\*\* \| CI test suites", readme)
    discovered = len(list((ROOT / "scripts").glob("test_*.py")))
    check("E1. contador do README == suítes descobertas",
          m is not None and int(m.group(1)) == discovered,
          detail=f"README={m.group(1) if m else '?'} vs {discovered}")

    print()
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        print(f"F102: {len(FAILURES)} falhas")
        return 1
    print("F102: TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
