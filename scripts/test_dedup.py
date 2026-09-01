"""Testes do modulo de deduplicacao (scripts/test_dedup.py).

Roda tres blocos: (1) normalizacoes puras, (2) deduplicate sintetico (chaves e
regra do vencedor), (3) execucao real sobre data/eligible_jobs.json com
verificacao dos grupos removidos. Uso:

    .venv/bin/python scripts/test_dedup.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.dedup import (  # noqa: E402
    KEY_COMPANY_TITLE_LOCATION,
    KEY_EXTERNAL_ID,
    KEY_URL,
    deduplicate,
    normalize_location,
    normalize_title,
    normalize_url,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_normalizations() -> None:
    print("== normalizacoes ==")
    # genero
    check(
        "genero (m/w/d) vs (f/m/d)",
        normalize_title("Werkstudent (m/w/d) SAP") == normalize_title("Werkstudent (f/m/d) SAP"),
    )
    check(
        "genero w/m/div.",
        normalize_title("Praktikant (w/m/div.) Einkauf") == normalize_title("Praktikant (m/w/div.) Einkauf"),
    )
    # EN/DE: JMP Purchasing (par real do conjunto)
    check(
        "EN/DE JMP Purchasing",
        normalize_title("Junior Managers Program (Trainee) - Start your Leadership Journey in Purchasing")
        == normalize_title("Junior Managers Program (Trainee) - Starte deine Leadership Journey im Bereich Purchasing"),
    )
    # EN/DE: werkstudent == working student
    check(
        "EN/DE werkstudent == working student",
        normalize_title("Werkstudent (w/m/d) - IT End-User Enablement and Operations")
        == normalize_title("Working Student (f/m/d) - IT End-User Enablement and Operations"),
    )
    # ordem das palavras indiferente
    check(
        "ordem das palavras indiferente",
        normalize_title("Praktikum in der Logistik - Data & Analytics")
        == normalize_title("Praktikum Data Analytics in der Logistik"),
    )
    # pontuacao/espaços
    check(
        "pontuacao/espaços",
        normalize_title("Working Student (f/m/d) - Marketing - SAP Services MEE")
        == normalize_title("Working Student (f/m/d) - Marketing- SAP Services MEE"),
    )
    # acentos
    check("acentos", normalize_title("Einkauf Höhe") == normalize_title("Einkauf Hohe"))
    # NAO-duplicatas permanecem diferentes (falsos positivos reais do conjunto)
    check(
        "falso positivo: eMobility vs eBike",
        normalize_title("Praktikum im Projektmanagement - Einkauf eMobility")
        != normalize_title("Praktikum im Einkauf eBike - Projektmanagement"),
    )
    check(
        "falso positivo: Business Transformation vs Success Management",
        normalize_title("Werkstudent (w/m/d) - SAP Business Transformation Management")
        != normalize_title("Working Student (f/m/d) - SAP Business Transformation Success Management"),
    )
    check(
        "falso positivo: Marketing Support vs Technical Enablement",
        normalize_title("Working Student (f/m/d) - Security Compliance Education and Awareness (Marketing Support)")
        != normalize_title("Working Student (f/m/d) - Security Compliance Education and Awareness (Technical Enablement)"),
    )
    # url
    check(
        "url normalizada",
        normalize_url("https://jobs.sap.com/job/X/123?lang=de#top") == "https://jobs.sap.com/job/x/123?lang=de",
    )
    check("url trailing slash", normalize_url("https://a.com/x/") == "https://a.com/x")
    # query mantida: eightfold carrega o id da vaga nela (falso positivo real
    # se stripping: "Industrial Trainee" vs "Documentation Engineer" fundidos)
    check(
        "url query mantida (eightfold)",
        normalize_url("https://infineon.eightfold.ai/careers/job/private?pid=563808971367597")
        != normalize_url("https://infineon.eightfold.ai/careers/job/private?pid=563808971810705"),
    )
    # location
    check("location ISO-2", normalize_location("Stuttgart, DE") == "stuttgart")
    check("location acento", normalize_location("Gerlingen-Schillerhöhe") == "gerlingen-schillerhohe")


def test_synthetic() -> None:
    print("== deduplicate sintetico ==")
    base = {
        "id": "1", "source": "t", "title": "Intern (m/f/d) Procurement",
        "company": "Acme", "location": "Berlin, DE", "url": "https://a.com/1",
        "external_id": "111", "collected_at": "2026-08-10T00:00:00Z",
    }
    dup_ext = dict(base, id="2", url="https://a.com/2")  # mesma external_id, URL diferente
    dup_url = dict(base, id="3", external_id="333", url="https://a.com/1")  # mesma URL
    dup_ctl = dict(base, id="4", external_id="444", url="https://a.com/4",
                   title="Intern (m/w/d) - Procurement")  # mesmo company+titulo+local
    diferente = dict(base, id="5", external_id="555", url="https://a.com/5",
                     title="Werkstudent IT", location="Munich, DE")

    out, stats, removed = deduplicate([base, dup_ext, dup_url, dup_ctl, diferente])
    check("sintetico: 3 duplicatas removidas", len(out) == 2 and len(removed) == 3)
    check("sintetico: 1 por external_id", stats.get(KEY_EXTERNAL_ID) == 1)
    check("sintetico: 1 por url", stats.get(KEY_URL) == 1)
    check("sintetico: 1 por company+title+location", stats.get(KEY_COMPANY_TITLE_LOCATION) == 1)
    check("sintetico: vencedora = primeira (empate)", out[0]["id"] == "1")

    # regra do vencedor: descricao preenchida vence
    com_desc = dict(base, id="6", external_id="666", url="https://a.com/6",
                    description="descricao completa")
    sem_desc = dict(base, id="7", external_id="666", url="https://a.com/7")  # mesma external_id
    out2, _, removed2 = deduplicate([sem_desc, com_desc])
    check("vencedor: descricao preenchida", out2[0]["id"] == "6")
    check("vencedor: removida registrada", removed2[0][1]["id"] == "7")

    # regra do vencedor: employment_type quando ambos sem descricao
    com_et = dict(base, id="8", external_id="888", url="https://a.com/8", employment_type="INTERN")
    sem_et = dict(base, id="9", external_id="888", url="https://a.com/9")
    out3, _, _ = deduplicate([sem_et, com_et])
    check("vencedor: employment_type", out3[0]["id"] == "8")

    # sem localizacao: chave (c) nao funde
    no_loc_a = dict(base, id="10", external_id="1010", url="https://a.com/10",
                    location=None, title="Intern Procurement")
    no_loc_b = dict(base, id="11", external_id="1111", url="https://a.com/11",
                    location=None, title="Intern Procurement")
    out4, _, _ = deduplicate([no_loc_a, no_loc_b])
    check("sem localizacao: nao funde por (c)", len(out4) == 2)


def test_real_data() -> None:
    print("== execucao real (data/eligible_jobs.json) ==")
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "eligible_jobs.json"
    # Ambiente sem coleta (ex.: CI runner sem data/): skip do bloco real com
    # exit 0. O bloco de dados so roda onde o arquivo existe localmente.
    if not path.exists():
        print("  SKIP: data/eligible_jobs.json ausente (sem coleta local) - bloco real ignorado")
        return
    jobs = json.loads(path.read_text(encoding="utf-8"))
    out, stats, removed = deduplicate(jobs)
    print(f"  eligible: {len(jobs)} -> {len(out)} (removidas {len(removed)})")
    print(f"  por chave: {stats}")
    check("real: sem duplicatas no resultado", len(out) == len(set(id(j) for j in out)))

    # todo par removido deve ter a MESMA chave normalizada (auditoria)
    for winner, loser, label in removed:
        keys_w = dict(candidate_keys_for_audit := {})
        # reutiliza candidate_keys para auditoria
        from internship_finder.dedup import candidate_keys
        wk = candidate_keys(winner)
        lk = candidate_keys(loser)
        wk_map = {l: k for l, k in wk}
        lk_map = {l: k for l, k in lk}
        if label == KEY_COMPANY_TITLE_LOCATION:
            check(f"auditoria (c): {winner['title'][:40]!r}", wk_map[label] == lk_map[label])
        else:
            check(f"auditoria {label}", wk_map[label] == lk_map[label])


def main() -> int:
    test_normalizations()
    test_synthetic()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
