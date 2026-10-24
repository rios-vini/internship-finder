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

F57 (18/10) — bare month-year (mês + ano SEM prefixo: ``Internship March
2027``, BDO ``... Advisor Bruxelles (février 2027)``) foi MEDIDO sobre o
eligible real (736 vagas) e REJEITADO: 88 hits novos, 78 legítimos
(88,6% < 90% exigido pela card). O ruído é irrecuperável por regex e sem
relógio/mundo — data de notícia (``On 22 September 2025, CANAL+
confirmed``), registro de empresa (``registered in March 2024``), citação
de lei (``law of 23 July 2016``), marco de processo (``Offer extended to
the successful candidate by December 2026``) e boilerplate stale
(``Start date: December/January 2024``). Decisão: data solta continua
fora — mês-ano sem prefixo segue AMBÍGUO por design (``Bewerbungsfrist
März 2027`` NÃO é início; trava no test_f45 A6). GAP aceito: título com
bare MMY (7/7 legítimos na medição, caso BDO) continua sem janela —
variante "bare MMY só no título" documentada como opção futura no
relatório F57 (exigiria passar o título separado ao parser).

F67 (19/10) — CONTEXTO DE INÍCIO para o imediato. A medição F62 §2 (run
17/10, a olho) splitou os 37 canônicos ``ab sofort`` em 26 janelas
declaradas de verdade (``Beginn: ab sofort``, ``Ab sofort für 6
Monate``, ``STARTING IMMEDIATELY … FOR 6 MONTHS``) e 11
falsos-positivos em prosa (7× slogan Lidl ``steigt sofort in die
Arbeitswelt ein``, 2× rodapé anti-fraude Medtronic ``contact us
immediately``, 1× processo boas ``join us immediately``, 1× lab OLAM
``measuring … immediately after production``). A diferença observável:
os reais vêm com um MARCADOR DE CONTEXTO DE INÍCIO colado ao termo
(``_IMMEDIATE_CONTEXT_RE`` — Beginn/Start/Wann/Zeitraum/zu besetzen/
Suchen/duração ``N Monate``/``als Praktikant``); a prosa, não. Todo
hit imediato agora carrega ``"context"``: True quando um marcador
aparece na janela ``_IMMEDIATE_CONTEXT_WINDOW`` (±60 chars — o real
mais distante dos 37 mede 45; os 11 FPs não têm NENHUM marcador a
±250). Sem contexto o hit CONTINUA no calendário 📆 com o rótulo
``ab sofort`` (contagem preservada — decisão F67: o parser segue
honesto sobre o TEXTO; quem fica mais estrito é o SINAL de imediato)
mas deixa de ser IMEDIATO: o badge da F62 (``ab_sofort_flag``) e a
linha ⚠ do digest (``immediate_context`` do summary) só acendem com
``context=True``. Canônico: entre hits imediatos do MESMO texto, um
COM contexto vence um em prosa (proteção contra vaga futura com
slogan + janela real no mesmo texto — nos runs medidos não existe
vaga com 2 hits imediatos, delta 0).

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

# Non-capturing month pattern for use in patterns with multiple months
# (avoids "redefinition of group name" error)
_MONTH_RE_NC = rf"(?:(?<!\\w)(?:{_MONTH_ALT})(?!\\w))"

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

# F95 — rótulos de início COM DOIS-PONTOS: "Start Date: January 2026"
# (keplercheuvreux verbatim), "Beginning : August 2026" (Mondelez R-160904
# verbatim — o " : " quebra o ``\s+`` do _START_PREFIX e a vaga ficava sem
# janela), "Startdatum: ab 09/01/2027" (BMW). O DOIS-PONTOS é obrigatório —
# sem ele "beginning August 2026" casaria DUAS vezes (aqui e no
# _START_MONTH_RE). Exige mês-NOME (as formas numéricas vivem no
# _START_SLASH_RE/_START_DOT_RE abaixo).
_START_LABEL_RE = re.compile(
    rf"(?:start\s*date|startdatum|beginn(?:ing)?|eintritt(?:stermin)?)\s*:\s*"
    rf"{_DAY_PREFIX}{_MONTH_RE}\s+(?P<yr>\d{{4}})(?!\d)",
    re.IGNORECASE)

