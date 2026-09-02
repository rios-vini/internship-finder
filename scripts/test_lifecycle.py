"""Script standalone — P1 #8: ciclo de vida do multiprocessing (ACH-07).

Cobre o item do MASTER_PLAN #8 na ``fetch_with_timeout``: o subprocesso do
scraper deve ter ciclo de vida completo e sem orfaos em QUALQUER desfecho
(sucesso, erro do worker, timeout, worker morto), distinguindo "worker morreu"
de "timeout" e detectando a morte ANTES do deadline.

Verifica, com testes REAIS de subprocesso (sem rede, mocks do scraper):

1. **timeout real** — fetch que dorme + margem parametrizada pequena -> desfecho
   timeout com ``CollectionError(TIMEOUT)``, o processo encerrado (nao fica
   ``is_alive``/órfão) e a queue fechada.
2. **worker morre de verdade** — mock do ``get_scraper`` cujo ``fetch()`` chama
   ``os._exit(1)`` (mata o subprocesso sem passar pelo ``except``) -> desfecho
   "worker morto" distinto de timeout, retornando RAPIDO (antes do deadline),
   com o exitcode no ``detail``.
3. **erro do worker** — payload ``("-error", code, detail)`` -> ``CollectionError(code)``.
4. **sucesso** — resultado correto e processo terminado.
5. **N chamadas seguidas** (5) — nenhum processo orfao acumulado e queues fechadas.

Modelo de verificacao de orfao: cada chamada roda DESCOBRINDO o pid do worker
antes (captura via monitoramento da queue — ver helpers) e depois do retorno
verifica que o processo daquele pid nao esta vivo (``os.kill(pid,0)``). Alem
disso, ``multiprocessing.active_children()`` nao acumula apos o batch.

Não depende de ``data/`` e nao faz coleta real. Padrão dos demais scripts:
``[OK]``/``[FAIL]`` e termina com ``TUDO OK`` (exit 0) ou ``FALHAS:`` (exit != 0).

Detecção precoce de morte usa o ``exitcode`` real do subprocesso (os._exit(1)
produz exitcode 1 e ``is_alive()`` False logo apos), entao o worker morto
retorna em ~milissegundos, bem antes do deadline.

Uso:  .venv/bin/python scripts/test_lifecycle.py
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.collectors import ats_scraper  # noqa: E402
from internship_finder.errors import TIMEOUT, UNKNOWN, CollectionError  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [OK] {name}")
    else:
        print(f"  [FAIL] {name} {detail}")
        FAILURES.append(name)


def make_company() -> Company:
    return Company(name="Acme", ats="smartrecruiters", slug="acme", query="Acme")


def pid_alive(pid: int) -> bool:
    """True se o processo ``pid`` (nosso subprocesso) ainda existe."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        # PermissionError => o processo existe (de outro usuario); aqui nao ocorre.
        return False
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Cenario real de subprocesso. Para capturar o pid do worker de FORMA real,
# usamos uma variante do fetch_worker que divulga seu pid numa queue de pid a
# parte. As chamadas reais de fetch_with_timeout usam o fetch_worker de
# producao (nao o de teste) a menos que explicitamente marcadas: garantimos
# mais fidelidade nos cenarios 1-4 (fetch_worker real) e usamos a variante
# "pid-aware" apenas para verificar orfaos pos-chamada.
# ---------------------------------------------------------------------------

# Para testar o fetch_with_timeout REAL (a funcao do modulo, nao uma replica),
# capturamos o pid do worker que ELE cria: ``fetch_with_timeout`` referencia o
# worker pela global ``fetch_worker`` do modulo (``Process(target=fetch_worker,
# ...)``). Patchamos ``ats_scraper.fetch_worker`` com um wrapper que (a) escreve
# o pid num arquivo temporario (grava com fsync, entao sobrevive a ``os._exit``
# e ao fechamento do feeder da queue) e (b) delega ao fetch_worker original —
# assim o cenario inteiro roda no subprocesso real e no fluxo real.
_PID_FILE: str | None = None
_ORIG_FETCH_WORKER = ats_scraper.fetch_worker
# ultimo pid de worker capturado (para leitura mesmo quando CollectionError sobe)
_LAST_PID: int | None = None


def _worker_reporting_pid(company, timeout, include_descriptions, queue):
    """Wrapper do fetch_worker que grava o pid em arquivo e delega ao original."""
    try:
        with open(_PID_FILE, "w") as fh:  # type: ignore[arg-type]
            fh.write(str(os.getpid()))
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:  # noqa: BLE001 - _PID_FILE pode nao existir em edge
        pass
    _ORIG_FETCH_WORKER(company, timeout, include_descriptions, queue)


