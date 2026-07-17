"""Testes da mixagem multi-dispositivo (mic + loopback).

Cobrem apenas a parte pura (mix_float_blocks e resample) — captura real
de dispositivo exige hardware e é validada manualmente.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("webrtcvad")

from ordem.audio import FRAME_SAMPLES, _resample_f32, mix_float_blocks  # noqa: E402


def _pcm(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.int16)


def test_mix_soma_duas_fontes():
    a = np.full(FRAME_SAMPLES, 0.4, np.float32)
    b = np.full(FRAME_SAMPLES, 0.3, np.float32)
    out = _pcm(mix_float_blocks([a, b]))
    assert len(out) == FRAME_SAMPLES
    assert abs(out[0] / 32767 - 0.7) < 0.01


def test_mix_clipa_sem_estourar():
    c = np.full(FRAME_SAMPLES, 0.8, np.float32)
    out = _pcm(mix_float_blocks([c, c]))
    assert out.max() <= 32767
    assert abs(out[0] / 32767 - 1.0) < 0.01


def test_mix_uma_fonte_passthrough():
    a = np.full(FRAME_SAMPLES, -0.25, np.float32)
    out = _pcm(mix_float_blocks([a]))
    assert abs(out[0] / 32767 + 0.25) < 0.01


def test_mix_vazio():
    assert mix_float_blocks([]) == b""


def test_resample_preserva_duracao():
    # 48kHz -> 16kHz: 4800 amostras viram 1600
    data = np.sin(np.linspace(0, 20 * np.pi, 4800)).astype(np.float32)
    out = _resample_f32(data, 48000, 16000)
    assert len(out) == 1600
    # amplitude preservada (sem ganho espúrio)
    assert 0.9 < np.abs(out).max() <= 1.001
