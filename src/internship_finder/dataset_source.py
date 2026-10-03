"""Fonte `sf_dataset` (F3): o dataset hospedado do ats-scrapers como fonte PRIMARIA.

O pacote `ats-scrapers` 0.3.0 expoe DUAS camadas: (1) um dataset HOSPEDADO
(Cloudflare R2, manifest publico em ``https://storage.stapply.ai/jobhive/v1/manifest.json``,
atualizacao diaria ~05h UTC, sem API key) com ~5,1M jobs / 80.390 empresas /
63 fontes; (2) scrapers per-ATS que a coleta do registry usa. Esta fonte
consome a camada (1) pela borda correta e ALIMENTA o MESMO fluxo
filtros -> dedup -> ranking.

Por que NAO usar ``Client.search()`` do pacote (fato medido, spec F3 §2.1):

- ``search()`` filtra CLIENT-SIDE sobre um DataFrame materializado; params
  existentes sao ``query`` (substring no titulo), ``location`` (substring),
  ``company``, ``ats``, ``remote``, ``salary_*``, ``experience_max``,
  ``limit``. NAO existe ``country_iso`` (e coluna do schema, nao filtro) e
  "estagio" nao e expressavel de forma confiavel (substring literal no
  titulo).
- ``load(ats=...)`` materializa a fatia INTEIRA por-ATS em RAM (BytesIO ->
  DataFrame); o snapshot completo tem 16,8 GB. O venv de producao nao tem
  pyarrow (parquet).
- ``by_date`` esta VAZIO no manifest vivo (nao ha delta diario publicado).

Mecanica desta fonte (streaming, NUNCA DataFrame):

1. ``fetch_manifest`` baixa o manifest (timeout ``DATASET_HTTP_TIMEOUT``) e
   devolve ``by_ats``: ``{ats: {"csv": url, "rows": n, ...}}``.
2. Para cada fonte em ``sources`` (default: TODAS as chaves de ``by_ats``,
   ordenadas), baixa a fatia CSV para um arquivo temporario em disco
   (streaming por chunks - pico de disco = maior fatia) e aplica o
   PREFILTER em streaming (``csv.DictReader`` linha a linha): so rows com
   (a) marcador de estagio no TITULO (``filters.STUDENT_TYPE_PATTERNS``,
   reuso integral), (b) SEM exclusao de tipo/programa no TITULO
   (``filters.TYPE_EXCLUSION_PATTERNS`` + ``PROGRAM_EXCLUSION_PATTERNS``)
   e (c) DE (``country_iso == "de"`` OU location casa
   ``\\bDE\\b|deutschland|germany`` - a fatia successfactors tem iso vazio,
   fato medido §2.5). A fatia local e apagada apos o prefilter de CADA
   fonte (nunca acumula em disco).
3. Rows sobreviventes viram ``Job`` direto (helper ``row_to_job``): id
   ``"<company>|sf_dataset:<ats_type>:<ats_id>"`` (hash sha1 16-hex da URL
   quando ``ats_id`` ausente, mesma regra do ``AtsJobAdapter._make_id``),
   ``source = "sf_dataset:<ats_type>"``, ``raw`` = row inteira MENOS
   description (mesmo contrato do adapter). Row sem company/title/url ->
   SKIP com contador proprio ``invalid_rows`` (nunca crash, nunca Job
   fabricado).

Volume: o prefilter reduz ~5,1M rows globais para ~21,6k antes de qualquer
``Job`` existir (fato medido §2.3). Budget total do estagio:
``DATASET_BUDGET_SECONDS`` (checado ENTRE fatias; estourado -> fatias
restantes viram ``skipped_budget``).

O registry NAO participa da entrada (a inversao arquitetural da F3): a
lista de 101 empresas vira componente ``registry`` no RANKING
(``ranking.WEIGHT_REGISTRY_INTEREST``), nunca filtro de existencia.

Jobs do dataset NAO entram no lifecycle SQLite (invariante §7.8): a fonte
e efemera, re-derivada a cada run - so as unidades de coleta do registry
(``--sqlite``) persistem first_seen/last_seen.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
import tempfile
import time
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from internship_finder.filters import (
    PROGRAM_EXCLUSION_PATTERNS,
    STUDENT_TYPE_PATTERNS,
    TYPE_EXCLUSION_PATTERNS,
    infer_country_iso,
    is_student_role,
)
from internship_finder.models.job import Job

log = logging.getLogger(__name__)

# Manifest do dataset hospedado (publico, sem API key; atualizacao diaria).
MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json"

# Teto TOTAL do estagio dataset (segundos), checado ENTRE fatias. Estourado:
# as fatias restantes viram ``skipped_budget`` no registro dataset e o run
# segue (best-effort - mesmo espirito da hidratacao, Fase A).
DATASET_BUDGET_SECONDS = 1800.0

# Timeout POR request HTTP (manifest e cada fatia).
DATASET_HTTP_TIMEOUT = 120.0

# Chaves de ``by_ats`` processadas por default: TODAS (ordenadas). O
# manifest e a fonte - sem allowlist manual; fontes com 0 rows DE+intern
# (wanted, ukg, wellfound...) custam so o download da fatia pequena.
SF_DATASET_SOURCES: list[str] | None = None

# DE: ``country_iso`` populado (eures/bundesagentur) OU marcador na location
# (fatia successfactors tem iso vazio e carrega "Berlin, DE, 10587" - fato
# medido §2.5). Case-insensitive, word-boundary para o ISO.
_DE_MARKER_RE = re.compile(r"\bde\b|deutschland|germany", re.IGNORECASE)

# F7 — marcadores de location por pais-alvo (canal secundario). Formatos
# medidos nas fatias reais (2026-10-03): "LU", "NL (NL126)", "FI (FI1B1)",
# "Belgien", "Niederlande", "Aarschot, BE, 3200", "Antwerpen, BE".
# Word-boundary no ISO de 2 letras; nomes locais do pais como fallback.
_LOCATION_MARKERS: dict[str, re.Pattern[str]] = {
    "de": _DE_MARKER_RE,
    "lu": re.compile(r"\blu\b|luxembourg|luxemburg", re.IGNORECASE),
    "nl": re.compile(r"\bnl\b|netherlands|nederland|niederlande|holland", re.IGNORECASE),
    "fi": re.compile(r"\bfi\b|finland|suomi", re.IGNORECASE),
    "be": re.compile(r"\bbe\b|belgium|belgique|belgien|belgië", re.IGNORECASE),
}

# Patterns de estagio/exclusao compilados UMA vez (reuso integral de
# ``filters`` - zero vocabulario novo; mesma heuristica do funil).
_STUDENT_RE = [re.compile(p, re.IGNORECASE) for p in STUDENT_TYPE_PATTERNS]
_EXCLUSION_RE = [
    re.compile(p, re.IGNORECASE)
    for p in TYPE_EXCLUSION_PATTERNS + PROGRAM_EXCLUSION_PATTERNS
]


def _clean(value: Any) -> str | None:
    """String normalizada (strip); vazio/None -> ``None`` (ausencia != falso)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_dt(value: Any) -> datetime | None:
    """Parse tolerante de datas ISO 8601 (``Z`` -> ``+00:00``); nunca crash."""
    if not value:
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def is_country_row(
    country_iso: Any,
    location: Any,
    isos: Any = ("de",),
) -> bool:
    """Row e de um dos paises-alvo? (criterio (c) do prefilter; F7).

    F7 generaliza o ``is_de_row`` da F3 para um CONJUNTO de ISOs:

    - ``country_iso`` da row em ``isos`` (case-insensitive); OU
    - a location carrega marcador textual de um dos paises (regex por
      ISO, word-boundary — mesmo espirito do ``\\bDE\\b``/deutschland/
      germany da F3, extendido aos paises-alvo).

    Default sem argumento = so DE (retrocompatibilidade TOTAL: os
    chamadores existentes da F3/F4 nao mudam de comportamento). A fatia
    eures/bundesagentur tem ``country_iso`` populado; a successfactors
    povoou a coluna a partir do manifest de out/2026 (fato medido F7:
    35.496 rows 'de', 6.412 'nl', 6025 'fr'...) mas o marcador de
    location continua como fallback barato — o prefilter e
    propositalmente MAIS BARATO que a inferencia completa porque roda
    sobre ~5,8M rows; a inferencia canonica acontece depois, so nos
    sobreviventes.
    """
    iso = _clean(country_iso)
    if isos:
        targets = {str(t).strip().lower() for t in isos}
    else:
        targets = set()
    if iso and iso.lower() in targets:
        return True
    loc = str(location or "")
    return any(_LOCATION_MARKERS[t].search(loc) for t in targets if t in _LOCATION_MARKERS)