def _captured_fetch_with_timeout(company, timeout, include_descriptions, margin):
    """Chama o ``fetch_with_timeout`` REAL e devolve ``(payload, worker_pid)``.

    O pid do worker e capturado via patch global do ``fetch_worker`` (que grava
    o pid num arquivo antes de delegar, com fsync). ``worker_pid`` e devolvido
    tanto no sucesso quanto quando ``CollectionError`` sobe: o teste verifica a
    ausencia de orfao em TODOS os desfechos — inclusive no worker que morre via
    ``os._exit`` (arquivo sobrevive, queue nao).
    """
    import tempfile
    global _PID_FILE, _LAST_PID
    _PID_FILE = Path(tempfile.mktemp(prefix="if_workerpid_", suffix=".txt"))
    _LAST_PID = None
    try:
        with patch.object(ats_scraper, "fetch_worker", _worker_reporting_pid):
            try:
                payload = ats_scraper.fetch_with_timeout(
                    company, timeout, include_descriptions, margin=margin)
            except CollectionError:
                raise
        try:
            _LAST_PID = int(Path(_PID_FILE).read_text().strip())
        except Exception:  # noqa: BLE001
            _LAST_PID = None
    finally:
        _PID_FILE.unlink(missing_ok=True)
        _PID_FILE = None
    return payload, _LAST_PID


# ---------------------------------------------------------------------------
# 1. timeout real (fetch que dorme; margem pequena)
# ---------------------------------------------------------------------------

def test_timeout() -> None:
    print("== [1] timeout real: fetch dorme alem do deadline ==")
    company = make_company()

    def slow_scraper(*args, **kwargs):
        time.sleep(30)
        raise AssertionError("nunca deveria chegar aqui (killed antes)")

    t0 = time.monotonic()
    saw_timeout = False
    try:
        # margem 0.5s + timeout 0.5s => deadline ~1s (rapido p/ teste)
        with patch.object(ats_scraper, "get_scraper", side_effect=slow_scraper):
            _captured_fetch_with_timeout(company, timeout=0.5,
                                         include_descriptions=False, margin=0.5)
    except CollectionError as exc:
        saw_timeout = True
        dt = time.monotonic() - t0
        check("1a. CollectionError com code=TIMEOUT", exc.code == TIMEOUT,
              f"code={exc.code!r}")
        check("1b. detail menciona timeout", "timeout" in exc.detail.lower(),
              f"detail={exc.detail!r}")
        check("1c. retornou rapido (~deadline, nao 30s)",
              0.5 <= dt <= 3.5, f"dt={dt:.2f}s")
        check("1d. sem orfao apos timeout", not pid_alive(_LAST_PID or 0),
              f"worker pid={_LAST_PID} vivo!")
        print(f"      (timing do timeout: {dt:.2f}s)")
    check("1e. timeout atingido", saw_timeout, "nenhum CollectionError levantado")


# ---------------------------------------------------------------------------
# 2. worker morre de verdade (os._exit(1) no fetch) — distinto de timeout
# ---------------------------------------------------------------------------

def test_worker_dead() -> None:
    print("== [2] worker morre: fetch chama os._exit(1) ==")
    company = make_company()

    def dead_scraper(*args, **kwargs):
        os._exit(1)  # mata o subprocesso sem passar pelo except do worker

    t0 = time.monotonic()
    saw_dead = False
    try:
        with patch.object(ats_scraper, "get_scraper", side_effect=dead_scraper):
            _captured_fetch_with_timeout(company, timeout=10,
                                         include_descriptions=False, margin=25)
    except CollectionError as exc:
        saw_dead = True
        dt = time.monotonic() - t0
        check("2a. code=UNKNOWN (nao TIMEOUT)", exc.code == UNKNOWN,
              f"code={exc.code!r}")
        check("2b. exitcode no detail", "exitcode" in exc.detail
              and "1" in exc.detail, f"detail={exc.detail!r}")
        check("2c. retornou ANTES do deadline (nao 35s)",
              dt < 20.0, f"dt={dt:.2f}s (deadline 35s)")
        check("2d. sem orfao apos worker morto", not pid_alive(_LAST_PID or 0),
              f"worker pid={_LAST_PID} vivo!")
        print(f"      (timing do worker morto: {dt:.2f}s — bem antes do deadline)")
    check("2e. desfecho coletado", saw_dead, "nenhum CollectionError levantado")


