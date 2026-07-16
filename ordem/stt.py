"""Transcrição de fala (STT) local com faster-whisper.

O modelo roda offline depois do primeiro download (feito automaticamente
na 1ª execução na sua máquina, cacheado em ~/.cache/huggingface).

Tamanhos: 'tiny'/'base' (rápidos, menos precisos), 'small' (bom equilíbrio
para pt-BR em CPU), 'medium'/'large-v3' (mais precisos, pedem GPU).
compute_type='int8' acelera em CPU; use 'float16' em GPU.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TranscriptSegment:
    text: str
    start_s: float
    end_s: float
    avg_logprob: float          # confiança aproximada do modelo


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "cpu",
                 compute_type: str = "int8", language: str = "pt"):
        self.language = language
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None       # carregado sob demanda

    @property
    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._model_size, device=self._device,
                                       compute_type=self._compute_type)
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcreve uma fala (float32 16kHz) e devolve o texto."""
        segments, _ = self.model.transcribe(
            audio, language=self.language, beam_size=5,
            vad_filter=False,          # já segmentamos com webrtcvad
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe_detailed(self, audio: np.ndarray) -> list[TranscriptSegment]:
        segments, _ = self.model.transcribe(
            audio, language=self.language, beam_size=5, vad_filter=False,
            condition_on_previous_text=False,
        )
        return [
            TranscriptSegment(s.text.strip(), s.start, s.end, s.avg_logprob)
            for s in segments
        ]
