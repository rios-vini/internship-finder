"""F76 — Robustez upstream: modulo fetch (E1) do estagio dataset (test_f76).

Trava o comportamento NOVO da fase — a camada ``dataset_fetch`` aplicada ao
manifest E as fatias (equivalente proprio dos padroes do upstream
``ats_scrapers.fetch`` v0.3.0):

GRUPO A — mapa de status, fail-loud NAO-retryavel (opener scriptado):
  A1. 403 -> BlockedHTTPStatusError IMEDIATO (1 tentativa, zero sleeps).
  A2. 406 -> idem (WAF/load balancer; upstream _BLOCKED_STATUSES).
  A3. 404 -> HTTPStatusError explicito com status na excecao, 1 tentativa.
  A4. 400 -> HTTPStatusError nao-retryavel, 1 tentativa.
  A5. taxonomia: todas as excecoes novas sao DatasetFetchError e carregam
      ``.url``.

GRUPO B — retryable + Retry-After (sleep COLETADO, zero espera real):
  B1. 429 + Retry-After "7" -> espera EXATAMENTE 7.0; 2a tentativa 200 ->
      JSON parseado.
  B2. 429 SEM header -> backoff exponencial (base 2.0 — default da casa,
      mesmo numero do direct_fetch F4).
  B3. 503 x3 (max_retries=3) -> RetryExhaustedError com status 503;
      sleeps [2.0, 4.0].
  B4. Retry-After "300" -> respeitado ate o TETO (60s) — desvio CONSCIENTE
      documentado no modulo (lote diario de ~63 fatias com budget entre
      fatias; o upstream nao tem teto porque e scraper por-tenant).
  B5. falha de rede (URLError) x3 -> RetryExhaustedError com 'falha de
      rede'; sleeps [2.0, 4.0].
  B6. 408 e retryavel (paridade com o upstream — nao so 429/5xx).
  B7. download_file com 429-then-200 -> o retry vale para a FATIA:
      (bytes, sha256) corretos apos a 2a tentativa.

GRUPO C — 200-falso (HTML de WAF onde se espera JSON/CSV):
  C1. fetch_json: 200 + corpo HTML -> MalformedJSONError (E ValueError —
      contrato F80) com o comeco do corpo na mensagem.
  C2. download_file: 200 + corpo HTML de 3 MiB -> MalformedCSVError com
      UM UNICO read (early-abort: pagina de N GB nunca chega ao disco) e
      dest NUNCA criado.
  C3. _looks_like_html: gate apertado (doctype/html/head/body/script/title
      True; BOM+brancos True; header CSV False; '<' sem marcador False).
  C4. RETROCOMPAT F80 C1: fetch_manifest REAL via file:// com HTML ->
      ValueError (MalformedJSONError) com 'nao e JSON' + comeco do corpo.
  C5. RETROCOMPAT F80 C2: fetch_manifest via file:// JSON -> dict COMPLETO
      (by_ats DENTRO).
  C6. RETROCOMPAT F80 D4: _http_fetch via file:// CSV -> (bytes, sha256) +
      conteudo em disco idempotente.

GRUPO D — integracao com o estagio (collect_dataset_jobs, offline):
  D1. fatia com erro da camada (http_fetch simulando o que o default agora
      levanta: BlockedHTTPStatusError) -> entry failed + forense
      per_ats[name]['error'] com o tipo E o status; demais fatias
      prosseguem; status ok.
  D2. TODAS as fatias falham -> status 'failed' (contrato F3/F80) com o
      forense em CADA entry.
  D3. retrocompat injecao http_fetch (padrao F80/F70): fatia boa -> entry
      SEM chave 'error' (forense so existe em falha).
  D4. determinismo: 2 coletas identicas -> summaries identicos.

GRUPO E — contratos e membership:
  E1. MalformedJSONError/MalformedCSVError: DatasetFetchError E ValueError
      (dupla heranca — wrappers contra qualquer um dos dois).
  E2. file:// NUNCA passa pelo maquinario de retry (sleep nao chamado).
  E3. UA preservado: o Request montado carrega internship-finder/0.1
      (pitfall F3: o UA default do urllib e 403 no manifest do R2).
  E4. json_loads morto removido do dataset_source (F76: o parse vive na
      camada dataset_fetch).
  E5. membership: test_f76 na suite descoberta (auto-discovery F78).

100% offline: respostas injetadas via opener scriptado; sleeps coletados
(zero espera real); file:// para os caminhos REAIS do dataset_source.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import dataset_fetch, dataset_source  # noqa: E402
from internship_finder.dataset_fetch import (  # noqa: E402
    BLOCKED_STATUSES,
    DEFAULT_RETRY_BASE_DELAY,
    MalformedCSVError,
    MalformedJSONError,
    BlockedHTTPStatusError,
    DatasetFetchError,
    HTTPStatusError,
    RetryExhaustedError,
    download_file,
    fetch_json,
    _looks_like_html,
)
from internship_finder.dataset_source import (  # noqa: E402
    _http_fetch,
    collect_dataset_jobs,
    fetch_manifest,
)

FAILURES: list[str] = []

# Header minimo do dataset com as 9 colunas exigidas pelo prefilter (F80).
DATASET_HEADER = [
    "title", "company", "url", "ats_id", "location", "country_iso",
    "description", "employment_type", "posted_at",
]

HTML_BODY = (
    b"<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare"
    b"</title></head><body>You are being blocked.</body></html>"
)


def check(desc: str, ok: bool, msg: str = "") -> None:
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {desc}" + (f" -> {msg}" if msg and not ok else ""))
    if not ok:
        FAILURES.append(desc)


class FakeResponse:
    """Resposta file-like com status/headers/corpo (contrato do _Response)."""

    def __init__(self, status, body=b"", headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        if size is None or size < 0 or size >= len(self._body):
            chunk, self._body = self._body, b""
        else:
            chunk, self._body = self._body[:size], self._body[size:]
        return chunk


class FakeOpener:
    """Opener scriptado: devolve/levanta o proximo passo a cada chamada."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[str] = []
        self.last_request = None

    def __call__(self, req, timeout=None):
        self.calls.append(req.full_url)
        self.last_request = req
        if not self.script:
            raise AssertionError("script do FakeOpener esgotado")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def spy_sleep(sink):
    def _sleep(seconds):
        sink.append(seconds)
    return _sleep


