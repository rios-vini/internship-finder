"""Digest do ranking para o Telegram (Fase 2 do plano de evolucao).

Transforma a mensagem diaria em um resumo util SEM virar segunda interface:
o ranking completo continua no GitHub Pages (link estavel da Fase 1); o
Telegram mostra perfil/criterios ativos, novas vagas no Top 30, Top 5 atual,
mudancas relevantes no ranking e o link.

Principios (escopo Fase 2, "comunicacao/monitoramento"):

- **Nenhuma regra de ranking e duplicada aqui**: os pesos/sinais do perfil
  sao LIDOS das constantes de ``src/internship_finder/ranking.py`` e os
  marcadores de tipo/area de ``src/internship_finder/filters.py`` em tempo de
  execucao — se o ranking mudar, o digest reflete sozinho (teste invariante:
  test_digest compara a saida com as constantes vivas). A unica coisa fixa
  aqui e VOCABULARIO DE EXIBICAO (rotulo humano de padrao regex -> nome
  curto). Padrao novo sem rotulo aparece como "outro termo", nunca mentira.
- **Estado anterior = o proprio archive da rotacao** (``data/archive/<ts>/``,
  de ``refresh_daily.rotate``): a rotacao copia ``eligible_jobs.json`` do run
  anterior ANTES da coleta sobrescrever ``data/``. O digest compara o ranking
  do run (``data/eligible_jobs.json``) contra esse snapshot — zero arquivo
  novo, zero banco novo, zero infra (prioridade 1 do enunciado: reutilizar
  estado que ja existe).
- **"Nova vaga" != "vaga que subiu"**: nova = id AUSENTE do ranking elegivel
  anterior (nao existia no snapshot). Vaga antiga que entrou no Top 30 vai
  para "Mudancas no ranking" (entrou), nunca para "Novas vagas".
- **Best-effort**: digest nunca derruba o run (chamador envolve em
  try/except) e so e montado para coleta VALIDA (exit 0) — mesmo gate da
  publicacao do GitHub Pages (nunca apresenta ranking parcial como oficial).

Uso (so o refresh_daily chama; nada de CLI propria):

    sections = ranking_digest.digest_sections(
        current_path=data_dir / "eligible_jobs.json",
        previous_path=archive_dir / "eligible_jobs.json",   # snapshot da rotacao
        pages_url=ranking_digest.resolve_pages_url(root),
    )
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from internship_finder import filters
from internship_finder import ranking as ranking_mod
from internship_finder.enrichment import present as enr_present
from internship_finder.materials_ranking import rank_materials_jobs

# ---------------------------------------------------------------------------
# Limites do digest (exibicao; NAO sao regras de ranking)
# ---------------------------------------------------------------------------

# Faixa "Top 30" do ranking (mesmo conceito do enunciado da Fase 2).
DIGEST_TOP = 30
# Top 5 exibido no resumo diario.
DIGEST_TOP5 = 5
# Variacao minima de posicao (em posicoes) para contar como "movimento
# relevante" entre runs (evita ruido de troca +/-1).
MOVER_MIN_DELTA = 5
# Maximo de movimentos listados (mensagem compacta).
MOVER_MAX_SHOWN = 5
# Teto defensivo de novas vagas listadas (Telegram tem limite de 4096 chars).
NEW_MAX_SHOWN = 15
# Fase 4: Tetos da secao do perfil Materials (compacta — mesma mensagem).
MATERIALS_TOP5 = 5
MATERIALS_NEW_MAX = 5
# F36: tetos da seção do perfil EU non-DE (mesmo formato compacto).
EU_TOP5 = 5
EU_NEW_MAX = 5

# F36.1 — headers das seções de perfil 🧪/🇪🇺 do digest. O compactador do
# Telegram (refresh_daily.build_message) extrai essas seções para que os
# headers sobrevivam ao encurtamento >4096 (padrão F13: o PREFIXO é o
# contrato de reconhecimento — o sufixo pode evoluir sem quebrar o
# compactador). Antes do fix elas nem eram candidatas: a reconstrução por
# prioridade as dropava inteiras (🧪 não aparecia no digest compactado
# desde 28/09; 🇪🇺 estreou invisível no compacto).
MATERIALS_SECTION_PREFIX = "🧪 Perfil Materials Engineering"
EU_SECTION_PREFIX = "🇪🇺 Perfil EU non-DE"

# Fase 3 (enrichment): tetos da secao de dados da pagina oficial.
ENRICH_TOP5 = 5

# F6: Top 5 diário com apply_url no digest. Teto de truncagem por linha
# (títulos longos não estouram o limite de 4096 do Telegram).
# F12.5: a URL NUNCA é truncada — elipse DENTRO do link quebra o acesso
# (bug real do Telegram de 05/10: 4 das 5 URLs do Top 5 com 404 ao
# clicar). O comprimento da mensagem continua garantido pela truncagem
# por LINHAS INTEIRAS (``max_len`` + aviso "(+N na página)"): linha a
# mais sai inteira, link nunca cortado ao meio. Título/empresa seguem
# clipados (não são clicáveis).
TOP5_TITLE_LIMIT = 48

# F6.1 — header da secao ⚡ do digest. O compactador do Telegram
# (refresh_daily.build_message) extrai essa secao para preserva-la no
# encurtamento; o PREFIXO e o contrato de reconhecimento (o sufixo pode
# evoluir sem quebrar o compactador).
TOP5_SECTION_PREFIX = "⚡ Top 5 do dia"
TOP5_SECTION_HEADER = f"{TOP5_SECTION_PREFIX} (candidatura direta)"

# F7: bandeira por país no Top 5 (canal secundário LU/NL/FI/BE visível no
# Telegram; DE = vazio — default visual, 0 chars no caso dominante).
_TOP5_FLAGS = {"lu": "🇱🇺 ", "nl": "🇳🇱 ", "fi": "🇫🇮 ", "be": "🇧🇪 "}

# F29 — countdown do visto §16e no digest (item 6: 1 linha estática ANTES
# do top-5). A DATA é DERIVADA DE CONSTANTES (alvo jan/2027 + lead de visto
# de 6–8 semanas após a oferta, pesquisa 12/10), nunca hardcoded no texto:
# mudar o alvo aqui muda a linha em todo lugar (o teste trava a derivação).
#   VISA_TARGET_START: mês de início pretendido do estágio;
#   VISA_LEAD_DAYS: dias de lead entre oferta e início (visto + mudança).
VISA_TARGET_START = (2027, 1, 1)   # alvo: início do estágio em jan/2027
VISA_LEAD_DAYS = 47                # ~6,5 semanas (meio da faixa 6–8 sem)
VISA_COUNTDOWN_PREFIX = "📅 Visto §16e:"


def visa_countdown_line() -> str:
    """F29 item 6: linha estática do countdown do visto para o digest.

    '📅 Visto §16e: oferta necessária até ~15/11/2026 p/ início jan/2027'
    — a data-limite = início alvo menos o lead de visto (constantes
    acima; o texto NÃO carrega data hardcoded). Pura e offline.
    """
    from datetime import date, timedelta
    start = date(*VISA_TARGET_START)
    deadline = start - timedelta(days=VISA_LEAD_DAYS)
    month_names = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
                   7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}
    target_txt = f"{month_names[start.month]}/{start.year}"
    return (f"{VISA_COUNTDOWN_PREFIX} oferta necessária até "
            f"~{deadline.strftime('%d/%m/%Y')} p/ início {target_txt}")

# Spec de pais do filtro (espelha o default de ``cli.py --country``; o teste
# test_digest confere os dois — se o CLI mudar o default, o teste falha).
DEFAULT_COUNTRY_SPEC = "de"

# Rotulo humano por spec (vocabulario de exibicao, nao regra de filtro).
COUNTRY_DISPLAY: dict[str, str] = {
    "de": "Germany",
    "europe": "Europa",
    "remote": "Remoto",
    "all": "Todos os paises",
}

# Fallback da URL estavel do ranking publico (Fase 1). Em producao a URL e
# derivada do remote do repo (mesma fonte do clone de deploy); este valor so
# serve quando o remote nao esta disponivel.
PAGES_URL_FALLBACK = "https://rios-vini.github.io/internship-finder/"


# ---------------------------------------------------------------------------
# Rotulos de exibicao dos padroes de area (filters.AREA_PRIMARY). Chave = o
# literal EXATO do padrao no modulo; valor = rotulo CURTO canonico (variantes
# do mesmo conceito agrupam num rotulo so — o digest fica compacto). Padrao
# novo sem rotulo cai no "outro termo" (ver _area_labels).
# ---------------------------------------------------------------------------
_AREA_PRIMARY_LABELS: dict[str, str] = {
    r"\bsupply[ -]?chain\b": "Supply Chain",
    r"\bprocurement\b": "Procurement/Purchasing",
    r"\bpurchasing\b": "Procurement/Purchasing",
    r"\bpurchase\b": "Procurement/Purchasing",
    r"\beinkauf": "Procurement/Purchasing",
    r"\bbeschaffung": "Procurement/Purchasing",
    r"\bcompras\b": "Procurement/Purchasing",
    r"\bsuprimentos\b": "Procurement/Purchasing",
    r"\bbusiness intelligence\b": "BI",
    r"\bbi\b": "BI",
    r"\bdata[ &]+analytics\b": "Analytics",
    r"\banalytics\b": "Analytics",
    r"\bprocess automation\b": "Automação de Processos (RPA)",
    r"\bprocess excellence\b": "Automação de Processos (RPA)",
    r"\brpa\b": "Automação de Processos (RPA)",
    r"\brobotic process automation\b": "Automação de Processos (RPA)",
}

# Tipos de vaga aceitos (vocabulario fixo; a LISTA ativa vive em
# filters.STUDENT_TYPE_PATTERNS — o digest mostra a contagem viva).
_TYPE_ACCEPTED_DISPLAY = (
    "Internship/Intern · Working Student/Werkstudent · Praktikum · iXp · "
    "teses (Abschlussarbeit/Bachelor-/Masterarbeit)"
)

# Exclusoes de tipo (vocabulario fixo; contagem viva de
# filters.TYPE_EXCLUSION_PATTERNS + PROGRAM_EXCLUSION_PATTERNS).
_TYPE_EXCLUDED_DISPLAY = (
    "Duales Studium, Ausbildung/Apprentice, estagios escolares, "
    "Graduate/JMP, graduacao no titulo (Bachelor of ...)"
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _fmt(n: int) -> str:
    """Numero no formato pt-BR (37.373), legivel no Telegram."""
    return f"{n:,}".replace(",", ".")


def _score_text(score) -> str:
    """Score sem zeros desnecessarios (14.75, 17.5, 6)."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "—"
    return f"{value:g}"


