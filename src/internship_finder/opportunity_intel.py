"""Opportunity Intelligence — Fase 7 (Company & Location Intelligence).

Camada DETERMINISTICA, offline e complementar ao ranking. Nenhum valor
aqui entra no score de relevancia (Job Fit): esta camada responde "o que
devo saber antes de decidir", nao "quanto a vaga combina comigo".

Tres camadas separadas (enunciado da Fase 7):

- Job Fit: score do pipeline (ranking.py / materials_ranking.py).
- Candidate Fit: app_intel.py (Fase 6) — sinais objetivos de candidatura.
- Opportunity Intelligence: este modulo — empresa, beneficios, carreira,
  internship→fulltime, turnover, localizacao, custo de vida, salario.

Principios (enunciado Fase 7):

- **Nada e inventado**: dados de empresa/custo de vida vêm de arquivos
  curados versionados no repo (``company_intel/*.json``), cada item com
  fonte + URL + data de verificacao + qualidade. Salario e modalidade sao
  extraidos por EVIDENCIA no proprio anuncio (nunca estimados).
- **Fonte externa nao derruba o pipeline**: arquivo ausente/malformado
  vira dict vazio; campos faltantes viram ``None`` (interface mostra
  "Not available"/"Not mentioned"). Zero rede em tempo de render.
- **Nunca transformar dados em opiniao**: turnover/layoffs sao registrados
  como fato com fonte e periodo; nenhum score de empresa e calculado.
- **Internship → Full-time pathway** nunca vira probabilidade: so os
  estados Explicitly supported / Evidence available / Not mentioned /
  Unknown, a partir da FONTE curada (politica explicita da empresa).
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

# Normalização de texto para detectores (item 5, auditoria pós-Fases 1–8):
# definida em ``app_intel`` (lar dos detectores de idioma/WA); este módulo
# importa de lá — sem ciclo (``app_intel`` não importa este módulo).
from internship_finder.app_intel import normalize_text

# ---------------------------------------------------------------------------
# Arquivos curados (versionados no repo; estruturas reutilizaveis por empresa)
# ---------------------------------------------------------------------------

DEFAULT_COMPANY_INTEL_PATH = Path("company_intel/company_intelligence.json")
DEFAULT_LOCATION_INTEL_PATH = Path("company_intel/location_intel.json")

# Qualidade da fonte (enunciado Fase 7, secao 6).
SOURCE_QUALITIES = ("primary", "secondary", "aggregated", "unknown")

# Estados do caminho Internship -> Full-time (nunca uma probabilidade).
INTERNSHIP_PATHWAY_STATES = (
    "explicitly_supported",
    "evidence_available",
    "not_mentioned",
    "unknown",
)

# Modalidades de trabalho por EVIDENCIA no anuncio.
WORK_MODES = ("remote", "hybrid", "on_site", "not_mentioned")


def _norm(s: str) -> str:
    """Normaliza para comparacao exata: casefold + acentos -> base + 'ß'->'ss'.

    "München"/"Munchen"/"MÜNCHEN" colapsam em "munchen" (mesmo padrao do
    geocoding). Nao faz substring — o match e sempre pelo valor inteiro."""
    text = unicodedata.normalize("NFD", str(s).strip().casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.replace("ß", "ss").split())


def load_company_intel(path: str | Path | None = None) -> dict[str, dict]:
    """Le o arquivo curado de Company Intelligence; {} em qualquer falha.

    Chave: nome canonico da empresa normalizado. Cada entrada carrega
    ``aliases`` (nomes alternativos observados) e campos opcionais com
    fontes (``sources``). Arquivo ausente, JSON quebrado ou lista vazia
    nunca levantam excecao — a interface cai em "Not available".
    """
    if path is None:
        path = DEFAULT_COMPANY_INTEL_PATH
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = raw.get("companies") if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            return {}
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("company"):
            continue
        out[_norm(entry["company"])] = entry
        for alias in entry.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                out[_norm(alias)] = entry
    return out


def load_location_intel(path: str | Path | None = None) -> dict[str, dict]:
    """Le o arquivo curado de custo de vida; {} em qualquer falha.

    Chave: cidade normalizada (ex.: "munchen"); cada entrada tem
    ``source`` (nome+URL) e ``checked`` (data da verificacao). Nunca
    fabrica valores; cidade ausente -> None no consultante.
    """
    if path is None:
        path = DEFAULT_LOCATION_INTEL_PATH
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = raw.get("cities") if isinstance(raw, dict) else raw
        if not isinstance(entries, dict):
            return {}
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for city, data in entries.items():
        if isinstance(data, dict):
            out[_norm(city)] = data
    return out


def company_intel_for(job: dict, intel_map: dict[str, dict]) -> dict | None:
    """Entrada de Company Intelligence da vaga; None quando nao ha dados.

    ``intel_map`` e o mapa normalizado de ``load_company_intel`` (empresa
    canconica + aliases). Reuso: a MESMA entrada atende todas as vagas da
    empresa — a coleta nao e repetida por vaga (estrutura reutilizavel).
    """
    name = str(job.get("company") or "").strip()
    if not name:
        return None
    return intel_map.get(_norm(name))


# ---------------------------------------------------------------------------
# Salario — SOMENTE evidencia do proprio anuncio (nunca estimado)
# ---------------------------------------------------------------------------

# Padroes DE/EN de anuncios que citam valor ("Gehalt: 2.117 €/Monat",
# "Vergütung: €1.500–€1.800", "Salary: EUR 2,000 per month").
# Uma clausula monetaria generica: "2.117 €/Monat", "EUR 2,000 per month",
# "€3,000 – €3,500 / month", "1.500 € - 1.800 €". Currencies opcionais de
# cada lado do(s) numero(s) e periodo opcional logo apos.
_MONEY_CLAUSE = re.compile(
    r"(?P<pre>(?:€|eur|euro)\s*)?"
    r"(?P<a>\d{1,3}(?:[.,]\d{3})*|\d+(?:[.,]\d+)?)"
    r"(?P<post>\s*(?:€|eur|euro))?"
    r"(?:\s*[–\-–]\s*(?P<pre2>(?:€|eur|euro)\s*)?"
    r"(?P<b>\d{1,3}(?:[.,]\d{3})*|\d+(?:[.,]\d+)?)"
    r"(?P<post2>\s*(?:€|eur|euro))?)?"
    r"(?P<period>\s*(?:per\s+)?(?:monat|month|jahr|year))?",
    re.IGNORECASE,
)
_SALARY_LABEL = re.compile(
    r"\b(?:gehalt|vergütung|verguetung|bezahlung|salary|compensation|pay)\b",
    re.IGNORECASE,
)
_SALARY_LABEL_WINDOW = 40


def _to_number(text: str) -> float | None:
    """'2.117'/'2,000'/'1,5' -> numero real (sem ambiguidade).

    Padrao DE/EN de milhar (1-3 digitos + separadores de 3 em 3) vira
    inteiro; senao a virgula e decimal (ex.: 1,5). Nunca divide nem
    arredonda valores reais.
    """
    s = text.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", s):
        return float(s.replace(",", "").replace(".", ""))
    cleaned = s.replace(".", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def _to_float_or_none(value: Any) -> float | None:
    """Valor monetário estruturado -> float; None se ausente/inválido/<=0."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _norm_period(value: Any) -> str | None:
    """``MONTH``/``month``/``Monat`` -> ``month``; ``YEAR``/``year`` -> ``year``.

    Preserva a periodicidade que a fonte declara; NUNCA infere quando
    ausente (upstream recruitee publica ``salary_period`` vazio).
    """
    if not value:
        return None
    v = str(value).strip().casefold()
    if v in ("month", "monat", "monatlich", "monthly"):
        return "month"
    if v in ("year", "jahr", "jahrlich", "jaehrlich", "annually", "annual"):
        return "year"
    if v in ("hour", "stunde", "hourly"):
        return "hour"
    return None


