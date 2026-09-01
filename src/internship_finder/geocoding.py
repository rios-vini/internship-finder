"""Resolucao de pais/localizacao para vagas sem pais explicito (cache-first).

A API do Workday expoe apenas a string de localizacao (na maioria das vezes
cidade sozinha, ex.: "Leverkusen", "Freiburg im Breisgau"). Sem pais explicito
na string, ``filters.infer_country_iso`` retorna ``None`` (por construcao e
seguro) e o filtro ``--country de`` descarta vagas alemas reais.

Este modulo e o FALLBACK pos-``infer_country_iso``: entra somento quando a
inferencia atual nao determinou pais e existe ``location``. Nunca substitui
nem roda antes de ``infer_country_iso``. Cadeia de confianca:

1. Cidade alema conhecida (lista local verificada) -> ``de`` (sem rede).
2. Localizacao ja resolvida antes -> cache persistente (sem repetir chamadas).
3. Sem cache -> geocoder (OSM Nominatim, sem key), GATEADO por flag
   ``INTERNSHIP_FINDER_GEOCODING`` (default OFF). O flag tambem liga o cache:
   com o flag OFF, a cadeia se limita a camada de cidades conhecidas + cache
   ja populado — NENHUMA chamada de rede e feita em hipotese alguma.

Regras de seguranca:
- Nunca fabrica ISO: devolve ``"de"`` somente quando a evidencia e segura
  (cidade DE conhecida, cache ``de``, ou geocoder retornando DE).
- Nunca levanta excecao: cache corrompido vira cache vazio; geocoder com
  erro/timeout/HTTP != 200 devolve ``None`` e registra warning.
- Nao usa API com key. HTTP via ``requests`` (dependencia DECLARADA).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

# Env que liga geocoding de rede (default OFF). Soh com ele o geocoder e
# consultado; cache (leitura/escrita) e sempre ativo.
GEOCODING_ENV = "INTERNSHIP_FINDER_GEOCODING"

# Default do caminho do cache. Sempre criado junto da camada local de dados.
DEFAULT_CACHE_PATH = Path("data/geocoding_cache.json")

# Geocoder OSM Nominatim (gratuito, sem key). Rate limit de >=1s por chamada,
# conforme politica de uso; UA identifica o projeto.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "internship-finder/0.1 (job location country resolution)"
RATE_LIMIT_SECONDS = 1.0
HTTP_TIMEOUT = 10.0

# Cache lands no formato: {"<location-normalizada>": "<iso-2-minusc>" | null}.
# Um miss (None) tambem e cacheado, para nao re-consultar cidades
# desconhecidas a cada coleta.


def _norm(city: str) -> str:
    """Normaliza cidade/location para comparacao exata (case / acentos).

    - minusculas
    - colapso de espacos internos
    - remove acentos/marks (NFD + strip combining marks): "München" -> "munchen"
    - "ß" -> "ss"
    Nao faz substring: o match e sempre pelo valor NORMALIZADO INTEIRO.
    """
    s = str(city).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("ß", "ss")
    return re.sub(r"\s+", " ", s).strip()


def _build_german_city_variants(raw: tuple[str, ...]) -> set[str]:
    """Converte nomes de cidades DE (versoes com/sem umlaut) em chaves normalizadas."""
    out: set[str] = set()
    for name in raw:
        out.add(_norm(name))
    return out


# Cidades alemas VERIFICADAS observadas nas coletas Workday (escopo: paises DE).
# Cada entrada e verificadamente alema. Formas transliteradas (Goettingen vs
# Göttingen) sao listadas juntas para o match normalizado capturar ambos os
# spellings da API. Umlaut e a forma "oe/ue/ae" sao normalizados para a mesma
# chave? Nao — NFD mapeia "ü"->"u", nao "ue"; por isso as duas grafias precisam
# de entrada propria. A lista e curta e auditavel (dezenas, nao milhares).
_GERMAN_CITIES_RAW: tuple[str, ...] = (
    "Aalen",
    "Ansbach",
    "Augsburg",
    "Bad Homburg",
    "Berlin",
    "Bielefeld",
    "Braunschweig",
    "Bremen",
    "Buxtehude",
    "Darmstadt",
    "Ditzingen",
    "Dortmund",
    "Dossenheim",
    "Dresden",
    "Dusseldorf",
    "Essen",
    "Frankfurt",
    "Freiburg",
    "Freiburg im Breisgau",
    "Friedberg",
    "Geesthacht",
    "Giessen",
    "Goettingen",
    "Göttingen",
    "Anröchte",
    "Crivitz",
    "Gross Ippener",
    "Grossschirma",
    "Guxhagen",
    "Halle",
    "Hamburg",
    "Hanau",
    "Herne",
    "Hettingen",
    "Jena",
    "Karlsdorf-Neuthard",
    "Karlsruhe",
    "Kassel",
    "Klipphausen",
    "Koeln",
    "Krostitz",
    "Köln",
    "Lahr",
    "Lehrte",
    "Leipzig",
    "Leverkusen",
    "Ludwigsfelde",
    "Mannheim",
    "Meppen",
    "Moenchengladbach",
    "Muenchen",
    "München",
    "Neu Isenburg",
    "Neukirch",
    "Neumuenster",
    "Neunkirchen",
    "Norderstedt",
    "Nossen",
    "Nuernberg",
    "Nuremberg",
    "Nürnberg",
    "Oberkochen",
    "Oelde",
    "Osnabrueck",
    "Osnabrück",
    "Osterweddingen",
    "Polch",
    "Roßdorf",
    "Schloss Holte-Stukenbrock",
    "Schramberg",
    "Steinau",
    "Stutensee",
    "Stuttgart",
    "Teningen",
    "Voelklingen",
    "Völklingen",
    "Werne",
    "Wesseling",
    "Weiterstadt",
    "Wetzlar",
    "Wittlich",
    "Woerrstadt",
    "Wörrstadt",
)

GERMAN_CITIES = _build_german_city_variants(_GERMAN_CITIES_RAW)


def _geocoding_enabled() -> bool:
    """Flag env ``INTERNSHIP_FINDER_GEOCODING`` (default OFF)."""
    return os.environ.get(GEOCODING_ENV) == "1"


def set_geocoding_enabled(enabled: bool) -> None:
    """Alterna programaticamente a flag de geocoding (so leitura do cache fica ativa de outra forma).

    ``True`` liga o geocoder de rede (equivalente a ``INTERNSHIP_FINDER_GEOCODING=1``);
    ``False`` o desliga (default). Usado por testes e por quem quer controlar a
    flag via codigo, sem depender de variavel de ambiente.
    """
    os.environ[GEOCODING_ENV] = "1" if enabled else "0"


def is_geocoding_enabled() -> bool:
    """True quando o geocoder de rede esta habilitado."""
    return _geocoding_enabled()


class GeocodingCache:
    """Cache persistente (JSON em disco) de localizacao -> ISO (ou miss ``None``).

    Cache-first: uma localizacao ja resolvida (inclusive um fail) nunca e
    re-consultada. Tolerante a corrupcao (arquivo quebrado vira cache vazio,
    nunca excecao). Escrita controlada (``flush``), espacada entre a leitura.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_CACHE_PATH
        self._data: dict[str, str | None] = {}
        self._dirty = False
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            with self.path.open(encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                raise ValueError("cache raiz nao e dict")
            for k, v in raw.items():
                if isinstance(k, str) and (v is None or isinstance(v, str)):
                    self._data[str(k)] = v
        except (OSError, ValueError, json.JSONDecodeError):
            # Arquivo quebrado/corrompido -> cache vazio (nunca excecao).
            log.warning("cache de geocoding ilegivel (%s); usando cache vazio", self.path)
            self._data = {}
            self._dirty = False

    def get(self, location: str) -> str | None:
        """Valor cacheado para ``location`` (ISO ou ``None`` para miss cacheado).

        Use ``contains`` antes para distinguir "nao conhecida" de "cacheada
        como miss (None)". Uma chave ausente retorna ``None`` da mesma forma
        que um miss cacheado — a diferenciacao e feita por ``contains``.
        """
        key = _norm(location)
        if not key:
            return None
        with self._lock:
            return self._data.get(key)

    def contains(self, location: str) -> bool:
        key = _norm(location)
        if not key:
            return False
        with self._lock:
            return key in self._data

    def set(self, location: str, iso: str | None) -> None:
        key = _norm(location)
        if not key:
            return
        with self._lock:
            self._data[key] = iso
            self._dirty = True

    def flush(self) -> None:
        """Persiste o cache em disco (cria ``data/`` se nao existir)."""
        with self._lock:
            if not self._dirty:
                return
            snapshot = dict(self._data)
            self._dirty = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            log.warning("falha ao gravar cache de geocoding (%s): %s", self.path, exc)


class NominatimGeocoder:
    """Geocoder OSM Nominatim com rate limit, timeout, UA e nunca levanta excecao.

    Retorna o ISO do pais do resultado mais importante ou ``None``. Usado
    apenas para decidir se a cidade e DE — so aceita resultados com pais
    ``Germany``/``Deutschland``.
    """

    def __init__(self, session=None, rate_limit_seconds: float = RATE_LIMIT_SECONDS) -> None:
        import requests  # dependencia declarada no pyproject

        self._requests = requests
        self._session = session
        self._rate_limit_seconds = rate_limit_seconds
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self._rate_limit_seconds - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _query(self, params: dict) -> list | None:
        self._throttle()
        try:
            kwargs = {
                "url": NOMINATIM_URL,
                "params": params,
                "headers": {"User-Agent": NOMINATIM_UA},
                "timeout": HTTP_TIMEOUT,
            }
            if self._session is not None:
                resp = self._session.get(**kwargs)
            else:
                resp = self._requests.get(**kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - geocoder nunca levanta
            log.warning("geocoding falhou para %r: %s", params.get("q"), exc)
            return None

    def country_code(self, location: str) -> str | None:
        """ISO (minusculo) do pais da ``location``; ``None`` se inseguro/sem resultado."""
        results = self._query(
            {"q": location, "format": "json", "accept-language": "en", "limit": 1}
        )
        if not results:
            return None
        cc = (results[0].get("country_code") or "").strip().lower()
        return "de" if cc == "de" else None


class CountryResolver:
    """Resolve pais de uma localizacao usando a cadeia cache-first -> geocoder.

    Ordem: cidade DE conhecida -> cache -> geocoder (so com flag ON).
    Nunca fabrica ISO; nunca levanta excecao; sem flag nunca faz rede.
    """

    def __init__(
        self,
        cache: GeocodingCache | None = None,
        geocoder: NominatimGeocoder | None = None,
    ) -> None:
        self.cache = cache or GeocodingCache()
        self.geocoder = geocoder

    def resolve(self, location: str) -> str | None:
        """Retorna ISO ``"de"`` para uma localizacao seguramente alema, ou ``None``."""
        if not location or not str(location).strip():
            return None
        loc = str(location).strip()

        # 1. Cidade alemã conhecida (camada local, sem rede, sempre ativa).
        norm = _norm(loc)
        if norm in GERMAN_CITIES:
            return "de"

        # 2. Cache (ja resolveu antes, inclusive miss). So consulta geocoder se
        #    nao temos nenhum registro desta localizacao.
        if self.cache.contains(loc):
            return self.cache.get(loc)

        # 3. Geocoder: SOMENTE com flag ON.
        if not is_geocoding_enabled() or self.geocoder is None:
            return None

        iso = self.geocoder.country_code(loc)
        # Escopo confiado ao resolver: so devolve ``de`` quando a evidencia e
        # segura para Alemanha. Qualquer outro ISO do geocoder e tratado como
        # nao-DE (None) — nunca fabrica um pais fora do escopo. O cache guarda
        # o valor ja filtrado, para que um resultado nao-DE nunca vaze depois
        # de um flush/reload (== um miss cacheado, seguro de reutilizar).
        resolved = iso if iso == "de" else None
        self.cache.set(loc, resolved)
        return resolved


# Folha singleton leve para uso direto na integracao do adapter.
_default_cache = GeocodingCache()
_default_resolver = CountryResolver(cache=_default_cache)


def resolve_country_iso(location: str | None) -> str | None:
    """Fallback pos-``infer_country_iso``: preenche ``de`` quando seguro.

    Entra SOMENTE quando a inferencia atual ja devolveu ``None``. Camada de
    cidades DE conhecidas + cache sempre; geocoder so com
    ``INTERNSHIP_FINDER_GEOCODING=1``. Nunca fabrica ISO e nunca faz rede sem
    o flag.
    """
    if not location or not str(location).strip():
        return None
    return _default_resolver.resolve(str(location).strip())


def flush_cache() -> None:
    """Persiste o cache singleton. Chamado ao fim da coleta/integracao."""
    _default_cache.flush()


def set_cache_path(path: str | Path) -> None:
    """Redefine o cache singleton para ``path`` (usado em testes)."""
    global _default_cache, _default_resolver
    _default_cache = GeocodingCache(path)
    _default_resolver = CountryResolver(cache=_default_cache)