def _short_location(job: dict) -> str:
    """Localizacao compacta: primeiro segmento da vaga (cidade/regiao)."""
    location = job.get("location") or ""
    if not location:
        return "—"
    first = str(location).split(",", 1)[0].strip()
    return first[:40] if first else "—"


def _short_title(job: dict, limit: int = 60) -> str:
    """Titulo truncado para a mensagem ficar compacta (Telegram 4096)."""
    title = str(job.get("title") or "").strip() or "sem título"
    return title if len(title) <= limit else title[: limit - 1] + "…"


def _sort_key(job: dict) -> tuple:
    """Chave de ordenacao oficial do ranking (score desc + desempate)."""
    return (
        -float(job.get("score") or 0.0),
        str(job.get("title") or "").casefold(),
        str(job.get("company") or "").casefold(),
        str(job.get("id") or ""),
    )


# ---------------------------------------------------------------------------
# Leitura do ranking (defensiva — digest nunca derruba o run)
# ---------------------------------------------------------------------------

def load_ranking(path: str | Path) -> list[dict]:
    """Ranking do run (lista ordenada de dicts); ``[]`` em qualquer falha.

    Ausencia, JSON malformado ou lista vazia sao todos ``[]`` — o digest
    trata como "sem estado disponivel" e segue (best-effort).
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [j for j in data if isinstance(j, dict) and j.get("id")]


def top_positions(
    ranking: list[dict], n: int = DIGEST_TOP,
) -> list[tuple[int, dict]]:
    """Os primeiros ``n`` do ranking com posicao 1-based.

    A ordem do arquivo e a ordem oficial do ranking (score desc, desempate
    deterministico — o run grava ja ordenado). ``top_positions`` apenas
    enumera; nao reordena.
    """
    return list(enumerate(ranking[:n], start=1))


# ---------------------------------------------------------------------------
# Comparacao com o estado anterior (snapshot da rotacao)
# ---------------------------------------------------------------------------

def _ids(ranking: list[dict]) -> set[str]:
    return {j.get("id") for j in ranking if j.get("id")}


def load_ranking_or_none(path: str | Path) -> list[dict] | None:
    """Ranking do snapshot anterior; ``None`` = arquivo INACEITAVEL (F11).

    Distingue (o ``load_ranking`` best-effort nao distingue): lista vazia
    VALIDA -> ``[]`` (snapshot existe e o run anterior nao tinha vagas — o
    diff e legitimo e diz "tudo e novo"); arquivo AUSENTE/corrompido/nao-
    lista -> ``None`` (sem estado anterior; o chamador NAO monta secao de
    diff — nunca trata o dataset inteiro como "novo de ontem").
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    return [j for j in data if isinstance(j, dict) and j.get("id")]


def new_since_previous(
    current: list[dict],
    previous: list[dict] | None,
) -> tuple[set[str], set[str]] | None:
    """Diff de IDs do dia vs o snapshot anterior (F11 Tarefa 1; pura).

    Devolve ``(new_ids, gone_ids)`` — ids presentes hoje e ausentes ontem
    ("novas de ontem") e vice-versa ("sumiram"). ``previous=None`` (sem
    snapshot usavel) -> ``None``: o chamador omite a secao, sem erro. Um
    snapshot anterior VALIDO e vazio (``[]``) e um estado real (primeiro
    run com dataset vazio): devolve todos os ids atuais como novos.

    O diff e de EXIBICAO: nada e escrito em data/; ids de jobs
    ``sf_dataset:*``/``direct:*`` nunca passaram pelo SQLite e o
    ``first_seen`` NAO os cobre — por isso o diff e de IDs contra o
    snapshot arquivado, nao contra o banco.
    """
    if previous is None:
        return None
    cur_ids = _ids(current)
    prev_ids = _ids(previous)
    return (cur_ids - prev_ids, prev_ids - cur_ids)


def new_top_entries(
    current: list[dict],
    previous: list[dict],
    top: int = DIGEST_TOP,
) -> list[tuple[int, dict]]:
    """Vagas NOVAS no Top 30: id ausente do ranking elegivel anterior.

    O conceito central da Fase 2 ([enunciado]): "nova vaga" = nao existia na
    execucao anterior. Vaga antiga que subiu para o Top 30 NAO entra aqui
    (entra em ``ranking_changes`` -> 'entrou'): sem snapshot, todo o Top 30
    seria "novo" e o alerta perderia o significado.
    """
    previous_ids = _ids(previous)
    return [
        (pos, job)
        for pos, job in top_positions(current, top)
        if job.get("id") not in previous_ids
    ]


def ranking_changes(
    current: list[dict],
    previous: list[dict],
    top: int = DIGEST_TOP,
    min_delta: int = MOVER_MIN_DELTA,
    max_movers: int = MOVER_MAX_SHOWN,
) -> dict:
    """Mudancas no Top 30 entre runs.

    Devolve::

        {
          "entered": [(pos_atual, job), ...],   # no Top 30 atual, nao no anterior
          "exited":  [(pos_anterior, job), ...],# no Top 30 anterior, nao no atual
          "movers":  [(job, pos_prev, pos_cur), ...],  # |delta| >= min_delta
        }

    ``entered`` inclui vagas NOVAS (o chamador cruza com ``new_top_entries``
    para separar "novas" de "subiram"). ``movers``: |delta| desc, ate
    ``max_movers``; delta = pos_prev - pos_cur (>0 subiu).
    """
    cur_by_id = {job["id"]: (pos, job) for pos, job in top_positions(current, top)}
    prev_by_id = {job["id"]: (pos, job) for pos, job in top_positions(previous, top)}
    cur_ids = set(cur_by_id)
    prev_ids = set(prev_by_id)

    entered = [cur_by_id[jid] for jid in sorted(
        cur_ids - prev_ids, key=lambda jid: cur_by_id[jid][0])]
    exited = [prev_by_id[jid] for jid in sorted(
        prev_ids - cur_ids, key=lambda jid: prev_by_id[jid][0])]

    movers: list[tuple[dict, int, int]] = []
    for jid in sorted(prev_ids & cur_ids):  # ordenado: determinismo com empate
        prev_pos, _prev_job = prev_by_id[jid]
        cur_pos, cur_job = cur_by_id[jid]
        if abs(cur_pos - prev_pos) >= min_delta:
            movers.append((cur_job, prev_pos, cur_pos))
    movers.sort(key=lambda m: -abs(m[2] - m[1]))
    return {
        "entered": entered,
        "exited": exited,
        "movers": movers[:max_movers],
    }


def score_stats(ranking: list[dict]) -> dict | None:
    """min/mediana/max dos scores do ranking; None sem scores validos."""
    scores = [
        float(j["score"]) for j in ranking
        if isinstance(j.get("score"), (int, float))
    ]
    if not scores:
        return None
    ordered = sorted(scores)
    mid = len(ordered) // 2
    median = (
        ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    )
    return {
        "min": ordered[0],
        "median": median,
        "max": ordered[-1],
        "count": len(ordered),
    }


# ---------------------------------------------------------------------------
# Perfil e criterios ativos (lidos das constantes vivas — nunca duplicados)
# ---------------------------------------------------------------------------

def _area_labels() -> list[str]:
    """Rotulos das areas primarias ativas (ordem do modulo, sem duplicar)."""
    labels: list[str] = []
    for pattern in filters.AREA_PRIMARY:
        label = _AREA_PRIMARY_LABELS.get(pattern, "outro termo")
        if label not in labels:
            labels.append(label)
    return labels


def _signal_lines() -> list[str]:
    """Principais sinais com os PESOS VIVOS de ``ranking.py``.

    Renderiza as constantes de peso diretamente: se o ranking mudar pesos,
    esta linha muda junto (sem copiar a regra). Sinais com peso 0 sao
    omitidos (ex.: area da descricao calibrada em 0.0).
    """
    rows = [
        ("área no título", ranking_mod.WEIGHT_AREA_TITLE),
        ("competências na descrição (por termo)", ranking_mod.WEIGHT_SKILL),
        ("inglês (evidência no anúncio)", ranking_mod.WEIGHT_LANG_EN),
        ("tipo de vaga no título", ranking_mod.WEIGHT_TYPE_TITLE),
        ("localização DE", ranking_mod.WEIGHT_DE_EXPLICIT),
        ("Berlin", ranking_mod.WEIGHT_DE_CAPITAL),
    ]
    parts = [
        f"{label} (+{weight:g})"
        for label, weight in rows
        if weight > 0
    ]
    penalties = [
        ("senioridade", ranking_mod.PENALTY_SENIOR),
        ("manager", ranking_mod.PENALTY_MANAGER),
        ("full-time", ranking_mod.PENALTY_FULL_TIME),
        # Fase 6: alemão deixou de bonificar menção — as penalidades refletem
        # a EXIGÊNCIA detectada por app_intel.german_level no texto do anúncio
        # (required -> PENALTY_LANG_DE_REQUIRED; preferred -> PREFERRED; plus/sem
        # menção -> neutro; o idioma em que o anúncio foi escrito nunca é requisito).
        ("alemão exigido", ranking_mod.PENALTY_LANG_DE_REQUIRED),
        ("alemão preferido", ranking_mod.PENALTY_LANG_DE_PREFERRED),
    ]
    penalty_parts = [
        f"{label} ({weight:g})"
        for label, weight in penalties
        if weight != 0
    ]
    text = " · ".join(parts)
    if penalty_parts:
        text += " · penalidades: " + ", ".join(penalty_parts)
    return [f"Sinais no score: {text}"]


def profile_lines(country_spec: str = DEFAULT_COUNTRY_SPEC) -> list[str]:
    """Secao 'Perfil e criterios ativos' (compacta, sem regras duplicadas)."""
    areas = " · ".join(_area_labels())
    country = COUNTRY_DISPLAY.get(country_spec, f"spec {country_spec!r}")
    n_types = len(filters.STUDENT_TYPE_PATTERNS)
    n_excl = (
        len(filters.TYPE_EXCLUSION_PATTERNS)
        + len(filters.PROGRAM_EXCLUSION_PATTERNS)
    )
    lines = ["🎯 Perfil e critérios ativos"]
    lines.append(f"Áreas: {areas}")
    lines.append(f"Localização principal: {country} (spec {country_spec!r})")
    lines.append(
        f"Tipo: {_TYPE_ACCEPTED_DISPLAY} — {n_types} marcadores ativos; "
        f"excluídos: {_TYPE_EXCLUDED_DISPLAY} ({n_excl} padrões)"
    )
    lines.extend(_signal_lines())
    # Fase 4: o mesmo conjunto elegivel tambem tem o perfil secundario
    # (mesmas vagas, score proprio — secoes abaixo).
    lines.append(
        "Perfil secundário (ranking próprio, mesmas vagas elegíveis): "
        "Materials Engineering — materiais/metalurgia/polímeros/cerâmicas/"
        "metais/superfície/corrosão/ensaios + manufatura/processo"
    )
    return lines


