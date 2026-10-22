#!/usr/bin/env python3
"""F96 — Fila manual-check com link direto + id_collision (offline).

O DELTA (ITENS 11 + 8 + 7-typo da delegação): itens não-avaliáveis
(F87) e borderline ficam espalhados no registro sem link direto — "ficar
procurando tá dando confusão". F96 gera o ``data/MANUAL-CHECK.md`` no
run diário (estágio do refresh, junto ao digest) com UMA linha por item:
empresa, cargo, link DIRETO (alvo final dos redirects rdr/jump), motivo
(saml_wall | empty_desc | js_only | cookie_wall | borderline) e data do
sighting — mais o flag ``id_collision`` (Consultport recruitee "2100111"
colidindo com a Simvia morta; flag p/ revisão manual, NUNCA remove,
NUNCA funde).

Doutrina testada (F87 mantida pela spec F96): a fila é PARALELA — o
Top-5 NÃO é filtrado, nenhuma vaga sai do ranking; o dono vê o ⚠️ no
card, a linha no digest e agora o arquivo com links prontos.

Fixtures VERBATIM (doc do dono + eligible/caderno F70 medidos):
henkel csod ×4 (89534/89499/89644/89756 — SAML wall, fragmento de 584
chars medido na F87), Amazon Koblenz absolventa 13423224 (desc vazia),
Consultport recruitee 2100111 (viva) × Simvia (morta; IDs reais do
caderno: 2638996/2700387/2770853 + o 2100111 do doc), Lidl rdr stub Ref
753653 com alvo final medido na F94 (209.849B). Colisões de variante de
tenant do MESMO empregador (Allegion×SimonsVoss) e par vivo×vivo do
mesmo grupo (RELX×LexisNexis) = controle negativo (não acende).

Zero rede: openers fake scriptados, tempdir para data/ e caderno; nada
de data/ de produção. Standalone exit-code: imprime [OK]/[FAIL]; rc=0
só se tudo passar.
"""
from __future__ import annotations

import inspect
import json
import sqlite3
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import manual_check as mc  # noqa: E402
import ranking_digest  # noqa: E402
import refresh_daily as rd  # noqa: E402
import url_liveness as ul  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def check(name: str, cond, detail: str | None = None) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"[OK] {name}" + (f" — {detail}" if detail else ""))
    else:
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (doc do dono 21/10 + caderno F70/eligible medidos)
# ---------------------------------------------------------------------------

HENKEL_DOC_IDS = (89534, 89499, 89644, 89756)  # doc: "henkel csod ×4"


