"""Testes da Fase F12 — camada de EXIBICAO EN (100% offline).

Cobre as 5 tarefas da fase sem rede e sem ``data/`` de producao:

- **T1 Titulos DE->EN deterministicos** (``display_translate.title_en``):
  dicionario display, word-boundary (compostos NAO traduzidos), smart-case,
  fora-do-dicionario fica como esta, ja-EN nao muda, None/vazio -> None,
  case-insensitive, guarda Pflichtpraktikum == "Mandatory internship"
  (PROTECAO contra copiar TYPE_EQUIVALENCES do dedup, que colapsa
  praktikum em "working student" — errado para display).
- **T1b Linha EN no card**: abaixo do titulo DE (que NUNCA e substituido),
  so quando a traducao difere; ja-EN/fora-do-dicionario sem linha falsa.
- **T4 Glossario**: rodape estatico com os 6 termos fixos, HTML puro
  (sem JS), presente em todo render.
- **T2 Cache + snippet EN**: hit -> snippet EN marcado como traducao;
  miss/ausente/corrompido -> snippet DE como hoje; persistencia
  escreve->re-le; gravacao atomica sem temporario sobrando.
- **T2b Ferramenta on-demand** (``scripts/translate_description.py``):
  transport falso injetado (SEM rede), retry 429, erro nao-retryavel para
  na 1a, sanitize (key nunca no erro), --top/--job-id, cache hit pulado,
  --force, env ausente -> falha graciosa SEM gravar nada.
- **T3 Original nunca sai**: JSON/CSV byte a byte identicos com a camada
  F12 exercida (save_outputs 2x + sha256); nenhum modulo do pipeline
  importa display_translate (grafo de imports); digest NAO traduzido.
- **T5 Fallback offline**: sem NVIDIA_API_KEY a ferramenta recusa com
  mensagem clara; titulos por dicionario + glossario seguem (offline);
  render sem cache e identico ao de hoje nos snippets (DE).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import publish_pages as pp  # noqa: E402
import translate_description as td  # noqa: E402
from internship_finder import display_translate as dt  # noqa: E402
from internship_finder.enrichment.fetch import RequestsTransport  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures (offline; mesmo formato do eligible_jobs.json)
# ---------------------------------------------------------------------------

def _job(i: int, *, company=None, title=None, score=None, desc=None) -> dict:
    return {
        "id": f"t{i}",
        "title": title or f"Praktikum Supply Chain {i}",
        "company": company or f"Firma {i} GmbH",
        "location": "Berlin, DE", "country_iso": "de",
        "score": 15.0 - (i * 0.1) if score is None else score,
        "url": f"https://jobs.example.com/{i}",
        "description": desc or "Werkstudent supply chain logistics procurement",
        "raw": {},
    }


def _resp(payload: dict, status: int = 200):
    return status, json.dumps(payload)


def _llm_ok(content: str) -> tuple[int, str]:
    return _resp({"choices": [{"message": {"content": content}}],
                  "usage": {"prompt_tokens": 10, "completion_tokens": 7}})


class FakeTransport:
    """Transport falso (padrao test_enrichment): respostas em fila."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple] = []

    def post(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload))
        if not self.responses:
            raise AssertionError("transport: chamada alem das respostas")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, headers, timeout):  # protocolo Transport
        raise AssertionError("transport de traducao nao deve fazer GET")


NO_BACKOFF = (0.0, 0.0)


# ---------------------------------------------------------------------------
# T1 — title_en (dicionario display deterministico, offline)
# ---------------------------------------------------------------------------