# ---------------------------------------------------------------------------
# URL estavel do ranking completo (GitHub Pages, Fase 1)
# ---------------------------------------------------------------------------

def pages_url(origin_url: str | None) -> str:
    """URL estavel a partir do remote (``owner/repo`` -> Pages de projeto).

    Mesma fonte do clone de deploy de ``publish_pages`` (remote do repo).
    Aceita https e ssh (``git@``). Sem remote reconhecivel -> fallback.
    """
    if origin_url:
        match = re.search(
            r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$", origin_url
        )
        if match:
            owner, repo = match.group(1), match.group(2)
            return f"https://{owner}.github.io/{repo}/"
    return PAGES_URL_FALLBACK


def resolve_pages_url(root: str | Path) -> str:
    """URL estavel lendo ``remote.origin.url`` do repo (fallback na falha)."""
    try:
        proc = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(root), capture_output=True, text=True, timeout=15,
        )
        origin = proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        origin = ""
    return pages_url(origin or None)


# ---------------------------------------------------------------------------
# Montagem do digest completo
# ---------------------------------------------------------------------------

def _job_entry(pos: int, job: dict) -> list[str]:
    """Linha compatta de uma vaga: posicao, titulo, empresa, local, score,
    link (formato proposto no enunciado: ``#3 — titulo — empresa — local —
    score`` + link)."""
    url = job.get("url")
    return [
        f"#{pos} — {_short_title(job)} — "
        f"{job.get('company') or '—'} — {_short_location(job)} — "
        f"{_score_text(job.get('score'))}",
    ] + ([url] if url else [])


def _novas_section(
    novas: list[tuple[int, dict]], country_spec: str,
) -> list[str]:
    lines = ["🆕 Novas vagas no Top 30"]
    if not novas:
        lines.append("— nenhuma vaga nova no Top 30")
        return lines
    for pos, job in novas[:NEW_MAX_SHOWN]:
        lines.extend(_job_entry(pos, job))
    if len(novas) > NEW_MAX_SHOWN:
        lines.append(f"(+{len(novas) - NEW_MAX_SHOWN} outras novas — ver ranking)")
    return lines


def _top5_section(current: list[dict],
                  excluded_ids: set[str] | None = None) -> list[str]:
    """🏆 Top 5 atual (seção resumo do digest).

    F25: ``excluded_ids`` = ids demovidos das superfícies exibidas
    (mesma semântica F20 da página — mortas/inaplicáveis descem do top
    e a vaga seguinte sobe). Default ``None`` = sem exclusões (regressão
    zero para chamadores legados).
    """
    lines = ["🏆 Top 5 atual"]
    if not current:
        return lines + ["— ranking vazio"]
    excluded = {str(i) for i in (excluded_ids or set())}
    shown = ([j for j in current
              if str(j.get("id") or "") not in excluded]
             if excluded else current)
    if not shown:
        return lines + ["— todas as vagas do topo foram demovidas (ver ranking)"]
    for pos, job in top_positions(shown, DIGEST_TOP5):
        lines.append(
            f"{pos}. {_short_title(job)} — "
            f"{job.get('company') or '—'} ({_score_text(job.get('score'))})"
        )
    return lines


# ---------------------------------------------------------------------------
# F6 — Top 5 diário com apply_url (função pura, offline-testável)
# ---------------------------------------------------------------------------

def _apply_url_of(job: dict) -> str | None:
    """URL de candidatura da vaga: raw.apply_url (http/https) com fallback
    para job.url — a MESMA prioridade da página (Fase B/F6)."""
    raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}
    for candidate in (raw.get("apply_url"), job.get("url")):
        if not candidate:
            continue
        text = str(candidate).strip()
        try:
            scheme = urlsplit(text).scheme
        except ValueError:
            continue
        if scheme.casefold() in ("http", "https"):
            return text
    return None


def _clip(text: str, limit: int) -> str:
    """Corta no limite com elipse; strings curtas intactas."""
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_top5(jobs: list[dict], *, max_len: int | None = None,
                quality_map: dict[str, dict] | None = None,
                excluded_ids: set[str] | None = None) -> str:
    """Top-5 do dia em 1 linha compacta por vaga (F6; função PURA).

    Formato por linha (spec §3.4): ``N. título — empresa — score —
    apply_url``. Regras:

    - ``0 vagas`` -> mensagem graciosa ("nenhuma vaga elegível hoje");
    - lista maior que 5 -> só as 5 primeiras (ordem oficial do ranking);
    - cada título cortado em ``TOP5_TITLE_LIMIT`` chars; a URL sai
      INTEIRA (F12.5 — link cortado ao meio é link quebrado);
    - ``max_len`` (default: limite do Telegram) -> truncagem SEGURA no
      limite de mensagem, cortando linhas inteiras (nunca no meio de uma
      linha) e avisando quantas ficaram de fora.

    F15: ``quality_map`` = mapa normalizado de employer_quality (default
    ``None`` = saída byte a byte a pré-F15). Empresa mapeada (com score
    Kununu OU prêmio GPTW — entrada "unavailable" não conta) ganha um ⭐
    DEPOIS do nome (2 chars; o corte de 24 do nome continua valendo
    ANTES do marcador — linha inteira segue sendo a unidade do
    format_top5, nunca link cortado). Empresa sem entrada = linha
    idêntica a hoje (regressão zero).

    F25: ``excluded_ids`` = ids demovidos das superfícies exibidas
    (liveness mortas + inaplicáveis pós-hidratação, incluindo o backlog
    da F25). MESMA semântica da página F20: descem do Top 5 e a vaga
    seguinte sobe — ficam no JSON. Default ``None`` = sem exclusões
    (comportamento pré-F25, regressão zero para chamadores legados).
    """
    if max_len is None:
        from refresh_daily import TELEGRAM_MAX_LEN  # lazy (evita ciclo de import)
        max_len = TELEGRAM_MAX_LEN
    if not jobs:
        return "🙂 Nenhuma vaga elegível hoje — ranking vazio."
    # F25 — corte ANTES da enumeração: as demovidas saem do Top 5 e a
    # vaga seguinte sobe (mesma mecânica do `alive` da página F20).
    excluded = {str(i) for i in (excluded_ids or set())}
    if excluded:
        jobs = [j for j in jobs
                if str(j.get("id") or "") not in excluded]
    if not jobs:
        return "🙂 Nenhuma vaga elegível hoje após exclusões do topo (ver ranking)."
    # F15 — lookup exato por empresa (match _norm; silêncio gracioso).
    # Mapeada = entrada COM score OU prêmio (spec §3: "quando mapeada";
    # entrada "unavailable" não tem sinal para oferecer — sem ⭐).
    starred: set[str] = set()
    if quality_map:
        try:
            from internship_finder import employer_quality
            from internship_finder.opportunity_intel import _norm
            for job in jobs[:DIGEST_TOP5]:
                entry = quality_map.get(
                    _norm(str(job.get("company") or "")))
                if (employer_quality._score_of(entry) is not None
                        or employer_quality.has_gptw(entry)):
                    starred.add(str(job.get("id") or ""))
        except Exception:  # noqa: BLE001 — marcador é best-effort
            starred = set()
    lines: list[str] = []
    for pos, job in enumerate(list(jobs)[:DIGEST_TOP5], 1):
        url = _apply_url_of(job) or "—"
        # F7: bandeira do pais (1-2 chars) quando a vaga NAO e DE — destaca
        # o canal secundario LU/NL/FI/BE sem quebrar o formato da linha.
        iso = str(job.get("country_iso") or "").strip().lower()
        flag = _TOP5_FLAGS.get(iso, "")
        # F15: ⭐ após o nome da empresa quando o mapa de qualidade a
        # registra com score >= 4,0 OU prêmio GPTW (sinal INFORMATIVO —
        # o ranking não muda). Sem mapa/sem entrada = sem marcador.
        star = "⭐" if quality_map and str(job.get("id") or "") in starred else ""
        lines.append(
            f"{pos}. {flag}{_clip(job.get('title'), TOP5_TITLE_LIMIT)} — "
            f"{_clip(job.get('company'), 24)}{star} — "
            f"{_score_text(job.get('score'))} — "
            f"{url}"  # F12.5: URL inteira, NUNCA clipada (link quebrado = 404)
        )
    text = "\n".join(lines)
    if len(text) > max_len:
        # Truncagem segura: mantém linhas inteiras que caibam e avisa.
        kept: list[str] = []
        used = 0
        notice = f"(+{len(lines) - 1} na página)"
        for line in lines:
            budget = max_len - len(notice) - 1
            if used + len(line) + 1 > budget:
                break
            kept.append(line)
            used += len(line) + 1
        if not kept:
            return notice
        kept.append(f"(+{len(lines) - len(kept)} na página)")
        text = "\n".join(kept)
    return text


