"""Pipeline de tempo real: áudio → transcrição → detecção de mecânicas.

Emite eventos que tanto o CLI quanto o servidor web (Fase 3) consomem.
Cada fala transcrita gera um Event com o texto e as mecânicas detectadas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterator

from . import audio as audiomod
from . import db as dbmod
from .detect import Detection, Detector


@dataclass
class Event:
    start_s: float
    duration_s: float
    text: str
    detections: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _detection_to_dict(d: Detection) -> dict:
    return {
        "term": d.term, "category": d.category, "score": d.score,
        "elemento": d.meta.get("elemento"), "circulo": d.meta.get("circulo"),
        "summary": d.summary,
        "page": d.page, "source": d.source,
    }


class Pipeline:
    """Junta STT + Detector. O áudio é fornecido como fluxo de frames."""

    def __init__(self, db_path: str = "ordem.db", model_size: str = "small",
                 device: str = "cpu", compute_type: str = "int8"):
        self.conn = dbmod.connect(db_path)
        self.detector = Detector(dbmod.all_lexicon(self.conn))
        from .stt import Transcriber
        # o modelo em si só é baixado/carregado na 1ª transcrição
        self.transcriber = Transcriber(model_size, device, compute_type)

    def run(self, frames: Iterator[bytes], aggressiveness: int = 2,
            padding_ms: int = 400) -> Iterator[Event]:
        for utt in audiomod.utterances(frames, aggressiveness, padding_ms):
            text = self.transcriber.transcribe(utt.audio)
            if not text:
                continue
            dets = self.detector.detect(text)
            yield Event(
                start_s=round(utt.start_s, 2),
                duration_s=round(utt.duration_s, 2),
                text=text,
                detections=[_detection_to_dict(d) for d in dets],
            )

    def detect_text(self, text: str) -> Event:
        """Atalho para testar a detecção sem áudio (texto já transcrito)."""
        dets = self.detector.detect(text)
        return Event(0.0, 0.0, text,
                     [_detection_to_dict(d) for d in dets])
