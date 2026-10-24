#!/usr/bin/env python3
"""Test F113 — visa-friendly count no dashboard bate com o JSON (fonte única de verdade).

O contador do rodapé (n_vf) deve ser igual à contagem de visa_friendly=True
no eligible_jobs.json completo — não ao subconjunto exibido (shown), que
sofre cap 2/empresa, remoção de dead links, etc.

Fixture: usa o eligible_jobs.json real do data/ (688 vagas, 237 visa_friendly).
O teste roda o render_minimal_html e verifica que o rodapé contém "237".
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import minimal_page


def test_f113_visa_friendly_count_matches_json() -> None:
    """O n_vf do rodapé deve bater com visa_friendly do eligible_jobs.json."""
    # Carrega o JSON real (fonte de verdade)
    eligible_path = ROOT / "data" / "eligible_jobs.json"
    with eligible_path.open(encoding="utf-8") as fh:
        jobs = json.load(fh)

    # Contagem direta do campo visa_friendly (já preenchido pelo pipeline)
    expected_vf = sum(1 for j in jobs if j.get("visa_friendly") is True)
    total_eligible = len(jobs)

    # Render minimal page (full-list regime, como no publish)
    html = minimal_page.render_minimal_html(
        jobs=jobs,
        total_eligible=total_eligible,
        generated_at="2026-10-24 07:00",
        full_list=True,
        lang="en",  # publish usa EN
    )

    # O rodapé EN contém: "{shown} · {n_vf} with 🛂 (employer with a stated visa policy)..."
    # Verifica se o n_vf esperado aparece no HTML
    expected_marker = f"{expected_vf} with 🛂"
    assert expected_marker in html, (
        f"Rodapé não contém a contagem visa_friendly esperada ({expected_vf}). "
        f"Procurado: '{expected_marker}'"
    )

    # Também verifica que NÃO aparece o valor antigo incorreto (235)
    assert "235 with 🛂" not in html, "Valor antigo (drift) ainda presente no rodapé"

    print(f"✓ F113 OK: visa_friendly count = {expected_vf} (bate com JSON)")


def test_f113_contador_nao_usa_shown() -> None:
    """Garante que o contador n_vf usa 'jobs' (lista completa) e não 'shown'."""
    # Cria jobs sintéticos: 10 vagas, 5 visa_friendly
    # 3 das visa_friendly são da mesma empresa (simula cap 2/empresa -> 1 cai do shown)
    jobs = [
        {"id": f"job{i}", "company": "EmpresaA", "title": f"Vaga {i}", "visa_friendly": True, "score": 10.0}
        for i in range(5)
    ] + [
        {"id": f"job{i}", "company": f"EmpresaB{i}", "title": f"Vaga {i}", "visa_friendly": False, "score": 5.0}
        for i in range(5, 10)
    ]
    total_eligible = len(jobs)
    expected_vf = 5  # 5 visa_friendly no total

    # Render no regime full-list (sem cap 2/empresa aplicado ao contador)
    html = minimal_page.render_minimal_html(
        jobs=jobs,
        total_eligible=total_eligible,
        generated_at="2026-10-24 07:00",
        full_list=True,
        lang="en",
    )

    # O contador deve refletir os 5 do JSON, não o que sobra no shown após cap
    expected_marker = f"{expected_vf} with 🛂"
    assert expected_marker in html, (
        f"Contador usou shown (com cap) em vez do JSON completo. "
        f"Esperado {expected_vf}, HTML contém contagem diferente."
    )

    print("✓ F113 OK: contador ignora cap/empresa e lê do JSON completo")


if __name__ == "__main__":
    test_f113_visa_friendly_count_matches_json()
    test_f113_contador_nao_usa_shown()
    print("\n=== F113: todos os testes passaram ===")