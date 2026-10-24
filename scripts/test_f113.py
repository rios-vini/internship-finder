#!/usr/bin/env python3
"""Testes da Fase F113 — visa_friendly count: fonte única de verdade
(100% offline, HERMÉTICO — sem dependência de data/, que é git-ignored
e não existe no checkout do CI; o teste original lia data/eligible_jobs.json
direto e quebraria qualquer checkout limpo).

Origem: varredura 237 — dashboard 235 × JSON 237. Causa medida: o contador
somava `shown` (cap 2/empresa + dead links) em vez da lista COMPLETA.
Evidência real (23/10, documentação não-fixture): eligible 688 vagas,
237 visa_friendly; shown exibia 235 → drift. A verificação end-to-end com
o JSON real roda na bateria do orquestrador (produção tem data/).
"""
from __future__ import annotations
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import minimal_page
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


def test_f113_codigo_usa_jobs_nao_shown() -> None:
    """Guard de fonte: a linha do contador soma sobre 'jobs', não 'shown'."""
    src = Path(__file__).resolve().parent.parent.joinpath(
        "scripts", "minimal_page.py").read_text(encoding="utf-8")
    linha = [l for l in src.splitlines() if "n_vf = sum(" in l]
    assert linha, "linha 'n_vf = sum(' não encontrada no minimal_page.py"
    assert any("for j in jobs" in l for l in linha), (
        "contador n_vf não soma sobre 'jobs' (lista completa) — regressão "
        "para 'shown' reintroduziria o drift 235×237"
    )
    print("✓ F113: guard de fonte — contador soma sobre 'jobs'")


if __name__ == "__main__":
    test_f113_contador_nao_usa_shown()
    test_f113_codigo_usa_jobs_nao_shown()
    print("\n=== F113: todos os testes passaram ===")