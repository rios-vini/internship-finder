"""F45 — Parser PURO de sazonalidade de vagas (semestres alemães + janelas de datas EN/DE/FR).

Função pura, SEM I/O e SEM relógio: ``parse_seasonality(texto)`` devolve TODOS
os hits detectados; ``canonical_seasonality(texto)`` escolhe UM por texto
(prioridade documentada); ``seasonality_calendar(textos)`` agrega por rótulo.
Mesma entrada = mesma saída, byte a byte (testável isoladamente; o digest e o
relatório ``funnel_report.py`` são os consumidores).

O QUE É DETECTADO (escopo F45 — medido sobre o eligible real de produção):

- Semestres alemães: ``SoSe``/``Sommersemester`` (abr–set do ano) e
  ``WiSe``/``Wintersemester``/``WS`` (out do ano – mar do ano seguinte).
  ABREVIAÇÕES (SoSe/WiSe/SS/WS) EXIGEM ano — ``SoSe 2027``, ``SoSe 27``,
  ``SS 2027`` (caso real TRUMPF), ``WS 2026/27``; sem ano, só o nome COMPLETO
  (``Wintersemester``) conta (abreviação sem ano não define janela e "wise" é
  palavra inglesa/empresa — falso positivo documentado e evitado).
  Ano de 2 dígitos: ``27`` -> 2027 (século fixo — vagas são 20xx).
- Inícios ("start"): prefixos ``ab / ab dem / starting / beginning / from /
  as of / à partir de / a partir de / dès le / dès`` + ``mês ano`` (nomes DE/
  EN/FR, com ou sem dia: ``ab 15. März 2027``, ``starting 5th June 2027``,
  ``à partir de mars 2027``) ou data numérica (``ab 01.03.2027``,
  ``starting 2027-03-01``). Data NUMÉRICA só com prefixo — data solta no
  texto é ambígua (deadline? coleta?).
- Duração pós-início: ``für/for/pour N Monate/months/mois`` e fim ``zum
  <data>`` nos ~80 chars seguintes estendem o hit com o fim da janela
  (caso real Daimler Buses: ``ab März 2027 für 6 Monate`` -> mar–ago/2027).
- Janelas ("range"): ``März 2027 bis Juni 2027``, ``March 2027 to June 2027``,
  ``März bis Juni 2027`` (ano único no fim, padrão DE), ``de janvier à juin
  2027`` (padrão FR), ``January-June 2027`` (traço).
- Imediato: ``ab sofort / sofort / immediately`` — sinal sem datas.

PRIORIDADE DO CANÔNICO (1 hit por vaga; decisões F45):

    semester > range > start > imediato

A vaga que menciona ``SoSe 2027`` E ``ab März 2027`` é contada UMA vez, no
semestre (o termo do semestre é mais específico que a data). Empate dentro da
mesma prioridade: primeiro hit na ordem de leitura do texto.

RÓTULOS (chave do calendário; abreviações de mês em pt-BR):

    SoSe 2027 (abr–set/2027) · WiSe 2026/27 (out/26–mar/27) ·
    mar–jun/2027 · dez/2026–jun/2027 · mar/2027 · ab sofort

NÃO é detector de deadline: ``deadline``/``bewerbung bis`` não entram no
escopo (sazonalidade = QUANDO A VAGA COMEÇA; deadline é outro eixo).
"""

from __future__ import annotations

import re
from typing import Iterable

# ---------------------------------------------------------------------------
# Meses — variantes DE/EN/FR (case-insensitive; acentos explícitos no padrão).
# ---------------------------------------------------------------------------

_MONTH_NUM: dict[str, int] = {
    # DE
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
    # EN
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "october": 10, "december": 12,
    # FR
    "janvier": 1, "février": 2, "mars": 3, "juin": 6, "juillet": 7,
    "août": 8, "octobre": 10, "décembre": 12,
}

# Alternation por comprimento desc — "january" antes de "januar" evita
# match parcial (os lookarounds (?<!\w)/(?!\w) já bloqueiam palavra parcial;
# a ordem só decide qual variante ganha quando mais de uma casa).
_MONTH_ALT = "|".join(sorted(_MONTH_NUM, key=len, reverse=True))


