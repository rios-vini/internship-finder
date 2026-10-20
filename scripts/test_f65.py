#!/usr/bin/env python3
"""test_f65 — F65: hidratação estendida (além do top exibido) com teto de fetches/dia.

Suíte offline (exit-code; ZERO rede — fake opener injetável; data/ real
intocada). Cobre a card F65 (classe B da F60 — vagas cegas fora da
janela F20, caso Lidl praktikum_info:13308116):

- **Gate flag-gated (regra 9)**: ``INTERNSHIP_FINDER_HYDRATION_BUDGET``
  env OU ``.env`` (padrão F1); 0/ausente/inválido/negativo = OFF — nenhum
  fetch, nenhuma leitura de arquivo, JSON byte-identical, nenhuma
  métrica (kill switch total; env tem precedência sobre o arquivo).
- **Candidatas** (pura): FORA do top exibido (shown_ids), description
  curta/vazia (< HYDRATION_SHORT_LIMIT), ordem OFICIAL do ranking
  preservada ("as melhores primeiro" — spec F65).
- **Teto**: exatamente N fetches (as N melhores por score; N < pool
  trunca, N > pool cobre tudo sem passar do pool).
- **Fixture VERBATIM**: Lidl ``praktikum_info:13308116`` — JSON-LD
  JobPosting salvo pela F60 (página viva, 2524 chars de description,
  "Sehr gute Deutschkenntnisse" na seção "Dein Profil"), embutido byte
  a byte. Hidrata => detector F60 VÊ o texto => ``german_required`` =>
  varredura F37.3 remove do JSON (a classe Lidl fecha).
- **Contra-casos**: topo nunca re-fetchado pela janela estendida;
  hidratada (desc longa) não é candidata no run seguinte (idempotente);
  mortas do passe estendido são CONTADAS (``dead_seen``) mas NUNCA
  marcadas (semântica de morte pertence à janela do topo); falha total
  de rede não hidrata/marca nada; CSV acompanha o re-score F56; métrica
  ``extended_hydration`` auditável (baseline 0 quando não há cegas).
- **E2E**: ``rd.main()`` integra o estágio ANTES da F25/F37.3
  (german_required revelado pela janela estendida sai do JSON no MESMO
  run) com o MESMO gate de publicação da F20 (sem ``--pages-dir`` o
  estágio nem roda).
"""

import json
import os
import sys
import tempfile
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

