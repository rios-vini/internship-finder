"""Testes da Fase F6 — pagina publica MINIMA + Telegram top-5 (100% offline).

Cobre os dois produtos da fase sem rede e sem data/ de producao:

- ``scripts/minimal_page.py``: render do top-50 com fixtures sinteticas —
  campos obrigatorios (titulo/empresa/local/score/apply_url/badge 🛂),
  AUSENCIA dos campos mortos (application_deadline, official_page, intel de
  enrichment), tamanho < 150 KB (cap duro da spec; alvo 100 KB), gate
  ``check_public_safe`` verde, e o nucleo JS de filtro executado em node
  quando disponivel (mesmo metodo do test_f5).
- ``ranking_digest.format_top5``: 5 vagas -> 5 linhas compactas; 0 vagas
  -> mensagem graciosa; truncagem respeitando o limite (linhas inteiras).
- ``publish_pages.render_ranking_html`` INTEGRADO: chama o minimal_page
  como subprocesso num repo-fixture (mesmo desenho do test_publish_pages)
  e o resultado passa no gate de seguranca.
- Mecanica de deploy intacta: ``publish_html`` atomico/condicional ja
  coberta pelo test_publish_pages (roda na suite; aqui so o render novo).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import publish_pages as pp  # noqa: E402
import ranking_digest as rd  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures sinteticas (offline; formato real do eligible_jobs.json)
# ---------------------------------------------------------------------------

def _job(i: int, *, visa=None, company="Acme", apply_url=None, score=10.0,
         title=None, url=None) -> dict:
    """Vaga no formato do eligible_jobs.json (campos que a F6 consome)."""
    job = {
        "id": f"t{i}", "title": title or f"Praktikum Supply Chain {i}",
        "company": company, "location": "Berlin, BE, DE, 10115",
        "country_iso": "de", "score": score,
        "url": url or f"https://jobs.example.com/{i}",
        "description": ("Werkstudent Supply Chain Management mit Fokus auf "
                        "Logistik und Beschaffung. " * 30),
        "employment_type": "Working Student",
        "posted_at": "2026-10-01T00:00:00+00:00",
        # campo MORTO (F1): validade do FEED — NUNCA pode ser renderizado
        "application_deadline": "2026-10-31T00:00:00+00:00",
        "raw": {"apply_url": apply_url} if apply_url else {},
    }
    if visa is not None:
        job["visa_friendly"] = visa
    return job


def _jobs_realistic(n: int = 50) -> list[dict]:
    """n vagas variadas (algumas visa-friendly, uma com apply_url)."""
    out = []
    for i in range(n):
        company = ["SAP", "BoschGroup", "BASF", "STIHL", "VW", "Miebach"][i % 6]
        out.append(_job(
            i, score=16.0 - i * 0.2,
            company=company,
            visa=(i % 3 == 0),
            apply_url=f"https://apply.example.com/{i}" if i % 2 == 0 else None,
        ))
    return out


# ---------------------------------------------------------------------------
# F6.1 — render minimal (campos obrigatorios / mortos / tamanho)
# ---------------------------------------------------------------------------

def test_render_minimal() -> None:
    print("== F6.1: render minimal — campos, mortos ausentes, tamanho ==")
    jobs = _jobs_realistic(50)
    html = mp.render_minimal_html(
        jobs, total_eligible=478, generated_at="2026-10-03 12:00",
    )
    size = len(html.encode("utf-8"))
    # F11: cap de EXIBICAO 2 vagas/empresa — 50 vagas em 6 empresas => 12 cards
    n_cards = html.count("<li class=")
    check("cap 2/empresa aplicado (50 vagas/6 empresas -> 12 cards)",
          n_cards == 12)
    check("tamanho < 150 KB (cap duro)", size < mp.PAGE_HARD_CAP_BYTES)
    check("tamanho <= 100 KB (alvo)", size <= mp.PAGE_TARGET_BYTES,
          )
    check("sem application_deadline (morto F1)",
          "application_deadline" not in html and "2026-10-31" not in html)
    check("sem official_page (morto F1)", "official_page" not in html)
    check("sem intel de enrichment (Fase 3 morta)", "🔎" not in html
          and "enrichment" not in html.lower())
    check("badge visa_friendly presente (🛂)", "🛂" in html)
    # F11: o badge conta por CARD RENDERIZADO (pos-cap), nao por vaga de
    # entrada — recalcular contra a lista pos-cap.
    from minimal_page import apply_company_cap
    shown = apply_company_cap(jobs)
    n_vf = sum(1 for j in shown if j.get("visa_friendly"))
    check("contagem de badges = vagas visa_friendly EXIBIDAS",
          html.count('vf-on') == n_vf)
    check("titulo da 1a vaga presente", "Praktikum Supply Chain 0" in html)
    check("empresa presente", ">SAP<" in html or "SAP ·" in html)
    check("local (cidade) presente", "Berlin" in html)
    check("score presente", 'data-s="16"'.replace('"', '"') in html
          or "16.0" in html)
    check("apply_url vira botao candidatar-se",
          html.count('>candidatar-se') == sum(
              1 for j in shown if j.get("raw", {}).get("apply_url")))
    check("job.url usado como fallback (sem apply_url)",
          'abrir vaga' in html)
    check("sem caminho absoluto da VPS", "/home/" not in html
          and "/tmp/" not in html)
    check("gate check_public_safe aprova", pp.check_public_safe(html) == [])
    # escape: titulo com <script> nao executa
    evil = _job(99, title='<script>alert(1)</script> Evil')
    html_evil = mp.render_minimal_html([evil], total_eligible=1,
                                       generated_at="x")
    check("escape HTML: <script> no titulo nao vira tag",
          "<script>alert" not in html_evil
          and "<script>" in html_evil)
    check("gate reprova se vazasse token (sanity do gate)",
          pp.check_public_safe(html + "ghp_" + "A" * 30) != [])


def test_render_top_cap() -> None:
    print("== F6.1b: cap do top e top menor ==")
    jobs = _jobs_realistic(80)
    html = mp.render_minimal_html(jobs, total_eligible=80,
                                  generated_at="x", top=50)
    # F11: cap 2/empresa — 80 vagas em 6 empresas -> 12 cards (o corte em
    # ``top`` 50 e o teto de VAGAS EXIBIDAS, nao de entrada).
    check("80 vagas/6 empresas -> 12 cards (cap 2/empresa)",
          html.count("<li class=") == 12)
    html2 = mp.render_minimal_html(jobs[:3], total_eligible=80,
                                    generated_at="x", top=50)
    check("3 vagas -> 3 cards", html2.count("<li class=") == 3)
    check("rodape informa o total (80)", "80 vagas elegíveis" in html)


def test_visa_retrocompat() -> None:
    print("== F6.1c: badge visa via fallback do company_intel (pre-F5) ==")
    # job SEM campo visa_friendly (snapshot pre-F5) — re-deriva do map
    entry = {"visa_policy": "explicit_support"}
    job = _job(1, visa=None)
    job.pop("visa_friendly", None)
    check("fallback explicit_support -> True",
          mp._visa_friendly(job, entry) is True)
    entry2 = {"visa_policy": "unclear"}
    check("fallback unclear -> True (VISA_FRIENDLY_STATES F5)",
          mp._visa_friendly(job, entry2) is True)
    entry3 = {"visa_policy": "candidate_must_have_authorization"}
    check("fallback candidate_must_have_authorization -> False",
          mp._visa_friendly(job, entry3) is False)
    check("sem entry e sem campo -> False",
          mp._visa_friendly(job, None) is False)
    job["visa_friendly"] = True
    check("campo do pipeline (F5) TEM prioridade sobre o fallback",
          mp._visa_friendly(job, {"visa_policy": "not_verified"}) is True)


def test_salary_only_when_cited() -> None:
    print("== F6.1d: salario so quando citado (evidencia textual) ==")
    j = _job(1)
    j["description"] = ("Wir bieten ein monatliches Gehalt von 2.117 €. "
                        "Weitere Aufgaben im Supply Chain Management.")
    html = mp.render_minimal_html([j], total_eligible=1, generated_at="x")
    check("salario citado aparece (€2117)", "€2117" in html)
    j2 = _job(2)
    html2 = mp.render_minimal_html([j2], total_eligible=1, generated_at="x")
    check("sem salario citado -> sem valor inventado",
          "€" not in html2.split("<body>")[1].split("<ol")[0]
          and 'class="sal"' not in html2)


def test_js_filter_node() -> None:
    print("== F6.1e: nucleo JS do filtro executado em node ==")
    if shutil.which("node") is None:
        print("  [SKIP] node ausente — nucleo JS nao executado (CI tem node)")
        return
    js = mp._JS
    harness = """
