"""Testes F72 — auditoria viva do registry: o runner batch, 100% OFFLINE.

O ``scripts/audit_registry.py`` e a UNICA ferramenta do repo com rede
permitida (spec F72: batch ``verify_companies --fetch`` sobre TODAS as
entradas do registry, guardrails de pacing/janela/checkpoint). Esta suíte
trava o comportamento DETERMINÍSTICO dele sem nunca tocar rede:

1. **parse_window** — ``HH:MM-HH:MM`` (UTC) parseia; ``none``/vazio desliga;
   inversão (inicio >= fim) e lixo rejeitados com SystemExit (nunca silencioso);
2. **window_sleep_seconds** — o guard ANTECIPA a janela proibida: um fetch
   so inicia se ``agora + custo maximo`` termina ANTES do inicio da janela
   (ou a janela ja passou); caso contrario dorme ate o fim (+1s). Pura em
   relacao ao ``now`` recebido — determinística em qualquer data de execucao;
3. **classify_company** — desfechos do ``collect_company`` mapeiam para
   healthy/empty/error. Fixtures VERBATIM da auditoria real de 20/10/2026
   (Statista ashby; Adyen greenhouse+smartrecruiters empty; AkzoNobel
   successfactors 500 RetryExhausted; BCG bamboohr+phenom:nan+icims) e
   casos controlados para os desfechos restantes (empty puro, timeout,
   not_found, skipped-only, fatal);
4. **load_checkpoint** — RESUMIVEL: linhas completas voltam indexadas por
   empresa; linha truncada (crash no meio do append) e linha sem
   name/result sao ignoradas SEM derrubar o lote; arquivo ausente = vazio;
   idempotente em re-execucao;
5. **registry** — o batch cobre TODAS as entradas (145, re-ancora F71) e o
   runner expoe main() com os guardrails nos args;
6. **CI (F78)** — ``test_f72`` e descoberto por ``ci_discover_tests`` (a
   linha morta ``tests=`` continua MORTA no ci.yml — E1 persiste).

Zero rede, zero escrita em ``data/`` (tmp via tempfile). Uso:
    .venv/bin/python scripts/test_f72.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, time as dtime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent / "src"))

FAILURES: list[str] = []
N = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _load_runner():
    """Importa scripts/audit_registry.py como modulo (sem executa-lo)."""
    spec = importlib.util.spec_from_file_location(
        "audit_registry", SCRIPTS / "audit_registry.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit = _load_runner()

# ---------------------------------------------------------------------------
# Fixtures VERBATIM da auditoria real (20/10/2026, checkpoint do lote F72).
# Summary do collect_company exatamente como devolvido pelo caminho do
# verify_companies --fetch (limit=8, timeout=30) — sem edicao.
# ---------------------------------------------------------------------------
FX_STATISTA_OK = {
    "ok": [["ashby:statista", 8, "0.5s"]],
    "empty": [], "timeout": [], "failed": [], "skipped": [],
    "not_found": False,
    "companies": {"ashby:statista": "statista"},
}
FX_ADYEN_OK_EMPTY = {
    "ok": [["greenhouse:adyen", 8, "1.8s"]],
    "empty": [["smartrecruiters:adyen", "0.7s"]],
    "timeout": [], "failed": [], "skipped": [],
    "not_found": False,
    "companies": {"greenhouse:adyen": "adyen", "smartrecruiters:adyen": "Adyen"},
}
FX_AKZONOBEL_500 = {
    "ok": [], "empty": [], "timeout": [],
    "failed": [[
        "successfactors:careers", "FETCH_ERROR",
        "RetryExhaustedError: SuccessFactorsScraper('https://careers.akzonobel.com'): "
        "https://careers.akzonobel.com/sitemal.xml returned 500 after 3 attempts",
    ]],
    "skipped": [],
    "not_found": False,
    "companies": {},
}
FX_BCG_MULTI = {
    "ok": [["bamboohr:bcg", 3, "0.9s"], ["phenom:nan", 8, "2.3s"]],
    "empty": [["icims:bcg", "0.9s"]],
    "timeout": [], "failed": [], "skipped": [],
    "not_found": False,
    "companies": {
        "bamboohr:bcg": "bcg", "icims:bcg": "bcg",
        "phenom:nan": "careers.bcg.com",
    },
}
# Casos CONTROLADOS (shape do summary, valores sinteticos minimal): a regra de
# classificacao precisa apanhar TODOS os desfechos, nao so os observados.
FX_EMPTY_ONLY = {"ok": [], "empty": [["greenhouse:x", "1.0s"]], "timeout": [],
                 "failed": [], "skipped": [], "not_found": False, "companies": {}}
FX_TIMEOUT_ONLY = {"ok": [], "empty": [], "timeout": [["workday:a/b", "TIMEOUT", "x"]],
                   "failed": [], "skipped": [], "not_found": False, "companies": {}}
FX_NOT_FOUND = {"ok": [], "empty": [], "timeout": [], "failed": [], "skipped": [],
                "not_found": True, "companies": {}}
FX_SKIPPED_ONLY = {"ok": [], "empty": [], "timeout": [], "failed": [],
                   "skipped": ["oracle:x"], "not_found": False, "companies": {}}
FX_FATAL = {"ok": [], "empty": [], "timeout": [], "failed": [], "skipped": [],
            "not_found": False, "companies": {},
            "fatal": "KeyboardInterrupt: audit killed"}


def group_a() -> None:
    print("A. parse_window — janela proibida HH:MM-HH:MM (UTC)")
    w = audit.parse_window("09:00-09:15")
    check("a1. '09:00-09:15' -> (09:00, 09:15)",
          w == (dtime(9, 0), dtime(9, 15)), f"got {w}")
    check("a2. 'none' e '' desligam o guard (None)",
          audit.parse_window("none") is None and audit.parse_window("") is None)
    for bad, why in [("09:15-09:00", "inicio >= fim"), ("09-15", "sem HH:MM"),
                     ("09:00-09:00", "janela vazia"), ("ab:cd-10:00", "lixo")]:
        try:
            audit.parse_window(bad)
            check(f"a3. {bad!r} ({why}) rejeitado", False, "aceitou sem erro")
        except SystemExit:
            check(f"a3. {bad!r} ({why}) rejeitado com SystemExit", True)


def group_b() -> None:
    print("B. window_sleep_seconds — o guard ANTECIPA a janela (puro em now)")
    utc = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    w = (dtime(9, 0), dtime(9, 15))
    check("b1. 08:00 + custo 120s termina 08:02 < 09:00 -> livre (0.0)",
          audit.window_sleep_seconds(utc, w, 120.0) == 0.0)
    near = datetime(2026, 10, 20, 8, 59, tzinfo=timezone.utc)
    s = audit.window_sleep_seconds(near, w, 120.0)
    check("b2. 08:59 + 120s atravessaria 09:00 -> dorme ate 09:15 (+1s)",
          abs(s - 961.0) < 1e-6, f"got {s}s (esperado 961)")
    inside = datetime(2026, 10, 20, 9, 5, tzinfo=timezone.utc)
    s2 = audit.window_sleep_seconds(inside, w, 10.0)
    check("b3. dentro da janela (09:05) -> dorme ate o fim (+1s)",
          abs(s2 - (10 * 60 + 1)) < 1e-6, f"got {s2}s (esperado 601)")
    after = datetime(2026, 10, 20, 9, 16, tzinfo=timezone.utc)
    check("b4. 09:16 (janela passou) -> livre",
          audit.window_sleep_seconds(after, w, 300.0) == 0.0)
    check("b5. janela=None nunca bloqueia (mesmo em cima da hora)",
          audit.window_sleep_seconds(inside, None, 300.0) == 0.0)
    check("b6. expected_max<=0 desarma o guard (explicito)",
          audit.window_sleep_seconds(inside, w, 0.0) == 0.0)
    edge = datetime(2026, 10, 20, 8, 58, tzinfo=timezone.utc)
    check("b7. borda: 08:58 + 120s == 09:00 EXATO -> livre (<=, nao atravessa)",
          audit.window_sleep_seconds(edge, w, 120.0) == 0.0)


def group_c() -> None:
    print("C. classify_company — desfechos -> healthy/empty/error")
    for name, fx, want in [
        ("Statista healthy verbatim (ashby 8 vagas)", FX_STATISTA_OK, "healthy"),
        ("Adyen healthy com empty adicional (multi-tenant)", FX_ADYEN_OK_EMPTY, "healthy"),
        ("BCG healthy multi verbatim (bamboohr+phenom:nan ok, icims empty)",
         FX_BCG_MULTI, "healthy"),
        ("AkzoNobel error verbatim (successfactors 500)", FX_AKZONOBEL_500, "error"),
        ("empty puro controlado -> empty", FX_EMPTY_ONLY, "empty"),
        ("timeout puro controlado -> error", FX_TIMEOUT_ONLY, "error"),
        ("not_found controlado -> error", FX_NOT_FOUND, "error"),
        ("skipped-only controlado -> error", FX_SKIPPED_ONLY, "error"),
        ("fatal (excecao capturada pelo runner) -> error", FX_FATAL, "error"),
    ]:
        got = audit.classify_company(fx)
        check(f"c. {name}", got == want, f"got {got}")
    # Um ok real conta 8 (limit do batch), mas a classe depende so do shape.
    check("c. summary verbatim de Statista serializa sem perda (json roundtrip)",
          json.loads(json.dumps(FX_STATISTA_OK))["ok"][0][1] == 8)


def group_d() -> None:
    print("D. load_checkpoint — resumivel, crash-proof, idempotente")
    with tempfile.TemporaryDirectory() as td:
        ck = Path(td) / "audit_checkpoint.jsonl"
        rec1 = {"name": "Statista", "result": {"health": "healthy"}}
        rec2 = {"name": "Celonis", "result": {"health": "healthy"}}
        good = json.dumps(rec1) + "\n" + json.dumps(rec2) + "\n"
        ck.write_text(good + '{"name": "Trunc", "resu', encoding="utf-8")
        done = audit.load_checkpoint(ck)
        check("d1. 2 linhas completas carregadas, truncada no fim ignorada",
              set(done) == {"Statista", "Celonis"}, f"got {sorted(done)}")
        ck.write_text(good + json.dumps({"name": "SemResult"}) + "\n", encoding="utf-8")
        done2 = audit.load_checkpoint(ck)
        check("d2. linha sem 'result' ignorada (nao conta como auditada)",
              set(done2) == {"Statista", "Celonis"})
        check("d3. arquivo inexistente -> {} (batch comeca do zero)",
              audit.load_checkpoint(Path(td) / "nope.jsonl") == {})
        done3 = audit.load_checkpoint(ck)
        check("d4. idempotente: re-leitura devolve o mesmo conjunto",
              {k: done2[k] for k in done2} == {k: done3[k] for k in done3})
        # Linha completa preserva o payload inteiro (result verbatim).
        check("d5. payload 'result' preservado integro (resume sem perda)",
              done2["Statista"]["result"]["health"] == "healthy")


def group_e() -> None:
    print("E. registry — o batch cobre TODAS as entradas (re-ancora F71)")
    from internship_finder.registry import CompanyRegistry

    entries = CompanyRegistry().entries
    check("e1. registry tem 145 entradas (F71: contagem == soma das ondas)",
          len(entries) == 145, f"got {len(entries)}")
    check("e2. runner expoe main() (entrypoint do lote)",
          callable(getattr(audit, "main", None)))
    src = (SCRIPTS / "audit_registry.py").read_text(encoding="utf-8")
    for needle, why in [
        ("--pacing", "guardrail 1 req/2s entre empresas"),
        ("--window", "janela proibida UTC"),
        ("--checkpoint", "resumivel"),
        ("load_checkpoint(ckpt_path)", "resume pula ja-auditadas"),
    ]:
        check(f"e3. guardrail no runner: {needle} ({why})", needle in src)


def group_f() -> None:
    print("F. CI (F78) — auto-discovery pega a suíte nova")
    # NOTA: os contratos DO ci.yml (array literal morto, invocação do
    # discovery, guarda de vazio) pertencem ao scripts/test_f78.py — o E1
    # dele proíbe QUALQUER outra suíte de citar o padrão da linha morta,
    # então aqui vai SOMENTE o membership: test_f72 precisa ser descoberto.
    sys.path.insert(0, str(SCRIPTS))
    try:
        import ci_discover_tests
        discovered = ci_discover_tests.discover_tests()
    finally:
        sys.path.remove(str(SCRIPTS))
    check("f1. 'test_f72' descoberto pelo ci_discover_tests (ordem alfabetica)",
          "test_f72" in discovered, f"{len(discovered)} suítes")


def main() -> int:
    print("F72 — auditoria viva do registry: runner batch (offline, fixtures reais)")
    group_a()
    group_b()
    group_c()
    group_d()
    group_e()
    group_f()

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"F72: {len(FAILURES)} de {N} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"F72: TUDO OK — {N} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
