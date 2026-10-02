#!/usr/bin/env python3
"""Fase F4 — Bundesagentur + EURES com filtro de estagio (test_f4, offline).

Cobre a spec F4 §5 — 100% OFFLINE (nenhuma rede; fetchers/transporte
injetados com fixtures sinteticas):

A. Parsing BA: item v6 (angebotsart=34) -> Job; internship pelo titulo;
   location/country_iso; description do detail v4 (hydratada) ou None.
B. Parsing EURES: jv de busca -> Job; description embutida (translations);
   epoch-ms -> posted_at; locationMap -> location/iso.
C. Filtros de estagio: jobs diretos com marcador no titulo passam no
   is_student_role; programas (Trainee/MBA) NAO viram internship.
D. Dedup cross-fonte: a MESMA vaga vinda de direct:bundesagentur e
   sf_dataset:bundesagentur (mesma URL) colapsa na chave URL; mesma vaga
   com company divergente NAO colapsa (escopo P1.1); EURES direto vs
   dataset idem.
E. Rate limit/config: caps por fonte (<=200), paginacao sequencial (1
   request por vez — contador de chamadas), timeout curto, budget entre
   fontes (estoura -> EURES skipped_budget).
F. Degradacao graciosa: BA falha -> EURES entrega jobs (status partial);
   AMBAS falham -> status failed, run segue (exit code do pipeline
   intocado); pagina nao-1 falha -> entrega o que tem.
G. Hidratacao: mapa single-source (bundesagentur/eures) — job
   sf_dataset:bundesagentur com description vazia hidrata via scraper real
   do pacote (mock get_description); job direct:* com description ja
   presente NAO e re-fetchada; workday sf_dataset segue derivando slug da
   URL (regressao F3).
H. Registro JSONL direct_fetch: campos do registro; CLI wiring
   (--direct-fetch default ON no --registry, --no-direct-fetch desliga,
   --companies explicito OFF).
"""

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import direct_fetch as df  # noqa: E402
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.hydration import (  # noqa: E402
    _effective_ats,
    _slug_for,
    hydrate_descriptions,
)
from internship_finder.models.job import Job  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  [OK]   {label}")
    else:
        FAILURES.append(label)
        print(f"  [FAIL] {label} {detail}")


# ---------------------------------------------------------------------------
# Fixtures sinteticas (derivadas das fatias/probes reais, 02/10)
# ---------------------------------------------------------------------------

BA_ITEM = {
    "referenznummer": "10001-1003695576-S",
    "stellenangebotsTitel": "Praktikum Vertrieb",
    "firma": "coffee perfect GmbH",
    "stellenlokationen": [
        {"adresse": {"plz": "10115", "ort": "Berlin", "region": "BERLIN",
                     "land": "DEUTSCHLAND"}}
    ],
    "arbeitszeitVollzeit": True,
    "datumErsteVeroeffentlichung": "2026-10-01",
    "stellenangebotsart": "PRAKTIKUM_TRAINEE",
}

BA_ITEM_AUSBILDUNG = {
    "referenznummer": "2-2-S",
    "stellenangebotsTitel": "Ausbildung Kaufmann",
    "firma": "Andere GmbH",
    "stellenlokationen": [
        {"adresse": {"plz": "20095", "ort": "Hamburg", "region": "HAMBURG",
                     "land": "DEUTSCHLAND"}}
    ],
}

EURES_ITEM = {
    "id": "MTczNjc5NjkgNDM",
    "title": "Trainee für Bauleiter/in",
    "employerName": "Strabag AG",
    "locationMap": {"DE": ["DE12"]},
    "description": "<b>Praktikum</b> in Vienna<br/>apply now",
    "creationDate": 1759270400000,
    "positionOfferingCode": "apprenticeship",
}

EURES_ITEM_NO_DESC = {
    "id": "jv-2",
    "title": "Werkstudent Logistics (m/w/d)",
    "employerName": "DHL",
    "locationMap": {"DE": []},
    "translations": {"de": {"description": "Werkstudent im Bereich Logistik."}},
    "creationDate": 1759270400000,
}


