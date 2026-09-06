"""Testes do modulo de pais (scripts/test_countries.py).

Cobre o dominio extraido para ``src/internship_finder/countries.py`` (P2 #12):
constantes (COUNTRY_CODES, EUROPE_COUNTRIES, COUNTRY_NAMES) e as funcoes de
inferencia/filtro (infer_country_iso, parse_country_spec, matches_country,
is_remote). Inclui um bloco de compatibilidade comprovando que ``filters``
re-exporta os mesmos simbolos, e um bloco "real" sobre data/eligible_jobs.json
(skip com exit 0 quando os dados nao existem). Uso:

    .venv/bin/python scripts/test_countries.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.countries import (  # noqa: E402
    COUNTRY_CODES,
    COUNTRY_NAMES,
    EUROPE_COUNTRIES,
    infer_country_iso,
    is_remote,
    matches_country,
    parse_country_spec,
)
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.filters import select_eligible  # noqa: E402
from internship_finder.models.job import normalize_job_dict  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_synthetic() -> None:
    print("== sintetico ==")
    # infer_country_iso com location DE explicita.
    check("infer_country_iso('Berlin, DE') == 'de'",
          infer_country_iso(location="Berlin, DE") == "de")
    check("infer_country_iso('Berlin, Germany') == 'de'",
          infer_country_iso(location="Berlin, Germany") == "de")
    # ISO antes de CEP numerico (formato SAP).
    check("infer_country_iso('Walldorf, DE, 69190') == 'de'",
          infer_country_iso(location="Walldorf, DE, 69190") == "de")
    check("infer_country_iso('Friedrichshafen, BW, DE, 88046') == 'de'",
          infer_country_iso(location="Friedrichshafen, BW, DE, 88046") == "de")
    # Sem pais confiavel -> None (token de 2 letras no MEIO nao vale).
    check("infer_country_iso('UnresolvableCityXYZ') is None",
          infer_country_iso(location="UnresolvableCityXYZ") is None)
    check("infer_country_iso('Sao Bernardo do Campo') is None",
          infer_country_iso(location="Sao Bernardo do Campo") is None)
    check("infer_country_iso(None, None, None) is None",
          infer_country_iso() is None)
    # country_iso explícito preservado.
    check("country_iso explicito preservado",
          infer_country_iso(location="x", country_iso="ch") == "ch")
    # Pais declarado nao-ISO valido cai para o fallback por location.
    check("country invalido cai para ISO da location",
          infer_country_iso(location="Berlin, DE", country="france") == "de")

    # parse_country_spec.
    check("parse_country_spec('de') == {'de'}",
          parse_country_spec("de") == frozenset({"de"}))
    check("parse_country_spec('de,at') == {'de','at'}",
          parse_country_spec("de,at") == frozenset({"de", "at"}))
    check("parse_country_spec('europe') e EUROPE_COUNTRIES",
          parse_country_spec("europe") is EUROPE_COUNTRIES)
    check("parse_country_spec('all') is None",
          parse_country_spec("all") is None)
    check("parse_country_spec('remote') == 'remote'",
          parse_country_spec("remote") == "remote")
    # P2 #15: validacao — token nao-ISO ou spec vazia levantam ValueError.
    for bad, token in (
        ("xx", "xx"),
        ("de,xx", "xx"),
        ("europe,de", "europe"),
        (",", None),
    ):
        try:
            parse_country_spec(bad)
        except ValueError as exc:
            check(f"parse_country_spec({bad!r}) levanta ValueError", True)
            if token:
                check(f"parse_country_spec({bad!r}) cita {token!r}",
                      token in str(exc))
        else:
            check(f"parse_country_spec({bad!r}) levanta ValueError", False)
    # Compat/comportamento preservado para especs validas.
    check("parse_country_spec('DE,AT') == {'de','at'} (case-insensitive)",
          parse_country_spec("DE,AT") == frozenset({"de", "at"}))
    check("parse_country_spec('de,,at') == {'de','at'} (virgulas duplas ok)",
          parse_country_spec("de,,at") == frozenset({"de", "at"}))
    check("parse_country_spec('world') is None (compat, 'all' canonico)",
          parse_country_spec("world") is None)
    check("parse_country_spec('any') is None (compat)", parse_country_spec("any") is None)
    check("parse_country_spec('EUROPE') e EUROPE_COUNTRIES (case)",
          parse_country_spec("EUROPE") is EUROPE_COUNTRIES)

    # matches_country com 'de'.
    spec_de = parse_country_spec("de")
    check("matches_country de: country_iso=de aceita",
          matches_country("de", None, None, spec_de))
    check("matches_country de: Berlin, DE aceita",
          matches_country(None, "Berlin, DE", None, spec_de))
    check("matches_country de: sem localizacao rejeita",
          not matches_country(None, None, None, spec_de))
    check("matches_country all: aceita sem localizacao",
          matches_country(None, None, None, parse_country_spec("all")))

    # is_remote (geografia, vive em countries).
    check("is_remote: campo remote True",
          is_remote("Munich", True))
    check("is_remote: 'remote' na location",
          is_remote("Remote (Germany)", False))
    # P3 #20 (ACH-16): o filtro --country remote funciona SEM o campo remote
    # preenchido (nenhum ATS expoe o campo hoje — medido 0/38.038 em
    # data/jobs.json), via marcador na location.
    spec_remote = parse_country_spec("remote")
    check("matches_country remote: so location com 'remote' aceita",
          matches_country(None, "Remote (Germany)", None, spec_remote))
    check("matches_country remote: home office na location aceita",
          matches_country(None, "Hamburg | Home Office", None, spec_remote))
    check("matches_country remote: sem marcador rejeita",
          not matches_country(None, "Stuttgart", None, spec_remote))

    # Constantes do dominio.
    check("EUROPE_COUNTRIES contem de/at/ch",
          {"de", "at", "ch"} <= EUROPE_COUNTRIES)
    # P3 #20 (ACH-19): BY/RU ficam de fora de EUROPE_COUNTRIES (decisao
    # documentada na docstring — comentario ja dizia; o codigo incluia 'by'
    # por engano. Medido: 0 vagas reais com ISO 'by'/'ru' em data/jobs.json).
    check("EUROPE_COUNTRIES NAO contem 'by' (BY excluido, ACH-19)",
          "by" not in EUROPE_COUNTRIES)
    check("EUROPE_COUNTRIES NAO contem 'ru' (RU excluido)",
          "ru" not in EUROPE_COUNTRIES)
    check("COUNTRY_NAMES mapeia 'Germany' -> 'de'",
          COUNTRY_NAMES.get("germany") == "de")
    check("COUNTRY_NAMES mapeia 'Deutschland' -> 'de'",
          COUNTRY_NAMES.get("deutschland") == "de")
    check("COUNTRY_NAMES mapeia 'United States' -> 'us'",
          COUNTRY_NAMES.get("united states") == "us")
    check("COUNTRY_CODES valido tem 'de'",
          "de" in COUNTRY_CODES)


def test_compat_re_export() -> None:
    print("== compatibilidade (filters re-exporta) ==")
    from internship_finder.filters import (  # noqa: F401
        COUNTRY_CODES as F_COUNTRY_CODES,
        infer_country_iso as F_infer,
        is_remote as F_is_remote,
        matches_country as F_matches,
        parse_country_spec as F_parse,
    )
    check("filters.infer_country_iso e o mesmo objeto",
          F_infer is infer_country_iso)
    check("filters.matches_country e o mesmo objeto", F_matches is matches_country)
    check("filters.parse_country_spec e o mesmo objeto", F_parse is parse_country_spec)
    check("filters.is_remote e o mesmo objeto", F_is_remote is is_remote)
    check("filters.COUNTRY_CODES e o mesmo objeto", F_COUNTRY_CODES is COUNTRY_CODES)
    # Funcionamento via re-export.
    check("filters.infer_country_iso('Berlin, DE') == 'de'",
          F_infer(location="Berlin, DE") == "de")
    check("filters.matches_country de aceita",
          F_matches("de", None, None, F_parse("de")))


def test_cli_validation() -> None:
    print("== CLI: validacao de --country (P2 #15) ==")
    import contextlib
    import io

    from internship_finder.cli import main

    # Valor invalido -> SystemExit(2) com mensagem clara (antes: 0 vagas
    # silencioso com exit 1). A validacao roda antes de ler --input, entao
    # nao depende de arquivo nenhum.
    for spec in ("xx", "de,xx", ",", "europe,de"):
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                main(["--country", spec, "--input", "/tmp/nao-existe-p2-15.json",
                      "--output", "/tmp/p2_15_invalido.json"])
        except SystemExit as exc:
            check(f"cli --country {spec!r} -> exit 2", exc.code == 2)
            check(f"cli --country {spec!r} -> mensagem clara",
                  "invalida" in err.getvalue() or "vazia" in err.getvalue())
        else:
            check(f"cli --country {spec!r} -> SystemExit(2)", False)

    # Spec valida nao e bloqueada: o erro passa a ser do --input inexistente
    # (prova que a validacao nova nao interfere em especs validas).
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            main(["--country", "de,at", "--input", "/tmp/nao-existe-p2-15.json",
                  "--output", "/tmp/p2_15_valido.json"])
    except SystemExit as exc:
        check("cli --country 'de,at' valido: erro vem do input (nao do pais)",
              exc.code == 2 and "nao encontrado" in err.getvalue())
    else:
        check("cli --country 'de,at' valido: erro vem do input (nao do pais)", False)


def test_real_data() -> None:
    print("== execucao real (data/eligible_jobs.json) ==")
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "eligible_jobs.json"
    # Ambiente sem coleta (ex.: CI runner sem data/): skip do bloco real com
    # exit 0. O bloco so roda onde o arquivo existe localmente.
    if not path.exists():
        print("  SKIP: data/eligible_jobs.json ausente (sem coleta local) - bloco real ignorado")
        return
    elig = json.loads(path.read_text(encoding="utf-8"))
    jobs_path = root / "data" / "jobs.json"
    if not jobs_path.exists():
        print("  SKIP: data/jobs.json ausente - nao da para re-rodar a cascata")
        return
    raw = json.loads(jobs_path.read_text(encoding="utf-8"))
    normalized = [j.to_dict() if hasattr(j, "to_dict") else normalize_job_dict(j)
                  for j in raw]
    sel, _ = select_eligible(normalized, student=True, area=True, country="de")
    sel, _, _ = deduplicate(sel)
    # Selecionados (antes do ranking) devem ser SUBCONJUNTO do snapshot eligible
    # (ranking nao muda pertencimento) — dedup so REMOVE, nunca adiciona, entao
    # o pipeline atual nunca pode conter id fora do snapshot. Comparacao exata
    # (numero magico / ids iguais) amarrava o teste ao snapshot vigente e quebrou
    # quando o dedup 2.0 (P2 #14, 03/09) passou a remover 4 duplicatas textuais a
    # mais (236 -> 232) sem regenerar o snapshot — mesmo acoplamento que P2 #16
    # removeu de test_ranking (fixture + invariantes no lugar do numero magico).
    elig_ids = {j["id"] for j in elig}
    sel_ids = {j["id"] for j in sel}
    check("real: pipeline atual e subconjunto do snapshot (dedup so remove)",
          len(sel_ids - elig_ids) == 0)
    check("real: todos com country_iso='de'",
          all(j.get("country_iso") == "de" for j in sel))
    # Observabilidade do delta: snapshot mais antigo pode ter ids a mais
    # (removidos como duplicatas por regras novas); ids ausentes no pipeline
    # atual indicam apenas dedup mais forte, nunca corrupcao de saida.
    staled = sorted(elig_ids - sel_ids)
    print(f"  observacao: snapshot {len(elig_ids)} ids | pipeline atual "
          f"{len(sel_ids)} ids | no snapshot e fora do atual: {len(staled)}")
    for jid in staled:
        print(f"    - {jid}")


def main() -> int:
    test_synthetic()
    test_compat_re_export()
    test_cli_validation()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())