def top5_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a secao ⚡ (header + linhas seguintes) de ``digest_lines`` (F6.1).

    O compactador do Telegram (``refresh_daily.build_message``) recebe o
    digest ja montado como lista de linhas e precisa preservar o Top 5 do
    dia mesmo quando a mensagem estoura 4096 chars. Esta funcao devolve a
    secao inteira — header + corpo ate a proxima linha em branco (as secoes
    do ``digest_sections`` sao sempre separadas por uma linha em branco) —
    ou ``[]`` quando a secao nao existe (digest vazio/None, ranking vazio,
    falha best-effort na montagem). Somente leitura; nunca lanca.
    """
    header_idx = None
    for idx, line in enumerate(digest_lines):
        if line.startswith(TOP5_SECTION_PREFIX):
            header_idx = idx
            break
    if header_idx is None:
        return []
    section = [digest_lines[header_idx]]
    for line in digest_lines[header_idx + 1:]:
        if not line.strip():
            break
        section.append(line)
    return section


def _changes_section(
    changes: dict,
    new_ids: set[str],
) -> list[str]:
    lines = ["📈 Mudanças no ranking (Top 30)"]
    entered_old = [(pos, j) for pos, j in changes["entered"] if j.get("id") not in new_ids]
    exited = changes["exited"]
    movers = changes["movers"]
    shown = False

    if entered_old:
        shown = True
        lines.append("Entraram no Top 30:")
        for pos, job in entered_old:
            lines.append(
                f"  #{pos} — {_short_title(job)} — "
                f"{job.get('company') or '—'} ({_score_text(job.get('score'))})"
            )
    if exited:
        shown = True
        lines.append("Saíram do Top 30:")
        for pos, job in exited:
            lines.append(
                f"  #{pos} — {_short_title(job)} — "
                f"{job.get('company') or '—'}"
            )
    if movers:
        shown = True
        lines.append("Maiores movimentos:")
        for job, prev_pos, cur_pos in movers:
            delta = prev_pos - cur_pos  # >0 = subiu (posicao menor)
            arrow = "↑" if delta > 0 else "↓"
            lines.append(
                f"  {arrow} {abs(delta)} — {_short_title(job)} — "
                f"{job.get('company') or '—'} (#{prev_pos} → #{cur_pos})"
            )
    if not shown:
        lines.append("— sem mudanças relevantes no Top 30")
    return lines


def materials_lines(current: list[dict], previous: list[dict]) -> list[str]:
    """Secao compacta do perfil Materials (Fase 4): Top 5 + novas no Top 30.

    O ranking materials e COMPUTADO aqui (``rank_materials_jobs`` — funcao
    pura sobre as MESMAS vagas elegiveis ja carregadas; score e posicoes
    PROPRIOS, independentes do principal). Zero arquivo novo, zero infra:
    a mesma mensagem unica do refresh carrega a secao do segundo perfil.
    Best-effort: lista vazia sem vagas; nunca derruba o digest.
    """
    if not current:
        return []
    mat_cur = rank_materials_jobs(current)
    lines = [
        "🧪 Perfil Materials Engineering (ranking próprio, mesmas vagas elegíveis)"
    ]
    top5 = mat_cur[:MATERIALS_TOP5]
    if not top5:
        lines.append("— ranking materials vazio")
        return lines
    lines.append("Top 5:")
    for pos, j in enumerate(top5, 1):
        lines.append(
            f"  {pos}. {_short_title(j)} — {j.get('company') or '—'} "
            f"(mat {_score_text(j.get('materials_score'))})"
        )
    if previous:
        novas = new_top_entries(mat_cur, previous, top=DIGEST_TOP)
        if novas:
            lines.append(f"🆕 Novas no Top 30 Materials ({len(novas)}):")
            for pos, j in novas[:MATERIALS_NEW_MAX]:
                lines.append(
                    f"  #{pos} — {_short_title(j)} — {j.get('company') or '—'}"
                )
            if len(novas) > MATERIALS_NEW_MAX:
                lines.append(f"  (+{len(novas) - MATERIALS_NEW_MAX} outras)")
        else:
            lines.append("— nenhuma vaga nova no Top 30 Materials")
    return lines


def eu_lines(current: list[dict], previous: list[dict]) -> list[str]:
    """Secao compacta do perfil EU non-DE (F36): Top 5 + novas no Top 30.

    Mesmo padrao da secao Materials (Fase 4): o ranking e COMPUTADO aqui
    (``rank_eu_jobs`` — funcao pura sobre as MESMAS vagas elegiveis;
    score e posicoes PROPRIOS, independentes do business/materials).
    Best-effort: lista vazia sem vagas; nunca derruba o digest.
    """
    if not current:
        return []
    from internship_finder.eu_ranking import rank_eu_stratum

    # Display do perfil EU = estrato não-DE (a seção é o canal
    # secundário "Fora da Alemanha" — só promete vagas fora da DE).
    eu_cur = rank_eu_stratum(current)
    lines = [
        "🇪🇺 Perfil EU non-DE (ranking próprio, mesmas vagas elegíveis)"
    ]
    top5 = eu_cur[:EU_TOP5]
    if not top5:
        lines.append("— ranking EU vazio")
        return lines
    lines.append("Top 5:")
    for pos, j in enumerate(top5, 1):
        lines.append(
            f"  {pos}. {_short_title(j)} — {j.get('company') or '—'} "
            f"(eu {_score_text(j.get('eu_score'))})"
        )
    if previous:
        novas = new_top_entries(eu_cur, previous, top=DIGEST_TOP)
        if novas:
            lines.append(f"🆕 Novas no Top 30 EU ({len(novas)}):")
            for pos, j in novas[:EU_NEW_MAX]:
                lines.append(
                    f"  #{pos} — {_short_title(j)} — {j.get('company') or '—'}"
                )
            if len(novas) > EU_NEW_MAX:
                lines.append(f"  (+{len(novas) - EU_NEW_MAX} outras)")
        else:
            lines.append("— nenhuma vaga nova no Top 30 EU")
    return lines


# ---------------------------------------------------------------------------
# F11 — secoes do funil de aplicacao
# ---------------------------------------------------------------------------

# Contagem que caracteriza "evento de dataset novo" (ex.: onboarding de
# fonte nova): o diff e legitimo mas listar top-3 como "novas de ontem"
# vende uma ida de shopping como novidade do dia. Acima disso, o digest
# mostra so a contagem honesta; a pagina segue mostrando o top-10.
NEW_SINCE_BIG_DIFF = 500

# Exibicao da secao 🆕 da pagina (spec F11 T1: top 10 por score).
NEW_SINCE_PAGE_TOP = 10


def _german_level_of(job: dict) -> str:
    """Nivel de alemao da vaga ('required'/'preferred'/'plus'/'none').

    MESMO detector do fit da interface (app_intel.german_level sobre
    titulo+descricao); None = sem mencao -> 'none'. Best-effort: falha
    de import/parse -> 'none' (nunca derruba render/digest).
    """
    try:
        from internship_finder import app_intel
        text = f"{job.get('title') or ''} {job.get('description') or ''}"
        gl = app_intel.german_level(text)
        return gl.level if gl is not None else "none"
    except Exception:  # noqa: BLE001 — view best-effort
        return "none"


def applicable_lines(current: list[dict], *, top: int = DIGEST_TOP5) -> list[str]:
    """Secao '🎯 Top 5 aplicáveis' (F11 T2c): sem DE-required E visa_friendly.

    Escaneia o ranking em ordem oficial ate preencher ``top``; se houver
    menos, lista o que houver; se 0, linha graciosa honesta (filtros
    muito restritivos hoje) — nunca lista vagas fora do criterio.
    """
    lines = ["🎯 Top 5 aplicáveis (sem alemão exigido + 🛂)"]
    if not current:
        return lines + ["— ranking vazio"]
    picks: list[dict] = []
    for job in current:
        if len(picks) >= top:
            break
        if not bool(job.get("visa_friendly")):
            continue
        if _german_level_of(job) == "required":
            continue
        picks.append(job)
    if not picks:
        return lines + [
            "— nenhuma vaga aplicável hoje — filtros de alemão/visto "
            "muito restritivos"
        ]
    for pos, job in enumerate(picks, 1):
        lines.append(
            f"  {pos}. {_short_title(job)} — {job.get('company') or '—'} "
            f"({_score_text(job.get('score'))})"
        )
    return lines


def new_since_lines(
    diff: tuple[set[str], set[str]] | None,
    current: list[dict],
    *,
    max_shown: int = 3,
    big_diff: int = NEW_SINCE_BIG_DIFF,
) -> list[str]:
    """Secao '🆕 Novas desde ontem' do digest (F11 T1; contagem + top 3).

    ``diff`` = saida de ``new_since_previous`` (None = sem snapshot; secao
    ausente). Diff gigante (>= ``big_diff`` novas — evento de dataset
    novo, ex. onboarding de fonte): mostra SO a contagem, NUNCA a lista
    (o +1.793 de 03/10 nao caberia e seria desinformacao util).

    O top-3 e escaneado em ordem oficial (score do pipeline) entre as
    novas; cada linha: titulo, empresa, score, apply_url (mesma prioridade
    da pagina — raw.apply_url com fallback job.url).
    """
    if diff is None:
        return []
    new_ids, gone_ids = diff
    if not new_ids:
        lines = ["🆕 Novas desde ontem: 0 (nenhuma vaga nova no dataset)"]
        if gone_ids:
            lines.append(f"({len(gone_ids)} vaga(s) saíram do dataset)")
        return lines
    lines = [f"🆕 Novas desde ontem: {len(new_ids)}"]
    if len(new_ids) >= big_diff:
        lines.append(
            "(evento de dataset novo — onboarding de fonte; o dia a dia "
            "volta no próximo run)"
        )
        return lines
    shown = 0
    for job in current:
        if shown >= max_shown:
            break
        if job.get("id") not in new_ids:
            continue
        url = _apply_url_of(job) or "—"
        lines.append(
            f"  {shown + 1}. {_short_title(job)} — "
            f"{job.get('company') or '—'} — {_score_text(job.get('score'))} "
            f"— {url}"  # F12.5: URL inteira, NUNCA clipada (link quebrado = 404)
        )
        shown += 1
    if len(new_ids) > shown:
        lines.append(f"  (+{len(new_ids) - shown} outras novas — ver página)")
    return lines


# ---------------------------------------------------------------------------
# F13 — radar de empresas-alvo (watchlist). O MECANISMO de "vaga nova" é o
# diff de IDs da F11 (``new_since_previous``); a watchlist é apenas um FILTRO
# por empresa (string exata, casefold). Nenhum coletor novo, nenhum HTTP novo.
# ---------------------------------------------------------------------------

# Cap de linhas/dia da seção 🎯 (spec F13 §2.3: máx. 5 linhas/dia).
RADAR_MAX_SHOWN = 5

# Header ÚNICO da seção de radar — distinto dos outros usos de 🎯 no digest
# ("🎯 Perfil e critérios ativos" e "🎯 Top 5 aplicáveis"): o compactador
# extrai seções por prefixo EXATO de header, nunca por emoji.
WATCHLIST_SECTION_PREFIX = "🎯 Empresas-alvo"
WATCHLIST_SECTION_HEADER = (
    f"{WATCHLIST_SECTION_PREFIX} (watchlist) — vagas novas de ontem nas "
    "empresas que você acompanha"
)


def _norm_company(value) -> str:
    """Casefold + colapso de espaços (mesma normalização do cap de exibição)."""
    return " ".join(str(value or "").strip().casefold().split())


def load_watchlist(path: str | Path) -> list[str] | None:
    """Carrega ``config/company_watchlist.json`` (F13; pura, best-effort).

    Devolve a lista de strings de empresa (EXATAS como no dataset; o match
    e casefold) ou ``None`` quando o arquivo nao existe / e invalido / nao
    contem ``companies`` — o chamador omite a secao de radar inteira, sem
    erro (o radar nunca e obrigatorio; arquivo e opcional por design).
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("companies")
    if not isinstance(raw, list):
        return None
    companies = [str(c).strip() for c in raw
                 if isinstance(c, (str, int, float)) and str(c).strip()]
    return companies or None


