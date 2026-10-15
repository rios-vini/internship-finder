"""F48 — Deduplicacao CROSS-FONTE por campos estruturados (espelhos EN/DE).

BURACO FECHADO (medido nos archives congelados de 13/10 e 14/10): a MESMA
vaga publicada em DUAS FONTES diferentes (ex.: dataset ``sf_dataset:bundesagentur``
x ``successfactors:jobs``) passa reta por todos os estagios existentes:

- tiers 1/2/URL: ids e URLs sao de tenants distintos (e o escopo por empresa,
  P1.1, exige a MESMA empresa textual);
- tier 3 (``company+title+location``) e tier 4 (``+de/en``): exigem empresa
  normalizada IGUAL e localizacao normalizada IGUAL. No par real medido as
  duas coisas divergem POR FORMATO, nao por identidade:
  ``'Bayer AG Pharmaceuticals'`` x ``'Bayer'``;
  ``'51373 Leverkusen, Nordrhein Westfalen, Deutschland'`` x
  ``'Leverkusen, North Rhine Westfalia, DE'`` (mesma cidade Leverkusen).
- ``mirror_dedup`` (Fase C): exige MESMO tenant (``source``) + mesmo
  ``requisition_id`` — um espelho cross-fonte nunca e candidato la.
- similaridade textual NAO resolve: o par EN/DE medido tem
  SequenceMatcher = 2,88% (idiomas diferentes).

REGRA (deterministica, idempotente, so campos estruturados):

1. CANDIDATO: mesma CIDADE normalizada + mesmo TITULO normalizado
   (``_de_en_title_key`` — bag do ``normalize_title`` + dicionario minimo
   DE<->EN da F5) + ``source`` DIFERENTE (o alvo e espelho cross-fonte;
   par da MESMA fonte e assunto dos estagios existentes).
2. CIDADE normalizada (``city_key``): ``normalize_location`` -> 1a parte
   antes da virgula -> strip do CEP/PLZ inicial (``51373 Leverkusen`` ->
   ``leverkusen``) -> ``CITY_ALIASES`` do Company Intelligence
   (``munich``==``munchen``, ``cologne``==``koln``). LOCATION-AWARE por
   construcao: cidade diferente = vaga diferente (contra-casos medidos que
   DEVEM sobreviver: Google x3-5 = 3 paises, indiecampers x4-8 = cidades
   distintas).
3. EMPRESA: chave de IDENTIDADE = tokens (casefold + sem acentos) MENOS os
   ``NON_IDENTITY_TOKENS`` (formas legais, qualificadores corporativos/
   geograficos, artefatos de hostname e os qualificadores de razao social
   observados no dataset). Duas empresas casam quando as chaves de
   identidade sao IGUAIS e nao vazias. ``'Bayer AG Pharmaceuticals'`` ->
   ``{bayer}`` == ``'Bayer'`` -> ``{bayer}``; ``'MTU Aero Engines AG'`` ->
   ``{mtu, aero, engines}`` != ``'MTU Maintenance Hannover GmbH'`` ->
   ``{mtu, maintenance, hannover}`` (nao casa, correto).
4. GUARDRAILS (ambos presentes; ausencia != dado falso, mesma disciplina do
   mirror_dedup Fase C):
   - ``country`` diferente -> par REJEITADO;
   - ``salary`` diferente (quando ambos parseiam para valor+moeda) -> par
     REJEITADO. Nota medida: no universo elegivel 13/10-15/10 o campo
     ``salary`` esta vazio em 100% das vagas (cobertura da coluna e zero) —
     o guardrail e defensivo, nunca disparou; a evidencia de salario
     identico do par Bayer vive no TEXTO da description (2.280 EUR brutto
     vs € 2.280), fora do escopo deste estagio.
   ``employment_type`` NAO e guardrail aqui (diferente da Fase C): entre
   FONTES distintas o vocabulario do campo e incompativel (``FULL_TIME`` x
   None nos pares medidos) — usa-lo reprovaria espelhos reais. Ele segue
   valendo como criterio de VENCEDOR via ``_prefer``.
5. CANONICAL: (a) FONTE PRIMARIA — o registro de dataset (``source`` com
   prefixo ``sf_dataset:``) vence o twin de registry/ATS (inversao
   arquitetural da F3 declarada no proprio CLI: "dataset e fonte primaria,
   registry e lista de interesse"; e o registro do dataset carrega os
   campos indexados do feed — ``employment_type``/``posted_at``/referencia
   BA — usados por ranking/decay); (b) mesma classe de fonte -> ``_prefer``
   existente (description > employment_type > frescor > ordem de entrada),
   reusada verbatim para nao inventar uma segunda regra de vencedor.
   O NAO-canonico recebe ``duplicate_of = <id do canonico>`` (provenance) e
   SAI do conjunto elegivel (display/digest/ranking). O canonico NUNCA e
   alterado (sem merge de campos).
6. Reversibilidade: sub-estagio do estagio de dedup — ``--no-dedup``
   desliga tambem este (mesma semantica do F23/Fase C).

LIMITE DOCUMENTADO (conservador por construcao, mesmo trade-off da F5): o
titulo do par precisa convergir na chave DE/EN; conteudo fora do dicionario
minimo (ex.: "Betriebswirtschaft" vs "Business Administration") NAO funde —
um dup perdido e mais barato que uma fusao errada.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

# Reuso deliberado da MESMA chave de titulo do tier DE/EN (F5) e da regra de
# vencedor documentada do modulo de dedup (fonte unica da verdade).
from internship_finder.dedup import _de_en_title_key, _prefer, normalize_location
from internship_finder.opportunity_intel import CITY_ALIASES as _CITY_ALIASES

# Rotulo do sub-estagio: chave de ``estatisticas`` (CLI/JSONL ``type: run``)
# e do registro de provenance ``type: dedup_cross_source``.
KEY_CROSS_SOURCE = "cross_source_mirror"

# Campo de provenance gravado no registro NAO-canonico (que sai do eligible).
DUPLICATE_OF_FIELD = "duplicate_of"

# Prefixo das fontes de DATASET (F3: fonte primaria do universo).
_DATASET_SOURCE_PREFIX = "sf_dataset:"

# CEP/PLZ inicial da localizacao ("51373 Leverkusen, ..." -> "leverkusen").
_PLZ_PREFIX = re.compile(r"^\d{4,5}\s+")

# Tokens que NAO carregam identidade empresarial (removidos da chave de
# empresa). Lista MINIMALISTA E INTENCIONAL (mesma disciplina do dicionario
# DE/EN da F5), em 4 familias:
#   (1) formas legais/juridicas DE e internacionais;
#   (2) qualificadores corporativos/geograficos genericos;
#   (3) artefatos de hostname (a fonte phenom grava o host como "empresa":
#       "www.careers.philips.com");
#   (4) qualificadores de razao social observados no dataset medido
#       ("AG Pharmaceuticals" da Bayer, "Procurement Company S.a.r.l." da
#       Vodafone, "SE Haupverwaltung" da AUMOVIO).
# Qualquer token FORA desta lista impede o casamento: e o freio de
# conservadorismo (ex.: "Rexroth"/"Healthineers"/"Maintenance" mantem as
# empresas separadas).
NON_IDENTITY_TOKENS = frozenset(
    """
    gmbh mbh ag se kg kgaa co ohg gbr ug ev egen inc ltd llc bv nv plc sarl
    sa srl spa asa ab oy aps
    deutschland germany holding group groups international company companies
    www com de net org eu io careers career jobs job
    verwaltung haupverwaltung hauptverwaltung
    pharma pharmaceuticals pharmaceutical procurement
    """.lower().split()
)

_NUMBER_RE = re.compile(r"\d[\d.,]*")


def _strip_accents(text: str) -> str:
    """Remove acentos ('Höhe' -> 'Hohe'); mesma disciplina do dedup.py."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def city_key(location: str | None) -> str:
    """Cidade canonica da localizacao (location-aware): CEP fora + aliases.

    Duas localizacoes da MESMA cidade em FORMATOS/IDIOMAS diferentes
    convergem: ``"51373 Leverkusen, Nordrhein Westfalen, Deutschland"`` ->
    ``"leverkusen"``; ``"Leverkusen, North Rhine Westfalia, DE"`` ->
    ``"leverkusen"``; ``"Munich, Bayern, Germany"`` -> ``"munchen"``
    (``CITY_ALIASES``). Vazio quando nao ha localizacao utilizavel.
    """
    loc = normalize_location(location)
    if not loc:
        return ""
    city = loc.split(",", 1)[0].strip()
    city = _PLZ_PREFIX.sub("", city).strip()
    return _CITY_ALIASES.get(city, city)