def raises(func, *args, exc=Exception, **kwargs):
    try:
        func(*args, **kwargs)
    except exc as e:  # noqa: BLE001
        return True, str(e)
    return False, "nao levantou"


# ---------------------------------------------------------------------------
# Fixtures do estagio (manifest completo no shape F80)
# ---------------------------------------------------------------------------


def full_manifest(by_ats):
    return {
        "version": "2.0",
        "generated_at": "2026-10-20T10:00:00Z",
        "stats": {
            "schema_version": "2.0",
            "schema_columns": list(DATASET_HEADER) + ["extra_upstream"],
        },
        "by_ats": by_ats,
    }


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DATASET_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path.read_bytes()


def make_row(url, title, company, iso="de", location="Berlin, DE"):
    return {
        "title": title,
        "company": company,
        "url": url,
        "ats_id": None,
        "location": location,
        "country_iso": iso,
        "description": None,
        "employment_type": None,
        "posted_at": None,
    }


def fetch_from(files):
    """http_fetch de fixtures (padrao F80): copia o arquivo para dest."""
    def _fetch(url, dest):
        src = Path(files[url])
        dest = Path(dest)
        dest.write_bytes(src.read_bytes())
        data = src.read_bytes()
        return len(data), hashlib.sha256(data).hexdigest()
    return _fetch


# ---------------------------------------------------------------------------
# A. Mapa de status — fail-loud NAO-retryavel
# ---------------------------------------------------------------------------