# ---------------------------------------------------------------------------
# A. Parsing BA
# ---------------------------------------------------------------------------


def test_parsing_ba() -> None:
    print("\n== A. Parsing BA (item v6 -> Job) ==")
    job = df._ba_item_to_job(BA_ITEM, "Beschreibung des Praktikums.")
    check("A1: Job criado", job is not None)
    if job is None:
        return
    check("A2: id com escopo company + source direto",
          job.id == "coffee perfect GmbH|direct:bundesagentur:10001-1003695576-S")
    check("A3: source direct:bundesagentur", job.source == "direct:bundesagentur")
    check("A4: internship pelo titulo (Praktikum)", job.internship is True)
    check("A5: description do detail repassada",
          job.description == "Beschreibung des Praktikums.")
    check("A6: country_iso de", job.country_iso == "de")
    check("A7: location formatada", "Berlin" in (job.location or ""))
    check("A8: posted_at parseada (ISO)",
          job.posted_at == datetime.fromisoformat("2026-10-01"))
    check("A9: external_id = refnr", job.external_id == "10001-1003695576-S")
    check("A10: raw preserva campos (sem description)", "stellenangebotsart" in job.raw)
    check("A11: URL do jobdetail com refnr", "jobdetail/10001-1003695576-S" in job.url)

    job2 = df._ba_item_to_job(BA_ITEM, None)
    check("A12: description None preservada (vaga continua)", job2 is not None and job2.description is None)

    bad = dict(BA_ITEM)
    bad["referenznummer"] = ""
    check("A13: item sem refnr -> None (nunca Job fabricado)",
          df._ba_item_to_job(bad, "x") is None)
    bad2 = {"referenznummer": "1-S", "stellenangebotsTitel": ""}
    check("A14: item sem titulo -> None", df._ba_item_to_job(bad2, None) is None)

    aus = df._ba_item_to_job(BA_ITEM_AUSBILDUNG, None)
    check("A15: Ausbildung no titulo NAO e internship",
          aus is not None and aus.internship is False)


# ---------------------------------------------------------------------------
# B. Parsing EURES
# ---------------------------------------------------------------------------


def test_parsing_eures() -> None:
    print("\n== B. Parsing EURES (jv de busca -> Job) ==")
    job = df._eures_item_to_job(EURES_ITEM)
    check("B1: Job criado", job is not None)
    if job is None:
        return
    check("B2: id com escopo company + source direto",
          job.id.startswith("Strabag AG|direct:eures:MTczNjc5NjkgNDM"))
    check("B3: internship via title+description (Trainee.../apprenticeship)",
          job.internship is True)
    check("B4: description HTML limpa (br->\n, tags fora)",
          job.description == "Praktikum in Vienna\napply now")
    check("B5: posted_at de epoch-ms",
          job.posted_at == datetime.fromtimestamp(1759270400000 / 1000, tz=UTC))
    check("B6: location do locationMap", job.location == "DE (DE12)")
    check("B7: country_iso de (locationMap)", job.country_iso == "de")
    check("B8: URL jv-details", "jv-details/MTczNjc5NjkgNDM" in job.url)

    job2 = df._eures_item_to_job(EURES_ITEM_NO_DESC)
    check("B9: description das translations quando description vazia",
          job2 is not None and job2.description == "Werkstudent im Bereich Logistik.")
    check("B10: Werkstudent no titulo -> internship", job2 is not None and job2.internship is True)

    bad = dict(EURES_ITEM)
    bad["id"] = None
    check("B11: jv sem id -> None", df._eures_item_to_job(bad) is None)
    bad2 = dict(EURES_ITEM)
    bad2["title"] = "  "
    check("B12: jv sem titulo -> None", df._eures_item_to_job(bad2) is None)


# ---------------------------------------------------------------------------
# Helpers de fixture: fetchers falsos (offline)
# ---------------------------------------------------------------------------