var __hidden = 0, __shown = [];
var document = {
  querySelectorAll: function () { return []; },
  getElementById: function () { return null; },
  addEventListener: function () {},
};
%(js)s
console.log("js-ok");
""" % {"js": js}
    proc = subprocess.run(["node", "-"], input=harness,
                          capture_output=True, text=True, timeout=30)
    check("nucleo JS roda em node sem erro (guard document.getElementById null)",
          proc.returncode == 0 and "js-ok" in proc.stdout)


# ---------------------------------------------------------------------------
# F6.2 — format_top5 (funcao pura)
# ---------------------------------------------------------------------------

def test_format_top5() -> None:
    print("== F6.2: format_top5 — 5 linhas, vazia graciosa, truncagem ==")
    jobs = [
        {"id": "a", "title": "Praktikum Data", "company": "STIHL",
         "score": 15.75, "url": "https://jobs.example.com/a",
         "raw": {"apply_url": "https://apply.example.com/a"}},
        {"id": "b", "title": "Werkstudent Logistik", "company": "Bosch",
         "score": 14.0, "url": "https://jobs.example.com/b", "raw": {}},
        {"id": "c", "title": "Intern SCM", "company": "BASF",
         "score": 12.5, "url": "https://jobs.example.com/c", "raw": {}},
        {"id": "d", "title": "Praktikum Einkauf", "company": "VW",
         "score": 11.0, "url": "https://jobs.example.com/d", "raw": {}},
        {"id": "e", "title": "Working Student Analytics", "company": "SAP",
         "score": 10.5, "url": "https://jobs.example.com/e", "raw": {}},
    ]
    text = rd.format_top5(jobs)
    lines = text.splitlines()
    check("5 vagas -> 5 linhas", len(lines) == 5)
    check("formato N. titulo — empresa — score — url",
          lines[0].startswith("1. Praktikum Data — STIHL — 15.75 — https://"))
    check("apply_url tem prioridade sobre job.url",
          "apply.example.com/a" in lines[0])
    check("sem apply_url cai no job.url",
          "jobs.example.com/b" in lines[1])
    check("0 vagas -> mensagem graciosa",
          "Nenhuma vaga elegível" in rd.format_top5([]))
    # >5 vagas: so as 5 primeiras
    many = jobs + [{"id": f"x{i}", "title": f"X{i}", "company": "C",
                    "score": 1.0, "url": "https://e.com/x"} for i in range(5)]
    check("lista maior -> exatamente 5 linhas",
          len(rd.format_top5(many).splitlines()) == 5)
    # truncagem segura: limite curto corta linhas inteiras
    tight = rd.format_top5(jobs, max_len=150)
    check("truncagem respeita o limite", len(tight) <= 150)
    check("truncagem avisa o corte", "na página" in tight)
    check("truncagem nao corta no meio de linha",
          all(ln.endswith("…") or "—" in ln or ln.startswith("(")
              for ln in tight.splitlines()))
    # limite generoso nao trunca
    full = rd.format_top5(jobs, max_len=4096)
    check("limite 4096 nao trunca 5 linhas reais", full == text)
    # URL invalida (javascript:) NUNCA entra
    evil = [{"id": "z", "title": "Evil", "company": "X", "score": 1.0,
             "url": "javascript:alert(1)", "raw": {"apply_url": "javascript:alert(1)"}}]
    check("scheme nao-http rejeitado (javascript: -> —)",
          "javascript:" not in rd.format_top5(evil))


# ---------------------------------------------------------------------------
# F6.3 — integracao publish_pages -> minimal_page (subprocesso real)
# ---------------------------------------------------------------------------

def _make_repo_fixture(tmp_root: Path) -> Path:
    """Repo fake: src/ copiado + scripts (minimal_page/publish_pages) +
    data/eligible_jobs.json com 55 vagas (5 alem do top-50)."""
    root = Path(__file__).resolve().parent.parent
    (tmp_root / "scripts").mkdir(parents=True)
    for name in ("minimal_page.py", "publish_pages.py"):
        shutil.copy2(root / "scripts" / name, tmp_root / "scripts" / name)
    shutil.copytree(
        root / "src" / "internship_finder",
        tmp_root / "src" / "internship_finder",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    ci = root / "company_intel"
    if (ci / "company_intelligence.json").exists():
        shutil.copytree(ci, tmp_root / "company_intel",
                        ignore=shutil.ignore_patterns("__pycache__"))
    data_dir = tmp_root / "data"
    data_dir.mkdir()
    # F11: empresas DISTINTAS (30 empresas x ~2) — o corte 2/empresa nao
    # pode mascarar o cap do ``top``; o cenario antigo (6 empresas
    # ciclando) parava em 12 cards por causa do cap novo.
    jobs = []
    for i in range(55):
        jobs.append(_job(i, score=16.0 - i * 0.2,
                         company=f"Firma {i} GmbH"))
    (data_dir / "eligible_jobs.json").write_text(
        json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    return tmp_root


def test_publish_integration() -> None:
    print("== F6.3: render_ranking_html via minimal_page (subprocesso) ==")
    with tempfile.TemporaryDirectory(prefix="t_f6_pp_") as tmp:
        fake_root = _make_repo_fixture(Path(tmp))
        out = Path(tmp) / "out" / "index.html"
        out.parent.mkdir()
        html = pp.render_ranking_html(fake_root, out, top=pp.PUBLIC_TOP)
        size = len(html.encode("utf-8"))
        check("HTML gerado pelo minimal_page", "top do dia" in html)
        # F11: PAGE_TOP=100; 55 vagas em 55 empresas -> 55 cards PRINCIPAIS
        # (a seção Materials opcional adiciona os seus — contar o <ol>).
        main_list = html.split('<ol id="list">')[1].split("</ol>")[0]
        check("55 vagas/55 empresas -> 55 cards no ranking principal",
              main_list.count("<li class=") == 55)
        check("seção Materials presente (top 10, perfil alternativo)",
              "🧪 Materials Engineering" in html
              and html.count("<li class=") == 55 + mp.MATERIALS_SECTION_TOP)
        check("tamanho < 150 KB no cenario integrado", size < mp.PAGE_HARD_CAP_BYTES)
        check("tamanho <= 100 KB (alvo) no cenario integrado",
              size <= mp.PAGE_TARGET_BYTES)
        check("arquivo temporario removido", not out.exists())
        check("gate de seguranca aprova o HTML integrado",
              pp.check_public_safe(html) == [])
        check("sem caminho absoluto da fixture no HTML",
              str(fake_root) not in html)
        # JSON/CSV completos NAO sao tocados pelo render (contrato F6)
        data_file = fake_root / "data" / "eligible_jobs.json"
        check("JSON de entrada intocado pelo render",
              len(json.loads(data_file.read_text(encoding="utf-8"))) == 55)


# ---------------------------------------------------------------------------
# F6.4 — digest integra o top-5 (montagem completa)
# ---------------------------------------------------------------------------

def test_digest_top5_integration() -> None:
    print("== F6.4: digest_sections embute o Top 5 com apply_url ==")
    with tempfile.TemporaryDirectory(prefix="t_f6_dg_") as tmp:
        base = Path(tmp)
        cur = _jobs_realistic(6)[:5]
        prev = cur[:2]
        for name, payload in (("cur.json", cur), ("prev.json", prev)):
            (base / name).write_text(json.dumps(payload), encoding="utf-8")
        sections = rd.digest_sections(base / "cur.json", base / "prev.json",
                                      pages_url="https://x.github.io/r/")
        text = "\n".join(sections or [])
        check("secao Top 5 (candidatura direta) presente",
              "⚡ Top 5 do dia (candidatura direta)" in text)
        check("linha com apply_url no digest",
              "https://apply.example.com/0" in text)
        check("secao antes do link final",
              text.index("⚡ Top 5") < text.index("🔗 Ranking completo"))
        check("link continua sendo a ultima linha",
              (sections or [])[-1].startswith("🔗 Ranking completo"))
        # mensagem completa cabe no Telegram (limite 4096)
        from refresh_daily import TELEGRAM_MAX_LEN
        check("digest completo < 4096 (cenario compacto)",
              len(text) < TELEGRAM_MAX_LEN)


def test_top5_no_digest_when_empty() -> None:
    print("== F6.4b: sem vagas -> sem secao (digest None) ==")
    with tempfile.TemporaryDirectory(prefix="t_f6_dg2_") as tmp:
        base = Path(tmp)
        (base / "cur.json").write_text("[]", encoding="utf-8")
        check("ranking vazio -> digest None (regra existente preservada)",
              rd.digest_sections(base / "cur.json", base / "prev.json",
                                 pages_url="https://x/") is None)


def main() -> None:
    test_render_minimal()
    test_render_top_cap()
    test_visa_retrocompat()
    test_salary_only_when_cited()
    test_js_filter_node()
    test_format_top5()
    test_publish_integration()
    test_digest_top5_integration()
    test_top5_no_digest_when_empty()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()