def test_status_map() -> None:
    print("== A. mapa de status: 403/406/4xx -> erro explicito imediato ==")
    for idx, status in ((1, 403), (2, 406)):
        op = FakeOpener([FakeResponse(status, body=b"blocked")])
        sink: list[float] = []
        ok, msg = raises(
            fetch_json, "https://r2/x.json", opener=op, sleep=spy_sleep(sink),
            exc=BlockedHTTPStatusError)
        check(f"A{idx}a. HTTP {status} -> BlockedHTTPStatusError", ok, msg)
        check(f"A{idx}b. imediato: 1 tentativa, ZERO sleeps",
              len(op.calls) == 1 and sink == [],
              f"calls={len(op.calls)} sleeps={sink}")
        check(f"A{idx}c. mensagem denuncia o bloqueio (fail-loud)",
              ok and str(status) in msg and "bloqueando" in msg, msg)

    op = FakeOpener([FakeResponse(404, body=b"gone")])
    ok, msg = raises(fetch_json, "https://r2/x.json", opener=op,
                     sleep=spy_sleep([]), exc=HTTPStatusError)
    err = None
    try:
        fetch_json("https://r2/x.json", opener=FakeOpener([FakeResponse(404)]),
                   sleep=spy_sleep([]))
    except HTTPStatusError as e:
        err = e
    check("A3a. 404 -> HTTPStatusError", ok, msg)
    check("A3b. status 404 NA excecao (.status)", err is not None and err.status == 404,
          str(err))
    check("A3c. nao-retryavel: 1 tentativa", len(op.calls) == 1, f"{len(op.calls)}")

    ok, _ = raises(fetch_json, "https://r2/x.json",
                   opener=FakeOpener([FakeResponse(400)]), sleep=spy_sleep([]),
                   exc=HTTPStatusError)
    check("A4. 400 -> HTTPStatusError nao-retryavel", ok, _)

    # A5. taxonomia — todas carregam .url e sao DatasetFetchError
    cases = [
        (BlockedHTTPStatusError("x", url="u1"),),
        (HTTPStatusError("x", url="u2", status=404),),
        (RetryExhaustedError("x", url="u3"),),
        (MalformedJSONError("x", url="u4"),),
        (MalformedCSVError("x", url="u5"),),
    ]
    all_ok = all(
        isinstance(c[0], DatasetFetchError) and getattr(c[0], "url", None)
        for c in cases
    )
    check("A5. taxonomia: 5 classes sao DatasetFetchError com .url", all_ok,
          str([type(c[0]).__name__ for c in cases]))
    check("A5b. 403/406 sao EXATAMENTE os bloqueados (paridade upstream)",
          BLOCKED_STATUSES == frozenset({403, 406}), str(sorted(BLOCKED_STATUSES)))


# ---------------------------------------------------------------------------
# B. Retryable + Retry-After (sleep coletado)
# ---------------------------------------------------------------------------


