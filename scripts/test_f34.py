#!/usr/bin/env python3
"""Testes da Fase F34 — apply-assist sob demanda (100% offline, FakeTransport).

Trava o contrato do CLI scripts/apply_assist.py (test_f34, 68ª suíte — entra
no CI):

GRUPO A — Contrato do CLI (offline, LLM falso):
  A1. --job-id inexistente -> SystemExit com erro claro (nada gerado).
  A2. input ausente / perfil ausente -> SystemExit com erro claro.
  A3. NVIDIA_API_KEY ausente -> SystemExit "nada parcial silencioso".

GRUPO B — Outputs no path gitignored (FakeLLMTransport, 2 chamadas):
  B1. Sucesso: 4 arquivos em <output>/<job-id>/ (cover_letter.md,
      keyword_gap.md, interview_briefing.md, visa_facts.md).
  B2. cover_letter.md com header literal 'DRAFT — revisar antes de enviar'
      + estrutura comercial alemã (saudação, 3 parágrafos, fecho, nome) +
      placeholders de conferência.
  B3. keyword_gap.md determinístico: skill da JD presente no perfil em
      "Presentes", skill da JD sem evidência em "GAPS" (mesma vaga+perfil
      -> mesma saída, determinismo).
  B4. interview_briefing.md: 8–12 perguntas com kind + skeleton STAR;
      pergunta com [FALTA: ...] passa como está (anti-invenção sinaliza).
  B5. visa_facts.md: frases jurídicas aprovadas LITERAIS (substring
      asserts) e ESTÁTICO (não vem da LLM — payload da LLM nunca contém
      o texto de visto além do que o perfil fornece; o arquivo é byte a
      byte a constante em qualquer execução).
  B6. --lang de: prompt da carta instrui alemão; markdown declara revisão.
  B7. LLM devolve JSON incompleto (parágrafo vazio) -> SystemExit, ZERO
      arquivos escritos (nada parcial silencioso).
  B8. LLM devolve questions com 3 itens (< 8) -> SystemExit, ZERO arquivos.

GRUPO C — Falha de API (retry esgotado):
  C1. Transport devolve 429 nas 3 tentativas -> SystemExit com contagem
      de tentativas + erro; ZERO arquivos escritos.
  C2. Primeira chamada OK, segunda falha -> SystemExit; ZERO arquivos
      (o arquivo da primeira NÃO é escrito — sem parcial silencioso).

GRUPO D — Invariante ZERO REDE além da API LLM:
  D1. O módulo apply_assist NÃO importa/encontra nenhuma lib de envio
      (requests é usado só via cliente llm; nenhum smtplib/telegram/
      webhook/form-post no código).
  D2. Execução inteira com socket.socket.connect bloqueado: tudo passa
      (FakeTransport nunca toca rede; qualquer socket externo falha a
      suíte) e o único destino de POST é o endpoint da API LLM.
  D3. Nenhum caminho fora de <output> é escrito (produção data/ das
      vagas intocada; outputs só em data/personal/apply_assist — path
      gitignored: 'data/' no .gitignore).

Uso:  .venv/bin/python scripts/test_f34.py
"""

from __future__ import annotations

import http.client
import json
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import apply_assist  # noqa: E402
from internship_finder.enrichment import llm  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures (sintéticas — nenhum dado pessoal real aqui)
# ---------------------------------------------------------------------------

FAKE_KEY = "fake-key-DO-NOT-LEAK-1234567890"

JOB_ID = "TestGmbH|smartrecruiters:TestGmbH:999"

JOB = {
    "id": JOB_ID,
    "title": "Praktikum Procurement Analytics (m/w/d)",
    "company": "TestGmbH",
    "location": "Stuttgart, BW, de",
    "country": "de",
    "url": "https://jobs.example.com/TestGmbH/999",
    "description": (
        "Deine Aufgaben: Du unterstützt das Einkaufsteam bei der Analyse von "
        "Beschaffungsdaten mit Python und Power BI und erstellst Dashboards "
        "für das Lieferantenmanagement. Außerdem automatisierst du "
        "Reporting-Prozesse und arbeitest mit SAP und SQL. Voraussetzungen: "
        "Studium der Wirtschaftswissenschaften oder Ingenieurwissenschaften, "
        "Excel-Kenntnisse, sehr gute Deutschkenntnisse und Englisch. "
        "Erfahrung mit Tableau ist ein Plus."
    ),
}

