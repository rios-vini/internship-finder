"""Testes de validacao forte do modelo ``Job`` (scripts/test_validation.py).

Cobre o comportamento implementado em P2 #11:

1. Sintetico: titulo/url sao ``strip``-eados; titulo/url vazios (ou so
   whitespace) sao INVVALIDOS (erro de validacao); campos opcionais vazios
   viram ``None``; campos opcionais ausentes continuam ``None``.
2. Compatibilidade: um Job construido igual ao do adapter (via ``Job(**{...})``)
   sobrevive sem regressao nos campos normais.
3. Dados reais (SKIP se ``data/eligible_jobs.json`` nao existir): os Jobs
   recarregam via ``Job(**d)`` sem erro e nenhum ``title``/``url`` tem borda
   de whitespace.

Uso:  .venv/bin/python scripts/test_validation.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.models.job import Job  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"  [OK] {label}")
    else:
        print(f"  [FAIL] {label}")
        FAILURES.append(label)


def rejects_validation(label: str, fn) -> None:
    """Espera que ``fn`` levante ``ValidationError`` (vaga invalida)."""
    try:
        fn()
        check(label, False)
    except ValidationError:
        check(label, True)


def test_synthetic() -> None:
    print("== sintetico: normalizacao e rejeicao ==")
    base = dict(id="1", source="s", company="Acme", collected_at=datetime.now(timezone.utc))

    # strip em title/url
    j = Job(**base, title="  Werkstudent Einkauf  ", url="  https://a.example/x  ")
    check("titulo e strip-ado", j.title == "Werkstudent Einkauf")
    check("url e strip-ada", j.url == "https://a.example/x")

    # obrigatorios vazios -> erro de validacao
    rejects_validation("title='' -> erro de validacao", lambda: Job(**base, title=""))
    rejects_validation("title='   ' -> erro de validacao", lambda: Job(**base, title="   "))
    rejects_validation("url='   ' -> erro de validacao",
                       lambda: Job(**base, title="T", url="   "))
    rejects_validation("url ausente -> erro de validacao",
                       lambda: Job(**base, title="T"))

    # opcionais vazios -> None
    j = Job(**base, title="T", url="https://a.x", country_iso="   ", location="  ")
    check("country_iso='   ' -> None", j.country_iso is None)
    check("location='  ' -> None", j.location is None)

    j = Job(**base, title="T", url="https://a.x", description="  ",
            employment_type=" ", country="  ", external_id=" ")
    check("description='  ' -> None", j.description is None)
    check("employment_type=' ' -> None", j.employment_type is None)
    check("country='  ' -> None", j.country is None)
    check("external_id=' ' -> None", j.external_id is None)

    # opcionais ausentes -> None (default preservado)
    j = Job(**base, title="T", url="https://a.x")
    check("opcionais ausentes continuam None",
          j.location is None and j.country_iso is None and j.employment_type is None
          and j.external_id is None and j.country is None)

    # job valido com todos os campos -> passou intacto
    j = Job(**base, title="Praktikum Procurement", url="https://a.example/p",
            location="Berlin, DE", country="Germany", description="Role desc",
            employment_type="Internship", external_id="R7", country_iso="de")
    check("job valido com todos os campos -> intacto",
          j.title == "Praktikum Procurement" and j.url == "https://a.example/p"
          and j.location == "Berlin, DE" and j.country == "Germany"
          and j.country_iso == "de" and j.external_id == "R7")


def test_compat() -> None:
    print("== compatibilidade: construcao igual ao adapter ==")
    # Igual ao fluxo do adapter: campos opcionais ausentes -> None; normais
    # sobrevivem. Mensagem clara de erro para o campo obrigatorio.
    payload = {
        "id": "source:hash",
        "source": "smartrecruiters:BoschGroup",
        "title": "Praktikum Einkauf Data",
        "company": "Bosch Group",
        "location": "Walldorf, DE, 69190",
        "country": "de",
        "url": "https://jobs.example/praktikum",
        "description": "Vaga em Einkauf",
        "employment_type": "Internship",
        "external_id": "R42",
        "country_iso": "de",
        "collected_at": datetime.now(timezone.utc),
    }
    j = Job(**payload)
    check("campos normais sobrevivem (title/url/company/location)",
          j.title == "Praktikum Einkauf Data" and j.url == "https://jobs.example/praktikum"
          and j.company == "Bosch Group" and j.location == "Walldorf, DE, 69190")
    check("country_iso preservado", j.country_iso == "de")
    check("id/source preservados", j.id == "source:hash" and j.source == "smartrecruiters:BoschGroup")
    check("raw ausente -> None", j.raw is None)

    # campos opcionais omitidos (como no fluxo real) -> None, sem erro
    slim = {k: v for k, v in payload.items() if k not in
            ("location", "country", "description", "employment_type", "external_id",
             "country_iso")}
    j2 = Job(**slim)
    check("opcionais omitidos -> None",
          j2.location is None and j2.country is None and j2.description is None
          and j2.external_id is None and j2.employment_type is None
          and j2.country_iso is None)


def test_real_data() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "eligible_jobs.json"
    if not path.exists():
        print("== dados reais: SKIP (data/eligible_jobs.json ausente) ==")
        return
    print("== dados reais: data/eligible_jobs.json ==")
    jobs = json.loads(path.read_text())
    if not isinstance(jobs, list):
        jobs = jobs.get("jobs", jobs)
    ok = 0
    border_title = 0
    border_url = 0
    loaded: list[Job] = []
    for d in jobs:
        try:
            loaded.append(Job(**d))
            ok += 1
        except ValidationError:
            check(f"Job recarrega sem erro: {d.get('id', '?')}", False)
            return
    for j in loaded:
        if j.title != j.title.strip():
            border_title += 1
        if j.url != j.url.strip():
            border_url += 1
    check(f"recarregados sem erro ({ok})", ok == len(jobs))
    check(f"nenhum title com borda de whitespace ({border_title})", border_title == 0)
    check("nenhum url com borda de whitespace", border_url == 0)


def main() -> int:
    test_synthetic()
    test_compat()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())