def job_salary(job: dict) -> dict | None:
    """Salário citado NO ANUNCIO; None sem evidencia (nunca inventa).

    DUAS fontes de evidência, SEM conflito (item 6 da auditoria):

    1. **Campo estruturado do ATS** (``raw.salary_min``/``raw.salary_max``/
       ``raw.salary_currency``/``raw.salary_period`` — exposto pelo scraper
       recruitee do ats-scrapers): quando ``salary_min``/``salary_max`` são
       números > 0, são a evidência mais forte — valor da própria fonte,
       sem parsing. Moeda preservada; periodicidade preservada quando
       presente (``MONTH``/``month``) e ``None`` quando ausente (NUNCA
       inferida — o upstream recruitee não a publica).
    2. **Clausula monetária no texto** (regex ``_MONEY_CLAUSE`` existente):
       fallback quando não há campo estruturado.

    Retorna ``{"min", "max", "period", "text", "currency"}`` — ``min``==
    ``max`` para valor único; ``text`` e o trecho exato da fonte (para o
    campo estruturado, a representação canônica do valor); ``currency`` só
    no caminho estruturado (quando a fonte declara). No caminho textual o
    comportamento e o MESMO de antes (periodo default ``month`` quando a
    clausula cita valor sem periodo — regra Fase 7; nunca converte).
    """
    raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}
    if raw:
        lo = _to_float_or_none(raw.get("salary_min"))
        hi = _to_float_or_none(raw.get("salary_max"))
    else:
        lo = hi = None
    if lo is not None or hi is not None:
        if lo is None:
            lo = hi
        if hi is None:
            hi = lo
        period = _norm_period(raw.get("salary_period"))
        currency = str(raw.get("salary_currency") or "").strip().upper() or None
        text = f"{currency or 'EUR'} {lo:g}–{hi:g}"
        if period:
            text = f"{text} / {period}"
        return {"min": lo, "max": hi, "period": period,
                "text": text, "currency": currency}
    text = " ".join(
        normalize_text(x) for x in (job.get("title"), job.get("description")) if x
    )
    if not text:
        return None
    best: dict | None = None
    for m in _MONEY_CLAUSE.finditer(text):
        start, end = m.start(), m.end()
        window = text[max(0, start - _SALARY_LABEL_WINDOW): end + 60]
        has_currency = any(m.group(k) for k in ("pre", "post", "pre2", "post2"))
        has_label = _SALARY_LABEL.search(window) is not None
        has_period = m.group("period") is not None
        if not (has_currency and (has_label or has_period)) \
                and not (has_label and has_period):
            continue  # valor numerico sem moeda/rotulo/periodo NAO e salario
        lo_raw = m.group("a")
        lo = _to_number(lo_raw)
        hi_raw = m.group("b")
        hi = _to_number(hi_raw) if hi_raw else None
        if lo is None and hi is None:
            continue
        if lo is None:
            lo = hi
        if hi is None:
            hi = lo
        if lo > hi:
            lo, hi = hi, lo
        period_m = m.group("period")
        period = "year" if period_m and period_m.strip().casefold() in ("jahr", "year") else "month"
        clause = {"min": lo, "max": hi, "period": period, "text": m.group(0).strip()}
        # Preferencia: clausula com periodo explicito vence a sem periodo
        # (mesmo anuncio pode citar "Gehalt: X €" e depois "pro Jahr").
        if best is None or (has_period and best.get("_period") is not True):
            clause["_period"] = has_period
            best = clause
    if best is None:
        return None
    best.pop("_period", None)
    return best