def radar_events(
    diff: tuple[set[str], set[str]] | None,
    current: list[dict],
    watchlist: list[str] | None,
) -> list[dict]:
    """Vagas NOVAS cuja empresa esta na watchlist (F13; pura).

    ``diff`` = saida de ``new_since_previous`` (None = sem snapshot ->
    sem eventos). O match e por STRING EXATA casefold — a watchlist carrega
    os strings que o dataset usa (ex.: ``BoschGroup``, ``lidlstiftup2``),
    NAO nomes bonitos. Ordem oficial do ranking (nao reordena nada); a
    vaga fora do top exibido tambem conta (o radar e alerta, nao ranking).
    Empresa ausente do dataset = simplesmente nunca casa (silencio).
    """
    if diff is None or not watchlist:
        return []
    new_ids = diff[0]
    if not new_ids:
        return []
    wanted = {_norm_company(c) for c in watchlist}
    events: list[dict] = []
    for job in current:
        if job.get("id") not in new_ids:
            continue
        if _norm_company(job.get("company")) in wanted:
            events.append(job)
    return events


def radar_lines(
    diff: tuple[set[str], set[str]] | None,
    current: list[dict],
    watchlist: list[str] | None,
    *,
    max_shown: int = RADAR_MAX_SHOWN,
) -> list[str]:
    """Secao '🎯 Empresas-alvo' do digest (F13; contagem + cap 5).

    Sem watchlist, sem snapshot, ou zero eventos -> ``[]`` (secao AUSENTE,
    sem linha vazia — spec §2.3). Cada evento: ``🎯 <empresa>: <titulo>
    (<local>)`` — 1 linha por vaga, cap ``max_shown``; excedentes viram a
    linha ``(+N outras — ver página)`` (padrao de colapso-para-contagem da
    F11/F6.1). O header carrega a CONTAGEM (sobrevive ao compact).
    """
    events = radar_events(diff, current, watchlist)
    if not events:
        return []
    lines = [f"{WATCHLIST_SECTION_HEADER} — {len(events)} nova(s)"]
    for pos, job in enumerate(events[:max_shown], 1):
        lines.append(
            f"  🎯 {pos}. {job.get('company') or '—'}: "
            f"{_short_title(job)} ({_short_location(job)})"
        )
    if len(events) > max_shown:
        lines.append(f"  (+{len(events) - max_shown} outras — ver página)")
    return lines


def watchlist_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a secao 🎯 de radar de ``digest_lines`` (F13; para o compact).

    Espelho de ``top5_section_lines`` (F6.1): header + corpo ate a proxima
    linha em branco, ou ``[]`` quando a secao nao existe. Somente leitura.
    """
    header_idx = None
    for idx, line in enumerate(digest_lines):
        if line.startswith(WATCHLIST_SECTION_PREFIX):
            header_idx = idx
            break
    if header_idx is None:
        return []
    section = [digest_lines[header_idx]]
    for line in digest_lines[header_idx + 1:]:
        if not line.strip():
            break
        section.append(line)
    return section


def _section_by_prefix(digest_lines: list[str], prefix: str) -> list[str]:
    """Extrai header + corpo de ``digest_lines`` ate o próximo blank (F36.1).

    Mecânica comum dos extratores do compactador (F6.1/F13/F14): reconhece
    a seção pelo PREFIXO EXATO de header (contrato; o sufixo pode evoluir),
    copia header + corpo até a linha em branco seguinte. ``[]`` quando a
    seção não existe (digest vazio/None, perfil ausente, best-effort).
    Somente leitura; nunca lança.
    """
    header_idx = None
    for idx, line in enumerate(digest_lines):
        if line.startswith(prefix):
            header_idx = idx
            break
    if header_idx is None:
        return []
    section = [digest_lines[header_idx]]
    for line in digest_lines[header_idx + 1:]:
        if not line.strip():
            break
        section.append(line)
    return section


def materials_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a seção 🧪 Perfil Materials (F36.1; para o compact).

    Espelho de ``watchlist_section_lines`` (F13): header + corpo até o
    próximo blank, ou ``[]`` quando ausente. O compactador usa o header
    (que carrega a natureza da seção) como forma colapsada — o corpo
    cede espaço às seções de maior prioridade, a seção NUNCA é dropada
    inteira (bug latente pré-F36.1: 🧪 sumia do digest compactado desde
    28/09 porque a reconstrução por prioridade nem a considerava).
    """
    return _section_by_prefix(digest_lines, MATERIALS_SECTION_PREFIX)


def eu_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a seção 🇪🇺 Perfil EU non-DE (F36.1; para o compact).

    Mesmo espelho da 🧪 (padrão F13/F36): header + corpo até o próximo
    blank, ou ``[]`` quando ausente. ``[]`` também quando o estrato
    não-DE está vazio (a seção honestamente não existe nesse dia).
    """
    return _section_by_prefix(digest_lines, EU_SECTION_PREFIX)


# ---------------------------------------------------------------------------
# F14 — pendências de follow-up (banco privado; best-effort sempre).
# A MÁQUINA é a do personal_tracker (followup_pending); o digest só
# formata. Colapsa ao header com contagem no compact (padrão F13).
# ---------------------------------------------------------------------------

# Header ÚNICO da seção (o compactador extrai por prefixo EXATO).
FOLLOWUP_SECTION_PREFIX = "⏰ Follow-up"
FOLLOWUP_SECTION_HEADER = (
    f"{FOLLOWUP_SECTION_PREFIX} — candidaturas sem resposta"
)

# Cap de linhas/dia da seção (spec F14 §2.3: máx. 5 linhas).
FOLLOWUP_MAX_SHOWN = 5


def _format_followup(pending: list[dict], ranking: list[dict], *,
                     after_days: int,
                     max_shown: int = FOLLOWUP_MAX_SHOWN) -> list[str]:
    """Formatador puro da seção ⏰ (F14; usado pelo digest e testes).

    ``pending`` = saída de ``personal_tracker.followup_pending``;
    ``ranking`` = ranking atual (título/empresa das linhas; vaga fora do
    ranking segue listada — aplicada não desaparece, §19 da F8).
    """
    if not pending:
        return []
    by_id = {str(j.get("id")): j for j in ranking if j.get("id")}
    lines = [f"{FOLLOWUP_SECTION_HEADER} — {len(pending)} pendente(s) "
             f"(aplicadas há mais de {after_days} dias sem resposta)"]
    for pos, p in enumerate(pending[:max_shown], 1):
        j = by_id.get(p["job_id"], {})
        title = str(j.get("title") or "").strip() or "(fora do ranking atual)"
        company = str(j.get("company") or "").strip() or "—"
        lines.append(
            f"  ⏰ {pos}. {company}: {_short_title({'title': title})} "
            f"(há {p['days']} dias)"
        )
    if len(pending) > max_shown:
        lines.append(f"  (+{len(pending) - max_shown} outra(s) — ver "
                     f"`personal_tracker.py list --status applied`)")
    return lines


def followup_lines(db_path: str | Path, current_path: str | Path, *,
                   ref_date=None, after_days: int | None = None,
                   max_shown: int = FOLLOWUP_MAX_SHOWN) -> list[str]:
    """Seção '⏰ Follow-up' do digest (F14 §2.3; contagem + cap 5).

    Vagas com status ``applied`` há mais de ``after_days`` dias (default
    10 = ``personal_tracker.FOLLOWUP_AFTER_DAYS``) sem evento de
    interação posterior (a máquina é ``personal_tracker.followup_pending``
    — zero regra duplicada), formatadas por ``_format_followup`` com o
    ranking atual de ``current_path``.

    Banco ausente/corrompido ou zero pendências -> ``[]`` (seção
    AUSENTE, sem linha vazia). Sem notas, sem contatos, sem dados
    privados — só empresa/título/dias.
    """
    try:
        sys_path_scripts = Path(__file__).resolve().parent
        if str(sys_path_scripts) not in __import__("sys").path:
            __import__("sys").path.insert(0, str(sys_path_scripts))
        import personal_tracker as pt
        conn = pt.connect(db_path)
    except Exception:  # noqa: BLE001 — banco pessoal nunca derruba o run
        return []
    try:
        if after_days is None:
            after_days = pt.FOLLOWUP_AFTER_DAYS
        pending = pt.followup_pending(conn, ref=ref_date,
                                      after_days=after_days,
                                      max_shown=0)  # cap é do FORMATADOR
    except Exception:  # noqa: BLE001 — leitura inválida -> silêncio
        return []
    finally:
        conn.close()
    return _format_followup(pending, load_ranking(current_path),
                            after_days=after_days, max_shown=max_shown)


def followup_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a seção ⏰ de ``digest_lines`` (F14; para o compact).

    Espelho de ``watchlist_section_lines`` (F13): header + corpo até a
    próxima linha em branco; ``[]`` quando ausente.
    """
    header_idx = None
    for idx, line in enumerate(digest_lines):
        if line.startswith(FOLLOWUP_SECTION_PREFIX):
            header_idx = idx
            break
    if header_idx is None:
        return []
    section = [digest_lines[header_idx]]
    for line in digest_lines[header_idx + 1:]:
        if not line.strip():
            break
        section.append(line)
    return section


# ---------------------------------------------------------------------------
# F44 — frescor do intel de empresas (staleness). GATILHO de curadoria,
# não produto do dia: aponta o que está velho/noivo para o HUMANO ir
# buscar (princípio da fase: "automatize o gatilho, humanize o fetch").
# A MÁQUINA é a do intel_freshness (report offline determinístico); o
# digest só formata os gatilhos. Zero gatilhos -> seção AUSENTE (digest
# byte a byte o de antes). Colapsa ao header no compact (padrão F13).
# ---------------------------------------------------------------------------

# Header ÚNICO da seção — distinto do ⏰ Follow-up (F14): o compactador
# extrai por PREFIXO EXATO de header, nunca por emoji.
INTEL_SECTION_PREFIX = "⏰ Intel de empresas"
INTEL_SECTION_HEADER = f"{INTEL_SECTION_PREFIX} (frescor do intel)"

# Cap de exemplos por gatilho na seção (o header carrega a CONTAGEM
# absoluta; exemplos são ilustrativos — padrão "cap 5" da F13/F14).
INTEL_MAX_SHOWN = 5


