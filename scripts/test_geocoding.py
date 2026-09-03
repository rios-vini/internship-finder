"""Testes do resolver de pais/localizacao (P0.1) — offline e deterministico.

Cobre: cache-first (miss->geocode, hit->sem chamada, cache corrupto->cache
vazio), flag OFF => zero rede em qualquer hipotese, camada de cidades DE
conhecidas (sem rede), integracao com infer_country_iso (via adapter), e
geocoder mockado com flag ON.

Uso:  .venv/bin/python scripts/test_geocoding.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.filters import infer_country_iso  # noqa: E402
from internship_finder.geocoding import (  # noqa: E402
    CountryResolver,
    GeocodingCache,
    NominatimGeocoder,
    set_geocoding_enabled,
)

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def make_adapter():
    return AtsJobAdapter()


def fake_company():
    from internship_finder.models.company import Company

    return Company(name="Covestro", ats="workday", slug="covestro",
                   url="https://careers.covestro")


TMP = tempfile.mkdtemp(prefix="geocache_")


def test_known_german_cities_and_misses() -> None:
    """Camada de cidades DE conhecidas, sem rede; cidades nao-DE/desconhecidas -> None."""
    cache = GeocodingCache(Path(TMP, "c1.json"))
    res = CountryResolver(cache=cache, geocoder=None)  # sem geocoder -> nunca rede
    # Cidades alemãs conhecidas -> de (sem rede)
    check("cidade DE conhecida 'Leverkusen' -> de", res.resolve("Leverkusen") == "de")
    check("cidade DE 'Oberkochen' -> de", res.resolve("Oberkochen") == "de")
    check("cidade DE umlaut 'München' -> de", res.resolve("München") == "de")
    check("cidade DE translit 'Goettingen' -> de", res.resolve("Goettingen") == "de")
    check("cidade DE translit 'Göttingen' -> de", res.resolve("Göttingen") == "de")
    # Cidades claramente nao-DE, sem flag e sem cache -> None (nunca fabrica)
    check("nao-DE 'Bangalore' -> None", res.resolve("Bangalore") is None)
    check("nao-DE 'Pasay City' -> None", res.resolve("Pasay City") is None)
    check("nao-DE 'Shanghai' -> None", res.resolve("Shanghai") is None)
    check("vazia '' -> None", res.resolve("") is None)


def test_cache_miss_then_hit_no_network() -> None:
    """miss -> resolve (geocoder); hit posterior NUNCA chama geocoder de novo."""
    cache = GeocodingCache(Path(TMP, "c2.json"))
    geocoder = MagicMock(spec=NominatimGeocoder)
    geocoder.country_code.return_value = "de"
    res = CountryResolver(cache=cache, geocoder=geocoder)
    geocoder.reset_mock()
    set_geocoding_enabled(True)
    try:
        # Simula o fluxo real: cache vazio -> geocoder
        cache._data = {}  # garante miss
        cache._dirty = True
        iso1 = res.resolve("Weinheim")
        check("miss -> geocoder chamado", geocoder.country_code.call_count == 1)
        check("miss resolve-> de", iso1 == "de")
        # hit -> geocoder NAO chamado de novo
        geocoder.reset_mock()
        iso2 = res.resolve("Weinheim")
        check("hit -> geocoder NAO chamado", geocoder.country_code.call_count == 0)
        check("hit -> de", iso2 == "de")
    finally:
        set_geocoding_enabled(False)


def test_cache_miss_cached() -> None:
    """Um miss (None) do geocoder tambem e cacheado para nao re-consultar."""
    cache = GeocodingCache(Path(TMP, "c3.json"))
    geocoder = MagicMock(spec=NominatimGeocoder)
    geocoder.country_code.return_value = None  # geocoder nao achou DE
    res = CountryResolver(cache=cache, geocoder=geocoder)
    set_geocoding_enabled(True)
    try:
        iso1 = res.resolve("SomewhereUnknown")
        check("miss geocoder -> None", iso1 is None)
        check("miss cacheado (contains)", cache.contains("SomewhereUnknown"))
        geocoder.reset_mock()
        res.resolve("SomewhereUnknown")
        check("miss cacheado -> NAO re-consulta", geocoder.country_code.call_count == 0)
    finally:
        set_geocoding_enabled(False)


def test_corrupt_cache_falls_back_safely() -> None:
    """Cache corrompido vira cache vazio (sem excecao) e nao quebra a resolucao."""
    path = Path(TMP, "c4.json")
    path.write_text("{not-valid-json!!!", encoding="utf-8")
    cache = GeocodingCache(path)
    check("cache corrupto nao estoura; vazio", cache.contains("Leverkusen") is False)
    res = CountryResolver(cache=cache, geocoder=None)
    check("apos corrupcao: cidade DE conhecida -> de", res.resolve("Leverkusen") == "de")
    # Raiz do cache nao-dict tambem e tolerada
    path2 = Path(TMP, "c5.json")
    path2.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    cache2 = GeocodingCache(path2)
    check("cache nao-dict tolerado", cache2.contains("x") is False)


def test_flag_off_no_network_at_all() -> None:
    """Flag OFF (default): NUNCA ha chamada de rede, mesmo p/ cidade desconhecida."""
    fake_session = MagicMock()
    geocoder = NominatimGeocoder(session=fake_session, rate_limit_seconds=0.0)
    cache = GeocodingCache(Path(TMP, "c6.json"))
    res = CountryResolver(cache=cache, geocoder=geocoder)
    set_geocoding_enabled(False)  # default
    try:
        res.resolve("Oberkochen")          # conhecida
        res.resolve("CityOnTheMoon")       # desconhecida (deveria consultar se flag ON)
        res.resolve("Bangalore")           # nao-DE
    finally:
        set_geocoding_enabled(False)
    fake_session.get.assert_not_called()
    check("flag OFF -> session.get NUNCA chamado", fake_session.get.call_count == 0)


def test_flag_on_geocoder_mock_unknown_german_city() -> None:
    """Flag ON + geocoder mock: cidade DE desconhecida (nao na lista) -> 'de'."""
    cache = GeocodingCache(Path(TMP, "c7.json"))
    geocoder = MagicMock(spec=NominatimGeocoder)
    geocoder.country_code.return_value = "de"
    res = CountryResolver(cache=cache, geocoder=geocoder)
    set_geocoding_enabled(True)
    try:
        check("flag ON cidade desconhecida->de (mock)",
              res.resolve("SmallGermanTown") == "de")
        # geocoder retornando outro pais -> None (nunca fabrica 'de')
        geocoder.country_code.return_value = "us"
        check("flag ON geocoder 'us' -> None", res.resolve("SomeUSTown") is None)
        # geocoder com erro (None) -> None
        geocoder.country_code.return_value = None
        check("flag ON geocoder None -> None", res.resolve("ErroredTown") is None)
    finally:
        set_geocoding_enabled(False)


def test_integration_with_infer_country_iso_and_adapter() -> None:
    """Adapter: infer_country_iso segue intacta; resolver preenche como fallback."""
    from internship_finder.geocoding import set_cache_path

    set_cache_path(Path(TMP, "singleton.json"))  # isola do data/ real
    set_geocoding_enabled(False)  # default (sem rede)
    try:
        # infer_country_iso NAO mudou (regressao F3 direta)
        check("infer 'Oberkochen' continua None", infer_country_iso(location="Oberkochen") is None)
        # adapter: cidade DE conhecida -> 'de' (resolver), sem rede
        ad = make_adapter()
        job = ad.to_job({
            "title": "Werkstudent Supply Chain (m/w/x)",
            "location": "Oberkochen",
            "url": "https://jobs.example/r1",
            "requisition_id": "R1",
            "ats_type": "workday",
        }, fake_company())
        check("adapter 'Oberkochen' -> de (resolver)", job.country_iso == "de")
        # adapter: location com pais explicito mantem infer_country_iso (resolver nao sobrescreve)
        job2 = ad.to_job({
            "title": "Praktikum Einkauf",
            "location": "Walldorf, DE, 69190",
            "url": "https://jobs.example/r2",
            "requisition_id": "R2",
        }, fake_company())
        check("adapter 'Walldorf, DE, 69190' -> de (infer, nao resolver)",
              job2.country_iso == "de")
        # adapter: cidade nao-DE/desconhecida -> None (com flag OFF)
        job3 = ad.to_job({
            "title": "Role X",
            "location": "Bangalore",
            "url": "https://jobs.example/r3",
            "requisition_id": "R3",
        }, fake_company())
        check("adapter 'Bangalore' -> None (nao fabrica)", job3.country_iso is None)
    finally:
        set_geocoding_enabled(False)


def test_adapter_flag_off_no_network() -> None:
    """Integra flag OFF no adapter: a foto do src nunca toca rede (mock requests)."""
    from internship_finder.geocoding import set_cache_path

    set_cache_path(Path(TMP, "singleton2.json"))
    ad = make_adapter()
    set_geocoding_enabled(False)
    try:
        with patch("requests.get", side_effect=AssertionError("rede chamada")) as mocked:
            ad.to_job({
                "title": "Werkstudent (m/w/x)",
                "location": "Braunschweig",
                "url": "https://jobs.example/r9",
                "requisition_id": "R9",
            }, fake_company())
            # cidade conhecida nao faz rede
            ad.to_job({
                "title": "X",
                "location": "UnresolvableCityXYZ",
                "url": "https://jobs.example/r10",
                "requisition_id": "R10",
            }, fake_company())
            mocked.assert_not_called()
        check("adapter flag OFF -> requests.get nunca chamado", True)
    finally:
        set_geocoding_enabled(False)


def main() -> None:
    print("== P0.1 Resolver de pais/localizacao (geocoding) ==")
    test_known_german_cities_and_misses()
    test_cache_miss_then_hit_no_network()
    test_cache_miss_cached()
    test_corrupt_cache_falls_back_safely()
    test_flag_off_no_network_at_all()
    test_flag_on_geocoder_mock_unknown_german_city()
    test_integration_with_infer_country_iso_and_adapter()
    test_adapter_flag_off_no_network()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FALHA(S):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())