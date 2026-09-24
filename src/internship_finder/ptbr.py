"""Camada PT-BR da interface — Fase 5 (compreensao das vagas).

Apresenta em portugues campos estruturados da vaga (titulo traduzido de forma
deterministica, tipo, modalidade, pais, sinais de relevancia e score breakdown
explicado), SEM traduzir a descricao inteira e SEM LLM/API/servico externo.
Nao altera ranking, score, filtros nem dedup: apenas ENRIQUECE a exibicao do
resultado existente.

Principios (enunciado da Fase 5):

- **Glossario pequeno e deterministico**: termos realmente recorrentes
  (Working Student, Internship, Procurement, Supply Chain...) com traducao
  unica canonica; termos profissionais internacionais podem aparecer junto da
  traducao PT-BR (ex.: "Compras (Procurement)", "Working Student (Werkstudent)")
  para nao substituir a terminologia do mercado. Nao e um tradutor generico.
- **Preservar o original**: o titulo da vaga NUNCA e substituido; a traducao
  PT-BR (quando segura de gerar por regras locais) e um CAMPO SEPARADO
  ("PT-BR"), com o original sempre visivel ("Original").
- **Nao inventar**: campo indisponivel simplesmente nao e exibido.
- **Determinismo total**: mesma vaga -> mesmas traducoes/rotulos (regex sem
  estado e sem rede), computadas uma vez por vaga na geracao do HTML.

Como adicionar termos no futuro: acrescente uma entrada em ``GLOSSARY``
(``regex -> (frase_pt, rotulo_pt)``), de preferencia com a frase especifica
antes da generica (frases compostas antes de palavras soltas). Documentado em
README e em docs/relatorio_fase5_ptbr.md.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Glossario deterministico. Cada entrada: (regex, frase_pt, rotulo_pt).
#
# Regras de ouro:
# 1. ORDEM = especificidade: frases compostas (mais palavras) ANTES de
#    palavras soltas do mesmo grupo ("Supply Chain Management" antes de
#    "Supply Chain"; "Materials Engineering" antes de "Materials"; "SAP
#    Analytics Cloud" antes de "Analytics"). A alternancia une as regexes na
#    ordem da lista e o motor escolhe a PRIMEIRA que casa em cada posicao.
# 2. ``frase_pt`` = representacao PT-BR; manter o termo internacional entre
#    parenteses quando a traducao sozinha perderia o jargao do anúncio.
# 3. ``rotulo_pt`` = classificacao curta (chips/sinais), opcional.
# 4. Frases "identidade" (mantem o texto original) existem para PROTEGER
#    nomes proprios de produto da traducao generica (ex.: SAP Analytics
#    Cloud) — usa-se ``frase_pt=None``.
# 5. NUNCA traduzir a descricao inteira — so termos/grupos deste glossario.
# ---------------------------------------------------------------------------

GLOSSARY: list[tuple[str, str | None, str | None]] = [
    # ---- Frases compostas (especificas primeiro) ----
    (r"\bsap analytics cloud\b", None, None),  # nome de produto — nao traduzir
    (r"\bsupply chain management\b", "Gestão da Cadeia de Suprimentos", "Cadeia de Suprimentos"),
    (r"\bsupply chain analytics\b", "Análise de Dados da Cadeia de Suprimentos", "Cadeia de Suprimentos"),
    (r"\bworking student\b", "Estudante / Working Student", "Estágio"),
    (r"\bstudent worker\b", "Estudante trabalhador", "Estágio"),
    (r"\bstudent trainee\b", "Estudante em treinamento", "Estágio"),
    (r"\bstrategic procurement\b", "Compras Estratégicas", "Compras"),
    (r"\bstrategic sourcing\b", "Sourcing Estratégico", "Compras"),
    (r"\bglobal supply chain\b", "Cadeia de Suprimentos Global", "Cadeia de Suprimentos"),
    (r"\banalytics advisory\b", "Consultoria em Análise de Dados", "Dados"),
    (r"\bmaster of science\b", "Mestrado (Master of Science)", "Tese"),
    (r"\bprocess optimization\b", "Otimização de Processos", "Processos"),
    (r"\bgeneral service\b", "Serviços Gerais", "Operações"),
    (r"\bscm\b", "Cadeia de Suprimentos (SCM)", "Cadeia de Suprimentos"),
    (r"\bsc&l\b", None, None),  # sigla de negocio — nao traduzir
    (r"\bim bereich\w*", "na área de", None),
    (r"\bmaster'?s? thesis\b", "Tese de mestrado", "Tese"),
    (r"\bbachelor'?s? thesis\b", "Tese de bacharelado", "Tese"),
    (r"\bdata analytics\b", "Análise de Dados", "Dados"),
    (r"\bdata science\b", "Ciência de Dados", "Dados"),
    (r"\bdata engineering\b", "Engenharia de Dados", "Dados"),
    (r"\bdata engineer\b", "Engenheiro(a) de Dados", "Dados"),
    (r"\bmaterials engineering\b", "Engenharia de Materiais", "Materiais"),
    (r"\bmaterials science\b", "Ciência dos Materiais", "Materiais"),
    (r"\bmechanical engineering\b", "Engenharia Mecânica", "Engenharia"),
    (r"\belectrical engineering\b", "Engenharia Elétrica", "Engenharia"),
    (r"\bindustrial engineering\b", "Engenharia Industrial", "Engenharia"),
    (r"\bchemical engineering\b", "Engenharia Química", "Engenharia"),
    (r"\bprocess engineering\b", "Engenharia de Processos", "Processos"),
    (r"\bsoftware engineering\b", "Engenharia de Software", "Software"),
    (r"\bsoftware development\b", "Desenvolvimento de Software", "Software"),
    (r"\bcomputer science\b", "Ciência da Computação", "Computação"),
    (r"\bbusiness intelligence\b", "Inteligência de Negócios (BI)", "BI"),
    (r"\bprocess automation\b", "Automação de Processos", "Automação"),
    (r"\bartificial intelligence\b", "Inteligência Artificial (IA)", "IA"),
    (r"\bmachine learning\b", "Aprendizado de Máquina", "IA"),
    (r"\bdeep learning\b", "Aprendizado Profundo", "IA"),
    (r"\bresearch\s*(?:&|and)\s*development\b", "Pesquisa e Desenvolvimento (P&D)", "P&D"),
    (r"\badditive manufacturing\b", "Manufatura Aditiva (3D)", "Manufatura"),
    (r"\bproject management\b", "Gestão de Projetos", "Gestão"),
    (r"\bproduct management\b", "Gestão de Produto", "Gestão"),
    (r"\bsupplier management\b", "Gestão de Fornecedores", "Fornecedores"),
    (r"\bquality management\b", "Gestão da Qualidade", "Qualidade"),
    (r"\bbusiness administration\b", "Administração de Empresas", "Administração"),
    (r"\bbusiness development\b", "Desenvolvimento de Negócios", "Negócios"),
    (r"\bcustomer service\b", "Atendimento ao Cliente", "Atendimento"),
    (r"\bhuman resources\b", "Recursos Humanos (RH)", "RH"),

    # ---- Germanismos compostos (prefixo, sem fronteira final) ----
    (r"\bpflichtpraktikum\w*", "Estágio obrigatório (Pflichtpraktikum)", "Estágio"),
    (r"\bhochschulpraktikum\w*", "Estágio universitário (Hochschulpraktikum)", "Estágio"),
    (r"\bwerkstudent\w*", "Estudante / Working Student (Werkstudent)", "Estágio"),
    (r"\bpraktikant\w*", "Estagiário(a) (Praktikant)", "Estágio"),
    (r"\bpraktikum\w*", "Estágio (Praktikum)", "Estágio"),
    (r"\bmasterarbeit\w*", "Tese de mestrado (Masterarbeit)", "Tese"),
    (r"\bbachelorarbeit\w*", "Tese de bacharelado (Bachelorarbeit)", "Tese"),
    (r"\b(?:abschluss|studien)[- ]?arbeit\w*", "Trabalho de conclusão", "Tese"),
    (r"\bmaterialwissenschaft\w*", "Ciência dos Materiais (Materialwissenschaft)", "Materiais"),
    (r"\bmaterialtechnik\w*", "Engenharia de Materiais (Materialtechnik)", "Materiais"),
    (r"\bwerkstofftechnik\w*", "Engenharia de Materiais (Werkstofftechnik)", "Materiais"),
    (r"\bwerkstoff\w*", "Materiais (Werkstoff)", "Materiais"),
    (r"\bverfahrenstechnik\w*", "Engenharia de Processos (Verfahrenstechnik)", "Processos"),
    (r"\bprozesstechnik\w*", "Engenharia de Processos (Prozesstechnik)", "Processos"),
    (r"\bbeschichtung\w*", "Revestimentos (Beschichtung)", "Materiais"),
    (r"\bdatenanalyse\w*", "Análise de Dados (Datenanalyse)", "Dados"),
    (r"\bdigitalisierung\w*", "Digitalização", "Digitalização"),
    (r"\bfertigung\w*", "Manufatura (Fertigung)", "Manufatura"),
    (r"\bproduktion\w*", "Produção", "Produção"),
    (r"\blogistik\w*", "Logística", "Logística"),
    (r"\bbeschaffung\w*", "Compras (Beschaffung)", "Compras"),
    (r"\beinkauf\w*", "Compras (Einkauf)", "Compras"),
    (r"\bqualität\w*", "Qualidade", "Qualidade"),
    (r"\bbereich\w*", "área", None),
    (r"\bchemie\w*", "Química", "Química"),
    (r"\bkunststoff\w*", "Plásticos (Kunststoff)", "Materiais"),
    (r"\bkorrosion\w*", "Corrosão", "Materiais"),
    (r"\bhalbleiter\w*", "Semicondutores", "Semicondutores"),
    (r"\bbatterie\w*", "Bateria", "Materiais"),
    (r"\bforschung\w*", "Pesquisa", "P&D"),
    (r"\bentwickl\w*", "Desenvolvimento", "P&D"),
    (r"\btechnologieentwicklung\w*", "Desenvolvimento Tecnológico", "P&D"),

    # ---- Palavras soltas (genericas, por ultimo no grupo) ----
    (r"\binternships?\b", "Estágio (Internship)", "Estágio"),
    (r"\bintern\b", "Estagiário(a) (Intern)", "Estágio"),
    (r"\bthesis\b", "Tese", "Tese"),
    (r"\bsupply chain\b", "Cadeia de Suprimentos", "Cadeia de Suprimentos"),
    (r"\bprocurement\b", "Compras (Procurement)", "Compras"),
    (r"\bpurchasing\b", "Compras (Purchasing)", "Compras"),
    (r"\bsourcing\b", "Sourcing (Compras)", "Compras"),
    (r"\bsupplier\b", "Fornecedores", "Fornecedores"),
    (r"\bmaterials\b", "Materiais", "Materiais"),
    (r"\bmanufacturing\b", "Manufatura", "Manufatura"),
    (r"\bproduction\b", "Produção", "Produção"),
    (r"\bquality\b", "Qualidade", "Qualidade"),
    (r"\btesting\b", "Testes", "Qualidade"),
    (r"\bstandards?\b", "Normas", "Qualidade"),
    (r"\banalytics\b", "Análise de Dados", "Dados"),
    (r"\banalysis\b", "Análise", "Dados"),
    (r"\bautomation\b", "Automação", "Automação"),
    (r"\br&d\b", "Pesquisa e Desenvolvimento (P&D)", "P&D"),
    (r"\bresearch\b", "Pesquisa", "P&D"),
    (r"\bdevelopment\b", "Desenvolvimento", "P&D"),
    (r"\bengineering\b", "Engenharia", "Engenharia"),
    (r"\bengineer\b", "Engenheiro(a)", "Engenharia"),
    (r"\bprocess\b", "Processo", "Processos"),
    (r"\bchemistry\b", "Química", "Química"),
    (r"\bchemicals?\b", "Produtos Químicos", "Química"),
    (r"\bpolymer\w*", "Polímeros", "Materiais"),
    (r"\bplastics?\b", "Plásticos", "Materiais"),
    (r"\bmetallurg\w*", "Metalurgia", "Materiais"),
    (r"\bcorrosion\w*", "Corrosão", "Materiais"),
    (r"\bcoatings?\b", "Revestimentos", "Materiais"),
    (r"\bsemiconductor\w*", "Semicondutores", "Semicondutores"),
    (r"\bbatter\w*", "Bateria", "Materiais"),
    (r"\blaborator\w*", "Laboratório", "Laboratório"),
    (r"\blaborant\w*", "Técnico(a) de Laboratório", "Laboratório"),
    (r"\bwelding\b", "Soldagem", "Manufatura"),
    (r"\blogistics\b", "Logística", "Logística"),
    (r"\bwarehouse\b", "Armazém", "Logística"),
    (r"\bfreight\b", "Frete/Carga", "Logística"),
    (r"\bmanagement\b", "Gestão", "Gestão"),
    (r"\bcontrolling\b", "Controladoria (Controlling)", "Finanças"),
    (r"\bfinance\b", "Finanças", "Finanças"),
    (r"\bfinancial\b", "Financeiro", "Finanças"),
    (r"\baccounting\b", "Contabilidade", "Finanças"),
    (r"\bsales\b", "Vendas", "Vendas"),
    (r"\bconsulting\b", "Consultoria", "Consultoria"),
    (r"\bdigitalization\b", "Digitalização", "Digitalização"),
    (r"\bdigital\b", "Digital", "Digitalização"),
    (r"\breporting\b", "Relatórios", "Dados"),
    (r"\boperations\b", "Operações", "Operações"),
    (r"\bai\b", "Inteligência Artificial (IA)", "IA"),
]

# Marcadores de genero/decoração que so poluem a traducao (o original os
# mantem). Removidos em QUALQUER posicao APENAS do campo PT-BR derivado.
_GENDER_DECOR_RE = re.compile(
    r"\s*\((?:f/m/d|m/f/d|m/w/d|w/m/d|w/m/x|m/f/x|w/m/div|m/w/div|d/w/m|"
    r"all genders|alle geschlechter)\)\s*", re.IGNORECASE
)

# Alternancia unica (ordem da lista = prioridade de casamento por posicao).
_MASTER_RE = re.compile(
    "|".join(f"({rx})" for rx, _f, _r in GLOSSARY),
    re.IGNORECASE,
)

# Palavras-ponte (baixissimo risco, alto retorno de legibilidade): traduzidas
# SOMENTE em minusculas (maiuscula pode ser sigla — "IN", "FOR"...) e SEMPRE
# apos a passada do glossario (frases como "im Bereich" ja foram consumidas).
# Aplicadas UNICAMENTE em lacunas ENTRE dois segmentos traduzidos — cabeca e
# cauda nao traduzidas permanecem intactas ("Direction for a New Business
# Segment" nao vira "Direction para..."). O lookbehind impede o gatilho apos
# '*'/'/'/'.' (sufixo generico alemao "*in", "Praktikant/in", "e.g. in").
# Continuam sendo traducao deterministica por regra local — nao um tradutor.
_BRIDGES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<![*/.])\bim\b"), "em"),
    (re.compile(r"(?<![*/.])\bin\b"), "em"),
    (re.compile(r"(?<![*/.])\bfor\b"), "para"),
    (re.compile(r"(?<![*/.])\bund\b"), "e"),
    (re.compile(r"(?<![*/.])\band\b"), "e"),
]

_GLUE = " · "  # separador entre segmentos traduzidos consecutivos

# Marcadores FORTES de idioma no TITULO (deterministicos, sem stopword list):
# um marcador alemao classico (tipo de vaga DE) decide o idioma na hora.
_DE_STRONG_MARKERS = re.compile(
    r"\b(praktikum|werkstudent|praktikant|abschlussarbeit|bachelorarbeit|"
    r"masterarbeit|hochschulpraktikum|pflichtpraktikum|datenanalyse|"
    r"logistik|einkauf|beschaffung|mitarbeit|bereich)\w*",
    re.IGNORECASE,
)
_EN_STRONG_MARKERS = re.compile(
    r"\b(working student|internship|intern\b|thesis|procurement|"
    r"supply chain|engineering|analytics|business intelligence|"
    r"automation|manufacturing|data science)\w*",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Funcoes publicas
# ---------------------------------------------------------------------------


def detect_language(title: str | None) -> str | None:
    """Idioma provavel do TITULO original: 'en' | 'de' | None.

    Regra conservadora e deterministica (sem stoplist): marcador DE forte no
    titulo -> 'de'; senao marcador EN forte -> 'en'; senao None (idioma
    indefinido ou ja PT). Usado apenas para ROTULAR o original
    ("Original (DE)"), nunca para filtrar/traduzir.
    """
    if not title:
        return None
    text = str(title)
    if _DE_STRONG_MARKERS.search(text):
        return "de"
    if _EN_STRONG_MARKERS.search(text):
        return "en"
    return None


def title_pt(title: str | None) -> str | None:
    """Traducao PT-BR segura e deterministica do titulo (glossario).

    Substitui cada termo do glossario pela ``frase_pt`` correspondente,
    preservando palavras desconhecidas e a pontuacao original. Frases
    "identidade" (``frase_pt=None``, nomes de produto/siglas) sao mantidas e
    PROTEgem o match de regras genericas. Segmentos traduzidos consecutivos
    sao separados por " · " (leitura); apos a passada, palavras-ponte
    lowercase (in/for/und/im/and) viram conectivos PT-BR.

    Retorna ``None`` quando o titulo nao contem NENHUM termo traduzivel —
    a interface entao nao mostra o campo PT-BR (regra Fase 5: nao inventar).
    A decoracao de genero (f/m/d etc.) e removida do campo derivado.
    """
    if not title:
        return None
    text = str(title).strip()
    if not text:
        return None

    def replace(m: re.Match) -> tuple[str, bool]:
        """(texto substituido, foi_traduzido) para um match do glossario."""
        for idx, (_rx, frase, _rot) in enumerate(GLOSSARY, 1):
            if m.group(idx) is not None:
                return (frase, True) if frase is not None else (m.group(0), False)
        return (m.group(0), False)  # inalcancavel

    parts: list[str] = []
    pos = 0
    prev_tx = False
    for m in _MASTER_RE.finditer(text):
        gap = text[pos:m.start()]
        tx, is_tx = replace(m)
        if (
            is_tx and prev_tx
            and gap and not gap.strip() and len(parts) > 0
        ):
            parts.append(_GLUE)  # espaco limpo entre dois segmentos traduzidos
        else:
            # Pontes so em lacunas ENTRE dois segmentos traduzidos — cabeca e
            # cauda nao traduzidas permanecem intactas ("Direction for a New
            # Business Segment" nao vira "Direction para..."); o lookbehind dos
            # _BRIDGES impede gatilho apos '*'/'/'/'.' ("Praktikant*in").
            if is_tx and prev_tx and gap:
                for rx, bridge in _BRIDGES:
                    gap = rx.sub(bridge, gap)
            parts.append(gap)
            if gap and not gap.endswith((" ", "-", "/", "(", "·")):
                parts.append(" ")
        parts.append(tx)
        prev_tx = is_tx
        pos = m.end()
    parts.append(text[pos:])

    out = "".join(parts)
    out = _GENDER_DECOR_RE.sub(" ", out)  # remove decor de genero (qquer posicao)
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.;:!?])", r"\1", out).strip()
    if not out or out == text.strip():
        return None  # nada mudou / so decoracao removida
    return out


def employment_type_pt(value) -> str:
    """Rotulo PT-BR do tipo de anuncio (campo real, nunca inventado).

    Valor desconhecido/None -> retorna o valor original (ou ''); a interface
    decide nao exibir quando nao ha dado confiavel.
    """
    if not value:
        return ""
    t = str(value).strip().upper()
    _map = {
        "FULL_TIME": "Período integral",
        "PART_TIME": "Meio período",
        "INTERN": "Estágio",
        "INTERNSHIP": "Estágio",
        "CONTRACT": "Contrato",
        "OTHER": "",
        "WORKING_STUDENT": "Working Student",
        "WERKSTUDENT": "Working Student",
    }
    pt = _map.get(t)
    if pt is None:
        return str(value).strip()
    if pt == "":
        return ""
    return pt


def modalidade_label(remote, employment_type) -> str | None:
    """Modalidade PT-BR derivada de campos REAIS (None = nao exibir).

    ``remote`` verdadeiro -> "Remoto"; senao, o ``employment_type`` conhecido
    vira rotulo PT. Nao infere modalidade ausente (regra Fase 5).
    """
    try:
        is_remote = bool(remote)
    except Exception:
        is_remote = False
    if is_remote:
        return "Remoto"
    return employment_type_pt(employment_type) or None


def country_label(iso: str | None) -> str | None:
    """Pais PT-BR a partir do ISO alpha-2 (None = ISO desconhecido)."""
    if not iso:
        return None
    iso = str(iso).strip().casefold()
    return _PT_COUNTRY.get(iso)


_PT_COUNTRY: dict[str, str] = {
    "de": "Alemanha", "at": "Áustria", "ch": "Suíça", "nl": "Países Baixos",
    "be": "Bélgica", "fr": "França", "it": "Itália", "es": "Espanha",
    "pt": "Portugal", "pl": "Polônia", "cz": "Tchéquia", "gb": "Reino Unido",
    "ie": "Irlanda", "us": "Estados Unidos", "ca": "Canadá", "br": "Brasil",
    "se": "Suécia", "no": "Noruega", "dk": "Dinamarca", "fi": "Finlândia",
    "lu": "Luxemburgo", "hu": "Hungria", "ro": "Romênia", "bg": "Bulgária",
    "hr": "Croácia", "si": "Eslovênia", "sk": "Eslováquia", "ee": "Estônia",
    "lv": "Letônia", "lt": "Lituânia", "gr": "Grécia", "tr": "Turquia",
}


# ---------------------------------------------------------------------------
# Explicacao do score ("Por que esta vaga?") — valores REAIS do breakdown.
# ---------------------------------------------------------------------------

# Rotulos PT-BR das componentes do score_breakdown (perfil principal).
BREAKDOWN_LABELS: dict[str, str] = {
    "area": "Área",
    "skills": "Skills",
    "language": "Idioma",
    "type": "Tipo",
    "location": "Local",
    "penalties": "Penalidades",
}
BREAKDOWN_ORDER = ("area", "skills", "language", "type", "location", "penalties")

# Rotulos PT-BR das componentes do materials_breakdown (perfil Materials).
MATERIALS_BREAKDOWN_LABELS: dict[str, str] = {
    "materials": "Materiais",
    "adjacent": "Manufatura/Processo",
    "context": "Qualidade/P&D/Lab",
    "type": "Tipo",
    "location": "Local",
    "penalties": "Penalidades",
}
MATERIALS_BREAKDOWN_ORDER = (
    "materials", "adjacent", "context", "type", "location", "penalties",
)

# Detalhe PT-BR por componente — o que aquela componente MEDE (texto fixo,
# correspondente as regras do ranking existente; sem inventar componente).
BREAKDOWN_EXPLAIN: dict[str, str] = {
    "area": "termos da área alvo (Procurement, Supply Chain, BI, Analytics, Automação)",
    "skills": "competências do perfil citadas na descrição",
    # Fase 6: alemão deixou de bonificar — a componente agora mede a EVIDÊNCIA
    # de inglês (+1.5) e a EXIGÊNCIA de alemão detectada no TEXTO do anúncio
    # (exigido −2.0 / preferido −0.5 / menção difusa neutra / sem menção neutra).
    "language": "inglês mencionado (+1,5); alemão: exigido (−2,0) ou preferido (−0,5) — exigência detectada no texto, nunca pelo idioma do anúncio",
    "type": "marcador forte de vaga de estudante no título",
    "location": "Alemanha explícita (DE) / Berlim",
    "penalties": "características que REDUZIRAM a relevância",
}
MATERIALS_BREAKDOWN_EXPLAIN: dict[str, str] = {
    "materials": "termos do núcleo de materiais no título (e, corroborando, na descrição)",
    "adjacent": "manufatura/produção e engenharia de processos",
    "context": "qualidade/P&D/laboratório — só com contexto técnico no título",
    "type": "marcador forte de vaga de estudante no título",
    "location": "Alemanha explícita (DE) / Berlim",
    "penalties": "função de negócio no título (compras/SCM, logística, vendas…)",
}


def relevance_signals(job: dict, *, profile: str = "biz") -> list[dict]:
    """Sinais de relevancia PT-BR a partir do breakdown REAL do perfil.

    Cada componente com valor != 0 vira um sinal
    ``{"key", "label", "detail", "value", "kind"}``, ordenado por |value|
    desc (mais forte primeiro). ``label``/``detail`` vem das tabelas fixas
    acima; ``value`` e o VALOR REAL do breakdown da vaga — nada e somado ou
    alterado. Com isso a "explicacao" nunca inventa numeros: cada linha
    corresponde a uma componente existente.
    """
    if profile == "biz":
        key_breakdown, labels, explains, order = (
            "score_breakdown", BREAKDOWN_LABELS, BREAKDOWN_EXPLAIN, BREAKDOWN_ORDER,
        )
    else:
        key_breakdown, labels, explains, order = (
            "materials_breakdown", MATERIALS_BREAKDOWN_LABELS,
            MATERIALS_BREAKDOWN_EXPLAIN, MATERIALS_BREAKDOWN_ORDER,
        )
    bd = job.get(key_breakdown)
    if not isinstance(bd, dict):
        return []
    out: list[dict] = []
    for key in order:
        try:
            v = float(bd[key])
        except (KeyError, TypeError, ValueError):
            continue
        if v == 0.0:
            continue
        out.append({
            "key": key,
            "label": labels.get(key, key),
            "detail": explains.get(key, ""),
            "value": v,
            "kind": "neg" if v < 0 else "pos",
        })
    out.sort(key=lambda s: (-abs(s["value"]), s["key"]))
    return out


def penalties(job: dict, *, profile: str = "biz") -> list[dict]:
    """Apenas as componentes NEGATIVAS (o que reduziu a nota), ou []."""
    return [s for s in relevance_signals(job, profile=profile) if s["kind"] == "neg"]


# ---------------------------------------------------------------------------
# Fase 6 — Application Intelligence (rotulos PT-BR das camadas de candidatura;
# os ESTADOS/KEYS vem de app_intel.py; aqui so a apresentacao em portugues)
# ---------------------------------------------------------------------------

# Estados de work authorization (app_intel.work_authorization).
WORK_AUTH_LABELS: dict[str, str] = {
    "support": "Suporte/patrocínio de visto mencionado",
    "existing_required": "Requer autorização de trabalho existente",
    "no_sponsorship": "Sem sponsorship (não patrocina visto)",
    "unclear": "Informação não clara",
    "not_mentioned": "Não mencionado",
}

# Niveis de exigencia de alemao (app_intel.german_level).
GERMAN_LEVEL_LABELS: dict[str, str] = {
    "required": "exigido",
    "preferred": "preferido",
    "plus": "mencionado (nível não informado)",
    "none": "",
}

# Tipos de deadline (app_intel.deadline_kind).
DEADLINE_KIND_LABELS: dict[str, str] = {
    "employer": "prazo de candidatura (informado na vaga)",
    "employer_textual": "prazo de candidatura declarado no texto do anúncio",
    "platform_sf": "validade do anúncio na fonte (feed da plataforma, +30 dias)",
    "none": "Not specified",
}

# Sinais de Candidate Fit (app_intel.candidate_fit; ``key`` -> rotulo).
FIT_LABELS: dict[str, str] = {
    "germany": "Alemanha",
    "student_type": "Vaga de estudante",
    "english": "Inglês mencionado",
    "location_known": "Localização informada",
    "description_known": "Descrição disponível",
    "german": "Alemão",
    "work_auth": "Autorização de trabalho",
}

# Problemas possiveis (app_intel.possible_problems): template por key.
# ``{arg}`` e preenchido com o detalhe real (ex.: a data do deadline).
PROBLEM_TEXTS: dict[str, str] = {
    "german_required": "Alemão exigido no anúncio (penalidade no score)",
    "german_preferred": "Alemão preferencial (não obrigatório)",
    "wa_existing": "Requer autorização de trabalho já existente",
    "wa_no_sponsorship": "Empresa não patrocina visto",
    "wa_unclear": "Autorização de trabalho não clara no anúncio",
    "deadline": "Candidaturas até {arg}",
    "sf_validity_passed": "Validade do anúncio na fonte já venceu: {arg}",
    "senior_title": "Título sugere senioridade acima do nível de estágio",
}

# Quality flags (app_intel.quality_flags): template por key.
QUALITY_TEXTS: dict[str, str] = {
    "no_deadline": "Sem deadline informado",
    "platform_validity": (
        "A 'data limite' é validade do feed da plataforma (fonte), "
        "não um prazo de candidatura do empregador"
    ),
    "deadline_textual": (
        "Prazo de candidatura declarado no texto do anúncio "
        "(Bewerbungsfrist) — evidência do empregador, extraída do texto"
    ),
    "no_location": "Localização ausente",
    "short_description": "Descrição ausente ou muito curta ({arg} caracteres)",
    "no_language": "Sem menção a idioma no anúncio",
    "old_posting": "Publicação antiga ({arg} dias)",
}

# Application readiness (app_intel.application_readiness).
READINESS_LABELS: dict[str, str] = {
    "ready": "Pronta para revisar",
    "verify": "Precisa verificação",
}

# ---------------------------------------------------------------------------
# Fase 7 — Opportunity Intelligence (rotulos PT-BR; estados/keys vem de
# opportunity_intel.py; aqui so a apresentacao em portugues)
# ---------------------------------------------------------------------------

# Modalidade de trabalho (opportunity_intel.work_mode).
WORK_MODE_LABELS: dict[str, str] = {
    "remote": "Remoto",
    "hybrid": "Híbrido",
    "on_site": "Presencial",
    "not_mentioned": "Não mencionado",
}

# Estados do caminho Internship -> Full-time (opportunity_intel.pathway_state).
PATHWAY_LABELS: dict[str, str] = {
    "explicitly_supported": "Explicitly supported",
    "evidence_available": "Evidence available",
    "not_mentioned": "Not mentioned",
    "unknown": "Unknown",
}

# Politica de visto/autorizacao da EMPRESA (opportunity_intel.visa_policy_state,
# item 11 da auditoria pos-Fases 1-8). Curada com fonte oficial; distinta do
# work_authorization da VAGA (detector textual do anuncio).
VISA_POLICY_LABELS: dict[str, str] = {
    "explicit_support": "Suporte explícito ao processo de visto (fonte oficial)",
    "explicit_no_support": "Sem patrocínio de visto (fonte oficial)",
    "candidate_must_have_authorization": "Candidato deve ter autorização própria",
    "unclear": "Política condicional/não clara (fonte oficial)",
    "not_verified": "Não verificado",
}

# Qualidade da fonte (opportunity_intel.SOURCE_QUALITIES).
SOURCE_QUALITY_LABELS: dict[str, str] = {
    "primary": "Primary (fonte oficial)",
    "secondary": "Secondary (fonte pública confiável)",
    "aggregated": "Aggregated (dados agregados de terceiros)",
    "unknown": "Unknown (fonte insuficiente)",
}

# Periodo de salario (opportunity_intel.job_salary).
SALARY_PERIOD_LABELS: dict[str, str] = {
    "month": "mês",
    "year": "ano",
}

# Rotulos dos fatores de comparacao (funcionalidade Compare opportunities).
COMPARE_FACTOR_LABELS: dict[str, str] = {
    "fit": "Job Fit (score)",
    "ready": "Candidate Fit (readiness)",
    "language": "Idioma",
    "wa": "Work authorization",
    "deadline": "Deadline",
    "role": "Vaga",
    "salary": "Salário",
    "mode": "Work mode",
    "duration": "Duração",
    "benefits": "Benefícios (empresa)",
    "career": "Desenvolvimento de carreira",
    "pathway": "Internship → Full-time",
    "city": "Cidade",
    "cost": "Custo de vida",
    "transport": "Transporte",
}