# F65 (hotfix 20/10): `now` do re-score F56 PINADO na data da evidência.
# O decay de frescor (score_job) envelhece o score da fixture ~0,005/dia;
# sem o pino, os valores de evidência (9.0 -> 7.96) e a literal do CSV eram
# uma bomba-relógio — quebrou 20/10, 1 dia após o merge (CI verde no dia
# do push, vermelho no dia seguinte). Pino = autoria da evidência (19/10).
# O monkeypatch intercepta o nome no namespace de refresh_daily (o import
# é `from internship_finder.ranking import rescore_hydrated_jobs`), SEM
# tocar em src/ — comportamento de produção usa o now real, SEMPRE.
_FROZEN_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# VERBATIM: JSON-LD JobPosting da página viva da Lidl praktikum_info:13308116
# (probe 2 da F60, 18/10; salvo em /tmp/f60-data/lidl_13308116_enriched.jsonld.json
# e aqui embutido byte a byte — CI não depende de /tmp). A description tem 2524
# chars com "Sehr gute Deutschkenntnisse" verbatim na seção "Dein Profil".
LIDL_JSONLD_VERBATIM = r'''{
 "@context": "http://schema.org",
 "@type": "JobPosting",
 "title": "Praktikum Controlling International - BI Requirement Engineering",
 "datePosted": "2026-10-17",
 "validThrough": "2026-12-02T23:59:59+01:00",
 "employmentType": "[INTERN]",
 "industry": "controlling",
 "description": "Einleitung&lt;br&gt;&lt;p&gt;Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und bieten spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich.&lt;/p&gt;&lt;br&gt;Deine Aufgaben&lt;br&gt;&lt;p&gt;&lt;strong&gt;Unterstütze uns bei der Digitalisierung und Weiterentwicklung des Reportings mit SAP und der SAP Analytics Cloud. Ab Februar / März für 6 Monate.&lt;br&gt;&lt;/strong&gt;… konkret heißt das:&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Mitarbeit im Anforderungsprozess von der Aufnahme bis zum internationalen Rollout fachlicher Anforderungen an unsere BI Systeme&lt;/li&gt;&lt;li&gt;Systemseitige Sicherstellung einer durchgängig hohen Reporting-Qualität&lt;/li&gt;&lt;li&gt;Austausch mit Schnittstellen in den operativen und technischen Fachbereichen (IT) sowie in den Landesgesellschaften&lt;/li&gt;&lt;/ul&gt;&lt;br&gt;Dein Profil&lt;br&gt;&lt;ul&gt;&lt;li&gt;Studium* im Bereich Wirtschaftsiwssenschaften oder ein vergleichbarer Studiengang&lt;/li&gt;&lt;li&gt;Idealerweise Interesse an IT Themen sowie erste praktische Erfahrung mit BI Produkten&lt;/li&gt;&lt;li&gt;Sehr guter Umgang mit Google Sheets&lt;/li&gt;&lt;li&gt;Sehr gute Deutschkenntnisse&lt;/li&gt;&lt;/ul&gt;&lt;p&gt; &lt;/p&gt;&lt;p&gt;*Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu.&lt;/p&gt;&lt;br&gt;Wir bieten&lt;br&gt;&lt;p&gt;Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deines festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze die Chance, dir ein erstes Karrierenetzwerk aufzubauen.&lt;/p&gt;",
 "jobLocation": [
  {
   "@type": "Place",
   "address": {
    "@type": "PostalAddress",
    "addressLocality": "Neckarsulm",
    "addressRegion": "DE",
    "postalCode": "74167",
    "streetAddress": "Stiftsbergstraße 1"
   }
  }
 ],
 "hiringOrganization": {
  "@type": "Organization",
  "name": "Lidl Dienstleistung GmbH &amp; Co. KG",
  "url": "https://www.absolventa.de/unternehmen/1290291-s-lidl-dienstleistung-gmbh-co-kg",
  "logo": "https://d1e0s3eaddm99m.cloudfront.net/accounts/logos/72/original_1547035929.svg",
  "description": "Lidl ist eines der führenden Unternehmen im Lebensmitteleinzelhandel und betreibt weltweit über 12.200 Filialen in derzeit 32 Ländern."
 }
}'''

LIDL_HTML = (
    '<html><head><title>Praktikum Controlling International - BI Requirement'
    ' Engineering - Lidl</title>\n'
    '<script type="application/ld+json">' + LIDL_JSONLD_VERBATIM +
    '</script></head>\n<body>job page body</body></html>'
)

# Página viva SEM JSON-LD parseável (phenom/oracle-style: hidratação falha,
# vaga permanece com a descrição original — nunca piora).
NO_JSONLD_HTML = (
    '<html><head><title>Working Student - Other</title></head>'
    '<body>rendered by JS</body></html>'
)

LIDL_ID = "Lidl Stiftung & Co. KG|praktikum_info:13308116"
LIDL_URL = ("https://www.praktikum.info/stellenangebote/13308116-p-praktikum-"
            "controlling-international-bi-requirement-engineering")

LONG_DESC = "logistics procurement supply chain SAP " * 40  # > 500 chars


def _long_job(i: int, company: str, score: float) -> dict:
    return {
        "id": f"{company}|sf_dataset:x:{i}", "company": company,
        "title": f"Praktikum Supply Chain {i}",
        "url": f"https://jobs.example.com/long/{i}",
        "description": LONG_DESC, "score": score,
        "location": "Berlin, DE", "posted_at": "2026-10-01",
    }


def _blind_job(jid: str, company: str, score: float, url: str) -> dict:
    return {
        "id": jid, "company": company, "title": f"Praktikum {company}",
        "url": url, "description": None, "score": score,
        "location": "Hamburg, DE", "posted_at": "2026-10-01",
    }


def _lidl_job(score: float = 9.0) -> dict:
    # Campos do snapshot real (score 9.0, description vazia) — a vaga da card.
    return {
        "id": LIDL_ID, "company": "Lidl Stiftung & Co. KG",
        "title": "Praktikum Controlling International - BI Requirement "
                 "Engineering",
        "url": LIDL_URL, "description": None, "score": score,
        "location": "Neckarsulm", "posted_at": "2026-10-17",
    }


