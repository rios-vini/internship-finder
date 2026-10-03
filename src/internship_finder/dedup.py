"""Deduplicacao de vagas — funcoes puras, sem dependencia de CLI/modelos.

Duas entradas sao a MESMA vaga quando baterem em qualquer uma das chaves, em
ordem de confiabilidade (a primeira que bater decide):

1. ``external_id`` (ou ``id``) do ATS — identidade oficial da vaga no sistema
   de origem (SmartRecruiters publica ids globais; SuccessFactors ids numericos
   longos). Quando presente e o sinal mais forte. **Escopada pela identidade
   empresarial + origem (``company`` + ``source``)**: o mesmo valor de
   ``external_id`` em empresas diferentes representa vagas DIFERENTES — mesmo
   DENTRO do mesmo tenant ATS compartilhado (P1.1: ``successfactors:jobs``
   cobre SAP/ZF/Kaufland/...; cada empresa numera seus ids de forma
   independente dentro do tenant).
2. URL normalizada — sem fragmento, sem barra final, casefold (a query e
   mantida: eightfold carrega o id da vaga nela). Tambem escopada pela
   empresa (P1.1): uma URL identica em empresas diferentes nao pode fazer a
   Empresa B remover a vaga da Empresa A.
3. ``company + titulo normalizado + localizacao normalizada`` — fallback para
   quando nao ha id/URL confiavel (ou quando a mesma vaga foi publicada com
   outro id, ex.: versoes EN/DE de um mesmo cargo, ou repostagens).

Para pegar EN/DE e variantes, o titulo e normalizado em passos deterministicos:
casefold, remocao de acentos, remocao de sufixos de genero (m/w/d, f/m/d,
w/m/div., "all genders"...), equivalencia de marcador de tipo traduzido
(``Werkstudent`` == ``Working Student`` == ``Praktikum`` == ``Intern(ship)`` —
mesma relacao que o filtro ``is_student_role`` ja usa), remocao de palavras
funcionais EN/DE (artigos, preposicoes, "start/starte your/deine"...) e
comparacao do BAG de palavras (ordem indiferente: "Praktikum in der Logistik -
Data & Analytics" == "Praktikum Data Analytics in der Logistik"). Palavras
repetidas na bag sao colapsadas (ex.: "Werkstudentin / Werkstudent" vira um
unico "working student").

Limite documentado (parcialmente fechado pela F5): o tier 4 agora cobre a
traducao REAL mais comum — marcadores de tipo ja eram equivalentes no tier
3 (Praktikum<->Internship); a F5 adicionou o dicionario MINIMO de conteudo
DE->EN (Logistik/Logistics, Einkauf/Purchasing, Vertrieb/Sales...) e alias
de cidade (Munich/Munchen). Titulos com conteudo fora do dicionario minimo
(ex.: "Betriebswirtschaft" vs "Business Administration") NAO fundem: o
dicionario e deliberadamente minimo para nao gerar falsos positivos — um
token divergente impede a fusao (trade-off documentado no relatorio F5).

Regra do "vencedor" quando duas versoes da mesma vaga existem (deterministica):
1. a que tem ``description`` preenchida; 2. senao a que tem ``employment_type``;
3. senao a que veio primeiro na lista de entrada. As demais sao removidas.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

# F5 — aliases de cidade EN->DE do Company Intelligence (mesma fonte da
# verdade do enriquecimento; ``opportunity_intel`` nao importa ``dedup``,
# sem ciclo). Usados SO pelo tier DE/EN da deduplicacao.
from internship_finder.opportunity_intel import CITY_ALIASES as _CITY_ALIASES

# ---------------------------------------------------------------------------
# Normalizacoes
# ---------------------------------------------------------------------------

# Sufixos de genero comuns em vagas DE/EN (removidos do titulo).
GENDER_SUFFIX_PATTERNS = [
    r"\b(?:m/w/d|x|mwd|f/m/d|f/m|m/f/d|m/f|w/m/d|w/m|m/w|d/m/w)\b",
    r"\b(?:w/m/div\.?|m/w/div\.?|all genders|alle geschlechter|all gender|any gender)\b",
]

# Marcadores de tipo de vaga traduzidos DE->EN->DE. Minimalista e intencional:
# apenas marcadores de tipo de vaga (mesma relacao que ``filters.is_student_role``
# ja enxerga como equivalentes), NAO palavras de conteudo (pais, departamento).
# Alem do par original ``Werkstudent`` == ``Working Student``, cobrem os pares
# reais medidos no dataset (03/09): ``Praktikum`` == ``Internship`` == ``Intern``
# == ``Praktikant`` == ``Working Student`` = ``Werkstudent``. Os ``\b`` de borda
# de palavra garantem que markadores compostos de outra natureza (ex.:
# ``Pflichtpraktikum``, ``Hochschulpraktikum``) NAO sejam atingidos.
TYPE_EQUIVALENCES = [
    (r"\bwerkstudenten?\b", "working student"),
    (r"\bwerkstudentin\b", "working student"),
    (r"\bwerkstudent\b", "working student"),
    (r"\bpraktikanten?\b", "working student"),
    (r"\bpraktikantin\b", "working student"),
    (r"\bpraktikant\b", "working student"),
    (r"\bpraktikums?\b", "working student"),
    (r"\binternships?\b", "working student"),
    (r"\binterns?\b", "working student"),
]

# Palavras funcionais EN/DE removidas do titulo para a comparacao (nao carregam
# a identidade da vaga: artigos, preposicoes, verbos de ligacao e as variacoes
# de traducao vistas nos pares EN/DE reais, ex.: "Start your..." / "Starte
# deine..."). Acentos sao removidos ANTES (ex.: "für" vira "fur" e e coberto).
FUNCTION_WORDS = frozenset(
    """
    a an and or of in on at to for from with your you my our the as by be do it
    der die das den dem des ein eine einen einem einer und oder im in fur von
    mit bei zu als start starte deine bereich unser werden
    """.lower().split()
)

_URL_FRAGMENT = re.compile(r"#.*$")

# F5 — params de TRACKING removidos da URL canonica de dedup (tier 1/URL).
# O buraco documentado (dedup.py antes da F5): "?utm_*" nao fundia a mesma
# vaga — dup perdido (aceito ate hoje). Agora o strip e ANTES da chave URL.
# REGRA: so params que NUNCA carregam identidade da vaga. Params funcionais
# (page, id, pid, jf, refNum, req...) sao PRESERVADOS — em ATS como eightfold
# a identidade vive na query ("...?pid=5638..."); strip-la fundiria vagas
# diferentes (falso positivo caro). Assimetria deliberada: param novo
# duvidoso NAO entra (um dup perdido e mais barato que uma fusao errada).
#
# Duas regras: (1) qualquer param com prefixo ``utm_`` e tracking POR
# DEFINICAO (convencao do Google Analytics — utm_source, utm_medium,
# utm_campaign, utm_content, e qualquer variante futura); (2) lista fixa de
# trackers conhecidos, incluindo os citados pela spec (gclid, fbclid, ref,
# source). "site"/"siteid"/"sjid" ficam FORA: podem ser funcionais em boards.
_TRACKING_PARAMS = frozenset(
    """
    gclid fbclid msclkid dclid twclid ttclid li_fat_id igshid
    mc_cid mc_eid ref referrer referer source spm
    _ga _gl _hsenc _hsmi
    """.lower().split()
)
_TRACKING_PREFIXES = ("utm_",)


def _is_tracking_param(name: str) -> bool:
    """Param de tracking? (prefixo ``utm_`` OU lista fixa)."""
    n = name.strip().lower()
    if not n:
        return False
    if n in _TRACKING_PARAMS:
        return True
    return any(n.startswith(p) for p in _TRACKING_PREFIXES)


def _strip_tracking_params(query: str) -> str:
    """Remove params de tracking de uma query string (sem '?')."""
    if not query:
        return ""
    kept: list[str] = []
    for part in query.split("&"):
        if not part:
            continue
        name = part.split("=", 1)[0]
        if _is_tracking_param(name):
            continue
        kept.append(part)
    return "&".join(kept)


def _strip_accents(text: str) -> str:
    """Remove acentos (ex.: 'Höhe' -> 'Hohe', 'für' -> 'fur')."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_url(url: str | None) -> str:
    """URL canonica: sem fragmento, sem barra final, casefold, sem tracking.

    A QUERY string e MANTIDA (menos params de tracking — F5): em ATS como
    eightfold a identidade da vaga vive na query (ex.: ``.../job/private?
    pid=5638...``) — strip-la fundiria vagas diferentes. Params de tracking
    (``utm_*``, gclid, fbclid, ref, source...) sao REMOVIDOS antes da
    comparacao: nunca carregam identidade, so campanha de marketing. O
    buraco documentado antes da F5 ("query de tracking nao funde a mesma
    vaga") esta fechado — mesmo anuncio compartilhado com e sem ``?utm_``
    agora colapsa na chave URL.
    """
    if not url:
        return ""
    u = str(url).strip()
    u = _URL_FRAGMENT.sub("", u)  # strip #fragment (query fica)
    if "?" in u:
        base, _, query = u.partition("?")
        query = _strip_tracking_params(query)
        u = f"{base}?{query}" if query else base
    u = u.rstrip("/")
    return u.casefold()