# F95 — início numérico com BARRA (spec ITEM 3 "ab MM/YYYY" + forma BMW
# real "Startdatum: ab 09/01/2027"): 2 partes = MM/YYYY; 3 partes =
# DD/MM/YYYY (ordem alemã, MESMA leitura do _START_DOT_RE). Sem prefixo
# NUNCA casa (doutrina F57: data solta é ambígua).
_START_SLASH_RE = re.compile(
    rf"{_START_PREFIX}\s+(?:(?P<d>\d{{1,2}})/)?(?P<m>\d{{1,2}})/"
    rf"(?P<y>\d{{4}}|\d{{2}})(?!\d)",
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

# F67 — marcadores de CONTEXTO DE INÍCIO: o hit imediato só é janela
# declarada quando um destes aparece colado ao termo. Calibrado nos 37
# canônicos do run 17/10 (tábua F62 §2): os 26 reais têm marcador a
# <=45 chars; os 11 FPs em prosa (slogan Lidl, rodapé Medtronic,
# processo boas, lab OLAM) não têm NENHUM a ±250. Word-aware:
# "start" NÃO casa "startet" (verbo do slogan Lidl), mas casa
# "START IMMEDIATELY" e "Start: ab sofort"; "starting" cobre o DHL EN.
_IMMEDIATE_CONTEXT_RE = re.compile(
    r"(?i)\b(?:" 
    r"beginn\w*|beginning|start|starts|starting|einstieg"
    r"|wann|zeitraum|dauer|duration|zu\s+besetzen|besetzung"
    r"|suchen|gesucht"
    r"|monate|monaten|monatig\w*|months|mois"
    r"|als\s+praktikant|als\s+werkstudent"
    r")\b")

# F67 — janela de contexto: ±60 chars do termo (folga de 15 sobre o
# real mais distante medido, 45; FPs limpos até ±250).
_IMMEDIATE_CONTEXT_WINDOW = 60

# F109 — início ambíguo: "ab <mês>" SEM ano (ex.: "Ab August / September",
# "ab Februar", "from January"). Mesma prefixos do _START_PREFIX, mas
# o mês NÃO é seguido por ano de 4 dígitos. Difere de "bare month-year"
# (F57 rejeitado) por EXIGIR prefixo de início — "Ab August" é janela
# declarada; "August 2027" solto no texto é ambíguo (deadline? registro?).
# O padrão também cobre "Ab August / September" (dois meses, sem ano).
_AMBIGUOUS_START_RE = re.compile(
    rf"{_START_PREFIX}\s+{_DAY_PREFIX}{_MONTH_RE}"
    rf"(?:\s*/\s*{_MONTH_RE_NC})*"  # opcional: " / September" etc. (non-capturing)
    rf"(?!\s+\d{{4}})",  # NÃO seguido por ano de 4 dígitos
    re.IGNORECASE)

# Prioridade do canônico (menor = mais específico).
# F109: ambiguous_start tem prioridade MENOR que start datado —
# uma vaga com "ab August" E "ab March 2027" canoniza a datada.
_KIND_RANK = {"semester": 0, "range": 1, "start": 2, "ambiguous_start": 3, "immediate": 4}


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
                          (_START_ISO_RE, "iso"),
                          (_START_LABEL_RE, "label"),   # F95
                          (_START_SLASH_RE, "slash")):  # F95
        for m in pattern.finditer(text):
            if kind == "month":
                y = _year(m.group("yr"))
                mo = _month_of(m, "mon")
            elif kind == "label":
                y = _year(m.group("yr"))
                mo = _month_of(m, "mon")
            elif kind == "slash":
                y = _year(m.group("y"))
                mo = int(m.group("m"))
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
    # F95 — dedupe por mês de início: "Startdatum: ab März 2027" casa no
    # rótulo NOVO e no "ab März 2027" do _START_MONTH_RE — a MESMA janela
    # não pode virar 2 hits (o calendário e o canônico são 1 por vaga).
    # Mantém o PRIMEIRO na ordem de leitura (menor pos), padrão do canônico.
    seen: set[str] = set()
    deduped: list[dict] = []
    for h in sorted(hits, key=lambda h: h["pos"]):
        if h["start"] in seen:
            continue
        seen.add(h["start"])
        deduped.append(h)
    return deduped


def _immediate_has_context(text: str, start: int, end: int) -> bool:
    """F67: há marcador de contexto de início na janela ±60 do termo?

    Pura; janela clampada ao texto (termo no início/fim não lança).
    """
    lo = max(0, start - _IMMEDIATE_CONTEXT_WINDOW)
    hi = min(len(text), end + _IMMEDIATE_CONTEXT_WINDOW)
    return _IMMEDIATE_CONTEXT_RE.search(text, lo, hi) is not None


