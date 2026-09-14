"""Testes standalone — escrita ATOMICA dos JSONs finais (jobs.json / eligible_jobs.json).

Prova a propriedade da tarefa "JSON nao atomico" (save_outputs):

1. **Escrita normal** — JSON valido e byte-a-byte identico ao comportamento
   atual (mesmos parametros de ``json.dump``: ``ensure_ascii=False``,
   ``indent=2``); CSV segue no mesmos contrato; modo do arquivo novo respeita
   o umask (como ``open("w")``); nenhum temporario sobra.
2. **Falha durante a geracao/escrita** — ``json.dump`` levantando ``OSError``
   (simula disco cheio/erro de I/O no meio da serializacao): o JSON final
   existente permanece valido e BYTE-A-BYTE inalterado; nenhum JSON parcial e
   deixado; o CSV (etapa posterior) nao e tocado; o temporario e removido.
3. **Falha na substituicao** — ``os.replace`` levantando ``OSError``: o final
   continua sendo o arquivo valido anterior; temporario removido.
4. **Substituicao normal** — escrita bem-sucedida substitui o anterior
   integralmente (conteudo novo, JSON valido) e preserva o modo do arquivo.
5. **Interacao com a rotacao do refresh_daily** — ``rotate()`` REAL antes de
   uma geracao que falha: o ultimo output valido continua em ``data/`` (nao
   truncado) E no archive; nenhum temporario abandonado.

As falhas sao injetadas nos pontos reais da implementacao (``json.dump`` /
``os.replace`` do proprio helper), nao num mock do helper inteiro — os testes
exercitam a propriedade que queremos garantir.

CSV (mesma propriedade, desde 14/09): o CSV (derivado do JSON) tambem e
escrito atomicamente via ``_write_atomic``. Blocos 6-10:

6. **Escrita normal do CSV** — arquivo valido, parseavel, com o conteudo
   esperado (header = ``CSV_COLUMNS``, linhas na mesma ordem dos dados) e sem
   temporarios residuais.
7. **Falha durante a escrita do CSV** — ``csv.DictWriter.writerow`` levantando
   ``OSError`` (disco cheio no meio da serializacao tabular): o CSV final
   existente permanece INALTERADO BYTE A BYTE; o temporario e removido.
8. **Falha na substituicao do CSV** — ``os.replace`` levantando ``OSError``
   somente para o destino ``.csv`` (o JSON nao falha): CSV final anterior
   preservado; temporario removido.
9. **Substituicao normal do CSV** — escrita bem-sucedida substitui o anterior
   integralmente (conteudo novo, parseavel) e preserva o modo do arquivo.
10. **JSON continua atomico** — garantia de nao-regressao: com o CSV agora
    atômico, uma falha no dump do JSON ainda deixa o JSON anterior intacto e
    nao toca o CSV.

Nao depende de ``data/`` nem de rede; usa ``tempfile`` e limpa ao final.
Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_atomic_outputs.py
"""

from __future__ import annotations

import csv
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import refresh_daily  # noqa: E402 (rotate real, para o bloco 5)
from internship_finder.cli import CSV_COLUMNS, save_outputs  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def tmp_leftovers(directory: Path, output: Path) -> list[Path]:
    """Temporarios do padrao ``.{output.name}.*.tmp`` deixados para tras."""
    return sorted(
        p for p in directory.iterdir()
        if p.name.startswith(f".{output.name}.") and p.name.endswith(".tmp")
    )


def sample_jobs() -> list[dict]:
    """Dicts com unicode/collections aninhados para prender os bytes do JSON."""
    return [
        {"id": "sf:1", "source": "successfactors:jobs", "title": "Werkstudent Logistik (m/w/d) — München",
         "company": "ZF", "url": "https://jobs.zf.example/1", "country_iso": "de",
         "collected_at": "2026-09-11T06:00:00+00:00", "score": 6.0,
         "score_breakdown": {"area": 1.0, "lang": {"de": 0.5, "en": 0.5}}},
        {"id": "smartrecruiters:acme:2", "source": "smartrecruiters:acme",
         "title": "Intern Supply Chain — Stuttgart", "company": "Acme",
         "url": "https://acme.example/job/2", "remote": True,
         "collected_at": "2026-09-11T06:00:00+00:00"},
    ]


def test_normal_write() -> None:
    print("== 1. Escrita normal: JSON identico ao comportamento atual ==")
    jobs = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        save_outputs(jobs, out)

        expected = json.dumps(jobs, ensure_ascii=False, indent=2).encode("utf-8")
        check("JSON byte-a-byte identico ao formato atual (dump/dumps arg iguais)",
              out.read_bytes() == expected)
        check("JSON valido (roundtrip)", json.loads(out.read_text(encoding="utf-8")) == jobs)
        check("CSV continua sendo gravado ao lado", out.with_suffix(".csv").exists())
        check("sem temporarios apos sucesso", tmp_leftovers(base, out) == [])

        # Arquivo novo imita open("w"): 0666 & umask.
        control = base / "control_w"
        with control.open("w", encoding="utf-8"):
            pass
        check("arquivo novo com modo padrao do open('w') (umask)",
              stat.S_IMODE(out.stat().st_mode) == stat.S_IMODE(control.stat().st_mode))