def test_retries() -> None:
    print("== B. 408/429/5xx: backoff + Retry-After (sleep coletado) ==")
    # B1. Retry-After numerico respeitado EXATAMENTE
    op = FakeOpener([
        FakeResponse(429, headers={"Retry-After": "7"}),
        FakeResponse(200, body=b'{"ok": 1}'),
    ])
    sink: list[float] = []
    data = fetch_json("https://r2/x.json", opener=op, sleep=spy_sleep(sink))
    check("B1a. 429 com Retry-After 7 -> espera EXATAMENTE 7.0", sink == [7.0],
          str(sink))
    check("B1b. 2a tentativa 200 -> JSON parseado", data == {"ok": 1}
          and len(op.calls) == 2, f"{len(op.calls)} chamadas")

    # B2. sem header -> backoff exponencial (base da casa: 2.0)
    op = FakeOpener([FakeResponse(429), FakeResponse(200, body=b"[]")])
    sink = []
    fetch_json("https://r2/x.json", opener=op, sleep=spy_sleep(sink))
    check("B2. 429 SEM Retry-After -> backoff da casa (2.0)",
          sink == [DEFAULT_RETRY_BASE_DELAY] and DEFAULT_RETRY_BASE_DELAY == 2.0,
          f"{sink} base={DEFAULT_RETRY_BASE_DELAY}")

    # B3. esgotando tentativas com 503
    op = FakeOpener([FakeResponse(503), FakeResponse(503), FakeResponse(503)])
    sink = []
    ok, msg = raises(fetch_json, "https://r2/x.json", opener=op,
                     sleep=spy_sleep(sink), exc=RetryExhaustedError)
    err = None
    try:
        fetch_json("https://r2/x.json",
                   opener=FakeOpener([FakeResponse(503)] * 3),
                   sleep=spy_sleep([]))
    except RetryExhaustedError as e:
        err = e
    check("B3a. 503 x3 -> RetryExhaustedError", ok, msg)
    check("B3b. status 503 na excecao", err is not None and err.status == 503,
          str(err))
    check("B3c. sleeps [2.0, 4.0] (exponencial entre tentativas)",
          sink == [2.0, 4.0], str(sink))
    check("B3d. exatamente 3 tentativas (max_retries)", len(op.calls) == 3,
          f"{len(op.calls)}")

    # B4. Retry-After acima do teto -> teto (desvio consciente documentado)
    op = FakeOpener([
        FakeResponse(429, headers={"Retry-After": "300"}),
        FakeResponse(200, body=b"{}"),
    ])
    sink = []
    fetch_json("https://r2/x.json", opener=op, sleep=spy_sleep(sink))
    check("B4. Retry-After 300 -> teto 60.0 (budget do lote protegido)",
          sink == [60.0], str(sink))

    # B5. falha de rede e retryavel como 5xx
    op = FakeOpener([urllib.error.URLError("timed out")] * 3)
    sink = []
    ok, msg = raises(fetch_json, "https://r2/x.json", opener=op,
                     sleep=spy_sleep(sink), exc=RetryExhaustedError)
    check("B5a. URLError x3 -> RetryExhaustedError", ok, msg)
    check("B5b. mensagem denuncia 'falha de rede'", "falha de rede" in msg, msg)
    check("B5c. rede tambem faz backoff [2.0, 4.0]", sink == [2.0, 4.0],
          str(sink))

    # B6. 408 e retryavel (paridade upstream — nao so 429/5xx)
    op = FakeOpener([FakeResponse(408), FakeResponse(200, body=b"{}")])
    sink = []
    fetch_json("https://r2/x.json", opener=op, sleep=spy_sleep(sink))
    check("B6. 408 retryable -> 2a tentativa vence", len(op.calls) == 2
          and len(sink) == 1, f"{len(op.calls)} {sink}")

    # B7. o retry vale para FATIA (download_file), nao so manifest
    body = b"ats_id,title\n1,Werkstudent\n"
    op = FakeOpener([
        FakeResponse(429, headers={"Retry-After": "3"}),
        FakeResponse(200, body=body),
    ])
    sink = []
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "slice.csv"
        nbytes, digest = download_file("https://r2/a.csv", dest,
                                        opener=op, sleep=spy_sleep(sink))
        check("B7a. fatia 429-then-200 -> (bytes, sha256) da 2a tentativa",
              nbytes == len(body)
              and digest == hashlib.sha256(body).hexdigest()
              and dest.read_bytes() == body,
              f"n={nbytes}")
        check("B7b. Retry-After da fatia respeitado", sink == [3.0], str(sink))


# ---------------------------------------------------------------------------
# C. 200-falso (HTML de WAF onde se espera JSON/CSV)
# ---------------------------------------------------------------------------