# ---------------------------------------------------------------------------
# Modalidade — EVIDENCIA no anuncio (nunca inferida do local/empresa)
# ---------------------------------------------------------------------------

_WORK_MODE_RE = {
    "hybrid": re.compile(
        r"\bhybrid\w*\b|mischung\s+(?:aus|von)\s+präsenz|\bmischung\s+aus\s+"
        r"home\s*office|teilweise\s+(?:remote|home)\s*office|flexible\s+split\b",
        re.IGNORECASE,
    ),
    "remote": re.compile(
        r"\b(?:fully|full|100%?|complete)?\s*remote\b|\b(?:voll|komplett)?"
        r"\s*(?:remote|home\s*office)\b|work\s+from\s+anywhere\b",
        re.IGNORECASE,
    ),
    "on_site": re.compile(
        r"\b(?:on[\s\-]?site|vor\s+ort|in\s+(?:the\s+)?office|in\s+unserem\s+"
        r"büro|am\s+(?:standort|arbeitsort))\b",
        re.IGNORECASE,
    ),
}


def work_mode(job: dict) -> str:
    """Wok mode por evidencia: remote / hybrid / on_site / not_mentioned.

    ``raw.is_remote`` verdadeiro decide remote; senao, palavras-chave no
    titulo+descricao. ``hybrid`` vence ``remote``/``on_site`` difusos
    (mencoes de "remote" ao lado de "hybrid" indicam regime hibrido).
    Sem evidencia -> ``not_mentioned`` (presenca em escritorio NAO e
    inferida).
    """
    raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}
    if raw.get("is_remote") is True:
        return "remote"
    text = " ".join(normalize_text(x) for x in (job.get("title"), job.get("description")) if x)
    if not text:
        return "not_mentioned"
    if _WORK_MODE_RE["hybrid"].search(text):
        return "hybrid"
    if _WORK_MODE_RE["remote"].search(text):
        return "remote"
    if _WORK_MODE_RE["on_site"].search(text):
        return "on_site"
    return "not_mentioned"


