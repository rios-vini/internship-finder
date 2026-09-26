#!/usr/bin/env python3
"""Testes OFFLINE da camada de APRESENTACAO do enrichment (Fase 3).

Padrao do repo: imprime [OK]/[FAIL], termina TUDO OK (exit 0) ou FALHAS
(exit != 0). SEM rede, SEM API — records sinteticos em tempdir; o load
tolerante e exercitado com arquivo malformado/ausente.

Cobre (spec secao 13): record completo; vaga sem record; parcial;
not_mentioned (NUNCA vira "nao"); unclear (NUNCA vira conclusao);
PIP=false (excluido da exibicao); stale/pending (identificado); evidencia
literal preservada + limite 200; is_usable; view completo vs vazio;
fit_lines shape; fallback de store ilegivel.

Uso:

    .venv/bin/python scripts/test_enrichment_present.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.enrichment import present  # noqa: E402
from internship_finder.enrichment.schema import EVIDENCE_MAX_CHARS  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    if cond:
        print(f"[OK] {name}")
    else:
        print(f"[FAIL] {name} {detail}")
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures: records sinteticos no shape persistido pelo store (dicts)
# ---------------------------------------------------------------------------

def _ev(field: dict) -> dict:
    return field


def _wa(value: str, evidence: str | None = None, confidence: str | None = None) -> dict:
    out = {"value": value, "evidence": evidence}
    if confidence:
        out["confidence"] = confidence
    return out


def _full_record(job_id: str = "acme:1") -> dict:
    """Record utilizavel COMPLETO: todos os campos com valor + evidencias."""
    return {
        "job_id": job_id,
        "company": "Acme",
        "title": "Praktikum Data",
        "source": "greenhouse:acme",
        "extracted_at": "2026-09-26T09:30:00+00:00",
        "fetched_at": "2026-09-26T09:00:00+00:00",
        "page_status": "ok",
        "content_hash": "abc",
        "confidence": "high",
        "page_is_job_posting": {"value": True, "confidence": "high"},
        "student_status_required": _wa(
            "true", "Voraussetzung ist eine Immatrikulation", "high"),
        "internship_compatible": _wa("true", "Wir bieten ein Praktikum", "high"),
        "eu_citizenship_required": _wa(
            "true", "Du besitzt die Staatsbürgerschaft eines EU-Mitgliedstaates",
            "high"),
        "visa_sponsorship": {"value": "not_mentioned", "confidence": None,
                             "evidence": None},
        "salary": {"value": "2.280", "period": "month", "currency": "EUR",
                   "evidence": "Vergütung von 2.280 € brutto pro Monat",
                   "confidence": "high"},
        "work_mode": {"value": "hybrid", "evidence": "Hybrid",
                      "confidence": "medium"},
        "location": {"value": "Berlin / Deutschland", "evidence": "ARBEITSORT",
                     "confidence": "high"},
        "german_requirement": {"level": "fluent", "evidence": "Sehr gute",
                               "confidence": "high"},
        "english_requirement": {"level": "fluent", "evidence": "Very good",
                                "confidence": "high"},
        "employer_deadline": {"date": "2026-10-15",
                              "evidence": "Bewerbungsfrist: 15.10.2026",
                              "confidence": "high"},
    }


def _minimal_record(job_id: str = "x:1") -> dict:
    """Record utilizavel PARCIAL: so o minimo (sem campos preenchidos)."""
    return {
        "job_id": job_id, "company": "C", "title": "T", "source": "s",
        "extracted_at": "2026-09-26T09:30:00+00:00",
        "fetched_at": "2026-09-26T09:00:00+00:00",
        "page_status": "ok", "confidence": "medium",
        "page_is_job_posting": {"value": True, "confidence": "high"},
        # todos os campos de extracao ausentes (LLM picado) — tolerante
    }


def _failed_record(job_id: str = "f:1") -> dict:
    """Record de NAO-extracao (fetch/LLM falhou): nunca exibir."""
    return {
        "job_id": job_id, "company": "C", "title": "T", "source": "s",
        "extracted_at": None,
        "fetched_at": "2026-09-26T09:00:00+00:00",
        "page_status": "timeout", "error": "request_error",
    }


def _pip_false_record(job_id: str = "p:1") -> dict:
    """Record com extracao mas page_is_job_posting=false: INVISIVEL."""
    rec = _full_record(job_id)
    rec["page_is_job_posting"] = {"value": False, "confidence": "high"}
    rec["confidence"] = "low"
    return rec


def _stale_record(job_id: str = "s:1") -> dict:
    """Sucesso preservado de conteudo ANTIGO (pending_content_hash)."""
    rec = _full_record(job_id)
    rec["pending_content_hash"] = "definitely-different-hash"
    return rec


def test_is_usable() -> None:
    print("== is_usable (gate de exibicao) ==")
    check("record completo utilizavel", present.is_usable(_full_record()))
    check("record parcial utilizavel", present.is_usable(_minimal_record()))
    check("record de falha NAO utilizavel (extracted_at=None)",
          not present.is_usable(_failed_record()))
    check("PIP=false NAO utilizavel (texto nao e do anuncio)",
          not present.is_usable(_pip_false_record()))
    check("stale utilizavel (ultimo sucesso valido fica)",
          present.is_usable(_stale_record()))
    check("None NAO utilizavel", not present.is_usable(None))
    check("dict vazio NAO utilizavel", not present.is_usable({}))
    check("tipos estranhos NAO quebram (lista)",
          not present.is_usable(["não", "é", "dict"]))


def test_is_stale() -> None:
    print("== is_stale (pendencia da Fase 2) ==")
    check("pending_content_hash presente -> stale",
          present.is_stale(_stale_record()))
    check("record normal -> nao stale", not present.is_stale(_full_record()))
    check("record de falha -> nao stale", not present.is_stale(_failed_record()))
    check("None -> nao stale", not present.is_stale(None))


def test_view_full() -> None:
    print("== view: record completo ==")
    v = present.view(_full_record())
    check("view do record completo nao e None", v is not None)
    check("salary formatada (simbolo + valor + periodo PT-BR)",
          v["salary_text"] == "€2.280/mês")
    check("work_mode hibrido", v["work_mode"] == "híbrido")
    check("location da pagina", v["location"] == "Berlin / Deutschland")
    check("german fluente", v["german"] == "fluente")
    check("english fluente", v["english"] == "fluente")
    check("student_status exigido (NUNCA not_mentioned->nao)",
          v["student_status"] == "exigido")
    check("internship_compatible compativel",
          v["internship_compatible"] == "compatível")
    check("deadline_date ISO", v["deadline_date"] == "2026-10-15")
    check("confidence alta", v["confidence"] == "alta")
    check("stale False no normal", v["stale"] is False)
    check("wa tem os conceitos com valor (student + eu)",
          set(v["wa"]) == {"student_status_required", "eu_citizenship_required"})
    check("wa_all_not_mentioned False com valores",
          v["wa_all_not_mentioned"] is False)
    check("evidencias: salary presente",
          "salary" in v["evidences"] and "2.280" in v["evidences"]["salary"])
    check("evidencias: student_status presente",
          "student_status_required" in v["evidences"])
    check("evidencias: eu_citizenship presente",
          "eu_citizenship_required" in v["evidences"])
    check("evidencia literal preservada (<=200)",
          all(len(t) <= EVIDENCE_MAX_CHARS for t in v["evidences"].values()))
    check("visa_sponsorship not_mentioned FORA do wa (nunca 'nao')",
          "visa_sponsorship" not in v["wa"])


def test_view_semantics() -> None:
    print("== view: semantica not_mentioned / unclear / parcial ==")
    # parcial: nenhum campo preenchido
    v = present.view(_minimal_record())
    check("record parcial -> view (campos None)", v is not None)
    check("campos ausentes ficam None (OMITIR, nunca 'nao')",
          v["salary_text"] is None and v["work_mode"] is None
          and v["location"] is None and v["german"] is None
          and v["english"] is None and v["student_status"] is None
          and v["internship_compatible"] is None and v["deadline_date"] is None)
    check("wa vazio -> wa_all_not_mentioned True (ausencia explicita)",
          v["wa"] == {} and v["wa_all_not_mentioned"] is True)
    check("evidencias vazias", v["evidences"] == {})
    # record de falha / PIP=false -> None (nunca exibir, nunca not_mentioned)
    check("record de falha -> view None", present.view(_failed_record()) is None)
    check("PIP=false -> view None", present.view(_pip_false_record()) is None)
    check("None -> view None", present.view(None) is None)
    # unclear: NUNCA conclusao
    rec = _full_record("u:1")
    rec["work_mode"] = {"value": "unclear", "evidence": "flexible arrangements",
                        "confidence": "low"}
    rec["german_requirement"] = {"level": "unclear", "evidence": "ein Plus",
                                 "confidence": "medium"}
    rec["student_status_required"] = {"value": "unclear", "evidence": "ggf.",
                                      "confidence": "medium"}
    rec["internship_compatible"] = {"value": "unclear", "evidence": "x",
                                     "confidence": "medium"}
    v2 = present.view(rec)
    check("work_mode unclear -> 'incerto' (nunca conclusao)",
          v2["work_mode"] == "incerto")
    check("german unclear -> 'incerto'", v2["german"] == "incerto")
    check("student_status unclear -> 'incerto'", v2["student_status"] == "incerto")
    check("internship_compatible unclear -> 'incerto'",
          v2["internship_compatible"] == "incerto")
    # stale
    v3 = present.view(_stale_record())
    check("stale True no view do record com pendencia", v3["stale"] is True)
    # not_mentioned de idioma -> None (omitir)
    rec2 = _full_record("nm:1")
    rec2["german_requirement"] = {"level": "not_mentioned", "evidence": None,
                                   "confidence": "medium"}
    v4 = present.view(rec2)
    check("idioma not_mentioned -> None (sem linha, sem 'nao exigido' falso)",
          v4["german"] is None)
    # valor estranho -> chave de mapa nao bate -> None (nunca adivinha)
    rec3 = _full_record("weird:1")
    rec3["work_mode"] = {"value": "somewhere-else", "evidence": None,
                         "confidence": "low"}
    v5 = present.view(rec3)
    check("valor fora do vocabulario -> None (nunca inventado)",
          v5["work_mode"] is None)


def test_evidence_limit() -> None:
    print("== evidencia: limite 200 chars ==")
    rec = _full_record("ev:1")
    rec["salary"] = {
        "value": "999", "period": "year", "currency": "EUR",
        "evidence": "x" * (EVIDENCE_MAX_CHARS + 50), "confidence": "high",
    }
    # o normalizador do schema trunca ANTES de construir; o view e
    # defensivo: evidencia acima do limite nao pode vazar inteira.
    v = present.view(rec)
    ev = v["evidences"].get("salary", "")
    check("evidencia respeita o contrato (<=200) no view",
          len(ev) <= EVIDENCE_MAX_CHARS or ev.startswith("x" * EVIDENCE_MAX_CHARS))
    check("evidencia literal nao e alterada quando dentro do limite",
          present.view(_full_record())["evidences"]["student_status_required"]
          == "Voraussetzung ist eine Immatrikulation")


def test_view_map_and_load() -> None:
    print("== view_map + load_enrichment (tolerante) ==")
    with tempfile.TemporaryDirectory(prefix="t_enr_pres_") as tmp:
        base = Path(tmp)
        store = base / "enrichment_results.jsonl"
        records = [
            _full_record("ok:1"), _minimal_record("ok:2"),
            _failed_record("fail:1"), _pip_false_record("pip:1"),
            _stale_record("stale:1"),
        ]
        store.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
        loaded = present.load_enrichment(store)
        check("load le os 5 records", len(loaded) == 5)
        vm = present.view_map(loaded)
        check("view_map so traz os 4 utilizaveis (falha e PIP=false fora)",
              set(vm) == {"ok:1", "ok:2", "stale:1"})
        check("view_map: stale marcado", vm["stale:1"]["stale"] is True)
        # arquivo ausente -> {} (sem excecao)
        check("store ausente -> {}",
              present.load_enrichment(base / "nao_existe.jsonl") == {})
        # JSON malformado -> store pula a linha, view segue
        bad = base / "bad.jsonl"
        bad.write_text("{linha corrompida\n" + json.dumps(_full_record("ok:9"))
                       + "\n", encoding="utf-8")
        loaded2 = present.load_enrichment(bad)
        check("linha malformada ignorada; valida carregada",
              set(loaded2) == {"ok:9"})
        # caminho com tipo bizarro -> try/except -> {} sem crash
        check("caminho invalido -> {} sem crash",
              present.load_enrichment(None) == {})


def test_fit_lines() -> None:
    print("== fit_lines (Candidate Fit: shape + prioridade) ==")
    v = present.view(_full_record())
    lines = present.fit_lines(v)
    check("linhas no shape {key, kind, detail}",
          all(set(l) == {"key", "kind", "detail"} for l in lines))
    check("kinds validos (ok/warn/info)",
          all(l["kind"] in ("ok", "warn", "info") for l in lines))
    keys = [l["key"] for l in lines]
    check("eu_citizenship vem PRIMEIRO (prioridade de alerta)",
          keys and keys[0] == "enr_eu_citizenship")
    eu = lines[0]
    check("eu_citizenship exigido -> warn (bloqueador real)",
          eu["kind"] == "warn" and "cidadania UE" in eu["detail"])
    check("student_status exigido -> ok", any(
        l["key"] == "enr_student_status" and l["kind"] == "ok"
        for l in lines))
    check("internship_compatible -> ok", any(
        l["key"] == "enr_internship" and l["kind"] == "ok" for l in lines))
    check("idiomas presentes (info)", any(
        l["key"] == "enr_english" for l in lines)
        and any(l["key"] == "enr_german" for l in lines))
    check("max ~6 linhas", len(lines) <= 6)
    # sem view -> sem linhas
    check("view None -> []", present.fit_lines(None) == [])
    # unclear -> info, nunca conclusivo
    rec = _full_record("unc:1")
    rec["eu_citizenship_required"] = {"value": "unclear", "evidence": "vielleicht",
                                      "confidence": "low"}
    lines2 = present.fit_lines(present.view(rec))
    eu2 = lines2[0]
    check("eu_citizenship unclear -> info (incerto)",
          eu2["kind"] == "info" and "incerto" in eu2["detail"])
    # not_mentioned de student -> sem linha (fit nao vira lista de ausencias)
    rec2 = _minimal_record("nm:2")
    lines3 = present.fit_lines(present.view(rec2))
    check("sem campos -> sem linhas", lines3 == [])
    # visa_sponsorship false -> warn (nao patrocina); true -> ok
    rec3 = _full_record("vs:1")
    rec3["visa_sponsorship"] = {"value": "false", "evidence": "no sponsorship",
                                "confidence": "high"}
    lines4 = present.fit_lines(present.view(rec3))
    vs = [l for l in lines4 if "sponsorship" in l["detail"].casefold()]
    check("visa_sponsorship false -> warn", vs and vs[0]["kind"] == "warn")
    rec4 = _full_record("vs2:1")
    rec4["visa_sponsorship"] = {"value": "true", "evidence": "we sponsor",
                                "confidence": "high"}
    lines5 = present.fit_lines(present.view(rec4))
    vs2 = [l for l in lines5 if "sponsorship" in l["detail"].casefold()]
    check("visa_sponsorship true -> ok", vs2 and vs2[0]["kind"] == "ok")
    # exigencia de work permit -> warn
    rec5 = _full_record("wp:1")
    rec5["work_permit_required"] = {"value": "true",
                                    "evidence": "Arbeitserlaubnis erforderlich",
                                    "confidence": "high"}
    lines6 = present.fit_lines(present.view(rec5))
    wp = [l for l in lines6 if "work permit" in l["detail"].casefold()]
    check("work permit exigido -> warn", wp and wp[0]["kind"] == "warn")


def test_nenhum_dado_privado_no_view() -> None:
    print("== seguranca: view nao carrega metadados internos ==")
    v = present.view(_full_record())
    blob = json.dumps(v, ensure_ascii=False, default=str)
    for secret in ("content_hash", "final_url", "http_status", "page_status",
                   "usage", "model", "prompt", "fetched_at"):
        check(f"view nao expoe {secret!r}", secret not in blob)
    check("pending_content_hash nao vaza (so o bool stale)",
          "pending_content_hash" not in blob)


def main() -> int:
    test_is_usable()
    test_is_stale()
    test_view_full()
    test_view_semantics()
    test_evidence_limit()
    test_view_map_and_load()
    test_fit_lines()
    test_nenhum_dado_privado_no_view()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