def intel_lines(
    triggers: dict | None,
    *,
    max_shown: int = INTEL_MAX_SHOWN,
) -> list[str]:
    """Seção '⏰ Intel de empresas' do digest (F44; contagens + cap 5).

    ``triggers`` = saída de ``intel_freshness.triggers`` (None quando os
    arquivos de origem não existem/ilegíveis — seção ausente). Zero
    gatilhos (``stale_count == 0`` e ``no_kununu_count == 0``) -> ``[]``
    (seção AUSENTE, sem linha vazia — A/B do card F44).

    Layout (header carrega as contagens, sobrevive ao compact):

        ⏰ Intel de empresas (frescor do intel) — 12 >90d; 3 alvo sem Kununu
          🕰 1. BASF SE — checked 2026-06-10 (127d)
          ...
          ⭐ 1. Vanderlande — sem score Kununu (alvo da watchlist)
          ...
          → humano: CDP attach Kununu (~30s/empresa) + atualizar checked

    Cada gatilho lista até ``max_shown`` exemplos; excedentes viram a
    linha ``(+N outras — ver relatório intel_freshness.py)`` (padrão de
    colapso-para-contagem da F11/F6.1). Nunca lança; nunca escreve.
    """
    if not triggers:
        return []
    stale_count = triggers.get("stale_count") or 0
    no_kununu_count = triggers.get("no_kununu_count") or 0
    if stale_count <= 0 and no_kununu_count <= 0:
        return []
    stale_days = triggers.get("stale_days")
    # Header carrega só os gatilhos VIVOS (parte zerada é ruído — o
    # exemplo do card "⏰ Intel: 12 empresas >90d; 3 alvo sem Kununu"
    # pressupõe ambos; com um deles em zero só o outro aparece).
    parts_txt: list[str] = []
    if stale_count > 0:
        parts_txt.append(f"{stale_count} >{stale_days}d")
    if no_kununu_count > 0:
        parts_txt.append(f"{no_kununu_count} alvo sem Kununu")
    lines = [f"{INTEL_SECTION_HEADER} — " + "; ".join(parts_txt)]
    stale_top = list(triggers.get("stale_top") or [])[:max_shown]
    for pos, name in enumerate(stale_top, 1):
        checked = (triggers.get("stale_top_checked") or [None] * len(stale_top))
        checked_txt = f" — checked {checked[pos - 1]}" if pos <= len(checked) and checked[pos - 1] else ""
        lines.append(f"  🕰 {pos}. {name}{checked_txt}")
    if len(stale_top) < stale_count:
        lines.append(f"  (+{stale_count - len(stale_top)} outras — ver relatório"
                     " intel_freshness.py)")
    no_kununu_top = list(triggers.get("no_kununu_top") or [])[:max_shown]
    for pos, name in enumerate(no_kununu_top, 1):
        lines.append(f"  ⭐ {pos}. {name} — sem score Kununu (alvo da watchlist)")
    if len(no_kununu_top) < no_kununu_count:
        lines.append(f"  (+{no_kununu_count - len(no_kununu_top)} outras — ver"
                     " relatório intel_freshness.py)")
    # Rodapé de ritual: só o que o gatilho VIVO pede (o rodapé único
    # "CDP attach + checked" seria orientação errada quando só há um
    # dos gatilhos — cada um tem seu fetch humano).
    ritual: list[str] = []
    if no_kununu_count > 0:
        ritual.append("CDP attach Kununu nos alvo(s) sem score (~30s/empresa)")
    if stale_count > 0:
        ritual.append("reverificar sources/checked das >"
                      f"{triggers.get('stale_days')}d")
    lines.append("  → humano: " + "; ".join(ritual))
    return lines


def intel_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a seção ⏰ Intel de ``digest_lines`` (F44; para o compact).

    Espelho de ``followup_section_lines`` (F14): header + corpo até a
    próxima linha em branco; ``[]`` quando ausente.
    """
    return _section_by_prefix(digest_lines, INTEL_SECTION_PREFIX)


def new_since_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a secao 🆕 'Novas desde ontem' de ``digest_lines`` (F13).

    O header da secao e sempre o emitido por ``new_since_lines`` (comeca
    com ``🆕 Novas desde ontem:``); o corpo segue ate o blank. ``[]`` quando
    ausente. Uso: compactador do Telegram (prioridade de preservacao F13).
    """
    for idx, line in enumerate(digest_lines):
        if line.startswith("🆕 Novas desde ontem:"):
            section = [line]
            for ln in digest_lines[idx + 1:]:
                if not ln.strip():
                    break
                section.append(ln)
            return section
    return []


def enrichment_lines(
    current: list[dict],
    enrichment_path: str | Path | None,
    *,
    top: int = DIGEST_TOP,
    max_shown: int = ENRICH_TOP5,
) -> list[str]:
    """Secao '🔎 Enrichment — dados da pagina oficial' (Fase 3, best-effort).

    Ate ``max_shown`` vagas do Top 30 com view UTILIZAVEL (na ordem do
    ranking — sem reordenar; PIP=false e nao-extracoes ficam fora), 1 linha
    por vaga com so campos presentes (salary, work mode, local, idiomas,
    student status, WA relevantes, deadline). Evidencias NAO vem ao
    Telegram (tamanho) — ficam no HTML. ``stale`` ganha sufixo
    "(extracao antiga)". Store ausente/malformado -> secao inteira some
    (enrichment NUNCA e obrigatoria; load tolerante -> {}).
    """
    records = enr_present.load_enrichment(enrichment_path or "")
    if not records:
        return []
    views = enr_present.view_map(records)
    if not views:
        return []
    lines = ["🔎 Enrichment — dados da página oficial (Top 5 com análise)"]
    shown = 0
    for pos, job in top_positions(current, top):
        jid = str(job.get("id") or "")
        view = views.get(jid)
        if view is None:
            continue
        parts: list[str] = []
        if view.get("salary_text"):
            parts.append(view["salary_text"])
        if view.get("work_mode"):
            parts.append(f"modalidade: {view['work_mode']}")
        if view.get("location"):
            parts.append(f"local: {view['location']}")
        if view.get("english"):
            parts.append(f"inglês: {view['english']}")
        if view.get("german"):
            parts.append(f"alemão: {view['german']}")
        if view.get("student_status"):
            parts.append(f"estudante: {view['student_status']}")
        wa = view.get("wa") or {}
        for concept in ("eu_citizenship_required", "visa_sponsorship",
                        "existing_work_authorization_required",
                        "work_permit_required", "residence_permit_required"):
            entry = wa.get(concept)
            if entry is not None:
                label = enr_present.WA_CONCEPT_LABELS.get(concept, concept)
                parts.append(f"{label}: {entry['label']}")
        if view.get("deadline_date"):
            parts.append(f"deadline: {view['deadline_date']}")
        if not parts:
            continue
        stale = " (extração antiga)" if view.get("stale") else ""
        lines.append(
            f"#{pos} — {_short_title(job)} — {job.get('company') or '—'} — "
            + " · ".join(parts[:6])
            + stale
        )
        shown += 1
        if shown >= max_shown:
            break
    if shown == 0:
        return []
    return lines