def _universe() -> list:
    """Universo com top exibido CHEIO (100) + cegas fora da janela F20.

    55 empresas × 2 vagas longas = 110 → apply_company_cap admite 100;
    as cegas (score abaixo) ficam todas FORA do top exibido.
    """
    jobs: list = []
    n = 0
    for c in range(55):
        for k in range(2):
            jobs.append(_long_job(n, f"Firma {c} GmbH", 200.0 - n))
            n += 1
    for i in range(5):
        jobs.append(_blind_job(f"blind{i}", f"Blind Corp {i}", 15.0 - i,
                               f"https://jobs.example.com/blind/{i}"))
    jobs.append(_lidl_job())
    jobs.append(_blind_job("dead-410", "Dead Corp", 8.0,
                            "https://jobs.example.com/410-dead"))
    return jobs


class _Resp:
    """Fake de resposta HTTP com corpo e URL final."""

    def __init__(self, body: bytes, url: str):
        self._body = body
        self.url = url

    def read(self, n: int = -1) -> bytes:
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _make_opener(calls: list, *, dead_status: "dict | None" = None):
    """Opener fake: Lidl serve o JSON-LD verbatim; '410' morre; resto vivo
    sem JSON-LD. Registra cada request em ``calls`` (ordem auditável)."""
    dead_status = dead_status or {}

    def opener(req, timeout=None):
        url = req.full_url
        calls.append(url)
        if "410" in url:
            raise urllib.error.HTTPError(
                url, dead_status.get(url, 410), "Gone", {}, None)
        if "13308116" in url:
            return _Resp(LIDL_HTML.encode("utf-8"), url)
        return _Resp(NO_JSONLD_HTML.encode("utf-8"), url)

    return opener


def _write_universe(data_dir: Path, jobs: list) -> None:
    (data_dir / "eligible_jobs.json").write_text(
        json.dumps(jobs), encoding="utf-8")


class _EnvBudget:
    """Context manager: seta a env do budget e restaura no fim."""

    def __init__(self, value):
        self._value = value

    def __enter__(self):
        self._old = os.environ.get(rd.HYDRATION_BUDGET_ENV_FLAG)
        if self._value is None:
            os.environ.pop(rd.HYDRATION_BUDGET_ENV_FLAG, None)
        else:
            os.environ[rd.HYDRATION_BUDGET_ENV_FLAG] = str(self._value)
        return self

    def __exit__(self, *a):
        if self._old is None:
            os.environ.pop(rd.HYDRATION_BUDGET_ENV_FLAG, None)
        else:
            os.environ[rd.HYDRATION_BUDGET_ENV_FLAG] = self._old
        return False


# ---------------------------------------------------------------------------
# A. Gate do budget (puro)
# ---------------------------------------------------------------------------

def test_budget_gate() -> None:
    section("A: gate INTERNSHIP_FINDER_HYDRATION_BUDGET (flag-gated, regra 9)")
    with tempfile.TemporaryDirectory(prefix="t_f65_gate_") as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text("INTERNSHIP_FINDER_HYDRATION_BUDGET=25\n",
                            encoding="utf-8")
        with _EnvBudget(None):
            check("env ausente + sem .env => 0 (default OFF)",
                  rd._hydration_budget(Path(tmp) / "inexistente.env") == 0)
            check("env ausente + .env=25 => 25 (padrão F1: arquivo lê)",
                  rd._hydration_budget(env_file) == 25)
        with _EnvBudget("50"):
            check("env=50 => 50",
                  rd._hydration_budget(Path(tmp) / "inexistente.env") == 50)
            check("env=50 TEM PRECEDÊNCIA sobre .env=25",
                  rd._hydration_budget(env_file) == 50)
        for bad in ("abc", "", "-5", "3.7", "  "):
            with _EnvBudget(bad):
                check(f"env inválida {bad!r} => 0 (fail-safe OFF)",
                      rd._hydration_budget(env_file) == 25
                      if False else
                      rd._hydration_budget(
                          Path(tmp) / "inexistente.env") == 0)
        with _EnvBudget(None):
            env_file.write_text(
                "INTERNSHIP_FINDER_HYDRATION_BUDGET=-7\n", encoding="utf-8")
            check(".env negativo => 0",
                  rd._hydration_budget(env_file) == 0)
            env_file.write_text(
                "INTERNSHIP_FINDER_HYDRATION_BUDGET=xyz\n", encoding="utf-8")
            check(".env inválido => 0",
                  rd._hydration_budget(env_file) == 0)
            env_file.write_text(
                "INTERNSHIP_FINDER_HYDRATION_BUDGET=  7  \n", encoding="utf-8")
            check(".env com espaços => 7 (strip)",
                  rd._hydration_budget(env_file) == 7)
        env_file.write_text("chave=quebrada sem newline\n",
                            encoding="utf-8")
        with _EnvBudget(None):
            check(".env sem a chave => 0",
                  rd._hydration_budget(env_file) == 0)
        # config_path None + env ausente => 0 (nunca explode)
        with _EnvBudget(None):
            check("config_path=None + env ausente => 0",
                  rd._hydration_budget(None) == 0)