def _month_group(name: str) -> str:
    """Fragmento de mês com grupo nomeado PRÓPRIO (padrões com dois meses
    precisam de nomes distintos — ``re`` proíbe redefinição de grupo)."""
    return rf"(?P<{name}>(?<!\w)(?:{_MONTH_ALT})(?!\w))"


_MONTH_RE = _month_group("mon")

# Abreviações pt-BR dos rótulos do calendário.
_MONTH_ABREV = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
                7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}

# ---------------------------------------------------------------------------
# Semestres
# ---------------------------------------------------------------------------

# Nome completo: ano OPCIONAL (janela sem ano é "sem janela", mas é sinal).
_SEM_FULL_RE = re.compile(
    r"(?<!\w)(?P<full>sommersemester|summer\s+semester|wintersemester"
    r"|winter\s+semester)\s*(?P<y1>(?:20)?\d{2})?"
    r"(?:\s*/\s*(?P<y2>\d{2}|\d{4}))?(?!\w)",
    re.IGNORECASE)

# Abreviação: ano OBRIGATÓRIO (razões no docstring do módulo).
_SEM_ABBR_RE = re.compile(
    r"(?<!\w)(?P<abbr>sose|wise|ss|ws)\s*(?P<y1>(?:20)?\d{2})"
    r"(?:\s*/\s*(?P<y2>\d{2}|\d{4}))?(?!\w)",
    re.IGNORECASE)

# ---------------------------------------------------------------------------
# Inícios ("start") e janelas ("range")
# ---------------------------------------------------------------------------

# Prefixos de início DE/EN/FR. "from"/"as of" só casam com mês+ano depois —
# não são genéricos (sem FP em "from our office in ...").
_START_PREFIX = (
    r"(?:ab\s+dem|ab|starting|beginning|start(?:ing)?\s+at|as\s+of|from"
    r"|à\s+partir\s+du|à\s+partir\s+de|a\s+partir\s+de|dès\s+le|dès|dès\s+la)"
)
_DAY_PREFIX = r"(?:(?P<day>\d{1,2})(?:\.|er|st|nd|rd|th)?\s+)?"

# ab März 2027 · starting June 2027 · à partir de mars 2027 · ab 15. März 2027
_START_MONTH_RE = re.compile(
    rf"{_START_PREFIX}\s+{_DAY_PREFIX}{_MONTH_RE}\s+(?P<yr>\d{{4}})(?!\d)",
    re.IGNORECASE)

# ab 01.03.2027 · ab 1.3.27 (data alemã, pontos)
_START_DOT_RE = re.compile(
    rf"{_START_PREFIX}\s+(?P<d>\d{{1,2}})\.(?P<m>\d{{1,2}})\."
    rf"(?P<y>\d{{4}}|\d{{2}})(?!\d)",
    re.IGNORECASE)

# starting 2027-03-01 (ISO com prefixo)
_START_ISO_RE = re.compile(
    rf"{_START_PREFIX}\s+(?P<y>\d{{4}})-(?P<m>\d{{1,2}})-(?P<d>\d{{1,2}})(?!\d)",
    re.IGNORECASE)

# Janela mês-ano A (sep) mês-ano B: März 2027 bis Juni 2027 · March 2027
# to June 2027 · de janvier 2027 à juin 2027 · janvier 2027 - juin 2027.
# O ano final rejeita sufixo alfabético ((?![a-zA-Z\d]) — "June 30th" não
# pode virar ano 30; o espaço ao redor do separador é OPCIONAL
# ("January-June 2027") e o 2º lado aceita dia pós-mês ("June 30th 2028").
_RANGE_SEP = r"(?:(?:bis|to|until|au|jusqu'à|à)|[–—-])"
# 2º lado de uma janela com anos explícitos: mês + dia opcional (com ou sem
# vírgula: "June 30th 2028"/"June 30, 2028") + ano SEMPRE de 4 dígitos —
# ano de 2 dígitos no fim de range é ambíguo com dia ("June 30" NUNCA vira
# ano 30); 2 dígitos segue válido nos semestres ("SoSe 27"), onde é inequívoco.
_RANGE_TAIL = (rf"{_month_group('mon_b')}"
               rf"(?:\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*,\s*|\s+))?"
               rf"\s*(?P<y2>\d{{4}})(?![a-zA-Z\d])")