def company_identity(company: str | None) -> frozenset[str]:
    """Chave de IDENTIDADE empresarial: tokens menos ``NON_IDENTITY_TOKENS``.

    Conjunto vazio -> empresa sem identidade utilizavel (nunca casa).
    """
    text = (company or "").strip().casefold()
    # Formas legais abreviadas com pontos ("S.a.r.l.", "S.A.", "G.m.b.H."):
    # colapsa os pontos INTERNOS a siglas curtas ANTES de tokenizar, para que
    # "s.a.r.l." gere o token "sarl" (a lista de formas legais usa a forma
    # sem pontos). Siglas de uma letra isolada (ex.: "K. Müller GmbH") ficam.
    text = re.sub(r"(?<=\b[a-z])\.(?=[a-z]\b)", "", text)
    text = _strip_accents(text)
    tokens = {t for t in re.findall(r"[a-z0-9]+", text) if t not in NON_IDENTITY_TOKENS}
    return frozenset(tokens)


def salary_value(job: dict[str, Any]) -> tuple[float, str | None] | None:
    """Valor canonico do campo ``salary`` (quando parseavel), senao ``None``.

    Normaliza separador de milhar/decimal (``"2.280 €"`` -> ``(2280.0, "eur")``,
    ``"€ 2,280.00"`` -> ``(2280.0, "eur")``) para comparar o MESMO salario
    escrito em convencoes diferentes. Formato nao interpretavel -> ``None``
    (ausencia/ignorancia != divergencia: nunca reprova um par por isso).
    """
    raw = job.get("salary")
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return (round(float(raw), 2), None)
    text = str(raw)
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    number = _parse_number(match.group(0))
    if number is None:
        return None
    value = round(number, 2)
    low = text.lower()
    currency = "eur" if ("eur" in low or "€" in low) else None
    if currency is None and ("usd" in low or "$" in low):
        currency = "usd"
    return (value, currency)


