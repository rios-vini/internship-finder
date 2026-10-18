''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F50 — reaberturas flag-gated do enriquecimento: decisões COM EVIDÊNCIA.

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f50.py`` e ``python scripts/test_f50.py`` rodam
a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

Decisões da fase (medição ao vivo 18/10, universo real, data/ intocado —
zero rede nesta suíte; fixtures VERBATIM do que foi medido):

1. OFFICIAL_PAGE via JSON-LD do dataset: **MANTER DESLIGADA**. O corpus
   (108.143 records) tem ZERO blocos JSON-LD: 0 ocorrências de
   ``ld+json``/``@type`` em descriptions e no ``raw.raw`` do sf_dataset
   (scan completo); 0/108.143 records com campo ``official_page``; 0/779
   no archive mais antigo disponível (archives cobrem só 7 dias pós-F1).
   Os campos estruturados do ``raw`` (salary 23.803, lat/lon 20.921,
   deadline 32.038) JÁ têm display com proveniência honesta própria
   (Fase B/structured_fields, job_salary, deadline_kind) — derivar
   "official_page" deles duplicaria display e quebraria o contrato da view
   (labels afirmam VERIFICAÇÃO por GET). Reabrir o estágio GET = 150
   GETs/dia pelo valor medido zero da F1 (0 descriptions melhoradas).
   Trava: pipeline com o estágio OFF nunca emite ``official_page``; job
   real do dataset nunca ganha view/chip de página oficial (grupo A).

2. ENRIQUECIMENTO LLM: **REABRIR COM REPARO** (default continua OFF).
   Valor medido: 11/11 records utilizáveis do store têm ≥1 conceito WA
   com evidência (10/11 idioma; 3/11 salário literal) — cobertura
   semântica que nenhum detector textual dá (Fase H: 100% not_mentioned).
   Custo: calibração com 1 payload REAL tentada 18/10 — bloqueada pelo
   muro 429 do glm-5.3-flash (fast-fail 0,37s ×3 tentativas; cenário
   codificado no check B4); estimativa da classe: F34 mediu low=23s vs
   max≈504s no mesmo payload. Reparo obrigatório embarcado: o call-site
   do runner passava ``reasoning_effort`` NENHUM → endpoint NIM aplica
   default ``max`` → a causa-classe do zumbi de 5h38/0 extrações (F1).
   Agora toda chamada envia ``low`` (env ajusta; vazia = histórico).
   Risco limitado pelo desenho F1: teto 1800s, store atômico, flock,
   exit do refresh intocável, view-only no display (nunca ranking).

3. GEOCODING: **MANTER DESLIGADA POR VALOR + REPARO DO CANAL MORTO**.
   DUAS pontas mortas medidas ao vivo: (a) o parser lia
   ``country_code`` no TOPO do resultado — a API /search só devolve o
   campo DENTRO de ``address`` e só com ``addressdetails=1`` → TODA
   consulta devolvia None (probe: 0/12 locations alemãs, incl.
   Cologne/Munich; pós-reparo 15/20, controles cn/nl/br/ph fora);
   (b) nenhum código de produção construía o ``NominatimGeocoder`` —
   com a flag ON a consulta morria no ``geocoder is None``. Reparos:
   ``addressdetails=1`` + leitura de ``address.country_code`` +
   construção LAZY após o gate (OFF nunca constrói). Valor medido
   pós-reparo: pool de 487 candidatas alemãs None-ISO (recentes) →
   apenas 3 sobrevivem a TODOS os filtros (SICK Pflichtpraktikum
   Waldkirch; 0,4% do eligible de 736) — não justifica rede no cron.
   Flip futuro = 1 env var, com o backlog (~2.278 locations × 1s/s)
   amortizando no cache a partir do 2º run.