# ---------------------------------------------------------------------------
# B. Candidatas da janela estendida (pura)
# ---------------------------------------------------------------------------

def test_candidates() -> None:
    section("B: candidatas — fora do top exibido, desc curta, ordem oficial")
    ranking = _universe()
    shown = rd.minimal_page.apply_company_cap(ranking)
    shown_ids = {str(j["id"]) for j in shown}
    check("universo fixture: top exibido = 100 (cap 2/empresa)",
          len(shown) == 100)
    cands = rd._extended_hydration_candidates(ranking, shown_ids)
    ids = [j["id"] for j in cands]
    check("7 cegas fora do topo (5 blind + Lidl + dead)",
          len(cands) == 7)
    check("Lidl 13308116 é candidata (a vaga da card)",
          LIDL_ID in ids)
    check("ordem = ordem oficial do ranking (score desc; blind0..4, "
          "Lidl, dead)", ids == ["blind0", "blind1", "blind2", "blind3",
                                 "blind4", LIDL_ID, "dead-410"])
    check("top exibido NUNCA entra (shown_ids excluídos)",
          not (set(ids) & shown_ids))
    # topo com desc curta também fica fora (janela da F20 é dona do topo)
    short_top = dict(ranking[0])
    short_top["description"] = "curta"
    ranking2 = [short_top] + ranking[1:]
    shown2 = rd.minimal_page.apply_company_cap(ranking2)
    cands2 = rd._extended_hydration_candidates(
        ranking2, {str(j["id"]) for j in shown2})
    check("vaga do TOPO com desc curta continua fora (sem double fetch)",
          short_top["id"] not in [j["id"] for j in cands2])
    # desc longa fora do topo não é candidata
    long_out = _blind_job("long-out", "Long Corp", 1.0,
                          "https://jobs.example.com/x")
    long_out["description"] = LONG_DESC
    cands3 = rd._extended_hydration_candidates(
        ranking + [long_out], shown_ids)
    check("desc longa fora do topo NÃO é candidata",
          "long-out" not in [j["id"] for j in cands3])
    # description vazia ("") conta como cega; id vazio ignorado; não-dict ok
    weird = [{"id": "", "url": "https://x", "description": None},
             "não-dict",
             {"id": "empty-desc", "url": "https://x", "description": ""},
             {"id": "short-desc", "url": "https://x", "description": "abc"}]
    cands4 = rd._extended_hydration_candidates(weird, set())
    check("id vazio e não-dict ignorados; ''/curta são candidatas",
          [j["id"] for j in cands4] == ["empty-desc", "short-desc"])
    cands5 = rd._extended_hydration_candidates(weird, set(),
                                                short_description_limit=2)
    check("limite custom respeitado (<2 chars: só a vazia é candidata; "
          "'abc' tem 3)",
          [j["id"] for j in cands5] == ["empty-desc"])


# ---------------------------------------------------------------------------
# C. Estágio offline (fake opener) — contra-casos da card
# ---------------------------------------------------------------------------

