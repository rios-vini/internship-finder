"""Persistencia do enrichment: JSONL incremental com escrita atomica.

Arquivo: 1 record por linha, key = ``job_id`` (reprocessar uma vaga
SUBSTITUI o record do mesmo job_id — upsert). Escrita atomica com
temporario no MESMO diretorio + ``os.replace`` (mesma mecanica do
``_write_atomic`` do cli.py — quem le nunca ve arquivo pela metade).

Preservacao: record bem-sucedido anterior NUNCA e apagado por uma falha
nova do MESMO conteudo (``content_hash`` identico) — a falha e descartada
e o sucesso preservado. Falha de conteudo NOVO (hash diferente) e gravada
normalmente (o estado atual da pagina e dado valido). ``load()`` pula
linhas malformadas com aviso, nunca crasha.
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

        - record novo/sucesso -> substitui o anterior (upsert);
        - record de FALHA + anterior bem-sucedido com o MESMO content_hash
          -> "preserved" (o sucesso fica; falha repetida de conteudo igual
          nao destrui extracao valida);
        - record de FALHA sem content_hash (fetch falho: conteudo desconhecido —
          timeout/rede/nao-200) + anterior bem-sucedido -> "preserved" tambem:
          o requisito e NAO PERDER a extracao valida em falha transitatoria. A
          falha fica auditavel em ``last_error``/``last_failed_at`` dentro do
          record preservado (nao e estado escondido) sem apagar os campos
          extraidos;
        - record de FALHA de conteudo diferente (ou sem anterior) -> gravada.
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
            # Falha nao pode destruir extracao valida: preserva quando o
            # conteudo e o MESMO (hash igual) ou DESCONHECIDO (hash None:
            # fetch falho). So uma falha de conteudo comprovadamente NOVO
            # substitui (o estado da pagina mudou e isso e dado).
            if rec.get("content_hash") is None or existing.get("content_hash") == rec.get("content_hash"):
                # Auditoria da falha dentro do record preservado (campos
                # last_*): a extracao valida continua, a falha fica visivel.
                existing = dict(existing)
                existing["last_error"] = rec.get("error")
                existing["last_failed_at"] = rec.get("fetched_at")
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