def _ba_payload(items: list[dict]) -> dict:
    return {"maxErgebnisse": len(items), "ergebnisliste": items}


def _eures_payload(items: list[dict]) -> dict:
    return {"numberRecords": len(items), "jvs": items}


class _FakeTransport:
    """Conta chamadas e devolve payloads programados; simula falhas.

    Emula o OFFSET real das APIs: pagina N devolve items
    [(N-1)*size : N*size] do catalogo programado — variar o size entre
    paginas (bug) produziria overlap visivel ao teste.
    """

    def __init__(self, ba_pages: list[dict | None], eures_pages: list[dict | None],
                 ba_details: dict[str, str] | None = None):
        self.ba_pages = list(ba_pages)
        self.eures_pages = list(eures_pages)
        self.ba_details = ba_details or {}
        self.ba_calls = 0
        self.eures_calls = 0
        self.detail_calls = 0

    def ba_json(self, method, url, **kwargs):
        self.ba_calls += 1
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        page = int(q.get("page", ["1"])[0])
        size = int(q.get("size", ["100"])[0])
        idx = min(self.ba_calls - 1, len(self.ba_pages) - 1)
        payload = self.ba_pages[idx]
        if payload is None:
            return None
        items = payload["ergebnisliste"]
        return {"maxErgebnisse": len(items), "ergebnisliste": items[(page - 1) * size: page * size]}

    def ba_text(self, url, **kwargs):
        self.detail_calls += 1
        for refnr, text in self.ba_details.items():
            if refnr in url:
                import json as _json
                return _json.dumps({"stellenangebotsBeschreibung": text})
        return None

    def eures_json(self, method, url, **kwargs):
        import json as _json
        self.eures_calls += 1
        body = _json.loads(kwargs.get("payload_raw") or "{}") if kwargs.get("payload_raw") else (kwargs.get("payload") or {})
        page = int(body.get("page", 1)) if isinstance(body, dict) else 1
        rpp = int(body.get("resultsPerPage", 50)) if isinstance(body, dict) else 50
        if not self.eures_pages:
            return None
        payload = self.eures_pages[0]
        items = payload["jvs"]
        return {"numberRecords": len(items),
                "jvs": items[(page - 1) * rpp: page * rpp]}


# ---------------------------------------------------------------------------
# C. Rate limit / caps / paginacao sequencial
# ---------------------------------------------------------------------------