def test_stage_offline() -> None:
    section("C: estágio offline — OFF byte-identical, teto, Lidl verbatim, "
            "mortas, idempotência")

    with tempfile.TemporaryDirectory(prefix="t_f65_stage_") as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        metrics = data_dir / "collection_metrics.jsonl"

        # --- C1: OFF (budget 0) = kill switch total -------------------------
        _write_universe(data_dir, _universe())
        before = (data_dir / "eligible_jobs.json").read_bytes()
        calls: list = []
        opener = _make_opener(calls)
        with _EnvBudget(None):
            rec = rd._run_extended_hydration(
                data_dir, metrics, config_path=Path(tmp) / ".env",
                opener=opener)
        check("OFF: retorna {'budget': 0, 'status': 'off'}",
              rec == {"budget": 0, "status": "off"})
        check("OFF: NENHUM fetch (opener intocado)", not calls)
        check("OFF: JSON byte-identical (nenhuma escrita)",
              (data_dir / "eligible_jobs.json").read_bytes() == before)
        check("OFF: nenhuma métrica gravada", not metrics.exists())

        # --- C2: teto respeitado — exatamente N fetches, as N melhores -----
        calls.clear()
        with _EnvBudget("3"):
            rec = rd._run_extended_hydration(
                data_dir, metrics, config_path=Path(tmp) / ".env",
                opener=opener)
        check("budget=3: exatamente 3 fetches (teto da card)",
              len(calls) == 3 and rec["fetched"] == 3)
        check("budget=3: as 3 melhores por score (blind/0,1,2)",
              [u.rsplit("/", 1)[-1] for u in calls] == ["0", "1", "2"])
        check("budget=3: 7 cegas contadas no pool (blind_candidates)",
              rec["blind_candidates"] == 7)
        check("budget=3: 0 hidratadas (páginas sem JSON-LD) + falhas contadas",
              rec["hydrated"] == 0 and rec["hydration_failed"] == 3)
        check("budget=3: métrica extended_hydration gravada (auditável)",
              json.loads(metrics.read_text(encoding="utf-8").splitlines()[-1])
              ["type"] == "extended_hydration")

        # --- C3: cobertura total — Lidl VERBATIM hidrata ------------------
        calls.clear()
        with _EnvBudget("10"):
            rec = rd._run_extended_hydration(
                data_dir, metrics, config_path=Path(tmp) / ".env",
                opener=opener)
        out = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        lidl = next(j for j in out if j["id"] == LIDL_ID)
        dead = next(j for j in out if j["id"] == "dead-410")
        check("budget=10: 7 fetches (pool inteiro), 1 hidratada (Lidl), "
              "1 morta VISTA",
              rec["fetched"] == 7 and rec["hydrated"] == 1
              and rec["dead_seen"] == 1)
        check("Lidl: description hidratada == 2147 chars (parser real, "
              "fixture congelada)",
              len(lidl["description"]) == 2147)
        check("Lidl: 'Sehr gute Deutschkenntnisse' verbatim no texto "
              "hidratado (a frase da evidência F60)",
              "Sehr gute Deutschkenntnisse" in lidl["description"])
        check("Lidl: provenance hydrated_extended (distinta da top-N)",
              lidl["description_source"] == "hydrated_extended"
              and rd.HYDRATION_SOURCE_EXTENDED == "hydrated_extended")
        check("Lidl: description_hydrated_at ISO UTC presente "
              "(formato utcnow_iso, sufixo '+00:00')",
              str(lidl.get("description_hydrated_at", ""))
              .endswith("+00:00")
              and "T" in str(lidl.get("description_hydrated_at")))
        check("Lidl: detector F60 VÊ o texto => german_required (flag F20)",
              lidl.get(rd.HYDRATION_INAPPLICABLE_FLAG) == "german_required")
        check("Lidl: score RE-SCOREADO pela F56 (9.0 -> 7.96 no fixture)",
              abs(float(lidl["score"]) - 7.96) < 0.01)
        original_dead = next(j for j in _universe() if j["id"] == "dead-410")
        check("mortas do passe estendido: CONTADAS mas NUNCA marcadas "
              "(dict da dead-410 byte-identical ao original — semântica "
              "de morte pertence à janela do topo)",
              dead == original_dead)
        check("CSV acompanhou o re-score (score é coluna do contrato)",
              (data_dir / "eligible_jobs.csv").exists())
        csv_text = (data_dir / "eligible_jobs.csv").read_text(
            encoding="utf-8")
        check("CSV: linha da Lidl com o score re-scoreado",
              "7.96" in csv_text)
        check("ordem do JSON continua score desc (reordenação F56)",
              [j["score"] for j in out] == sorted(
                  (j["score"] for j in out), reverse=True))
        check("métrica: contadores completos (budget/candidates/fetched/"
              "hydrated/dead_seen/by_reason/hydrated_ids)",
              rec["by_reason"] == {"german_required": 1}
              and rec["hydrated_ids"] == [LIDL_ID]
              and rec["newly_inapplicable"] == 1
              and rec["budget"] == 10 and rec["blind_candidates"] == 7)
        check("métrica: registro incremental (3 registros: 3, 7… ordem)",
              [json.loads(l)["fetched"] for l in
               metrics.read_text(encoding="utf-8").splitlines()]
              == [3, 7])

        # --- C4: F37.3 varre o german_required revelado (classe fecha) ----
        ranking_after = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        excl = rd._remove_json_excluded(ranking_after)
        check("F37.3 (mesma semântica do main): Lidl german_required SAIU "
              "do JSON — a classe Lidl fecha",
              excl["removed"] == 1
              and all(j["id"] != LIDL_ID for j in ranking_after))

        # --- C5: idempotência — hidratada não re-fetcha --------------------
        calls.clear()
        with _EnvBudget("10"):
            rec2 = rd._run_extended_hydration(
                data_dir, metrics, config_path=Path(tmp) / ".env",
                opener=opener)
        check("re-run: Lidl hidratada (desc longa) NÃO é re-fetchada",
              not any("13308116" in u for u in calls))
        check("re-run: 6 cegas restantes (Lidl saiu do pool; dead+5 blind)",
              rec2["blind_candidates"] == 6 and rec2["hydrated"] == 0)

        # --- C6: falha total de rede — nada marcado, nada hidratado --------
        err_calls: list = []

        def all_error_opener(req, timeout=None):
            err_calls.append(req.full_url)
            raise OSError("network down")

        data_dir2 = Path(tmp) / "data2"
        data_dir2.mkdir()
        _write_universe(data_dir2, _universe())
        metrics2 = data_dir2 / "collection_metrics.jsonl"
        with _EnvBudget("4"):
            rec3 = rd._run_extended_hydration(
                data_dir2, metrics2, config_path=Path(tmp) / ".env",
                opener=all_error_opener)
        out3 = json.loads(
            (data_dir2 / "eligible_jobs.json").read_text(encoding="utf-8"))
        check("falha total de rede: 4 tentativas, 0 hidratadas, 0 mortas",
              len(err_calls) == 4 and rec3["hydrated"] == 0
              and rec3["dead_seen"] == 0)
        check("falha total de rede: JSON intocado (nenhuma marca)",
              all(j.get("description_source") is None for j in out3)
              and not any(
                  rd.HYDRATION_INAPPLICABLE_FLAG in j for j in out3))

        # --- C7: sem cegas — baseline auditável sem fetch -------------------
        data_dir3 = Path(tmp) / "data3"
        data_dir3.mkdir()
        all_long = [_long_job(i, f"Firma {i} GmbH", 10.0 - i)
                    for i in range(10)]
        _write_universe(data_dir3, all_long)
        metrics3 = data_dir3 / "collection_metrics.jsonl"
        calls.clear()
        with _EnvBudget("10"):
            rec4 = rd._run_extended_hydration(
                data_dir3, metrics3, config_path=Path(tmp) / ".env",
                opener=opener)
        check("sem cegas: 0 fetches (budget intocado) e métrica baseline 0",
              not calls and rec4["fetched"] == 0
              and json.loads(metrics3.read_text(encoding="utf-8")
                             .splitlines()[-1])["hydrated"] == 0)

        # --- C8: budget via .env (integração do gate) -----------------------
        os.environ.pop(rd.HYDRATION_BUDGET_ENV_FLAG, None)
        env_file = Path(tmp) / ".env"
        env_file.write_text("INTERNSHIP_FINDER_HYDRATION_BUDGET=2\n",
                            encoding="utf-8")
        data_dir4 = Path(tmp) / "data4"
        data_dir4.mkdir()
        _write_universe(data_dir4, _universe())
        metrics4 = data_dir4 / "collection_metrics.jsonl"
        calls.clear()
        rd._run_extended_hydration(data_dir4, metrics4,
                                   config_path=env_file, opener=opener)
        check("budget via .env: 2 fetches (gate lê o arquivo — reativa "
              "sem editar crontab)", len(calls) == 2)