def test_title_en_dictionary() -> None:
    section("T1: title_en — dicionario display DE->EN")
    cases = [
        # (entrada, esperado)
        ("Praktikum Logistik", "Internship Logistics"),
        ("Werkstudent SCM Beschaffung", "Working student SCM Procurement"),
        ("Pflichtpraktikum Einkauf", "Mandatory internship Purchasing"),
        ("Abschlussarbeit im Bereich Vertrieb",
         "Thesis im Bereich Sales"),  # preposicoes DE ficam (parcial honesta)
        ("Facharbeit Produktion", "Thesis project Production"),
        ("Praktikant Logistik (m/w/d)", "Intern Logistics (m/w/d)"),
        ("Werkstudentin / Werkstudent", "Working student / Working student"),
        ("Datenanalyse und Künstliche Intelligenz",
         "Data analytics und Artificial Intelligence"),
        ("Lieferkette und Lager", "Supply chain und Warehouse"),
    ]
    for src, want in cases:
        got = dt.title_en(src)
        check(f"{src!r} -> {want!r}", got == want)

    # guarda CRITICO da spec: display Praktikum = internship; NUNCA copiar
    # TYPE_EQUIVALENCES do dedup (que colapsa em "working student")
    check("guarda: Pflichtpraktikum == 'Mandatory internship'",
          dt.title_en("Pflichtpraktikum") == "Mandatory internship")
    check("guarda: 'working student' NUNCA aparece para Praktikum",
          "working student" not in (dt.title_en("Praktikum") or ""))
    check("Praktikum -> Internship (spec do dono)",
          dt.title_en("Praktikum") == "Internship")


def test_title_en_edge_cases() -> None:
    section("T1: title_en — bordas: None/vazio, ja-EN, fora do dicionario")
    check("None -> None", dt.title_en(None) is None)
    check("vazio -> None", dt.title_en("") is None)
    check("ja-EN nao muda", dt.title_en("Working Student Logistics")
          == "Working Student Logistics")
    check("ja-EN internship nao muda", dt.title_en("Internship Program")
          == "Internship Program")
    check("fora do dicionario fica como esta (parcial honesta)",
          dt.title_en("Betriebswirtschaft") == "Betriebswirtschaft")
    check("parcial: termo DE + fora do dicionario",
          dt.title_en("Praktikum Betriebswirtschaft")
          == "Internship Betriebswirtschaft")
    # case-insensitive + smart-case
    check("case-insensitive: PRAKTIKUM LAGER",
          dt.title_en("PRAKTIKUM LAGER") == "INTERNSHIP WAREHOUSE")
    check("case-insensitive: werkstudent logistik (minusculo)",
          dt.title_en("werkstudent logistik") == "working student logistics")
    check("misto: pRAKTIKUM -> p...? smart-case segue o 1o char do match "
          "(minusculo fica minusculo — honesto, sem casing inventado)",
          dt.title_en("pRAKTIKUM") == "internship")
    # compostos alemaes NAO sao traduzidos (word-boundary dos dois lados)
    check("composto 'Einkaufslogistik' intacto (sem monstro 'purchasinglogistik')",
          dt.title_en("Einkaufslogistik Specialist") == "Einkaufslogistik Specialist")
    check("composto 'Werkstudentenwerk' intacto",
          dt.title_en("Werkstudentenwerk") == "Werkstudentenwerk")
    check("'Pflichtpraktikum' NAO casa dentro de 'Praktikum' (word-boundary)",
          dt.title_en("Pflichtpraktikum") != "PflichtInternship")
    # plural/genitivo suportados SO como palavra inteira
    check("Praktika -> Internships", dt.title_en("Praktika") == "Internships")
    check("Werkstudenten -> Working students",
          dt.title_en("Werkstudenten") == "Working students")
    check("Einkaufs (genitivo solto) -> Purchasing",
          dt.title_en("Bereich Einkaufs") == "Bereich Purchasing")


def test_title_line_in_card() -> None:
    section("T1b: linha EN no card — abaixo do titulo; DE nunca substituido")
    jobs = [
        _job(0, title="Praktikum Logistik"),
        _job(1, title="Working Student Logistics"),   # ja-EN
        _job(2, title="Betriebswirtschaft"),         # fora do dicionario
        _job(3, title=None),                          # sem titulo
    ]
    jobs[3]["title"] = None
    html = mp.render_minimal_html(jobs, total_eligible=4, generated_at="x")
    check("linha EN presente no card DE", 'class="en">EN: Internship Logistics<' in html)
    check("titulo DE original preservado", "Praktikum Logistik" in html)
    check("so UMA linha EN (ja-EN/fora-do-dicionario nao ganham)",
          html.count('class="en">EN:') == 1)
    check("card ja-EN sem linha EN falsa",
          "EN: Working Student Logistics" not in html)
    # ordem: linha EN vem DEPOIS do titulo original (dentro do mesmo card)
    card0 = html.split('data-q="Praktikum Logistik')[1].split("</li>")[0]
    check("linha EN abaixo do titulo (titulo antes da linha EN)",
          card0.index("Praktikum Logistik") < card0.index("EN: Internship Logistics"))
    # linha EN fica entre o titulo e a linha meta (empresa): dentro do
    # corpo do card (apos o fechamento do data-q), o texto visualizado
    bd = card0.split('<div class="bd">')[1]
    check("linha EN antes do meta (empresa) no corpo do card",
          bd.index("EN: Internship Logistics") < bd.index("Firma 0 GmbH"))
    # data-q continua sem o titulo EN (busca nao muda de contrato)
    check("data-q nao embute o titulo EN",
          'data-q="Praktikum Logistik Firma 0 GmbH Berlin, DE"' in html)


