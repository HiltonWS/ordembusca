"""Pipeline de tempo real: áudio → transcrição → detecção de mecânicas.

Emite eventos que tanto o CLI quanto o servidor web (Fase 3) consomem.
Cada fala transcrita gera um Event com o texto e as mecânicas detectadas.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Iterator

from . import db as dbmod
from .detect import Detection, Detector, is_explanation_question

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
        "tier": d.tier, "tier_summary": d.tier_summary,
        "page": d.page, "loc": d.loc, "source": d.source,
    }


def _canonical_fallback() -> list[dict]:
    """Termos canônicos (perícias/condições/recursos/atributos) sem livros.

    Usado quando o banco não tem léxico (nenhuma fonte ingerida ainda) —
    assim o servidor/CLI reconhece pelo menos os termos fixos do sistema
    em vez de não detectar absolutamente nada. Rituais/poderes nomeados
    continuam exigindo `ingest.py` com os livros reais.
    """
    from .lexicon import canonical_entries
    entries = canonical_entries(None)
    return [
        {"term": e.term, "category": e.category, "aliases": e.aliases,
         "meta": e.meta, "summary": e.summary, "page": e.page,
         "loc": e.loc, "title": None, "filename": None}
        for e in entries
    ]


class Pipeline:
    """Junta STT + Detector. O áudio é fornecido como fluxo de frames."""

    def __init__(self, db_path: str = "ordem.db", model_size: str = "small",
                 device: str = "cpu", compute_type: str = "int8"):
        self.conn = dbmod.connect(db_path)
        lexicon = dbmod.all_lexicon(self.conn) or _canonical_fallback()
        self.detector = Detector(lexicon)
        # vocabulário para o viés do Whisper: nomes próprios primeiro
        # (rituais/poderes, que o STT mais erra), depois o resto do sistema
        prio = {"ritual": 0, "poder": 1, "caracteristica": 1, "mascara": 1,
            "trilha": 1, "classe": 1, "sobrevivente": 1, "nex": 1,
            "armadura": 2, "vestimenta": 2, "acessorio": 2,
            "perseguicao": 2, "combate": 2,
            "sinergia": 2, "pericia": 3, "condicao": 4,
            "recurso": 5, "atributo": 6}
        vocab = [e["term"] for e in sorted(
            lexicon, key=lambda e: prio.get(e["category"], 9))]
        self._stt_args = (model_size, device, compute_type)
        self._vocab = vocab
        self._transcriber = None

    @property
    def transcriber(self):
        if self._transcriber is None:
            from .stt import Transcriber
            self._transcriber = Transcriber(*self._stt_args,
                                            vocabulary=self._vocab)
        return self._transcriber

    def run(self, frames: Iterator[bytes], aggressiveness: int = 2,
            padding_ms: int = 550) -> Iterator[Event]:
        # import sob demanda: as deps de voz (webrtcvad etc.) só são
        # necessárias quando há áudio de verdade — o modo demo/web e o
        # detect_text funcionam sem elas instaladas.
        from . import audio as audiomod
        for utt in audiomod.utterances(frames, aggressiveness, padding_ms):
            text = self.transcriber.transcribe(utt.audio)
            if not text:
                continue
            dets = self.detector.detect(text)
            serialized = [_detection_to_dict(d) for d in dets]
            self._add_explanations(text, serialized)
            yield Event(
                start_s=round(utt.start_s, 2),
                duration_s=round(utt.duration_s, 2),
                text=text,
                detections=serialized,
            )

    def detect_text(self, text: str) -> Event:
        """Atalho para testar a detecção sem áudio (texto já transcrito)."""
        dets = self.detector.detect(text)
        serialized = [_detection_to_dict(d) for d in dets]
        self._add_explanations(text, serialized)
        return Event(0.0, 0.0, text, serialized)

    def _add_explanations(self, text: str, detections: list[dict]) -> None:
        if not is_explanation_question(text):
            return
        for detection in detections:
            if detection["category"] not in ("condicao", "efeito", "dt"):
                continue
            details = dbmod.explain_term(self.conn, detection["term"])
            if details:
                detection["details"] = details
