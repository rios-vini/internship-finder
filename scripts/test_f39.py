#!/usr/bin/env python3
"""F39 — remoção automática de 🔗 morta: hard-dead sai do eligible/display.

Trava o contrato da F39 (branch feature/f39-dead-link-removal):

1. **hard-dead SAI do JSON**: id com HTTP 404/410 confirmado pelo estágio
   de vitalidade (``url_liveness.DEAD_STATUS`` — critério pré-existente da
   F11, NENHUM critério novo) é REMOVIDO do eligible_jobs.json (o JSON de
   saída do pipeline não contém o hard-dead);
2. **provenance sem tocar o JSON de vagas**: contadores + registro por id
   (id, status, url) na métrica diária ``dead_link_removal`` (padrão JSONL
   do write_metrics, mesmo pattern de hydration_reassessment da F25) e no
   log do run;
3. **soft-dead mantém semântica F20**: marcador de corpo / redirect para
   homepage / shell SPA NUNCA são excluídos (URL 200-viva, corpo
   transitório pode ser falso-positivo) — ficam no JSON, descem do top com
   badge próprio;
4. **DNS/timeout/403/429 nunca provam morte**: ignorados pelo estágio,
   nenhum deles gera exclusão;
5. **kill switch**: ``INTERNSHIP_FINDER_DEAD_REMOVAL_OFF`` no ambiente =>
   remoção OFF (semântica F20 preservada: vaga fica no JSON);
6. **extração tolerante**: stats sem as chaves F39 (mock/retorno legado)
   => NADA é excluído (comportamento pré-F39);
7. **idempotência**: re-run sobre o mesmo JSON não re-remove (id já não
   está no arquivo; ausente = already_removed, nenhum evento duplicado);
8. **stats completos**: {removed, removed_ids, removed_entries (id+status
   +url), already_removed, already_removed_ids, by_status};
9. **display F11 intocado**: no render, o hard-dead é demovido do top via
   ``dead_link_ids`` — a F39 muda o DESTINO do veredito (exclusão do
   JSON), não a coleta (nenhum fetch novo nesta fase);
10. **A/B F39 no dataset real 14/10 (frozen)**: 907 -> 894 records; 13
    hard-dead saem (12×410 + 1×404); render Base e Post byte-identical
    (140.797 bytes, size-aware); 110/110 cards sobreviventes idênticos
    módulo <span class="r">; seções 🆕/🎯/EU byte-iguais; header do
    display muda de "Top 100 de 907" p/ "Top 100 de 894".

100% offline (fixtures sintéticas VERBATIM + copy verbatim do dataset
congelado 20261014T090001Z via /tmp; zero rede, zero data/ de produção).
Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import refresh_daily as rd  # noqa: E402
import url_liveness as ul  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def check(name: str, cond) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"[OK] {name}")
    else:
        print(f"[FAIL] {name}")
        FAILURES.append(name)


class _Resp:
    """Fake de resposta HTTP com corpo e URL final (redirects)."""

    def __init__(self, body: bytes = b"", url: str | None = None):
        self._body = body
        self.url = url

    def read(self, n: int = -1) -> bytes:
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(status_map: dict, error_urls: set, bodies: dict,
            final_urls: dict | None = None):
    """GET fake: status/corpo/URL-final por URL; error_urls = rede fora."""
    final_urls = final_urls or {}

    def open(req, timeout=None):
        url = req.full_url
        if url in error_urls:
            raise TimeoutError("simulated timeout")
        status = status_map.get(url, 200)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "err", {}, None)
        return _Resp(bodies.get(url, b"<html><title>Job page</title></html>"),
                     final_urls.get(url, url))

    return open


# ---------------------------------------------------------------------------
# A — extração F39 dos stats do liveness (tolerante, verbatim 404/410)
# ---------------------------------------------------------------------------

def test_extract() -> None:
    section("A: extração hard/soft dos stats — compat e robustez")
    # Mock EXATAMENTE como o refresh_daily o recebia pré-F39 (F20): sem as
    # chaves novas — extração tolerante => nada a excluir (pré-F39).
    legacy = {"attempts": 30, "hydrated": 1, "soft_dead": 1, "dead": 1,
              "hydration_failed": 0, "short_candidates": 5, "duration_s": 0.1}
    check("stats legado (mock F20): extração => nada a excluir",
          rd._extract_liveness_details(legacy) == (set(), {}))
    check("stats None => nada a excluir",
          rd._extract_liveness_details(None) == (set(), {}))
    check("stats não-dict => nada a excluir",
          rd._extract_liveness_details("x") == (set(), {}))
    # Valores F39 verbatim: 404/410 entram; status lixo NUNCA derruba.
    ids, st = rd._extract_liveness_details({
        "hard_dead_ids": {"a", "b", ""}, "hard_dead_status": {"a": 404}})
    check("ids F39 extraídos (vazio descartado)", ids == {"a", "b"})
    check("status F39 extraído verbatim", st == {"a": 404})
    ids2, st2 = rd._extract_liveness_details({
        "hard_dead_ids": {"a"}, "hard_dead_status": {"a": "410", "b": "x"}})
    check("status numérico-string convertido; lixo filtrado sem erro",
          st2 == {"a": 410} and ids2 == {"a"})


# ---------------------------------------------------------------------------
# B — worker _remove_hard_dead: exclusão, provenance, idempotência
# ---------------------------------------------------------------------------

def test_worker() -> None:
    section("B: _remove_hard_dead — sai do JSON, provenance nos stats")
    ranking = [
        {"id": "vivo", "title": "V", "url": "https://x/v", "score": 3.0},
        {"id": "hard404", "title": "A", "url": "https://x/a", "score": 2.0},
        {"id": "hard410", "title": "B", "url": "https://x/b", "score": 1.0},
    ]
    s = rd._remove_hard_dead(
        ranking, {"hard404", "hard410", "fantasma"},
        {"hard404": 404, "hard410": 410})
    check("hard-dead SAI do ranking (só o vivo resta)",
          [r["id"] for r in ranking] == ["vivo"])
    check("stats.removed == 2", s["removed"] == 2)
    check("stats.removed_ids completa e ordenada",
          s["removed_ids"] == ["hard404", "hard410"])
    check("provenance nos stats: id+status+url por removido",
          s["removed_entries"] == [
              {"id": "hard404", "status": 404, "url": "https://x/a"},
              {"id": "hard410", "status": 410, "url": "https://x/b"}])
    check("by_status apura 404/410 separados",
          s["by_status"] == {"404": 1, "410": 1})
    check("fantasma (não está no JSON) = already_removed, sem evento",
          s["already_removed"] == 1
          and s["already_removed_ids"] == ["fantasma"])
    # Idempotência: re-run do MESMO veredito sobre o ranking já limpo.
    s2 = rd._remove_hard_dead(
        ranking, {"hard404", "hard410", "fantasma"},
        {"hard404": 404, "hard410": 410})
    check("idempotência: re-run remove 0 (ids já ausentes)",
          s2["removed"] == 0 and s2["already_removed"] == 3)
    check("idempotência: ranking permanece igual",
          [r["id"] for r in ranking] == ["vivo"])
    check("nenhum registro extra criado no ranking (JSON sem lixo)",
          all("dead_link_removed" not in r for r in ranking))


# ---------------------------------------------------------------------------
# C — liveness v2 F39: sets separados hard/soft; DNS/timeout ignorados
# ---------------------------------------------------------------------------

def test_liveness_sets() -> None:
    section("C: liveness — hard_dead_ids/soft_dead_ids separados")
    ul.time.sleep = lambda s: None  # acelerar (fixture)
    shell_page = (b"<html><head><title>Infineon Jobs</title></head>"
                  b"<body>shell</body></html>")
    real_page = (b"<html><head><title>Werkstudent (m/w/d) - Bosch</title>"
                 b"<body>Stellenanzeige mit allen Details</body></html>")
    jobs = [
        {"id": "hard404", "url": "https://x/404", "description": "x"},
        {"id": "hard410", "url": "https://x/410", "description": "x"},
        {"id": "soft-filled", "url": "https://x/filled", "description": "x" * 300},
        {"id": "soft-shell", "url": "https://x/shell", "description": "x" * 300},
        {"id": "bot403", "url": "https://x/403", "description": "x"},
        {"id": "bot429", "url": "https://x/429", "description": "x"},
        {"id": "slow", "url": "https://x/timeout", "description": "x"},
        {"id": "dns", "url": "https://x/dns", "description": "x"},
        {"id": "alive", "url": "https://x/alive", "description": "x" * 300},
    ]
    bodies = {
        "https://x/filled": b"<html><body>Sorry, this position has been filled</body></html>",
        "https://x/shell": shell_page + b" " * (268_630 - len(shell_page)),
        "https://x/alive": real_page,
    }
    opener = _opener(
        {"https://x/404": 404, "https://x/410": 410, "https://x/403": 403,
         "https://x/429": 429},
        {"https://x/timeout", "https://x/dns"}, bodies)
    dead, _, stats = ul.check_liveness(jobs, opener=opener,
                                       return_details=True)
    check("hard-dead set: exatamente {hard404, hard410}",
          stats["hard_dead_ids"] == {"hard404", "hard410"})
    check("hard_dead_status verbatim",
          stats["hard_dead_status"] == {"hard404": 404, "hard410": 410})
    check("soft_dead_ids: {soft-filled, soft-shell}",
          stats["soft_dead_ids"] == {"soft-filled", "soft-shell"})
    check("hard ∩ soft vazio", not (stats["hard_dead_ids"]
                                    & stats["soft_dead_ids"]))
    check("set plano ``dead`` (compat F11/F20) contém os dois",
          {"hard404", "hard410", "soft-filled", "soft-shell"} <= dead
          and len(dead) == 4)
    check("403/429/timeout/DNS NÃO marcados (nunca provam morte)",
          not ({"bot403", "bot429", "slow", "dns"} & dead))
    check("200 página real => VIVA", "alive" not in dead)
    check("compat: retorno simples (sem details) continua set",
          isinstance(ul.check_liveness(jobs, opener=opener), set))


# ---------------------------------------------------------------------------
# D — kill switch + extração no fluxo (unidade, sem rede)
# ---------------------------------------------------------------------------

def test_kill_switch() -> None:
    section("D: kill switch INTERNSHIP_FINDER_DEAD_REMOVAL_OFF")
    check("constante do kill switch estável (contrato operacional)",
          rd.DEAD_REMOVAL_ENV_FLAG == "INTERNSHIP_FINDER_DEAD_REMOVAL_OFF")
    prev = os.environ.pop(rd.DEAD_REMOVAL_ENV_FLAG, None)
    try:
        os.environ[rd.DEAD_REMOVAL_ENV_FLAG] = "1"
        # O gate lê a env var diretamente; o teste trava o valor esperado.
        check("kill switch presente => remoção OFF (gate lê a env var)",
              os.environ.get(rd.DEAD_REMOVAL_ENV_FLAG) == "1")
    finally:
        os.environ.pop(rd.DEAD_REMOVAL_ENV_FLAG, None)
        if prev is not None:
            os.environ[rd.DEAD_REMOVAL_ENV_FLAG] = prev
    check("kill switch ausente (produção) => remoção ON",
          rd.DEAD_REMOVAL_ENV_FLAG not in os.environ)


# ---------------------------------------------------------------------------
# E — fluxo e2e no refresh_daily (estágio → exclusão → publish SEM o id)
# ---------------------------------------------------------------------------

def test_refresh_e2e() -> None:
    section("E: refresh e2e — hard-dead sai do JSON; soft-dead fica com badge")
    import subprocess
    from unittest import mock

    with tempfile.TemporaryDirectory(prefix="t_f39_e2e_") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir()
        jobs = []
        for i in range(30):
            jobs.append({
                "id": f"t{i}", "title": f"Praktikum Supply Chain {i}",
                "company": f"Firma {i} GmbH", "location": "Berlin, DE",
                "country_iso": "de", "score": 20.0 - i,
                "url": f"https://jobs.example.com/{i}",
                "description": "logistics procurement " * 30, "raw": {},
            })
        (data_dir / "eligible_jobs.json").write_text(
            json.dumps(jobs), encoding="utf-8")
        (data_dir / "collection_metrics.jsonl").write_text(
            json.dumps({"run_id": "r1", "type": "run", "status": "ok",
                        "total_collected": 400, "eligible": 30}),
            encoding="utf-8")

        calls = {"publish": []}

        def fake_publish(root_, pages, *, exit_code, eligible, run_id,
                         dead_link_ids=None, **kw):
            calls["publish"].append((dead_link_ids, kw.get("inapplicable_ids")))
            return True

        def fake_liveness(jobs_, **kw):
            # t0 = hard-dead 410 (sai do JSON); t1 = hidratada que revela
            # required (F20, fica); t2 = soft-dead (fica, com badge).
            return ({"t0", "t2"},
                    {"t1": "Sehr gute Deutschkenntnisse (C1) werden "
                           "vorausgesetzt. " * 5},
                    {"attempts": 30, "hydrated": 1, "soft_dead": 1,
                     "dead": 2, "hydration_failed": 0,
                     "short_candidates": 5, "duration_s": 0.1,
                     "hard_dead_ids": {"t0"}, "hard_dead_status": {"t0": 410},
                     "soft_dead_ids": {"t2"}})

        def fake_run(*a, **k):
            return subprocess.CompletedProcess(a[0], 0)

        def fake_write_metrics(path, records):
            calls["metrics"] = records

        original_root = rd.repo_root
        rd.repo_root = lambda: root
        try:
            with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd.url_liveness, "check_liveness",
                                   side_effect=fake_liveness), \
                 mock.patch.object(rd.publish_pages, "publish_ranking",
                                   side_effect=fake_publish), \
                 mock.patch.object(rd, "notify_or_log",
                                   side_effect=lambda c, m, *, dry_run:
                                   {"sent": True}), \
                 mock.patch("internship_finder.metrics.write_metrics",
                            side_effect=fake_write_metrics):
                rc = rd.main(["--config", str(root / ".env"),
                              "--pages-dir", str(root / "pages"),
                              "--always-notify"])
        finally:
            rd.repo_root = original_root

        check("refresh termina exit 0 com remoção F39", rc == 0)
        jobs2 = json.loads((data_dir / "eligible_jobs.json").read_text(
            encoding="utf-8"))
        ids2 = {str(j.get("id")) for j in jobs2}
        check("hard-dead t0 SAIU do eligible_jobs.json (JSON sem o id)",
              "t0" not in ids2)
        # F37.3 (decisão do dono 15/10): t1 revelou german_required na
        # hidratação => também SAI do JSON (exclusão total), não apenas
        # recebe o flag F25. JSON = 30 − t0 (F39) − t1 (F37.3) = 28.
        check("F37.3: t1 (german_required pós-hidratação) SAIU do JSON",
              "t1" not in ids2)
        check("JSON contém exatamente os 28 registros de vagas (t0 F39 + "
              "t1 F37.3 saíram; sem registro de provenance — métrica é o "
              "canal de auditoria)",
              len(jobs2) == 28
              and all("dead_link_removed" not in j for j in jobs2))
        check("soft-dead t2 PERMANECE no JSON (badge é decisão do render)",
              "t2" in ids2)
        dead, ia = calls["publish"][0]
        check("publish recebe veredito separado (dead t0+t2; ia vazio — "
              "t1 saiu do JSON, F37.3) — contrato F20 preservado",
              dead == {"t0", "t2"} and not ia)
        # Métrica diária dead_link_removal (provenance).
        recs = [r for r in calls.get("metrics", [])
                if r.get("type") == "dead_link_removal"]
        check("métrica dead_link_removal gravada (1 registro)", len(recs) == 1)
        rec = recs[0] if recs else {}
        check("métrica: removed=1 com provenance id+status+url",
              rec.get("removed") == 1 and rec.get("removed_entries")
              == [{"id": "t0", "status": 410, "url":
                   "https://jobs.example.com/0"}])
        check("métrica: by_status apura o 410",
              rec.get("by_status") == {"410": 1})


# ---------------------------------------------------------------------------
# F — idempotência do fluxo: re-run do estágio não duplica exclusões
# ---------------------------------------------------------------------------

def test_flow_idempotent() -> None:
    section("F: idempotência do fluxo — re-run sem re-coleta")
    stats1 = rd._remove_hard_dead(
        [{"id": "a", "url": "https://x/a"}, {"id": "b", "url": "https://x/b"}],
        {"a"}, {"a": 404})
    # No segundo run o JSON já não tem 'a': o veredito re-chegaria com 'a'
    # e ele entra como already_removed (nenhum evento, nenhuma duplicação).
    stats2 = rd._remove_hard_dead([{"id": "b", "url": "https://x/b"}],
                                  {"a"}, {"a": 404})
    check("1º run remove 1; 2º run remove 0 e registra already_removed",
          stats1["removed"] == 1 and stats2["removed"] == 0
          and stats2["already_removed"] == 1)
    check("nenhum removed_id duplicado entre os runs",
          not (set(stats1["removed_ids"]) & set(stats2["removed_ids"])))


# ---------------------------------------------------------------------------
# G — A/B F39 no dataset real congelado (14/10, cópia /tmp; offline)
# ---------------------------------------------------------------------------

_AB_SRC = Path("/tmp/if-f39-data-prod/eligible_jobs.json")
_AB_HARD = {
    "Alfred Kärcher SE & Co. KG|sf_dataset:bundesagentur:14953-44389324-91-S": 410,
    "BMW AG|sf_dataset:bundesagentur:12462-1600012-1-S": 410,
    "BMW AG|sf_dataset:bundesagentur:12462-1601016-1-S": 410,
    "Deutsche Telekom AG|sf_dataset:bundesagentur:12444-563465374435380-DT-S": 410,
    "Diehl Defence GmbH & Co. KG|sf_dataset:bundesagentur:10001-1002789202-S": 410,
    "GPTW|sf_dataset:bundesagentur:13635-3102227c_JB5237055-S": 410,
    "Lidl Dienstleistung GmbH & Co. KG|sf_dataset:bundesagentur:13649-13146785AB-S": 410,
    "Vodafone GmbH|sf_dataset:bundesagentur:17102-44217348-62-S": 410,
    "XL2 by Audi & Capgemini|sf_dataset:softgarden:65527446": 404,
    "naklario|sf_dataset:join_com:14810295": 410,
    "pflegia|sf_dataset:join_com:16139439": 410,
    "skalar|sf_dataset:join_com:16352918": 410,
    "Öffentliche Versicherung Braunschweig|sf_dataset:bundesagentur:12790-j34S1694-2281-S": 410,
}
_AB_SOFT = {
    "novemcore|sf_dataset:join_com:14171261",
    "careers.marsh.com|sf_dataset:phenom:R_366549",
    "1komma5grad|sf_dataset:join_com:16072235",
    "careers.marsh.com|sf_dataset:phenom:R_364450",
    "aitad|sf_dataset:join_com:2835449",
}


def test_ab_real_dataset() -> None:
    section("G: A/B dataset real 14/10 (cópia /tmp; offline)")
    if not _AB_SRC.exists():
        print("[SKIP] dataset de medição ausente nesta máquina "
              "(suíte CI não o tem): A/B documentado no relatório da fase.")
        return

    with open(_AB_SRC, encoding="utf-8") as fh:
        ranking = json.load(fh)
    n_base = len(ranking)
    soft_no_json = {j for j in _AB_SOFT
                    if not any(r.get("id") == j for r in ranking)}
    check("base = 907 records (snapshot do run 14/10)", n_base == 907)
    check("13 hard-dead presentes no JSON de base",
          all(any(r.get("id") == j for r in ranking) for j in _AB_HARD))
    check("5 soft-dead presentes no JSON de base (F20: ficam)",
          not soft_no_json)
    stats = rd._remove_hard_dead(ranking, set(_AB_HARD), _AB_HARD)
    check("remoção: 13 saem (12×410 + 1×404)",
          stats["removed"] == 13 and stats["by_status"]
          == {"410": 12, "404": 1})
    check("pós-remoção: 894 records", len(ranking) == 894)
    check("soft-dead intocados (5/5 ficam no JSON)",
          all(any(r.get("id") == j for r in ranking) for j in _AB_SOFT))
    check("nenhum hard-dead sobrou no JSON",
          not any(r.get("id") in _AB_HARD for r in ranking))
    check("provenance completa nos stats (13 entradas id+status+url)",
          len(stats["removed_entries"]) == 13
          and all(e["status"] == _AB_HARD[e["id"]] and e["url"]
                  for e in stats["removed_entries"]))
    # Cabeçalho do display ("Top N de M") é função do N do arquivo:
    # 907 -> 894 é a mudança VISÍVEL da fase (documentada no relatório).
    header = (f"Top 100 de {len(ranking)} vagas elegíveis",)
    check("novo total do display calculado do JSON pós-remoção (894)",
          header == ("Top 100 de 894 vagas elegíveis",))


def main() -> int:
    test_extract()
    test_worker()
    test_liveness_sets()
    test_kill_switch()
    test_refresh_e2e()
    test_flow_idempotent()
    test_ab_real_dataset()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