# ---------------------------------------------------------------------------
# Localizacao — cidade/regiao a partir da string real; nunca inferida
# ---------------------------------------------------------------------------

# Aliases de cidade (item 9, auditoria pós-Fases 1–8): nome EN que aparece
# em vagas reais do dataset -> CHAVE CANÔNICA já curada no
# ``location_intel.json``. Somente aliases COMPROVADOS (contagem no
# run 23/09: Munich 14, Cologne 1, Nuremberg 1 — todos com entrada
# canônica correspondente no catálogo). Determinístico, sem fuzzy
# matching: chave exata após a normalização existente (_norm). O alias
# serve APENAS para localizar o registro de enriquecimento — o valor
# original exibido ao usuário NUNCA muda.
CITY_ALIASES: dict[str, str] = {
    "munich": "munchen",      # EN (Numbeo/careers EN) -> München
    "cologne": "koln",        # EN -> Köln
    "nuremberg": "nurnberg",  # EN -> Nürnberg
}


def resolve_city_key(city: str | None) -> str | None:
    """Chave de enriquecimento da cidade: alias -> canônica; senão _norm.

    ``Munich``/``München``/``Munchen`` colapsam na MESMA chave curada
    ``munchen``. Cidade desconhecida devolve a própria chave normalizada
    (lookup falha em ``cost_of_living`` -> None, como antes); cidade vazia
    -> None. A cidade ORIGINAL exibida ao usuário não é alterada.
    """
    if not city or not str(city).strip():
        return None
    key = _norm(city)
    return CITY_ALIASES.get(key, key)


# Primeiro segmento com cara de rua (numero/strasse/street/estrada) — nesses
# casos a cidade e o segmento seguinte ao codigo postal, se houver.
_STREETISH = re.compile(r"\d|stra\b|str\.|strasse|street|road|weg\b|allee|platz", re.IGNORECASE)
_COUNTRY_ONLY = re.compile(
    r"^(?:germany|deutschland|de|allemagne|holland|netherlands|niederlande|"
    r"austria|österreich|switzerland|schweiz|suisse)$",
    re.IGNORECASE,
)