def _immediate_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    for m in _IMMEDIATE_RE.finditer(text):
        hits.append({
            "kind": "immediate", "semester": None,
            "term": m.group(0).strip(),
            "start": None, "end": None, "year": None,
            "pos": m.start(),
            # F67: contexto de início colado ao termo (True = janela
            # declarada; False = prosa — permanece no calendário 📆,
            # mas NÃO é sinal de início imediato).
            "context": _immediate_has_context(text, m.start(), m.end()),
        })
    return hits


def _ambiguous_start_hits(text: str) -> list[dict]:
    """F109: hits de início ambíguo — 'ab <mês>' SEM ano.

    Não decide TOO_EARLY/TOO_LATE (sem ano não dá para comparar).
    Apenas sinaliza que há uma janela declarada com mês mas sem ano.
    Retorna hits com kind='ambiguous_start', start/end=None, year=None.
    """
    hits: list[dict] = []
    for m in _AMBIGUOUS_START_RE.finditer(text):
        # Evita sobreposição com _START_MONTH_RE (que casa o mesmo prefixo
        # mas EXIGE ano). O _START_MONTH_RE roda ANTES no parse_seasonality
        # e tem prioridade maior (kind='start' rank 2 vs 3).
        # Mesmo assim, garantimos que não duplicamos: se o termo casado
        # já aparece num hit 'start' (com ano), pulamos.
        hits.append({
            "kind": "ambiguous_start", "semester": None,
            "term": m.group(0).strip(),
            "start": None, "end": None, "year": None,
            "pos": m.start(),
        })
    return hits


# ---------------------------------------------------------------------------
# API pública (pura)
# ---------------------------------------------------------------------------


def parse_seasonality(text: str) -> list[dict]:
    """Todos os hits de sazonalidade do texto, ordenados por (prioridade,
    posição). Determinístico; texto vazio/None -> [].

    Cada hit: ``{"kind", "semester", "term", "start", "end", "year",
    "pos", "context"}`` — ``start``/``end`` em ``YYYY-MM`` (None quando
    desconhecido), ``term`` é o trecho literal casado, ``pos`` a
    posição no texto e ``context`` (F67, só no kind=immediate) diz se
    há marcador de contexto de início colado ao termo (True = janela
    declarada; False = prosa). F109 adiciona kind='ambiguous_start'
    para 'ab <mês>' sem ano (flag própria, NÃO conflito).
    """
    if not text:
        return []
    hits: list[dict] = []
    hits.extend(_sem_hits(text))
    hits.extend(_range_hits(text))
    hits.extend(_start_hits(text))
    hits.extend(_ambiguous_start_hits(text))  # F109
    hits.extend(_immediate_hits(text))
    hits.sort(key=lambda h: (_KIND_RANK.get(h["kind"], 9), h["pos"]))
    return hits


def canonical_seasonality(text: str) -> dict | None:
    """UM hit por texto (prioridade: semester > range > start > imediato;
    empate: primeiro na ordem de leitura). None quando nada detectado.

    F67 — desempate DENTRO do imediato: se o canônico seria um hit
    imediato SEM contexto (prosa) mas o texto também tem um hit
    imediato COM contexto (janela declarada), o COM contexto vence.
    Proteção contra vaga futura com slogan e janela real no mesmo
    texto; nos runs medidos (17–19/10) nenhuma vaga tem 2 hits
    imediatos — delta zero. Outros kinds: intocados.
    """
    hits = parse_seasonality(text)
    if not hits:
        return None
    if hits[0].get("kind") == "immediate" and not hits[0].get("context"):
        with_ctx = next(
            (h for h in hits
             if h.get("kind") == "immediate" and h.get("context")), None)
        if with_ctx is not None:
            return with_ctx
    return hits[0]


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
    if kind == "ambiguous_start":  # F109
        # Extrai o(s) mês(es) do termo para o rótulo (ex.: "ago/set (sem ano)")
        return _label_ambiguous_start(hit.get("term", ""))
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


