"""Registro opcional de transcrições para revisão e preparação de datasets."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class TranscriptStore:
    """Grava uma sessão em JSONL e Markdown; não é ativado automaticamente."""

    def __init__(self, directory: str | Path, session_id: str | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.jsonl_path = self.directory / f"{self.session_id}.jsonl"
        self.markdown_path = self.directory / f"{self.session_id}.md"
        self._lock = threading.Lock()
        self._sequence = 0
        if not self.markdown_path.exists():
            self.markdown_path.write_text(
                f"# Revisão de transcrições — {self.session_id}\n\n"
                "> Marque erros e preencha a correção sugerida. O JSONL contém "
                "os dados estruturados da sessão.\n\n",
                encoding="utf-8",
            )

    def append(self, event: dict, origin: str) -> None:
        text = str(event.get("text") or "").strip()
        if not text:
            return
        with self._lock:
            self._sequence += 1
            detections = event.get("detections") or []
            record = {
                "id": self._sequence,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "origin": origin,
                "start_s": event.get("start_s"),
                "duration_s": event.get("duration_s"),
                "text": text,
                "detections": detections,
                "review": {"status": "pending", "corrected_text": None, "notes": None},
            }
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._append_markdown(record)

    def _append_markdown(self, record: dict) -> None:
        seconds = float(record.get("start_s") or 0)
        timestamp = f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"
        mechanics = ", ".join(
            f"{item.get('term')} ({item.get('score')}%)"
            for item in record["detections"]
        ) or "nenhuma"
        text = record["text"].replace("\n", " ")
        block = (
            f"## {record['id']:04d} · {timestamp}\n\n"
            f"- **Origem:** {record['origin']}\n"
            f"- **Transcrição:** {text}\n"
            f"- **Mecânicas:** {mechanics}\n"
            "- **Revisão:** [ ] correta  [ ] erro de transcrição  [ ] erro de detecção\n"
            "- **Correção sugerida:** \n"
            "- **Observações:** \n\n"
        )
        with self.markdown_path.open("a", encoding="utf-8") as stream:
            stream.write(block)