def digest_sections(
    current_path: str | Path,
    previous_path: str | Path,
    *,
    pages_url: str,
    country_spec: str = DEFAULT_COUNTRY_SPEC,
    top: int = DIGEST_TOP,
    enrichment_path: str | Path | None = None,
    watchlist_path: str | Path | None = None,
    employer_quality_path: str | Path | None = None,
    intel_freshness_paths: tuple | None = None,
    excluded_ids: set[str] | None = None,
    visa_countdown: bool = True,
) -> list[str] | None:
    """Secoes do digest do Telegram; ``None`` quando nao ha ranking atual.

    Layout (ordem do enunciado da Fase 2): perfil/criterios -> novas vagas
    no Top 30 -> Top 5 atual -> mudancas -> link do ranking completo (sempre
    a ultima linha). ``previous_path`` e o snapshot da rotacao (ranking do
    run anterior); sem snapshot (primeiro run), o digest avisa que a
    comparacao comeca no proximo run — nunca trata todo o Top 30 como novo.

    F13: ``watchlist_path`` = ``config/company_watchlist.json`` (default
    ``None`` = radar desligado — secao 🎯 ausente e o digest e byte a byte
    o de antes). A secao de radar reusa o MESMO diff de IDs da secao 🆕
    (``new_since_previous``): vaga nova em empresa da watchlist = evento,
    independente de score/posicao. Best-effort: falha nunca derruba o digest.

    F15: ``employer_quality_path`` = ``config/employer_quality.json``
    (default ``None`` = mapa desligado — Top 5 byte a byte o de antes).
    Quando o mapa existe, o ⚡ Top 5 ganha ⭐ após o nome da empresa
    mapeada com score Kununu >= 4,0 OU prêmio GPTW (2 chars; sinal
    INFORMATIVO — o ranking não muda). Best-effort: mapa ausente/
    corrompido -> sem marcador, nunca derruba o digest.

    F25: ``excluded_ids`` = ids demovidos das superfícies exibidas pelo
    refresh (vagas mortas do liveness + inaplicáveis pós-hidratação,
    incluindo o backlog hidratado reavaliado por
    ``_reassess_backlog_applicability``). Os DOIS Top 5 do digest (🏆
    resumo e ⚡ com apply_url) cortam esses ids — MESMA semântica F20 da
    página: a vaga seguinte sobe; o JSON/CSV ficam intocados. Default
    ``None`` = sem exclusões (comportamento pré-F25, regressão zero).

    F29: ``visa_countdown`` = linha estática do countdown do visto §16e
    ANTES do ⚡ Top 5 (default ``True``; ``False`` = digest byte a byte
    o de antes — usado pelo teste de presença/ausência).

    F44: ``intel_freshness_paths`` = tupla (intel, watchlist,
    employer_quality) — caminhos dos três arquivos versionados que
    alimentam o gatilho de frescor (default ``None`` = seção ⏰ Intel
    AUSENTE e o digest é byte a byte o de antes). Zero gatilhos
    (nenhuma empresa >90d, nenhum alvo sem Kununu) também = seção
    ausente. Best-effort: arquivos ausentes/corrompidos -> sem seção,
    nunca derruba o digest.
    """
    current = load_ranking(current_path)
    if not current:
        return None
    previous = load_ranking(previous_path)
    excluded = {str(i) for i in (excluded_ids or set())}

    lines: list[str] = [""]
    lines.extend(profile_lines(country_spec))

    stats = score_stats(current)
    if stats:
        lines.append(
            f"Score do run: min {stats['min']:g} · mediana "
            f"{stats['median']:g} · máx {stats['max']:g} "
            f"({_fmt(stats['count'])} vagas elegíveis)"
        )

    if not previous:
        lines.append("")
        lines.append(
            "ℹ️ Sem snapshot do run anterior (primeiro digest): a comparação "
            "de novas vagas começa no próximo run."
        )
        lines.append("")
        lines.extend(_top5_section(current, excluded_ids=excluded))
    else:
        novas = new_top_entries(current, previous, top=top)
        lines.append("")
        lines.extend(_novas_section(novas, country_spec))
        lines.append("")
        lines.extend(_top5_section(current, excluded_ids=excluded))
        changes = ranking_changes(current, previous, top=top)
        lines.append("")
        lines.extend(_changes_section(changes, {j.get("id") for _, j in novas}))

    # Fase 4: secao compacta do perfil Materials (antes do link — o link do
    # ranking completo segue sendo a ULTIMA linha).
    mat_lines = materials_lines(current, previous)
    if mat_lines:
        lines.append("")
        lines.extend(mat_lines)

    # F36: secao compacta do perfil EU non-DE (mesmo padrao da Materials).
    try:
        eu_sec = eu_lines(current, previous)
        if eu_sec:
            lines.append("")
            lines.extend(eu_sec)
    except Exception:  # noqa: BLE001 — secao nova nunca derruba o digest
        pass

    # F11 — secoes do funil de aplicacao (antes do link, best-effort):
    # 🆕 Novas desde ontem (diff de IDs contra o snapshot anterior — o
    # `previous_path` e o MESMO snapshot da rotacao usado pelas secoes
    # acima; sem snapshot usavel, secao ausente) e 🎯 Top 5 aplicaveis
    # (visa_friendly E sem DE-required — o filtro que mais importa para
    # o dono). Falha em qualquer secao nova NUNCA derruba o digest.
    try:
        previous_for_diff = load_ranking_or_none(previous_path)
        diff = new_since_previous(current, previous_for_diff)
        ns_lines = new_since_lines(diff, current)
        if ns_lines:
            lines.append("")
            lines.extend(ns_lines)
    except Exception:  # noqa: BLE001 — secao nova nunca derruba o digest
        pass
    try:
        lines.append("")
        lines.extend(applicable_lines(current))
    except Exception:  # noqa: BLE001
        pass

    # Fase 3 (enrichment): secao de dados da pagina oficial (antes do link;
    # store ausente -> secao inteira some — enrichment nunca e obrigatorio).
    # Default AUTO: <dir do current>/enrichment/enrichment_results.jsonl
    # (layout de data/ da Fase 2; refresh_daily/main() NAO precisam mudar).
    enr_path = enrichment_path
    if enr_path is None:
        enr_path = Path(current_path).parent / "enrichment" / "enrichment_results.jsonl"
    enr_lines = enrichment_lines(current, enr_path, top=top)
    if enr_lines:
        lines.append("")
        lines.extend(enr_lines)

    # F6 — Top 5 com apply_url (1 linha/vaga): logo após o "Top 5 atual"
    # (resumo visual). A lista vem do ranking em ordem oficial; a função é
    # pura e best-effort (nunca derruba o digest).
    # F15 — mapa de qualidade do empregador (uma leitura; best-effort:
    # ausente/corrompido -> None -> Top 5 sem marcador, byte a byte antes).
    quality_map: dict[str, dict] | None = None
    if employer_quality_path is not None:
        try:
            from internship_finder import employer_quality
            quality_map = employer_quality.load_employer_quality(
                employer_quality_path) or None
        except Exception:  # noqa: BLE001 — marcador nunca derruba digest
            quality_map = None
    # F29 (item 6) — countdown do visto §16e: 1 linha estática ANTES do
    # Top 5 (a data vem das constantes do módulo, nunca do texto). Pura e
    # best-effort: falha nunca derruba o digest. ``visa_countdown=False``
    # = comportamento pré-F29 (regressão zero para chamadores legados).
    if visa_countdown:
        try:
            lines.append("")
            lines.append(visa_countdown_line())
        except Exception:  # noqa: BLE001 — linha nova nunca derruba digest
            pass
    try:
        top5_text = format_top5(current, quality_map=quality_map,
                                excluded_ids=excluded)
        if top5_text:
            lines.append("")
            lines.append(TOP5_SECTION_HEADER)
            lines.extend(top5_text.splitlines())
    except Exception:  # noqa: BLE001 — seção extra nunca derruba o digest
        pass

    # F13 — radar de empresas-alvo: cruza o MESMO diff de IDs da secao 🆕
    # (nenhuma leitura nova, nenhum coletor novo) com a watchlist (strings
    # exatas de empresa; match casefold). Sem watchlist/sem snapshot/zero
    # eventos -> secao ausente. Best-effort: nunca derruba o digest.
    # Posicao (spec §2.3): DEPOIS do ⚡ Top 5 e das 🆕 — ultima secao antes
    # do link; o radar NAO reordena nada, so alerta.
    if watchlist_path is not None:
        try:
            watchlist = load_watchlist(watchlist_path)
            if watchlist:
                previous_for_radar = load_ranking_or_none(previous_path)
                diff_for_radar = new_since_previous(current, previous_for_radar)
                radar = radar_lines(diff_for_radar, current, watchlist)
                if radar:
                    lines.append("")
                    lines.extend(radar)
        except Exception:  # noqa: BLE001 — seção nova nunca derruba o digest
            pass

    # F44 — frescor do intel de empresas (gatilho de curadoria): lê os
    # MESMOS arquivos versionados do relatório offline (intel curado,
    # watchlist F13, mapa F15) e monta a seção ⏰ quando há gatilhos.
    # Best-effort: arquivos ausentes/corrompidos/zero gatilhos -> seção
    # ausente; falha nunca derruba o digest (padrão das seções novas).
    if intel_freshness_paths is not None:
        try:
            _scripts_dir = Path(__file__).resolve().parent
            if str(_scripts_dir) not in sys.path:
                sys.path.insert(0, str(_scripts_dir))
            import intel_freshness as ifr
            intel_comps = ifr.load_intel_companies(intel_freshness_paths[0])
            wl_comps = ifr.load_watchlist_companies(intel_freshness_paths[1])
            eq_comps = ifr.load_employer_quality_companies(
                intel_freshness_paths[2])
            # hoje via hook ``today()`` (padrão now_ref F29/F38): testes
            # substituem a função para datas determinísticas.
            trig = ifr.triggers(intel_comps, wl_comps, eq_comps,
                                ref_date=ifr.today(),
                                stale_days=ifr.DEFAULT_STALE_DAYS)
            i_lines = intel_lines(trig)
            if i_lines:
                lines.append("")
                lines.extend(i_lines)
        except Exception:  # noqa: BLE001 — seção nova nunca derruba o digest
            pass

    lines.append("")
    lines.append(f"🔗 Ranking completo (todas as vagas elegíveis): {pages_url}")
    return lines


# ---------------------------------------------------------------------------
# Fase 8 — secoes PESSOAIS do Telegram (banco privado; best-effort sempre)
# ---------------------------------------------------------------------------

def personal_sections(db_path: str | Path, current_path: str | Path, *,
                      ref_date=None, reminders_days: int = 3,
                      max_shown: int = 3,
                      followup_after_days: int | None = None) -> list[str]:
    """Secoes pessoais do digest (Fase 8 + F14 §2.3): reminders, follow-up
    e aguardando resposta.

    Le o banco privado ``data/personal/jobs_personal.db`` via
    ``scripts/personal_tracker.py`` (mesmo schema; nada de segunda fonte de
    verdade) e junta com o ranking atual. Regras (spec Fase 8):

    - SO deadline EMPLOYER conta como prazo (validade de feed
      SuccessFactors NUNCA — regra Fase 6);
    - shortlist = interesting/review/applied/interview/offer;
    - notas pessoais completas NUNCA sao enviadas;
    - banco ausente/corrompido -> ``[]`` silencioso (nunca derruba o run).

    F14: a secao "⏰ Follow-up" (aplicadas ha > ``followup_after_days``
    dias, default 10 do personal_tracker, sem interacao posterior; cap 5
    linhas + contagem) entra ANTES da linha de aguardando resposta —
    pendencia cronica na frente do contador de estado. Zero pendentes =
    secao ausente (sem linha vazia).

    As linhas entram ANTES do link do ranking (o link continua sendo a
    ultima linha do digest montado pelo chamador).
    """
    try:
        sys_path_scripts = Path(__file__).resolve().parent
        if str(sys_path_scripts) not in __import__("sys").path:
            __import__("sys").path.insert(0, str(sys_path_scripts))
        import personal_tracker as pt
        conn = pt.connect(db_path)
    except Exception:  # noqa: BLE001 — banco pessoal nunca derruba o run
        return []
    try:
        ranking = pt.load_ranking(current_path)
        reminders = pt.reminder_jobs(conn, ranking, ref=ref_date,
                                     max_days=reminders_days)
        followup = pt.followup_pending(
            conn, ref=ref_date,
            after_days=(pt.FOLLOWUP_AFTER_DAYS
                        if followup_after_days is None
                        else followup_after_days),
            max_shown=0)  # cap aplicado pelo formatador (F14)
        waiting = pt.waiting_response(conn)
    except Exception:  # noqa: BLE001 — leitura invalida -> silencio
        return []
    finally:
        conn.close()
    lines: list[str] = []
    if reminders:
        lines.append("")
        lines.append("\U000026A0\U0000FE0F Application reminders")
        lines.append(f"{len(reminders)} vaga(s) em sua shortlist vencem nos "
                     f"proximos {reminders_days} dias:")
        for r in reminders[:max_shown]:
            days = "amanha" if r["days"] == 1 else (
                "hoje" if r["days"] == 0 else f"em {r['days']} dias")
            lines.append(f"{r['company']} — {r['title']} ({days})")
        if len(reminders) > max_shown:
            lines.append(f"(+{len(reminders) - max_shown} outra(s))")
    if followup:
        after = (pt.FOLLOWUP_AFTER_DAYS if followup_after_days is None
                 else followup_after_days)
        lines.append("")
        lines.extend(_format_followup(
            followup, ranking, after_days=after))
    if waiting:
        lines.append("")
        lines.append(f"\U0001F4CC {waiting} aplicação(ões) aguardando resposta")
    return lines



# ---------------------------------------------------------------------------
# F45 — funil com motivo de morte + calendário de sazonalidade (a seção
# "semanal" do digest; padrão F44: a MÁQUINA é o relatório offline
# ``scripts/funnel_report.py`` + o parser puro ``scripts/seasonality.py``,
# o digest só FORMATA. Zero dados legíveis -> seção AUSENTE e o digest é
# byte a byte o de antes; no compact a 📅 colapsa ao header DEPOIS da
# ⏰ Intel — spec F45: "sua seção semanal entra depois disso" — e exibe
# por último, antes do 🔗 link, APÓS as seções pessoais (a ordem F44
# "⏰ Intel imediatamente antes da 📌 Follow-up" fica intacta).
# ---------------------------------------------------------------------------