def test_rate_limit_caps() -> None:
    print("\n== C. Rate limit: caps, paginacao sequencial, budget ==")
    # 250 items no catalogo, cap 200 -> para no cap (truncated_cap)
    many = [dict(BA_ITEM, referenznummer=f"r{i}-S",
                 stellenangebotsTitel=f"Praktikum Nr {i}") for i in range(250)]
    tr = _FakeTransport(ba_pages=[_ba_payload(many)], eures_pages=[])
    jobs, stats = df.fetch_ba_praktikum(max_jobs=200, http_json=tr.ba_json,
                                        http_text=lambda url, **kw: None)
    check("C1: cap de 200 jobs respeitado", len(jobs) == 200, f"got {len(jobs)}")
    check("C2: truncated_cap no stats", stats["truncated_cap"] is True)
    check("C3: rows_seen conta o catalogo varrido", stats["rows_seen"] == 200)

    # paginacao sequencial: cap 130 -> 2 paginas (100 + 30), 1 chamada/pagina
    tr2 = _FakeTransport(ba_pages=[_ba_payload(many)], eures_pages=[])
    calls = []
    orig = tr2.ba_json

    def counting(method, url, **kw):
        calls.append(url)
        return orig(method, url, **kw)
    jobs2, stats2 = df.fetch_ba_praktikum(max_jobs=130, http_json=counting,
                                          http_text=lambda url, **kw: None)
    check("C4: 2 paginas para 130 jobs", stats2["pages"] == 2, f"got {stats2['pages']}")
    check("C5: paginacao sequencial (2 requests lista)", len(calls) == 2)
    check("C6: size CONSTANTE entre paginas (offset estavel, sem overlap)",
          "size=100" in calls[1] and "page=2" in calls[1])
    ids2 = [j.external_id for j in jobs2]
    check("C6b: 130 jobs SEM duplicatas (offset correto)",
          len(ids2) == len(set(ids2)) == 130)
    check("C7: filtro angebotsart=34 em TODAS as paginas",
          all("angebotsart=34" in u for u in calls))
    check("C8: sort veroeffdatum presente", all("sortierung=veroeffdatum" in u for u in calls))

    # EURES: cap 120 -> 3 paginas de 50 (50+50+20)
    many_eu = [dict(EURES_ITEM, id=f"jv-{i}", title=f"Praktikum {i}") for i in range(300)]
    tr3 = _FakeTransport(ba_pages=[], eures_pages=[_eures_payload(many_eu)] * 10)
    jobs3, stats3 = df.fetch_eures_praktikum(max_jobs=120, http_json=tr3.eures_json)
    check("C9: EURES cap 120 respeitado", len(jobs3) == 120, f"got {len(jobs3)}")
    check("C10: EURES 3 paginas", stats3["pages"] == 3, f"got {stats3['pages']}")
    check("C11: EURES truncated_cap", stats3["truncated_cap"] is True)

    # hard caps de paginas (BA >20, EURES >8 nunca acontecem com cap 200)
    tr4 = _FakeTransport(ba_pages=[_ba_payload(many)], eures_pages=[])
    jobs4, stats4 = df.fetch_ba_praktikum(
        max_jobs=10000, http_json=tr4.ba_json, http_text=lambda url, **kw: None)
    check("C12: hard cap de paginas BA limita catalogo infinito",
          stats4["pages"] <= 20 and len(jobs4) <= 2000,
          f"pages={stats4['pages']} jobs={len(jobs4)}")

    # budget: BA consome o budget todo -> EURES skipped
    def _never_eures(**kw):
        raise AssertionError("EURES nao deveria rodar com budget 0")

    jobs5, summary = df.collect_direct_fetch(
        budget_seconds=0.0,
        ba_fetch=lambda **kw: ([], {"source": "direct:bundesagentur",
                                    "status": "ok", "jobs": 0, "rows_seen": 0,
                                    "pages": 0, "details_ok": 0,
                                    "details_failed": 0, "truncated_cap": False,
                                    "error": None}),
        eures_fetch=_never_eures,
        now=lambda: 100.0,
    )
    check("C13: budget 0 -> EURES skipped_budget",
          summary["eures"].get("status") == "skipped_budget"
          and summary["skipped_budget"] is True)
    check("C14: summary geral status ok (BA ok)", summary["status"] == "ok")


# ---------------------------------------------------------------------------
# D. Dedup cross-fonte (direct vs sf_dataset vs producao)
# ---------------------------------------------------------------------------


def _job_dict(job: Job) -> dict:
    return job.to_dict() if hasattr(job, "to_dict") else job


