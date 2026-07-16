"""Captura de áudio e segmentação por voz (VAD).

Transforma um fluxo de áudio (microfone ou arquivo WAV) em "falas"
(utterances): trechos contínuos de voz, com o silêncio no meio removido.
Cada fala sai como um numpy float32 mono 16kHz, pronto para o Whisper.

O microfone usa `sounddevice` (requer PortAudio no sistema). O modo WAV
não depende de PortAudio — útil para testar todo o pipeline com uma
gravação de sessão antes de ligar o microfone ao vivo.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Iterator

import numpy as np
import webrtcvad

SAMPLE_RATE = 16000          # Whisper e webrtcvad
FRAME_MS = 30                # webrtcvad aceita 10/20/30 ms
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000       # 480
FRAME_BYTES = FRAME_SAMPLES * 2                      # int16 = 2 bytes


@dataclass
class Utterance:
    audio: np.ndarray        # float32 mono 16kHz, faixa [-1, 1]
    start_s: float           # início (segundos desde o começo do stream)
    duration_s: float


def _pcm16_to_float32(pcm: bytes) -> np.ndarray:
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return a / 32768.0


class VADSegmenter:
    """Coleta frames de 30ms e emite falas usando o padrão ring-buffer.

    aggressiveness: 0 (permissivo) a 3 (agressivo, corta mais ruído).
    padding_ms:   silêncio necessário para fechar uma fala.
    """

    def __init__(self, aggressiveness: int = 2, padding_ms: int = 400):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.num_padding = padding_ms // FRAME_MS
        self.ring = collections.deque(maxlen=self.num_padding)
        self.triggered = False
        self.voiced: list[bytes] = []
        self._frame_index = 0
        self._utt_start = 0

    def process(self, frame: bytes) -> Utterance | None:
        """Consome um frame PCM16 de 30ms; devolve uma fala quando fechar."""
        is_speech = self.vad.is_speech(frame, SAMPLE_RATE)
        idx = self._frame_index
        self._frame_index += 1

        if not self.triggered:
            self.ring.append((frame, is_speech, idx))
            n_voiced = sum(1 for _, sp, _ in self.ring if sp)
            # dispara quando a maioria do buffer recente é voz
            if n_voiced > 0.9 * self.ring.maxlen:
                self.triggered = True
                self._utt_start = self.ring[0][2]
                self.voiced = [f for f, _, _ in self.ring]
                self.ring.clear()
            return None

        # já disparado: acumula até detectar silêncio prolongado
        self.voiced.append(frame)
        self.ring.append((frame, is_speech, idx))
        n_unvoiced = sum(1 for _, sp, _ in self.ring if not sp)
        if n_unvoiced > 0.9 * self.ring.maxlen:
            return self._flush()
        return None

    def _flush(self) -> Utterance | None:
        if not self.voiced:
            return None
        pcm = b"".join(self.voiced)
        audio = _pcm16_to_float32(pcm)
        utt = Utterance(
            audio=audio,
            start_s=self._utt_start * FRAME_MS / 1000.0,
            duration_s=len(audio) / SAMPLE_RATE,
        )
        self.triggered = False
        self.voiced = []
        self.ring.clear()
        return utt

    def finish(self) -> Utterance | None:
        """Fecha a fala pendente ao terminar o stream."""
        if self.triggered:
            return self._flush()
        return None


# ---- Fontes de frames -----------------------------------------------------

def frames_from_wav(path: str) -> Iterator[bytes]:
    """Frames de 30ms a partir de um WAV (convertido para 16kHz mono int16)."""
    import soundfile as sf

    data, sr = sf.read(path, dtype="int16", always_2d=True)
    data = data[:, 0]                      # canal 0 (mono)
    if sr != SAMPLE_RATE:
        data = _resample_int16(data, sr, SAMPLE_RATE)
    pcm = data.tobytes()
    for i in range(0, len(pcm) - FRAME_BYTES + 1, FRAME_BYTES):
        yield pcm[i:i + FRAME_BYTES]


def _resample_int16(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return data
    n_out = int(round(len(data) * sr_out / sr_in))
    x_old = np.linspace(0, 1, len(data), endpoint=False)
    x_new = np.linspace(0, 1, n_out, endpoint=False)
    resampled = np.interp(x_new, x_old, data.astype(np.float32))
    return resampled.astype(np.int16)


def frames_from_mic(device: int | None = None) -> Iterator[bytes]:
    """Frames de 30ms do microfone (requer sounddevice + PortAudio)."""
    import queue

    import sounddevice as sd

    q: queue.Queue[bytes] = queue.Queue()

    def callback(indata, frames, time_info, status):  # noqa: ANN001
        q.put(bytes(indata))

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES,
                           dtype="int16", channels=1, callback=callback,
                           device=device):
        buf = b""
        while True:
            buf += q.get()
            while len(buf) >= FRAME_BYTES:
                yield buf[:FRAME_BYTES]
                buf = buf[FRAME_BYTES:]


def utterances(frames: Iterator[bytes], aggressiveness: int = 2,
               padding_ms: int = 400,
               min_duration_s: float = 0.3) -> Iterator[Utterance]:
    """Converte um fluxo de frames em falas segmentadas."""
    seg = VADSegmenter(aggressiveness, padding_ms)
    for frame in frames:
        if len(frame) != FRAME_BYTES:
            continue
        utt = seg.process(frame)
        if utt and utt.duration_s >= min_duration_s:
            yield utt
    tail = seg.finish()
    if tail and tail.duration_s >= min_duration_s:
        yield tail