def normalize_title(title: str | None) -> str:
    """Titulo canonico para comparacao de igualdade.

    Passos: casefold -> remove acentos -> remove sufixos de genero ->
    equivalencia de marcador de tipo (werkstudent == working student) ->
    tokens sem pontuacao -> remove palavras funcionais EN/DE -> palavras em
    ordem alfabetica (bag). Duas versoes da mesma vaga produzem a mesma string.
    """
    if not title:
        return ""
    t = _strip_accents(str(title).casefold())
    for pattern in GENDER_SUFFIX_PATTERNS:
        t = re.sub(pattern, " ", t)
    for pattern, repl in TYPE_EQUIVALENCES:
        t = re.sub(pattern, repl, t)
    tokens = re.findall(r"[a-z0-9]+", t)
    tokens = [w for w in tokens if w not in FUNCTION_WORDS]
    # Colapsa palavras repetidas na BAG (ordem indiferente -> duplicadas nao
    # carregam identidade). Necessario para variantes como "Werkstudentin /
    # Werkstudent" (vista em pares DE reais) que, apos a equivalencia de tipo,
    # virariam "working student working student" — e nao devem diferir de uma
    # vaga com um unico "working student".
    return " ".join(dict.fromkeys(sorted(tokens)))


def normalize_location(location: str | None) -> str:
    """Localizacao canonica: casefold, sem acentos, espacos colapsados,
    sem o codigo ISO-2 de pais no final (ex.: 'Stuttgart, DE' -> 'stuttgart')."""
    if not location:
        return ""
    loc = _strip_accents(str(location).casefold()).strip()
    loc = re.sub(r"\s+", " ", loc)
    loc = re.sub(r",\s*[a-z]{2}$", "", loc)  # trailing ISO-2 (ex.: ", de")
    return loc.strip()


