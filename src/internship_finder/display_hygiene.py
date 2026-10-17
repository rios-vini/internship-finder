"""F54 — Higiene de display: sanitizer de mojibake + aliases de empresa.

Dois defeitos de credibilidade visíveis na página pública, corrigidos
NO RENDER (este módulo é display-only — o dataset ``data/`` nunca é
escrito; o ``job`` original NUNCA é mutado, o consumidor recebe uma
CÓPIA RASA com os campos de exibição higienizados):

1. **Mojibake UTF-8-decodado-como-latin-1** (padrão real medido no
   card #99 do build 15/10: ``QualitÃ¤t`` → ``Qualität``). O texto
   original era UTF-8 válido; alguma camada a montante decodou os
   bytes como latin-1/cp1252. O conserto é a inversão exata:
   re-encodear latin-1 → re-decodar UTF-8. DETERMINÍSTICO e zero
   dependências (NÃO usar ftfy — decisão da spec).

2. **Aliases de display de empresa** (``config/display_aliases.json``):
   strings EXATAS de ``company`` do dataset → nome de exibição
   (ex.: ``careers.dhl.com`` → ``DHL``). Regra de honestidade (spec
   item 4): o alias troca SÓ o nome de exibição (branding), nunca
   inventa empresa; string incerta fica ORIGINAL. O match de intel
   (``company_intel_for``) continua pelo nome ORIGINAL — o alias
   não pode contaminar o pipeline (daí a cópia rasa no render).

Aplicação (spec item 5): ambos os regimes da página (top-N e
full-list) — o ponto único é o ``_cards_section`` do minimal_page.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = [
    "MOJIBAKE_RE",
    "fix_mojibake",
    "looks_mojibake",
    "load_display_aliases",
    "display_company",
    "display_job_view",
]

# Padrão do mojibake real (medido 16/10 no build ao vivo): sequência de
# 2+ chars onde o 1º é um lead byte UTF-8 renderizado como latin-1/cp1252
# (Ã/Ä/Ö/Ü/Â/… i.e. U+00C2–U+00F4 — os bytes 0xC2–0xF4 vêm a montante)
# seguido de continuation bytes (0x80–0xBF). O card #99 real decodifica
# como CP1252 (não latin-1 puro): os bytes 0x80–0x9F viram chars
# TIPOGRÁFICOS (Ÿ=U+0178 de 0x9F, „=U+201E, –=U+2013, "=U+201C…) —
# a classe de continuation abaixo cobre OS DOIS regimes (cp1252
# tipográficos + latin-1 U+00A0–U+00BF). Ex.: o PAR "ÃŸ" re-encoda
# cp1252 → bytes C3 9F → UTF-8 válido "ß". Matches de 1 char isolado
# (ex.: "café" já correto) não casam: exige o PAR, minimizando falsos
# positivos em texto já limpo. A validação REAL é o round-trip strict;
# o regex só delimita candidatos.
_CP1252_CONTINUATION_CHARS = (
    "\u0080-\u009f\u00a0-\u00bf"   # latin-1 (controles + A0–BF)
    "\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192"  # ŒœŠšŸŽžƒ
    "\u02c6\u02dc"                  # ˆ˜
    "\u2013\u2014\u2018\u2019\u201a\u201c\u201d\u201e"
    "\u2020\u2021\u2022\u2026\u2030\u2039\u203a\u20ac\u2122"  # –—''""„†‡•…‰‹›€™
)
MOJIBAKE_RE = re.compile(
    "[\u00c2-\u00f4][" + _CP1252_CONTINUATION_CHARS + "]+"
)


def fix_mojibake(text: str, *, _depth: int = 0) -> str:
    """Corrige mojibake UTF-8-decodado-como-latin-1 em ``text``.

    Determinístico, funções puras, zero dependências. Detecta
    sequências candidatas via ``MOJIBAKE_RE`` e conserta cada uma pelo
    round-trip: encode latin-1 → decode utf-8 STRICT. O decode strict
    é o VALIDADOR — se os bytes não formam UTF-8 válido, a sequência
    é texto legítimo e fica ORIGINAL (nunca "chuta").

    Texto já correto (ex.: "Qualität", "café") NÃO é alterado: seus
    chars acentuados ou não casam o regex, ou falham o round-trip
    (ex.: "é" = U+00E9 não é lead byte do padrão; "Ã" isolado sem
    continuation não casa).

    Recursão de segurança: após um conserto, o resultado é re-examinado
    (máx 3 passadas — mojibake duplo é raro; o loop para quando
    estabiliza). Idempotente: aplicar 2× = mesmo resultado de 1×.
    """
    if not isinstance(text, str) or not text or _depth > 3:
        return text
    changed = False

    def _fix(match: re.Match[str]) -> str:
        nonlocal changed
        chunk = match.group(0)
        fixed = None
        # Round-trip EXATO da falha, nos dois regimes de decodagem
        # errada a montante: latin-1 (0x80–0xBF 1:1) e cp1252 (bytes
        # 0x80–0x9F → chars tipográficos). Tenta cp1252 PRIMEIRO (o
        # caso real medido — o decode latin-1 levantaria UnicodeDecode
        # Error nos bytes 0x80–0x9F de verdade; cp1252 mapeia TODOS os
        # 256). Qualquer falha = texto legítimo → chunk original.
        try:
            fixed = chunk.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                fixed = chunk.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return chunk
        if fixed != chunk:
            changed = True
        return fixed

    result = MOJIBAKE_RE.sub(_fix, text)
    if not changed:
        return result
    return fix_mojibake(result, _depth=_depth + 1)


def looks_mojibake(text: str) -> bool:
    """True quando ``text`` carrega mojibake corrigível (title/company/
    location com padrão lead+continuation). Usado na provenance do
    relatório (job-ids/fontes afetados) — o render nunca precisa dele.
    """
    if not isinstance(text, str) or not text:
        return False
    for match in MOJIBAKE_RE.finditer(text):
        chunk = match.group(0)
        for codec in ("cp1252", "latin-1"):
            try:
                chunk.encode(codec).decode("utf-8")
                return True
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return False


def load_display_aliases(path: Path | str) -> dict[str, str]:
    """Lê ``config/display_aliases.json`` → {company original → display}.

    Formato versionado (padrão company_watchlist/employer_quality):
    ``{"aliases": {"careers.dhl.com": "DHL", ...}}``. Best-effort
    total: arquivo ausente/corrompido → ``{}`` (página idêntica à
    pré-F54, nunca erro). Chaves/vazios não-string são descartados.
    Match EXATO por string (spec item 2) — sem casefold, sem substring;
    ``_norm`` NÃO é aplicado (aliases são strings EXATAS medidas no
    dataset).
    """
    try:
        with Path(path).open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict):
        raw = data.get("aliases")
    else:
        raw = None
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if (isinstance(key, str) and isinstance(value, str)
                and key and value):
            out[key] = value
    return out


def display_company(company: str | None, aliases: dict[str, str]) -> str:
    """Nome de exibição da empresa: alias EXATO quando curado, senão o
    original. Regra de honestidade (spec item 4): incerto → mantém
    original — NUNCA inventa empresa.
    """
    if not isinstance(company, str) or not company:
        return company or ""
    return aliases.get(company, company)


def display_job_view(job: dict, aliases: dict[str, str]) -> dict:
    """Cópia RASA do job com os campos de exibição higienizados.

    SANITIZER MOJIBAKE aplicado a title/company/location (spec item 1);
    ALIAS aplicado a company (item 2). O ``job`` original NÃO é mutado
    — o consumidor (``_cards_section``) usa a view para o HTML e o job
    REAL para intel/match (aliases não contaminam o pipeline).

    A cópia é rasa: campos aninhados (``raw``) são compartilhados por
    referência — nada além de title/company/location é tocado.
    """
    if not isinstance(job, dict):
        return job
    view = dict(job)
    for field in ("title", "company", "location"):
        value = view.get(field)
        if isinstance(value, str) and value:
            view[field] = fix_mojibake(value)
    if isinstance(view.get("company"), str) and aliases:
        view["company"] = display_company(view["company"], aliases)
    return view
