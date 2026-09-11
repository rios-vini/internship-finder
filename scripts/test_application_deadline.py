"""Testes do P0 Application Deadline (scripts/test_application_deadline.py).

Cobre o campo canonico ``application_deadline`` no modelo ``Job`` e sua
normalizacao no adapter:

- campo ausente -> None (nunca fabricado);
- valor explicito valido -> parseado;
- ISO 8601 com ``Z`` -> aware UTC;
- ISO com offset -> preserva offset;
- valor invalido -> None (graceful);
- ``posted_at`` nunca vira deadline (nao se infere de outras datas);
- serializacao (to_dict) inclui o campo;
- dedup nao usa o deadline como chave.
- (P1.4) deadline real preservado mesmo que coincida com ``posted_at + 30 dias``
  -- nunca remover por heuristica. Contexto do achado: varios tenants
  SuccessFactors publicam no feed RSS Google Merchant (``<host>/sitemal.xml``)
  o campo ``g:expiration_date`` com UM unico valor por feed, igual a
  ``data do feed + 30 dias``, para TODAS as vagas (ex.: feed de 10/09 ->
  ``2026-10-10``; feed de 11/09 -> ``2026-10-11``). E um horizonte de validade
  gerado pela PLATAFORMA (a fonte), nao um prazo definido pelo empregador;
  mas, por proveniencia, VEM DA FONTE. O scraper (ats-scrapers 0.3.0) apenas
  parseia ``g:expiration_date``; este adapter apenas mapeia/parseia. Nenhuma
  camada soma +30 dias. Remover por heuristica violaria este contrato (um
  prazo real que coincida com +30 dias seria apagado).

Uso:
    .venv/bin/python scripts/test_application_deadline.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def make_company() -> Company:
    return Company(name="Schaeffler", ats="successfactors", slug="schaeffler", url="https://careers.schaeffler.de")


def base_item(**overrides) -> dict:
    item = {
        "title": "Praktikum im Einkauf",
        "url": "https://careers.schaeffler.de/job/1",
        "external_id": "R123",
    }
    item.update(overrides)
    return item


def adapt(item: dict) -> Job:
    return AtsJobAdapter().to_job(item, make_company())


def test_model_default() -> None:
    print("== modelo: default None ==")
    job = Job(
        id="t:1",
        source="successfactors:schaeffler",
        title="Praktikum",
        company="Schaeffler",
        url="https://x/1",
        collected_at=datetime.now(UTC),
    )
    check("application_deadline default None", job.application_deadline is None)


def test_absent_is_none() -> None:
    print("== campo ausente -> None ==")
    job = adapt(base_item())
    check("sem deadline -> None", job.application_deadline is None)


def test_explicit_valid() -> None:
    print("== valor explicito valido ==")
    job = adapt(base_item(application_deadline="2026-09-30"))
    check(
        "YYYY-MM-DD parseado",
        job.application_deadline == datetime(2026, 9, 30),
    )


def test_iso_with_z() -> None:
    print("== ISO com Z (UTC) ==")
    job = adapt(base_item(application_deadline="2026-09-30T12:00:00Z"))
    check(
        "Z -> aware UTC",
        job.application_deadline == datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
    )


def test_iso_with_offset() -> None:
    print("== ISO com offset ==")
    job = adapt(base_item(application_deadline="2026-09-30T14:00:00+02:00"))
    check(
        "offset preservado",
        job.application_deadline == datetime(2026, 9, 30, 14, 0, tzinfo=timezone(timedelta(hours=2))),
    )


def test_invalid_is_none() -> None:
    print("== invalido -> None ==")
    job = adapt(base_item(application_deadline="not-a-date"))
    check("invalido -> None", job.application_deadline is None)


def test_posted_at_not_deadline() -> None:
    print("== posted_at nunca vira deadline ==")
    job = adapt(base_item(posted_at="2026-08-01T00:00:00Z"))
    check(
        "posted_at preenchido, deadline None",
        job.posted_at is not None and job.application_deadline is None,
    )


def test_serialization() -> None:
    print("== serializacao (to_dict) ==")
    job = adapt(base_item(application_deadline="2026-09-30T10:00:00Z"))
    d = job.to_dict()
    check("to_dict inclui application_deadline", "application_deadline" in d)
    check(
        "valor serializado ISO",
        d["application_deadline"] == "2026-09-30T10:00:00Z",
    )
    job_none = adapt(base_item())
    check("to_dict com None", job_none.to_dict()["application_deadline"] is None)


def test_caso1_deadline_real_2026_10_15() -> None:
    print("== Caso 1 (P1.4): deadline real fornecido e preservado ==")
    job = adapt(base_item(application_deadline="2026-10-15"))
    check("deadline 2026-10-15 preservado",
          job.application_deadline == datetime(2026, 10, 15))


def test_caso3_no_infer_plus30() -> None:
    print("== Caso 3 (P1.4): nao inferir +30 dias ==")
    # posted_at presente, deadline ausente: None — nunca posted_at + 30 dias.
    job = adapt(base_item(posted_at="2026-09-07"))
    check("posted_at sem deadline -> None", job.application_deadline is None)
    check("NUNCA inferido 2026-10-07 (posted_at+30)",
          job.application_deadline != datetime(2026, 10, 7))


def test_caso4_preserve_deadline_equal_plus30() -> None:
    print("== Caso 4 (P1.4): deadline real que coincide com +30 dias e preservado ==")
    # Guarda contra uma futura heuristica que detecte 'posted_at + 30 dias'
    # e apague o valor. A origem do campo determina a validade — um deadline
    # explicitamente fornecido pela fonte e preservado mesmo que coincida com
    # +30 dias.
    job = adapt(base_item(posted_at="2026-09-07", application_deadline="2026-10-07"))
    check("deadline explicito 2026-10-07 preservado (nao removido por +30d)",
          job.application_deadline == datetime(2026, 10, 7))


def test_dedup_ignores_deadline() -> None:
    print("== dedup nao usa deadline ==")
    base = {
        "id": "1", "source": "successfactors:schaeffler",
        "title": "Praktikum (m/w/d) Einkauf", "company": "Schaeffler",
        "location": "Herzogenaurach, DE", "url": "https://a.com/1",
        "external_id": "R1", "collected_at": "2026-08-10T00:00:00Z",
    }
    dup_deadline = dict(
        base, id="2", url="https://a.com/2",
        application_deadline="2026-09-30", posted_at="2026-08-01T00:00:00Z",
    )
    diferente = dict(
        base, id="3", url="https://a.com/3", external_id="R3",
        title="Werkstudent IT", location="Munich, DE",
        application_deadline="2026-10-15",
    )
    out, stats, removed = deduplicate([base, dup_deadline, diferente])
    check(
        "deadline nao diferencia duplicata (mesma chave)",
        len(out) == 2 and len(removed) == 1,
    )
    check("vagas com deadline diferente nao colidem", len(out) == 2)


def main() -> int:
    test_model_default()
    test_absent_is_none()
    test_explicit_valid()
    test_iso_with_z()
    test_iso_with_offset()
    test_invalid_is_none()
    test_posted_at_not_deadline()
    test_serialization()
    test_caso1_deadline_real_2026_10_15()
    test_caso3_no_infer_plus30()
    test_caso4_preserve_deadline_equal_plus30()
    test_dedup_ignores_deadline()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())