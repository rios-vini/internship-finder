"""Deduplicacao de vagas — funcoes puras, sem dependencia de CLI/modelos.

Duas entradas sao a MESMA vaga quando baterem em qualquer uma das chaves, em
ordem de confiabilidade (a primeira que bater decide):

1. ``external_id`` (ou ``id``) do ATS — identidade oficial da vaga no sistema
   de origem (SmartRecruiters publica ids globais; SuccessFactors ids numericos
   longos). Quando presente e o sinal mais forte.
2. URL normalizada — sem fragmento, sem barra final, casefold (a query e
   mantida: eightfold carrega o id da vaga nela).
3. ``company + titulo normalizado + localizacao normalizada`` — fallback para
   quando nao ha id/URL confiavel (ou quando a mesma vaga foi publicada com
   outro id, ex.: versoes EN/DE de um mesmo cargo, ou repostagens).

Para pegar EN/DE e variantes, o titulo e normalizado em passos deterministicos:
casefold, remocao de acentos, remocao de sufixos de genero (m/w/d, f/m/d,
w/m/div., "all genders"...), equivalencia de marcador de tipo traduzido
(``Werkstudent`` == ``Working Student`` — mesma relacao que o filtro
``is_student_role`` ja usa), remocao de palavras funcionais EN/DE (artigos,
preposicoes, "start/starte your/deine"...) e comparacao do BAG de palavras
(ordem indiferente: "Praktikum in der Logistik - Data & Analytics" ==
"Praktikum Data Analytics in der Logistik").

Limite documentado: titulos que sao traducao real (conteudo diferente, nao so
palavra funcional — ex.: "Marketing Deutschland" vs "Marketing Germany",
"Strategischer Vertrieb" vs "Strategic Sales") NAO sao considerados duplicatas:
exigiria dicionario de traducao/fuzzy, fora do escopo do MVP.

Regra do "vencedor" quando duas versoes da mesma vaga existem (deterministica):
1. a que tem ``description`` preenchida; 2. senao a que tem ``employment_type``;
3. senao a que veio primeiro na lista de entrada. As demais sao removidas.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

# ---------------------------------------------------------------------------
# Normalizacoes
# ---------------------------------------------------------------------------

# Sufixos de genero comuns em vagas DE/EN (removidos do titulo).
GENDER_SUFFIX_PATTERNS = [
    r"\b(?:m/w/d|x|mwd|f/m/d|f/m|m/f/d|m/f|w/m/d|w/m|m/w|d/m/w)\b",
    r"\b(?:w/m/div\.?|m/w/div\.?|all genders|alle geschlechter|all gender|any gender)\b",
]

# Marcadores de tipo de vaga traduzidos DE->EN. Minimalista e intencional:
# apenas marcadores de tipo de vaga (mesma relacao que ``filters.is_student_role``
# ja enxerga como equivalentes), NAO palavras de conteudo (pais, departamento).
TYPE_EQUIVALENCES = [
    (r"\bwerkstudentin\b", "working student"),
    (r"\bwerkstudenten?\b", "working student"),
    (r"\bwerkstudent\b", "working student"),
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


def _strip_accents(text: str) -> str:
    """Remove acentos (ex.: 'Höhe' -> 'Hohe', 'für' -> 'fur')."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_url(url: str | None) -> str:
    """URL canonica: sem fragmento, sem barra final, casefold.

    A QUERY string e MANTIDA: em ATS como eightfold a identidade da vaga vive
    na query (ex.: ``.../job/private?pid=5638...``) — strip-la fundiria vagas
    diferentes. Consequencia aceita: query de tracking (``?utm_*``) nao funde
    a mesma vaga — e um dup perdido (seguro), nao um falso positivo.
    """
    if not url:
        return ""
    u = str(url).strip()
    u = _URL_FRAGMENT.sub("", u)  # strip #fragment (query fica)
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
    return " ".join(sorted(tokens))


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
# Chaves de deduplicacao
# ---------------------------------------------------------------------------

# Rotulos usados no relatorio do CLI (e no retorno de ``deduplicate``).
KEY_EXTERNAL_ID = "external_id"
KEY_URL = "url"
KEY_COMPANY_TITLE_LOCATION = "company+title+location"
KEY_LABELS = [KEY_EXTERNAL_ID, KEY_URL, KEY_COMPANY_TITLE_LOCATION]


def candidate_keys(job: dict[str, Any]) -> list[tuple[str, str | tuple[str, str, str]]]:
    """Chaves candidatas de uma vaga, da mais confiavel para a menos.

    A primeira chave que colidir com uma vaga ja vista decide a duplicata
    (a ``external_id`` sozinha e suficiente; a URL entra quando o id falha; a
    chave company+titulo+localizacao so e usada quando as duas anteriores nao
    existem ou nao batem). A chave (c) exige titulo E localizacao nao vazios:
    sem localizacao, titulos iguais em cidades diferentes seriam fundidos.
    """
    keys: list[tuple[str, str | tuple[str, str, str]]] = []

    ext = job.get("external_id") or job.get("id")
    if ext:
        keys.append((KEY_EXTERNAL_ID, str(ext).strip()))

    url = normalize_url(job.get("url"))
    if url:
        keys.append((KEY_URL, url))

    company = (job.get("company") or "").strip().casefold()
    title = normalize_title(job.get("title"))
    location = normalize_location(job.get("location"))
    if company and title and location:
        keys.append((KEY_COMPANY_TITLE_LOCATION, (company, title, location)))

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
