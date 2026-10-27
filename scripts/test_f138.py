"""Testes para F138 — NEW diff com memória: re-entrantes + re-postagens marcadas + dead-marker FP."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

from internship_finder.cross_source_dedup_store import (  # noqa: E402
    CrossSourceDedupStore,
    compute_cross_source_dedup_key,
)
import ranking_digest  # noqa: E402
from url_liveness import _has_job_context, _soft_dead_in_body  # noqa: E402

class TestF138NewListMarkdown:
    """Testes para new_list_markdown com memória de sightings e vereditos manuais."""

    def test_new_list_markdown_basic(self):
        """Smoke test: new_list_markdown ainda funciona sem store/verdicts."""
        postings_diff = {
            "new_ids": {"job1"},
            "gone_ids": set(),
            "genuinely_new": [{"id": "job1", "company": "Acme", "title": "Intern", "location": "Berlin", "score": 5.0, "url": "http://example.com"}],
            "re_seen": [],
        }
        current = postings_diff["genuinely_new"]
        text = ranking_digest.new_list_markdown(
            postings_diff, current,
            previous_name="archive1",
            generated_at="2026-10-27T00:00:00+00:00",
        )
        assert "Acme · Intern · Berlin · 5 · http://example.com" in text
        assert "🔁 re-entrada" not in text
        assert "❌ você já eliminou" not in text

    def test_new_list_markdown_reentry_marker(self):
        """Re-entrada via cross_source_dedup_store marca 🔁 com data do 1º sighting."""
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "cross_source_dedup.db"
            store = CrossSourceDedupStore(store_path, "run-2026-10-27")
            store._open()

            # Job do run anterior (25/10)
            job_old = {
                "id": "ford-68902-old",
                "company": "Ford Global Career Site",
                "title": "Praktikant (m/w/d) im SAP Warehouse Management",
                "location": "Köln, Nordrhein Westfalen, Germany",
                "url": "https://efds.fa.em5.oraclecloud.com/?keyword=&mode=jobs&lang=en&site_number=CX_1#68902",
            }
            key = compute_cross_source_dedup_key(job_old)
            store.write(key, job_old["id"])
            store.close()

            # Re-abre store para novo run (26/10)
            store2 = CrossSourceDedupStore(store_path, "run-2026-10-28")
            store2._open()

            # Mesmo job aparece de novo (ID pode ser diferente)
            job_new = {
                "id": "ford-68902-new",
                "company": "Ford Global Career Site",
                "title": "Praktikant (m/w/d) im SAP Warehouse Management",
                "location": "Köln, Nordrhein Westfalen, Germany",
                "url": "https://efds.fa.em5.oraclecloud.com/?keyword=&mode=jobs&lang=en&site_number=CX_1#68902",
                "score": 3.86,
            }
            postings_diff = {
                "new_ids": {job_new["id"]},
                "gone_ids": set(),
                "genuinely_new": [job_new],
                "re_seen": [],
            }
            current = [job_new]

            text = ranking_digest.new_list_markdown(
                postings_diff, current,
                previous_name="archive1",
                generated_at="2026-10-28T00:00:00+00:00",
                dedup_store=store2,
            )

            assert "🔁 re-entrada (vista em 27/10)" in text or "🔁 re-entrada (vista em 2026-10-27)" in text
            store2.close()

    def test_new_list_markdown_manual_verdict(self):
        """Veredito manual do dono marca ❌ com motivo."""
        postings_diff = {
            "new_ids": {"job1"},
            "gone_ids": set(),
            "genuinely_new": [
                {"id": "job1", "company": "Ford", "title": "SAP Intern", "location": "Köln", "score": 3.86, "url": "http://ford.com/68902"}
            ],
            "re_seen": [],
        }
        current = postings_diff["genuinely_new"]
        key = compute_cross_source_dedup_key(current[0])
        manual_verdicts = {
            key: {"verdict": "eliminada", "reason": "eixo/alemão", "date": "25/10"}
        }

        text = ranking_digest.new_list_markdown(
            postings_diff, current,
            previous_name="archive1",
            generated_at="2026-10-28T00:00:00+00:00",
            manual_verdicts=manual_verdicts,
        )

        assert "❌ você já eliminou esta (eixo/alemão)" in text

    def test_new_list_markdown_reentry_and_verdict(self):
        """Ambos marcadores podem aparecer juntos."""
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "cross_source_dedup.db"
            store = CrossSourceDedupStore(store_path, "run-2026-10-27")
            store._open()

            job_old = {
                "id": "ford-old",
                "company": "Ford",
                "title": "SAP Intern",
                "location": "Köln",
                "url": "http://ford.com/68902",
            }
            key = compute_cross_source_dedup_key(job_old)
            store.write(key, job_old["id"])
            store.close()

            store2 = CrossSourceDedupStore(store_path, "run-2026-10-28")
            store2._open()

            job_new = {
                "id": "ford-new",
                "company": "Ford",
                "title": "SAP Intern",
                "location": "Köln",
                "url": "http://ford.com/68902",
                "score": 3.86,
            }
            postings_diff = {
                "new_ids": {job_new["id"]},
                "gone_ids": set(),
                "genuinely_new": [job_new],
                "re_seen": [],
            }
            current = [job_new]
            manual_verdicts = {
                key: {"verdict": "eliminada", "reason": "eixo/alemão", "date": "25/10"}
            }

            text = ranking_digest.new_list_markdown(
                postings_diff, current,
                previous_name="archive1",
                generated_at="2026-10-28T00:00:00+00:00",
                dedup_store=store2,
                manual_verdicts=manual_verdicts,
            )

            assert "🔁 re-entrada" in text
            assert "❌ você já eliminou esta (eixo/alemão)" in text
            store2.close()

class TestF138DeadMarkerFP:
    """Testes para evitar false-positivo em privacy policy (GDPR/Aufbewahrung)."""

    def test_privacy_policy_aufbewahrung_no_fp(self):
        """Texto de privacy policy sobre retenção NÃO marca dead."""
        # Texto típico de GDPR/Aufbewahrungsfristen
        privacy_text = """
        Datenschutzerklärung: Personenbezogene Daten werden gelöscht,
        sobald sie für die Zweckbestimmung nicht mehr erforderlich sind.
        Die Aufbewahrungsfrist beträgt 6 Jahre gemäß § 257 HGB.
        Daten, die nicht mehr verfügbar sind, werden gelöscht.
        Die Stelle ist besetzt mit der Verarbeitung Ihrer Daten.
        """
        # "nicht mehr verfügbar" e "stelle ist besetzt" aparecem mas SEM contexto de vaga
        assert _soft_dead_in_body(privacy_text) is None

    def test_job_page_stelle_ist_besetzt_marks_dead(self):
        """Página de vaga com 'stelle ist besetzt' + contexto MARCA dead."""
        job_text = """
        Praktikant (m/w/d) SAP Warehouse Management
        Diese Stelle ist leider bereits besetzt.
        Bewerbung nicht mehr möglich.
        """
        assert _soft_dead_in_body(job_text) is not None

    def test_job_page_nicht_mehr_verfugbar_marks_dead(self):
        """Página de vaga com 'nicht mehr verfügbar' + contexto MARCA dead."""
        job_text = """
        Stellenausschreibung: Werkstudent Supply Chain
        Diese Position ist nicht mehr verfügbar.
        Bewerbungen werden nicht mehr akzeptiert.
        """
        assert _soft_dead_in_body(job_text) is not None

    def test_has_job_context_detects_job_words(self):
        """_has_job_context encontra palavras de vaga próximas ao marcador."""
        text = "Dieser Praktikant Stelle ist nicht mehr verfügbar für Bewerbung"
        # "nicht mehr verfügbar" está na posição ~35
        marker_pos = text.casefold().find("nicht mehr verfügbar")
        assert _has_job_context(text, marker_pos) is True

    def test_has_job_context_no_fp_on_privacy(self):
        """_has_job_context NÃO encontra palavras de vaga em privacy policy."""
        text = "Daten werden gelöscht, sobald sie nicht mehr verfügbar sind. Aufbewahrungsfrist 6 Jahre."
        marker_pos = text.casefold().find("nicht mehr verfügbar")
        assert _has_job_context(text, marker_pos) is False

    def test_fake200_requires_context(self):
        """FAKE200 markers também exigem contexto de vaga."""
        from url_liveness import _fake_200_in_short_body, FAKE200_MAX_BODY_CHARS

        # Privacy policy curto (simulado) - NÃO deve marcar
        privacy_short = "Daten nicht mehr verfügbar. Aufbewahrung 6 Jahre."
        assert _fake_200_in_short_body(privacy_short, len(privacy_short)) is None

        # Job page curto com contexto - DEVE marcar
        job_short = "Stelle Praktikant bereits besetzt. Bewerbung geschlossen."
        assert _fake_200_in_short_body(job_short, len(job_short)) == "bereits besetzt"

class TestF138LoadManualVerdicts:
    """Testes para carregamento de manual_verdicts.json."""

    def test_load_manual_verdicts_valid(self):
        """Carrega vereditos válidos do JSON."""
        from refresh_daily import load_manual_verdicts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "key1": {"verdict": "eliminada", "reason": "eixo/alemão", "date": "25/10"},
                "key2": {"verdict": "pendente", "reason": "aguardando resposta", "date": ""},
            }, f)
            path = f.name

        try:
            verdicts = load_manual_verdicts(path)
            assert len(verdicts) == 2
            assert verdicts["key1"]["reason"] == "eixo/alemão"
            assert verdicts["key2"]["verdict"] == "pendente"
        finally:
            Path(path).unlink()

    def test_load_manual_verdicts_invalid_entries_ignored(self):
        """Entradas inválidas são ignoradas silenciosamente."""
        from refresh_daily import load_manual_verdicts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "key1": {"verdict": "eliminada", "reason": "ok"},
                "key2": {"verdict": "eliminada"},  # sem reason -> ignorado
                "key3": {"reason": "ok"},  # sem verdict -> ignorado
                "key4": "not a dict",  # ignorado
            }, f)
            path = f.name

        try:
            verdicts = load_manual_verdicts(path)
            assert len(verdicts) == 1
            assert "key1" in verdicts
        finally:
            Path(path).unlink()

    def test_load_manual_verdicts_missing_file_returns_empty(self):
        """Arquivo ausente retorna dict vazio (não derruba)."""
        from refresh_daily import load_manual_verdicts
        verdicts = load_manual_verdicts("/nonexistent/path/manual_verdicts.json")
        assert verdicts == {}

    def test_load_manual_verdicts_malformed_json_returns_empty(self):
        """JSON malformado retorna dict vazio (não derruba)."""
        from refresh_daily import load_manual_verdicts
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            path = f.name

        try:
            verdicts = load_manual_verdicts(path)
            assert verdicts == {}
        finally:
            Path(path).unlink()

    def test_load_manual_verdicts_example_file(self):
        """O arquivo de exemplo data/manual_verdicts.example.json carrega sem erro (gate F142)."""
        from refresh_daily import load_manual_verdicts
        # F142-cura: o example vive em config/ (data/ e gitignored — em data/ o
        # arquivo nunca chegaria ao runner do CI e este gate explodiria lá)
        example_path = Path(__file__).resolve().parent.parent / "config" / "manual_verdicts.example.json"
        assert example_path.exists(), f"Arquivo de exemplo não encontrado: {example_path}"
        verdicts = load_manual_verdicts(example_path)
        # Deve carregar as entradas válidas do exemplo
        assert len(verdicts) >= 2
        # Verificar estrutura das entradas carregadas
        for key, value in verdicts.items():
            assert "verdict" in value
            assert "reason" in value
            assert "date" in value
            assert value["verdict"] in ("eliminada", "pendente")
            assert isinstance(value["reason"], str) and value["reason"]
            assert isinstance(value["date"], str)

def main() -> int:
    """Runner standalone (padrao do projeto — f61/f93; o CI nao instala pytest)."""
    classes = [TestF138NewListMarkdown, TestF138DeadMarkerFP, TestF138LoadManualVerdicts]
    fails: list[str] = []
    total = 0
    for cls in classes:
        inst = cls()
        for name in sorted(dir(inst)):
            if not name.startswith("test_"):
                continue
            total += 1
            try:
                getattr(inst, name)()
                print(f"  [OK] {cls.__name__}.{name}")
            except Exception as exc:  # noqa: BLE001 — conta e segue
                print(f"  [FAIL] {cls.__name__}.{name}: {type(exc).__name__}: {exc}")
                fails.append(f"{cls.__name__}.{name}")
    print(f"\nF138: {len(fails)} falha(s) de {total}")
    return 1 if fails else 0

if __name__ == "__main__":
    raise SystemExit(main())