def city_and_region(job: dict) -> dict:
    """Cidade/regiao/pais apresentaveis a partir da string de local.

    Regra conservadora: usa SOMENTE a string ja presente. ``location``
    vazio -> tudo None. ``streetish`` no primeiro segmento -> tenta o
    segmento apos o CEP; sem CEP claro, None (nao adivinha). Pais vem de
    ``country_iso`` (campo real). Nunca inferir "Alemanha inteira" como
    cidade.
    """
    location = str(job.get("location") or "").strip()
    iso = str(job.get("country_iso") or job.get("country") or "").strip()
    if not location and not iso:
        return {"city": None, "region": None, "country": iso or None}
    parts = [p.strip() for p in location.split(",") if p.strip()]
    city, region = None, None
    if parts:
        first = parts[0]
        # "Germany"/"Deutschland"/"DE" como unico dado nao e uma cidade — nao
        # inferir localizacao precisa (regra do enunciado).
        if _COUNTRY_ONLY.search(first):
            return {"city": None, "region": None, "country": iso or None}
        if _STREETISH.search(first):
            found_in = -1
            for i, p in enumerate(parts):
                toks = p.split()
                for k, tok in enumerate(toks):
                    if re.fullmatch(r"\d{4,5}", tok):
                        rest = " ".join(toks[k + 1:])
                        if rest:
                            city = rest
                        elif i + 1 < len(parts):
                            city = parts[i + 1].strip()
                        found_in = i
                        break
                if city:
                    break
            if city and found_in + 1 < len(parts):
                # Regiao real: segmento depois do endereco/CEP.
                region = parts[found_in + 1]
        else:
            city = first
            if len(parts) >= 2:
                region = parts[1]
    return {"city": city, "region": region, "country": iso or None}


def cost_of_living(city: str | None, loc_map: dict[str, dict]) -> dict | None:
    """Custo de vida aproximado da cidade; None sem cidade conhecida.

    O lookup usa a chave de enriquecimento (``resolve_city_key``): aliases
    explícitos (``Munich`` -> ``munchen``) casam com a entrada canônica
    curada; o valor original da vaga não é alterado.
    """
    key = resolve_city_key(city)
    if not key:
        return None
    return loc_map.get(key)


# ---------------------------------------------------------------------------
# Duracao da vaga (Job) — evidencia explicita no anuncio
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(
    r"\b(?:for\s+|von\s+|über\s+)?(?P<n>[0-9]{1,2})\s*[–\-–]?\s*"
    r"(?P<n2>[0-9]{1,2})?\s*(?:monate|months|month|monaten)\b",
    re.IGNORECASE,
)


def job_duration(job: dict) -> dict | None:
    """Duracao citada no anuncio (meses); None sem evidencia.

    Nunca soma/inventa: ``{"min", "max"}`` quando ha faixa (ex.: "6–12
    Monate"), valor unico caso contrario. Nao deriva de datas."""
    text = " ".join(normalize_text(x) for x in (job.get("title"), job.get("description")) if x)
    m = _DURATION_RE.search(text)
    if not m:
        return None
    lo = int(m.group("n"))
    hi = int(m.group("n2")) if m.group("n2") else lo
    if hi < lo:
        lo, hi = hi, lo
    return {"min": lo, "max": hi}


# ---------------------------------------------------------------------------
# Pathway (Internship -> Full-time) — estados a partir da FONTE curada
# ---------------------------------------------------------------------------

PATHWAY_STATE_LABELS = {
    "explicitly_supported": "Explicitly supported",
    "evidence_available": "Evidence available",
    "not_mentioned": "Not mentioned",
    "unknown": "Unknown",
}