def _henkel_desc_584() -> str:
    """Fragmento de wall (584 chars, caso 89534 medido na F87).

    Texto de anúncio real truncado pelo wall — SEM marcador textual de
    login (o diagnose F87 é ``desc_curta`` <600; o wall em si só aparece
    no veredito de liveness). Pad determinístico até 584.
    """
    base = (
        "About this Position What you´ll do Become part of a team that "
        "bridges business operations, data, and digital solutions within "
        "Henkel Adhesive Technologies Transform business questions into "
        "insights, r"
    )
    pad = " Support cross-functional projects and master data quality."
    full = base + pad * (584 // len(pad) + 1)
    return full[:584]


def henkel_job(n: int, **extra) -> dict:
    job = {
        "id": f"henkel|cornerstone:henkel:{n}",
        "company": "henkel",
        "title": f"Praktikum Supply Chain {n}",
        "url": f"https://henkel.csod.com/ux/ats/careersite/1/job/{n}?c=henkel",
        "description": _henkel_desc_584(),
    }
    job.update(extra)
    return job


# Amazon Koblenz absolventa 13423224 — VERBATIM do eligible de produção
# (21/10): desc vazia ("owner deve checar no browser", ITEM 8).
AMAZON_KOBLENZ_13423224 = {
    "id": "Amazon Koblenz GmbH - C44|absolventa:13423224",
    "company": "Amazon Koblenz GmbH - C44",
    "title": "Praktikum im Bereich Logistik - Kobern-Gondorf - Start 2027",
    "location": None,
    "url": ("https://www.absolventa.de/stellenangebote/"
            "13423224-b-praktikum-im-bereich-logistik-kobern-gondorf-"
            "start-2027"),
    "description": "",
}

# Consultport recruitee 2100111 — viva no eligible (desc avaliável);
# o doc: "colide com a Simvia morta (provável typo — ID real incerto)".
CONSULTPORT_2100111 = {
    "id": "Consultport|sf_dataset:recruitee:2100111",
    "company": "Consultport",
    "title": "Finance & Operations Intern (m/f/d)",
    "location": "Berlin, Berlin, Germany",
    "url": "https://consultport.recruitee.com/o/finance-operations-intern-mfd",
    "description": (
        "Finance & Operations Intern (m/f/d) — you will support the "
        "operations team with vendor onboarding, invoicing and data "
        "quality. " * 60
    ),
}

# Simvia (morta): IDs reais no caderno F70 (21/10) + o 2100111 do doc.
SIMVIA_SEEN_JOB_IDS = (
    "Simvia|sf_dataset:recruitee:2100111",
    "Simvia|sf_dataset:recruitee:2638996",
    "Simvia|sf_dataset:recruitee:2700387",
    "Simvia|sf_dataset:recruitee:2770853",
)

# Lidl rdr stub (F94 G3): alvo final medido (209.849B) — o link direto da
# fila é o ALVO, não o stub.
LIDL_STUB_753653 = "https://jobs.lidl.de/rdr/jump-to-job/753653"
LIDL_ALVO_753653 = ("https://jobs.lidl.de/jobs/praktikum-controlling-"
                    "international-projekte-neckarsulm-753653")
LIDL_STUB_JOB = {
    "id": "lidlstiftup2|sf_dataset:successfactors:753653",
    "title": "Praktikum Controlling International - Projekte",
    "company": "lidlstiftup2",
    "location": "Neckarsulm, DE",
    "url": LIDL_STUB_753653,
    "description": "Praktikum im Controlling International - Projekte.",
    "liveness_status": "alive",
    "liveness_detail": "",
    "liveness_final_url": LIDL_ALVO_753653,
    "liveness_checked_at": "2026-10-22T09:00:00+00:00",
}

SAML_FINAL_URL = ("https://henkel.csod.com/samldefault.aspx?ouid=2"
                  "&ReturnUrl=https%3a%2f%2fhenkel.csod.com"
                  "%2fcommon%2frestrictedarea.aspx")


def _opener(status_map: dict, error_urls: dict):
    """Opener fake: url => _Resp(final_url, corpo) | HTTPError(code)."""
    class _Resp:
        def __init__(self, final_url, body):
            self.url = final_url
            self._body = body.encode("utf-8")

        def read(self, n=-1):
            return self._body if n == -1 else self._body[:n]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def open_url(req, timeout=None):
        url = req.full_url
        if url in error_urls:
            raise urllib.error.HTTPError(url, int(error_urls[url]),
                                         "fake", {}, None)
        if url in status_map:
            final_url, body = status_map[url]
            return _Resp(final_url, body)
        raise urllib.error.URLError("url fora do script do teste")

    return open_url


def _job_page_body(size: int = 60_000) -> str:
    return ("<html><head><title>Praktikum Procurement | Acme</title></head>"
            "<body>" + "<p>procurement supply chain logistics</p> " * size
            + "</body></html>")


# ---------------------------------------------------------------------------
# G1 — motivo_of: mapeamento F87 -> vocabulário da spec + prioridade
# ---------------------------------------------------------------------------

def test_motivo_of() -> None:
    section("G1 — motivo_of: F87 mapado na spec; prioridade; dead fora")
    check("desc_vazia -> empty_desc",
          mc.motivo_of({"not_assessable": "desc_vazia"}) == "empty_desc")
    check("login_wall -> saml_wall",
          mc.motivo_of({"not_assessable": "login_wall"}) == "saml_wall")
    check("desc_curta -> borderline",
          mc.motivo_of({"not_assessable": "desc_curta"}) == "borderline")
    check("liveness unknown + saml detail -> saml_wall",
          mc.motivo_of({"liveness_status": "unknown",
                        "liveness_detail": "saml wall (url:/samldefault)"})
          == "saml_wall")
    check("liveness unknown + http 403 -> detalhe cru (honesto)",
          mc.motivo_of({"liveness_status": "unknown",
                        "liveness_detail": "http 403"}) == "http 403")
    check("liveness unknown sem detalhe -> unknown",
          mc.motivo_of({"liveness_status": "unknown",
                        "liveness_detail": ""}) == "unknown")
    check("manual_check_required sem status => saml via detalhe",
          mc.motivo_of({"manual_check_required": True,
                        "liveness_detail": "saml wall (url)"}) == "saml_wall")
    check("id_collision vence qualquer outro sinal",
          mc.motivo_of({"id_collision": "Simvia",
                        "not_assessable": "login_wall",
                        "liveness_status": "unknown",
                        "liveness_detail": "saml wall (url)"})
          == "id_collision")
    check("saml_wall vence borderline (henkel 584 + wall)",
          mc.motivo_of({"not_assessable": "desc_curta",
                        "liveness_status": "unknown",
                        "liveness_detail": "saml wall (url)"}) == "saml_wall")
    check("liveness dead NÃO entra na fila (máquina julgou)",
          mc.motivo_of({"not_assessable": "desc_vazia",
                        "liveness_status": "dead"}) is None)
    check("avaliável e viva => fora da fila",
          mc.motivo_of({"description": "x" * 900}) is None)
    check("vaga não-dict => None (defensivo)", mc.motivo_of(None) is None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# G2 — resolve_direct_link: alvo final, não o redirect
# ---------------------------------------------------------------------------

def test_resolve_direct_link() -> None:
    section("G2 — link direto: wrappers rdr/jump + alvo do liveness")
    check("URL de careersite JÁ é o link direto (henkel csod)",
          mc.resolve_direct_link(
              "https://henkel.csod.com/ux/ats/careersite/1/job/89534?c=henkel")
          == "https://henkel.csod.com/ux/ats/careersite/1/job/89534?c=henkel")
    wrapped = ("https://feed.example.com/go?id=1"
               "&rdr=https%3A%2F%2Fhenkel.csod.com%2Fux%2Fats%2Fcareersite"
               "%2F1%2Fjob%2F89534%3Fc%3Dhenkel")
    check("?rdr= percent-encoded desembrulhado OFFLINE",
          mc.resolve_direct_link(wrapped)
          == "https://henkel.csod.com/ux/ats/careersite/1/job/89534?c=henkel")
    chained = ("https://a.example.com/go?rdr=https%3A%2F%2Fb.example.com"
               "%2Fjump%3Furl%3Dhttps%253A%252F%252Fc.example.com%252Fjob"
               "%252F1")
    check("cadeia rdr->jump->alvo resolve em hops",
          mc.resolve_direct_link(chained) == "https://c.example.com/job/1")
    check("self-wrapped rdr termina no alvo (guard de ciclo, ≤5 hops)",
          mc.resolve_direct_link(
              "https://x.example.com/?rdr=https%3A%2F%2Fx.example.com%2F")
          == "https://x.example.com/")
    check("alvo cru (não-encoded) em ?u= também sai",
          mc.resolve_direct_link("https://go.example.com/?u=https://ok.example.com/vaga")
          == "https://ok.example.com/vaga")
    check("stub Lidl SEM final_url fica o stub (honesto)",
          mc.resolve_direct_link(LIDL_STUB_753653) == LIDL_STUB_753653)
    check("stub Lidl + final_url do liveness => ALVO final",
          mc.resolve_direct_link(LIDL_STUB_753653, LIDL_ALVO_753653)
          == LIDL_ALVO_753653)
    check("final SAML (IdP) NUNCA vira link direto",
          mc.resolve_direct_link(
              "https://henkel.csod.com/ux/ats/careersite/1/job/89534?c=henkel",
              SAML_FINAL_URL)
          == "https://henkel.csod.com/ux/ats/careersite/1/job/89534?c=henkel")
    check("final homepage NUNCA vira link direto",
          mc.resolve_direct_link("https://x.example.com/jobs/1",
                                 "https://x.example.com/") 
          == "https://x.example.com/jobs/1")
    check("final == original => original",
          mc.resolve_direct_link("https://x.example.com/jobs/1",
                                 "https://x.example.com/jobs/1")
          == "https://x.example.com/jobs/1")
    check("url vazia => string vazia", mc.resolve_direct_link("") == "")


# ---------------------------------------------------------------------------
# G3 — provider_id_plausible: shape medida (recruitee = numérico 6–7)
# ---------------------------------------------------------------------------

def test_provider_id_plausible() -> None:
    section("G3 — ID plausível por provedor (shape medida no caderno F70)")
    check("recruitee 7 dígitos (doc: '2100111') => plausível",
          mc.provider_id_plausible("sf_dataset:recruitee", "2100111") is True)
    check("recruitee 6 dígitos (9 keys medidas) => plausível",
          mc.provider_id_plausible("sf_dataset:recruitee", "2638996") is True)
    check("recruitee com letras => NÃO plausível",
          mc.provider_id_plausible("sf_dataset:recruitee", "21o0111") is False)
    check("recruitee 8 dígitos => NÃO plausível",
          mc.provider_id_plausible("sf_dataset:recruitee", "21001111") is False)
    check("provedor sem shape medida => None (sem checagem, nunca bloqueia)",
          mc.provider_id_plausible("sf_dataset:workday", "JR29775") is None)


# ---------------------------------------------------------------------------
# G4 — detect_id_collisions: o caso do doc + controles negativos medidos
# ---------------------------------------------------------------------------

def test_detect_id_collisions() -> None:
    section("G4 — id_collision: Consultport×Simvia acende; falsos medidos não")
    history = {
        ("sf_dataset:recruitee", "2100111"): {"simvia": "Simvia"},
    }
    ranking = [dict(CONSULTPORT_2100111)]
    stats = mc.detect_id_collisions(ranking, history)
    check("colisão do doc acende (1 flag)",
          stats["flagged"] == 1 and stats["checked"] == 1, str(stats))
    check("flag no registro com a empresa ORIGINAL (legível)",
          ranking[0].get("id_collision") == "Simvia",
          str(ranking[0].get("id_collision")))
    check("colisões reportadas com o provider_id",
          stats["collisions"][0]["provider_id"] == "sf_dataset:recruitee:2100111"
          and stats["collisions"][0]["collides_with"] == ["Simvia"],
          str(stats["collisions"]))
    # NUNCA remove, NUNCA funde: a vaga segue no ranking intacta
    check("flag é sinal: vaga NÃO sai do ranking",
          len(ranking) == 1 and ranking[0]["id"] == CONSULTPORT_2100111["id"])

    # controle negativo MEDIDO (caderno F70): variantes de tenant do MESMO
    # empregador (Allegion×SimonsVoss compartilham JR29775) NÃO são colisão
    # — no mapa do caderno ambas normalizam para "allegion" (load_id_history
    # deduplica: 1ª original vence)
    allegion_hist = {
        ("sf_dataset:workday", "JR29775"): {
            "allegion": "Allegion (careers SimonsVoss English)"},
    }
    allegion_ranking = [{"id": "Allegion|sf_dataset:workday:JR29775",
                         "company": "Allegion", "title": "t",
                         "url": "https://x/1"}]
    stats2 = mc.detect_id_collisions(allegion_ranking, allegion_hist)
    check("variantes de tenant do MESMO empregador não acendem",
          stats2["flagged"] == 0, str(stats2))

    # par vivo×vivo (RELX×LexisNexis, mesmo grupo — medido R119275): sem
    # ausente => sem flag
    relx_ranking = [
        {"id": "RELX|sf_dataset:workday:R119275", "company": "RELX",
         "title": "t", "url": "https://x/1"},
        {"id": "LexisNexis® Risk Solutions|sf_dataset:workday:R119275",
         "company": "LexisNexis® Risk Solutions", "title": "t",
         "url": "https://x/2"},
    ]
    stats3 = mc.detect_id_collisions(relx_ranking, {})
    check("par vivo×vivo (mesmo grupo) não acende — nada ausente",
          stats3["flagged"] == 0, str(stats3))

    # ambos ausentes (PGIM×Pru medidos): nada PRESENTE para receber a flag
    stats4 = mc.detect_id_collisions(
        [dict(CONSULTPORT_2100111)], {
            ("sf_dataset:workday", "R-124041"): {"pgim": "PGIM",
                                                 "pru": "Pru"}})
    check("par morto×morto (nenhum no ranking) não acende",
          stats4["flagged"] == 0, str(stats4))

    # ID implausível para o provedor fica FORA da comparação
    stats5 = mc.detect_id_collisions(
        [{"id": "X|sf_dataset:recruitee:abc123", "company": "X",
          "title": "t", "url": "https://x/1"}],
        {("sf_dataset:recruitee", "abc123"): {"y": "Y"}})
    check("ID implausível não entra na comparação (contado à parte)",
          stats5["flagged"] == 0 and stats5["implausible"] == 1, str(stats5))

    # sem histórico => nada acende (caderno degradado, padrão F70)
    no_hist_ranking = [dict(CONSULTPORT_2100111)]
    stats6 = mc.detect_id_collisions(no_hist_ranking, {})
    check("sem histórico de colisão => nada acende (e flag não criada)",
          stats6["flagged"] == 0
          and "id_collision" not in no_hist_ranking[0], str(stats6))


# ---------------------------------------------------------------------------
# G5 — load_id_history: caderno F70 real (tmp), best-effort
# ---------------------------------------------------------------------------

def _make_seen_db(path: Path, job_ids: tuple[str, ...]) -> None:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE dataset_seen (run_id TEXT NOT NULL, job_id TEXT NOT "
        "NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, PRIMARY "
        "KEY (run_id, job_id))")
    for jid in job_ids:
        con.execute("INSERT INTO dataset_seen VALUES (?, ?, ?, ?)",
                    ("2026-10-21T09:00:02+00:00", jid,
                     "2026-10-21T09:13:10+00:00", "2026-10-21T09:13:10+00:00"))
    con.commit()
    con.close()


def test_load_id_history() -> None:
    section("G5 — load_id_history: caderno F70 -> mapa (best-effort)")
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "dataset_seen.db"
        _make_seen_db(db, SIMVIA_SEEN_JOB_IDS)
        hist = mc.load_id_history(db)
        key = ("sf_dataset:recruitee", "2100111")
        check("colisão do doc está no mapa com display original",
              hist.get(key, {}).get("simvia") == "Simvia", str(hist.get(key)))
        check("IDs reais da Simvia também mapeados",
              all(("sf_dataset:recruitee", jid.rsplit(":", 1)[1]) in hist
                  for jid in SIMVIA_SEEN_JOB_IDS[1:]))
        check("DB ausente => {} (best-effort, nunca derruba)",
              mc.load_id_history(Path(td) / "nao-existe.db") == {})
        check("path vazio => {}", mc.load_id_history("") == {})
        corrupt = Path(td) / "corrupt.db"
        corrupt.write_bytes(b"nao-e-sqlite")
        check("DB corrompido => {} (best-effort)",
              mc.load_id_history(corrupt) == {})


# ---------------------------------------------------------------------------
# G6 — rows + MANUAL-CHECK.md: linha do dono + carry-forward do sighting
# ---------------------------------------------------------------------------

def test_rows_and_md() -> None:
    section("G6 — build_manual_check_rows + write_manual_check_md")
    fixture_ranking = [
        henkel_job(89534, not_assessable="desc_curta",
                   liveness_status="unknown",
                   liveness_detail="saml wall (url:/samldefault.aspx)",
                   manual_check_required=True),
        henkel_job(89499, not_assessable="desc_curta"),
        henkel_job(89644, not_assessable="desc_curta"),
        henkel_job(89756, not_assessable="desc_curta",
                   liveness_status="unknown",
                   liveness_detail="saml wall (url:/samldefault.aspx)"),
        dict(AMAZON_KOBLENZ_13423224, not_assessable="desc_vazia"),
        dict(CONSULTPORT_2100111, id_collision="Simvia"),
        dict(LIDL_STUB_JOB, not_assessable="desc_curta"),
    ]
    rows = mc.build_manual_check_rows(fixture_ranking)
    check("7 linhas (4 henkel + amazon + consultport + lidl)",
          len(rows) == 7, str(len(rows)))
    by_id = {r["id"]: r for r in rows}
    check("motivos: saml×2, borderline×3, empty_desc, id_collision",
          [by_id[f"henkel|cornerstone:henkel:{n}"]["motivo"]
           for n in (89534, 89499, 89644, 89756)]
          == ["saml_wall", "borderline", "borderline", "saml_wall"]
          and by_id[AMAZON_KOBLENZ_13423224["id"]]["motivo"] == "empty_desc"
          and by_id[CONSULTPORT_2100111["id"]]["motivo"] == "id_collision",
          str({r["id"]: r["motivo"] for r in rows}))
    check("lidl: link direto = ALVO final (não o stub), marcado resolved",
          by_id[LIDL_STUB_JOB["id"]]["url"] == LIDL_ALVO_753653
          and by_id[LIDL_STUB_JOB["id"]]["resolved"] is True)
    check("ordenado por empresa (casefold, estável entre runs)",
          [r["company"] for r in rows]
          == sorted((r["company"] for r in rows), key=str.casefold))
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "MANUAL-CHECK.md"
        mc.write_manual_check_md(path, rows, "2026-10-19T09:00:00+00:00")
        text1 = path.read_text(encoding="utf-8")
        check("cabeçalho com contagem", "# Manual check — 7 item(ns)" in text1)
        check("doutrina no cabeçalho (fila PARALELA, Top-5 não filtrado)",
              "nenhuma vaga sai do ranking/Top-5" in text1)
        line_amazon = [l for l in text1.splitlines()
                       if "13423224" in l][0]
        check("linha do dono: empresa + cargo + link + motivo + visto",
              ("**Amazon Koblenz GmbH - C44** — Praktikum im Bereich "
               "Logistik" in line_amazon)
              and "[abrir](https://www.absolventa.de/stellenangebote/"
                  "13423224" in line_amazon
              and "motivo: empty_desc" in line_amazon
              and "visto: 2026-10-19" in line_amazon
              and "<!-- id:" in line_amazon, line_amazon[:160])
        # carry-forward: reescreve no run seguinte com data mais nova — o
        # sighting ORIGINAL (19/10) sobrevive para o item que continua
        rows2 = mc.build_manual_check_rows([
            henkel_job(89499, not_assessable="desc_curta",
                       liveness_checked_at="2026-10-22T09:00:00+00:00")])
        mc.write_manual_check_md(path, rows2, "2026-10-22T12:00:00+00:00")
        text2 = path.read_text(encoding="utf-8")
        line2 = [l for l in text2.splitlines() if "89499" in l][0]
        check("carry-forward: sighting original (19/10) sobrevive ao run",
              "visto: 2026-10-19" in line2, line2[:160])
        # fila vazia = arquivo honesto
        mc.write_manual_check_md(path, [], "2026-10-23T09:00:00+00:00")
        text3 = path.read_text(encoding="utf-8")
        check("fila vazia => arquivo com 0 item(ns)",
              "# Manual check — 0 item(ns)" in text3
              and "Fila vazia" in text3)


# ---------------------------------------------------------------------------
# G7 — generate_manual_check: integração (arquivo + persistência do flag)
# ---------------------------------------------------------------------------

def test_generate_manual_check() -> None:
    section("G7 — generate_manual_check: JSON + MANUAL-CHECK.md + caderno")
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        ranking = [
            henkel_job(89534), henkel_job(89499), henkel_job(89644),
            henkel_job(89756), dict(AMAZON_KOBLENZ_13423224),
            dict(CONSULTPORT_2100111), dict(LIDL_STUB_JOB),
            {"id": "Acme|workday:acme:42", "company": "Acme",
             "title": "Internship Procurement", "url": "https://acme/42",
             "description": "x" * 900},
        ]
        # caminho REAL do pipeline: annotators F87/F94 sobre a lista
        rd._annotate_assessability(ranking)
        rd._annotate_liveness_state(
            ranking,
            {henkel_job(89534)["id"]: {"status": "unknown",
                                       "detail": "saml wall (url)",
                                       "final_url": SAML_FINAL_URL},
             henkel_job(89756)["id"]: {"status": "unknown",
                                       "detail": "saml wall (url)",
                                       "final_url": SAML_FINAL_URL},
             LIDL_STUB_JOB["id"]: {"status": "alive", "detail": "",
                                   "final_url": LIDL_ALVO_753653}},
            {henkel_job(89534)["id"], henkel_job(89756)["id"]},
            "2026-10-22T09:00:00+00:00")
        (data_dir / "eligible_jobs.json").write_text(
            json.dumps(ranking, ensure_ascii=False), encoding="utf-8")
        _make_seen_db(data_dir / "dataset_seen.db", SIMVIA_SEEN_JOB_IDS)
        stats = mc.generate_manual_check(
            data_dir, generated_at="2026-10-22T09:30:00+00:00",
            seen_db_path=data_dir / "dataset_seen.db")
        check("7 linhas na fila (8ª vaga avaliável/viva fora)",
              stats["rows"] == 7, str(stats["rows"]))
        check("1 colisão flagada", stats["collisions"]["flagged"] == 1)
        persisted = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        by_id = {j["id"]: j for j in persisted}
        check("id_collision PERSISTIDO no registro (padrão F87/F94)",
              by_id[CONSULTPORT_2100111["id"]].get("id_collision") == "Simvia")
        check("liveness_detail persistido (o porquê do veredito)",
              by_id[henkel_job(89534)["id"]].get("liveness_detail")
              == "saml wall (url)")
        check("final SAML NUNCA persiste como alvo (unknown não é alive)",
              "liveness_final_url" not in by_id[henkel_job(89534)["id"]])
        check("alvo final persistido na vaga VIVA com redirect (Lidl)",
              by_id[LIDL_STUB_JOB["id"]].get("liveness_final_url")
              == LIDL_ALVO_753653)
        md = (data_dir / "MANUAL-CHECK.md").read_text(encoding="utf-8")
        check("MANUAL-CHECK.md gerado no data_dir",
              stats["path"].endswith("MANUAL-CHECK.md") and len(md) > 100)
        check("linha consultport com motivo id_collision no arquivo",
              "motivo: id_collision" in md
              and "consultport.recruitee.com" in md)


# ---------------------------------------------------------------------------
# G8 — annotator F94 estendido: liveness_detail + liveness_final_url
# ---------------------------------------------------------------------------

def test_annotator_fields() -> None:
    section("G8 — _annotate_liveness_state: detalhe + alvo final no registro")
    job_alive_redirect = {"id": "a|workday:a:1", "title": "t", "company": "c",
                          "url": "https://x/stub"}
    job_alive_plain = {"id": "a|workday:a:2", "title": "t", "company": "c",
                       "url": "https://x/2"}
    job_unknown = {"id": "henkel|cornerstone:henkel:9", "title": "t",
                   "company": "c", "url": "https://x/9"}
    job_dead = {"id": "a|workday:a:4", "title": "t", "company": "c",
                "url": "https://x/4"}
    ranking = [job_alive_redirect, job_alive_plain, job_unknown, job_dead]
    stats_state = rd._annotate_liveness_state(
        ranking,
        {job_alive_redirect["id"]: {"status": "alive", "detail": "",
                                    "final_url": "https://x/jobs/1"},
         job_alive_plain["id"]: {"status": "alive", "detail": ""},
         job_unknown["id"]: {"status": "unknown",
                             "detail": "saml wall (url)",
                             "final_url": SAML_FINAL_URL},
         job_dead["id"]: {"status": "dead", "detail": "http 404"}},
        set(), "2026-10-22T09:00:00+00:00")
    check("contagens F94 intocadas", stats_state["annotated"] == 4
          and stats_state["alive"] == 2 and stats_state["dead"] == 1
          and stats_state["unknown"] == 1, str(stats_state))
    check("alive com redirect: alvo final + detalhe no registro",
          job_alive_redirect.get("liveness_final_url") == "https://x/jobs/1"
          and job_alive_redirect.get("liveness_detail") == "")
    check("alive sem redirect: SEM campo de alvo (e stale apagado)",
          "liveness_final_url" not in job_alive_plain)
    check("unknown: detalhe persistido, SEM alvo (IdP não é link direto)",
          job_unknown.get("liveness_detail") == "saml wall (url)"
          and "liveness_final_url" not in job_unknown)
    check("dead: detalhe persistido (consultável), sem alvo novo",
          job_dead.get("liveness_detail") == "http 404"
          and "liveness_final_url" not in job_dead)
    # cura idempotente: viva que volta a responder sem redirect perde o alvo
    rd._annotate_liveness_state(
        [job_alive_redirect],
        {job_alive_redirect["id"]: {"status": "alive", "detail": ""}},
        set(), "2026-10-22T10:00:00+00:00")
    check("cura: alvo stale apaga quando o run não vê redirect",
          "liveness_final_url" not in job_alive_redirect)


# ---------------------------------------------------------------------------
# G9 — check_liveness_v2: final_url no veredito (só quando difere)
# ---------------------------------------------------------------------------

def test_verdict_final_url() -> None:
    section("G9 — veredito carrega final_url do redirect (contrato F96)")
    stub_job = {"id": "lidlstiftup2|sf_dataset:successfactors:753653",
                "title": "t", "company": "c", "url": LIDL_STUB_753653}
    plain_job = {"id": "a|workday:a:2", "title": "t", "company": "c",
                 "url": "https://x.example.com/jobs/2"}
    dead_job = {"id": "GFO Kliniken Niederrhein|sf_dataset:softgarden:1",
                "title": "t", "company": "c", "url": "https://gfo.example/1"}
    saml_job = henkel_job(89534)
    _dead, _b, stats = ul.check_liveness_v2(
        [stub_job, plain_job, dead_job, saml_job],
        opener=_opener(
            {LIDL_STUB_753653: (LIDL_ALVO_753653, _job_page_body(2_000)),
             plain_job["url"]: (plain_job["url"], _job_page_body(2_000)),
             saml_job["url"]: (SAML_FINAL_URL,
                               "<title>SAML Authentication Request</title>")},
            {dead_job["url"]: 404}),
        delay=0)
    v = stats["verdicts"]
    check("stub vivo: verdict com final_url do ALVO",
          v[stub_job["id"]] == {"final_url": LIDL_ALVO_753653,
                                "status": "alive", "detail": ""},
          str(v.get(stub_job["id"])))
    check("sem redirect: verdict SEM final_url (contrato F94 intacto)",
          v[plain_job["id"]] == {"status": "alive", "detail": ""},
          str(v.get(plain_job["id"])))
    check("HTTP 404: verdict SEM final_url (contrato F94 intacto)",
          v[dead_job["id"]] == {"status": "dead", "detail": "http 404"},
          str(v.get(dead_job["id"])))
    check("SAML: unknown + final_url presente (consumidor decide)",
          v[saml_job["id"]]["status"] == "unknown"
          and v[saml_job["id"]].get("final_url") == SAML_FINAL_URL
          and "saml wall" in v[saml_job["id"]]["detail"],
          str(v.get(saml_job["id"])))


# ---------------------------------------------------------------------------
# G10 — fila PARALELA: Top-5 NÃO filtrado (doutrina F87 mantida)
# ---------------------------------------------------------------------------

def test_queue_parallel() -> None:
    section("G10 — doutrina F87: nenhuma vaga sai do ranking/Top-5")
    ranking = [
        henkel_job(89534, not_assessable="desc_curta"),
        dict(AMAZON_KOBLENZ_13423224, not_assessable="desc_vazia"),
        dict(CONSULTPORT_2100111, id_collision="Simvia"),
        {"id": "Acme|workday:acme:42", "company": "Acme",
         "title": "Internship Procurement", "url": "https://acme/42",
         "description": "x" * 900},
        {"id": "B|workday:b:43", "company": "B", "title": "Internship",
         "url": "https://b/43", "description": "y" * 900},
    ]
    snapshot = json.dumps(ranking, sort_keys=True, ensure_ascii=False)
    rows = mc.build_manual_check_rows(ranking)
    after = json.dumps(ranking, sort_keys=True, ensure_ascii=False)
    check("build_manual_check_rows não muta o ranking",
          snapshot == after and len(rows) == 3)
    top5_text = ranking_digest.format_top5(ranking)  # contrato F6: str
    for jid, needle in (
        (henkel_job(89534)["id"], "Praktikum Supply Chain 89534"),
        (AMAZON_KOBLENZ_13423224["id"], "Amazon Koblenz"),
        (CONSULTPORT_2100111["id"], "Finance & Operations Intern"),
    ):
        check(f"Top-5 mantém a flagada ({jid.split('|')[0][:20]}…)",
              needle in top5_text, top5_text[:120])


# ---------------------------------------------------------------------------
# G11 — wiring: o refresh diário chama o gerador (junto ao digest)
# ---------------------------------------------------------------------------

def test_refresh_wiring() -> None:
    section("G11 — refresh_daily.main chama generate_manual_check")
    source = inspect.getsource(rd.main)
    check("chamada generate_manual_check no fluxo de produção",
          "generate_manual_check" in source)
    check("hook dentro do gate do digest (publication_allowed)",
          source.find("publication_allowed") < source.find(
              "generate_manual_check"))
    check("import do módulo no refresh", hasattr(rd, "manual_check"))


def main() -> int:
    test_motivo_of()
    test_resolve_direct_link()
    test_provider_id_plausible()
    test_detect_id_collisions()
    test_load_id_history()
    test_rows_and_md()
    test_generate_manual_check()
    test_annotator_fields()
    test_verdict_final_url()
    test_queue_parallel()
    test_refresh_wiring()
    print(f"\n==== test_f96: {CHECKS} checks, "
          f"{len(FAILURES)} falha(s) ====")
    if FAILURES:
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