PROFILE_TEXT = """# PERFIL-CANDIDATO (fixture sintética)

- Python (scripting, análise de dados).
- Power BI + DAX (modelagem, medidas, dashboards).
- SQL / SQLite (dedup e queries do pipeline).
- Excel, Power Query, Git, GitHub Actions (CI).
- Procurement: gestão de inventário e fornecedores (prática familiar
  2019–2024), curva ABC / Pareto de fornecedores, sourcing.
- Inglês fluente; alemão básico A1–A2 em progresso.
- Estatística; Comunicação com stakeholder; reporting de KPI.
"""

LETTER_JSON = {
    "salutation": "Sehr geehrte Damen und Herren,",
    "paragraph_1": "Mit großem Interesse habe ich die Stelle gesehen.",
    "paragraph_2": "Ich studiere Werkstoffkunde und arbeite mit Python.",
    "paragraph_3": "Verfügbar ab Januar 2027; Englisch Arbeitssprache.",
    "closing": "Mit freundlichen Grüßen",
    "contact_name": "Test Kandidat",
    "contact_block": "Test Kandidat\nStraße 1, Stadt",
    "subject_line": "Bewerbung um ein Praktikum als Procurement Analytics",
}

QUESTIONS_JSON = [
    {
        "question": "Wie würdest du Beschaffungsdaten analysieren?",
        "kind": "technical",
        "star_skeleton": "Point to: procurement analytics dashboard (Power BI/DAX).",
    },
    {
        "question": "Erzähl von einer Situation mit Lieferantenproblemen.",
        "kind": "behavioral",
        "star_skeleton": "[FALTA: descrever situação real de fornecedor]",
    },
] + [
    {
        "question": f"Frage {i} aus der JD",
        "kind": "technical" if i % 2 else "behavioral",
        "star_skeleton": f"Skeleton {i} apontando para o perfil.",
    }
    for i in range(3, 11)  # total 10 perguntas
]