_RANGE_YMY_RE = re.compile(
    rf"{_month_group('mon_a')}\s+(?P<y1>\d{{4}})\s*{_RANGE_SEP}\s*"
    + _RANGE_TAIL,
    re.IGNORECASE)

# Janela mês A (sep) mês B ANO (ano único no fim): März bis Juni 2027 ·
# de janvier à juin 2027 · March to June 2027 · January-June 2027
_RANGE_MMY_RE = re.compile(
    rf"(?:de\s+)?{_month_group('mon_a')}\s*{_RANGE_SEP}\s*"
    rf"{_month_group('mon_b')}\s+(?P<yr>\d{{4}})(?![a-zA-Z\d])",
    re.IGNORECASE)

# Janela EN com dia antes do mês (e dia pós-mês no 2º lado):
# "1 July 2027 – June 30th 2028" (caso real Bosch Breda).
_RANGE_DMY_RE = re.compile(
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{_month_group('mon_a')}\s+(?P<y1>\d{{4}})"
    rf"\s*{_RANGE_SEP}\s*"
    + _RANGE_TAIL,
    re.IGNORECASE)

# Duração/fim nos ~80 chars após um início: für 6 Monate · for 6 months ·
# pour 6 mois · zum 30.06.2027 · zum Juni 2027
_DUR_RE = re.compile(
    r"(?P<kw>(?:für|for|pour))\s+(?P<n>\d{1,2})\s+"
    r"(?:monate|monaten|months|mois)(?!\w)",
    re.IGNORECASE)
_END_ZUM_RE = re.compile(
    rf"\bzum\s+(?:(?P<d>\d{{1,2}})\.(?P<m>\d{{1,2}})\."
    rf"(?P<y>\d{{4}}|\d{{2}})(?!\d)|{_MONTH_RE}\s+(?P<yr>\d{{4}})(?!\d))",
    re.IGNORECASE)

# Imediato: ab sofort · sofort · immediately (sinal, sem datas)
_IMMEDIATE_RE = re.compile(
    r"(?<!\w)(?:ab\s+sofort|sofort|immediately)(?!\w)",
    re.IGNORECASE)

# Prioridade do canônico (menor = mais específico).
_KIND_RANK = {"semester": 0, "range": 1, "start": 2, "immediate": 3}


# ---------------------------------------------------------------------------
# Auxiliares puros
# ---------------------------------------------------------------------------


def _year(tok: str | None) -> int | None:
    """Normaliza ano 'YYYY'/'YY' -> int (século 20xx fixo; vagas são 20xx)."""
    if not tok:
        return None
    if len(tok) == 4 and tok.isdigit():
        return int(tok)
    if len(tok) == 2 and tok.isdigit():
        return 2000 + int(tok)
    return None


