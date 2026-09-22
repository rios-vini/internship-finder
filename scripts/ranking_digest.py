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
from pathlib import Path

from internship_finder import filters
from internship_finder import ranking as ranking_mod
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


def _top5_section(current: list[dict]) -> list[str]:
    lines = ["🏆 Top 5 atual"]
    if not current:
        return lines + ["— ranking vazio"]
    for pos, job in top_positions(current, DIGEST_TOP5):
        lines.append(
            f"{pos}. {_short_title(job)} — "
            f"{job.get('company') or '—'} ({_score_text(job.get('score'))})"
        )
    return lines


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


def digest_sections(
    current_path: str | Path,
    previous_path: str | Path,
    *,
    pages_url: str,
    country_spec: str = DEFAULT_COUNTRY_SPEC,
    top: int = DIGEST_TOP,
) -> list[str] | None:
    """Secoes do digest do Telegram; ``None`` quando nao ha ranking atual.

    Layout (ordem do enunciado da Fase 2): perfil/criterios -> novas vagas
    no Top 30 -> Top 5 atual -> mudancas -> link do ranking completo (sempre
    a ultima linha). ``previous_path`` e o snapshot da rotacao (ranking do
    run anterior); sem snapshot (primeiro run), o digest avisa que a
    comparacao comeca no proximo run — nunca trata todo o Top 30 como novo.
    """
    current = load_ranking(current_path)
    if not current:
        return None
    previous = load_ranking(previous_path)

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
        lines.extend(_top5_section(current))
    else:
        novas = new_top_entries(current, previous, top=top)
        lines.append("")
        lines.extend(_novas_section(novas, country_spec))
        lines.append("")
        lines.extend(_top5_section(current))
        changes = ranking_changes(current, previous, top=top)
        lines.append("")
        lines.extend(_changes_section(changes, {j.get("id") for _, j in novas}))

    # Fase 4: secao compacta do perfil Materials (antes do link — o link do
    # ranking completo segue sendo a ULTIMA linha).
    mat_lines = materials_lines(current, previous)
    if mat_lines:
        lines.append("")
        lines.extend(mat_lines)

    lines.append("")
    lines.append(f"🔗 Ranking completo (todas as vagas elegíveis): {pages_url}")
    return lines


# ---------------------------------------------------------------------------
# Fase 8 — secoes PESSOAIS do Telegram (banco privado; best-effort sempre)
# ---------------------------------------------------------------------------

def personal_sections(db_path: str | Path, current_path: str | Path, *,
                      ref_date=None, reminders_days: int = 3,
                      max_shown: int = 3) -> list[str]:
    """Secoes pessoais do digest (Fase 8): reminders + aguardando resposta.

    Le o banco privado ``data/personal/jobs_personal.db`` via
    ``scripts/personal_tracker.py`` (mesmo schema; nada de segunda fonte de
    verdade) e junta com o ranking atual. Regras (spec Fase 8):

    - SO deadline EMPLOYER conta como prazo (validade de feed
      SuccessFactors NUNCA — regra Fase 6);
    - shortlist = interesting/review/applied/interview/offer;
    - notas pessoais completas NUNCA sao enviadas;
    - banco ausente/corrompido -> ``[]`` silencioso (nunca derruba o run).

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
    if waiting:
        lines.append("")
        lines.append(f"\U0001F4CC {waiting} aplicação(ões) aguardando resposta")
    return lines



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