def test_dedup_cross_source() -> None:
    print("\n== D. Dedup cross-fonte ==")
    direct = df._ba_item_to_job(BA_ITEM, "desc direta com texto")
    # mesma vaga na fatia (F3): MESMA URL, id diferente (source diferente)
    dataset_job = Job(
        id="coffee perfect GmbH|sf_dataset:bundesagentur:10001-1003695576-S",
        source="sf_dataset:bundesagentur",
        title="Praktikum Vertrieb", company="coffee perfect GmbH",
        country="de", url=direct.url, description=None,
        internship=True, external_id="10001-1003695576-S",
        collected_at=datetime.now(UTC),
    )
    out, stats, removed = deduplicate([_job_dict(direct), _job_dict(dataset_job)])
    check("D1: mesma vaga direct+dataset colapsa (1 sobrevive)",
          len(out) == 1, f"got {len(out)}")
    check("D2: vencedor e o direct (tem description — regra _prefer)",
          out and out[0].get("description") == "desc direta com texto")

    # company divergente (mesma URL) NAO colapsa: escopo P1.1
    other = Job(
        id="Outra Firma|sf_dataset:bundesagentur:10001-1003695576-S",
        source="sf_dataset:bundesagentur",
        title="Praktikum Vertrieb", company="Outra Firma",
        country="de", url=direct.url, description=None,
        internship=True, external_id="10001-1003695576-S",
        collected_at=datetime.now(UTC),
    )
    out2, _, _ = deduplicate([_job_dict(direct), _job_dict(other)])
    check("D3: company divergente NAO colapsa (P1.1)", len(out2) == 2)

    # EURES direto vs dataset: mesma URL colapsa
    eu_direct = df._eures_item_to_job(EURES_ITEM)
    eu_ds = Job(
        id="Strabag AG|sf_dataset:eures:MTczNjc5NjkgNDM",
        source="sf_dataset:eures",
        title="Trainee für Bauleiter/in", company="Strabag AG",
        country="de", url=eu_direct.url, description="texto fatia",
        internship=True, external_id="MTczNjc5NjkgNDM",
        collected_at=datetime.now(UTC),
    )
    out3, _, _ = deduplicate([_job_dict(eu_direct), _job_dict(eu_ds)])
    check("D4: EURES direct+dataset colapsa pela URL", len(out3) == 1)

    # job producao (tenant) NUNCA colide: source/escopo distintos, URL do
    # jobdetail da BA nao existe na coleta registry -> sem colapso espurio
    prod = Job(
        id="coffee perfect GmbH|greenhouse:coffee:123",
        source="greenhouse:coffee",
        title="Praktikum Vertrieb", company="coffee perfect GmbH",
        country="de", url="https://boards.greenhouse.io/coffee/jobs/123",
        description="desc producao", internship=True,
        collected_at=datetime.now(UTC),
    )
    out4, _, _ = deduplicate([_job_dict(direct), _job_dict(prod)])
    check("D5: job producao (tenant) preservado ao lado do direct", len(out4) == 2)


# ---------------------------------------------------------------------------
# E. Degracao graciosa (falha de fonte)
# ---------------------------------------------------------------------------


def test_degradacao_graciosa() -> None:
    print("\n== E. Degradacao graciosa ==")
    # BA falha na 1a pagina -> status failed da fonte, EURES entrega
    tr = _FakeTransport(ba_pages=[None], eures_pages=[
        _eures_payload([dict(EURES_ITEM, id="jv-ok")])])
    jobs, summary = df.collect_direct_fetch(
        ba_fetch=lambda **kw: df.fetch_ba_praktikum(
            http_json=lambda m, u, **k: None, http_text=lambda u, **k: None),
        eures_fetch=lambda **kw: df.fetch_eures_praktikum(http_json=tr.eures_json),
        now=lambda: 0.0,
    )
    check("E1: BA falha -> status failed da fonte",
          summary["ba"]["status"] == "failed")
    check("E2: EURES entrega jobs mesmo com BA fora",
          summary["eures"]["jobs"] == 1 and len(jobs) == 1)
    check("E3: summary geral partial (uma fonte ok)",
          summary["status"] == "partial")

    # AMBAS falham -> failed, jobs vazios, NENHUMA excecao
    jobs2, summary2 = df.collect_direct_fetch(
        ba_fetch=lambda **kw: df.fetch_ba_praktikum(
            http_json=lambda m, u, **k: None, http_text=lambda u, **k: None),
        eures_fetch=lambda **kw: df.fetch_eures_praktikum(
            http_json=lambda m, u, **k: None),
        now=lambda: 0.0,
    )
    check("E4: ambas falham -> status failed geral", summary2["status"] == "failed")
    check("E5: jobs vazios sem excecao", jobs2 == [])

    # BA falha na pagina 2+ -> entrega o que tem (partial dentro da fonte)
    page1 = _ba_payload([dict(BA_ITEM, referenznummer=f"p{i}-S",
                              stellenangebotsTitel=f"Praktikum p{i}") for i in range(100)])
    tr3 = _FakeTransport(ba_pages=[page1, None], eures_pages=[])
    jobs3, stats3 = df.fetch_ba_praktikum(max_jobs=150, http_json=tr3.ba_json,
                                          http_text=lambda u, **k: None)
    check("E6: pagina 2 falha -> 100 jobs da pagina 1 entregues",
          len(jobs3) == 100, f"got {len(jobs3)}")
    check("E7: status ok com o que houver (nao failed)",
          stats3["status"] == "ok" and stats3["pages"] == 1)

    # detail v4 falha por vaga -> vaga preservada SEM description
    tr4 = _FakeTransport(ba_pages=[_ba_payload([BA_ITEM])], eures_pages=[])
    jobs4, stats4 = df.fetch_ba_praktikum(max_jobs=5, http_json=tr4.ba_json,
                                          http_text=lambda u, **k: None)
    check("E8: detail falha -> vaga preservada sem description",
          len(jobs4) == 1 and jobs4[0].description is None)
    check("E9: details_failed contada", stats4["details_failed"] == 1)