class FakeLLMTransport:
    """Transport falso (padrão test_enrichment.py): fila de respostas .post."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.posts: list[dict] = []

    def post(self, url, headers, payload, timeout):
        self.posts.append({"url": url, "headers": headers, "payload": payload})
        if not self.responses:
            raise AssertionError("respostas esgotadas no FakeLLMTransport")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        return status, body

    def get(self, url, headers, timeout):
        raise AssertionError("apply_assist não deve fazer GET na suíte")


def llm_body(content: str) -> str:
    return json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }
    )


def ok_responses() -> list:
    """Fila feliz: chamada 1 (carta) + chamada 2 (briefing)."""
    return [
        (200, llm_body(json.dumps(LETTER_JSON))),
        (200, llm_body(json.dumps({"questions": QUESTIONS_JSON}))),
    ]


# ---------------------------------------------------------------------------
# Helpers de execução do CLI com fakes
# ---------------------------------------------------------------------------


def run_cli(
    job_id: str,
    tmp: Path,
    responses=None,
    lang: str | None = None,
    key: str = FAKE_KEY,
    exit_ok: bool = False,
):
    """Roda apply_assist.main com input/perfil/output em tmp e LLM falso.

    O FakeLLMTransport é injetado nas duas chamadas LLM via monkeypatch dos
    construtores run_cover_letter/run_interview_briefing (padrão: trocar o
    transporte default do cliente llm.extract SEM tocar a rede).
    """
    input_path = tmp / "input.json"
    input_path.write_text(json.dumps([JOB]), encoding="utf-8")
    profile_path = tmp / "PERFIL.md"
    profile_path.write_text(PROFILE_TEXT, encoding="utf-8")
    out_root = tmp / "out"

    argv = [
        "--job-id", job_id,
        "--input", str(input_path),
        "--profile", str(profile_path),
        "--output", str(out_root),
    ]
    if lang:
        argv += ["--lang", lang]

    transport = FakeLLMTransport(responses or ok_responses())
    env_key = {"NVIDIA_API_KEY": key} if key else {}
    code = None

    real_extract = apply_assist.llm.extract

    def _extract(key_, prompt, **kw):
        if kw.get("transport") is None:
            kw["transport"] = transport
        if not kw.get("backoff") or kw["backoff"] == llm.DEFAULT_BACKOFF_S:
            kw["backoff"] = (0, 0)
        return real_extract(key_, prompt, **kw)

    with patch.dict("os.environ", env_key, clear=False):
        with patch.object(apply_assist.llm, "extract", side_effect=_extract):
            try:
                code = apply_assist.main(argv)
            except SystemExit as exc:
                code = exc.code
    return code, transport, out_root / job_id


def main() -> int:
    section("A. Contrato do CLI (offline)")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # A1: job-id inexistente
        code, _t, out = run_cli("NaoExiste|x:1", tmp)
        check("A1. job-id inexistente -> SystemExit != 0", code not in (0, None),
              f"code={code}")
        check("A1b. nenhum arquivo escrito", not out.exists())

        # A2: input ausente
        argv = ["--job-id", JOB_ID, "--input", str(tmp / "missing.json"),
                "--profile", str(tmp / "p.md"), "--output", str(tmp / "o")]
        try:
            code = apply_assist.main(argv)
        except SystemExit as exc:
            code = exc.code
        check("A2. input ausente -> SystemExit != 0", code not in (0, None),
              f"code={code}")

        # A2b: perfil ausente
        (tmp / "in.json").write_text(json.dumps([JOB]), encoding="utf-8")
        argv = ["--job-id", JOB_ID, "--input", str(tmp / "in.json"),
                "--profile", str(tmp / "nope.md"), "--output", str(tmp / "o")]
        with patch.dict("os.environ", {"NVIDIA_API_KEY": FAKE_KEY}, clear=False):
            try:
                code = apply_assist.main(argv)
            except SystemExit as exc:
                code = exc.code
        check("A2b. perfil ausente -> SystemExit != 0", code not in (0, None))

        # A3: sem key
        with patch.dict("os.environ", {}, clear=False):
            with patch.dict("os.environ", {"NVIDIA_API_KEY": ""}, clear=False):
                argv = ["--job-id", JOB_ID,
                        "--input", str(tmp / "in.json"),
                        "--profile", "x", "--output", str(tmp / "o")]
                try:
                    code = apply_assist.main(argv)
                except SystemExit as exc:
                    code = exc.code
        check("A3. NVIDIA_API_KEY ausente -> SystemExit != 0",
              code not in (0, None))

    section("B. Outputs no path gitignored (FakeLLMTransport)")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        code, transport, out_dir = run_cli(JOB_ID, tmp)
        check("B1a. execução feliz termina 0", code == 0, f"code={code}")
        names = sorted(p.name for p in out_dir.iterdir()) if out_dir.exists() else []
        check("B1b. 4 arquivos em <output>/<job-id>/",
              names == ["cover_letter.md", "interview_briefing.md",
                        "keyword_gap.md", "visa_facts.md"], f"{names}")

        letter = (out_dir / "cover_letter.md").read_text(encoding="utf-8")
        check("B2a. header literal 'DRAFT — revisar antes de enviar'",
              apply_assist.DRAFT_HEADER in letter)
        check("B2b. saudação comercial presente",
              "Sehr geehrte Damen und Herren," in letter)
        check("B2c. 3 parágrafos + fecho + nome",
              all(s in letter for s in (LETTER_JSON["paragraph_1"],
                                        LETTER_JSON["paragraph_2"],
                                        LETTER_JSON["paragraph_3"],
                                        LETTER_JSON["closing"],
                                        LETTER_JSON["contact_name"])))
        check("B2d. placeholders de conferência ([DATA] / [CIDADE-EMPRESA])",
              "[DATA]" in letter and "[CIDADE-EMPRESA]" in letter)

        gap = (out_dir / "keyword_gap.md").read_text(encoding="utf-8")
        check("B3a. skill presente (Python) listada",
              "- Python" in gap)
        gap_sec = gap.split("## GAPS")[1]
        gaps_listed = [ln[2:] for ln in gap_sec.splitlines()
                       if ln.startswith("- ")]
        check("B3b. GAPS listadas com variante da JD",
              any("SAP" in g for g in gaps_listed),
              f"{gaps_listed}")
        check("B3b2. presente na JD e no perfil NÃO vira gap",
              not any("KPI" in g or "Power BI" in g for g in gaps_listed))
        check("B3c. German Language NÃO é gap (regra A1–A2 honesta)",
              "German Language" not in gap.split("## GAPS")[1].split("## Notas")[0])
        # determinismo: mesma vaga+perfil -> mesma saída
        with tempfile.TemporaryDirectory() as td2:
            tmp2 = Path(td2)
            _c2, _t2, out2 = run_cli(JOB_ID, tmp2)
            gap2 = (out2 / "keyword_gap.md").read_text(encoding="utf-8")
            check("B3d. keyword_gap determinístico (byte a byte)", gap == gap2)

        briefing = (out_dir / "interview_briefing.md").read_text(encoding="utf-8")
        q_headers = [ln for ln in briefing.splitlines()
                     if ln.startswith("## ") and ln[3:4].isdigit()]
        check("B4a. 8–12 perguntas numeradas", 8 <= len(q_headers) <= 12,
              f"{len(q_headers)}")
        check("B4b. kinds technical/behavioral marcados",
              "[technical]" in briefing and "[behavioral]" in briefing)
        check("B4c. skeleton com [FALTA: ...] preservado",
              "[FALTA:" in briefing)
        check("B4d. título da vaga no briefing",
              JOB["title"][:20] in briefing)

        visa = (out_dir / "visa_facts.md").read_text(encoding="utf-8")
        for frase in (
            "duração máxima de 6 meses (AufenthG §16e Abs. 2)",
            "BeschV §15 Nr. 1",
            "NÃO exige Zustimmung da Bundesagentur für Arbeit",
            "confirmar procedimento atualizado com consulado/Ausländerbehörde",
            "Pflichtpraktikum é isento do salário mínimo por lei",
            "freiwilliges Praktikum tem piso de €13,90/h (2026)",
            "Werkstudent é categoria contratual DIFERENTE do §16e",
            "Ofertas >6 meses não cabem no §16e",
            "BeschV §15 Nr. 6, até 1 ano durante estudo em universidade estrangeira após o 4º semestre",
            "exige verificação prévia com as autoridades",
        ):
            check(f"B5. frase literal: {frase[:45]}…", frase in visa)
        check("B5b. visa_facts byte a byte a constante (ESTÁTICO, sem LLM)",
              visa == apply_assist.VISA_FACTS_TEXT)

        # B6: --lang de
        code6, transport6, out6 = run_cli(JOB_ID, tmp, lang="de")
        letter6 = (out6 / "cover_letter.md").read_text(encoding="utf-8")
        prompt6 = transport6.posts[0]["payload"]["messages"][0]["content"]
        check("B6a. --lang de: prompt instrui alemão",
              "German (Deutsch)" in prompt6)
        check("B6b. --lang de: markdown declara revisão de alemão",
              "ALEMÃO formal" in letter6)
        check("B6c. 2 chamadas LLM por execução",
              len(transport.posts) == 2, f"posts={len(transport.posts)}")
        check("B6d. destino único das chamadas = endpoint LLM",
              all(p["url"] == llm.CHAT_COMPLETIONS_URL for p in transport.posts))

    section("C. Falha de API (retry esgotado / JSON inválido)")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # C1: 429 em todas as tentativas (fila repete a última)
        code, _t, out = run_cli(
            JOB_ID, tmp,
            responses=[(429, json.dumps({"error": "rate"}))] * 3,
        )
        check("C1a. 429 x3 -> SystemExit != 0", code not in (0, None))
        check("C1b. ZERO arquivos escritos", not out.exists())

        # C2: primeira chamada OK, segunda falha 429 x3
        responses = ok_responses()[:1] + [(429, "{}")] * 3
        code, _t, out = run_cli(JOB_ID, tmp, responses=responses)
        check("C2a. 2ª chamada falha -> SystemExit != 0", code not in (0, None))
        check("C2b. ZERO arquivos (sem parcial silencioso)", not out.exists())

        # B7: JSON incompleto da carta (parágrafo vazio)
        broken = dict(LETTER_JSON)
        broken["paragraph_2"] = ""
        code, _t, out = run_cli(
            JOB_ID, tmp, responses=[(200, llm_body(json.dumps(broken)))]
        )
        check("B7a. carta incompleta -> SystemExit != 0", code not in (0, None))
        check("B7b. ZERO arquivos escritos", not out.exists())

        # B8: questions com 3 itens
        code, _t, out = run_cli(
            JOB_ID, tmp,
            responses=[(200, llm_body(json.dumps(LETTER_JSON))),
                       (200, llm_body(json.dumps(
                           {"questions": QUESTIONS_JSON[:3]})))],
        )
        check("B8a. questions < 8 -> SystemExit != 0", code not in (0, None))
        check("B8b. ZERO arquivos escritos", not out.exists())

    section("D. Invariante ZERO REDE além da API LLM")

    # D1: nenhuma lib de envio no módulo
    src = Path(apply_assist.__file__).read_text(encoding="utf-8")
    for banned in ("smtplib", "telegram", "webhook", "smtp", "sendmail",
                   "api.telegram.org", "urllib.request"):
        check(f"D1. '{banned}' ausente no apply_assist.py",
              banned not in src)

    # D2: execução inteira com socket bloqueado — tudo passa offline
    blocked: list[str] = []

    def _fail_connect(self, address):  # noqa: ANN001
        blocked.append(str(address))
        raise OSError("socket externo bloqueado pela suíte F34")

    orig_connect = socket.socket.connect
    orig_urlopen = None
    try:
        import urllib.request

        orig_urlopen = urllib.request.urlopen

        def _fail_open(*_a, **_kw):
            blocked.append("urlopen")
            raise OSError("urlopen bloqueado pela suíte F34")

        urllib.request.urlopen = _fail_open  # type: ignore[assignment]
    except ImportError:
        pass
    socket.socket.connect = _fail_connect  # type: ignore[method-assign]

    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            code, _t, out = run_cli(JOB_ID, tmp)
            check("D2a. execução com sockets bloqueados termina 0",
                  code == 0, f"code={code}")
            check("D2b. nenhum socket externo tentado", blocked == [],
                  f"blocked={blocked[:3]}")
    finally:
        socket.socket.connect = orig_connect  # type: ignore[method-assign]
        if orig_urlopen is not None:
            urllib.request.urlopen = orig_urlopen  # type: ignore[assignment]

    # D3: outputs SÓ no path <output> (gitignored); data/ de produção intocado
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _c, _t, out_dir = run_cli(JOB_ID, tmp)
        written = [p for p in tmp.rglob("*") if p.is_file()]
        outside = [p for p in written if not str(p).startswith(str(out_dir))
                   and p.name not in ("input.json", "PERFIL.md")]
        check("D3a. nada escrito fora de <output>/<job-id>/ (e inputs)",
              outside == [], f"outside={[str(p) for p in outside]}")
        gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
        gi = gitignore.read_text(encoding="utf-8")
        check("D3b. 'data/' no .gitignore cobre o output default",
              any(ln.strip() == "data/" for ln in gi.splitlines()))
        check("D3c. http.client não usado pelo módulo",
              "http.client" not in src and "HTTPConnection" not in src)

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print(f"OK — test_f34: {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
