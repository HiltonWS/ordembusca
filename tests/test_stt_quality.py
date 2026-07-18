"""Testes das melhorias de qualidade do STT (sem exigir o modelo Whisper)."""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("numpy")

from ordem.stt import build_vocab_prompt, normalize_peak  # noqa: E402


def test_prompt_respeita_orcamento_e_prefixo():
    terms = [f"Ritual Número {i}" for i in range(200)]
    p = build_vocab_prompt(terms, budget_chars=300)
    assert len(p) <= 360                      # orçamento + prefixo/sufixo
    assert p.startswith("Sessão de RPG Ordem Paranormal")
    assert "Ritual Número 0" in p


def test_prompt_deduplica_e_ignora_vazios():
    p = build_vocab_prompt(["NEX", "nex", "", "  ", "PE"], budget_chars=200)
    assert p.count("NEX") == 1
    assert "PE" in p


def test_prompt_vazio():
    assert build_vocab_prompt([]) == ""


def test_normalize_amplifica_sinal_fraco():
    weak = np.full(1600, 0.05, np.float32)
    out = normalize_peak(weak)
    assert abs(out.max() - 0.9) < 0.01


def test_normalize_preserva_sinal_forte():
    strong = np.full(1600, 0.95, np.float32)
    assert normalize_peak(strong).max() == np.float32(0.95)


def test_normalize_ignora_silencio():
    silent = np.zeros(1600, np.float32)
    assert normalize_peak(silent).max() == 0.0