# ---------------------------------------------------------------------------
# D. E2E — integração no main() (offline, mocks herdados do test_f20)
# ---------------------------------------------------------------------------

def test_e2e_refresh() -> None:
    section("D: e2e rd.main() — estágio antes da F25/F37.3; gate pages_dir")
    from unittest import mock

    with tempfile.TemporaryDirectory(prefix="t_f65_e2e_") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir()
        jobs = _universe()
        _write_universe(data_dir, jobs)
        (data_dir / "collection_metrics.jsonl").write_text(
            json.dumps({"run_id": "r1", "type": "run", "status": "ok",
                        "total_collected": 400, "eligible": len(jobs)})
            + "\n", encoding="utf-8")
        # .env com o budget LIGADO cobrindo o pool inteiro (o dono reativa
        # sem tocar no crontab — padrão F1)
        (root / ".env").write_text(
            "INTERNSHIP_FINDER_HYDRATION_BUDGET=10\n", encoding="utf-8")

        calls = {"publish": [], "v2": []}

        def fake_publish(root_, pages, *, exit_code, eligible, run_id,
                         dead_link_ids=None, **kw):
            calls["publish"].append((dead_link_ids,
                                     kw.get("inapplicable_ids")))
            return True

        def fake_liveness(jobs_, **kw):
            return set()  # topo: nada morto, nada hidratado (compat F11)

        def fake_liveness_v2(jobs_, **kw):
            calls["v2"].append([j["id"] for j in jobs_])
            return (set(),
                    {LIDL_ID: "Sehr gute Deutschkenntnisse (C1) werden "
                              "vorausgesetzt. " * 5},
                    {"attempts": len(jobs_), "http_responses": len(jobs_),
                     "net_errors": 0, "soft_dead": 0, "dead": 0,
                     "hydrated": 1, "hydration_failed": 0,
                     "short_candidates": len(jobs_), "duration_s": 0.1,
                     "hard_dead_ids": set(), "hard_dead_status": {},
                     "soft_dead_ids": set()})

        def fake_run(*a, **k):
            import subprocess
            return subprocess.CompletedProcess(a[0], 0)

        original_root = rd.repo_root
        rd.repo_root = lambda: root
        try:
            with _EnvBudget(None), \
                 mock.patch.object(rd, "run_collection",
                                   side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd.url_liveness, "check_liveness",
                                   side_effect=fake_liveness), \
                 mock.patch.object(rd.url_liveness, "check_liveness_v2",
                                   side_effect=fake_liveness_v2), \
                 mock.patch.object(rd.publish_pages, "publish_ranking",
                                   side_effect=fake_publish), \
                 mock.patch.object(
                     rd, "notify_or_log",
                     side_effect=lambda c, m, *, dry_run: {"sent": True}):
                rc = rd.main(["--config", str(root / ".env"),
                              "--pages-dir", str(root / "pages"),
                              "--always-notify"])
        finally:
            rd.repo_root = original_root

        check("e2e: refresh termina exit 0 com o estágio F65 ligado",
              rc == 0)
        check("e2e: janela estendida chamada UMA vez com as cegas "
              "(budget 10 cobre as 7 do pool)",
              len(calls["v2"]) == 1 and len(calls["v2"][0]) == 7)
        out = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        ids_out = {str(j.get("id")) for j in out}
        check("e2e: Lidl german_required revelada pela janela estendida "
              "SAIU do JSON no MESMO run (F37.3 após F65)",
              LIDL_ID not in ids_out)
        check("e2e: cegas não-flaggadas permanecem no JSON",
              {"blind0", "blind1", "blind2", "blind3", "blind4"}
              <= ids_out)

        # métrica do run: registro extended_hydration (run_id real ou
        # fallback utcnow_iso — a rotação arquiva o metrics antes da
        # coleta fake, então o resumo do run não vê registros)
        recs = [json.loads(l) for l in
                (data_dir / "collection_metrics.jsonl").read_text(
                    encoding="utf-8").splitlines()]
        ext = [r for r in recs if r.get("type") == "extended_hydration"]
        check("e2e: métrica extended_hydration no JSONL do run "
              "(run_id sempre presente, budget 10)",
              len(ext) == 1 and bool(ext[0]["run_id"])
              and ext[0]["budget"] == 10 and ext[0]["hydrated"] == 1)

        # --- contra-caso: SEM --pages-dir o estágio nem roda (gate F20) ----
        calls["v2"].clear()
        data_dir5 = root / "data5"
        data_dir5.mkdir()
        _write_universe(data_dir5, _universe())
        (data_dir5 / "collection_metrics.jsonl").write_text(
            json.dumps({"run_id": "r2", "type": "run", "status": "ok",
                        "total_collected": 400, "eligible": 117}),
            encoding="utf-8")
        (root / ".env5").write_text(
            "INTERNSHIP_FINDER_HYDRATION_BUDGET=5\n", encoding="utf-8")
        rd.repo_root = lambda: root
        try:
            with _EnvBudget(None), \
                 mock.patch.object(rd, "run_collection",
                                   side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd.url_liveness, "check_liveness",
                                   side_effect=fake_liveness), \
                 mock.patch.object(rd.url_liveness, "check_liveness_v2",
                                   side_effect=fake_liveness_v2), \
                 mock.patch.object(rd.publish_pages, "publish_ranking",
                                   side_effect=fake_publish), \
                 mock.patch.object(
                     rd, "notify_or_log",
                     side_effect=lambda c, m, *, dry_run: {"sent": True}):
                rc2 = rd.main(["--config", str(root / ".env5"),
                               "--always-notify"])
        finally:
            rd.repo_root = original_root
        check("contra-caso: SEM --pages-dir => janela estendida NEM roda "
              "(mesmo gate de rede da F20/F11)",
              rc2 == 0 and not calls["v2"])