# ---------------------------------------------------------------------------
# F5 — Tier DE/EN: traducao MINIMA de conteudo para o 4o tier da dedup
# ---------------------------------------------------------------------------

# Dicionario DE<->EN de palavras de CONTEUDO para o tier DE/EN (4a chave).
# MINIMALISTA E INTENCIONAL, 3 regras:
#   (1) so termos de area funcional comuns em titulos de vagas — nunca
#       jargo proprio de empresa/produto (traduzir "S4 Hana" seria FP);
#   (2) so pares UNIVOCOS (sem polissemia: "personal" NAO entra — "Personal
#       DE=RH" cruzaria com "Personal Assistant EN");
#   (3) marcadores de TIPO de vaga NAO entram aqui — ja sao colapsados pelo
#       ``TYPE_EQUIVALENCES`` do ``normalize_title`` em TODOS os tiers
#       (Praktikum<->internship, Werkstudent<->working student — a spec F5
#       cita exatamente esses pares; o que FALTA no tier 3 e a traducao de
#       CONTEUDO e o alias de CIDADE).
# Forma: token -> forma canonica (DE e EN convergem para a MESMA string;
# valores multi-palavra sao re-divididos em tokens pelo consumidor).
CONTENT_TRANSLATIONS: dict[str, str] = {
    # logistica/operacoes (canonica EN)
    "logistik": "logistics",
    "lieferkette": "supply chain",
    "einkauf": "purchasing",
    "beschaffung": "procurement",
    "lager": "warehouse",
    "versand": "shipping",
    "produktion": "production",
    "fertigung": "manufacturing",
    # dados/IT
    "daten": "data",
    "datenanalyse": "data analytics",
    "informatik": "computer science",
    "kunstliche": "artificial",
    "intelligenz": "intelligence",
    # negocios
    "vertrieb": "sales",
    "buchhaltung": "accounting",
    "finanzen": "finance",
    # adjetivos comuns com flexao de genero/caso DE (Einkauf/Vertrieb)
    "strategischer": "strategic",
    "strategische": "strategic",
    "strategisches": "strategic",
}