def is_de_row(country_iso: Any, location: Any) -> bool:
    """Row e da Alemanha? (retrocompat — delega a ``is_country_row``)."""
    return is_country_row(country_iso, location, ("de",))


def row_is_intern_candidate(title: Any) -> bool:
    """Criterios (a)+(b) do prefilter sobre o TITULO (uppercase-free, uma vez).

    Mantem: marcador de estagio presente E nenhuma exclusao de
    tipo/programa. Mesma regra que o funil aplica depois
    (``is_student_role``); o prefilter e o corte BARATO por titulo que
    evita materializar rows que o funil descartaria.
    """
    t = str(title or "")
    if not t:
        return False
    if any(p.search(t) for p in _EXCLUSION_RE):
        return False
    return any(p.search(t) for p in _STUDENT_RE)


def row_to_job(row: Mapping[str, Any], ats_type: str) -> Job | None:
    """Converte uma row do dataset em ``Job`` (ou ``None`` se invalida).

    Identidade (P1.1 preservada com source novo):
    ``id = "<company>|sf_dataset:<ats_type>:<ats_id>"`` - o escopo
    company + source distingue o job do dataset da vaga equivalente vinda
    da coleta do registry (mesma vaga, fontes diferentes: colapsam no dedup
    pela chave URL (b), nao pelo id). Sem ``ats_id``: hash sha1 16-hex da
    URL (mesma regra do ``AtsJobAdapter._make_id``).

    ``raw`` e o contrato: a row inteira MENOS ``description`` (padrao do
    adapter - texto grande nao entra no ``raw``; o campo canonico
    ``description`` carrega o valor).

    Row sem company OU sem title OU sem url -> ``None`` (o chamador conta
    em ``invalid_rows`` - nunca crash, nunca Job fabricado).
    """
    title = _clean(row.get("title"))
    company = _clean(row.get("company"))
    url = _clean(row.get("url"))
    if not title or not company or not url:
        return None

    ats_id = _clean(row.get("ats_id"))
    source = f"sf_dataset:{ats_type}"
    if ats_id:
        job_id = f"{company}|{source}:{ats_id}"
        external_id = ats_id
    else:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        job_id = f"{company}|{source}:{digest}"
        external_id = None

    location = _clean(row.get("location"))
    country_iso = _clean(row.get("country_iso"))
    description = _clean(row.get("description"))
    employment_type = _clean(row.get("employment_type"))
    iso = infer_country_iso(location=location, country_iso=country_iso)

    raw = {k: v for k, v in row.items() if k != "description"} or None

    return Job(
        id=job_id,
        source=source,
        title=title,
        company=company,
        location=location,
        country=iso,
        url=url,
        description=description,
        internship=is_student_role(title, description, employment_type),
        posted_at=_parse_dt(row.get("posted_at")),
        collected_at=datetime.now(UTC),
        external_id=external_id,
        employment_type=employment_type,
        country_iso=iso,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Download + coleta
# ---------------------------------------------------------------------------


def _http_fetch(url: str, dest: Path, timeout: float = DATASET_HTTP_TIMEOUT) -> int:
    """Baixa ``url`` em streaming para ``dest``; devolve bytes baixados.

    Streaming por chunks de 1 MiB em DISCO (nunca RAM): pico de uso = a
    fatia em download. O chamador apaga ``dest`` apos o prefilter.
    ``urllib.request`` (stdlib) - sem dependencia nova no runtime.
    """
    bytes_downloaded = 0
    req = urllib.request.Request(url, headers={"User-Agent": "internship-finder/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            bytes_downloaded += len(chunk)
    return bytes_downloaded


def fetch_manifest(
    url: str = MANIFEST_URL,
    timeout: float = DATASET_HTTP_TIMEOUT,
) -> dict[str, Any]:
    """Manifest vivo -> ``by_ats`` (dict ``{ats: meta}``). Levanta em falha."""
    req = urllib.request.Request(url, headers={"User-Agent": "internship-finder/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        manifest = json_loads(resp.read().decode("utf-8"))
    by_ats = manifest.get("by_ats")
    if not isinstance(by_ats, dict) or not by_ats:
        raise ValueError("manifest sem 'by_ats' (schema inesperado)")
    return by_ats


def json_loads(text: str) -> dict[str, Any]:
    import json

    return json.loads(text)


def collect_dataset_jobs(
    *,
    sources: list[str] | None = SF_DATASET_SOURCES,
    budget_seconds: float = DATASET_BUDGET_SECONDS,
    manifest_url: str = MANIFEST_URL,
    timeout: float = DATASET_HTTP_TIMEOUT,
    manifest: Mapping[str, Any] | None = None,
    http_fetch: Callable[[str, Path], int] | None = None,
    now: Callable[[], float] = time.monotonic,
    workdir: Path | None = None,
    country_isos: Any = ("de",),
) -> tuple[list[Job], dict[str, Any]]:
    """Coleta do dataset hospedado com prefilter; devolve ``(jobs, summary)``.

    - ``manifest``: injeta o by_ats diretamente (testes offline); sem ele,
      baixa o manifest vivo de ``manifest_url``.
    - ``http_fetch(url, dest)``: injeta o download (testes apontam para
      fixtures locais); default baixa via urllib em streaming.
    - ``workdir``: diretorio para as fatias temporarias (default: tempdir
      do SO - TMPDIR em producao; testes apontam para o tempdir do teste).
    - ``country_isos`` (F7): ISOs-alvo do prefilter (criterio (c)). Default
      ``("de",)`` = retrocompatibilidade total com a F3; a producao passa
      ``countries.TARGET_COUNTRIES`` (DE primario + LU/NL/FI/BE).

    Summary (dict de metricas, gravado no JSONL como registro
    ``type: dataset`` pelo CLI):

    - ``status``: ``"ok"`` | ``"failed"`` (falha estrutural: manifest ou
      TODAS as fatias falharam - o chamador loga e o run segue com so os
      jobs do registry).
    - ``rows_total`` / ``rows_prefiltered``: linhas lidas / rows que
      passaram nos 3 criterios (antes da validacao de Job).
    - ``invalid_rows``: rows prefilteradas que nao viraram Job (sem
      company/title/url).
    - ``jobs``: Jobs criados.
    - ``per_ats``: ``{ats: {"rows": n, "kept": n, "skipped_budget": bool,
      "failed": bool}}``.
    - ``skipped_budget`` / ``failed_slices``: contagens.
    - ``bytes_downloaded`` / ``duration``: volume e duracao.
    """
    t0 = now()
    fetch = http_fetch or _http_fetch
    summary: dict[str, Any] = {
        "source": "sf_dataset",
        "rows_total": 0,
        "rows_prefiltered": 0,
        "invalid_rows": 0,
        "jobs": 0,
        "per_ats": {},
        "skipped_budget": 0,
        "failed_slices": 0,
        "bytes_downloaded": 0,
    }
    jobs: list[Job] = []
    deadline = t0 + budget_seconds

    try:
        by_ats = dict(manifest) if manifest is not None else fetch_manifest(manifest_url, timeout)
    except Exception as exc:  # noqa: BLE001 - dataset e best-effort
        log.error("sf_dataset: manifest falhou (%s); estagio abortado", exc)
        summary["status"] = "failed"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["duration"] = round(now() - t0, 2)
        return jobs, summary

    names = sorted(sources) if sources is not None else sorted(by_ats)

    tmp_ctx = None
    tmp_dir = None
    try:
        if workdir is None:
            tmp_ctx = tempfile.TemporaryDirectory(prefix="sf_dataset_")
            tmp_dir = Path(tmp_ctx.__enter__())
        else:
            tmp_dir = Path(workdir)
            tmp_dir.mkdir(parents=True, exist_ok=True)

        for name in names:
            meta = by_ats.get(name)
            if not isinstance(meta, Mapping) or not meta.get("csv"):
                log.warning("sf_dataset: fonte %s sem 'csv' no manifest; pulada", name)
                continue
            entry = summary["per_ats"].setdefault(
                name, {"rows": 0, "kept": 0, "skipped_budget": False, "failed": False}
            )
            if now() >= deadline:
                entry["skipped_budget"] = True
                summary["skipped_budget"] += 1
                log.warning(
                    "sf_dataset: budget de %.0fs estourado; %s e as fatias "
                    "restantes viram skipped_budget", budget_seconds, name)
                continue
            slice_path = tmp_dir / f"{name}.csv"
            try:
                summary["bytes_downloaded"] += fetch(str(meta["csv"]), slice_path)
                slice_jobs, rows, kept, invalid = _prefilter_slice(slice_path, name, country_isos)
                summary["rows_total"] += rows
                summary["rows_prefiltered"] += kept
                summary["invalid_rows"] += invalid
                entry["rows"] = rows
                entry["kept"] = kept
                jobs.extend(slice_jobs)
            except Exception as exc:  # noqa: BLE001 - fatia falha, resto segue
                entry["failed"] = True
                summary["failed_slices"] += 1
                log.warning("sf_dataset: fatia %s falhou (%s); seguindo", name, exc)
            finally:
                # NUNCA manter fatias em disco (pico = maior fatia, ~4,6 GB
                # workday; disco livre ~27 GB - acumular as 63 estouraria).
                slice_path.unlink(missing_ok=True)
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()

    summary["jobs"] = len(jobs)
    summary["status"] = "failed" if summary["failed_slices"] and not jobs else "ok"
    summary["duration"] = round(now() - t0, 2)
    return jobs, summary


def _prefilter_slice(
    path: Path,
    ats_type: str,
    isos: Any = ("de",),
) -> tuple[list[Job], int, int, int]:
    """Prefilter em streaming de UMA fatia: (jobs, rows, kept, invalid)."""
    jobs: list[Job] = []
    rows = kept = invalid = 0
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            title = str(row.get("title") or "")
            if not row_is_intern_candidate(title):
                continue
            if not is_country_row(row.get("country_iso"), row.get("location"), isos):
                continue
            kept += 1
            job = row_to_job(row, ats_type)
            if job is None:
                invalid += 1
                continue
            jobs.append(job)
    return jobs, rows, kept, invalid