# ---------------------------------------------------------------------------
# E. Resumo A/B offline (contadores da card)
# ---------------------------------------------------------------------------

def test_ab_counters() -> None:
    section("E: mini A/B — contadores antes/depois (offline)")
    with tempfile.TemporaryDirectory(prefix="t_f65_ab_") as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        metrics = data_dir / "collection_metrics.jsonl"
        universe = _universe()
        _write_universe(data_dir, universe)
        before_blind = sum(
            1 for j in universe
            if not j.get("description")
            or len(str(j.get("description"))) < rd.HYDRATION_SHORT_LIMIT)
        calls: list = []
        with _EnvBudget("10"):
            rec = rd._run_extended_hydration(
                data_dir, metrics, config_path=Path(tmp) / ".env",
                opener=_make_opener(calls))
        after = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        after_blind = sum(
            1 for j in after
            if not j.get("description")
            or len(str(j.get("description"))) < rd.HYDRATION_SHORT_LIMIT)
        cured = before_blind - after_blind
        flagged = sum(
            1 for j in after if j.get(rd.HYDRATION_INAPPLICABLE_FLAG))
        ranking_after = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        excl = rd._remove_json_excluded(ranking_after)
        check(f"A/B: {before_blind} cegas -> {after_blind} "
              f"({cured} curadas = Lidl)",
              before_blind == 7 and cured == 1 and rec["hydrated"] == 1)
        check("A/B: 1 NOVA flag acesa pelos detectores (german_required — "
              "expectativa da card)",
              flagged == 1 and rec["newly_inapplicable"] == 1)
        check(f"A/B: {excl['removed']} exclusão(ões) no sweep F37.3 "
              "(novas exclusões documentadas)",
              excl["removed"] == 1
              and excl["by_reason"] == {"german_required": 1})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    # F65 (hotfix 20/10): pino do `now` do re-score F56 durante TODO o teste
    # — intercepta `rescore_hydrated_jobs` no namespace de refresh_daily e
    # força o _FROZEN_NOW (o argumento now=datetime.now(UTC) da linha 1735
    # é sobrescrito). Restore no finally: produção NUNCA é afetada.
    _orig_rescore = rd.rescore_hydrated_jobs

    def _frozen_rescore(jobs, hydrated_ids, *, now=None, **kw):
        return _orig_rescore(jobs, hydrated_ids, now=_FROZEN_NOW, **kw)

    rd.rescore_hydrated_jobs = _frozen_rescore
    try:
        test_budget_gate()
        test_candidates()
        test_stage_offline()
        test_e2e_refresh()
        test_ab_counters()
    finally:
        rd.rescore_hydrated_jobs = _orig_rescore
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