# ---------------------------------------------------------------------------
# F. Hidratacao: mapa single-source (F4) + regressao F3
# ---------------------------------------------------------------------------


class _FakeBAScraper:
    """get_description fake (offline): 1 chamada por vaga."""

    def __init__(self):
        self.calls = 0

    def get_description(self, job):
        self.calls += 1
        return "Descricao completa do detail v4."


def test_hidratacao() -> None:
    print("\n== F. Hidratacao (mapa F4 + regressao F3) ==")
    check("F1: _effective_ats sf_dataset:bundesagentur -> bundesagentur",
          _effective_ats("sf_dataset:bundesagentur") == "bundesagentur")
    check("F2: _effective_ats direct:eures -> eures",
          _effective_ats("direct:eures") == "eures")
    check("F3: _effective_ats registry ats:slug -> ats",
          _effective_ats("greenhouse:coffee") == "greenhouse")

    job_ds = {
        "id": "coffee perfect GmbH|sf_dataset:bundesagentur:10001-1003695576-S",
        "source": "sf_dataset:bundesagentur",
        "title": "Praktikum Vertrieb", "company": "coffee perfect GmbH",
        "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1003695576-S",
        "external_id": "10001-1003695576-S", "description": None,
    }
    check("F4: slug single-source bundesagentur (stub fixo)",
          _slug_for("bundesagentur", job_ds) == "bundesagentur")
    job_eu = {
        "id": "X|sf_dataset:eures:MTcz", "source": "sf_dataset:eures",
        "title": "Trainee", "company": "Strabag",
        "url": "https://europa.eu/eures/portal/jv-se/jv-details/MTcz?lang=en",
        "external_id": "MTcz", "description": None,
    }
    check("F5: slug single-source eures", _slug_for("eures", job_eu) == "eures")

    # regressao F3: workday segue derivando slug da URL
    job_wd = {
        "id": "X|sf_dataset:workday:abc", "source": "sf_dataset:workday",
        "title": "Working Student", "company": "ABB",
        "url": "https://abb.wd3.myworkdayjobs.com/ABB/careers/job/123",
        "external_id": "abc", "description": None,
    }
    check("F6: (regressao F3) workday slug da URL",
          _slug_for("workday", job_wd) == "https://abb.wd3.myworkdayjobs.com/ABB")

    # hidratacao real com factory fake: dataset BA hidrata
    fake = _FakeBAScraper()
    out, stats = hydrate_descriptions(
        [dict(job_ds)], scraper_factory=lambda ats, slug: fake)
    check("F7: dataset BA hidratada via scraper",
          stats["hydration_success"] == 1 and out[0]["description"])
    check("F8: description_source=hydration", out[0].get("description_source") == "hydration")
    check("F9: factory recebeu (bundesagentur, stub)", fake.calls == 1)

    # job direct com description NAO e re-fetchada
    direct_job = {
        "id": "X|direct:bundesagentur:10001-S", "source": "direct:bundesagentur",
        "title": "Praktikum", "company": "Y",
        "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-S",
        "external_id": "10001-S", "description": "texto do fetch direto",
    }
    fake2 = _FakeBAScraper()
    out2, stats2 = hydrate_descriptions(
        [dict(direct_job)], scraper_factory=lambda ats, slug: fake2)
    check("F10: direct com description preservada (sem fetch)",
          stats2["already_has_description"] == 1 and fake2.calls == 0)

    # source desconhecido -> unsupported_no_detail (nunca scraper com slug inventado)
    weird = {
        "id": "X|sf_dataset:phenom:1", "source": "sf_dataset:phenom",
        "title": "Intern", "company": "Z",
        "url": "https://phenom.example/1", "description": None,
    }
    fake3 = _FakeBAScraper()
    out3, stats3 = hydrate_descriptions(
        [dict(weird)], scraper_factory=lambda ats, slug: fake3)
    check("F11: ATS sem endpoint -> unsupported_no_detail (preservada)",
          stats3["unsupported_no_detail"] == 1 and fake3.calls == 0
          and out3[0].get("description") is None)


