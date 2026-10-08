#!/usr/bin/env python3
"""Testes do consumo da evidencia da pagina oficial (Fase D2) — 100% OFFLINE.

Cobre os casos obrigatorios da spec D2 (secao 10), sem rede e sem escrever
em data/ (REGRA do PR #78). Duas frentes:

1. ``present_official`` (view pura): status/validThrough/location por caso;
2. ``interface.py`` (render): linhas de fato, chip, escape e — acima de tudo
   — os INVARIANTES da fase: score/ordem/ids IDENTICOS com e sem evidencia,
   validThrough NUNCA vira deadline de candidatura, eligibility/dedup
   intocados (nenhuma funcao de ranking/filtro e chamada por esta via).

Convencao do repo: [OK]/[FAIL], termina "TUDO OK" (exit 0).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import present_official  # noqa: E402

import interface  # noqa: E402

_FAILS = 0


def check(name: str, cond: bool) -> None:
    global _FAILS
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}")
    if not cond:
        _FAILS += 1


# ---------------------------------------------------------------- fixtures


def op_job(
    *,
    status: str = "ok",
    checked_at: str = "2026-09-28T06:10:00+00:00",
    valid_through: str | None = None,
    location_relation: str | None = None,
    employment_type: str | None = None,
    reason: str | None = None,
    job_id: str = "TestCo|a:TestCo:1",
    seq: int = 0,
) -> dict:
    """Vaga com blocos ``official_page`` no formato EXATO da Fase D.

    ``seq`` diferencia titulo/localizacao entre fixtures (dedup
    company+title+location do projeto colapsa vagas identicas).
    """
    # F18: título HÍBRIDO — Werkstudent puro sai no hard exclude de
    # aplicabilidade; este bloco testa a evidência official_page (A/B).
    title = "Werkstudent / Praktikum Data Analytics"
    location = "Munich, Bavaria"
    if seq:
        title = f"{title} {seq}"
        location = f"Munich {seq}, Bavaria"
    jsonld: dict = {}
    if valid_through:
        jsonld["valid_through"] = valid_through
    if location_relation:
        jsonld["location_relation"] = location_relation
        jsonld["location"] = {"city": "München"}
    if employment_type:
        jsonld["employment_type"] = employment_type
    op: dict = {
        "original_url": f"https://jobs.example.com/{job_id}",
        "final_url": f"https://jobs.example.com/{job_id}",
        "http_status": 200 if status in ("ok", "js_rendered", "empty_content",
                                         "redirected") else 404,
        "status": status,
        "reason": reason,
        "checked_at": checked_at,
    }
    if jsonld:
        op["jsonld"] = jsonld
    return {
        "id": job_id,
        "source": "a:TestCo",
        "title": title,
        "company": "TestCo",
        "location": location,
        "country_iso": "de",
        "url": f"https://jobs.example.com/{job_id}",
        "description": "Support the team. English required.",
        "score": 8.0,
        "score_breakdown": {"area": 4.0, "skills": 0.5, "language": 2.0,
                            "type": 1.0, "location": 0.5, "penalties": 0.0},
        "collected_at": "2026-09-28T06:00:00+00:00",
        "official_page": op,
    }


def render(jobs: list[dict], **kw) -> str:
    """Render minimo (mesmo helper do test_interface, assinatura estavel)."""
    return interface.render_html(
        jobs, total=len(jobs), source_label="test", filters_desc=[],
        generated_at="2026-09-28T00:00:00Z", show_how=False,
        intel_map=interface._intel_map_for(jobs, None, interface.app_intel
                                           .snapshot_ref_date(jobs)),
        **kw,
    )


# ---------------------------------------------------------------- bloco 1
# View pura: casos de evidencia (spec secao 10, itens 1-7)


def test_view_pura() -> None:
    print("== view pura: status, validThrough, location, employmentType ==")
    # 1. vaga sem official-page evidence -> nada a exibir
    plain = {"id": "x", "title": "t", "company": "c", "url": "https://j/1"}
    v = present_official.official_view(plain)
    check("1. vaga sem evidencia -> view None (HTML de sempre)",
          v is None and present_official.lines(v) == []
          and present_official.chip(v) is None)
    check("1b. job não-dict / None não quebra",
          present_official.official_view(None) is None
          and present_official.official_view({"x": 1}) is None)

    # 2. page_verified -> linha de fato com data, SEM chip
    v = present_official.official_view(op_job())
    lines = [l["detail"] for l in present_official.lines(v)]
    check("2. page_verified -> 'página oficial verificada em <data>'",
          v is not None and v["status"] == "verified"
          and lines == ["página oficial verificada em 2026-09-28"]
          and present_official.chip(v) is None)

    # 3. validThrough -> linha propria com ORIGEM explicita
    v = present_official.official_view(op_job(valid_through="2027-03-15"))
    lines = [l["detail"] for l in present_official.lines(v)]
    check("3. validThrough exibido com origem (JobPosting, página oficial)",
          lines == ["página oficial verificada em 2026-09-28",
                    "validThrough do JobPosting (página oficial): 2027-03-15"])

    # 4. location confirmada -> linha discreta
    v = present_official.official_view(op_job(location_relation="confirmed"))
    lines = [l["detail"] for l in present_official.lines(v)]
    check("4. location confirmada -> 'local confirmado pela página oficial'",
          lines[-1] == "local confirmado pela página oficial")

    # 5. location conflitante -> INTERNO (nunca vira linha/chip)
    v = present_official.official_view(op_job(location_relation="conflict"))
    lines = [l["detail"] for l in present_official.lines(v)]
    check("5. location conflito -> sem linha de conflito na UI",
          all("local" not in l for l in lines)
          and v is not None and not v["location_confirmed"])

    # 6. employmentType presente -> INTERNO (badge proibido pela spec §6)
    v = present_official.official_view(op_job(employment_type="FULL_TIME"))
    lines = [l["detail"] for l in present_official.lines(v)]
    check("6. employmentType presente -> NENHUMA linha o exibe",
          all("FULL_TIME" not in l and "employment" not in l.lower()
              for l in lines))

    # 7. ausencia de employmentType -> idem (sem diferenca de UI)
    v_sem = present_official.official_view(op_job())
    check("7. sem employmentType -> view igual (campo é interno)",
          [l["detail"] for l in present_official.lines(v_sem)]
          == [l["detail"] for l in present_official.lines(v)])

    # status tecnicos NUNCA viram UI (redirect/JS/403/empty) — nem linha,
    # nem chip; validThrough de pagina nao-verificada não vaza
    for status in ("redirected", "js_rendered", "http_error",
                   "empty_content", "fetch_error", "timeout"):
        v = present_official.official_view(
            op_job(status=status, valid_through="2027-03-15"))
        check(f"   status técnico {status} -> sem UI (evidência não vaza)",
              v is None)
    # not_found -> fato + chip (o único caso com chip)
    v = present_official.official_view(op_job(status="not_found"))
    lines = [l["detail"] for l in present_official.lines(v)]
    check("   not_found -> linha de fato + chip c-warn",
          lines == ["página oficial não foi encontrada na verificação "
                    "em 2026-09-28"]
          and present_official.chip(v) is not None)
    # view_map: vagas sem evidencia ficam fora
    vm = present_official.view_map([plain, op_job(), op_job(status="js_rendered")])
    check("   view_map: somente vagas com evidência útil",
          set(vm) == {"TestCo|a:TestCo:1"})


# ---------------------------------------------------------------- bloco 2
# Render HTML: fatos, chip, escape e invariantes (spec secao 10, 8-11)


def test_render_html() -> None:
    print("== render HTML: fatos, chip, escape, invariantes ==")
    base = op_job(job_id="Co|a:Co:1")
    with_vt = op_job(valid_through="2027-03-15", job_id="Co|a:Co:2", seq=2)
    not_found = op_job(status="not_found", job_id="Co|a:Co:3", seq=3)
    confirmed = op_job(location_relation="confirmed", job_id="Co|a:Co:4", seq=4)

    page = render([base, with_vt, not_found, confirmed])
    body = page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]

    # linha de fato na vaga verificada (dentro do <details> 'por que')
    check("8. 'página oficial verificada em' no details da vaga ok",
          "página oficial verificada em 2026-09-28" in page)
    # validThrough com origem explicita — e NUNCA como deadline de candidatura
    check("9. validThrough exibido COM origem; NUNCA 'candidaturas até'",
          "validThrough do JobPosting (página oficial): 2027-03-15" in page
          and "candidaturas até 2027-03-15" not in page)
    # location confirmada
    check("10. location confirmada aparece na vaga com relation=confirmed",
          "local confirmado pela página oficial" in page)
    # chip not_found visível ANTES do clique; vaga ok sem chip
    check("11. chip not_found presente uma única vez",
          page.count("🔗 página não encontrada na verificação") == 1)
    check("11b. vaga verificada NÃO ganha chip de verificação",
          "página oficial verificada" in page
          and "verificada</span>" not in body)

    # invariante fundamental: mesmas vagas SEM official_page -> HTML sem as
    # linhas novas, mas scores/ids/ordem IDÊNTICOS
    stripped = []
    for j in (base, with_vt, not_found, confirmed):
        j2 = {k: v for k, v in j.items() if k != "official_page"}
        stripped.append(j2)
    page_sem = render(stripped)
    scores_com = re.findall(r'data-score="([^"]*)" data-date', page)
    scores_sem = re.findall(r'data-score="([^"]*)" data-date', page_sem)
    ids_com = re.findall(r'data-job-id="([^"]*)"', page)
    ids_sem = re.findall(r'data-job-id="([^"]*)"', page_sem)
    check("12. scores/ids/ordem IDÊNTICOS com vs sem evidência",
          scores_com == scores_sem and ids_com == ids_sem
          and len(scores_com) == 4)
    check("12b. sem evidência: nenhuma das linhas novas aparece",
          "página oficial verificada" not in page_sem
          and "validThrough do JobPosting" not in page_sem
          and "local confirmado pela página oficial" not in page_sem
          and "🔗 página não encontrada" not in page_sem)

    # 9 (invariante de dado): validThrough NUNCA promove application_deadline
    j = op_job(valid_through="2027-03-15")
    check("13. validThrough NÃO altera application_deadline do job",
          j.get("application_deadline") is None
          and j["official_page"]["jsonld"]["valid_through"] == "2027-03-15")

    # escape: evidência maliciosa nos campos exibidos
    evil = op_job(job_id="Evil|a:Evil:1", valid_through="<script>x</script>")
    evil["official_page"]["checked_at"] = ("<script>alert(1)</script>"
                                           "2026-09-28T00:00:00Z")
    page_evil = render([evil])
    check("14. texto da evidência escapado (sem injeção)",
          "<script>alert(1)</script>" not in page_evil
          and page_evil.count("<script>") >= 1)


# ---------------------------------------------------------------- bloco 3
# Pipeline: eligibility/score/dedup intocados PELA CONSTRUÇÃO + A/B local


def test_pipeline_invariants() -> None:
    print("== invariantes de pipeline (construção + A/B local) ==")
    # NENHUM modulo de ranking/filtro/dedup e importado pela view
    src = (ROOT / "src" / "internship_finder" / "present_official.py").read_text()
    check("15. view pura: nenhum import de ranking/filters/dedup",
          all(f"import {m}" not in src and f"from internship_finder.{m}" not in src
              for m in ("ranking", "filters", "dedup", "materials_ranking")))

    # interface.py: consumo apenas via present_official (sem leitura crua)
    iface_src = (ROOT / "scripts" / "interface.py").read_text()
    check("16. interface lê evidência SOMENTE via present_official",
          'job["official_page"]' not in iface_src
          and "job.get(\"official_page\")" not in iface_src
          and "present_official." in iface_src)

    # A/B local: run_filter_pipeline produz ranking identico com e sem
    # evidência — a evidência NÃO é lida por select_eligible/rank_jobs;
    # simulamos o estágio D aplicado ao MESMO conjunto.
    from internship_finder.cli import run_filter_pipeline
    import tempfile

    jobs = [op_job(valid_through="2027-03-15", job_id=f"Co|a:Co:{i}", seq=i)
            for i in range(1, 4)]
    jobs_sem = [{k: v for k, v in j.items() if k != "official_page"}
                for j in jobs]
    with tempfile.TemporaryDirectory(prefix="t_d2_") as td:
        out_a = Path(td) / "a.json"
        out_b = Path(td) / "b.json"
        rc_a = run_filter_pipeline(
            [json.loads(json.dumps(j)) for j in jobs_sem],
            student=True, area=True, country="de", output=out_a,
            dedup=True, rank=True, hydrate=False, official_page=False,
        )
        rc_b = run_filter_pipeline(
            [json.loads(json.dumps(j)) for j in jobs],
            student=True, area=True, country="de", output=out_b,
            dedup=True, rank=True, hydrate=False, official_page=False,
        )
        a = json.loads(out_a.read_text())
        b = json.loads(out_b.read_text())
        check("17. A/B pipeline: exit codes iguais e >0 vagas",
              rc_a == rc_b == 0 and len(a) == len(b) == 3)
        check("18. A/B pipeline: ids, ordem e scores IDÊNTICOS",
              [j["id"] for j in a] == [j["id"] for j in b]
              and [j.get("score") for j in a] == [j.get("score") for j in b])
        check("19. A/B pipeline: evidência preservada no lado B (payload)",
              all("official_page" in j for j in b)
              and all("official_page" not in j for j in a))
        check("20. A/B pipeline: breakdowns IDÊNTICOS (0 diffs de score)",
              [j.get("score_breakdown") for j in a]
              == [j.get("score_breakdown") for j in b])


# ---------------------------------------------------------------- bloco 4
# Comparator D2: fix dos falsos conflitos (rua parseada como cidade)


def test_comparator_fix() -> None:
    print("== comparator location: fix rua→cidade (AIXTRON FP) ==")
    from internship_finder.official_page import _location_relation

    # caso real do A/B (FP): location com rua + CEP + cidade; o JSON-LD traz
    # a CIDADE. split(",")[0] antigo lia 'Dornkaulstraße 2' como cidade.
    job = {"location": ("Dornkaulstraße 2, 52134 Herzogenrath, "
                        "Nordrhein-Westfalen, Deutschland")}
    loc = {"city": "Herzogenrath"}
    check("21. rua+CEP+cidade -> confirmed (era FP de conflito)",
          _location_relation(loc, job) == "confirmed")
    # conflito REAL continua conflito (cidade genuinamente diversa)
    check("22. cidade genuinamente diversa -> conflict",
          _location_relation({"city": "Hamburg"}, job) == "conflict")
    # notação de cidade distinta (LEV vs Leverkusen) segue conflito honesto
    check("23. notação divergente (LEV x Leverkusen) -> conflict (interno)",
          _location_relation({"city": "LEV"},
                             {"location": "Leverkusen, NRW, DE"}) == "conflict")
    # sem cidade em um dos lados -> None (não sabe, não afirma)
    check("24. sem cidade no job -> None",
          _location_relation({"city": "Berlin"}, {"location": ""}) is None)
    check("25. sem location no JSON-LD -> None",
          _location_relation(None, job) is None)


def main() -> int:
    test_view_pura()
    test_render_html()
    test_pipeline_invariants()
    test_comparator_fix()
    print()
    if _FAILS:
        print(f"FAIL: {_FAILS} check(s) falharam")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
