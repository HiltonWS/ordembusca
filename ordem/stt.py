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


def build_vocab_prompt(terms: list[str], budget_chars: int = 700) -> str:
    """Monta o initial_prompt do Whisper com o vocabulário do jogo.

    O Whisper usa o prompt como contexto e passa a favorecer esses termos
    na decodificação — a melhoria mais barata e eficaz para nomes próprios
    (rituais, perícias) que ele erraria. O orçamento respeita o limite de
    ~224 tokens do modelo.
    """
    seen: set[str] = set()
    out: list[str] = []
    used = 0
    for t in terms:
        t = t.strip()
        key = t.lower()
        if not t or key in seen:
            continue
        if used + len(t) + 2 > budget_chars:
            break
        seen.add(key)
        out.append(t)
        used += len(t) + 2
    if not out:
        return ""
    return ("Sessão de RPG Ordem Paranormal. Termos do jogo: "
            + ", ".join(out) + ".")


def normalize_peak(audio: np.ndarray, target: float = 0.9,
                   floor: float = 1e-4) -> np.ndarray:
    """Amplifica falas fracas (comum ao mixar mic + loopback) até um pico
    saudável para o Whisper. Sinais já fortes passam intactos."""
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    if floor < peak < target:
        audio = audio * (target / peak)
    return audio


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "cpu",
                 compute_type: str = "int8", language: str = "pt",
                 vocabulary: list[str] | None = None):
        self.language = language
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None       # carregado sob demanda
        vocab = vocabulary or []
        self.initial_prompt = build_vocab_prompt(vocab) or None
        # hotwords: viés mais forte, orçamento menor — só os nomes próprios
        self.hotwords = build_vocab_prompt(vocab, budget_chars=300) or None

    @property
    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._model_size, device=self._device,
                                       compute_type=self._compute_type)
        return self._model

    def _kwargs(self) -> dict:
        kw = dict(language=self.language, beam_size=5, vad_filter=False,
                  condition_on_previous_text=False)
        if self.initial_prompt:
            kw["initial_prompt"] = self.initial_prompt
        if self.hotwords:
            kw["hotwords"] = self.hotwords
        return kw

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcreve uma fala (float32 16kHz) e devolve o texto."""
        audio = normalize_peak(audio)
        try:
            segments, _ = self.model.transcribe(audio, **self._kwargs())
        except TypeError:
            # faster-whisper antigo sem 'hotwords': tenta sem
            kw = self._kwargs()
            kw.pop("hotwords", None)
            segments, _ = self.model.transcribe(audio, **kw)
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe_detailed(self, audio: np.ndarray) -> list[TranscriptSegment]:
        audio = normalize_peak(audio)
        segments, _ = self.model.transcribe(audio, **self._kwargs())
        return [
            TranscriptSegment(s.text.strip(), s.start, s.end, s.avg_logprob)
            for s in segments
        ]