# Header ÚNICO da seção — o compactador extrai por PREFIXO EXATO de
# header, nunca por emoji (padrão F44/F14/F13).
FUNNEL_SECTION_PREFIX = "📅 Funil & sazonalidade"

# F62 — rótulo do início imediato no calendário da F45 (o badge da página
# e o calendário 📆 usam a MESMA fonte; este espelho é PINADO em teste
# contra seasonality.seasonality_label(kind=immediate) — se o parser
# mudar o rótulo, o test_f62 acusa antes de divergirem em silêncio).
IMMEDIATE_LABEL = "ab sofort"

# Cap de exemplos por bloco (motivos de morte / janelas do calendário) —
# o header carrega as CONTAGENS, os exemplos são ilustrativos (padrão
# "cap 5" da F13/F44).
FUNNEL_MAX_SHOWN = 5


def _fmt_count(value: int | None) -> str:
    """Inteiro com separador de milhar (padrão pt-BR: 2.134)."""
    if value is None:
        return "—"
    return f"{value:,}".replace(",", ".")


def funnel_seasonality_lines(
    report: dict | None,
    *,
    max_reasons: int = FUNNEL_MAX_SHOWN,
    max_windows: int = FUNNEL_MAX_SHOWN,
) -> list[str]:
    """Seção '📅 Funil & sazonalidade' do digest (F45; PURA sobre ``report``).

    ``report`` = saída de ``funnel_report.build_report`` (None quando
    nenhuma fonte legível -> seção ausente). O header carrega as
    contagens vivas (sobrevive ao compact): dia do último run, total de
    inaplicáveis e vagas com janela de início. Corpo (cap 5 por bloco):

        📅 Funil & sazonalidade (último run 17/10) — 2.134 inaplicáveis; 156 vagas com janela de início
          ✂ alemão exigido: 1.189 · werkstudent puro: 705 · ... (+7 outros motivos)
          📈 elegíveis: 871 hoje vs 779 há 7 runs (+92)
          📆 jan–jul/2027: 48 · ab sofort: 37 · ... (+19 outras janelas)
          ⚠ início imediato (ab sofort): 37 vagas — conflita com jan/2027
          📌 candidaturas (log F41): 12 eventos · 8 vagas — aplicadas 5 · ...

    F62: a linha ⚠ (acima da 📌) existe SÓ quando o calendário tem vagas
    de início imediato — display-only, sem imediatas a seção é byte a
    byte a da F45. Bloco ausente quando o dado ausente (sem trend, sem
    eventos F41, sem janelas). Nunca lança; nunca escreve; nunca lê
    arquivo (a pureza é o contrato de teste — I/O fica no loader
    ``funnel_seasonality_section``).
    """
    if not report:
        return []
    fun = report.get("funnel")
    sea = report.get("seasonality") or {}
    app = report.get("application")

    # Header: contagens VIVAS (partes zeradas/ausentes não aparecem —
    # ruído, padrão F44 do "12 >90d; 3 alvo sem Kununu").
    header_parts: list[str] = []
    run_day = ""
    if fun:
        day = str(fun.get("run_id") or "")[:10]
        if day:
            y, m, d = day.split("-")
            run_day = f" (último run {d}/{m})"
        deaths = (fun.get("applicability") or {}).get("total") or 0
        if deaths > 0:
            header_parts.append(f"{_fmt_count(deaths)} inaplicáveis")
    with_window = sea.get("with_window") or 0
    if with_window > 0:
        header_parts.append(f"{with_window} vagas com janela de início")
    if not header_parts and not app:
        return []
    lines = [FUNNEL_SECTION_PREFIX + run_day
             + (f" — {'; '.join(header_parts)}" if header_parts else "")]

    # ✂ motivos de morte (death-reason breakdown) — cap 5, só > 0.
    reasons = ((fun or {}).get("applicability") or {}).get("reasons") or {}
    alive = [(k, n) for k, n in reasons.items() if n > 0]
    if alive:
        alive.sort(key=lambda kv: (-kv[1], kv[0]))
        shown = alive[:max_reasons]
        # rótulo do próprio funnel_report (mesma fonte, sem segunda tabela)
        try:
            _scripts_dir = Path(__file__).resolve().parent
            if str(_scripts_dir) not in sys.path:
                sys.path.insert(0, str(_scripts_dir))
            import funnel_report as _fr
            label_of = _fr.death_label
        except Exception:  # noqa: BLE001 — rótulo é best-effort
            label_of = lambda k: k  # noqa: E731 — fallback: chave crua
        txt = " · ".join(f"{label_of(k)}: {_fmt_count(n)}" for k, n in shown)
        if len(alive) > max_reasons:
            txt += f" (+{len(alive) - max_reasons} outros motivos)"
        lines.append(f"  ✂ {txt}")

    # 📈 trend semanal (último run vs 7 runs atrás; ausente sem histórico).
    trend = report.get("trend")
    if trend:
        d = int(trend.get("delta") or 0)
        delta_txt = f"+{d}" if d > 0 else (str(d) if d < 0 else "±0")
        lines.append(f"  📈 elegíveis: {trend.get('eligible_last')} hoje vs "
                     f"{trend.get('eligible_then')} há {trend.get('window')} runs "
                     f"({delta_txt})")

    # 📆 calendário de sazonalidade — cap 5 janelas.
    cal = sea.get("calendar") or []
    if cal:
        shown = cal[:max_windows]
        txt = " · ".join(f"{item['label']}: {item['count']}" for item in shown)
        if len(cal) > max_windows:
            txt += f" (+{len(cal) - max_windows} outras janelas)"
        lines.append(f"  📆 {txt}")

    # F62 — ⚠ sinal de conflito: as vagas de início imediato ("ab sofort"
    # do calendário acima, MESMA fonte) conflitam com a meta do dono
    # (início jan/2027). Linha INFORMATIVA (display-only): nunca mexe em
    # score/ranking; janelas FUTURAS (SoSe 2027, jan–jul/2027) seguem
    # positivas e NÃO ganham aviso. Sem imediatas -> linha AUSENTE e o
    # digest é byte a byte o de antes (never-worsens).
    imm = next((int(item["count"]) for item in cal
                if item.get("label") == IMMEDIATE_LABEL), 0)
    if imm > 0:
        lines.append(f"  ⚠ início imediato ({IMMEDIATE_LABEL}): {imm} "
                     f"{'vaga' if imm == 1 else 'vagas'} — conflita com "
                     f"jan/2027")

    # 📌 cauda pessoal (event log F41) — só quando existem eventos.
    if app:
        parts = ", ".join(
            f"{_F45_EVENT_LABELS.get(et, et)} {n}"
            for et, n in sorted(app.get("by_type", {}).items()))
        lines.append(f"  📌 candidaturas (log F41): {app.get('events')} eventos"
                     f" · {app.get('jobs')} vagas — {parts}")
    return lines


# Rótulos dos desfechos F41 na linha 📌 (mesma nomenclatura do relatório).
_F45_EVENT_LABELS = {
    "applied": "aplicadas", "screening": "triagem", "interview": "entrevista",
    "offer": "oferta", "rejected": "rejeitadas", "withdrawn": "desistiu",
    "note": "notas",
}


def funnel_section_lines(digest_lines: list[str]) -> list[str]:
    """Extrai a seção 📅 Funil & sazonalidade de ``digest_lines`` (F45).

    Espelho de ``intel_section_lines`` (F44): header + corpo até a próxima
    linha em branco; ``[]`` quando ausente. Uso: compactador do Telegram.
    """
    return _section_by_prefix(digest_lines, FUNNEL_SECTION_PREFIX)


def funnel_seasonality_section(
    metrics_path: str | Path,
    events_path: str | Path,
    eligible_path: str | Path,
    *,
    best_top: int | None = None,
    week_window: int | None = None,
) -> list[str]:
    """Monta a seção 📅 PRONTA (F45): carrega o relatório offline
    (``funnel_report.build_report``) e formata. Best-effort TOTAL: fontes
    ausentes/corrompidas/qualquer falha -> ``[]`` (seção ausente, digest
    byte a byte o de antes — nunca derruba o run). I/O vive AQUI (o
    formatador ``funnel_seasonality_lines`` segue puro p/ os testes).
    """
    try:
        _scripts_dir = Path(__file__).resolve().parent
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        import funnel_report as fr
        kwargs: dict = {}
        if best_top is not None:
            kwargs["best_top"] = best_top
        if week_window is not None:
            kwargs["week_window"] = week_window
        report = fr.build_report(metrics_path, events_path, eligible_path,
                                 **kwargs)
        return funnel_seasonality_lines(report)
    except Exception:  # noqa: BLE001 — seção nova nunca derruba o digest
        return []


# ---------------------------------------------------------------------------
# CLI de inspecao (uso manual/testes; NAO e usada pelo refresh)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    import refresh_daily as rd

    parser = argparse.ArgumentParser(
        description="Compara o ranking atual com o snapshot anterior e imprime "
        "as secoes do digest do Telegram (nada e enviado).",
    )
    parser.add_argument("--root", default=None,
                        help="raiz do repo (default: detectada pelo refresh_daily)")
    parser.add_argument("--previous", default=None,
                        help="snapshot anterior (default: archive mais recente "
                             "com eligible_jobs.json)")
    parser.add_argument("--pages-url", default=None,
                        help="override da URL do ranking completo")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else rd.repo_root()
    data_dir = root / "data"
    previous_path = args.previous or _latest_archive_eligible(data_dir / "archive")
    url = args.pages_url or resolve_pages_url(root)
    sections = digest_sections(
        data_dir / "eligible_jobs.json", previous_path, pages_url=url,
    )
    if sections is None:
        print("sem ranking atual (data/eligible_jobs.json ausente/vazio)")
        return 1
    print("\n".join(sections))
    return 0


def _latest_archive_eligible(archive_root: Path) -> Path:
    """Snapshot anterior mais recente (a rotacao copia BEFORE a coleta, entao
    o archive mais novo = ranking do run anterior). Uso manual."""
    if not archive_root.exists():
        return Path("")
    candidates = sorted(archive_root.iterdir(), reverse=True)
    for d in candidates:
        eligible = d / "eligible_jobs.json"
        if eligible.exists():
            return eligible
    return Path("")


if __name__ == "__main__":
    raise SystemExit(main())