def immediate_context_count(texts: Iterable[str]) -> int:
    """F67: nº de textos cujo canônico é imediato COM contexto de início
    (janela declarada de verdade — "Ab sofort für 6 Monate", "Beginn: ab
    sofort"). FONTE ÚNICA da contagem apertada: a linha ⚠ do digest
    (``ranking_digest``) e o A/B da F67 consomem este número; o badge da
    página consome o MESMO sinal por vaga (``hit["context"]``). O
    calendário 📆 NÃO usa isto — ele preserva TODOS os hits imediatos
    no rótulo ``ab sofort`` (decisão F67: contagem textual intacta).
    Pura; determinística; nunca lança (texto inválido -> sem hit)."""
    n = 0
    for t in texts:
        hit = canonical_seasonality(t)
        if hit and hit.get("kind") == "immediate" and hit.get("context"):
            n += 1
    return n


def job_window_text(job: dict) -> str:
    """F62: texto canônico de janela de início de UMA vaga — FONTE ÚNICA
    da composição ``título — descrição``. O calendário da F45
    (``funnel_report.seasonality_summary``) e o badge de conflito da F62
    (``minimal_page.ab_sofort_flag``) varrem o MESMO texto; mudar a
    composição aqui muda os DOIS juntos (nunca uma segunda tabela).
    Pura: só lê o dict, nunca I/O."""
    return (f"{(job.get('title') or '')} — "
            f"{(job.get('description') or '')}")


# ---------------------------------------------------------------------------
# F95 — start_date + start_conflict (ITENS ITEM 3; doutrina F62: FLAG
# obrigatória, NÃO exclusão — display-only, o dono decide).
#
# Meta do dono: PRIMEIRA ENTRADA jan/2027 (visto §16e). Janela boa de
# início: jan/2027 .. set/2027 (spec ITEM 3: "início > ~set/2027" =
# TOO_LATE; setembro INTEIRO ainda cabe — boundary medida: início
# set/2027 NÃO flaga, out/2027 flaga).
#
#   TOO_EARLY  — janela canônica datada ANTES de jan/2027 (Mondelez
#                R-160904 "Beginning : August 2026" = ago/2026; kepler-
#                cheuvreux "Start Date: January 2026" = jan/2026 stale).
#   IMMEDIATE  — canônico imediato COM contexto (F62/F67, Lidl SAP BI
#                "Ab sofort für 6 Monate") OU fórmula ASAP sem data
#                ("zum nächstmöglichen Zeitpunkt" — 1254 hits no corpus
#                bruto, 3 no eligible 21/10; "Start date: ASAP" /
#                "as soon as possible" pós-rótulo — Gsk/Adaptyv).
#   TOO_LATE   — janela canônica datada DEPOIS de set/2027.
#
# A janela datada canônica é TERMINAL: "ab sofort oder für das
# Sommersemester 2027" (Liebherr) canoniza o semestre e fica POSITIVA —
# a ASAP-só-fórmula não vence a janela específica (mesma doutrina F62:
# janelas futuras continuam positivas). Imediato em prosa (sem contexto,
# slogan/rodapé) NÃO acende sozinho — só se houver fórmula ASAP declarada
# no texto (F67: o sinal é mais estrito que o texto).
# ---------------------------------------------------------------------------

START_WINDOW_MIN = (2027, 1)   # disponibilidade do dono (jan/2027)
START_WINDOW_MAX = (2027, 9)   # ~set/2027 (spec ITEM 3 — "início > ~set/2027")
START_CONFLICTS = ("TOO_EARLY", "IMMEDIATE", "TOO_LATE")

# Fórmulas ASAP sem data concreta. DE canônica do corpus ("Eintrittstermin:
# Zum nächstmöglichen Zeitpunkt" HORNBACH verbatim, "Beginn zum
# nächstmöglichen Zeitpunkt" GFO verbatim); EN só PÓS-RÓTULO de início
# ("Start date: ASAP" Adaptyv, "Start date: As soon as possible" Gsk —
# "as soon as possible" solto em prosa ("apply as soon as possible") NUNCA
# casa).
_ASAP_FORMS_RE = re.compile(
    r"zum\s+n(?:ä|ae)chstm(?:ö|oe)glichen\s+zeitpunkt"
    r"|(?:start\s*date|startdatum|beginn(?:ing)?)\s*:\s*"
    r"(?:asap|as\s+soon\s+as\s+possible)\b",
    re.IGNORECASE,
)


def _ym(value: str | None) -> tuple[int, int] | None:
    """"YYYY-MM" -> (y, m); None inválido."""
    if not value or "-" not in value:
        return None
    try:
        y, m = (int(x) for x in value.split("-"))
    except ValueError:
        return None
    if not 1 <= m <= 12:
        return None
    return y, m


