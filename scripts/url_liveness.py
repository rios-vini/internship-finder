"""Vitalidade de URL do top exibido (F11) + liveness v2 soft-dead (F20).

O feed da Bundesagentur nunca remove vagas preenchidas (medicao 04/10: vaga
SAP do topo com posted 25/08 retornando 410 Gone; mediana de idade das 502
vagas BA = 49 dias). O ranking continua correto, mas o usuario clica em
anuncios mortos. Este estagio verifica os URLs do topo EXIBIDO antes da
publicacao e devolve o conjunto de ids com link confirmadamente morto.

Regras (spec F11, item 3 + F20, item 2):

- **404/410 = morta** (hard-dead, F11). A vaga desce do top exibido; a
  proxima sobe. Nada e removido do JSON/CSV (data/ e intocavel — sao a base).
- **F20 — soft-dead**: HTTP 200/2xx cujo CORPO evidencia vaga encerrada —
  (i) marcador textual ("this position has been filled", "no longer
  accepting applications", "nicht mehr verfugbar", "Stelle ist besetzt"...
  lista configuravel, case-insensitive); (ii) redirect-para-homepage: a URL
  final apos redirects e a raiz do site de carreiras (path vazio/"("/")
  em vez de pagina de vaga — caso DHL: a URL da vaga redireciona para a
  homepage com 200, mas a pagina REAL da vaga esta 410); (iii) shell SPA
  de board: 200 com tamanho exato assinado (~268.630 bytes do shell
  generico eightfold) OU <title> generico de board sem o id da vaga
  (caso Infineon). Marcada = MESMA semantica do 404/410 (desce do top).
- **403/429/timeout/DNS = bloqueio de bot ou rede**: ignora, nao marca
  nada (marcar por 403 derrubaria vagas vivas de sites com bot-wall).
- **Falha total do estagio** (rede fora: nenhuma resposta HTTP recebida):
  log + devolve conjunto VAZIO — o pipeline nunca derruba por causa do
  check e nunca marca mortas sem evidencia.
- **Deadline defensivo**: estourou, devolve o que ja foi confirmado
  (mortas observadas com resposta HTTP real) e loga.

F20 — o check passa a GET (os marcadores soft-dead vivem no CORPO; HEAD nao
tem corpo). Mesmo custo de timeout curto (~5s), delay sequencial e UA
honesto; o passe continua bounded ao top exibido (o chamador corta).

Hidratacao (F20, item 3): o MESMO passe HTTP devolve, para as vagas do
top-N com descricao curta, a descricao completa extraida da pagina
(parser honesto: JSON-LD jobPosting description -> meta og:description ->
heuristica de corpo; SEM LLM). Falha de fetch/parse = a descricao
original permanece (nunca piora). A re-avaliacao de aplicabilidade
(german_level/requires_master da F18) roda no chamador sobre a descricao
hidratada — ver ``refresh_daily``.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from pathlib import Path

__all__ = [
    "LIVENESS_UA", "LIVENESS_TIMEOUT_S", "LIVENESS_DELAY_S",
    "LIVENESS_DEADLINE_S", "LIVENESS_MAX_BYTES", "SOFT_DEAD_MARKERS",
    "SPA_SHELL_SIZES", "SPA_SHELL_TITLE_RE", "DEAD_STATUS",
    "check_liveness", "check_liveness_v2", "parse_job_description",
]

# UA honesto e identificavel (spec: "UA honesto") — nao imita browser.
LIVENESS_UA = "internship-finder-liveness/1.1 (job ranking link check)"

LIVENESS_TIMEOUT_S = 5.0   # timeout por request (spec: curto, ~5s)
LIVENESS_DELAY_S = 0.2    # pausa curta entre requests sequenciais
LIVENESS_DEADLINE_S = 240.0  # teto TOTAL do estagio (50 reqs * ~4.8s pior caso)

# Teto de bytes lidos do corpo por request (soft-dead markers + hidratacao
# vivem no inicio do HTML; 512KB cobre qualquer job page real e protege o
# estagio de corpos gigantes/streams).
LIVENESS_MAX_BYTES = 512 * 1024

# Status que significam "anuncio removido para sempre" (spec F11: 404/410).
DEAD_STATUS = frozenset({404, 410})

# F20 — marcadores de vaga encerrada no CORPO (case-insensitive; lista
# configuravel). Medidos na investigacao 07/10: Deutsche Borse retorna 200
# com "Sorry, this position has been filled" no corpo.
SOFT_DEAD_MARKERS = (
    "this position has been filled",
    "no longer accepting applications",
    "no longer accepting",
    "position is no longer",
    "nicht mehr verfügbar",
    "stelle ist besetzt",
)

# F20 — assinaturas de shell SPA de board (Infineon/eightfold): tamanho
# EXATO do shell generico servido para vaga morta (268.630 bytes medidos
# 07/10) OU <title> generico de board sem pin da vaga. Sem hard-code de
# empresa: a assinatura e do PADRAO (tamanho exato + title), nao do site.
SPA_SHELL_SIZES = frozenset({268_630})

# <title> genericos de board (job board shell): quando o title NAO carrega
# o titulo/id da vaga, a pagina e um shell, nao um anuncio. Match exato
# (casefold, strip) contra a lista — "Infineon Jobs" casa; "Working Student
# (m/w/d) - Infineon" nao.
SPA_SHELL_TITLE_RE = re.compile(
    r"^(?:jobs(?: at .+)?|careers(?: at .+)?|.+ jobs|job openings"
    r"|work with us|join us|vacancies|stellenangebote|karriere(?: bei .+)?)$",
    re.IGNORECASE,
)

_META_TAG_RE = re.compile(r"<meta[^>]*>", re.IGNORECASE)


def _meta_content(html: str, key: str) -> str | None:
    """Content de uma meta tag por name/property (tolerante à ordem dos
    atributos — 'content' pode vir antes de 'name'). ``None`` = sem tag.
    """
    for m in _META_TAG_RE.finditer(html):
        tag = m.group(0)
        if not re.search(rf'(?:property|name)\s*=\s*["\']{re.escape(key)}["\']',
                         tag, re.IGNORECASE):
            continue
        c = re.search(r'content\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if c:
            return c.group(1)
    return None


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_JSON_LD_JOB_RE = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _soft_dead_in_body(body_text: str) -> str | None:
    """Marcador de vaga encerrada presente no corpo? Devolve o marcador.

    Case-insensitive (o corpo e comparado apos casefold). ``None` = corpo
    vivo. Pura — testavel offline com strings fixture.
    """
    folded = body_text.casefold()
    for marker in SOFT_DEAD_MARKERS:
        if marker.casefold() in folded:
            return marker
    return None


def _is_spa_shell(body_text: str, body_bytes: int) -> bool:
    """Corpo e um shell generico de board (200 sem anuncio real)?

    Assinatura dupla e FP-safe por combinacao: (a) tamanho EXATO na lista
    de tamanhos de shell conhecidos (medidos; um job page real raramente
    tem exatamente 268.630 bytes); OU (b) <title> generico de board
    (match exato contra o padrao — "Infineon Jobs" casa, "Working Student
    - Infineon" nao). Sem hard-code de empresa.
    """
    if body_bytes in SPA_SHELL_SIZES:
        return True
    m = _TITLE_RE.search(body_text[:4096])
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        if title and SPA_SHELL_TITLE_RE.match(title):
            return True
    return False


def _final_path_is_homepage(final_url: str, original_url: str) -> bool:
    """A URL final apos redirects e a raiz/homepage em vez de pagina de vaga?

    Caso DHL: a URL da vaga redireciona para a homepage do site de
    carreiras com 200. Sinal: path final vazio ou "/" (e o host pode ate
    ser o mesmo). Comparacao por path apenas — query/fragment nao
    caracterizam homepage. A URL ORIGINAL precisa ter path de vaga
    (senao toda vaga publicada na raiz seria marcada — anti-FP).
    """
    try:
        from urllib.parse import urlsplit
        orig = urlsplit(str(original_url or ""))
        final = urlsplit(str(final_url or ""))
    except ValueError:
        return False
    if not final.path or final.path == "/":
        # so e redirect-para-homepage se o original NAO era homepage
        return bool(orig.path) and orig.path != "/"
    return False


def parse_job_description(html: str) -> str | None:
    """Descricao completa da vaga a partir do HTML da pagina (F20; pura).

    Parser simples e honesto, SEM LLM — em ordem de confiabilidade:

    1. JSON-LD ``jobPosting.description`` (schema.org; padrao dos boards);
    2. meta ``og:description`` (boards modernos);
    3. meta ``description``.

    Devolve ``None`` quando nada e extraiivel (o chamador mantem a
    descricao original — nunca piora). O texto e normalizado (tags
    stripadas, espacos colapsados) e truncado em 16KB (descricao de vaga
    real e < 16KB; protege o JSON de pagas-por-byte gigantes).
    """
    if not html:
        return None
    # 1. JSON-LD
    import html as _html_mod
    import json as _json
    for m in _JSON_LD_JOB_RE.finditer(html):
        try:
            data = _json.loads(m.group(1).strip())
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            node = obj.get("@type", "")
            types = node if isinstance(node, list) else [node]
            if not any("JobPosting" in str(t) for t in types):
                continue
            desc = obj.get("description")
            if isinstance(desc, str) and desc.strip():
                return _clean_description(desc)
    # 2. og:description / 3. meta description — janela de 96KB (Thales
    # real: og:description na pos 67.694; job pages modernos colocam as
    # metas depois de bundles de CSS/JS) e parser tolerante à ordem dos
    # atributos (content antes de name).
    for key, min_len in (("og:description", 120), ("description", 120)):
        raw = _meta_content(html[:96_768], key)
        if raw:
            text = _html_mod.unescape(raw).strip()
            if len(text) >= min_len:
                return _clean_description(text)
    return None


_DESCRIPTION_CAP = 16 * 1024
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_description(text: str) -> str:
    """Normaliza a descricao extraida: strip de tags, espacos colapsados."""
    import html as _html_mod
    cleaned = _html_mod.unescape(text)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    cleaned = re.sub(r" ?\n ?", "\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned[:_DESCRIPTION_CAP]


def check_liveness(
    jobs: list[dict],
    *,
    timeout: float = LIVENESS_TIMEOUT_S,
    delay: float = LIVENESS_DELAY_S,
    deadline_s: float = LIVENESS_DEADLINE_S,
    opener=None,
    log=None,
    return_details: bool = False,
    short_description_limit: int = 500,
):
    """GET nos ``job.url`` (http/https) de ``jobs``; devolve ids mortos.

    F11 (hard-dead 404/410) + F20 (soft-dead por corpo/redirect/shell) +
    F20 (hidratacao de descricao curta no MESMO passe).

    ``return_details=False`` (default, compat F11): devolve apenas o
    ``set`` de ids mortos. ``return_details=True``: devolve a tupla
    ``(dead_ids, {job_id: descricao_hidratada}, stats)`` — usado pelo
    refresh_daily (F20) para aplicar a hidratacao e re-avaliar
    aplicabilidade; ``short_description_limit`` e o limiar de descricao
    curta (spec F20 item 3: ex. 500).

    ``jobs``: lista ORDENADA do topo exibido (o chamador decide o corte —
    refresh_daily passa o top exibido pos regra 2/empresa). Cada job
    contribui no maximo 1 request. ``opener`` injetavel (testes/CI sem
    rede; default ``urllib.request.urlopen``). ``log`` = logging.Logger
    opcional. Best-effort TOTAL: qualquer problema interno devolve um
    conjunto possivelmente vazio — nunca levanta.
    """
    dead, bodies, stats = check_liveness_v2(
        jobs, timeout=timeout, delay=delay, deadline_s=deadline_s,
        opener=opener, log=log, want_bodies=True,
        short_description_limit=short_description_limit,
    )
    if return_details:
        return dead, bodies, stats
    return dead


def check_liveness_v2(
    jobs: list[dict],
    *,
    timeout: float = LIVENESS_TIMEOUT_S,
    delay: float = LIVENESS_DELAY_S,
    deadline_s: float = LIVENESS_DEADLINE_S,
    opener=None,
    log=None,
    want_bodies: bool = True,
    max_bytes: int = LIVENESS_MAX_BYTES,
    short_description_limit: int = 500,
) -> tuple[set[str], dict[str, str], dict]:
    """Estagio completo de vitalidade + hidratacao (F20). Devolve
    ``(dead_ids, {job_id: descricao_hidratada}, estatisticas)``.

    Um UNICO passe GET sequencial por vaga do top exibido: o corpo serve
    ao soft-dead check (i-iii) E a hidratacao de descricao curta.

    - ``dead_ids``: hard-dead (404/410) + soft-dead (marcador de corpo /
      redirect-para-homepage / shell SPA). Mesma semantica F11: desce do
      top exibido; o JSON/CSV ficam intactos.
    - ``bodies``: para vagas VIVAS com descricao curta (< ``short_description_limit``
      chars) e corpo parseavel, a descricao completa extraida (JSON-LD ->
      og:description -> meta description). Vagas mortas nao hidratam (o
      corpo e de anuncio encerrado); fetch/parse falho = ausencia do mapa
      (a descricao original permanece — nunca piora).
    - ``stats``: contadores do passe (attempts/http_responses/net_errors/
      soft_dead/{marker,redirect,shell}/hydrated/hydration_failed/
      duration_s) para o log e o relatorio da fase.

    ``want_bodies=False`` = modo so-vitalidade (o parse de descricao e
    pulado; usado pelo ``check_liveness`` compativel).

    Best-effort TOTAL (nunca levanta; falha total de rede = nada marcado).
    """
    def _info(msg: str, *args) -> None:
        if log is not None:
            log.info(msg, *args)
        else:
            print("liveness: " + (msg % args if args else msg))

    def _warn(msg: str, *args) -> None:
        if log is not None:
            log.warning(msg, *args)
        else:
            print("liveness(WARN): " + (msg % args if args else msg))

    open_url = opener or urllib.request.urlopen
    started = time.monotonic()
    dead: set[str] = set()
    bodies: dict[str, str] = {}
    attempts = 0
    http_responses = 0  # qualquer resposta HTTP recebida (inclui 404/410)
    net_errors = 0
    soft_dead = 0
    hydrated = 0
    hydration_failed = 0
    short_candidates = 0
    try:
        for idx, job in enumerate(jobs):
            jid = str(job.get("id") or "")
            url = str(job.get("url") or "").strip()
            if not jid or not url.lower().startswith(("http://", "https://")):
                continue  # sem id/url verificavel: nao marcavel
            if time.monotonic() - started > deadline_s:
                _warn("deadline de %.0fs atingido apos %d checks; "
                      "seguindo com %d morta(s) confirmada(s)",
                      deadline_s, attempts, len(dead))
                break
            if idx > 0 and delay > 0:
                time.sleep(delay)
            attempts += 1
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": LIVENESS_UA},
            )
            final_url = url
            body_text = ""
            body_len = 0
            try:
                with open_url(req, timeout=timeout) as resp:
                    http_responses += 1
                    final_url = str(getattr(resp, "url", "") or url)
                    # corpo sempre lido: os marcadores soft-dead (F20)
                    # vivem nele. Fake openers de teste podem nao ter
                    # read() — getattr gracioso (corpo vazio = so o
                    # hard-dead 404/410 vale, comportamento F11 puro).
                    read = getattr(resp, "read", None)
                    raw: bytes = read(max_bytes + 1) if callable(read) else b""  # type: ignore[assignment]
                    if not isinstance(raw, (bytes, bytearray)):
                        raw = b""
                    body_len = len(raw)
                    if body_len > max_bytes:
                        body_len = max_bytes  # truncado: marcadores vivem no inicio
                    body_text = raw[:max_bytes].decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                # HTTPError E uma resposta HTTP do servidor (site no ar).
                http_responses += 1
                if exc.code in DEAD_STATUS:
                    dead.add(jid)
                    _info("morta %s: %s -> HTTP %d", jid, url, exc.code)
                continue
            except Exception:  # noqa: BLE001 — timeout/DNS/SSL/bloqueio
                net_errors += 1  # 403/429 chegam como HTTPError; rede nao
                continue

            # ---- soft-dead checks (so respostas 2xx chegam aqui) ----
            marker = _soft_dead_in_body(body_text)
            if marker is not None:
                dead.add(jid)
                soft_dead += 1
                _info("soft-dead %s: corpo contem %r (%s)", jid, marker, url)
                continue
            if _final_path_is_homepage(final_url, url):
                dead.add(jid)
                soft_dead += 1
                _info("soft-dead %s: redirect para homepage (%s -> %s)",
                      jid, url, final_url)
                continue
            if _is_spa_shell(body_text, body_len):
                dead.add(jid)
                soft_dead += 1
                _info("soft-dead %s: shell SPA de board (%d bytes, %s)",
                      jid, body_len, url)
                continue

            # ---- hidratacao (vaga VIVA com descricao curta) ----
            if want_bodies and jid not in dead:
                current = str(job.get("description") or "")
                if len(current) < short_description_limit:
                    short_candidates += 1
                    desc = parse_job_description(body_text)
                    if desc and len(desc) > len(current):
                        bodies[jid] = desc
                        hydrated += 1
                    else:
                        hydration_failed += 1
    except Exception as exc:  # noqa: BLE001 — estagio nunca derruba o run
        _warn("estagio falhou (%s: %s); seguindo sem novas marcas",
              type(exc).__name__, exc)
        duration = time.monotonic() - started
        stats = {
            "attempts": attempts, "http_responses": http_responses,
            "net_errors": net_errors, "soft_dead": soft_dead,
            "dead": len(dead), "hydrated": hydrated,
            "hydration_failed": hydration_failed,
            "short_candidates": short_candidates,
            "duration_s": round(duration, 1),
        }
        return dead, bodies, stats
    # Falha TOTAL de rede: nenhuma resposta HTTP de nenhuma tentativa —
    # nao ha evidencia de nada; nao marca ninguem (spec).
    duration = time.monotonic() - started
    if attempts > 0 and http_responses == 0 and net_errors == attempts:
        _warn("falha total de rede (%d/%d tentativas sem resposta HTTP); "
              "NENHUMA vaga marcada", net_errors, attempts)
        stats = {
            "attempts": attempts, "http_responses": http_responses,
            "net_errors": net_errors, "soft_dead": 0,
            "dead": set(), "hydrated": 0, "hydration_failed": 0,
            "short_candidates": short_candidates,
            "duration_s": round(duration, 1),
        }
        return set(), bodies, stats
    _info("%d checks: %d morta(s) (%d soft), %d hidratada(s), "
          "%d erro(s) de rede ignorado(s)",
          attempts, len(dead), soft_dead, hydrated, net_errors)
    stats = {
        "attempts": attempts, "http_responses": http_responses,
        "net_errors": net_errors, "soft_dead": soft_dead,
        "dead": len(dead), "hydrated": hydrated,
        "hydration_failed": hydration_failed,
        "short_candidates": short_candidates,
        "duration_s": round(duration, 1),
    }
    return dead, bodies, stats


if __name__ == "__main__":  # uso manual: python scripts/url_liveness.py data/eligible_jobs.json
    import json
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/eligible_jobs.json")
    jobs = json.loads(path.read_text(encoding="utf-8"))
    top = jobs[: int(sys.argv[2]) if len(sys.argv) > 2 else 50]
    dead, bodies, stats = check_liveness_v2(top)
    print("dead ids:", sorted(dead))
    print("hydrated:", len(bodies), "| stats:", stats)
