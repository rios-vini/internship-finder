"""Persistencia do enrichment: JSONL incremental com escrita atomica.

Arquivo: 1 record por linha, key = ``job_id`` (reprocessar uma vaga
SUBSTITUI o record do mesmo job_id — upsert). Escrita atomica com
temporario no MESMO diretorio + ``os.replace`` (mesma mecanica do
``_write_atomic`` do cli.py — quem le nunca ve arquivo pela metade).

Preservacao (Fase 2, spec secao 9): um sucesso anterior NUNCA e apagado
por uma falha nova. Falha do MESMO conteudo (hash igual) ou de conteudo
DESCONHECIDO (fetch falho, hash None) -> sucesso preservado com a falha
auditavel em ``last_error``/``last_failed_at``. Falha de conteudo NOVO
(hash diferente) -> sucesso preservado COM PENDENCIA: a versao nova da
pagina fica registrada em ``pending_content_hash`` (o planejador
reprocessa essa versao quando ela voltar a ser vista). Novo sucesso
SEMPRE substitui tudo (pendencia some). ``load()`` pula linhas
malformadas com aviso, nunca crasha.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from internship_finder.enrichment.schema import is_success_record


class EnrichmentStore:
    """JSONL de records de enrichment (key = job_id), read-only em data/."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, dict]:
        """Le todos os records: {job_id: record}. Linha malformada -> pula.

        Nunca crasha: arquivo ausente -> {}; JSON invalido/sem job_id ->
        aviso no stderr e segue (o dado ruim nao derruba o lote).
        """
        if not self.path.exists():
            return {}
        records: dict[str, dict] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    job_id = record.get("job_id")
                except (json.JSONDecodeError, AttributeError):
                    print(
                        f"[aviso] {self.path.name}:{lineno}: linha malformada "
                        "— ignorada",
                        file=sys.stderr,
                    )
                    continue
                if not isinstance(record, dict) or not job_id:
                    print(
                        f"[aviso] {self.path.name}:{lineno}: sem job_id — "
                        "ignorada",
                        file=sys.stderr,
                    )
                    continue
                records[str(job_id)] = record
        return records

    def get(self, job_id: str) -> dict | None:
        """Record atual do job_id (None se nunca processado)."""
        return self.load().get(job_id)

    def upsert(self, record) -> str:
        """Grava o record por job_id. Retorna "written" | "preserved".

        - record novo/sucesso -> substitui o anterior (upsert; se o
          anterior tinha pendencia, ela some — a re-extracao resolveu);
        - record de FALHA + anterior bem-sucedido -> "preserved": o
          sucesso anterior fica, a falha fica auditavel no proprio
          record preservado (``last_error``/``last_failed_at``). Quando
          a falha e de conteudo comprovadamente NOVO (``content_hash``
          diferente do sucesso preservado), a versao nova da pagina e
          registrada em ``pending_content_hash`` — spec secao 9: o
          sucesso anterior e o ultimo enrichment VALIDO e NUNCA e
          apagado por indisponibilidade da API; o planejador manda a
          versao pendente de volta ao pool quando a vir novamente.
          Falha com hash igual ou desconhecido (fetch falho, hash
          None) preserva sem pendencia (o conteudo do sucesso
          continua sendo o estado atual conhecido);
        - record de FALHA sem anterior bem-sucedido -> gravada
          normalmente (o estado atual, mesmo falho, e dado).
        """
        rec = (
            record
            if isinstance(record, dict)
            else record.model_dump(mode="json")
        )
        job_id = rec.get("job_id")
        if not job_id:
            raise ValueError("upsert exige record com job_id")
        current = self.load()
        existing = current.get(str(job_id))
        if (
            existing is not None
            and is_success_record(existing)
            and not is_success_record(rec)
        ):
            # Falha nunca destrroi extracao valida (spec secao 9).
            # So grava quando o anterior e falha OU nao existe.
            existing = dict(existing)
            existing["last_error"] = rec.get("error")
            existing["last_failed_at"] = rec.get("fetched_at")
            new_hash = rec.get("content_hash")
            if new_hash is not None and new_hash != existing.get("content_hash"):
                # Conteudo NOVO com falha de re-extracao: pendencia
                # registrada, sucesso preservado como ultimo valido.
                existing["pending_content_hash"] = new_hash
            current[str(job_id)] = existing
            self._write_all(list(current.values()))
            return "preserved"
        current[str(job_id)] = rec
        self._write_all(list(current.values()))
        return "written"

    def _write_all(self, records: list[dict]) -> None:
        """Escrita atomica: tmp no mesmo diretorio + os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                dir=self.path.parent,
                prefix=".enrichment-",
                suffix=".tmp",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp_name = tmp.name
                for record in records:
                    tmp.write(json.dumps(record, ensure_ascii=False) + "\n")
            os.replace(tmp_name, self.path)
        except BaseException:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
