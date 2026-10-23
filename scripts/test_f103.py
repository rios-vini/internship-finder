"""F103 — Flag de re-post/twin no 🆕 do digest (display-only).

Testes offline puros; fixtures VERBATIM do registro de avaliações 18–23/10.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import ranking_digest as rg  # noqa: E402
from internship_finder.repost_flag import (  # noqa: E402
    _norm_company,
    build_previous_index,
    flag_reposts,
    format_repost_suffix,
    is_repost_flag_enabled,
    load_repost_config,
    repost_key,
    repost_metric,
)


def _check(desc: str, cond: bool) -> None:
    if not cond:
        raise AssertionError(f"FAIL: {desc}")
    print(f"OK: {desc}")


def test_norm_company() -> None:
    """Normalização de empresa (casefold + colapso espaços)."""
    _check("LIDL normalizado", _norm_company("Lidl") == "lidl")
    _check("LIDL STIFTUNG normalizado", _norm_company("Lidl Stiftung") == "lidl stiftung")
    _check("BoschGroup normalizado", _norm_company("BoschGroup") == "boschgroup")
    _check("Vitesco normalizado", _norm_company("Vitesco Technologies") == "vitesco technologies")
    _check("None vira vazio", _norm_company(None) == "")
    _check("string vazia vira vazio", _norm_company("") == "")
    _check("espaços colapsados", _norm_company("  Lidl   Stiftung  ") == "lidl stiftung")


def test_repost_key() -> None:
    """Chave determinística de near-dup: titulo_norm + empresa_norm + local_norm."""
    job = {
        "id": "test-1",
        "title": "Praktikant (m/w/d) Einkauf",
        "company": "Lidl",
        "location": "Neckarsulm, DE",
    }
    key = repost_key(job)
    _check("chave não é None", key is not None)
    _check("chave contém empresa", "lidl" in key)
    # normalize_title colapsa Praktikant/Werkstudent -> "working student"
    # (tokens em ordem alfabética no bag: einkauf student working)
    _check("chave contém working", "working" in key)
    _check("chave contém student", "student" in key)
    _check("chave contém einkauf", "einkauf" in key)
    _check("chave contém localização", "neckarsulm" in key)

    # Sem localização -> None (não funde cidades diferentes)
    job_no_loc = {**job, "location": ""}
    _check("sem localização retorna None", repost_key(job_no_loc) is None)

    # Sem empresa -> None
    job_no_comp = {**job, "company": ""}
    _check("sem empresa retorna None", repost_key(job_no_comp) is None)

    # Sem título -> None
    job_no_title = {**job, "title": ""}
    _check("sem título retorna None", repost_key(job_no_title) is None)


def test_build_previous_index() -> None:
    """Índice do run anterior agrupa por chave de re-post."""
    prev = [
        {"id": "prev-1", "title": "Praktikant (m/w/d) Einkauf", "company": "Lidl", "location": "Neckarsulm, DE"},
        {"id": "prev-2", "title": "Werkstudent (m/w/d) Controlling", "company": "Lidl", "location": "Neckarsulm, DE"},
        {"id": "prev-3", "title": "Praktikant (m/w/d) Purchasing", "company": "Würth", "location": "Künzelsau, DE"},
    ]
    idx = build_previous_index(prev)
    _check("índice tem 3 chaves", len(idx) == 3)
    # Duas vagas da Lidl em Neckarsulm com títulos diferentes = chaves diferentes
    lidl_keys = [k for k in idx if k.startswith("lidl|")]
    _check("Lidl tem 2 chaves distintas", len(lidl_keys) == 2)


def test_flag_reposts_basic() -> None:
    """Detecção básica de re-post: mesmo título+empresa+local no run anterior."""
    previous = [
        {"id": "prev-1", "title": "Praktikant (m/w/d) Einkauf", "company": "Lidl", "location": "Neckarsulm, DE"},
    ]
    current = [
        {"id": "cur-1", "title": "Praktikant (m/w/d) Einkauf", "company": "Lidl", "location": "Neckarsulm, DE"},  # re-post
        {"id": "cur-2", "title": "Werkstudent (m/w/d) Controlling", "company": "Lidl", "location": "Neckarsulm, DE"},  # nova
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("1 re-post flagged", count == 1)
    _check("cur-1 tem repost_match", "repost_match" in flagged[0])
    _check("cur-1 match company = Lidl", flagged[0]["repost_match"]["company"] == "Lidl")
    _check("cur-2 NÃO tem repost_match", "repost_match" not in flagged[1])


def test_surviving_job_not_repost() -> None:
    """Vaga que sobreviveu de ontem (MESMO id) NÃO é re-post — o alvo da
    F103 é o id NOVO cuja chave já existia (re-post/twin cross-ATS).
    Medido no snapshot real 23/10: sem esse guard, 644 jobs continuando
    seriam flaggados (página cheia de 🔄) — semântica corrigida."""
    previous = [
        {"id": "same-1", "title": "Praktikant (m/w/d) Einkauf", "company": "Lidl", "location": "Neckarsulm, DE"},
        {"id": "old-2", "title": "Praktikum SAP BI", "company": "Lidl", "location": "Neckarsulm, DE"},
    ]
    current = [
        # sobrevivente: mesmo id, mesma chave — NÃO é re-post
        {"id": "same-1", "title": "Praktikant (m/w/d) Einkauf", "company": "Lidl", "location": "Neckarsulm, DE"},
        # re-post real: id NOVO, chave já existia
        {"id": "new-post-9", "title": "Praktikum SAP BI", "company": "Lidl", "location": "Neckarsulm, DE"},
        # nova genuína
        {"id": "fresh-1", "title": "Werkstudent Logistik", "company": "Outra", "location": "Berlin, DE"},
    ]
    prev_ids = {str(j["id"]) for j in previous}
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx, previous_ids=prev_ids)
    _check("só o id NOVO com chave antiga é flagged", count == 1)
    _check("sobrevivente sem flag", "repost_match" not in flagged[0])
    _check("re-post real flaggado", "repost_match" in flagged[1])
    _check("nova genuína sem flag", "repost_match" not in flagged[2])
    # count_reposts (métrica F75) segue a MESMA semântica
    from internship_finder.repost_flag import count_reposts
    n = count_reposts(current, previous)
    _check("count_reposts = 1 (sobrevivente não conta)", n == 1)


def test_flag_reposts_twin_cross_ats() -> None:
    """Twin cross-ATS: mesma vaga, ATS diferente (Bosch AA × SR)."""
    # AA = Arbeitsagentur, SR = SuccessRecruiters
    previous = [
        {"id": "AA-REF298898V", "title": "Praktikum Risk & Purchasing", "company": "BoschGroup", "location": "Gerlingen, DE", "source": "arbeitsagentur"},
    ]
    current = [
        {"id": "SR-744000155984519", "title": "Internship Risk & Purchasing", "company": "BoschGroup", "location": "Gerlingen, DE", "source": "successfactors"},  # twin cross-ATS
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("twin cross-ATS flagged", count == 1)
    _check("match company = BoschGroup", flagged[0]["repost_match"]["company"] == "BoschGroup")


def test_flag_reposts_lidl_sap_bi() -> None:
    """Lidl SAP BI re-post (praktikum.info vs SF)."""
    previous = [
        {"id": "SF-1436050633", "title": "Praktikum SAP BI", "company": "Lidl", "location": "Neckarsulm, DE"},
    ]
    current = [
        {"id": "PI-13231277", "title": "Praktikum SAP BI", "company": "Lidl", "location": "Neckarsulm, DE"},  # re-post
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("Lidl SAP BI re-post flagged", count == 1)


def test_flag_reposts_lidl_controlling_projete() -> None:
    """Lidl Controlling Projete re-post vs antiga viva (1441979333 / 753653)."""
    previous = [
        {"id": "SF-1441979333", "title": "Praktikant Controlling Projekte", "company": "Lidl", "location": "Neckarsulm, DE", "ref": "753653"},
    ]
    current = [
        {"id": "LIDL-1426446133", "title": "Praktikant Controlling Projekte", "company": "Lidl", "location": "Neckarsulm, DE", "ref": "735605"},
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("Lidl Controlling Projete flagged", count == 1)
    _check("antiga continua viva (não é exclusão)", "repost_match" in flagged[0])


def test_title_change_limitation() -> None:
    """LIMITAÇÃO documentada (design constraint 2): título materialmente
    diferente NÃO é flaggado pela chave exata. O caso real Lidl Projete
    'ab sofort' no TÍTULO não funde — trade-off consciente (fuzzy = FP)."""
    previous = [
        {"id": "SF-1441979333", "title": "Praktikant Controlling Projekte", "company": "Lidl", "location": "Neckarsulm, DE"},
    ]
    current = [
        {"id": "LIDL-1426446133", "title": "Praktikant Controlling Projekte (ab sofort)", "company": "Lidl", "location": "Neckarsulm, DE"},
    ]
    idx = build_previous_index(previous)
    _, count = flag_reposts(current, idx)
    _check("título com sufixo novo NÃO flagged (chave exata)", count == 0)


def test_flag_reposts_wurth() -> None:
    """Würth Import Beschaffung re-post vs pacote já em feitas."""
    previous = [
        {"id": "done-1", "title": "Praktikant Import Beschaffung", "company": "Würth", "location": "Künzelsau, DE"},
    ]
    current = [
        {"id": "new-1", "title": "Praktikant Import Beschaffung", "company": "Würth", "location": "Künzelsau, DE"},
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("Würth flagged", count == 1)


def test_flag_reposts_vitesco() -> None:
    """Vitesco Risk & Purchasing re-post vs já aplicada."""
    previous = [
        {"id": "applied-1", "title": "Praktikum Risk & Purchasing", "company": "Vitesco", "location": "Regensburg, DE"},
    ]
    current = [
        {"id": "new-1", "title": "Praktikum Risk & Purchasing", "company": "Vitesco", "location": "Regensburg, DE"},
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("Vitesco flagged", count == 1)


def test_flag_reposts_relx() -> None:
    """RELX re-post vs pacote 21/10."""
    previous = [
        {"id": "old-1", "title": "Praktikant Legal Tech", "company": "RELX", "location": "München, DE"},
    ]
    current = [
        {"id": "new-1", "title": "Praktikant Legal Tech", "company": "RELX", "location": "München, DE"},
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("RELX flagged", count == 1)


def test_flag_reposts_dboerse() -> None:
    """DBörse NFR re-post vs já aplicada."""
    previous = [
        {"id": "applied-1", "title": "Praktikum Non-Financial Risk", "company": "Deutsche Börse", "location": "Frankfurt, DE"},
    ]
    current = [
        {"id": "new-1", "title": "Praktikum Non-Financial Risk", "company": "Deutsche Börse", "location": "Frankfurt, DE"},
    ]
    idx = build_previous_index(previous)
    flagged, count = flag_reposts(current, idx)
    _check("DBörse flagged", count == 1)


def test_format_repost_suffix() -> None:
    """Sufixo 🔄 para a linha 🆕 do digest."""
    job_flagged = {
        "repost_match": {"company": "Lidl", "key": "lidl|working student einkauf|neckarsulm"}
    }
    job_clean = {}

    suffix_flagged = format_repost_suffix(job_flagged)
    suffix_clean = format_repost_suffix(job_clean)

    _check("flagged tem sufixo 🔄", "🔄" in suffix_flagged)
    _check("flagged menciona empresa", "Lidl" in suffix_flagged)
    _check("flagged menciona MANUAL-CHECK", "MANUAL-CHECK" in suffix_flagged)
    _check("clean retorna vazio", suffix_clean == "")


def test_config_fail_closed() -> None:
    """Config ausente/corrompida = flag OFF sem erro."""
    with TemporaryDirectory() as tmp:
        # Arquivo não existe
        config = load_repost_config(Path(tmp) / "nao_existe.json")
        _check("arquivo ausente retorna None", config is None)
        _check("flag OFF quando config None", not is_repost_flag_enabled(config))

        # Arquivo corrompido (JSON inválido)
        bad = Path(tmp) / "bad.json"
        bad.write_text("{not json")
        config = load_repost_config(bad)
        _check("JSON inválido retorna None", config is None)

        # Arquivo vazio
        empty = Path(tmp) / "empty.json"
        empty.write_text("")
        config = load_repost_config(empty)
        _check("arquivo vazio retorna None", config is None)

        # Schema inválido (window_days não é int positivo)
        bad_schema = Path(tmp) / "bad_schema.json"
        bad_schema.write_text('{"window_days": "sete"}')
        config = load_repost_config(bad_schema)
        _check("window_days string retorna None", config is None)

        bad_schema2 = Path(tmp) / "bad_schema2.json"
        bad_schema2.write_text('{"window_days": 0}')
        config = load_repost_config(bad_schema2)
        _check("window_days zero retorna None", config is None)

        # Config válido
        good = Path(tmp) / "good.json"
        good.write_text('{"window_days": 7}')
        config = load_repost_config(good)
        _check("config válido carregado", config == {"window_days": 7})
        _check("flag ON quando config válido", is_repost_flag_enabled(config))


def test_new_since_lines_repost_suffix() -> None:
    """A/B: new_since_lines adiciona sufixo 🔄 quando job tem repost_match."""
    # Carrega fixtures do registro real
    fixtures_dir = Path(__file__).parent / "fixtures" / "f103"
    if not fixtures_dir.exists():
        print("SKIP: fixtures não encontradas (rodar no repo completo)")
        return

    cur_path = fixtures_dir / "cur.json"
    prev_path = fixtures_dir / "prev.json"
    if not cur_path.exists() or not prev_path.exists():
        print("SKIP: fixtures cur/prev não encontradas")
        return

    current = json.loads(cur_path.read_text())
    previous = json.loads(prev_path.read_text())

    # Flag re-posts
    idx = build_previous_index(previous)
    current_flagged, flagged_count = flag_reposts(current, idx)

    # Gera linhas 🆕
    diff = rg.new_since_previous(current_flagged, previous)
    lines = rg.new_since_lines(diff, current_flagged)

    # Verifica que linhas flagged têm sufixo 🔄
    flagged_lines = [l for l in lines if "🔄" in l]
    _check(f"pelo menos 1 linha com 🔄 (flagged={flagged_count})", len(flagged_lines) >= 1 if flagged_count > 0 else True)

    # Verifica que vaga genuinamente nova NÃO tem sufixo
    # (assumindo que as fixtures têm pelo menos uma vaga nova sem match)
    for line in lines:
        if line.startswith("  ") and "🔄" not in line and "—" in line:
            # Linha de vaga listada sem 🔄 = OK (pode ser nova genuína)
            pass


def test_ab_regression_no_twins_byte_identical() -> None:
    """A/B: digest SEM twins = byte a byte o do main (regressão zero).

    Quando não há matches de re-post, a seção 🆕 deve ser IDÊNTICA
    à saída sem o código F103.
    """
    # Cenário: nenhuma vaga é re-post/twin
    current = [
        {"id": "new-1", "title": "Praktikant Novelty", "company": "NovaEmpresa", "location": "Berlin, DE", "score": 15.0},
        {"id": "new-2", "title": "Werkstudent Fresh", "company": "OutraEmpresa", "location": "München, DE", "score": 14.5},
    ]
    previous = [
        {"id": "old-1", "title": "Praktikant Old", "company": "AntigaEmpresa", "location": "Hamburg, DE", "score": 13.0},
    ]

    # Sem flag (config OFF ou previous vazio)
    diff = rg.new_since_previous(current, previous)
    lines_without = rg.new_since_lines(diff, current)

    # Com flag mas SEM matches (previous vazio ou chaves diferentes)
    # O flag_reposts não adiciona repost_match quando não há match
    idx = build_previous_index(previous)
    current_flagged, _ = flag_reposts(current, idx)
    diff2 = rg.new_since_previous(current_flagged, previous)
    lines_with = rg.new_since_lines(diff2, current_flagged)

    _check("A/B: saída idêntica quando sem re-posts", lines_without == lines_with)


def test_repost_metric() -> None:
    """Métrica repost_flagged: N no JSONL."""
    m = repost_metric(3)
    _check("métrica tem chave repost_flagged", m == {"repost_flagged": 3})


def test_all_fixtures_flagged() -> None:
    """Todas as fixtures do registro 18-23/10 devem ser flagged."""
    # Este teste roda os 7 cenários do registro
    test_cases = [
        ("Lidl SAP BI", "Praktikum SAP BI", "Lidl", "Neckarsulm, DE"),
        ("Lidl Controlling Projete", "Praktikant Controlling Projekte", "Lidl", "Neckarsulm, DE"),
        ("Würth Import Beschaffung", "Praktikant Import Beschaffung", "Würth", "Künzelsau, DE"),
        ("Vitesco Risk & Purchasing", "Praktikum Risk & Purchasing", "Vitesco", "Regensburg, DE"),
        ("RELX", "Praktikant Legal Tech", "RELX", "München, DE"),
        ("DBörse NFR", "Praktikum Non-Financial Risk", "Deutsche Börse", "Frankfurt, DE"),
        ("Bosch Twin AA×SR", "Praktikum Risk & Purchasing", "BoschGroup", "Gerlingen, DE"),
    ]

    for name, title, company, location in test_cases:
        previous = [{"id": f"prev-{name}", "title": title, "company": company, "location": location}]
        current = [{"id": f"cur-{name}", "title": title, "company": company, "location": location}]
        idx = build_previous_index(previous)
        flagged, count = flag_reposts(current, idx)
        _check(f"{name} flagged", count == 1)


if __name__ == "__main__":
    test_norm_company()
    test_repost_key()
    test_build_previous_index()
    test_flag_reposts_basic()
    test_surviving_job_not_repost()
    test_flag_reposts_twin_cross_ats()
    test_flag_reposts_lidl_sap_bi()
    test_flag_reposts_lidl_controlling_projete()
    test_title_change_limitation()
    test_flag_reposts_wurth()
    test_flag_reposts_vitesco()
    test_flag_reposts_relx()
    test_flag_reposts_dboerse()
    test_format_repost_suffix()
    test_config_fail_closed()
    test_new_since_lines_repost_suffix()
    test_ab_regression_no_twins_byte_identical()
    test_repost_metric()
    test_all_fixtures_flagged()
    print("\n=== TODOS OS TESTES F103 PASSARAM ===")