def pathway_state(intel: dict | None) -> str:
    """Estado do pathway da empresa; ``unknown`` sem dados curados.

    O estado vem do campo ``internship_pathway`` do arquivo curado (que so
    registra politicas EXPLICITAS da empresa com fonte). Quando a entrada
    nao existe ou o campo esta ausente -> ``unknown`` (sem coleta externa
    automatica — nunca estimar probabilidade).
    """
    if not intel:
        return "unknown"
    state = str(intel.get("internship_pathway") or "unknown")
    return state if state in INTERNSHIP_PATHWAY_STATES else "unknown"


# ---------------------------------------------------------------------------
# Visa policy (item 11 da auditoria) — estado da EMPRESA, curado com fonte
# ---------------------------------------------------------------------------

# Estados da politica de visto/autorizacao da empresa (analogia exata com
# INTERNSHIP_PATHWAY_STATES; ``visa_policy`` e da EMPRESA e
# ``work_authorization`` e da VAGA — nunca um deriva do outro).
#
# - ``explicit_support``: fonte oficial declara suporte INCONDICIONAL ao
#   processo de visto/autorizacao ("we support you with the visa process").
# - ``explicit_no_support``: fonte oficial declara que NAO patrocina/assist
#   ("we do not sponsor visas", "no visa sponsorship").
# - ``candidate_must_have_authorization``: fonte oficial exige autorizacao
#   previa do candidato ("must have a valid work permit to apply").
# - ``unclear``: fonte oficial TOCA no tema mas de forma condicional/
#   seletiva ("may sponsor", "case-by-case", "for eligible roles").
# - ``not_verified``: sem evidencia publica verificavel (default).
VISA_POLICY_STATES = (
    "explicit_support",
    "explicit_no_support",
    "candidate_must_have_authorization",
    "unclear",
    "not_verified",
)


def visa_policy_state(intel: dict | None) -> str:
    """Estado da politica de visto da empresa; ``not_verified`` default.

    Le o campo curado ``visa_policy`` (string de estado) da entrada de
    Company Intelligence — a curadoria ja aplicou a regra semantica:
    declaracoes CONDICIONAIS ("may sponsor", "case-by-case", "for
    eligible roles and locations", "coverage varies") sao registradas
    como ``unclear`` com a citacao textual preservada na fonte. Entrada
    ausente, campo ausente ou valor invalido -> ``not_verified``
    (analogia exata com ``pathway_state``; nunca promove a explicit_*).

    Independencia estrutural: ``visa_policy`` e da EMPRESA (curada,
    fonte oficial) e ``work_authorization`` e da VAGA (detector textual
    do anuncio) — nunca um deriva do outro e nenhum dos dois entra no
    score de relevancia.
    """
    if not intel:
        return "not_verified"
    state = str(intel.get("visa_policy") or "not_verified")
    return state if state in VISA_POLICY_STATES else "not_verified"


def pathway_percentage(intel: dict | None) -> dict | None:
    """Percentual oficial de efetivacao (dado factual de fonte), se houver.

    ``{"value", "text", "source"}`` somente quando o arquivo curado traz a
    estatistica explicita e confiavel; ``None`` caso contrario ("Not
    disclosed" — nunca estimar)."""
    if not intel or not intel.get("pathway_percentage"):
        return None
    pct = intel["pathway_percentage"]
    if not isinstance(pct, dict) or not pct.get("value"):
        return None
    return pct


def turnover_summary(intel: dict | None) -> dict | None:
    """Turnover/forca de trabalho registrado com fonte; None sem dado.

    ``{"kind", "detail", "source", "checked", "period"}`` — apenas dados
    publicos confiaveis curados; sem valor -> None (a interface mostra
    "Not available"). Nunca vira avaliacao de empresa.
    """
    if not intel or not intel.get("turnover"):
        return None
    t = intel["turnover"]
    if not isinstance(t, dict) or not t.get("source"):
        return None
    return t