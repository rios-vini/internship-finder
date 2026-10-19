"""Patch vendored do parser BambooHR (upstream PR #300) — F59.1.

Contexto (F59, 19/10): o widget ``/jobs/embed2.php`` da BambooHR passou a
servir JSON PURO (rollout ~08/10; probe F59/F59.1 ao vivo: HTTP 200,
623 bytes, ``application/json``, Accept-agnóstico). O parser HTML do
pacote instalado (ats-scrapers 0.3.0, marcador ``bhrPositionID_``) acha 0
vagas = ``empty`` silencioso — a série ``bamboohr:bcg`` está empty desde
08/10 com as vagas VIVAS no JSON. Quebra de PARSE, não fim das vagas.

O conserto correto é UPSTREAM: PR #300 (kalil0321/ats-scrapers; fork
rios-vini/ats-scrapers, head ``85c270a``) — detecção content-based +
extração de ``departments[].positions[]`` no MESMO formato de saída do
caminho HTML, que segue byte-idêntico. Enquanto o mantenedor não mergear
+ release (PRs #292/#293: 18/17 dias de precedente), esta camada VENDA o
parser corrigido aqui — 3º caso de bypass local do projeto
(TENANT_URL_OVERRIDES, TENANT_ATS_OVERRIDES, agora parser patch).

AUTO-DETECÇÃO — a chave do design (convergência sem divergência): antes
de parsear, o parser DO PACOTE INSTALADO é exercitado contra o fixture
JSON verbatim do BCG (623 bytes, offline, determinístico) pelo MESMO
caminho de produção (``afetch``):

- pacote parseia >0 vagas → upstream TEM o fix → **bypass total** (o
  comportamento é 100% do pacote, na instância que ``get_scraper``
  construiria);
- pacote parseia 0 vagas → patch vendored ativo.

Resultado: o patch é SELF-REMOVÍVEL — no merge+release+``pip install
-U`` o bypass liga sozinho e esta camada vira no-op (janela de
divergência com o upstream: ZERO). O canário ``(d)`` da suíte
``scripts/test_f59_1.py`` é a rede de segurança: no dia em que o pacote
instalado passar NATIVAMENTE no fixture, a suíte FALHA amigavelmente
exigindo a remoção (checklist abaixo).

Exceção no probe (``afetch`` refatorado upstream) = tratada como SEM fix
(fail-safe: o patch assume; o canário ``(d)`` continua sendo a verdade
sobre "o pacote já parseia nativamente?").

Kill switch (padrão F1, regra 9 da onda): env
``INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR`` — default ON; ``0`` =
comportamento histórico (pacote puro, mesmo sem fix).

CHECKLIST DE REMOÇÃO (upstream com fix: merge + release + upgrade):
1. Apagar este arquivo e ``upstream_patches/__init__.py`` (camada
   inteira — ela só existe enquanto o upstream NÃO tem o fix).
2. Reverter o ponto de uso em ``collectors/ats_scraper.py``:
   ``get_patched_scraper`` → ``get_scraper`` (import incluído).
3. ``scripts/test_f59_1.py``: o canário ``(d)`` passa a FALHAR (é o
   disparador da remoção); converter a suíte em assert DIRETO do pacote
   e removê-la do array do CI, ou reescrevê-la como regressão do
   caminho JSON do próprio pacote.
4. Atualizar os comentários F59/F59.1 em ``registry.py``/``health.py``
   (patch removido; zero_return de bamboohr:bcg deixa de existir).
5. Mover a âncora ``_AB_BASELINE_SHA`` do ``test_f53`` (esta fase toca
   ``src/``) — padrão F56/F50.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import HttpUrl

from ats_scrapers.exceptions import ScraperError
from ats_scrapers.models import ATSType, Job
from ats_scrapers.scrapers import get_scraper


# Kill switch (regra 9): default ON; valores falsos = comportamento
# histórico (pacote puro). Mesma mecânica das flags INTERNSHIP_FINDER_*
# (F1/Fase A): leitura direta de os.environ, sem deploy para desligar.
PATCH_ENV = "INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR"

# URLs públicas estáveis do widget BambooHR — espelham WIDGET_TEMPLATE/
# SHARE_URL_TEMPLATE do upstream 0.3.0 (o PR #300 não as altera). Cópias
# locais para a camada ser auto-contida (o PR reutiliza as constantes do
# módulo upstream; aqui o módulo inteiro é vendored).
_WIDGET_URL_TEMPLATE = "https://{slug}.bamboohr.com/jobs/embed2.php"
_SHARE_URL_TEMPLATE = "https://{slug}.bamboohr.com/careers/{id}"

# Fixture VERBATIM — resposta real de https://bcg.bamboohr.com/jobs/embed2.php
# capturada no probe F59.1 (19/10/2026 04:59 UTC: HTTP 200, 623 bytes,
# application/json; md5 ef2200a8b60e145fdf23f0a66103ce3f). As MESMAS 2
# vagas Remote da série com vagas de 07/10 (evidência F59) dentro de
# departments[].positions[]. NÃO editar e NÃO reformatar: este é o
# contrato do auto-detect (qualquer reformatação muda os bytes).
FIXTURE_JSON_BCG = r"""{"version":null,"labels":{"heading":"Open Positions","blankStateTitle":"We currently have no open positions.","blankStateBody":"Please check back as we will most certainly be looking for great people to join our team in the future."},"departments":[{"id":19228,"label":"Architecture & Service Excellence","positions":[{"id":81,"name":"Atlassian Platform & ITSM Engineer","url":"https:\/\/bcg.bamboohr.com\/careers\/81","location":"Remote"}]},{"id":18727,"label":"EIDS","positions":[{"id":80,"name":"Release Train Engineer (RTE) - DHMS","url":"https:\/\/bcg.bamboohr.com\/careers\/80","location":"Remote"}]}],"success":true}"""


def _patch_enabled() -> bool:
    """Flag env ``INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR`` (default ON).

    ``0``/``false``/``no``/``off`` desligam o patch e restauram o
    comportamento histórico (pacote puro) — reversibilidade sem deploy.
    """
    return os.environ.get(PATCH_ENV, "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class _FixtureFetcher:
    """Fetcher de stub que serve um corpo fixo — probe 100% offline.

    Implementa o subcontrato que ``afetch`` consome (context manager
    assíncrono + ``get_text``); nenhum socket é aberto. Os testes da
    suíte F59.1 o reutilizam para exercitar ambos os lados sem rede.
    """

    def __init__(self, body: str) -> None:
        self._body = body
        self.calls: list[str] = []

    async def __aenter__(self) -> _FixtureFetcher:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get_text(self, url: str, **kwargs: object) -> str:
        self.calls.append(url)
        return self._body


def _probe_cls(base: type, body: str) -> type:
    """Classe-filha de ``base`` com o fetcher trocado pelo stub (offline)."""

    class _Probe(base):  # noqa: N818 - classe de probe dinâmica e local
        def make_fetcher(self, **overrides: object) -> _FixtureFetcher:
            fetcher = _FixtureFetcher(body)
            # Observabilidade para a suíte F59.1: provar que o afetch REAL
            # buscou a URL do widget (o stub registrou a chamada).
            self._last_probe_fetcher = fetcher
            return fetcher

    return _Probe


def _installed_cls() -> type:
    """Classe BambooHR do PACOTE INSTALADO, via registro público.

    O pacote manda: "The registry is the only stable lookup mechanism —
    never import scraper classes by path from outside the package"
    (docstring do upstream base.py). A classe vem do próprio
    ``get_scraper`` — instância descartável: o construtor só valida o
    slug (``require_host_label``), zero rede.
    """
    return type(
        get_scraper("bamboohr", "bcg", timeout=1.0, include_descriptions=False)
    )


def upstream_has_json_fix(scraper_cls: type | None = None) -> bool:
    """Auto-detect: o parser INSTALADO já parseia o fixture JSON do BCG?

    Exercita o ``afetch`` REAL de ``scraper_cls`` (default: classe do
    pacote instalado, via registro) contra o fixture verbatim com o
    fetcher stubado — o MESMO caminho de produção (``fetch`` →
    ``afetch`` → parse), 100% offline e determinístico:

    - >0 vagas → upstream TEM o fix;
    - 0 vagas, ou exceção (``afetch`` refatorado) → NÃO tem.

    ``scraper_cls`` injetável é o gancho do simulacro ``(b)`` da suíte
    F59.1 (exercitar o bypass com um pacote-fantasma COM fix).
    """
    cls = scraper_cls if scraper_cls is not None else _installed_cls()
    probe = _probe_cls(cls, FIXTURE_JSON_BCG)(
        "bcg", timeout=1.0, include_descriptions=False
    )
    try:
        jobs = probe.fetch()
    except Exception:  # noqa: BLE001 - probe falha = sem fix (fail-safe)
        return False
    return len(jobs) > 0


# ---------------------------------------------------------------------------
# Parser vendored — verbatim do PR #300 (head 85c270a). Herda TUDO do
# pacote instalado (caminho HTML, detail API, get_description); sobrescreve
# SÓ o afetch (a branch JSON inserida exatamente onde o PR a insere) e
# adiciona _parse_widget_json.
# ---------------------------------------------------------------------------
_INSTALLED_BAMBOOHR = _installed_cls()


class PatchedBambooHRScraper(_INSTALLED_BAMBOOHR):
    """BambooHR do pacote instalado + parser JSON do PR #300 (vendored).

    Upstream mergear + release + ``pip install -U`` → o auto-detect dá
    bypass e esta classe para de ser instanciada; o canário ``(d)`` da
    suíte F59.1 falha e força a remoção do arquivo inteiro.
    """

    async def afetch(self) -> list[Job]:
        # afetch do pacote 0.3.0 + a branch JSON inserida exatamente onde o
        # PR #300 a insere (verbatim do PR, head 85c270a; fora da branch, o
        # corpo é o do 0.3.0 — caminho HTML byte-idêntico).
        async with self.make_fetcher() as fetch:
            widget_html = await fetch.get_text(
                _WIDGET_URL_TEMPLATE.format(slug=self.company_slug)
            )
            # Some tenants now serve this URL as pure JSON instead of the
            # HTML widget. Detection is content-based: a body starting
            # with `{` is decoded as JSON; a decode failure falls through
            # to the HTML parser, so HTML tenants behave exactly as before.
            # Only the ``json.loads`` decode is guarded — a malformed
            # payload must raise loudly, not silently hide the board.
            if widget_html.lstrip().startswith("{"):
                try:
                    payload = json.loads(widget_html)
                except ValueError:
                    payload = None
                if payload is not None:
                    jobs = self._parse_widget_json(payload)
                    if self.include_descriptions and jobs:
                        await self._enrich_from_detail_api(fetch, jobs)
                    return jobs
            jobs = self._parse_widget(widget_html)
            if re.search(r"bhrPositionID_", widget_html, re.IGNORECASE) and not jobs:
                raise ScraperError(
                    f"BambooHR widget for {self.company_slug} contains jobs "
                    "but none matched the parser"
                )
            if self.include_descriptions and jobs:
                await self._enrich_from_detail_api(fetch, jobs)
            return jobs

    def _parse_widget_json(self, payload: Any) -> list[Job]:
        """Parse the JSON form of `/jobs/embed2.php` (Oct 2026 rollout).

        Emits the same ``Job`` rows as the HTML widget path: one job per
        ``departments[].positions[]`` entry, inheriting the department
        label. The share URL is taken from the payload when absolute and
        derived from the position id otherwise. ``labels.blankStateTitle``
        is template text — an empty ``departments`` list means a genuine
        zero-jobs tenant, not an error.
        """
        if not isinstance(payload, dict):
            return []
        # An explicit application-level failure must not masquerade as an
        # empty board — the silent-empty class this parser guards against.
        if payload.get("success") is False:
            raise ScraperError(
                f"BambooHR widget for {self.company_slug} reported failure "
                "(success=false)"
            )
        departments = payload.get("departments")
        if not isinstance(departments, list):
            return []
        jobs: list[Job] = []
        seen: set[str] = set()
        positions_seen = 0
        for department in departments:
            if not isinstance(department, dict):
                continue
            label = department.get("label")
            dept_name = _collapse_ws(label) if isinstance(label, str) else None
            positions = department.get("positions")
            if not isinstance(positions, list):
                continue
            for position in positions:
                positions_seen += 1
                if not isinstance(position, dict):
                    continue
                raw_id = position.get("id")
                name = position.get("name")
                if raw_id is None or not isinstance(name, str):
                    continue
                ats_id = str(raw_id).strip()
                if not ats_id:
                    continue
                if ats_id in seen:
                    continue
                title = _collapse_ws(name)
                if not title:
                    continue
                seen.add(ats_id)
                raw_url = position.get("url")
                if (
                    isinstance(raw_url, str)
                    and raw_url.startswith(("http://", "https://"))
                    and urlsplit(raw_url).netloc
                ):
                    url = raw_url
                else:
                    url = _SHARE_URL_TEMPLATE.format(
                        slug=self.company_slug, id=ats_id
                    )
                location = position.get("location")
                jobs.append(
                    Job(
                        url=HttpUrl(url),
                        title=title,
                        company=self.company_slug,
                        ats_type=ATSType.BAMBOOHR,
                        ats_id=ats_id,
                        location=(
                            location.strip()
                            if isinstance(location, str) and location.strip()
                            else None
                        ),
                        department=dept_name,
                        posted_at=None,
                        fetched_at=datetime.now(UTC),
                    )
                )
        if positions_seen and not jobs:
            # Mirrors the HTML guard: the payload lists positions but none
            # were usable — raise instead of silently returning [].
            raise ScraperError(
                f"BambooHR widget for {self.company_slug} contains jobs "
                "but none matched the parser"
            )
        return jobs


def _collapse_ws(text: str) -> str:
    """JSON counterpart of ``_strip_tags`` for plain-text fields (position
    names, department labels): collapse whitespace only. No entity
    decoding — JSON text is already literal."""
    return re.sub(r"\s+", " ", text).strip()


def get_patched_scraper(
    ats: str,
    company_slug: str,
    *,
    probe_cls: type | None = None,
    **kwargs: object,
):
    """``get_scraper`` com o patch BambooHR auto-removível (ponto de uso).

    Ordem de decisão (primeira que casa manda):

    1. ATS != bamboohr → ``get_scraper`` puro (inércia: nenhum outro
       ATS é tocado por esta camada).
    2. Kill switch desligado (``INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR``
       falsy) → ``get_scraper`` puro (comportamento histórico).
    3. Auto-detect: o pacote INSTALADO parseia o fixture JSON → BYPASS
       total: ``get_scraper`` puro (o pacote é quem manda, byte a byte).
    4. Pacote sem fix → ``PatchedBambooHRScraper`` (parser vendored).

    ``probe_cls`` é injetável (só para o simulacro ``(b)`` da suíte
    F59.1): simula "o pacote instalado COM fix" — o bypass então
    instância a PRÓPRIA classe sondada, provando que o pacote é quem
    manda quando ele tem o fix. Em produção é sempre None (a classe
    real do pacote instalado).
    """
    if ats != "bamboohr":
        return get_scraper(ats, company_slug, **kwargs)
    if not _patch_enabled():
        return get_scraper(ats, company_slug, **kwargs)
    if upstream_has_json_fix(probe_cls):
        if probe_cls is not None:
            # Simulacro da suíte: "o pacote" é a classe injetada.
            return probe_cls(company_slug, **kwargs)
        return get_scraper(ats, company_slug, **kwargs)
    return PatchedBambooHRScraper(company_slug, **kwargs)
