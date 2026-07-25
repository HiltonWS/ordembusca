"""Storyboard limitado construído a partir de eventos ou transcrições JSONL."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path


class StoryBoard:
    def __init__(self, max_scenes: int = 120, moment_seconds: float = 20,
                 illustrator=None):
        self.scenes: deque[dict] = deque(maxlen=max_scenes)
        self.moment_seconds = moment_seconds
        self.illustrator = illustrator
        self._sequence = 0

    def add_event(self, event: dict) -> dict | None:
        text = str(event.get("text") or "").strip()
        if not text:
            return None
        detections = event.get("detections") or []
        start_s = float(event.get("start_s") or 0)
        primary = self._primary_category(detections)
        if self.scenes and self._continues_moment(self.scenes[-1], start_s, primary):
            scene = self.scenes[-1]
            scene["revision"] += 1
            scene["text"] = self._merge_text(scene["text"], text)
            scene["mechanics"] = self._merge_mechanics(scene["mechanics"], detections)
            scene["title"] = self._title(detections) if detections else scene["title"]
            if primary != "narrativa":
                scene["primary_category"] = primary
            scene["end_s"] = max(start_s + float(event.get("duration_s") or 0), start_s)
            asset = next(
                (item.get("thumbnail") for item in detections if item.get("thumbnail")), None
            )
            if asset:
                scene["asset_thumbnail"] = asset
            scene["updated"] = True
            if self.illustrator:
                scene["thumbnail"] = self.illustrator.render(scene)
            return scene

        self._sequence += 1
        scene = {
            "id": self._sequence,
            "revision": 1,
            "start_s": start_s,
            "end_s": start_s + float(event.get("duration_s") or 0),
            "text": text,
            "title": self._title(detections),
            "primary_category": primary,
            "mechanics": self._merge_mechanics([], detections),
            "asset_thumbnail": next(
                (item.get("thumbnail") for item in detections if item.get("thumbnail")),
                None,
            ),
            "updated": False,
        }
        scene["thumbnail"] = (
            self.illustrator.render(scene) if self.illustrator else scene["asset_thumbnail"]
        )
        evicted = self.scenes[0] if len(self.scenes) == self.scenes.maxlen else None
        self.scenes.append(scene)
        if evicted and self.illustrator and hasattr(self.illustrator, "discard"):
            self.illustrator.discard(evicted)
        return scene

    def _continues_moment(self, scene: dict, start_s: float, primary: str) -> bool:
        elapsed = start_s - float(scene.get("start_s") or 0)
        same_action = primary == scene.get("primary_category")
        narrative = primary == "narrativa" or scene.get("primary_category") == "narrativa"
        return elapsed <= self.moment_seconds and (same_action or narrative)

    @staticmethod
    def _merge_text(current: str, new: str) -> str:
        if new in current:
            return current
        return f"{current} {new}".strip()[-420:]

    @staticmethod
    def _merge_mechanics(current: list[dict], detections: list[dict]) -> list[dict]:
        merged = {(item.get("term"), item.get("category")): item for item in current}
        for item in detections:
            data = {
                "term": item.get("term"), "category": item.get("category"),
                "summary": item.get("summary"), "elemento": item.get("elemento"),
            }
            merged[(data["term"], data["category"])] = data
        return list(merged.values())[-8:]

    @staticmethod
    def _primary_category(detections: list[dict]) -> str:
        priorities = ("ritual", "poder", "combate", "perseguicao", "arma", "condicao")
        categories = {item.get("category") for item in detections}
        return next((category for category in priorities if category in categories), "narrativa")

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