def _parse_number(number: str) -> float | None:
    """Converte um numero com separadores ambiguos em float (``None`` = invalido).

    Convencao de planilha: com AMBOS separadores, o ULTIMO e o decimal
    (``"1.234,50"`` e ``"1,234.50"`` -> 1234.5); com apenas um e exatamente 3
    digitos depois, ele e milhar (``"2.280"`` -> 2280.0); caso contrario e
    decimal (``"2,50"`` -> 2.5).
    """
    if "." in number and "," in number:
        decimal_sep = "." if number.rfind(".") > number.rfind(",") else ","
        thousands = "," if decimal_sep == "." else "."
        number = number.replace(thousands, "").replace(decimal_sep, ".")
    elif "." in number or "," in number:
        sep = "." if "." in number else ","
        digits_after = len(number) - number.rfind(sep) - 1
        if digits_after == 3 and len(number.split(sep)[0]) <= 3:
            number = number.replace(sep, "")
        else:
            number = number.replace(sep, ".")
    try:
        return float(number)
    except ValueError:
        return None


def _is_dataset(job: dict[str, Any]) -> bool:
    """Vaga veio da fonte de dataset (F3: fonte primaria do universo)?"""
    return str(job.get("source") or "").startswith(_DATASET_SOURCE_PREFIX)