def test_glossary_footer() -> None:
    section("T4: rodape-glossario estatico (6 termos, HTML puro)")
    html = mp.render_minimal_html([_job(0)], total_eligible=1, generated_at="x")
    check("glossario presente", "Glossário DE→EN:" in html)
    for de, en in mp.GLOSSARY_TERMS:
        check(f"termo {de} = {en}", f"{de} = {en}" in html)
    check("6 termos fixos", len(mp.GLOSSARY_TERMS) == 6)
    check("sem JS no glossario (classe gloss, puro texto)",
          'class="gloss"' in html)
    check("glossario no fim (depois do rodape F6)",
          html.index("Glossário DE→EN:") > html.index("ranking, JSON e CSV completos"))
    check("sem emoji no glossario (contrato visual F7)",
          "🇩🇪" not in html.split("Glossário")[1].split("</p>")[0])


# ---------------------------------------------------------------------------
# T2 — cache + snippet EN
# ---------------------------------------------------------------------------

def test_cache_roundtrip() -> None:
    section("T2: cache — escreve -> re-le (persistencia); atomico")
    with tempfile.TemporaryDirectory(prefix="t_f12_cache_") as tmp:
        cache_path = Path(tmp) / "data" / dt.CACHE_FILE_NAME
        cache = {"t1": {"en": "Warehouse intern role", "ts": 123.456}}
        dt.save_translation_cache(cache_path, cache)
        check("arquivo criado", cache_path.exists())
        loaded = dt.load_translation_cache(cache_path)
        check("re-le igual ao gravado", loaded == cache)
        check("sem temporario sobrando",
              not [p for p in cache_path.parent.iterdir()
                   if p.name.startswith(".") and p.name.endswith(".tmp")])
        # entry invalida (sem "en") descartada no load — cache sujo nao polui
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        raw["t2"] = {"ts": 1}
        raw["t3"] = "sem dict"
        cache_path.write_text(json.dumps(raw), encoding="utf-8")
        check("entrada invalida descartada no load",
              dt.load_translation_cache(cache_path) == {"t1": cache["t1"]})


def test_cache_corrupt_graceful() -> None:
    section("T2: cache — ausente/corrompido -> vazio, NADA quebra")
    with tempfile.TemporaryDirectory(prefix="t_f12_corr_") as tmp:
        missing = Path(tmp) / "nao_existe.json"
        check("ausente -> {}", dt.load_translation_cache(missing) == {})
        corrupt = Path(tmp) / "corrompido.json"
        corrupt.write_text("{corrompido", encoding="utf-8")
        check("corrompido -> {}", dt.load_translation_cache(corrupt) == {})
        lista = Path(tmp) / "lista.json"
        lista.write_text("[1,2]", encoding="utf-8")
        check("topo lista (nao dict) -> {}", dt.load_translation_cache(lista) == {})
        check("path None -> {}", dt.load_translation_cache(None) == {})