Uso:  bash scripts/test_f50.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from internship_finder import present_official  # noqa: E402
from internship_finder.geocoding import (  # noqa: E402
    GEOCODING_ENV,
    GeocodingCache,
    NominatimGeocoder,
    CountryResolver,
    is_geocoding_enabled,
    set_geocoding_enabled,
)
from internship_finder.enrichment.fetch import FetchResult  # noqa: E402
from internship_finder.enrichment.runner import (  # noqa: E402
    DEFAULT_REASONING_EFFORT,
    REASONING_EFFORT_ENV,
    PlanItem,
    reasoning_effort,
    run_incremental,
)
from internship_finder.enrichment.store import EnrichmentStore  # noqa: E402
from internship_finder.official_page import parse_jsonld_blocks  # noqa: E402
import internship_finder.cli as cli_mod  # noqa: E402
import internship_finder.geocoding as geo_mod  # noqa: E402
import internship_finder.enrichment.llm as enr_llm  # noqa: E402
import internship_finder.enrichment.fetch as fetch_mod  # noqa: E402
import refresh_daily  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM — dados reais medidos 18/10 (universo de produção,
# leitura read-only; data/ intocado). Nada aqui é inventado.
# ---------------------------------------------------------------------------

# Record REAL do corpus (successfactors:jobs, o survivor da simulação de
# recuperação geocoding): id/company/title/location/url/description
# copiados sem alteração. country_iso None de verdade (é o caso perdido).
F_SICK_JOB = {
    "id": "SICK|successfactors:jobs:1442684633",
    "company": "SICK",
    "title": "Pflichtpraktikum im Bereich Software Test & Test Automation (Waldkirch (bei Freiburg), Waldkirch (bei Freiburg), Waldkirch (bei Freiburg), Waldkirch )",
    "location": "Waldkirch (bei Freiburg), Waldkirch (bei Freiburg), Waldkirch (bei Freiburg), Waldkirch",
    "source": "successfactors:jobs",
    "url": "https://jobs.sick.com/job/Waldkirch-%28bei-Freiburg%29-Pflichtpraktikum-im-Bereich-Software-Test-&-Test-Automation-Wald-Waldkirch/1442684633/",
    "employment_type": None,
    "country_iso": None,
    "country": None,
    "collected_at": "2026-10-18T09:09:19.896933Z",
    "posted_at": None,
    "remote": None,
    "internship": True,
    "external_id": "1442684633",
    "application_deadline": None,
    "description_source": None,
    "description": "Sommersemester 2027 – befristet auf 3–6 Monate IHRE AUFGABEN: Sie unterstützen bei projektspezifischen Verifikations- und Validierungsaktivitäten Sie bereiten Software- und Systemtests vor, führen diese durch und dokumentieren die Ergebnisse Sie erstellen und pflegen Testdaten, Testumgebungen und Testfälle Sie analysieren Fehler und verfolgen deren Behebung in Zusammenarbeit mit Entwicklungs- und Testteams Sie entwickeln bestehende Module eines automatisierten Testframeworks auf Basis von Google Test (GTest) weiter Sie implementieren, optimieren und warten automatisierte Tests und tragen damit zur Verbesserung von Testabdeckung und Testeffizienz bei Sie arbeiten an zukunftsorientierten Test- und Automatisierungslösungen im Umfeld von Continuous Integration und Continuous Delivery (CI/CD) mit Sie erstellen technische Dokumentationen und Auswertungen im Rahmen der Testaktivitäten IHR PROFIL: Studium der Informatik, Software Engineering, Elektrotechnik oder eines vergleichbaren technischen Studiengangs Erste Programmiererfahrung, idealerweise in C++ Grundkenntnisse in objektorientierter Softwareentwicklung von Vorteil Interesse an Softwaretest, Testautomatisierung und CI/CD Strukturierte und selbstständige Arbeitsweise Ausgeprägte Teamfähigkeit und Freude an der Zusammenarbeit mit Entwicklungs- und Testteams Kontakt: Sarah Disch",
}

# Resposta REAL do Nominatim (probe 18/10, addressdetails=1) para
# "Heidenheim, BW (DE)" — a location perdida mais frequente do corpus
# (109 records). Copiada sem alteração: é o shape que a API devolve.
F_HEIDENHEIM_NOMINATIM = [{
    "place_id": 127796801,
    "licence": "Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright",
    "osm_type": "relation",
    "osm_id": 2791896,
    "lat": "48.6767637",
    "lon": "10.1529230",
    "class": "boundary",
    "type": "administrative",
    "place_rank": 16,
    "importance": 0.5380582956255238,
    "addresstype": "town",
    "name": "Heidenheim an der Brenz",
    "display_name": "Heidenheim an der Brenz, VVG der Stadt Heidenheim an der Brenz, Landkreis Heidenheim, Baden-Württemberg, Germany",
    "address": {
        "town": "Heidenheim an der Brenz",
        "municipality": "VVG der Stadt Heidenheim an der Brenz",
        "county": "Landkreis Heidenheim",
        "state": "Baden-Württemberg",
        "ISO3166-2-lvl4": "DE-BW",
        "country": "Germany",
        "country_code": "de",
    },
    "boundingbox": ["48.6436140", "48.7832977", "10.1023345", "10.2792248"],
}]

# Prefixo VERBATIM da resposta REAL do Nominatim para "Cologne" SEM
# addressdetails (probe 18/10 — o formato que o código antigo consumia):
# o corpo NÃO tem country_code em NENHUM nível. É a falha exata do bug.
F_PRE_ADDRESSDETAILS = [{
    "place_id": 116309321,
    "licence": "Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright",
    "osm_type": "relation",
    "osm_id": 62578,
    "lat": "50.9383610",
    "lon": "6.9599740",
    "class": "boundary",
}]

# Prefixo VERBATIM (600 chars, como medido) do ``raw.raw`` REAL de um record
# sf_dataset (o único lugar do corpus com payload bruto embutido): JSON do
# upstream, sem bloco JSON-LD — o scan achou 0/23.764 com "JobPosting".
F_SF_RAWRAW = (
    "{\"business_category\": \"aws\", \"job_family\": \"Solution Architect\", \"basic_qualifications\": \"- Currently enrolled in penultimate or final year of a Bachelor's or Master's degree in Computer Science, Engineering, or related technical field, graduating in 2027 or 2028<br/>- Speak, write, and read fluently in English at C1 level or above<br/>- Speak, write, and read fluently in French at C1 level or above<br/>- Experience with at least one modern programming language (such as Python, Java, C++, or JavaScript)<br/>- Right to work in France for the duration of the internship<br/>- Understanding of bas"
    # prefixo VERBATIM de 600 chars, como medido no scan 18/10
)

# Resposta LLM no shape exato do contrato (schema.py): usada apenas para
# exercitar NOSSO código (runner/store) — nada de rede, nada de LLM.
LLM_OK = {
    "student_status_required": {
        "value": "true",
        "evidence": "Voraussetzung fuer das Praktikum ist die Immatrikulation an einer Hochschule",
        "confidence": "high",
    },
    "work_authorization_required": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "existing_work_authorization_required": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "work_permit_required": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "residence_permit_required": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "visa_sponsorship": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "international_candidates_explicitly_accepted": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "eu_citizenship_required": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "internship_compatible": {
        "value": "true",
        "evidence": "Pflichtpraktikum im Bereich Software Test Waldkirch",
        "confidence": "high",
    },
    "salary": {"value": None, "period": None, "currency": None, "evidence": None, "confidence": None},
    "work_mode": {"value": "not_mentioned", "evidence": None, "confidence": None},
    "location": {"value": None, "evidence": None, "confidence": None},
    "german_requirement": {"level": "not_mentioned", "evidence": None, "confidence": None},
    "english_requirement": {"level": "not_mentioned", "evidence": None, "confidence": None},
    "employer_deadline": {"date": None, "evidence": None, "confidence": None},
    "page_is_job_posting": {
        "value": True,
        "evidence": "Pflichtpraktikum im Bereich Software Test Waldkirch",
        "confidence": "high",
    },
}


# ---------------------------------------------------------------------------
# Sanidade dos fixtures (verbatim de verdade)
# ---------------------------------------------------------------------------

check("0.1 SICK record real: country_iso None e SEM chave official_page",
      F_SICK_JOB.get("country_iso") is None and "official_page" not in F_SICK_JOB)
check("0.2 Nominatim real (addressdetails): address.country_code == 'de'",
      F_HEIDENHEIM_NOMINATIM[0]["address"]["country_code"] == "de")
check("0.3 Nominatim pre-reparo: SEM country_code em qualquer nivel (o bug)",
      "country_code" not in json.dumps(F_PRE_ADDRESSDETAILS))


# ---------------------------------------------------------------------------
# A. Feature 1 — OFFICIAL_PAGE via JSON-LD do dataset: MANTER DESLIGADA
# ---------------------------------------------------------------------------

view_a = present_official.official_view(F_SICK_JOB)
check("A1 job real do dataset (so raw) -> official_view None (sem GET nao ha view)",
      view_a is None)
check("A1b lines vazias e chip None (display honesto sem verificacao)",
      present_official.lines(view_a) == [] and present_official.chip(view_a) is None)
check("A2 conteudo real do corpus tem ZERO blocos JSON-LD (premissa da feature e falsa)",
      parse_jsonld_blocks(F_SF_RAWRAW) == []
      and parse_jsonld_blocks(F_SICK_JOB["description"]) == [])

# A3: pipeline com o estagio OFF (default) NUNCA emite official_page — se
# alguem derivar o campo do raw no futuro, este check quebra (keep-off).
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "eligible.json"
    orig_op = cli_mod.enrich_official_pages
    def _bomb(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("estagio official_page rodou com o default OFF")
    cli_mod.enrich_official_pages = _bomb
    try:
        from internship_finder.cli import run_filter_pipeline
        rc = run_filter_pipeline(
            [dict(F_SICK_JOB)],
            student=True, area=False, country="all",
            output=out, dedup=True, rank=True, hydrate=False,
        )
    finally:
        cli_mod.enrich_official_pages = orig_op
    payload = json.loads(out.read_text(encoding="utf-8"))
    check("A3 pipeline default: rc=0 e saida SEM official_page em qualquer job",
          rc == 0 and isinstance(payload, list)
          and all("official_page" not in (r or {}) for r in payload))


# ---------------------------------------------------------------------------
# B. Feature 2 — LLM enrichment: call-site agora envia reasoning_effort
# ---------------------------------------------------------------------------

_SAVED_ENV = {k: os.environ.get(k) for k in (GEOCODING_ENV, REASONING_EFFORT_ENV)}
os.environ.pop(REASONING_EFFORT_ENV, None)
os.environ.pop(GEOCODING_ENV, None)

check("B1 default do call-site: reasoning_effort() == 'low' (nunca o max do endpoint)",
      reasoning_effort() == "low" and DEFAULT_REASONING_EFFORT == "low")
try:
    os.environ[REASONING_EFFORT_ENV] = "high"
    check("B2a env 'high' respeitada (ajuste sem deploy)", reasoning_effort() == "high")
    os.environ[REASONING_EFFORT_ENV] = ""
    check("B2b env VAZIA -> None (comportamento historico, escape de A/B)",
          reasoning_effort() is None)
finally:
    os.environ.pop(REASONING_EFFORT_ENV, None)


def _mk_job():
    return {
        "id": "TeamPicnic|greenhouse:teampicnic:6337034",
        "company": "TeamPicnic",
        "title": "Working Student Procurement",
        "url": "https://jobs.example/6337034",
        "source": "greenhouse:teampicnic",
        "score": 10.0,
        "external_id": "6337034",
    }


def _fake_fetch(url, transport=None):
    body = ("<html><body><p>TeamPicnic Working Student Procurement Berlin. "
            + "Werkstudent Aufgaben Projekte Einkauf Beschaffung " * 20
            + "</p></body></html>")
    return FetchResult(200, url, body, None)


def _run_with_extract(job, extract_fake):
    """run_incremental de 1 vaga com fetch/LLM stubados; devolve (summary, records)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = EnrichmentStore(Path(tmp) / "enrichment_results.jsonl")
        plan = [PlanItem(job=dict(job), bucket="new", record=None)]
        orig_extract, orig_fetch = enr_llm.extract, fetch_mod.fetch_page
        enr_llm.extract = extract_fake
        fetch_mod.fetch_page = _fake_fetch
        try:
            summary = run_incremental(
                plan, "key-de-teste", store, limit=1, top_n=None,
                sleep_fetch=0.0, log=lambda *a, **k: None,
            )
            records = store.load()
        finally:
            enr_llm.extract = orig_extract
            fetch_mod.fetch_page = orig_fetch
        return summary, records


captured: dict = {}
def _ok_extract(key, prompt, **kwargs):
    captured.clear()
    captured.update(kwargs)
    return (json.loads(json.dumps(LLM_OK)), {"prompt_tokens": 1200, "completion_tokens": 400}, 1.0, 1, None)

summary_b3, records_b3 = _run_with_extract(_mk_job(), _ok_extract)
rec_b3 = records_b3[_mk_job()["id"]]
check("B3a call-site envia reasoning_effort='low' em TODA chamada (fix F34)",
      captured.get("reasoning_effort") == "low")
check("B3b extracao ok contada no resumo", summary_b3["extractions_ok"] == 1)
check("B3c record de sucesso persistido (extracted_at presente)",
      rec_b3.get("extracted_at") is not None)

# B4: o cenario MEDIDO em 18/10 — muro 429 do flash (fast-fail 0,37s x3):
# falha por vaga e contada, o run segue, exit intacto, record de falha.
def _wall_extract(key, prompt, **kwargs):
    return (None, None, 0.37, 3, "http_429")

summary_b4, records_b4 = _run_with_extract(_mk_job(), _wall_extract)
rec_b4 = records_b4[_mk_job()["id"]]
check("B4a muro 429 (medido 18/10): falha contada, run nao derrubado",
      summary_b4["extractions_fail"] == 1 and summary_b4["llm_calls"] == 1)
check("B4b degradacao graciosa: record de falha sem extracted_at, erro auditavel",
      rec_b4.get("extracted_at") is None and "http_429" in str(rec_b4.get("error")))


# ---------------------------------------------------------------------------
# C. Feature 3 — geocoding: reparo do canal morto (flag continua OFF)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload

class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.captured = []
    def get(self, url, params=None, headers=None, timeout=None):
        self.captured.append(dict(params or {}))
        return _FakeResp(self.payload)

sess = _FakeSession(F_HEIDENHEIM_NOMINATIM)
geo = NominatimGeocoder(session=sess, rate_limit_seconds=0.0)
cc = geo.country_code("Heidenheim, BW (DE)")
check("C1 consulta pede addressdetails=1 (o reparo da 1a ponta morta)",
      sess.captured and sess.captured[-1].get("addressdetails") == "1")
check("C2 country_code le address.country_code (fixture real) -> 'de'",
      cc == "de")

sess_old = _FakeSession(F_PRE_ADDRESSDETAILS)
geo_old = NominatimGeocoder(session=sess_old, rate_limit_seconds=0.0)
check("C3 shape REAL pre-reparo (sem country_code) -> None: o bug nao regressa",
      geo_old.country_code("Cologne") is None)

set_geocoding_enabled(False)
_built: list[int] = []
class _BombGeo:
    def __init__(self):
        _built.append(1)
        raise AssertionError("geocoder construido com a flag OFF")
_orig_cls = geo_mod.NominatimGeocoder
geo_mod.NominatimGeocoder = _BombGeo
try:
    with tempfile.TemporaryDirectory() as tmp:
        cache_c4 = GeocodingCache(Path(tmp) / "c4.json")
        res_c4 = CountryResolver(cache=cache_c4)
        iso_c4 = res_c4.resolve("CityOnTheMoonXYZ")
    check("C4 flag OFF: nada construido, nada consultado, None, cache intocado",
          iso_c4 is None and not _built
          and not cache_c4.contains("CityOnTheMoonXYZ"))
finally:
    geo_mod.NominatimGeocoder = _orig_cls
    set_geocoding_enabled(False)

_built_lazy: list[int] = []
class _FakeGeoLazy:
    def __init__(self):
        _built_lazy.append(1)
    def country_code(self, location):
        return "de"
geo_mod.NominatimGeocoder = _FakeGeoLazy
set_geocoding_enabled(True)
try:
    with tempfile.TemporaryDirectory() as tmp:
        cache_c5 = GeocodingCache(Path(tmp) / "c5.json")
        res_c5 = CountryResolver(cache=cache_c5)  # geocoder=None -> lazy
        iso1 = res_c5.resolve("SmallGermanTown")
        iso2 = res_c5.resolve("SmallGermanTown")
    check("C5 flag ON: geocoder construido LAZILY 1x (2a ponta morta sanada); "
          "cache hit na 2a chamada",
          iso1 == "de" and iso2 == "de" and len(_built_lazy) == 1
          and cache_c5.contains("SmallGermanTown"))
finally:
    geo_mod.NominatimGeocoder = _orig_cls
    set_geocoding_enabled(False)

set_geocoding_enabled(True)
try:
    with tempfile.TemporaryDirectory() as tmp:
        cache_c6 = GeocodingCache(Path(tmp) / "c6.json")
        mg = MagicMock(spec=NominatimGeocoder)
        mg.country_code.return_value = "nl"
        res_c6 = CountryResolver(cache=cache_c6, geocoder=mg)
        iso_c6 = res_c6.resolve("Shanghai")
    check("C6 geocoder 'nl' (controle Shanghai) -> None e miss cacheado "
          "(nunca fabrica 'de')",
          bool(iso_c6 is None and cache_c6.contains("Shanghai")))
finally:
    set_geocoding_enabled(False)


# ---------------------------------------------------------------------------
# D. Registro do contrato F50 (gates da F1 intocados + defaults das F50)
# ---------------------------------------------------------------------------

os.environ.pop(GEOCODING_ENV, None)
os.environ.pop(REASONING_EFFORT_ENV, None)
check("D1 INTERNSHIP_FINDER_GEOCODING segue OFF por default",
      is_geocoding_enabled() is False)
import inspect  # noqa: E402
from internship_finder.cli import run_filter_pipeline  # noqa: E402
sig = inspect.signature(run_filter_pipeline)
check("D2 pipeline: official_page default False (decisao feature 1 no contrato)",
      sig.parameters["official_page"].default is False)
check("D3 gates F1 referenciados pela F50 intactos",
      refresh_daily.ENRICHMENT_ENV_FLAG == "INTERNSHIP_FINDER_ENRICHMENT"
      and GEOCODING_ENV == "INTERNSHIP_FINDER_GEOCODING")

# restaura o ambiente do processo
for _k, _v in _SAVED_ENV.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v


def main() -> int:
    print()
    fails = [(n, d) for n, ok, d in CHECKS if not ok]
    if fails:
        print(f"{len(fails)} FALHA(S):")
        for n, d in fails:
            print(f"  - {n}" + (f" — {d}" if d else ""))
        return 1
    print(f"{len(CHECKS)} checks — TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