def _canonical_prefer(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """``candidate`` deve ser o canonico no lugar de ``current``?

    (a) registro de DATASET vence twin de registry/ATS (fonte primaria, F3);
    (b) mesma classe -> ``dedup._prefer`` verbatim (description >
    employment_type > frescor > ordem de entrada).
    """
    if _is_dataset(candidate) != _is_dataset(current):
        return _is_dataset(candidate)
    return _prefer(candidate, current)


def _pair_ok(job_a: dict[str, Any], job_b: dict[str, Any]) -> bool:
    """Os dois lados do par candidato sao a MESMA vaga? (guardrails).

    Requer identidade de empresa IGUAL e nao vazia; reprova ``country``
    divergente e ``salary`` divergente quando ambos presentes/parseaveis.
    """
    identity_a = company_identity(job_a.get("company"))
    if not identity_a or identity_a != company_identity(job_b.get("company")):
        return False
    country_a, country_b = job_a.get("country"), job_b.get("country")
    if country_a and country_b and str(country_a).lower() != str(country_b).lower():
        return False
    salary_a, salary_b = salary_value(job_a), salary_value(job_b)
    if salary_a and salary_b and salary_a != salary_b:
        return False
    return True


def _group_key(job: dict[str, Any]) -> tuple[str, str] | None:
    """Chave de agrupamento (cidade normalizada, titulo DE/EN normalizado).

    ``None`` quando falta qualquer um dos dois (sem chave, sem fusao).
    """
    city = city_key(job.get("location"))
    title = _de_en_title_key(job.get("title"))
    if not city or not title:
        return None
    return city, title


def _source(job: dict[str, Any]) -> str:
    return str(job.get("source") or "").strip()


def deduplicate_cross_source(
    jobs: list[dict[str, Any]] | list[Any],
) -> tuple[list[dict[str, Any]], dict[str, int], list[tuple[dict[str, Any], dict[str, Any], str]]]:
    """Remove espelhos CROSS-FONTE da mesma vaga (F48) — campos estruturados.

    Roda DEPOIS de ``deduplicate`` (tiers 1-5) + ``deduplicate_ms_wildcard``
    (F23) + ``deduplicate_mirrors_de_en`` (Fase C), sobre o conjunto
    ELEGIVEL e ANTES da hidratacao. Retorna o MESMO contrato dos outros
    estagios: ``(sem_duplicatas, estatisticas, removidas)`` com

    - ``estatisticas``: ``{KEY_CROSS_SOURCE: n}`` (soma no relatorio e no
      ``dedup_removed`` do registro ``type: run``);
    - ``removidas``: lista ``(canonico, duplicata, rotulo)`` para auditoria —
      a duplicata carrega ``duplicate_of = <id do canonico>``.

    Determinismo: iteracao na ordem de entrada; para cada vaga a PRIMEIRA
    posicao compativel ja vista na mesma (cidade, titulo) decide a fusao;
    o canonico segue ``_canonical_prefer``. Idempotente: apos o estagio nao
    sobra nenhum par cross-fonte compativel (re-rodar e no-op).
    """
    normalized = [item.to_dict() if hasattr(item, "to_dict") else item for item in jobs]

    out: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    dead: set[int] = set()
    removed: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    stats: Counter[str] = Counter()

    for job in normalized:
        key = _group_key(job)
        if key is None:
            out.append(job)
            continue

        matched_pos: int | None = None
        for pos in buckets[key]:
            if pos in dead:
                continue  # posicao ja fundida (residente perdedor)
            resident = out[pos]
            if not _source(resident) or _source(resident) == _source(job):
                continue  # mesmo tenant/origem: nao e este o buraco
            if _pair_ok(resident, job):
                matched_pos = pos
                break

        if matched_pos is None:
            out.append(job)
            buckets[key].append(len(out) - 1)
            continue

        resident = out[matched_pos]
        if _canonical_prefer(job, resident):
            # Candidata vence: o residente sai da posicao dele (nao e
            # substituido in place — a subsequencia sobrevivente fica na
            # ordem de entrada original, byte a byte) e a candidata entra na
            # posicao NATURAL dela no fim da iteracao.
            canonical, duplicate = job, resident
            dead.add(matched_pos)
            out.append(job)
            buckets[key].append(len(out) - 1)
        else:
            canonical, duplicate = resident, job
        duplicate[DUPLICATE_OF_FIELD] = canonical.get("id")
        removed.append((canonical, duplicate, KEY_CROSS_SOURCE))
        stats[KEY_CROSS_SOURCE] += 1

    return [job for idx, job in enumerate(out) if idx not in dead], dict(stats), removed


def cross_source_provenance(
    removed: list[tuple[dict[str, Any], dict[str, Any], str]],
) -> list[dict[str, Any]]:
    """Registros de provenance (JSON-safe) das fusoes cross-fonte.

    Um registro por fusao: id da duplicata + ``duplicate_of`` (id do
    canonico) + empresa/cidade/fontes/URLs dos dois lados. Nenhum campo e
    inventado: tudo vem das proprias vagas; a duplicata SAI do eligible, o
    rastro fica aqui e na metrica diaria.
    """
    rows: list[dict[str, Any]] = []
    for canonical, duplicate, _label in removed:
        rows.append(
            {
                "id": duplicate.get("id"),
                DUPLICATE_OF_FIELD: duplicate.get(DUPLICATE_OF_FIELD),
                "canonical_id": canonical.get("id"),
                "company_duplicate": duplicate.get("company"),
                "company_canonical": canonical.get("company"),
                "city": city_key(duplicate.get("location")),
                "title_duplicate": duplicate.get("title"),
                "source_duplicate": _source(duplicate),
                "source_canonical": _source(canonical),
                "url_duplicate": duplicate.get("url"),
                "url_canonical": canonical.get("url"),
            }
        )
    return rows