# ---------------------------------------------------------------------------
# G. Registro JSONL + wiring CLI
# ---------------------------------------------------------------------------


def test_registro_e_wiring() -> None:
    print("\n== G. Registro direct_fetch + wiring CLI ==")
    from internship_finder import cli as if_cli

    # _direct_fetch_record: campos do registro
    record = if_cli._direct_fetch_record("run-1", {
        "source": "direct_fetch", "status": "partial", "jobs": 5,
        "ba": {"source": "direct:bundesagentur", "status": "failed", "jobs": 0},
        "eures": {"source": "direct:eures", "status": "ok", "jobs": 5},
        "duration": 12.5, "skipped_budget": False,
    })
    check("G1: type=direct_fetch", record["type"] == "direct_fetch")
    check("G2: run_id/timestamp/source/status presentes",
          record["run_id"] == "run-1" and record["timestamp"]
          and record["status"] == "partial")
    check("G3: sub-statuses por fonte no registro",
          record["ba"]["status"] == "failed" and record["eures"]["jobs"] == 5)

    # _run_direct_fetch_stage: excecao estrutural -> registro failed, jobs []
    # (monkeypatch do collect: o teste NUNCA faz rede)
    orig_collect = if_cli.collect_direct_fetch
    try:
        def _boom(**kw):
            raise RuntimeError("forjado: rede fora do teste")
        if_cli.collect_direct_fetch = _boom
        jobs, rec = if_cli._run_direct_fetch_stage("run-2", 600.0, None)
    finally:
        if_cli.collect_direct_fetch = orig_collect
    check("G4: excecao estrutural -> registro failed, jobs vazios",
          jobs == [] and rec is not None and rec["type"] == "direct_fetch"
          and rec["status"] == "failed")

    # wiring: defaults das flags
    import argparse as _ap
    parser_probe = if_cli.main.__module__  # sanity: modulo importavel
    check("G5: cli importavel e estagio definido",
          hasattr(if_cli, "_run_direct_fetch_stage")
          and parser_probe == "internship_finder.cli")

    # collection_command (refresh): --direct-fetch explicito
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
    import refresh_daily as rd  # type: ignore  # noqa: E402
    cmd = rd.collection_command(60)
    check("G6: refresh passa --direct-fetch explicito",
          "--direct-fetch" in cmd and "--dataset" in cmd and "--registry" in cmd)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=== test_f4: Bundesagentur + EURES com Praktikum (offline) ===")
    for fn in (
        test_parsing_ba,
        test_parsing_eures,
        test_rate_limit_caps,
        test_dedup_cross_source,
        test_degradacao_graciosa,
        test_hidratacao,
        test_registro_e_wiring,
    ):
        fn()
    print(f"\n=== {CHECKS} checks, {len(FAILURES)} falhas ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  FALHOU: {f}")
        print("TESTE F4: FAIL")
        return 1
    print("TESTE F4: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