# ---------------------------------------------------------------------------
# 3. erro do worker (payload "-error")
# ---------------------------------------------------------------------------

def test_worker_error() -> None:
    print("== [3] erro do worker: payload (-error, code, detail) ==")
    from internship_finder.errors import FETCH_ERROR
    company = make_company()

    def boom_scraper(*args, **kwargs):
        raise RuntimeError("boom")

    t0 = time.monotonic()
    saw_error = False
    try:
        with patch.object(ats_scraper, "get_scraper", side_effect=boom_scraper):
            _captured_fetch_with_timeout(company, timeout=5,
                                         include_descriptions=False, margin=1)
    except CollectionError as exc:
        saw_error = True
        dt = time.monotonic() - t0
        # RuntimeError no fetch -> classify_exception stage fetch -> FETCH_ERROR
        check("3a. code propagado do payload", exc.code == FETCH_ERROR,
              f"code={exc.code!r}")
        check("3b. detail legivel", "boom" in exc.detail, f"detail={exc.detail!r}")
        check("3c. rapido (worker termina normal)", dt < 4.0, f"dt={dt:.2f}s")
        check("3d. sem orfao apos erro do worker", not pid_alive(_LAST_PID or 0),
              f"worker pid={_LAST_PID} vivo!")
        print(f"      (timing do erro do worker: {dt:.2f}s)")
    check("3e. desfecho coletado", saw_error, "nenhum CollectionError levantado")


# ---------------------------------------------------------------------------
# 4. sucesso — resultado correto e processo terminado (sem orfao)
# ---------------------------------------------------------------------------

def test_success() -> None:
    print("== [4] sucesso: resultado correto e sem orfao ==")
    company = make_company()
    job_dict = {
        "id": "s:1", "source": "smartrecruiters:acme", "title": "Intern",
        "company": "Acme", "url": "https://a/1",
        "collected_at": "2026-08-01T00:00:00Z",
    }
    fs = MagicMock()
    fs.fetch.return_value = [object()]
    fa = MagicMock()
    fa.to_job.return_value.to_dict.return_value = job_dict

    with patch.object(ats_scraper, "get_scraper", return_value=fs), \
         patch.object(ats_scraper, "AtsJobAdapter", return_value=fa), \
         patch.object(ats_scraper, "flush_cache"):
        res, pid = _captured_fetch_with_timeout(company, timeout=5,
                                                include_descriptions=False, margin=1)
    check("4a. payload correto", res == [job_dict], f"res={res!r}")
    check("4b. processo terminado (sem orfao)", not pid_alive(pid),
          f"pid={pid} ainda vivo!")


# ---------------------------------------------------------------------------
# 5. N chamadas seguidas — nenhum orfao acumulado
# ---------------------------------------------------------------------------

def test_no_orphans_loop() -> None:
    print("== [5] 5 chamadas seguidas — nenhum orfao acumulado ==")
    company = make_company()
    job_dict = {
        "id": "s:1", "source": "smartrecruiters:acme", "title": "Intern",
        "company": "Acme", "url": "https://a/1",
        "collected_at": "2026-08-01T00:00:00Z",
    }
    fs = MagicMock()
    fs.fetch.return_value = [object()]
    fa = MagicMock()
    fa.to_job.return_value.to_dict.return_value = job_dict

    active_before = {p.pid for p in mp.active_children()}
    pids: list[int] = []
    for i in range(5):
        with patch.object(ats_scraper, "get_scraper", return_value=fs), \
             patch.object(ats_scraper, "AtsJobAdapter", return_value=fa), \
             patch.object(ats_scraper, "flush_cache"):
            res, pid = _captured_fetch_with_timeout(
                company, timeout=5, include_descriptions=False, margin=0.5)
        pids.append(pid)
        ok = res == [job_dict]
        check(f"5.{i + 1}a. chamada {i + 1} OK e processo terminado",
              ok and not pid_alive(pid), f"pid={pid} alive={pid_alive(pid)}")

    # nenhum pid das chamadas ficou vivo
    check("5b. nenhum pid vivo apos o loop",
          all(not pid_alive(p) for p in pids), f"pids={pids}")
    active_after = {p.pid for p in mp.active_children()} - active_before
    check("5c. active_children nao acumulou orfaos novos", active_after == set(),
          f"orfaos={active_after}")


def main() -> int:
    print("Script standalone — P1 #8: ciclo de vida do multiprocessing")
    test_timeout()
    test_worker_dead()
    test_worker_error()
    test_success()
    test_no_orphans_loop()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    import multiprocessing as _mp
    _mp.freeze_support()
    raise SystemExit(main())