def test_snippet_en_render() -> None:
    section("T2: render — snippet EN em cache marca a traducao; sem cache, DE")
    jobs = [_job(0), _job(1)]
    cache = {"t0": {"en": "Working student role in logistics and procurement",
                    "ts": 1.0}}
    html = mp.render_minimal_html(jobs, total_eligible=2, generated_at="x",
                                  translation_cache=cache)
    check("snippet EN marcado (EN · )", "EN · Working student role" in html)
    check("snippet EN com classe de traducao", 'class="d en"' in html)
    check("vaga SEM cache mantem snippet DE como hoje",
          "Werkstudent supply chain logistics procurement" in html)
    # sem cache: identico ao render de hoje nos snippets
    html_no = mp.render_minimal_html(jobs, total_eligible=2, generated_at="x")
    check("sem cache -> nenhum marcador EN · ",
          "EN · " not in html_no)
    check("sem cache -> sem classe d en", 'class="d en"' not in html_no)
    check("cache entry para vaga fora do top: ignorada sem erro",
          mp.render_minimal_html(jobs[:1], total_eligible=2, generated_at="x",
                                 translation_cache={"zzz": {"en": "x"}})
          is not None)
    # from_file com cache em disco (caminho real da ferramenta)
    with tempfile.TemporaryDirectory(prefix="t_f12_ff_") as tmp:
        base = Path(tmp)
        (base / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        cpath = base / "translation_cache.json"
        dt.save_translation_cache(cpath, cache)
        html_ff = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=None,
            translation_cache_path=cpath)
        check("from_file le o cache do disco", "EN · Working student role" in html_ff)
        html_ff2 = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=None,
            translation_cache_path=base / "nao_existe.json")
        check("from_file com cache inexistente: snippet DE",
              "Werkstudent supply chain" in html_ff2
              and "EN · " not in html_ff2)
        html_ff3 = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=None,
            translation_cache_path=None)
        check("from_file sem translation_cache_path: pagina de hoje",
              "EN · " not in html_ff3)


# ---------------------------------------------------------------------------
# T2b — ferramenta on-demand (transport falso, SEM rede)
# ---------------------------------------------------------------------------