def _de_en_title_key(title: str | None) -> str:
    """Chave de titulo do tier DE/EN: bag normalizada + traducao de conteudo.

    Partir do ``normalize_title`` (bag ordenada, ja com marcadores de tipo
    colapsados e palavras funcionais removidas) e aplicar o dicionario
    DE->EN token a token. Valores multi-palavra ("supply chain") sao
    RE-DIVIDIDOS em tokens — DE e EN convergem para a mesma bag. Palavras
    fora do dicionario ficam como estao: o par so funde se TODO o conteudo
    bater apos a traducao (conservador — um token divergente nao funde).
    """
    bag = normalize_title(title)
    if not bag:
        return ""
    out: list[str] = []
    for token in bag.split():
        out.extend(CONTENT_TRANSLATIONS.get(token, token).split())
    return " ".join(sorted(dict.fromkeys(out)))


def _de_en_location_key(location: str | None) -> str:
    """Chave de localizacao do tier DE/EN: CIDADE com alias EN->DE colapsado.

    Reuso da MESMA tabela do enriquecimento de cidade (Fase 7,
    ``CITY_ALIASES``): "Munich" == "München" == "munchen". A chave do tier
    DE/EN e a CIDADE CANONICA — primeira parte da localizacao, no formato
    REAL do dataset ("Stuttgart, BW, de" — cidade primeiro; as demais
    partes são região/ISO/CEP e divergem entre idiomas sem ganho: o
    titulo+empresa do tier já discriminam). A forma exibida ao usuário
    nunca muda — só a chave de dedup.
    """
    loc = normalize_location(location)
    if not loc:
        return ""
    city = loc.split(",", 1)[0].strip()
    return _CITY_ALIASES.get(city, city)


# ---------------------------------------------------------------------------
# Chaves de deduplicacao
# ---------------------------------------------------------------------------

# Rotulos usados no relatorio do CLI (e no retorno de ``deduplicate``).
KEY_EXTERNAL_ID = "external_id"
KEY_URL = "url"
KEY_COMPANY_TITLE_LOCATION = "company+title+location"
# F5 — 4o tier: mesma empresa + local + titulo apos traducao MINIMA de
# conteudo DE<->EN (o tier 3 ja colapsa marcadores de tipo; este cobre o
# par "Praktikum Logistik" vs "Logistics Internship" e "Munich"/"München").
KEY_COMPANY_TITLE_LOCATION_DE_EN = "company+title+location+de/en"
KEY_LABELS = [
    KEY_EXTERNAL_ID,
    KEY_URL,
    KEY_COMPANY_TITLE_LOCATION,
    KEY_COMPANY_TITLE_LOCATION_DE_EN,
]