def test_failure_during_dump() -> None:
    print("== 2. Falha durante a geracao/escrita do JSON ==")
    old = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        out.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        csv_path = out.with_suffix(".csv")
        csv_path.write_text("id,title\nsf:1,Werkstudent\n", encoding="utf-8")
        before_json = out.read_bytes()
        before_csv = csv_path.read_bytes()

        raised = False
        with patch.object(__import__("json"), "dump",
                          side_effect=OSError("disk full")):
            try:
                save_outputs([{"id": "novo"}], out)
            except OSError:
                raised = True
        check("falha de escrita propaga ao chamador", raised)
        check("JSON final existente inalterado (mesmos bytes)", out.read_bytes() == before_json)
        check("JSON final continua valido (sem truncamento)",
              json.loads(out.read_text(encoding="utf-8")) == old)
        check("CSV (etapa posterior) nao foi tocado", csv_path.read_bytes() == before_csv)
        check("nenhum temporario abandonado apos falha", tmp_leftovers(base, out) == [])


def test_failure_during_replace() -> None:
    print("== 3. Falha na substituicao (os.replace) ==")
    old = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        out.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        before_json = out.read_bytes()

        raised = False
        with patch.object(os, "replace", side_effect=OSError("rename failed")):
            try:
                save_outputs([{"id": "novo"}], out)
            except OSError:
                raised = True
        check("falha na substituicao propaga ao chamador", raised)
        check("JSON final existente inalterado (mesmos bytes)", out.read_bytes() == before_json)
        check("JSON final continua valido (sem truncamento)",
              json.loads(out.read_text(encoding="utf-8")) == old)
        check("nenhum temporario abandonado apos falha", tmp_leftovers(base, out) == [])


def test_replace_success() -> None:
    print("== 4. Substituicao: novo conteudo assume o lugar do anterior ==")
    old = [{"id": "antigo", "title": "ALT"}]
    new = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        out.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        os.chmod(out, 0o640)

        save_outputs(new, out)

        check("JSON novo substitui o anterior integralmente",
              json.loads(out.read_text(encoding="utf-8")) == new)
        check("modo do arquivo anterior preservado na substituicao",
              stat.S_IMODE(out.stat().st_mode) == 0o640)
        check("sem temporarios apos sucesso", tmp_leftovers(base, out) == [])


def test_rotation_interaction() -> None:
    print("== 5. Interacao com a rotacao: falha na geracao preserva o ultimo valido ==")
    old = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        data_dir = base / "data"
        data_dir.mkdir()
        (data_dir / "jobs.json").write_text(json.dumps(old, ensure_ascii=False),
                                            encoding="utf-8")
        archive_root = data_dir / "archive"
        ts = "20260911T000000Z"

        # Sequencia real do refresh: rotacao PRIMEIRO (backup do snapshot),
        # depois a geracao — que falha aqui.
        archive_dir = refresh_daily.rotate(data_dir, archive_root, ts)
        check("rotacao arquivou o snapshot anterior",
              (archive_dir / "jobs.json").exists())

        raised = False
        with patch.object(__import__("json"), "dump",
                          side_effect=OSError("disk full")):
            try:
                save_outputs([{"id": "novo"}], data_dir / "jobs.json")
            except OSError:
                raised = True
        check("falha de escrita propaga ao chamador", raised)

        current = json.loads((data_dir / "jobs.json").read_text(encoding="utf-8"))
        archived = json.loads((archive_dir / "jobs.json").read_text(encoding="utf-8"))
        check("data/jobs.json segue sendo o ultimo output valido (nao truncado)",
              current == old)
        check("archive preserva a copia do ultimo output valido", archived == old)
        check("nenhum temporario abandonado apos falha",
              tmp_leftovers(data_dir, data_dir / "jobs.json") == [])


def test_csv_normal_write() -> None:
    print("== 6. CSV: escrita normal produz CSV valido e no formato esperado ==")
    jobs = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        save_outputs(jobs, out)
        csv_path = out.with_suffix(".csv")

        check("CSV existe apos escrita normal", csv_path.exists())
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        check("CSV parseavel (DictReader)", len(rows) == len(jobs))
        check("header CSV == CSV_COLUMNS",
              list(rows[0].keys()) == CSV_COLUMNS)
        check("linhas na mesma ordem dos dados",
              [r["id"] for r in rows] == [j["id"] for j in jobs])
        check("conteudo de uma celula preservado (title unicode)",
              rows[0]["title"] == jobs[0]["title"])
        check("conteudo de uma celula preservado (score)",
              rows[0]["score"] == "6.0")
        check("sem temporarios apos sucesso no CSV",
              tmp_leftovers(base, csv_path) == [])


