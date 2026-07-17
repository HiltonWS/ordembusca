"""Pipeline de tempo real: áudio → transcrição → detecção de mecânicas.

Emite eventos que tanto o CLI quanto o servidor web (Fase 3) consomem.
Cada fala transcrita gera um Event com o texto e as mecânicas detectadas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Iterator

from . import db as dbmod
from .detect import Detection, Detector

if TYPE_CHECKING:  # só para tipagem; runtime importa sob demanda
    pass


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
        "page": d.page, "loc": d.loc, "source": d.source,
    }


class Pipeline:
    """Junta STT + Detector. O áudio é fornecido como fluxo de frames."""

    def __init__(self, db_path: str = "ordem.db", model_size: str = "small",
                 device: str = "cpu", compute_type: str = "int8"):
        self.conn = dbmod.connect(db_path)
        self.detector = Detector(dbmod.all_lexicon(self.conn))
        # STT é opcional: sem as deps de voz instaladas, detect_text e o
        # modo demo/web continuam funcionando; só o run() com áudio exige.
        self._stt_args = (model_size, device, compute_type)
        self._transcriber = None

    @property
    def transcriber(self):
        if self._transcriber is None:
            from .stt import Transcriber
            self._transcriber = Transcriber(*self._stt_args)
        return self._transcriber

    def run(self, frames: Iterator[bytes], aggressiveness: int = 2,
            padding_ms: int = 400) -> Iterator[Event]:
        # import sob demanda: as deps de voz (webrtcvad etc.) só são
        # necessárias quando há áudio de verdade — o modo demo/web e o
        # detect_text funcionam sem elas instaladas.
        from . import audio as audiomod
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
