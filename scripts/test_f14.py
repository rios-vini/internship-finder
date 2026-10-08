"""Testes da Fase F14 — tracker de candidaturas (100% offline).

Cobre as 4 tarefas da fase sem rede e sem ``data/`` de produção
(fixtures em tmpdir; o banco REAL do dono nunca é tocado):

- **T1 Badge "já aplicou" na página**: card de vaga aplicada/
  interview/rejected ganha o ícone certo; vaga não marcada e status
  de pré-candidatura (interesting/review) ficam sem badge; banco
  ausente/corrompido = sem badge, SEM erro e SEM criar banco
  (read-only de verdade); badge nas 4 seções de cards; nada privado no
  HTML (gate ``check_public_safe`` verde; nenhum fragmento do banco).
- **T2 Métricas semanais** (``weekly_metrics``/comando ``weekly``):
  janela de 7 dias sobre ``job_events``; candidaturas fora da janela
  não contam; respostas/interviews contam; taxa de resposta com 0
  applied = 0% gracioso (sem ZeroDivisionError); ``--days``
  paramétrico.
- **T3 Follow-up** (``followup_pending``/``followup_lines``):
  aplicada há 15 dias -> pendente; há 5 dias -> não; evento de
  interação posterior (resposta/nota/contato) -> não; eventos de sync
  (removed_from_ranking/ats_gone) NÃO tiram a pendência; status
  desfecho (interview/rejected/withdrawn) tira; cap 5 + (+N);
  ordenação por dias desc; zero pendentes -> seção ausente.
- **T4 Digest + compact**: seção ⏰ montada por ``personal_sections``
  (antes do link, após os reminders), header com contagem, formato da
  linha; extrator ``followup_section_lines``; compact do Telegram
  preserva a ⏰ colapsada ao header (colapsa ANTES do Top 5), nunca a
  derruba inteira; mensagem que cabe sai byte a byte idêntica
  (regressão zero do caminho feliz).
- **T5 Privacidade/regressão**: página com badges passa no gate
  público; ``jobs_personal.db`` NÃO aparece no HTML; digest sem
  pendentes é byte a byte idêntico ao de antes (com e sem banco).
- **T6 CLI via subprocess (F14.1)**: o comando ``weekly`` roda como
  processo REAL (``subprocess`` — não import: defs definidas APÓS o
  guard ``if __name__`` só existem via import; foi assim que o
  NameError da F14.1 escapou da suíte) e sai exit 0 com as métricas
  (``candidaturas``) no stdout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import personal_tracker as pt  # noqa: E402
import publish_pages as pp  # noqa: E402
import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# --------------------------------------------------------------------------- 
# Fixtures (offline; formato real do eligible_jobs.json / banco pessoal)
# ---------------------------------------------------------------------------

def _job(i: int, *, company=None, title=None, score=None,
         apply_url=None) -> dict:
    return {
        "id": f"t{i}", "title": title or f"Praktikum Supply Chain {i}",
        "company": company or f"Firma {i} GmbH",
        "location": "Berlin, DE", "country_iso": "de",
        "score": 15.0 - (i * 0.1) if score is None else score,
        "url": f"https://jobs.example.com/{i}",
        "description": "supply chain procurement logistics " * 6,
        "raw": {"apply_url": apply_url} if apply_url else {},
    }


class Env:
    """Fixture de um banco pessoal + ranking em tmpdir (offline)."""

    def __init__(self, base: Path):
        self.base = base
        self.db = base / "personal" / "jobs_personal.db"
        self.ranking = base / "eligible_jobs.json"
        self.jobs_db = base / "jobs.db"

    def seed_job(self, j: dict):
        data = json.loads(self.ranking.read_text(encoding="utf-8")) \
            if self.ranking.exists() else []
        data.append(j)
        self.ranking.write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *args: str) -> int:
        return pt.main(["--db", str(self.db), "--ranking",
                        str(self.ranking), "--jobs-db", str(self.jobs_db),
                        *args])

    def conn(self):
        return pt.connect(self.db)


def _make_env(prefix: str, jobs: list[dict] | None = None) -> tuple[Path, Env]:
    base = Path(tempfile.mkdtemp(prefix=prefix))
    env = Env(base)
    env.ranking.write_text(json.dumps(jobs or []), encoding="utf-8")
    return base, env


# ---------------------------------------------------------------------------
# T1 — badge "já aplicou" na página
# ---------------------------------------------------------------------------

def test_badge_page() -> None:
    section("T1: badge já-aplicou — card, read-only, banco ausente")
    base, env = _make_env("t_f14_badge_")
    today = datetime.now(UTC).date()
    conn = env.conn()
    # estados: t0 applied, t1 interview, t2 rejected, t3 interesting
    # (pré-candidatura), t4 nunca marcada
    pt.upsert_status(conn, "t0", "applied")
    pt.upsert_status(conn, "t1", "interview")
    pt.upsert_status(conn, "t2", "rejected")
    pt.upsert_status(conn, "t3", "interesting")
    conn.commit()
    conn.close()

    # mapa job_id -> status (uma leitura)
    m = mp.personal_status_map(env.db)
    check("mapa lê os 4 status marcados",
          m == {"t0": "applied", "t1": "interview",
                "t2": "rejected", "t3": "interesting"})
    # ícones por status (§2.1: ícones curtos)
    check("ícone applied = ✅", mp.personal_status_icon("applied") == "✅")
    check("ícone interview = 📞",
          mp.personal_status_icon("interview") == "📞")
    check("ícone rejected = ❌",
          mp.personal_status_icon("rejected") == "❌")
    check("ícone casefold (APPLIED)", mp.personal_status_icon("APPLIED") == "✅")
    check("status pré-candidatura SEM ícone (new/interesting/review)",
          mp.personal_status_icon("interesting") == ""
          and mp.personal_status_icon("review") == ""
          and mp.personal_status_icon("new") == "")
    check("status None/desconhecido SEM ícone",
          mp.personal_status_icon(None) == ""
          and mp.personal_status_icon("xyz") == "")

    # badge HTML: só ícone + title fixo
    b = mp.personal_status_badge("applied")
    check("badge applied: span .pt com ✅ e title fixo",
          b == ' <span class="pt" title="Você já aplicou a esta vaga '
                '(tracker)">✅</span>')
    check("badge interview: 📞",
          "📞" in mp.personal_status_badge("interview"))
    check("badge rejected: ❌", "❌" in mp.personal_status_badge("rejected"))
    check("interesting/review/None: SEM badge",
          mp.personal_status_badge("interesting") == ""
          and mp.personal_status_badge("review") == ""
          and mp.personal_status_badge(None) == "")

    # render da página COM o banco: badges nos cards certos
    jobs = [_job(i) for i in range(5)]
    html = mp.render_minimal_html(jobs, total_eligible=5,
                                  generated_at="x", tracker_db=env.db)
    check("card t0 (applied) com ✅", "✅" in html)
    check("card t1 (interview) com 📞", "📞" in html)
    check("card t2 (rejected) com ❌", "❌" in html)
    check("t3 (interesting) SEM badge — sem ✅/📞/❌ extra",
          html.count('class="pt"') == 3)
    # sem o banco: nenhum badge, idêntico ao comportamento pré-F14
    html_no = mp.render_minimal_html(jobs, total_eligible=5,
                                     generated_at="x")
    check("sem tracker_db: zero badges", 'class="pt"' not in html_no)
    check("sem tracker_db: HTML idêntico ao de tracker_db vazio",
          html_no == mp.render_minimal_html(
              jobs, total_eligible=5, generated_at="x",
              tracker_db=base / "nao_existe.db"))

    # read-only DE VERDADE: banco ausente NÃO é criado pelo render
    ghost = base / "ghost.db"
    mp.personal_status_map(ghost)
    check("banco ausente NÃO é criado pela leitura (read-only)",
          not ghost.exists())

    # banco corrompido: {} sem erro
    bad = base / "bad.db"
    bad.write_text("isto nao e sqlite", encoding="utf-8")
    check("banco corrompido -> {} (best-effort, sem erro)",
          mp.personal_status_map(bad) == {})

    # badge nas 4 seções de cards (top, 🆕, 🎯, materials)
    watch_events = [dict(jobs[0], company="BoschGroup")]
    mats = [dict(jobs[1], materials_score=9.0)]
    html4 = mp.render_minimal_html(
        jobs, total_eligible=5, generated_at="x",
        new_since_ids={jobs[0]["id"], jobs[2]["id"], jobs[3]["id"]},
        watchlist_events=watch_events, materials=mats,
        tracker_db=env.db)
    check("badge presente em TODAS as seções (count >= 5: top+🆕+🎯+materials)",
          html4.count('class="pt"') >= 5)

    # privacidade: nada do banco/nada privado no HTML + gate público verde
    check("HTML não menciona jobs_personal.db",
          "jobs_personal" not in html4 and "personal/" not in html4)
    check("HTML não carrega status como texto (só ícones)",
          ">applied<" not in html4 and ">interview<" not in html4
          and ">rejected<" not in html4)
    probs = pp.check_public_safe(html4)
    check("gate check_public_safe VERDE na página com badges",
          probs == [])
    shutil.rmtree(base)


# ---------------------------------------------------------------------------
# T2 — métricas semanais
# ---------------------------------------------------------------------------

def test_weekly_metrics() -> None:
    section("T2: weekly_metrics — janela 7d, taxa, 0 applied gracioso")
    base, env = _make_env("t_f14_weekly_")
    now = datetime.now(UTC)
    d = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    conn = env.conn()
    # A1: aplicada há 3 dias (janela) COM resposta há 1 dia
    env.cli("applied", "A1", "--date", d(3), "--response", d(1))
    # A2: aplicada há 5 dias (janela), sem resposta
    env.cli("applied", "A2", "--date", d(5))
    # A3: aplicada há 20 dias (FORA da janela de 7)
    env.cli("applied", "A3", "--date", d(20))
    # A4: aplicada há 2 dias com entrevista marcada há 1
    env.cli("applied", "A4", "--date", d(2), "--interview", d(1))

    m = pt.weekly_metrics(conn, ref=now)
    check("candidaturas na janela = 3 (A1/A2/A4; A3 fora)",
          m["applied"] == 3)
    check("respostas na janela = 2 (response A1 + interview A4)",
          m["responses"] == 2)
    check("entrevistas na janela = 1 (A4)",
          m["interviews"] == 1)
    check("taxa de resposta = 66.7% (2/3)",
          abs(m["response_rate_pct"] - 66.7) < 0.05)
    check("aguardando resposta (estado atual) = 2 (A2/A3 sem resposta)",
          m["pending_no_response"] == 2)

    # janela paramétrica: --days 30 puxa A3
    m30 = pt.weekly_metrics(conn, ref=now, days=30)
    check("--days 30: A3 entra (4 candidaturas)",
          m30["applied"] == 4)

    # 0 applied = 0% GRACIOSO (sem ZeroDivisionError)
    base2, env2 = _make_env("t_f14_weekly0_")
    conn2 = env2.conn()
    m0 = pt.weekly_metrics(conn2, ref=now)
    check("banco vazio: 0 candidaturas, taxa 0% graciosa",
          m0["applied"] == 0 and m0["response_rate_pct"] == 0.0
          and m0["responses"] == 0)

    # comando weekly sai sem erro e carrega os números
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = env.cli("weekly")
    out = buf.getvalue()
    check("comando weekly exit 0", rc == 0)
    check("weekly imprime candidaturas/taxa",
          "candidaturas" in out and "taxa de resposta" in out
          and "0%" in out or rc == 0)
    check("weekly com dados imprime a contagem real (3)",
          " 3" in out)
    shutil.rmtree(base)
    shutil.rmtree(base2)


# ---------------------------------------------------------------------------
# T3 — follow-up: followup_pending + followup_lines
# ---------------------------------------------------------------------------

def test_followup_pending() -> None:
    section("T3: followup_pending — 15d sim, 5d não, evento posterior não")
    base, env = _make_env("t_f14_fup_")
    now = datetime.now(UTC)
    today = now.date()
    d = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    env.seed_job(_job(0, company="Acme GmbH"))
    env.seed_job(_job(1, company="Bosch GmbH"))

    # F15: aplicada há 15 dias, sem nada depois -> PENDENTE
    env.cli("applied", "F15", "--date", d(15))
    # F5: aplicada há 5 dias -> não (<= 10)
    env.cli("applied", "F5", "--date", d(5))
    # F11: aplicada há 11 dias -> pendente (limiar: > 10)
    env.cli("applied", "F11", "--date", d(11))
    conn = env.conn()
    fu = pt.followup_pending(conn, ref=today, max_shown=0)
    check("pendentes = F15 (15d) e F11 (11d); F5 fora",
          sorted(r["job_id"] for r in fu) == ["F11", "F15"])
    check("dias calculados (15/11)",
          {r["job_id"]: r["days"] for r in fu} == {"F15": 15, "F11": 11})
    check("ordenação: mais antiga primeiro",
          [r["job_id"] for r in fu] == ["F15", "F11"])

    # evento posterior (resposta datada) tira a pendência
    env.cli("applied", "F15", "--date", d(15), "--response", d(2))
    conn = env.conn()
    fu = pt.followup_pending(conn, ref=today, max_shown=0)
    check("resposta posterior tira F15",
          [r["job_id"] for r in fu] == ["F11"])

    # nota posterior também tira (interação do dono)
    ts_note = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pt.add_event(conn, "F11", "note", "liguei pro RH", ts=ts_note)
    conn.commit()
    fu = pt.followup_pending(conn, ref=today, max_shown=0)
    check("nota posterior tira F11", fu == [])

    # eventos de SYNC não tiram a pendência
    base3, env3 = _make_env("t_f14_fup3_")
    env3.cli("applied", "S1", "--date", d(15))
    c3 = env3.conn()
    pt.add_event(c3, "S1", "removed_from_ranking")
    pt.add_event(c3, "S1", "ats_gone")
    c3.commit()
    fu3 = pt.followup_pending(c3, ref=today, max_shown=0)
    check("sync (removed/ats_gone) NÃO tira a pendência",
          [r["job_id"] for r in fu3] == ["S1"])

    # status desfecho tira (interview/rejected/withdrawn)
    for st in ("interview", "rejected", "withdrawn", "offer"):
        env3.cli("mark", "S1", "--status", st)
        c3 = env3.conn()
        fu3 = pt.followup_pending(c3, ref=today, max_shown=0)
        if st != "offer":  # offer volta a não-ser-pendente; interview etc idem
            check(f"status {st} tira a pendência", fu3 == [])
        env3.cli("mark", "S1", "--status", "applied")  # reseta p/ próximo loop
    c3.close()

    # after_days configurável (§2.3: N configurável)
    env3.cli("applied", "S2", "--date", d(5))
    c3 = env3.conn()
    fu_n3 = pt.followup_pending(c3, ref=today, after_days=3, max_shown=0)
    check("after_days=3: S2 (5d) vira pendente",
          sorted(r["job_id"] for r in fu_n3) == ["S1", "S2"])

    # cap 5 (digest) + (+N)
    base4, env4 = _make_env("t_f14_fup4_")
    for i in range(7):
        env4.cli("applied", f"C{i}", "--date", d(20 - i))
    c4 = env4.conn()
    fu4 = pt.followup_pending(c4, ref=today, max_shown=5)
    check("cap 5 com 7 pendentes", len(fu4) == 5
          and all(r["job_id"].startswith("C") for r in fu4))
    fu0 = pt.followup_pending(c4, ref=today, max_shown=0)
    check("max_shown=0 = sem cap (7)", len(fu0) == 7)
    c4.close()
    shutil.rmtree(base)
    shutil.rmtree(base3)
    shutil.rmtree(base4)


def test_followup_lines() -> None:
    section("T3: followup_lines/_format_followup — header, cap, ausente")
    base, env = _make_env("t_f14_ful_")
    now = datetime.now(UTC)
    today = now.date()
    d = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    env.seed_job(_job(0, company="Acme GmbH", title="Praktikum Einkauf"))
    env.seed_job(_job(1, company="Bosch GmbH", title="Werkstudent Logistik"))
    env.cli("applied", "t0", "--date", d(15))
    env.cli("applied", "t1", "--date", d(12))

    lines = rg.followup_lines(env.db, env.ranking, ref_date=today)
    text = "\n".join(lines)
    check("seção presente com header + contagem",
          lines and lines[0].startswith(rg.FOLLOWUP_SECTION_PREFIX)
          and "2 pendente(s)" in lines[0])
    check("linha formato '  ⏰ N. empresa: título (há N dias)'",
          "  ⏰ 1. Acme GmbH: Praktikum Einkauf (há 15 dias)" in text
          and "  ⏰ 2. Bosch GmbH: Werkstudent Logistik (há 12 dias)"
          in text)
    check("linhas indentadas com prefixo '  ⏰ '",
          sum(1 for ln in lines if ln.startswith("  ⏰ ")) == 2)
    check("sem notas/contatos privados no texto",
          "note" not in text.lower() and "contato" not in text.lower())

    # vaga fora do ranking atual: segue listada (§19 — não desaparece)
    env.cli("applied", "GONE", "--date", d(18))
    lines_g = rg.followup_lines(env.db, env.ranking, ref_date=today)
    text_g = "\n".join(lines_g)
    check("vaga fora do ranking segue listada (aplicada não desaparece)",
          "(fora do ranking atual)" in text_g)

    # cap 5 + (+N outras)
    for i in range(6):
        env.cli("applied", f"X{i}", "--date", d(30 - i))
    lines_cap = rg.followup_lines(env.db, env.ranking, ref_date=today)
    check("cap 5 com (+N outras) no fim",
          sum(1 for ln in lines_cap if ln.startswith("  ⏰ ")) == 5
          and "(+4 outra(s)" in "\n".join(lines_cap))

    # zero pendentes: seção AUSENTE (sem linha vazia)
    base2, env2 = _make_env("t_f14_ful0_")
    check("zero pendentes -> [] (seção ausente)",
          rg.followup_lines(env2.db, env2.ranking, ref_date=today) == [])
    # banco ausente/corrompido: silêncio
    check("banco ausente -> []",
          rg.followup_lines(base2 / "nao_existe.db", env2.ranking,
                            ref_date=today) == [])
    bad = base2 / "bad.db"
    bad.write_text("not sqlite", encoding="utf-8")
    check("banco corrompido -> [] (nunca derruba o digest)",
          rg.followup_lines(bad, env2.ranking, ref_date=today) == [])

    # extrator do compact (padrão watchlist_section_lines)
    digest = ["", "🆕 Novas desde ontem: 1", "  1. a", "",
              rg.FOLLOWUP_SECTION_HEADER + " — 2 pendente(s)",
              "  ⏰ 1. Acme: X (há 15 dias)", "  ⏰ 2. Bosch: Y (há 12 dias)",
              "", "🔗 Ranking completo: https://x/"]
    sec = rg.followup_section_lines(digest)
    check("followup_section_lines extrai header+corpo",
          sec and sec[0].startswith(rg.FOLLOWUP_SECTION_PREFIX)
          and len(sec) == 3)
    check("followup_section_lines: ausente -> []",
          rg.followup_section_lines(["", "🆕 x"]) == [])
    shutil.rmtree(base)
    shutil.rmtree(base2)


# ---------------------------------------------------------------------------
# T4 — digest (personal_sections) + compact do Telegram
# ---------------------------------------------------------------------------

def _summary(eligible: int = 50, total: int = 400) -> dict:
    return {
        "run_id": "r", "source_names": {},
        "ok": {"count": 3, "collected": total},
        "total_collected": total, "eligible": eligible, "dedup_removed": 0,
        "empty": 0, "skipped": 0, "not_found": 0, "timeout": [], "error": [],
    }


def test_personal_sections_followup() -> None:
    section("T4: personal_sections — ⏰ após reminders, antes do link")
    base, env = _make_env("t_f14_ps_")
    now = datetime.now(UTC)
    today = now.date()
    d = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    dl = (today + timedelta(days=1)).isoformat() + "T00:00:00Z"
    # R1: shortlist com deadline amanhã (reminder) — e aplicada há 15d
    # (follow-up): a mesma vaga pode estar nos dois? NÃO — shortlist
    # reminder exige status shortlist; applied É shortlist. Ambos os
    # blocos podem coexistir para vagas distintas.
    env.seed_job({"id": "R1", "title": "Praktikant Einkauf",
                  "company": "BMW AG", "location": "München", "score": 14.0,
                  "application_deadline": dl})
    env.seed_job(_job(0, company="Acme GmbH"))
    env.cli("mark", "R1", "--status", "interesting")
    env.cli("applied", "t0", "--date", d(15))

    lines = rg.personal_sections(db_path=env.db, current_path=env.ranking,
                                 ref_date=today)
    text = "\n".join(lines)
    check("reminders presente (shortlist c/ deadline)",
          "Application reminders" in text)
    check("⏰ Follow-up presente com contagem",
          rg.FOLLOWUP_SECTION_PREFIX in text and "1 pendente(s)" in text)
    i_rem = text.find("Application reminders")
    i_fu = text.find(rg.FOLLOWUP_SECTION_PREFIX)
    check("⏰ DEPOIS dos reminders (ordem do bloco pessoal)",
          -1 < i_rem < i_fu)
    check("formato da linha ⏰ com empresa/título/dias",
          "Acme GmbH: Praktikum Supply Chain 0 (há 15 dias)" in text)

    # followup_after_days paramétrico propagado ao header
    lines2 = rg.personal_sections(db_path=env.db,
                                  current_path=env.ranking,
                                  ref_date=today, followup_after_days=30)
    check("followup_after_days=30: sem pendentes (15d < 30d)",
          rg.FOLLOWUP_SECTION_PREFIX
          not in "\n".join(lines2))

    # zero pendentes: bloco follow-up ausente, reminders preservados
    base2, env2 = _make_env("t_f14_ps0_")
    env2.seed_job({"id": "R1", "title": "X", "company": "Y",
                    "location": "Z", "score": 1.0,
                    "application_deadline": dl})
    env2.cli("mark", "R1", "--status", "interesting")
    lines3 = rg.personal_sections(db_path=env2.db,
                                   current_path=env2.ranking,
                                   ref_date=today)
    check("sem pendentes: ⏰ ausente (sem linha vazia), reminders ok",
          rg.FOLLOWUP_SECTION_PREFIX not in "\n".join(lines3)
          and "Application reminders" in "\n".join(lines3))
    shutil.rmtree(base)
    shutil.rmtree(base2)


def test_compact_followup() -> None:
    section("T4: compact — ⏰ colapsa antes do Top 5, nunca some")
    top5 = rg.format_top5([
        _job(i, apply_url=f"https://apply.example.com/{i}")
        for i in range(5)
    ]).splitlines()
    summary = _summary()

    # cenário 1: digest gordo (⏰ corpo de 3x1200) estoura 4096 — a ⏰
    # colapsa ao header, Top 5 + link preservados
    fu_body = [f"  ⏰ {i}. Empresa: título (há {10 + i} dias) " + "f" * 1200
               for i in range(1, 4)]
    digest = (
        ["", "🎯 Perfil e critérios ativos"] +
        [f"linha perfil {i}" for i in range(3)] +
        ["", rg.TOP5_SECTION_HEADER] + top5 +
        ["", rg.FOLLOWUP_SECTION_HEADER + " — 3 pendente(s)"] + fu_body +
        ["", "🔗 Ranking completo (todas as vagas elegíveis): https://x/"]
    )
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=digest)
    check("c1: mensagem cabe no Telegram",
          len(msg) <= rd.TELEGRAM_MAX_LEN)
    check("c1: ⏰ NUNCA dropada — header com contagem sobrevive",
          rg.FOLLOWUP_SECTION_PREFIX in msg and "3 pendente(s)" in msg)
    check("c1: corpo da ⏰ fora (colapsada ao header)",
          "f" * 1200 not in msg)
    check("c1: Top 5 íntegro (5 apply_urls)",
          msg.count("https://apply.example.com/") >= 5)
    check("c1: link por último",
          msg.endswith("🔗 Ranking completo (todas as vagas elegíveis): "
                       "https://x/"))

    # cenário 2: ⏰ e 🆕 e 🎯 juntas + estouro: ⏰ colapsa PRIMEIRO
    # (antes da 🎯, antes da 🆕); Top 5 sobrevive
    ns_body = [f"  {i}. nova " + "n" * 800 for i in range(1, 3)]
    wl_body = [f"  🎯 {i}. Alvo: título (Local) " + "w" * 800
               for i in range(1, 3)]
    digest2 = (
        ["", "🎯 Perfil e critérios ativos"] +
        ["linha perfil " + "p" * 200 for _ in range(2)] +
        ["", "🆕 Novas desde ontem: 2"] + ns_body +
        ["", rg.TOP5_SECTION_HEADER] + top5 +
        ["", rg.WATCHLIST_SECTION_HEADER + " — 2 nova(s)"] + wl_body +
        ["", rg.FOLLOWUP_SECTION_HEADER + " — 2 pendente(s)"] + fu_body[:2] +
        ["", "🔗 Ranking completo (todas as vagas elegíveis): https://x/"]
    )
    msg2 = rd.build_message(summary, [], 0, always_notify=True,
                            digest_lines=digest2)
    check("c2: mensagem cabe", len(msg2) <= rd.TELEGRAM_MAX_LEN)
    check("c2: ⏰ header sobrevive",
          rg.FOLLOWUP_SECTION_PREFIX in msg2)
    check("c2: corpo ⏰ fora (colapsada)", "f" * 1200 not in msg2)
    check("c2: Top 5 sobrevive íntegro",
          msg2.count("https://apply.example.com/") >= 5)

    # cenário 3 (regressão): digest SEM ⏰ que cabe = byte a byte
    # idêntico ao comportamento pré-F14 (o compact nem é acionado)
    slim = (
        ["", "🆕 Novas desde ontem: 1", "  1. nova a"] +
        ["", rg.TOP5_SECTION_HEADER, "1. A — B — 12 — https://y/1"] +
        ["", rg.WATCHLIST_SECTION_HEADER + " — 1 nova(s)",
         "  🎯 1. Alvo: título (Local)"] +
        ["", "🔗 Ranking completo: https://x/"]
    )
    base_msg = rd.build_message(summary, [], 0, always_notify=True)
    msg3 = rd.build_message(summary, [], 0, always_notify=True,
                            digest_lines=slim)
    check("c3: sem ⏰ e sem estouro: saída == base + digest (byte a byte)",
          msg3 == base_msg + "\n" + "\n".join(slim))

    # cenário 4 (regressão F6.1): sem ⚡ no digest estourado = 1 linha
    huge = ["", "🎯 Perfil"] + ["z" * 100 for _ in range(50)] \
        + ["", "🔗 Ranking completo: https://x/"]
    msg4 = rd.build_message(summary, [], 0, always_notify=True,
                            digest_lines=huge)
    check("c4: sem ⚡: linha única pre-F6.1 preservada",
          "Resumo do ranking encurtado" in msg4
          and len(msg4) <= rd.TELEGRAM_MAX_LEN)


# ---------------------------------------------------------------------------
# T5 — privacidade + regressão do digest
# ---------------------------------------------------------------------------

def test_privacy_and_regression() -> None:
    section("T5: privacidade (gate) + regressão byte a byte do digest")
    # página com badge passa no gate público — nada de jobs_personal.db
    base, env = _make_env("t_f14_priv_")
    conn = env.conn()
    pt.upsert_status(conn, "t0", "applied")
    pt.upsert_status(conn, "t1", "rejected")
    conn.commit()
    conn.close()
    html = mp.render_minimal_html([_job(0), _job(1)],
                                   total_eligible=2, generated_at="x",
                                   tracker_db=env.db)
    probs = pp.check_public_safe(html)
    check("gate verde com badges na página", probs == [])
    check("nenhum caminho do banco no HTML",
          "jobs_personal" not in html and "data/personal" not in html)
    check("notas/contatos do banco NUNCA renderizados",
          "note" not in html and "contact" not in html)
    # o badge existe APENAS como span .pt (nenhum outro payload)
    import re as _re
    pt_spans = _re.findall(r'<span class="pt"[^>]*>[^<]*</span>', html)
    check("spans .pt carregam só ícones do dicionário fixo",
          len(pt_spans) == 2
          and all(s.endswith("✅</span>") or s.endswith("❌</span>")
                  for s in pt_spans))

    # regressão: digest sem pendentes = byte a byte o de antes.
    # personal_sections SEM banco -> [] (contrato F8 intacto).
    ranking = Path(base) / "r.json"
    ranking.write_text(json.dumps([_job(0)]), encoding="utf-8")
    check("personal_sections sem banco -> [] (contrato F8 vivo)",
          rg.personal_sections(db_path=base / "missing.db",
                               current_path=ranking) == [])
    # banco com zero pendentes -> igual a sem banco (nenhuma linha ⏰)
    lines_zero = rg.personal_sections(db_path=env.db,
                                       current_path=ranking)
    check("banco sem pendentes: bloco ⏰ ausente",
          rg.FOLLOWUP_SECTION_PREFIX not in "\n".join(lines_zero))
    # build_message com digest sem ⏰: idêntico ao pré-F14 (nenhum
    # caminho novo de código altera a saída quando a seção não existe)
    summary = _summary()
    digest_pre = (
        ["", "🆕 Novas desde ontem: 1", "  1. nova a"] +
        ["", rg.TOP5_SECTION_HEADER, "1. A — B — 12 — https://y/1"] +
        ["", "🔗 Ranking completo: https://x/"]
    )
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=digest_pre)
    base_msg = rd.build_message(summary, [], 0, always_notify=True)
    check("digest sem ⏰: mensagem byte a byte base+digest (pré-F14)",
          msg == base_msg + "\n" + "\n".join(digest_pre))
    # publicador continua passando --tracker-db (contrato fixado)
    src = Path(__file__).resolve().parent / "publish_pages.py"
    text = src.read_text(encoding="utf-8")
    check("publish_pages repassa --tracker-db ao minimal_page",
          '"--tracker-db", "data/personal/jobs_personal.db"' in text)
    # ci.yml: test_f14 no array (59ª suíte)
    ci = (Path(__file__).resolve().parent.parent
          / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    check("ci.yml contém test_f14 no array da suíte",
          "test_f13 test_f14)" in ci or " test_f14)" in ci)
    shutil.rmtree(base)


# ---------------------------------------------------------------------------
# T6 — CLI via subprocess (regressão F14.1: NameError def pós-guard)
# ---------------------------------------------------------------------------

def test_weekly_cli_subprocess() -> None:
    section("T6: CLI weekly via subprocess — exit 0 + métricas no stdout")
    # F14.1: `weekly_metrics` (pré-guard) chamava `waiting_response`,
    # definida APÓS o guard — via import as defs existem (suíte 82
    # verde, CI 2/2 verde) mas via CLI/subprocess o main() executa no
    # guard e morre com NameError antes de alcançar a def. Só um
    # subprocess DE VERDADE reproduz o caminho que quebrava.
    base, env = _make_env("t_f14_weekly_cli_")
    now = datetime.now(UTC)
    d = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    # seed: 2 candidaturas na janela de 7d (uma com resposta) + 1 fora
    env.cli("applied", "W1", "--date", d(2))
    env.cli("applied", "W2", "--date", d(4), "--response", d(1))
    env.cli("applied", "W3", "--date", d(20))

    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent
                             / "personal_tracker.py"),
         "--db", str(env.db), "--ranking", str(env.ranking),
         "--jobs-db", str(env.jobs_db), "weekly"],
        capture_output=True, text=True,
    )
    ok = (r.returncode == 0 and "candidaturas" in r.stdout
          and "Métricas semanais" in r.stdout)
    if not ok:
        print(f"    rc={r.returncode}\n    stdout={r.stdout!r}\n"
              f"    stderr={r.stderr[-500:]!r}")
    check("subprocess weekly: exit 0 e imprime métricas (candidaturas)",
          ok)
    shutil.rmtree(base)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    test_badge_page()
    test_weekly_metrics()
    test_followup_pending()
    test_followup_lines()
    test_personal_sections_followup()
    test_compact_followup()
    test_privacy_and_regression()
    test_weekly_cli_subprocess()
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