def test_csv_failure_during_write() -> None:
    print("== 7. CSV: falha durante a escrita preserva o anterior byte a byte ==")
    old = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        save_outputs(old, out)
        csv_path = out.with_suffix(".csv")
        before_csv = csv_path.read_bytes()

        raised = False
        with patch.object(csv.DictWriter, "writerow",
                          side_effect=OSError("disk full")):
            try:
                save_outputs([{"id": "novo", "title": "N"}], out)
            except OSError:
                raised = True
        check("falha de escrita do CSV propaga ao chamador", raised)
        check("CSV final existente inalterado (mesmos bytes)",
              csv_path.read_bytes() == before_csv)
        check("JSON segue escrito (etapa anterior concluiu)",
              json.loads(out.read_text(encoding="utf-8")) ==
              [{"id": "novo", "title": "N"}])
        check("nenhum temporario CSV abandonado apos falha",
              tmp_leftovers(base, csv_path) == [])
        check("sem temporarios JSON residuais",
              tmp_leftovers(base, out) == [])
        check("bytes do CSV anterior preservados integralmente",
              before_csv != b"")


def test_csv_failure_during_replace() -> None:
    print("== 8. CSV: falha na substituicao (os.replace) preserva o anterior ==")
    old = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        save_outputs(old, out)
        csv_path = out.with_suffix(".csv")
        before_csv = csv_path.read_bytes()

        real_replace = os.replace

        def _fail_csv_replace(src, dst):
            # Falha SOMENTE no destino .csv; o JSON substitui normalmente.
            if str(dst).endswith(".csv"):
                raise OSError("rename failed")
            real_replace(src, dst)

        raised = False
        with patch.object(os, "replace", side_effect=_fail_csv_replace):
            try:
                save_outputs([{"id": "novo", "title": "N"}], out)
            except OSError:
                raised = True
        check("falha na substituicao do CSV propaga ao chamador", raised)
        check("CSV final existente inalterado (mesmos bytes)",
              csv_path.read_bytes() == before_csv)
        check("JSON novo foi substituido normalmente",
              json.loads(out.read_text(encoding="utf-8")) ==
              [{"id": "novo", "title": "N"}])
        check("nenhum temporario CSV abandonado apos falha",
              tmp_leftovers(base, csv_path) == [])


def test_csv_replace_success() -> None:
    print("== 9. CSV: substituicao normal (novo conteudo assume o lugar) ==")
    old = sample_jobs()
    new = [{"id": "novo", "title": "Novo Titulo", "score": 9.5}]
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        save_outputs(old, out)
        csv_path = out.with_suffix(".csv")
        os.chmod(csv_path, 0o640)

        save_outputs(new, out)

        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        check("CSV novo substitui o anterior integralmente",
              [r["id"] for r in rows] == ["novo"])
        check("conteudo novo presente",
              rows[0]["title"] == "Novo Titulo" and rows[0]["score"] == "9.5")
        check("modo do arquivo anterior preservado na substituicao",
              stat.S_IMODE(csv_path.stat().st_mode) == 0o640)
        check("sem temporarios apos sucesso no CSV",
              tmp_leftovers(base, csv_path) == [])


def test_json_still_atomic_with_csv() -> None:
    print("== 10. JSON continua atomico (nao-regressao com CSV atomico) ==")
    old = sample_jobs()
    with tempfile.TemporaryDirectory(prefix="if_atomic_") as tmp:
        base = Path(tmp)
        out = base / "jobs.json"
        out.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        csv_path = out.with_suffix(".csv")
        csv_path.write_text("id,title\nantigo,VELHO\n", encoding="utf-8")
        before_json = out.read_bytes()
        before_csv = csv_path.read_bytes()

        raised = False
        with patch.object(__import__("json"), "dump",
                          side_effect=OSError("disk full")):
            try:
                save_outputs([{"id": "novo"}], out)
            except OSError:
                raised = True
        check("falha de escrita do JSON propaga ao chamador", raised)
        check("JSON final existente inalterado (mesmos bytes)",
              out.read_bytes() == before_json)
        check("CSV (etapa posterior) nao foi tocado",
              csv_path.read_bytes() == before_csv)
        check("nenhum temporario JSON abandonado apos falha",
              tmp_leftovers(base, out) == [])


def main() -> int:
    test_normal_write()
    test_failure_during_dump()
    test_failure_during_replace()
    test_replace_success()
    test_rotation_interaction()
    test_csv_normal_write()
    test_csv_failure_during_write()
    test_csv_failure_during_replace()
    test_csv_replace_success()
    test_json_still_atomic_with_csv()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK (test_atomic_outputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())