def start_conflict_of(job: dict) -> dict | None:
    """F95 — conflito da janela de início com a meta jan/2027 do dono.

    Devolve ``{"conflict", "start", "term", "label"}`` ou None (sem
    conflito / sem janela). ``conflict`` ∈ START_CONFLICTS; ``start`` é
    "YYYY-MM" quando datado (None no imediato/ASAP); ``term`` é o trecho
    verbatim casado; ``label`` é o rótulo de exibição pt-BR ("ago/2026",
    "ab sofort", "zum nächstmöglichen Zeitpunkt"). Consome o MESMO
    canônico da F45 (``canonical_seasonality`` sobre
    ``job_window_text`` — o calendário 📆 e o badge F62 varrem o mesmo
    texto; nenhum parser novo). Pura, best-effort, nunca lança.
    """
    try:
        text = job_window_text(job)
        hit = canonical_seasonality(text)
        if hit is not None:
            kind = hit.get("kind")
            if kind == "immediate" and hit.get("context"):
                return {"conflict": "IMMEDIATE", "start": None,
                        "term": hit.get("term") or "", "label": "ab sofort"}
            start = hit.get("start")
            ym = _ym(start)
            if ym is not None:
                # Janela datada canônica é TERMINAL (Liebherr: semestre
                # vence o "ab sofort" em prosa e fica positivo).
                if ym < START_WINDOW_MIN:
                    return {"conflict": "TOO_EARLY", "start": start,
                            "term": hit.get("term") or "",
                            "label": _fmt_label_pt(ym)}
                if ym > START_WINDOW_MAX:
                    return {"conflict": "TOO_LATE", "start": start,
                            "term": hit.get("term") or "",
                            "label": _fmt_label_pt(ym)}
                return None
            # canônico sem data (semestre sem ano) — cai para ASAP
        asap = _ASAP_FORMS_RE.search(text)
        if asap:
            return {"conflict": "IMMEDIATE", "start": None,
                    "term": asap.group(0),
                    "label": "zum nächstmöglichen Zeitpunkt"}
    except Exception:  # noqa: BLE001 — best-effort, nunca erro
        return None
    return None


def _fmt_label_pt(ym: tuple[int, int]) -> str:
    """"(2026, 8)" -> "ago/2026" (mesma abreviação do calendário 📆)."""
    y, m = ym
    return f"{_MONTH_ABREV[m]}/{y:04d}"


# F109 — label para início ambíguo (ex.: "Ab August / September" -> "ago/set (sem ano)")
def _label_ambiguous_start(term: str) -> str:
    """Extrai meses do termo 'ab <mês> [/ <mês>]*' -> 'ago/set (sem ano)'."""
    # Procura nomes de meses no termo (case-insensitive, pt/DE/EN/FR)
    months_found: list[int] = []
    for m_name, m_num in _MONTH_NUM.items():
        # Word boundary para não casar "märz" dentro de "märzchen" etc.
        if re.search(rf"(?<!\w){re.escape(m_name)}(?!\w)", term, re.IGNORECASE):
            months_found.append(m_num)
    # Remove duplicatas mantendo ordem
    seen: set[int] = set()
    unique_months = [m for m in months_found if not (m in seen or seen.add(m))]
    if not unique_months:
        return "mês ambíguo (sem ano)"
    abrevs = [_MONTH_ABREV[m] for m in unique_months]
    return "/".join(abrevs) + " (sem ano)"


# F109 — flag start_date_ambiguous: True se o texto tem 'ab <mês>' SEM ano
# (kind='ambiguous_start' em parse_seasonality). NÃO decide conflito
# (TOO_EARLY/TOO_LATE) — é sinal informativo próprio.
def start_date_ambiguous_of(job: dict) -> bool:
    """F109: verifica se a vaga tem janela de início ambígua (mês sem ano).

    Best-effort, pura, nunca lança. Retorna True se houver pelo menos
    um hit 'ambiguous_start' no texto da vaga (título + descrição).
    """
    try:
        text = job_window_text(job)
        hits = parse_seasonality(text)
        return any(h.get("kind") == "ambiguous_start" for h in hits)
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":  # uso manual: echo de hits de um texto
    import sys as _sys
    for hit in parse_seasonality(" ".join(_sys.argv[1:])):
        print(hit)