def candidate_keys(job: dict[str, Any]) -> list[tuple[str, str | tuple[str, str] | tuple[str, str, str]]]:
    """Chaves candidatas de uma vaga, da mais confiavel para a menos.

    A primeira chave que colidir com uma vaga ja vista decide a duplicata
    (a ``external_id`` sozinha e suficiente; a URL entra quando o id falha; a
    chave company+titulo+localizacao so e usada quando as duas anteriores nao
    existem ou nao batem). A chave (c) exige titulo E localizacao nao vazios:
    sem localizacao, titulos iguais em cidades diferentes seriam fundidos.

    A chave (a) e escopada pela IDENTIDADE EMPRESARIAL + origem (``company``
    + ``source``): o mesmo valor de ``external_id`` em empresas diferentes
    representa vagas DIFERENTES — mesmo DENTRO de um tenant ATS compartilhado
    (P1.1: ``successfactors:jobs`` cobre SAP/ZF/Kaufland/...; cada tenant
    numera seus ids de forma independente POR EMPRESA). ``company`` e a mesma
    identidade que prefixa o ``Job.id`` (``<company>|<source>:...``) — o
    mesmo job nao pode ser considerado duplicata de outro so porque
    ``source == source`` e ``external_id == external_id``. A chave (b) (URL)
    tambem e escopada pela empresa: URL identica em empresas diferentes nao
    funde. Quando nao ha ``external_id``, usa-se o ``id`` canonico do job (ja
    ``<company>|<source>:...`` no pipeline, portanto unico por empresa+tenant).
    """
    keys: list[tuple[str, str | tuple[str, str] | tuple[str, str, str]]] = []

    # Mesma normalizacao do prefixo do ``Job.id``: strip, SEM casefold (a
    # identidade de empresa preserva a forma exibida; casefold aqui
    # divergiria do token do id e quebraria a dedup dentro da mesma empresa).
    company = (job.get("company") or "").strip()
    source = str(job.get("source") or "").strip()
    ext = job.get("external_id")
    if ext:
        scope = f"{company}|{source}" if (company or source) else ""
        key = f"{scope}:{str(ext).strip()}" if scope else str(ext).strip()
        keys.append((KEY_EXTERNAL_ID, key))
    else:
        job_id = job.get("id")
        if job_id:
            keys.append((KEY_EXTERNAL_ID, str(job_id).strip()))

    url = normalize_url(job.get("url"))
    if url:
        keys.append((KEY_URL, (company, url)))

    company = (job.get("company") or "").strip().casefold()
    title = normalize_title(job.get("title"))
    location = normalize_location(job.get("location"))
    if company and title and location:
        keys.append((KEY_COMPANY_TITLE_LOCATION, (company, title, location)))

    # F5 — tier DE/EN: a MESMA vaga publicada em DE e EN (conteudo do titulo
    # traduzido, cidade com alias EN<->DE). Conservador por construcao: so
    # funde se empresa E local E conteudo-do-titulo baterem apos a traducao
    # minima — um token de conteudo fora do dicionario ja impede a fusao.
    # Exige os mesmos campos do tier 3 (titulo E localizacao nao vazios).
    de_en_title = _de_en_title_key(job.get("title"))
    de_en_location = _de_en_location_key(job.get("location"))
    if company and de_en_title and de_en_location:
        keys.append(
            (KEY_COMPANY_TITLE_LOCATION_DE_EN, (company, de_en_title, de_en_location))
        )

    return keys


def _prefer(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """``candidate`` deve substituir ``current`` como vencedor?

    Regra deterministica: (1) descricao preenchida; (2) employment_type
    preenchido; (3) quem veio primeiro vence (ordem da lista de entrada).
    """
    if bool(candidate.get("description")) and not bool(current.get("description")):
        return True
    if bool(candidate.get("employment_type")) and not bool(current.get("employment_type")):
        return True
    return False


def deduplicate(
    jobs: list[dict[str, Any]] | list[Any],
) -> tuple[list[dict[str, Any]], dict[str, int], list[tuple[dict[str, Any], dict[str, Any], str]]]:
    """Remove duplicatas de uma lista de vagas (dicts ou ``Job``).

    Retorna ``(sem_duplicatas, estatisticas, removidas)`` onde:
    - ``estatisticas``: {rotulo_da_chave: quantas removidas} (ex.:
      ``{"company+title+location": 12}``);
    - ``removidas``: lista de ``(vencedora, removida, rotulo_da_chave)`` para
      auditoria/verificacao (a vencedora e a que fica no resultado).

    Deterministico: a iteracao segue a ordem da entrada e o vencedor segue a
    regra ``_prefer`` (descricao > employment_type > primeira).
    """
    seen: dict[Any, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    removed: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    stats: Counter[str] = Counter()

    for item in jobs:
        job = item.to_dict() if hasattr(item, "to_dict") else item
        keys = candidate_keys(job)

        matched: tuple[str, Any] | None = None
        for label, key in keys:
            if key in seen:
                matched = (label, key)
                break

        if matched is None:
            for label, key in keys:
                seen[key] = job
            out.append(job)
            continue

        label, key = matched
        winner = seen[key]
        if _prefer(job, winner):
            # Candidata vence: troca no resultado e em todas as chaves que
            # apontavam para o vencedor antigo.
            out[out.index(winner)] = job
            removed.append((job, winner, label))
            for k, v in seen.items():
                if v is winner:
                    seen[k] = job
        else:
            removed.append((winner, job, label))
        stats[label] += 1

    return out, dict(stats), removed
