#!/usr/bin/env python3
"""Escuta a mesa (microfone ou WAV) e mostra as mecânicas em tempo real.

Uso:
    python listen.py --mic                 # microfone ao vivo
    python listen.py --wav sessao.wav      # testar com uma gravação
    python listen.py --mic --model medium  # modelo maior (precisa de GPU)
    python listen.py --list-mics           # listar microfones disponíveis

Na 1ª execução o modelo do Whisper é baixado automaticamente (offline depois).
"""
from __future__ import annotations

import argparse
import sys

CORES = {
    "ritual": "\033[95m", "pericia": "\033[96m", "condicao": "\033[91m",
    "recurso": "\033[93m", "atributo": "\033[92m",
}
RESET = "\033[0m"


def print_event(ev) -> None:
    ts = f"[{int(ev.start_s // 60):02d}:{int(ev.start_s % 60):02d}]"
    print(f"\n{ts} 🎙  {ev.text}")
    for d in ev.detections:
        cor = CORES.get(d["category"], "")
        extra = f" [{d['elemento']} {d['circulo']}]" if d.get("elemento") else ""
        ref = f" — {d['source']} p.{d['page']}" if d.get("page") else ""
        print(f"       {cor}● {d['category']:9s}{RESET} {d['term']}{extra}"
              f"  ({d['score']}%){ref}")
        if d.get("summary"):
            print(f"         ↳ {d['summary']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--mic", action="store_true", help="ouvir o microfone")
    src.add_argument("--wav", help="processar um arquivo WAV")
    ap.add_argument("--db", default="ordem.db")
    ap.add_argument("--model", default="small",
                    help="tiny|base|small|medium|large-v3 (default: small)")
    ap.add_argument("--device", default="cpu", help="cpu|cuda")
    ap.add_argument("--compute", default="int8", help="int8|float16|float32")
    ap.add_argument("--mic-device", type=int, default=None,
                    help="índice do microfone (ver --list-mics)")
    ap.add_argument("--aggressiveness", type=int, default=2,
                    help="VAD 0-3 (maior corta mais ruído)")
    ap.add_argument("--list-mics", action="store_true")
    args = ap.parse_args()

    if args.list_mics:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                print(f"  [{i}] {d['name']}")
        return 0

    if not args.mic and not args.wav:
        ap.error("escolha --mic ou --wav (ou --list-mics)")

    from ordem.audio import frames_from_mic, frames_from_wav
    from ordem.pipeline import Pipeline

    print(f"Carregando modelo Whisper '{args.model}' ({args.device})...",
          file=sys.stderr)
    pipe = Pipeline(args.db, args.model, args.device, args.compute)
    print("Pronto. Ouvindo..." if args.mic else "Processando áudio...",
          file=sys.stderr)

    frames = (frames_from_mic(args.mic_device) if args.mic
              else frames_from_wav(args.wav))
    try:
        for ev in pipe.run(frames, aggressiveness=args.aggressiveness):
            print_event(ev)
    except KeyboardInterrupt:
        print("\nEncerrado.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
