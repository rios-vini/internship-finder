"""Normalizacao HTML -> texto plano (BeautifulSoup, html.parser).

Sem markdown, sem dependencia nova: remove blocos claramente irrelevantes
(script/style/noscript/template/svg/head + nav/footer e header boilerplate),
extrai o texto com separador de linha e colapsa whitespace. Pagina que vira
texto vazio devolve ``""`` — a classificacao (``fetch.classify_page``) cuida
do resto (empty_content/js_rendered).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Tags mortas para extracao: 100% codigo/estilo, zero conteudo de vaga.
_DEAD_TAGS = ("script", "style", "noscript", "template", "svg", "head")
# Navegacao/rodape claramente irrelevantes para o anuncio.
_NAV_TAGS = ("nav", "footer")


def normalize_html(html: str) -> str:
    """HTML bruto -> texto util para o prompt da LLM.

    ``<header>`` e removido apenas quando e boilerplate de menu (contem
    ``<nav>``); header com o titulo da vaga fica — remover o ``<h1>``
    quebraria o casamento de titulo do ``classify_page``. Entidades HTML
    (``&ccedil;`` etc.) sao decodificadas pelo get_text do BeautifulSoup.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(_DEAD_TAGS):
        tag.decompose()
    for tag in soup(_NAV_TAGS):
        tag.decompose()
    for tag in soup.find_all("header"):
        if tag.find("nav"):
            tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