def test_tool_happy_path() -> None:
    section("T2b: ferramenta --top N com transport falso (SEM rede)")
    with tempfile.TemporaryDirectory(prefix="t_f12_tool_") as tmp:
        base = Path(tmp)
        jobs = [_job(i) for i in range(6)]
        jobs[2]["description"] = ""  # sem descricao -> skip honesto
        (base / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        cache_path = base / "translation_cache.json"
        fake = FakeTransport([_llm_ok("Working student role in logistics.")] * 5)
        env = {"NVIDIA_API_KEY": "test-key-abcdef123456", "PATH": "/usr/bin:/bin"}
        with mock.patch.dict(os.environ, env, clear=True):
            rc = td.main(["--input", str(base / "eligible_jobs.json"),
                          "--cache", str(cache_path),
                          "--config", str(base / "no.env"),
                          "--top", "6"],
                         transport=fake, backoff=NO_BACKOFF, sleep=lambda s: None)
        check("exit 0", rc == 0)
        check("5 chamadas ao transport (1 vaga sem descricao pulada)",
              len(fake.calls) == 5)
        loaded = dt.load_translation_cache(cache_path)
        check("5 entradas no cache", len(loaded) == 5)
        check("entrada com texto EN + ts", isinstance(loaded["t0"], dict)
              and loaded["t0"]["en"] == "Working student role in logistics."
              and loaded["t0"]["ts"] > 0)
        check("cache em disco re-le igual",
              dt.load_translation_cache(cache_path) == loaded)
        # input JSON intocado (a ferramenta so le; o original nunca sai)
        check("eligible_jobs.json intocado",
              json.loads((base / "eligible_jobs.json")
                         .read_text(encoding="utf-8")) == jobs)
        # URL/payload do padrao enrichment (mesma API, temperatura 0)
        url, headers, payload = fake.calls[0]
        check("POST no endpoint do enrichment/llm",
              "integrate.api.nvidia.com" in url)
        check("Authorization Bearer com a key",
              headers.get("Authorization") == "Bearer test-key-abcdef123456")
        check("model GLM 5.3 flash", payload["model"] == "z-ai/glm-5.3-flash")
        check("temperature 0", payload["temperature"] == 0)


def test_tool_cache_hit_and_force() -> None:
    section("T2b: cache hit pulado; --force re-traduz; --job-id seleciona")
    with tempfile.TemporaryDirectory(prefix="t_f12_hit_") as tmp:
        base = Path(tmp)
        jobs = [_job(i) for i in range(4)]
        (base / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        cache_path = base / "translation_cache.json"
        dt.save_translation_cache(cache_path, {"t0": {"en": "old", "ts": 1}})
        fake = FakeTransport([_llm_ok("nova traducao")])
        env = {"NVIDIA_API_KEY": "k", "PATH": "/usr/bin:/bin"}
        with mock.patch.dict(os.environ, env, clear=True):
            rc = td.main(["--input", str(base / "eligible_jobs.json"),
                          "--cache", str(cache_path),
                          "--config", str(base / "no.env"),
                          "--top", "1"],
                         transport=fake, backoff=NO_BACKOFF, sleep=lambda s: None)
        check("cache hit: exit 0 SEM chamar LLM", rc == 0 and len(fake.calls) == 0)
        check("cache hit: entrada antiga preservada",
              dt.load_translation_cache(cache_path)["t0"]["en"] == "old")
        # --force re-traduz
        fake2 = FakeTransport([_llm_ok("nova traducao")])
        with mock.patch.dict(os.environ, env, clear=True):
            rc2 = td.main(["--input", str(base / "eligible_jobs.json"),
                           "--cache", str(cache_path),
                           "--config", str(base / "no.env"),
                           "--top", "1", "--force"],
                          transport=fake2, backoff=NO_BACKOFF, sleep=lambda s: None)
        check("--force re-traduz (1 chamada)", rc2 == 0 and len(fake2.calls) == 1)
        check("--force atualiza o cache",
              dt.load_translation_cache(cache_path)["t0"]["en"] == "nova traducao")
        # --job-id: selecao exata (ordem de score nao importa)
        fake3 = FakeTransport([_llm_ok("trad do t2")])
        with mock.patch.dict(os.environ, env, clear=True):
            rc3 = td.main(["--input", str(base / "eligible_jobs.json"),
                           "--cache", str(cache_path),
                           "--config", str(base / "no.env"),
                           "--job-id", "t2"],
                          transport=fake3, backoff=NO_BACKOFF, sleep=lambda s: None)
        loaded3 = dt.load_translation_cache(cache_path)
        check("--job-id traduz so a pedida (1 chamada)",
              rc3 == 0 and len(fake3.calls) == 1
              and loaded3["t2"]["en"] == "trad do t2")
        check("--job-id inexistente: erro de setup",
              td.main(["--input", str(base / "eligible_jobs.json"),
                       "--cache", str(cache_path),
                       "--config", str(base / "no.env"),
                       "--job-id", "zzz"],
                      transport=FakeTransport([]),
                      backoff=NO_BACKOFF, sleep=lambda s: None) == 1)


def test_tool_retry_and_sanitize() -> None:
    section("T2b: retry 429 -> 200; nao-retryavel para; key nunca em erro")
    with tempfile.TemporaryDirectory(prefix="t_f12_retry_") as tmp:
        base = Path(tmp)
        jobs = [_job(0), _job(1)]
        (base / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        cache_path = base / "translation_cache.json"
        secret = "nvapi-secret-key-XYZW"
        # 429 depois 200: 2 tentativas na vaga 0; 400 na vaga 1: para na 1a
        fake = FakeTransport([
            (429, "{}"),
            _llm_ok("traduzido depois do 429"),
            (400, json.dumps({"error": {"message": f"bad key {secret}"}})),
        ])
        env = {"NVIDIA_API_KEY": secret, "PATH": "/usr/bin:/bin"}
        with mock.patch.dict(os.environ, env, clear=True):
            rc = td.main(["--input", str(base / "eligible_jobs.json"),
                          "--cache", str(cache_path),
                          "--config", str(base / "no.env"),
                          "--top", "2"],
                         transport=fake, backoff=NO_BACKOFF, sleep=lambda s: None)
        loaded = dt.load_translation_cache(cache_path)
        check("sucesso apos retry gravado (429 -> 200)",
              loaded["t0"]["en"] == "traduzido depois do 429")
        check("http_400 nao-retryavel: 3 chamadas no total (2+1)",
              len(fake.calls) == 3)
        check("falha nao gravada no cache", "t1" not in loaded)
        check("exit 2 quando ha falha de LLM", rc == 2)
        # sanitize: a key NUNCA aparece em erro (transport ecoando a key)
        echo_key = FakeTransport([(401, json.dumps({"msg": secret}))])
        with mock.patch.dict(os.environ, env, clear=True), \
                tempfile.TemporaryDirectory() as t2:
            err_cache = Path(t2) / "c.json"
            result, usage, latency, attempts, error, trunc = dt.translate_text(
                secret, "texto", transport=echo_key,
                backoff=NO_BACKOFF, sleep=lambda s: None)
            check("erro http_401 curto", error == "http_401")
            check("key NUNCA no erro (sanitize)", secret not in str(error))
        # corpo do prompt contem o texto (traducao), nao a key
        seen_payloads = [c[2]["messages"][0]["content"] for c in fake.calls]
        check("prompt leva o texto (TRANSLATION_PROMPT + descricao)",
              all("TEXT TO TRANSLATE" in p for p in seen_payloads)
              and all("Werkstudent supply chain" in p for p in seen_payloads))
        check("key fora do prompt", all(secret not in p for p in seen_payloads))


def test_tool_llm_output_cleaning() -> None:
    section("T2b: parse_llm_text — think-blocks/fences/preambulo descartados")
    think_open, think_close = chr(60) + "think" + chr(62), chr(47) + "think" + chr(62)
    cases = [
        ("texto puro", "texto puro"),
        (think_open + "reasoning" + think_close + "\nHola", "Hola"),
        ("```json\nnao sou json\n```", "nao sou json"),
        ("Here is the translation:\nreal text", "real text"),
        ("translation:\nreal text 2", "real text 2"),
        (think_open + "r" + think_close + "\nHere is the translation:\ncorpo", "corpo"),
    ]
    for src, want in cases:
        check(f"parse limpo {src[:24]!r}", dt.parse_llm_text(src) == want)
    check("so think-block sem corpo -> vazio (vira empty_content)",
          dt.parse_llm_text(think_open + "x" + think_close) == "")
    # entrada truncada em 12k marca truncated (aviso honesto)
    long_text = "x" * (dt.MAX_INPUT_CHARS + 100)
    trunc_transport = FakeTransport([_llm_ok("curto")])
    result, _, _, _, err, trunc = dt.translate_text(
        "k", long_text, transport=trunc_transport,
        backoff=NO_BACKOFF, sleep=lambda s: None)
    check("entrada >12k truncada sinalizada", trunc is True and err is None)
    check("entrada <=12k nao truncada",
          dt.translate_text("k", "curto", transport=FakeTransport([_llm_ok("y")]),
                            backoff=NO_BACKOFF, sleep=lambda s: None)[5] is False)


# ---------------------------------------------------------------------------
# T3 — o original nunca sai (JSON/CSV byte a byte; grafo de imports; digest)
# ---------------------------------------------------------------------------

def test_outputs_byte_identical() -> None:
    section("T3: JSON/CSV byte a byte identicos com a camada F12 exercida")
    from internship_finder.cli import save_outputs

    jobs = [
        {"id": "a|smartrecruiters:1", "title": "Praktikum Logistik",
         "company": "A GmbH", "location": "Berlin, DE", "country_iso": "de",
         "url": "https://x/1", "score": 15.0,
         "description": "Werkstudent Einkauf Beschaffung",
         "raw": {}, "posted_at": None, "visa_friendly": True},
        {"id": "b|successfactors:2", "title": "Werkstudent Produktion",
         "company": "B AG", "location": "München", "country_iso": "de",
         "url": "https://x/2", "score": 12.5,
         "description": "Lager Versand", "raw": {}, "posted_at": None},
    ]
    with tempfile.TemporaryDirectory(prefix="t_f12_bytes_") as tmp:
        out1 = Path(tmp) / "run1"
        out2 = Path(tmp) / "run2"
        for d in (out1, out2):
            d.mkdir()
        save_outputs(jobs, out1 / "eligible_jobs.json")
        # camada F12 EXERCIDA sobre os mesmos dados (display-only)
        for job in jobs:
            _ = dt.title_en(job["title"])
            _ = dt.cached_translation({"a|smartrecruiters:1":
                                       {"en": "translated", "ts": 1}},
                                      job["id"])
        save_outputs(jobs, out2 / "eligible_jobs.json")
        j1 = (out1 / "eligible_jobs.json").read_bytes()
        j2 = (out2 / "eligible_jobs.json").read_bytes()
        c1 = (out1 / "eligible_jobs.csv").read_bytes()
        c2 = (out2 / "eligible_jobs.csv").read_bytes()
        import hashlib
        check("JSON byte a byte identico (sha256)",
              hashlib.sha256(j1).hexdigest() == hashlib.sha256(j2).hexdigest())
        check("CSV byte a byte identico (sha256)",
              hashlib.sha256(c1).hexdigest() == hashlib.sha256(c2).hexdigest())
        check("descricao ORIGINAL no JSON (nunca a traducao)",
              b"Praktikum Logistik" in j1 and b"Werkstudent Einkauf" in j1)
        check("nenhum texto EN injetado no JSON",
              b"translated" not in j1)


def test_import_graph_display_only() -> None:
    section("T3: nenhum modulo do pipeline importa display_translate")
    repo = Path(__file__).resolve().parent.parent
    pipeline_modules = [
        "src/internship_finder/cli.py",
        "src/internship_finder/ranking.py",
        "src/internship_finder/dedup.py",
        "src/internship_finder/filters.py",
        "scripts/refresh_daily.py",
        "scripts/ranking_digest.py",
        "scripts/interface.py",
    ]
    offenders = []
    for rel in pipeline_modules:
        text = (repo / rel).read_text(encoding="utf-8")
        if "display_translate" in text:
            offenders.append(rel)
    check("pipeline limpo: display_translate nao importado por cli/ranking/"
          "dedup/filters/refresh/digest/interface", not offenders)
    if offenders:
        print(f"    OFFENDERS: {offenders}")


def test_digest_not_translated() -> None:
    section("T3: digest NAO traduz — titulos originais, sem marcador EN")
    import ranking_digest as rg
    jobs = [_job(0, title="Praktikum Logistik", score=15.0),
            _job(1, title="Werkstudent Beschaffung", score=14.0)]
    text = rg.format_top5(jobs)  # devolve str unica (contrato F6)
    check("digest mantem titulo DE original", "Praktikum Logistik" in text)
    check("digest sem linha EN", "EN: " not in text and "EN · " not in text)
    check("digest sem 'Internship Logistics'",
          "Internship Logistics" not in text)
    with tempfile.TemporaryDirectory(prefix="t_f12_dg_") as tmp:
        base = Path(tmp)
        (base / "cur.json").write_text(json.dumps(jobs), encoding="utf-8")
        (base / "prev.json").write_text(json.dumps([]), encoding="utf-8")
        sections = rg.digest_sections(base / "cur.json", base / "prev.json",
                                      pages_url="https://x/")
        joined = "\n".join(sections or [])
        check("digest_sections tambem sem traducao",
              "Internship Logistics" not in joined and "EN: " not in joined)


# ---------------------------------------------------------------------------
# T5 — fallback offline (sem NVIDIA_API_KEY nada quebra)
# ---------------------------------------------------------------------------

def test_tool_no_env_graceful() -> None:
    section("T5: sem NVIDIA_API_KEY — falha graciosa, NADA gravado")
    with tempfile.TemporaryDirectory(prefix="t_f12_noenv_") as tmp:
        base = Path(tmp)
        jobs = [_job(0), _job(1)]
        (base / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        cache_path = base / "translation_cache.json"
        fake = FakeTransport([])
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
            rc = td.main(["--input", str(base / "eligible_jobs.json"),
                          "--cache", str(cache_path),
                          "--config", str(base / "no.env"),  # .env ausente
                          "--top", "2"],
                         transport=fake, backoff=NO_BACKOFF, sleep=lambda s: None)
        check("exit 1 (setup), mensagem clara", rc == 1)
        check("NENHUMA chamada de LLM", len(fake.calls) == 0)
        check("cache nao criado", not cache_path.exists())
        # com .env ausente e env limpa, a chave da maquina nao vaza p/ teste


def test_offline_layers_survive_without_env() -> None:
    section("T5: titulos por dicionario + glossario seguem OFFLINE (sem env)")
    code = (
        "import sys; sys.path.insert(0, {src!r}); sys.path.insert(0, {scripts!r});\n"
        "import os\n"
        "assert 'NVIDIA_API_KEY' not in os.environ, 'env deveria estar limpa'\n"
        "from internship_finder.display_translate import title_en\n"
        "import minimal_page as mp\n"
        "assert title_en('Praktikum Logistik') == 'Internship Logistics'\n"
        "html = mp.render_minimal_html([], total_eligible=0, generated_at='x')\n"
        "assert 'Glossário DE→EN:' in html\n"
        "print('OFFLINE_OK')\n"
    ).format(src=str(Path(__file__).resolve().parent.parent / "src"),
             scripts=str(Path(__file__).resolve().parent))
    env = {"PATH": "/usr/bin:/bin"}
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=60, env=env)
    check("dicionario + glossario funcionam sem env (subprocesso limpo)",
          "OFFLINE_OK" in proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr[-600:])


def test_render_without_cache_identical_today() -> None:
    section("T5: render sem cache = pagina de hoje (snippets DE, nada quebra)")
    jobs = [_job(0), _job(1)]
    html_none = mp.render_minimal_html(jobs, total_eligible=2,
                                       generated_at="x")
    html_empty = mp.render_minimal_html(jobs, total_eligible=2,
                                        generated_at="x",
                                        translation_cache={})
    check("cache None == cache {} (nenhum efeito)",
          html_none == html_empty)
    check("snippets DE como hoje",
          "Werkstudent supply chain logistics procurement" in html_none)
    check("contratos F11 vivos: data-de", 'data-de="' in html_none)
    check("contratos F11 vivos: data-iso", 'data-iso="de"' in html_none)
    check("contratos F11 vivos: data-vf", 'data-vf="0"' in html_none)


def test_size_budget() -> None:
    section("T4/T5: tamanho — linha EN + glossario dentro do alvo/cap")
    jobs = [_job(i) for i in range(100)]
    for j in jobs:
        j["description"] = ("Werkstudent supply chain logistik beschaffung "
                            "procurement SAP Excel " * 12)
    html = mp.render_minimal_html(jobs, total_eligible=2456,
                                  generated_at="2026-10-05 09:32")
    size = len(html.encode("utf-8"))
    check("100 cards principais",
          html.split('<ol id="list">')[1].split("</ol>")[0]
          .count("<li class=") == 100)
    check(f"tamanho {size} <= 100 KB (alvo)", size <= mp.PAGE_TARGET_BYTES)
    check(f"tamanho {size} < 150 KB (cap duro)", size < mp.PAGE_HARD_CAP_BYTES)
    check("100 linhas EN + nenhuma a mais",
          html.count('class="en">EN:') == 100)
    check("gate check_public_safe aprova (nenhum segredo)",
          pp.check_public_safe(html) == [])
    # cache EN completo nos 100: snippet EN entra, ainda dentro do cap
    cache = {f"t{i}": {"en": "Working student in logistics, procurement and "
                             "supply chain with SAP and Excel. " * 3,
                       "ts": 1.0} for i in range(100)}
    html_cache = mp.render_minimal_html(jobs, total_eligible=2456,
                                        generated_at="x",
                                        translation_cache=cache)
    size_cache = len(html_cache.encode("utf-8"))
    check("com cache EN: marcadores EN · presentes",
          html_cache.count("EN · ") == 100)
    check(f"com cache EN: {size_cache} < 150 KB (cap duro)",
          size_cache < mp.PAGE_HARD_CAP_BYTES)
    check("com cache EN: gate aprova", pp.check_public_safe(html_cache) == [])
    # degradacao size-aware (F11) segue: remonta sem snippets (EN junto)
    html_no_snip = mp.render_minimal_html(jobs, total_eligible=2456,
                                           generated_at="x",
                                           translation_cache=cache,
                                           with_snippets=False)
    check("sem snippets: sem marcador EN · (traducao vive no snippet)",
          "EN · " not in html_no_snip)
    check("sem snippets: linhas EN do TITULO permanecem (offline)",
          html_no_snip.count('class="en">EN:') == 100)
    check("sem snippets: glossario permanece",
          "Glossário DE→EN:" in html_no_snip)


def main() -> None:
    test_title_en_dictionary()
    test_title_en_edge_cases()
    test_title_line_in_card()
    test_glossary_footer()
    test_cache_roundtrip()
    test_cache_corrupt_graceful()
    test_snippet_en_render()
    test_tool_happy_path()
    test_tool_cache_hit_and_force()
    test_tool_retry_and_sanitize()
    test_tool_llm_output_cleaning()
    test_outputs_byte_identical()
    test_import_graph_display_only()
    test_digest_not_translated()
    test_tool_no_env_graceful()
    test_offline_layers_survive_without_env()
    test_render_without_cache_identical_today()
    test_size_budget()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()
