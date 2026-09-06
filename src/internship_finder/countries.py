"""Dominio de pais/localizacao: codigos ISO, nomes, inferencia e filtros.

Extraido de ``filters.py`` (P2 #12) para centralizar a logica de pais em um
modulo proprio. ``filters.py`` re-exporta estes simbolos para compatibilidade
total com quem importa de la (ex.: ``ranking.infer_country_iso``,
``adapters.ats.is_student_role``). Nenhuma logica nova — comportamento
preservado.

Funcoes puras (sem dependencia de CLI/modelos). ``country_iso`` e a fonte
primaria; fallback para ``country`` e, por fim, para codigo ISO de 2 letras
presente na ``location`` (ex.: SAP usa "Walldorf, DE, 69190" sem campo de
pais).

Pais configuravel (``parse_country_spec``): ISO alpha-2, "europe", "remote"
ou "all" (sem filtro).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Pais / localizacao
# ---------------------------------------------------------------------------

# ISO 3166-1 alpha-2 (codigos validos para o fallback por ``location``).
# Minusculas: todas as comparacoes usam ``.lower()``.
COUNTRY_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
    BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR
    CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF
    PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI
    SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
    TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.lower().split()
)

# "Europa" para o dono: UE/EEE + CH + UK + Balcas (paises onde estagio/estudo
# em alemao e viavel ou comum no contexto). RU/BY ficam de fora pelo mesmo
# criterio (viabilidade de estagio/estudo em alemao no contexto do dono;
# decidido e documentado em P3 #20/ACH-19 — medido: 0 vagas reais com ISO
# 'by'/'ru' em data/jobs.json, entao a exclusao nao altera resultado real).
# Minusculas, como COUNTRY_CODES.
EUROPE_COUNTRIES = frozenset(
    """
    AD AL AT BA BE BG CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT
    LU LV MC MD ME MK MT NL NO PL PT RO RS SE SI SK SM UA UK VA
    """.lower().split()
)

# Nomes de pais (ingles, minusculas) -> ISO 3166-1 alpha-2. Usado pelo fallback
# de ``infer_country_iso`` quando a ``location`` termina com o NOME do pais
# (ex.: API Phenom compoe "Cidade, Estado, Germany"). A chave e o dado real da
# vaga — a inferencia e segura (o nome do pais esta explicito na localizacao),
# nao inventada. Inclui os nomes observados nas coletas (Phenom/DHL, eightfold,
# greenhouse, etc.) + nomes padrao ISO 3166-1 + variantes comuns.
COUNTRY_NAMES: dict[str, str] = {
    "afghanistan": "af", "albania": "al", "algeria": "dz", "andorra": "ad",
    "angola": "ao", "anguilla": "ai", "antigua and barbuda": "ag",
    "argentina": "ar", "armenia": "am", "aruba": "aw", "australia": "au",
    "austria": "at", "azerbaijan": "az", "bahamas": "bs", "bahrain": "bh",
    "bangladesh": "bd", "barbados": "bb", "belarus": "by", "belgium": "be",
    "belize": "bz", "benin": "bj", "bermuda": "bm", "bhutan": "bt",
    "bolivia": "bo", "bosnia and herzegovina": "ba", "botswana": "bw",
    "brazil": "br", "brunei": "bn", "bulgaria": "bg", "burkina faso": "bf",
    "burundi": "bi", "cabo verde": "cv", "cape verde": "cv", "cambodia": "kh",
    "cameroon": "cm", "canada": "ca", "cayman islands": "ky",
    "central african republic": "cf", "chad": "td", "chile": "cl",
    "china": "cn", "colombia": "co", "comoros": "km", "congo": "cg",
    "costa rica": "cr", "croatia": "hr", "cuba": "cu", "curacao": "cw",
    "cyprus": "cy", "czech republic": "cz", "czechia": "cz",
    "democratic republic of the congo": "cd", "denmark": "dk", "djibouti": "dj",
    "dominica": "dm", "dominican republic": "do", "ecuador": "ec", "egypt": "eg",
    "el salvador": "sv", "equatorial guinea": "gq", "eritrea": "er",
    "estonia": "ee", "eswatini": "sz", "ethiopia": "et",
    "falkland islands": "fk", "faroe islands": "fo", "fiji": "fj",
    "finland": "fi", "france": "fr", "french guiana": "gf",
    "french polynesia": "pf", "gabon": "ga", "gambia": "gm", "georgia": "ge",
    "germany": "de", "deutschland": "de", "ghana": "gh", "gibraltar": "gi",
    "great britain": "gb", "greece": "gr", "greenland": "gl",
    "grenada": "gd", "guadeloupe": "gp", "guam": "gu", "guatemala": "gt",
    "guinea": "gn", "guinea-bissau": "gw", "guyana": "gy", "haiti": "ht",
    "honduras": "hn", "hong kong": "hk", "hungary": "hu", "iceland": "is",
    "india": "in", "indonesia": "id", "iran": "ir", "iraq": "iq",
    "ireland": "ie", "israel": "il", "italy": "it", "jamaica": "jm",
    "japan": "jp", "jordan": "jo", "kazakhstan": "kz", "kenya": "ke",
    "kiribati": "ki", "kuwait": "kw", "kyrgyzstan": "kg", "laos": "la",
    "latvia": "lv", "lebanon": "lb", "lesotho": "ls", "liberia": "lr",
    "libya": "ly", "libyan arab. jamahir": "ly", "libyan arab jamahiriya": "ly",
    "liechtenstein": "li", "lithuania": "lt", "luxembourg": "lu",
    "madagascar": "mg", "malawi": "mw", "malaysia": "my", "maldives": "mv",
    "mali": "ml", "malta": "mt", "martinique": "mq", "mauritania": "mr",
    "mauritius": "mu", "mayotte": "yt", "mexico": "mx", "micronesia": "fm",
    "moldova": "md", "monaco": "mc", "mongolia": "mn", "montenegro": "me",
    "montserrat": "ms", "morocco": "ma", "mozambique": "mz", "myanmar": "mm",
    "namibia": "na", "nauru": "nr", "nepal": "np", "netherlands": "nl",
    "new caledonia": "nc", "new zealand": "nz", "nicaragua": "ni", "niger": "ne",
    "nigeria": "ng", "north korea": "kp", "north macedonia": "mk",
    "norway": "no", "oman": "om", "pakistan": "pk", "palau": "pw",
    "palestine": "ps", "panama": "pa", "papua new guinea": "pg",
    "paraguay": "py", "peru": "pe", "philippines": "ph", "poland": "pl",
    "portugal": "pt", "puerto rico": "pr", "qatar": "qa", "reunion": "re",
    "romania": "ro", "russia": "ru", "russian federation": "ru",
    "rwanda": "rw", "samoa": "ws", "san marino": "sm",
    "sao tome and principe": "st", "saudi arabia": "sa", "senegal": "sn",
    "serbia": "rs", "seychelles": "sc", "sierra leone": "sl",
    "singapore": "sg", "slovakia": "sk", "slovenia": "si",
    "solomon islands": "sb", "somalia": "so", "south africa": "za",
    "south korea": "kr", "south sudan": "ss", "spain": "es", "espana": "es",
    "españa": "es", "sri lanka": "lk", "sudan": "sd", "suriname": "sr",
    "swaziland": "sz", "sweden": "se", "switzerland": "ch", "schweiz": "ch",
    "syria": "sy", "taiwan": "tw", "tajikistan": "tj", "tanzania": "tz",
    "thailand": "th", "timor-leste": "tl", "togo": "tg", "tonga": "to",
    "trinidad and tobago": "tt", "tunisia": "tn", "turkey": "tr",
    "turkmenistan": "tm", "turks and caicos islands": "tc", "tuvalu": "tv",
    "uganda": "ug", "ukraine": "ua", "united arab emirates": "ae",
    "united kingdom": "gb", "united states": "us", "usa": "us",
    "united states of america": "us", "uruguay": "uy", "uzbekistan": "uz",
    "vanuatu": "vu", "vatican city": "va", "venezuela": "ve", "vietnam": "vn",
    "yemen": "ye", "zambia": "zm", "zimbabwe": "zw",
    # Pares de 2 segmentos observados na API Phenom (nome do pais dividido
    # entre os dois ultimos segmentos da location).
    "china, people's republic of": "cn",
    "korea, (south) republic": "kr",
    # Variantes comuns em ingles.
    "uk": "gb", "u.k.": "gb", "u.k": "gb",
    # Variantes comuns em ingles.
    "ivory coast": "ci", "cote d'ivoire": "ci", "côte d'ivoire": "ci",
    "burma": "mm", "east timor": "tl", "holland": "nl",
    "england": "gb", "scotland": "gb", "wales": "gb", "northern ireland": "gb",
    "macao": "mo", "macedonia": "mk", "republic of korea": "kr",
    "people's republic of china": "cn", "the bahamas": "bs",
    "the netherlands": "nl", "the philippines": "ph",
    "democratic republic of congo": "cd", "dr congo": "cd", "dr. congo": "cd",
}


def _country_name_from_location(location: str) -> str | None:
    """ISO do pais quando o ULTIMO segmento da ``location`` e um nome de pais.

    Formato "Cidade, Estado, Pais" (API Phenom e similares): o nome do pais
    vem explicito no ultimo segmento separado por virgula — derivar o ISO
    disso e seguro (dado real, nao inferencia inventada). Suporta tambem
    nomes divididos em 2 segmentos ("China, People's Republic of",
    "Korea, (South) Republic").
    """
    parts = [p.strip().rstrip(".") for p in str(location).split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    last = parts[-1].lower()
    code = COUNTRY_NAMES.get(last)
    if code is None and len(parts) >= 2:
        code = COUNTRY_NAMES.get(f"{parts[-2].lower()}, {last}")
    return code


def _iso_token_from_location(location: str) -> str | None:
    """ISO alpha-2 de um token de 2 letras na ``location`` — SOMENTE quando o
    token esta em POSICAO CONFIRAVEL:
      - ultimo segmento da localizacao (ex.: "Neckarsulm, DE",
        "Stuttgart, BW, de" — o ISO vem explicito no fim); ou
      - imediatamente antes de um codigo postal numerico (ex.: SAP grava
        "Walldorf, DE, 69190" sem campo de pais).

    Um token de 2 letras NO MEIO da localizacao nao e pais confiavel: e
    palavra ("de" em espanhol/portugues, "im" em alemao, "do" em portugues)
    ou abreviacao de estado (US/CA/AU). Aceita-lo produzia ISOs falsos
    (ex.: "Ecatepec, Estado de Mexico" -> 'de' Alemanha; "Freiburg im
    Breisgau" -> 'im' Isle of Man; "Sao Bernardo do Campo" -> 'do' Republica
    Dominicana). Descoberto na Fase 3 (Workday): 168/2516 vagas Workday
    carregavam ISO inventado por esse fallback (11 delas 'de' falso, de
    localizacoes no Mexico/Espanha). Estados US ("Lafayette, IN" -> 'in')
    continuam um limite conhecido do ultimo segmento (a sigla de estado
    colide com ISO valido e nao ha como distinguir sem contexto).
    """
    tokens = re.split(r"[\s,.;:]+", location)
    tokens = [t for t in tokens if t]
    for i in range(len(tokens) - 1, -1, -1):
        token = tokens[i]
        if len(token) != 2 or not token.isascii() or not token.isalpha():
            continue
        code = token.lower()
        if code not in COUNTRY_CODES:
            continue
        if i == len(tokens) - 1:
            return code
        nxt = tokens[i + 1]
        if nxt and nxt[0].isdigit():
            return code
    return None


def infer_country_iso(
    location: str | None = None,
    country: str | None = None,
    country_iso: str | None = None,
) -> str | None:
    """ISO alpha-2 do pais da vaga, com fallbacks.

    1. Nome do pais como ULTIMO segmento da ``location`` (ex.: Phenom grava
       "Bonn, Nordrhein-Westfalen, Germany" — o pais vem explicito no dado).
       Vence ate um ``country_iso`` invalido/ruidoso armazenado: corrige
       falsos codigos antigos (ex.: "Remseck am Neckar, ..." -> 'am' Armenia
       pelo token de 2 letras; agora o nome do pais no fim vale 'de').
    2. ``country_iso`` / ``country`` (normalizados).
    3. Codigo de 2 letras valido em posicao confiavel na ``location``
       (``_iso_token_from_location``: ultimo segmento ou antes de CEP
       numerico — ex.: SAP grava "Walldorf, DE, 69190" sem campo de pais).
       Token de 2 letras no MEIO da localizacao NAO vale (palavra/estado).
    """
    if location:
        code = _country_name_from_location(location)
        if code is not None:
            return code
    for value in (country_iso, country):
        if value:
            code = str(value).strip().lower()
            if code in COUNTRY_CODES:
                return code
    if location:
        return _iso_token_from_location(location)
    return None


def is_remote(location: str | None, remote: bool | None) -> bool:
    """Vaga remota? (campo ``remote`` ou "remote"/"home office" na localizacao)."""
    if remote:
        return True
    loc = (location or "").lower()
    return "remote" in loc or "home office" in loc or "homeoffice" in loc


def parse_country_spec(spec: str) -> frozenset[str] | str | None:
    """Normaliza ``--country`` para uma especificacao de filtro.

    Retorna:
      - ``None`` -> sem filtro de pais ("all"; "world"/"any" aceitos por
        compatibilidade — "all" e o canonico);
      - ``"remote"`` -> vaga remota (campo ``remote`` ou "remote"/"home
        office" na localizacao);
      - ``EUROPE_COUNTRIES`` -> "europe";
      - ``frozenset`` de ISOs alpha-2 validos para lista ISO ("de,at,ch").

    Token fora desses (nao-ISO na lista, ex.: "de,xx" ou "europe,de") ou
    spec vazia (ex.: ",") levanta ``ValueError`` com a lista dos tokens
    invalidos — o CLI converte em erro claro (parser.error); chamadas
    diretas da funcao pura recebem a excecao (padronizacao P2 #15/ACH-11).
    Antes, token invalido virava frozenset que nunca casa (0 vagas
    silencioso) ou era ignorado.
    """
    s = (spec or "").strip().lower()
    if not s or s in {"all", "world", "any"}:
        return None
    if s == "remote":
        return "remote"
    if s == "europe":
        return EUROPE_COUNTRIES
    codes = {c.strip() for c in s.split(",") if c.strip()}
    if not codes:
        raise ValueError(
            "spec de pais vazia — use ISO alpha-2 (ex.: 'de,at,ch'), "
            "'europe', 'remote' ou 'all'"
        )
    invalid = sorted(c for c in codes if c not in COUNTRY_CODES)
    if invalid:
        raise ValueError(
            "spec de pais invalida: "
            + ", ".join(repr(c) for c in invalid)
            + " — use ISO alpha-2 (ex.: 'de,at,ch'), 'europe', 'remote' ou 'all'"
        )
    return frozenset(codes)


def matches_country(
    country_iso: str | None,
    location: str | None,
    remote: bool | None,
    spec: frozenset[str] | str | None,
) -> bool:
    """Vaga atende a especificacao de pais/localizacao? (spec = parse_country_spec)"""
    if spec is None:
        return True
    if isinstance(spec, str):  # "remote"
        return is_remote(location, remote)
    iso = infer_country_iso(location=location, country_iso=country_iso)
    return iso is not None and iso in spec