def test_false_ok() -> None:
    print("== C. 200-falso: HTML onde se espera JSON/CSV ==")
    # C1. fetch_json com 200 + HTML
    op = FakeOpener([FakeResponse(200, body=HTML_BODY)])
    ok, msg = raises(fetch_json, "https://r2/m.json", opener=op,
                     sleep=spy_sleep([]), exc=MalformedJSONError)
    check("C1a. 200 + HTML -> MalformedJSONError", ok, msg)
    check("C1b. E ValueError (contrato F80 preservado)",
          ok and isinstance(MalformedJSONError("x", url="u"), ValueError), msg)
    check("C1c. mensagem carrega o comeco do corpo",
          ok and "<!DOCTYPE html>" in msg and "nao e JSON" in msg, msg)
    check("C1d. sem retry no 200-falso (corpo bom, so nao e JSON)",
          len(op.calls) == 1, f"{len(op.calls)}")

    # C2. download_file com 200 + HTML GRANDE: early-abort
    big_html = HTML_BODY + b"<!-- " + b"x" * (3 * 1024 * 1024) + b" -->"
    resp = FakeResponse(200, body=big_html)
    op = FakeOpener([resp])
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "slice.csv"
        ok, msg = raises(download_file, "https://r2/a.csv", dest, opener=op,
                         sleep=spy_sleep([]), exc=MalformedCSVError)
        check("C2a. 200 + HTML -> MalformedCSVError", ok, msg)
        check("C2b. dest NUNCA criado (abort antes do open)",
              not dest.exists(), str(dest))
        check("C2c. UM UNICO read (pagina de N GB nunca baixa inteira)",
              resp.reads == 1, f"reads={resp.reads}")

    # C3. _looks_like_html: gate apertado
    cases = [
        (HTML_BODY, True),
        (b"<html lang=\"en\"><head></head></html>", True),
        (b"<head><title>blocked</title></head>", True),
        (b"  \t\r\n" + HTML_BODY, True),                      # brancos antes
        (b"\xef\xbb\xbf" + HTML_BODY, True),                  # BOM UTF-8
        (b"ats_id,title,company,url\n1,Werkstudent,A,https://a\n", False),
        (b"company,name\n\"<script>x</script>\",Acme\n", False),
        (b"<plain,csv,header,sem,marcador,html\n", False),     # '<' sem marker
        (b"", False),
    ]
    for body, expected in cases:
        got = _looks_like_html(body)
        tag = "html" if expected else "csv/nao-html"
        check(f"C3. sniff {tag} ({len(body)}B, comeca "
              f"{body[:12]!r}) -> {expected}", got == expected, f"got={got}")

    # C4-C6. RETROCOMPAT: os caminhos REAIS do dataset_source via file://
    with tempfile.TemporaryDirectory() as tmp:
        wall = Path(tmp) / "wall.html"
        wall.write_bytes(HTML_BODY)
        ok, msg = raises(fetch_manifest, wall.as_uri(), exc=ValueError)
        check("C4a. RETROCOMPAT F80 C1: fetch_manifest file:// HTML -> ValueError",
              ok, msg)
        check("C4b. mensagem 'nao e JSON' + corpo (MalformedJSONError)",
              ok and "nao e JSON" in msg and "<!DOCTYPE html>" in msg, msg)

        good = Path(tmp) / "manifest.json"
        good.write_text(json.dumps(
            full_manifest({"acme": {"csv": "https://x/a.csv", "rows": 1}})),
            encoding="utf-8")
        data = fetch_manifest(good.as_uri())
        check("C5. RETROCOMPAT F80 C2: file:// JSON -> dict COMPLETO",
              isinstance(data, dict) and "by_ats" in data and "stats" in data,
              str(sorted(data.keys())))

        csv_path = Path(tmp) / "a.csv"
        body = write_csv(csv_path, [make_row("https://a/1", "Werkstudent X",
                                             "A GmbH")])
        dest = Path(tmp) / "down.csv"
        nbytes, digest = _http_fetch(csv_path.as_uri(), dest)
        check("C6a. RETROCOMPAT F80 D4: (bytes, sha256) do arquivo",
              nbytes == len(body)
              and digest == hashlib.sha256(body).hexdigest(),
              f"n={nbytes}")
        check("C6b. conteudo em disco idempotente",
              dest.read_bytes() == body)


# ---------------------------------------------------------------------------
# D. Integracao com o estagio (collect_dataset_jobs, offline)
# ---------------------------------------------------------------------------


