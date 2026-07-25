"""Storyboard limitado construído a partir de eventos ou transcrições JSONL."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path


class StoryBoard:
    def __init__(self, max_scenes: int = 120):
        self.scenes: deque[dict] = deque(maxlen=max_scenes)
        self._sequence = 0

    def add_event(self, event: dict) -> dict | None:
        text = str(event.get("text") or "").strip()
        if not text:
            return None
        self._sequence += 1
        detections = event.get("detections") or []
        scene = {
            "id": self._sequence,
            "start_s": event.get("start_s") or 0,
            "text": text,
            "title": self._title(detections),
            "mechanics": [
                {
                    "term": item.get("term"),
                    "category": item.get("category"),
                    "summary": item.get("summary"),
                }
                for item in detections[:8]
            ],
            "thumbnail": next(
                (item.get("thumbnail") for item in detections if item.get("thumbnail")),
                None,
            ),
        }
        self.scenes.append(scene)
        return scene

    def load_jsonl(self, path: str | Path) -> int:
        loaded = 0
        transcript = Path(path)
        if not transcript.exists():
            return loaded
        for line in transcript.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if self.add_event(record):
                loaded += 1
        return loaded

    def to_json(self) -> list[dict]:
        return list(self.scenes)

    @staticmethod
    def _title(detections: list[dict]) -> str:
        priorities = (
            ("ritual", "Ritual"), ("poder", "Poder"), ("combate", "Combate"),
            ("perseguicao", "Perseguição"), ("arma", "Ação com arma"),
            ("condicao", "Consequência"), ("trilha", "Trilha"),
        )
        for category, label in priorities:
            match = next(
                (item for item in detections if item.get("category") == category),
                None,
            )
            if match:
                return f"{label}: {match.get('term')}"
        return "Cena da sessão"