def _month_of(match: re.Match, group: str = "mon") -> int | None:
    """Número do mês capturado (variante -> número)."""
    tok = match.group(group)
    if not tok:
        return None
    return _MONTH_NUM.get(tok.strip().lower())


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Aritmética de meses pura (delta positivo; clamp no ciclo real)."""
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, (idx % 12) + 1


def _fmt_month(year: int | None, month: int | None) -> str | None:
    if year is None or month is None:
        return None
    return f"{year:04d}-{month:02d}"


# ---------------------------------------------------------------------------
# Detectores (cada um devolve hits com kind/term/start/end)
# ---------------------------------------------------------------------------


def _sem_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    for pattern in (_SEM_FULL_RE, _SEM_ABBR_RE):
        for m in pattern.finditer(text):
            gd = m.groupdict()
            raw = (gd.get("full") or gd.get("abbr") or "").strip().lower()
            is_summer = raw.startswith(("sommer", "summer", "sose", "ss"))
            sem = "sose" if is_summer else "wise"
            y1 = _year(m.group("y1"))
            if y1 is None:
                # Nome completo sem ano: sinal sem janela (abreviação sem
                # ano não casa — padrão exige ano).
                hits.append({
                    "kind": "semester", "semester": sem,
                    "term": m.group(0).strip(),
                    "start": None, "end": None, "year": None,
                    "pos": m.start(),
                })
                continue
            if is_summer:
                start = _fmt_month(y1, 4)
                end = _fmt_month(y1, 9)
            else:
                # Wintersemester Y termina em março de Y+1 (slash é
                # decorativo — a janela canônica não depende de y2).
                start = _fmt_month(y1, 10)
                end = _fmt_month(y1 + 1, 3)
            hits.append({
                "kind": "semester", "semester": sem,
                "term": m.group(0).strip(),
                "start": start, "end": end, "year": y1,
                "pos": m.start(),
            })
    return hits


def _range_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    # YMY ("März 2027 bis Juni 2027") e DMY ("1 July 2027 – June 30th 2028")
    # compartilham a leitura de grupos (mês A/ano 1/mês B/ano 2).
    for pattern in (_RANGE_YMY_RE, _RANGE_DMY_RE):
        for m in pattern.finditer(text):
            m1 = _MONTH_NUM.get((m.group("mon_a") or "").strip().lower())
            m2 = _MONTH_NUM.get((m.group("mon_b") or "").strip().lower())
            y1 = _year(m.group("y1"))
            y2 = _year(m.group("y2"))
            if m1 is None or m2 is None or y1 is None or y2 is None:
                continue
            hits.append({
                "kind": "range", "semester": None,
                "term": m.group(0).strip(),
                "start": _fmt_month(y1, m1), "end": _fmt_month(y2, m2),
                "year": y1, "pos": m.start(),
            })
    for m in _RANGE_MMY_RE.finditer(text):
        m1 = _MONTH_NUM.get((m.group("mon_a") or "").strip().lower())
        m2 = _MONTH_NUM.get((m.group("mon_b") or "").strip().lower())
        y1 = _year(m.group("yr"))
        if m1 is None or m2 is None or y1 is None:
            continue
        # ano único no fim: janela que atravessa dez->jan usa Y+1
        y2 = y1 + 1 if m2 < m1 else y1
        hits.append({
            "kind": "range", "semester": None,
            "term": m.group(0).strip(),
            "start": _fmt_month(y1, m1), "end": _fmt_month(y2, m2),
            "year": y1, "pos": m.start(),
        })
    return hits


def _extend_with_tail(text: str, hit: dict) -> dict:
    """Estende um início com duração (für/for/pour N) ou fim (zum <data>)
    nos ~80 chars seguintes. Pura; nunca lança; muta só a cópia devolvida."""
    tail = text[hit["pos"]:hit["pos"] + len(hit["term"]) + 80]
    dm = _DUR_RE.search(tail)
    if dm and hit.get("start"):
        y, m = (int(x) for x in hit["start"].split("-"))
        ey, em = _add_months(y, m, int(dm.group("n")))
        # início mar + 6 meses = fim ago (o mês final é exclusivo −1)
        fy, fm = _add_months(ey, em, -1)
        hit["end"] = _fmt_month(fy, fm)
        hit["term"] = (hit["term"] + " " + dm.group(0).strip()).strip()
        return hit
    zm = _END_ZUM_RE.search(tail)
    if zm and hit.get("start"):
        if zm.group("m") and zm.group("y"):
            ey = _year(zm.group("y"))
            hit["end"] = _fmt_month(ey, int(zm.group("m")))
        elif zm.group("yr"):
            em = _month_of(zm, "mon")
            hit["end"] = _fmt_month(_year(zm.group("yr")), em)
        if hit.get("end"):
            hit["term"] = (hit["term"] + " " + zm.group(0).strip()).strip()
    return hit


def _start_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    for pattern, kind in ((_START_MONTH_RE, "month"),
                          (_START_DOT_RE, "dot"),
                          (_START_ISO_RE, "iso")):
        for m in pattern.finditer(text):
            if kind == "month":
                y = _year(m.group("yr"))
                mo = _month_of(m, "mon")
            elif kind == "dot":
                y = _year(m.group("y"))
                mo = int(m.group("m"))
            else:
                y = _year(m.group("y"))
                mo = int(m.group("m"))
            if y is None or mo is None or not 1 <= mo <= 12:
                continue
            hits.append(_extend_with_tail(text, {
                "kind": "start", "semester": None,
                "term": m.group(0).strip(),
                "start": _fmt_month(y, mo), "end": None,
                "year": y, "pos": m.start(),
            }))
    return hits


def _immediate_hits(text: str) -> list[dict]:
    return [{
        "kind": "immediate", "semester": None, "term": m.group(0).strip(),
        "start": None, "end": None, "year": None, "pos": m.start(),
    } for m in _IMMEDIATE_RE.finditer(text)]


# ---------------------------------------------------------------------------
# API pública (pura)
# ---------------------------------------------------------------------------


def parse_seasonality(text: str) -> list[dict]:
    """Todos os hits de sazonalidade do texto, ordenados por (prioridade,
    posição). Determinístico; texto vazio/None -> [].

    Cada hit: ``{"kind", "semester", "term", "start", "end", "year", "pos"}``
    — ``start``/``end`` em ``YYYY-MM`` (None quando desconhecido), ``term``
    é o trecho literal casado, ``pos`` a posição no texto.
    """
    if not text:
        return []
    hits: list[dict] = []
    hits.extend(_sem_hits(text))
    hits.extend(_range_hits(text))
    hits.extend(_start_hits(text))
    hits.extend(_immediate_hits(text))
    hits.sort(key=lambda h: (_KIND_RANK.get(h["kind"], 9), h["pos"]))
    return hits


def canonical_seasonality(text: str) -> dict | None:
    """UM hit por texto (prioridade: semester > range > start > imediato;
    empate: primeiro na ordem de leitura). None quando nada detectado."""
    hits = parse_seasonality(text)
    return hits[0] if hits else None


def seasonality_label(hit: dict | None) -> str | None:
    """Rótulo de exibição/calendário (pt-BR, meses abreviados)."""
    if not hit:
        return None
    kind = hit.get("kind")
    if kind == "semester":
        sem = "SoSe" if hit.get("semester") == "sose" else "WiSe"
        if not hit.get("year"):
            return f"{sem} (sem ano)"
        if sem == "SoSe":
            return f"SoSe {hit['year']:04d} (abr–set/{hit['year']:04d})"
        return f"WiSe {hit['year']:04d}/{(hit['year'] + 1) % 100:02d} (out/{hit['year'] % 100:02d}–mar/{(hit['year'] + 1) % 100:02d})"
    if kind == "range" and hit.get("start") and hit.get("end"):
        sy, sm = (int(x) for x in hit["start"].split("-"))
        ey, em = (int(x) for x in hit["end"].split("-"))
        if sy == ey:
            return f"{_MONTH_ABREV[sm]}–{_MONTH_ABREV[em]}/{sy:04d}"
        return (f"{_MONTH_ABREV[sm]}/{sy:04d}–"
                f"{_MONTH_ABREV[em]}/{ey:04d}")
    if kind == "start" and hit.get("start"):
        y, m = (int(x) for x in hit["start"].split("-"))
        return f"{_MONTH_ABREV[m]}/{y:04d}"
    if kind == "immediate":
        return "ab sofort"
    return None


def seasonality_calendar(texts: Iterable[str]) -> list[tuple[str, int]]:
    """Agrega o hit canônico de cada texto em (rótulo -> contagem),
    ordenado por contagem desc e rótulo asc (determinístico)."""
    counts: dict[str, int] = {}
    for t in texts:
        label = seasonality_label(canonical_seasonality(t))
        if label:
            counts[label] = counts.get(label, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


if __name__ == "__main__":  # uso manual: echo de hits de um texto
    import sys as _sys
    for hit in parse_seasonality(" ".join(_sys.argv[1:])):
        print(hit)
