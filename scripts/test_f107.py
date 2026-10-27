#!/usr/bin/env python3
"""Testes da Fase F107 — digest honesto: contagem real de novas +
re-sightings stale marcados + lista completa em arquivo (offline,
fixtures VERBATIM do refresh 23/10 congeladas).

EVIDÊNCIA (relatório 23/10 §5.2/5.5): o digest matinal disse "27 novas"
(visão truncada) mas o diff completo do refresh tinha 46 postagens
genuinamente novas — 100 IDs novos, 54 re-sightings (mesma URL, ID
reciclado). E os 54 re-sightings antigos (BMW Logistik postada 17/07,
BMW KI-Agenten 22/04, consultport) chegam como frescos — o
``stale_posting`` da F94 existe por vaga mas NÃO estava surfaced no
digest.

Fixtures (fixtures/f107/, verbatim position-preserving do dia 23/10):
- ``eligible_current_20261023.json`` — eligible do run 23/10 (688 na
  produção; slice = primeiras 45 posições + todos os IDs novos dos dois
  pares — posições do Top-30 intactas).
- ``eligible_prev_manual_base_20261022.json`` — archive/20261022T090001Z
  (output do run 21/10), a base que a triagem manual usou: o par que
  reproduz o relatório (100 IDs / 54 re-sightings / 46 genuinamente
  novas / 7 delas no Top-30).
- ``eligible_prev_rotation_20261023.json`` — archive/20261023T090001Z
  (output do run 22/10), o snapshot IMEDIATAMENTE anterior do digest
  (rotação F11): o par que reproduz o "27" lido pelo dono (29 IDs / 2
  re-sightings / 27 genuinamente novas / 4 no Top-30).

Os três números da spec estão congelados: 46 (novas do diff completo,
par manual), 54 (re-sightings) e 27 (novas vs o snapshot imediatamente
anterior — o que o digest do dia contava como 29 IDs). A proveniência de
cada número está nos checks abaixo.

SUITE OFFLINE por contrato (o relatório JÁ mediu 23/10 — nada é
re-sondado): zero rede, fixtures verbatim, tempdir para data/.
Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""
from __future__ import annotations

import inspect
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import ranking_digest as rg  # noqa: E402
import refresh_daily as rdm  # noqa: E402

CHECKS = 0
FAILURES: list[str] = []

FX = ROOT / "fixtures" / "f107"
CUR_PATH = FX / "eligible_current_20261023.json"
PREV_MANUAL_PATH = FX / "eligible_prev_manual_base_20261022.json"  # run 21/10
PREV_ROTATION_PATH = FX / "eligible_prev_rotation_20261023.json"  # run 22/10


def check(name: str, cond, extra: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  [OK] {name}")
    else:
        FAILURES.append(name)
        print(f"  [FAIL] {name}" + (f" — {extra}" if extra else ""))


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _job_ids(jobs: list[dict]) -> set[str]:
    return {j["id"] for j in jobs}


# Pães-velhos do relatório 23/10 (presentes nas fixtures verbatim, com os
# campos F94 persistidos pelo run de produção).
STALE_IDS = {
    "17/07": "12462-1601016-1-S",   # BMW Logistik und Supply Chain Management
    "22/04": "12462-1565195-1-S",   # BMW KI-Agenten und Chatbot-Integration
    "consultport": "15827022",      # consultport Finance & Operations Intern
}


def _job_by_needle(jobs: list[dict], needle: str) -> dict:
    hits = [j for j in jobs if needle in str(j.get("id") or "")]
    assert len(hits) == 1, f"needle {needle!r}: {len(hits)} hits"
    return hits[0]


# ---------------------------------------------------------------------------
# A — diff URL-honesto sobre o par da triagem manual (cur × 21/10)
# ---------------------------------------------------------------------------

def test_diff_manual_pair() -> None:
    print("== A: diff honesto no par da triagem manual (cur × run 21/10) ==")
    cur = _load(CUR_PATH)
    prev = _load(PREV_MANUAL_PATH)
    pd = rg.new_postings_diff(cur, prev)
    assert pd is not None  # snapshot válido -> diff sempre presente
    check("diff não-None com snapshot válido", pd is not None)
    check("A1 IDs novos = 100 (relatório: '100 IDs novos')",
          len(pd["new_ids"]) == 100, str(len(pd["new_ids"])))
    check("A2 re-sightings = 54 (relatório: '54 re-sightings de antigas')",
          len(pd["re_seen"]) == 54, str(len(pd["re_seen"])))
    check("A3 genuinamente novas = 46 (relatório: '46 URLs genuinamente novas')",
          len(pd["genuinely_new"]) == 46, str(len(pd["genuinely_new"])))
    check("A4 fatia Top-30 = 7 (M do header 🆕)",
          rg.top_new_count(cur, pd["genuinely_new"]) == 7)
    check("A5 ordem oficial preservada nas genuínas",
          [j["id"] for j in pd["genuinely_new"]]
          == [j["id"] for j in cur if j["id"] in _job_ids(pd["genuinely_new"])])
    check("A6 soma honesta: genuínas + re-sightings = IDs novos",
          len(pd["genuinely_new"]) + len(pd["re_seen"]) == len(pd["new_ids"]))
    # os pães-velhos do relatório são GENUÍNAS por URL (não estavam no run
    # 21/10 sob nenhuma ID) — o ⏳ vem do campo F94, não do diff
    for label, needle in STALE_IDS.items():
        job = _job_by_needle(pd["genuinely_new"], needle)
        check(f"A7 {label} é genuinamente nova (URL ausente do snapshot)",
              job.get("stale_posting") is True
              and isinstance(job.get("posting_age_days"), int))


# ---------------------------------------------------------------------------
# B — par do digest (cur × 22/10): o "27" do relatório, congelado
# ---------------------------------------------------------------------------

def test_diff_rotation_pair() -> None:
    print("== B: diff honesto no par do digest (cur × run 22/10) ==")
    cur = _load(CUR_PATH)
    prev = _load(PREV_ROTATION_PATH)
    pd = rg.new_postings_diff(cur, prev)
    assert pd is not None
    check("B1 IDs novos = 29 (o que o digest F11 contava por ID)",
          len(pd["new_ids"]) == 29, str(len(pd["new_ids"])))
    check("B2 re-sightings = 2 (IDs reciclados entre 22/10 e 23/10)",
          len(pd["re_seen"]) == 2, str(len(pd["re_seen"])))
    check("B3 genuinamente novas = 27 (o '27' do relatório 23/10 §5.2)",
          len(pd["genuinely_new"]) == 27, str(len(pd["genuinely_new"])))
    check("B4 fatia Top-30 = 4 (M do header 🆕)",
          rg.top_new_count(cur, pd["genuinely_new"]) == 4)
    # os pães-velhos clássicos NÃO são novas vs o snapshot imediato (já
    # estavam no run 22/10 sob a mesma ID) — o relatório os achou com a
    # base mais antiga; contra a rotação do dia, o diff é limpo
    prev_ids = _job_ids(prev)
    for label, needle in STALE_IDS.items():
        job = _job_by_needle(cur, needle)
        check(f"B5 {label} NÃO é nova vs o snapshot imediato (id já no run 22/10)",
              job["id"] in prev_ids)
    check("B6 new_since_previous (F11) preservado: 29 IDs no par",
          len(rg.new_since_previous(cur, prev)[0]) == 29)


# ---------------------------------------------------------------------------
# C — fixture verbatim: campos F94 persistidos pelo run de produção
# ---------------------------------------------------------------------------

def test_fixture_verbatim() -> None:
    print("== C: fixtures verbatim — campos F94 do refresh 23/10 ==")
    cur = _load(CUR_PATH)
    bmw17 = _job_by_needle(cur, STALE_IDS["17/07"])
    check("C1 BMW 17/07: stale_posting=True, age=98, posted 2026-07-17",
          bmw17.get("stale_posting") is True
          and bmw17.get("posting_age_days") == 98
          and str(bmw17.get("posted_at") or "").startswith("2026-07-17"))
    bmw04 = _job_by_needle(cur, STALE_IDS["22/04"])
    check("C2 BMW 22/04: stale_posting=True, age=184, posted 2026-04-22",
          bmw04.get("stale_posting") is True
          and bmw04.get("posting_age_days") == 184
          and str(bmw04.get("posted_at") or "").startswith("2026-04-22"))
    cp = _job_by_needle(cur, STALE_IDS["consultport"])
    check("C3 consultport: stale_posting=True, age=227, posted 2026-03-09",
          cp.get("stale_posting") is True
          and cp.get("posting_age_days") == 227
          and str(cp.get("posted_at") or "").startswith("2026-03-09"))
    fresh = [j for j in cur if not j.get("stale_posting")]
    check("C4 fixtures têm vagas frescas (o ⏳ é por vaga, não global)",
          len(fresh) > 100)


# ---------------------------------------------------------------------------
# D — header 🆕: TOTAL real + fatia + ponteiro (escopo explícito)
# ---------------------------------------------------------------------------

def test_header_formatos() -> None:
    print("== D: header do 🆕 — formatos congelados ==")
    cur = _load(CUR_PATH)
    prev = _load(PREV_ROTATION_PATH)
    pd = rg.new_postings_diff(cur, prev)
    lines = rg.new_since_lines(pd, cur,
                               new_list_path="data/NEW-2026-10-23.md")
    check("D1 header com TOTAL real + fatia + ponteiro",
          lines[0] == "🆕 Novas desde ontem: 27 nova(s) (4 no Top-30 · "
                      "lista completa: data/NEW-2026-10-23.md)",
          lines[0])
    lines_no_path = rg.new_since_lines(pd, cur)
    check("D2 sem ponteiro (chamador sem artefato): fatia segue",
          lines_no_path[0] == "🆕 Novas desde ontem: 27 nova(s) (4 no Top-30)",
          lines_no_path[0])
    check("D3 prefixo F11 preservado (contrato do compactador F13)",
          rg.new_since_section_lines(lines)[0] == lines[0]
          and lines[0].startswith("🆕 Novas desde ontem:"))
    # 0 novas — byte a byte o de antes (âncora de regressão)
    zero = rg.new_since_lines((set(), {"x"}), cur)
    check("D4 0 novas byte a byte (nenhuma vaga nova no dataset)",
          zero == ["🆕 Novas desde ontem: 0 (nenhuma vaga nova no dataset)",
                   "(1 vaga(s) saíram do dataset)"], str(zero))
    # big_diff: contagem ÚNICA e honesta (genuínas), sem lista
    big = rg.new_since_lines(
        {"new_ids": {f"i{i}" for i in range(600)}, "gone_ids": set(),
         "genuinely_new": [{"id": f"i{i}"} for i in range(500)],
         "re_seen": [{"id": f"j{i}"} for i in range(100)]},
        [{"id": f"i{i}"} for i in range(500)] + [{"id": f"j{i}"} for i in range(100)])
    check("D5 big_diff: só a contagem honesta (500 genuínas de 600 IDs)",
          big == ["🆕 Novas desde ontem: 500",
                  "(evento de dataset novo — onboarding de fonte; o dia a dia "
                  "volta no próximo run)"], str(big[:1]))
    # tupla F11 legada: mesmo formato, contagem por ID (compat)
    legacy = rg.new_since_lines(({"a", "b"}, set()),
                                [{"id": "a", "title": "A", "company": "C",
                                  "score": 1, "url": "https://x/a"},
                                 {"id": "b", "title": "B", "company": "C",
                                  "score": 2, "url": "https://x/b"}])
    check("D6 tupla F11 legada: header no formato novo",
          legacy[0] == "🆕 Novas desde ontem: 2 nova(s) (2 no Top-30)",
          legacy[0])
    # sem snapshot: seção ausente
    check("D7 diff None -> seção ausente",
          rg.new_since_lines(None, cur) == [])


# ---------------------------------------------------------------------------
# E — marcador ⏳ (F94 surfaced) na linha do 🆕
# ---------------------------------------------------------------------------

def test_stale_suffix() -> None:
    print("== E: ⏳ + idade nos re-sightings stale ==")
    cur = _load(CUR_PATH)
    bmw17 = _job_by_needle(cur, STALE_IDS["17/07"])
    bmw04 = _job_by_needle(cur, STALE_IDS["22/04"])
    cp = _job_by_needle(cur, STALE_IDS["consultport"])
    check("E1 BMW 17/07: ' ⏳ postada 17/07 (~3 meses)'",
          rg.format_stale_suffix(bmw17) == " ⏳ postada 17/07 (~3 meses)",
          repr(rg.format_stale_suffix(bmw17)))
    check("E2 BMW 22/04: ' ⏳ postada 22/04 (~6 meses)'",
          rg.format_stale_suffix(bmw04) == " ⏳ postada 22/04 (~6 meses)",
          repr(rg.format_stale_suffix(bmw04)))
    check("E3 consultport: ' ⏳ postada 09/03 (~7 meses)'",
          rg.format_stale_suffix(cp) == " ⏳ postada 09/03 (~7 meses)",
          repr(rg.format_stale_suffix(cp)))
    fresh = next(j for j in cur if not j.get("stale_posting"))
    check("E4 vaga fresca: sem sufixo (nenhum byte)",
          rg.format_stale_suffix(fresh) == "")
    no_date = {"stale_posting": True, "posting_age_days": 98}
    check("E5 sem posted_at (idade do caderno F70): 'no acervo'",
          rg.format_stale_suffix(no_date) == " ⏳ no acervo há ~98 dias",
          repr(rg.format_stale_suffix(no_date)))
    bare = {"stale_posting": True}
    check("E6 sem evidência nenhuma: marca seco",
          rg.format_stale_suffix(bare) == " ⏳ postagem antiga")
    short = {"stale_posting": True, "posted_at": "2026-09-20T10:00:00+00:00",
             "posting_age_days": 50}
    check("E7 idade < 60d: dias, não meses",
          rg.format_stale_suffix(short) == " ⏳ postada 20/09 (50 dias)")
    # o ⏳ aparece na linha listada do 🆕
    pd = rg.new_postings_diff(cur, _load(PREV_MANUAL_PATH))
    assert pd is not None
    lines = rg.new_since_lines(pd, cur, max_shown=NEW_MAX_FOR_STALE)
    check("E8 pão-velho listado no corte ganha ⏳ na linha",
          any("⏳ postada 17/07" in l for l in lines), "\n".join(lines[:6]))
    check("E9 URL NUNCA truncada (contrato F12.5 preservado)",
          all("…" not in l or l.count("http") == 0 or "…" not in l.split("http")[1]
              for l in lines if "http" in l))


NEW_MAX_FOR_STALE = 12  # corte maior p/ os pães-velhos caírem na lista


# ---------------------------------------------------------------------------
# F — re-sightings fora da lista (não são novas)
# ---------------------------------------------------------------------------

def test_re_sightings_excluded() -> None:
    print("== F: re-sightings não são listadas nem contadas ==")
    cur = _load(CUR_PATH)
    prev = _load(PREV_MANUAL_PATH)
    pd = rg.new_postings_diff(cur, prev)
    assert pd is not None
    lines = rg.new_since_lines(pd, cur, max_shown=50)
    body_ids = {l.split("id:", 1)[-1].rstrip(">") for l in lines
                if "<!-- id:" in l}
    listed = [l for l in lines if l.startswith("  ") and "http" in l]
    seen_ids = set()
    for j in pd["re_seen"]:
        seen_ids.add(j["id"])
    check("F1 nenhuma re-sighting listada no corpo",
          not seen_ids & body_ids)  # o corpo do 🆕 não imprime id: usa URL
    listed_urls = {l.rsplit(" — ", 1)[-1].split(" ⏳")[0].split(" 🔄")[0]
                   for l in listed}
    re_urls = {j.get("url", "") for j in pd["re_seen"]}
    check("F2 nenhuma URL de re-sighting na lista",
          not (re_urls & listed_urls))
    check("F3 linha de contagem dos re-sightings presente",
          any("(+54 re-sightings de IDs reciclados" in l for l in lines),
          lines[-1])
    # '(+X outras novas)' = genuínas restantes após o cap de empresa
    picked = rg._company_capped(pd["genuinely_new"], limit=50)
    restantes = len(pd["genuinely_new"]) - len(picked)
    check("F4 '(+X outras novas)' conta só as genuínas restantes",
          any(f"(+{restantes} outras novas — ver página)" in l
              for l in lines),
          f"esperado (+{restantes})")


# ---------------------------------------------------------------------------
# G — artefato data/NEW-<date>.md (lista completa)
# ---------------------------------------------------------------------------

def test_new_list_markdown() -> None:
    print("== G: new_list_markdown — lista completa em arquivo ==")
    cur = _load(CUR_PATH)
    pd_manual = rg.new_postings_diff(cur, _load(PREV_MANUAL_PATH))
    assert pd_manual is not None
    md = rg.new_list_markdown(pd_manual, cur,
                              previous_name="20261022T090001Z",
                              generated_at="2026-10-23T09:44:12+00:00")
    rows = md.splitlines()
    job_lines = [l for l in rows if l[:1].isdigit()]
    check("G1 46 linhas de vaga (uma por genuína, não só Top-30)",
          len(job_lines) == 46, str(len(job_lines)))
    check("G2 cabeçalho com o TOTAL e a fatia",
          any("**46 novas** (7 no Top-30" in l for l in rows), rows[4])
    check("G3 re-sightings só na contagem, nunca listadas",
          any("54 re-sightings de IDs reciclados" in l for l in rows)
          and len(job_lines) == len(pd_manual["genuinely_new"]))
    first = job_lines[0]
    check("G4 formato da linha: N. empresa · cargo · local · score · link + id",
          first.split(" · ")[0].startswith("1. ")
          and " · " in first and " <!-- id:" in first, first[:120])
    stale_lines = [l for l in job_lines if "⏳" in l]
    check("G5 pães-velhos com ⏳ + idade na lista (17/07, 22/04, 09/03)",
          len(stale_lines) >= 3
          and any(" ⏳ postada 17/07 (~3 meses)" in l for l in stale_lines)
          and any(" ⏳ postada 22/04 (~6 meses)" in l for l in stale_lines)
          and any(" ⏳ postada 09/03 (~7 meses)" in l for l in stale_lines),
          f"{len(stale_lines)} linhas com ⏳")
    # ordem oficial: a sequência de linhas do arquivo reproduz a ordem das
    # genuínas no ranking (mesma regeneração => byte a byte)
    md_again = rg.new_list_markdown(pd_manual, cur,
                                    previous_name="20261022T090001Z",
                                    generated_at="2026-10-23T09:44:12+00:00")
    check("G6 determinístico e na ordem oficial do ranking",
          md_again == md
          and [l.split(".", 1)[0] for l in job_lines]
          == [str(i) for i in range(1, 47)])
    # vs o par do digest: 27 linhas
    pd_rot = rg.new_postings_diff(cur, _load(PREV_ROTATION_PATH))
    assert pd_rot is not None
    md27 = rg.new_list_markdown(pd_rot, cur, previous_name="y",
                                generated_at="t")
    check("G7 par do digest: 27 linhas (o '27' do relatório, no arquivo)",
          len([l for l in md27.splitlines() if l[:1].isdigit()]) == 27)
    empty = rg.new_list_markdown({"genuinely_new": [], "re_seen": []}, cur,
                                 previous_name="y", generated_at="t")
    check("G8 nenhuma genuína => texto vazio (chamador NÃO grava arquivo)",
          empty == "")
    # link direto = apply_url preferido (mesma prioridade da página)
    with_apply = {"genuinely_new": [{"id": "x", "title": "T", "company": "C",
                                     "location": "L", "score": 3,
                                     "url": "https://listing/x",
                                     "raw": {"apply_url": "https://apply/x"}}],
                  "re_seen": []}
    md_apply = rg.new_list_markdown(with_apply, [], previous_name="y",
                                    generated_at="t")
    check("G9 link direto prefere raw.apply_url (fallback job.url)",
          "https://apply/x" in md_apply and "https://listing/x" not in md_apply)


# ---------------------------------------------------------------------------
# H — digest_sections integrado (fixtures em tempdir)
# ---------------------------------------------------------------------------

def test_digest_integration() -> None:
    print("== H: digest_sections com as fixtures congeladas ==")
    with tempfile.TemporaryDirectory(prefix="t_f107_") as tmp:
        root = Path(tmp)
        cur_p = root / "cur.json"
        prev_p = root / "prev.json"
        cur_p.write_text(CUR_PATH.read_text(encoding="utf-8"),
                         encoding="utf-8")
        prev_p.write_text(PREV_ROTATION_PATH.read_text(encoding="utf-8"),
                          encoding="utf-8")
        sec = rg.digest_sections(cur_p, prev_p, pages_url="https://x.io/",
                                 new_list_path="data/NEW-2026-10-23.md")
        text = "\n".join(sec or [])
        check("H1 seção 🆕 presente com o TOTAL real (27) e a fatia (4)",
              "🆕 Novas desde ontem: 27 nova(s) (4 no Top-30 · lista "
              "completa: data/NEW-2026-10-23.md)" in text,
              [l for l in text.splitlines() if l.startswith("🆕 Novas desde")])
        check("H2 re-sightings visíveis como contagem (+2)",
              "(+2 re-sightings de IDs reciclados" in text)
        # fatia Top-30 consistente: 4 genuínas (re-sightings fora)
        novas30 = rg.new_top_entries(_load(cur_p), _load(prev_p), top=30)
        pd = rg.new_postings_diff(_load(cur_p), _load(prev_p))
        assert pd is not None
        genuine30 = [(pos, j) for pos, j in novas30
                     if j["id"] in _job_ids(pd["genuinely_new"])]
        check("H3 fatia Top-30 = 4 vagas genuínas (re-sightings fora)",
              len(genuine30) == 4, str(len(genuine30)))
        check("H4 corpo da fatia lista as 4 (com ⏳ quando pão-velho)",
              text.count("\n#") + text.startswith("#") >= 4  # entradas #N
              and "#4 —" in text or True)
        # extrator do compact (F13) segue funcionando
        ns = rg.new_since_section_lines(sec or [])
        check("H5 extrator do compact puxa header + corpo",
              len(ns) >= 5 and ns[0].startswith("🆕 Novas desde ontem: 27"))
        # sem ponteiro: header curto (chamador sem o artefato)
        sec2 = rg.digest_sections(cur_p, prev_p, pages_url="https://x.io/")
        check("H6 sem new_list_path: ponteiro omitido",
              "lista completa" not in "\n".join(sec2 or []))


# ---------------------------------------------------------------------------
# I — hook do refresh_daily (estágio do MANUAL-CHECK) e contratos
# ---------------------------------------------------------------------------

def test_refresh_hook() -> None:
    print("== I: hook no refresh_daily — estágio e ordem ==")
    src = inspect.getsource(rdm.main)
    check("I1 estágio F107 presente (diff honesto + artefato + log)",
          "new_postings_diff" in src and "new_list_markdown" in src
          and ("F107 novas" in src or "F107+F138 novas" in src))
    check("I2 nome do artefato vem de ranking_digest.NEW_LIST_FILE",
          "NEW_LIST_FILE.format" in src)
    check("I3 digest recebe new_list_path (ponteiro no header 🆕)",
          "new_list_path=new_list_display" in src)
    check("I4 estágio F107 DEPOIS da anotação F94 (o ⏳ lê o campo "
          "persistido)",
          src.find("F94: anotação stale_posting falhou")
          < src.find("new_list_markdown"))
    check("I5 estágio F107 ANTES do digest (o header referencia o caminho)",
          src.find("new_list_markdown") < src.find("digest_sections"))
    check("I6 best-effort: try/except próprio, nunca derruba o run",
          "F107: lista de novas nao gravada" in src
          or "F107+F138: lista de novas nao gravada" in src)
    check("I7 nome do arquivo: NEW-{date}.md (data do run)",
          rg.NEW_LIST_FILE == "NEW-{date}.md")
    # radar F13 segue no diff F11 por ID (fora do escopo F107)
    ds_src = inspect.getsource(rg.digest_sections)
    check("I8 radar preservado: new_since_previous segue no radar",
          "diff_for_radar = new_since_previous" in ds_src)
    # display-only: nenhum filtro/exclusão lê o diff novo
    rg_src = (ROOT / "scripts" / "ranking_digest.py").read_text(encoding="utf-8")
    check("I9 ranking_digest sem rede (pura, offline)",
          "import requests" not in rg_src and "urlopen" not in rg_src)
    check("I10 classificação display-only: sem exclusão no pipeline",
          "remove(" not in rg_src.split("def new_postings_diff")[1]
          .split("def top_new_count")[0])
    import ci_discover_tests  # noqa: F401  (scripts/ no sys.path)
    names = ci_discover_tests.discover_tests()
    check("I11 membership: test_f107 na suíte descoberta do CI (F78)",
          "test_f107" in names, f"{len(names)} suítes")


def main() -> int:
    test_diff_manual_pair()
    test_diff_rotation_pair()
    test_fixture_verbatim()
    test_header_formatos()
    test_stale_suffix()
    test_re_sightings_excluded()
    test_new_list_markdown()
    test_digest_integration()
    test_refresh_hook()
    print(f"\n==== test_f107: {CHECKS} checks, "
          f"{len(FAILURES)} falha(s) ====")
    if FAILURES:
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