def test_stage_integration() -> None:
    print("== D. integracao: forense de erro na fatia, contratos vivos ==")
    with tempfile.TemporaryDirectory() as tmp:
        pa = Path(tmp) / "a.csv"
        write_csv(pa, [make_row("https://a/1", "Werkstudent A", "A GmbH"),
                       make_row("https://a/2", "Praktikum B", "A GmbH")])
        sha = hashlib.sha256(pa.read_bytes()).hexdigest()

        def fetch_blocked(url, dest):
            if "blocked" in url:
                raise BlockedHTTPStatusError(
                    "https://r2/blocked.csv: HTTP 403 — o WAF/load balancer "
                    "esta bloqueando o cliente (fail-loud, NAO retryavel)",
                    url=url)
            return fetch_from({str(pa): pa})(url, dest)

        by = {
            "acme": {"csv": str(pa), "rows": 2, "sha256": sha},
            "blocked": {"csv": "https://r2/blocked.csv", "rows": 9},
        }
        jobs, summary = collect_dataset_jobs(
            manifest=full_manifest(by), http_fetch=fetch_blocked,
            workdir=Path(tmp))
        e_bad = summary["per_ats"]["blocked"]
        e_ok = summary["per_ats"]["acme"]
        check("D1a. fatia bloqueada -> failed + forense entry['error']",
              e_bad["failed"] is True and "error" in e_bad, str(e_bad))
        check("D1b. forense carrega o TIPO e o status da camada",
              "BlockedHTTPStatusError" in e_bad.get("error", "")
              and "403" in e_bad.get("error", ""), e_bad.get("error", ""))
        check("D1c. demais fatias prosseguem (best-effort F3)",
              e_ok["failed"] is False and summary["jobs"] == 2,
              str(summary["per_ats"]))
        check("D1d. status ok com falha parcial (contrato existente)",
              summary["status"] == "ok" and summary["failed_slices"] == 1,
              summary["status"])

        # D2. TODAS falham -> status failed (contrato F3/F80) + forense em cada
        def fetch_all_fail(url, dest):
            raise RetryExhaustedError(
                "x: HTTP 503 apos 3 tentativas", url=url, status=503)

        by2 = {"acme": {"csv": str(pa), "rows": 2},
               "beta": {"csv": str(pa), "rows": 2}}
        jobs2, summary2 = collect_dataset_jobs(
            manifest=full_manifest(by2), http_fetch=fetch_all_fail,
            workdir=Path(tmp))
        check("D2a. todas falham -> status 'failed', 0 jobs",
              summary2["status"] == "failed" and summary2["jobs"] == 0,
              summary2["status"])
        check("D2b. forense em CADA entry",
              all("error" in e for e in summary2["per_ats"].values()),
              str(summary2["per_ats"]))

        # D3. retrocompat: fatia boa -> entry SEM chave error (so em falha)
        jobs3, summary3 = collect_dataset_jobs(
            manifest=full_manifest({"acme": {"csv": str(pa), "rows": 2,
                                            "sha256": sha}}),
            http_fetch=fetch_from({str(pa): pa}), workdir=Path(tmp))
        check("D3. injecao padrao F80/F70 intacta: ok, 2 jobs, SEM forense",
              summary3["status"] == "ok" and summary3["jobs"] == 2
              and "error" not in summary3["per_ats"]["acme"],
              str(summary3["per_ats"]))

        # D4. determinismo da coleta injetada
        jobs4, summary4 = collect_dataset_jobs(
            manifest=full_manifest({"acme": {"csv": str(pa), "rows": 2,
                                            "sha256": sha}}),
            http_fetch=fetch_from({str(pa): pa}), workdir=Path(tmp))
        check("D4. 2 coletas identicas -> summaries identicos",
              {k: v for k, v in summary3.items() if k != "duration"}
              == {k: v for k, v in summary4.items() if k != "duration"},
              "")


# ---------------------------------------------------------------------------
# E. Contratos e membership
# ---------------------------------------------------------------------------


def test_contracts() -> None:
    print("== E. contratos: heranca dupla, file://, UA, membership ==")
    check("E1. Malformed* sao DatasetFetchError E ValueError",
          issubclass(MalformedJSONError, DatasetFetchError)
          and issubclass(MalformedJSONError, ValueError)
          and issubclass(MalformedCSVError, DatasetFetchError)
          and issubclass(MalformedCSVError, ValueError), "")
    check("E1b. status/retry NAO sao ValueError (nao confundem com parse)",
          not issubclass(BlockedHTTPStatusError, ValueError)
          and not issubclass(HTTPStatusError, ValueError)
          and not issubclass(RetryExhaustedError, ValueError), "")

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.json"
        p.write_text("{}", encoding="utf-8")
        sink: list[float] = []
        fetch_json(p.as_uri(), sleep=spy_sleep(sink))
        dest = Path(tmp) / "d.bin"
        download_file(p.as_uri(), dest, sleep=spy_sleep(sink))
        check("E2. file:// NUNCA dorme (sem retry em esquema sem status)",
              sink == [], str(sink))

    op = FakeOpener([FakeResponse(200, body=b"{}")])
    fetch_json("https://r2/x.json", opener=op, sleep=spy_sleep([]))
    ua = None
    if op.last_request is not None:
        hdrs = {k.lower(): v for k, v in op.last_request.headers.items()}
        ua = hdrs.get("user-agent")
    check("E3. UA preservado: internship-finder/0.1 (pitfall F3 do R2)",
          ua == "internship-finder/0.1", str(ua))

    check("E4. json_loads morto removido do dataset_source",
          not hasattr(dataset_source, "json_loads"), "")

    import ci_discover_tests  # F78: suite = descoberta de scripts/test_*.py
    names = ci_discover_tests.discover_tests()
    check("E5. membership: test_f76 na suite descoberta do CI",
          "test_f76" in names, f"{len(names)} suites")


def main() -> int:
    test_status_map()
    print()
    test_retries()
    print()
    test_false_ok()
    print()
    test_stage_integration()
    print()
    test_contracts()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
