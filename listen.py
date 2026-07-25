#!/usr/bin/env python3
"""Escuta a mesa (microfone ou WAV) e mostra as mecânicas em tempo real.

Uso:
    python listen.py --mic                 # microfone ao vivo
    python listen.py --auto-io             # auto: mic + loopback (se houver)
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
    "recurso": "\033[93m", "atributo": "\033[92m", "poder": "\033[35m",
    "caracteristica": "\033[94m", "mascara": "\033[95m",
    "armadura": "\033[34m", "trilha": "\033[36m", "vestimenta": "\033[32m",
    "acessorio": "\033[33m", "sinergia": "\033[95m", "bonus": "\033[92m",
    "multiplicador": "\033[91m",
    "classe": "\033[96m", "sobrevivente": "\033[93m", "nex": "\033[94m",
    "perseguicao": "\033[33m", "combate": "\033[91m",
    "efeito": "\033[95m", "dt": "\033[96m",
}
RESET = "\033[0m"


def print_event(ev) -> None:
    ts = f"[{int(ev.start_s // 60):02d}:{int(ev.start_s % 60):02d}]"
    print(f"\n{ts} 🎙  {ev.text}")
    for d in ev.detections:
        cor = CORES.get(d["category"], "")
        if d.get("elemento"):
            circ = d.get("circulo")
            extra = f" [{d['elemento']}{f' {circ}' if circ else ''}]"
        else:
            extra = ""
        loc = d.get("loc") or (f"p.{d['page']}" if d.get("page") else None)
        ref = f" — {d['source']} · {loc}" if d.get("source") and loc else ""
        print(f"       {cor}● {d['category']:9s}{RESET} {d['term']}{extra}"
              f"  ({d['score']}%){ref}")
        if d.get("summary"):
            print(f"         ↳ {d['summary']}")
        if d.get("tier"):
            print(f"         ★ {d['tier']}: {d['tier_summary']}")
        if d.get("details"):
            print(f"         Regra ampliada: {d['details']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--mic", action="store_true", help="ouvir o microfone")
    src.add_argument("--auto-io", action="store_true",
                     help="auto-detectar entrada + saida (loopback)")
    src.add_argument("--wav", help="processar um arquivo WAV")
    src.add_argument("--devices", type=int, nargs="+", metavar="N",
                     help="mixar 2+ dispositivos (ex: --devices 1 5 = "
                          "microfone + loopback do sistema, para ouvir "
                          "o que você fala E o que você escuta)")
    ap.add_argument("--db", default="ordem.db")
    ap.add_argument("--model", default="small",
                    help="tiny|base|small|medium|large-v3 (default: small)")
    ap.add_argument("--device", default="cpu", help="cpu|cuda")
    ap.add_argument("--compute", default="int8", help="int8|float16|float32")
    ap.add_argument("--mic-device", type=int, default=None,
                    help="índice do microfone (ver --list-mics)")
    ap.add_argument("--aggressiveness", type=int, default=2,
                    help="VAD 0-3 (maior corta mais ruído)")
    ap.add_argument("--padding-ms", type=int, default=550,
                    help="silêncio (ms) para fechar uma fala; "
                         "maior = falas mais completas")
    ap.add_argument("--list-mics", action="store_true")
    args = ap.parse_args()

    if args.list_mics:
        from ordem.audio import list_input_devices
        print("Dispositivos de entrada ([LOOPBACK] = captura o que você escuta):")
        for d in list_input_devices():
            tag = "  [LOOPBACK]" if d["loopback"] else ""
            print(f"  [{d['index']}] {d['name']}{tag}")
        print("\nPara ouvir a mesa inteira (sua voz + Discord no fone):")
        print("  python listen.py --devices <mic> <loopback>")
        return 0

    if not args.mic and not args.auto_io and not args.wav and not args.devices:
        ap.error("escolha --mic, --auto-io, --wav ou --devices (ou --list-mics)")

    from ordem.audio import (
        auto_select_devices,
        describe_devices,
        frames_from_devices,
        frames_from_mic,
        frames_from_wav,
    )
    from ordem.pipeline import Pipeline

    print(f"Carregando modelo Whisper '{args.model}' ({args.device})...",
          file=sys.stderr)
    pipe = Pipeline(args.db, args.model, args.device, args.compute)
    print("Pronto. Ouvindo..." if (args.mic or args.devices or args.auto_io)
          else "Processando áudio...", file=sys.stderr)

    if args.devices:
        frames = frames_from_devices(args.devices)
    elif args.auto_io:
        chosen = auto_select_devices()
        print(f"Auto-IO: {describe_devices(chosen)}", file=sys.stderr)
        frames = frames_from_devices(chosen)
    elif args.mic:
        frames = frames_from_mic(args.mic_device)
    else:
        frames = frames_from_wav(args.wav)
    try:
        for ev in pipe.run(frames, aggressiveness=args.aggressiveness,
                           padding_ms=args.padding_ms):
            print_event(ev)
    except KeyboardInterrupt:
        print("\nEncerrado.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
