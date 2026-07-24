#!/usr/bin/env python3
"""Servidor web ao vivo: transcrição + mecânicas no navegador.

Reutiliza ordem/pipeline.py. O áudio roda num thread separado (captura e
Whisper são bloqueantes) e os eventos são empurrados por WebSocket.

Uso:
    python server.py --mic                 # ouve o microfone
    python server.py --auto-io             # auto: mic + loopback (se houver)
    python server.py --wav sessao.wav      # processa uma gravação
    python server.py --demo                # sem áudio: só o endpoint /simulate

Depois abra http://localhost:8000 no navegador.
Modo demo/teste: com a página aberta, envie texto para ver os cards:
    curl -X POST localhost:8000/simulate -H "Content-Type: application/json" \\
         -d '{"text":"conjura Sopro do Caos e faz teste de Ocultismo"}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Ordem — Detector de Mecânicas")

_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None
_config: dict = {}
_pipeline = None            # criado lazy (evita carregar Whisper em demo)


class SimulateIn(BaseModel):
    text: str


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from ordem.pipeline import Pipeline
        _pipeline = Pipeline(
            _config.get("db", "ordem.db"),
            _config.get("model", "small"),
            _config.get("device", "cpu"),
            _config.get("compute", "int8"),
        )
    return _pipeline


async def _broadcast(event: dict) -> None:
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


def _emit_from_thread(event: dict) -> None:
    """Chamado pelo thread de áudio para enfileirar no loop asyncio."""
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(_broadcast(event), _loop)


def _audio_worker() -> None:
    """Thread: lê o áudio, roda o pipeline e emite eventos."""
    from ordem.audio import (auto_select_devices, describe_devices,
                             frames_from_devices, frames_from_mic,
                             frames_from_wav)

    source = _config.get("source")
    if source == "devices":
        frames = frames_from_devices(_config["devices"])
    elif source == "auto":
        chosen = auto_select_devices()
        print(f"Auto-IO: {describe_devices(chosen)}")
        frames = frames_from_devices(chosen)
    elif source == "mic":
        frames = frames_from_mic(_config.get("mic_device"))
    elif source == "wav":
        frames = frames_from_wav(_config["wav"])
    else:
        return  # demo: sem áudio

    pipe = get_pipeline()
    for ev in pipe.run(frames, aggressiveness=_config.get("aggressiveness", 2),
                       padding_ms=_config.get("padding_ms", 550)):
        _emit_from_thread({"type": "event", **ev.to_json()})
    _emit_from_thread({"type": "end"})


@app.on_event("startup")
async def _startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    if _config.get("source") in ("mic", "wav", "devices"):
        threading.Thread(target=_audio_worker, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "source": _config.get("source"), "clients": len(_clients)}


@app.post("/simulate")
async def simulate(inp: SimulateIn) -> dict:
    """Detecta mecânicas num texto e transmite como evento (teste sem áudio)."""
    ev = get_pipeline().detect_text(inp.text)
    await _broadcast({"type": "event", **ev.to_json()})
    return {"detections": len(ev.detections)}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    await websocket.send_text(json.dumps({"type": "hello",
                                          "source": _config.get("source")}))
    try:
        while True:
            await websocket.receive_text()   # mantém a conexão viva
    except WebSocketDisconnect:
        _clients.discard(websocket)


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--mic", action="store_true")
    src.add_argument("--auto-io", action="store_true",
                     help="auto-detectar entrada + saida (loopback)")
    src.add_argument("--devices", type=int, nargs="+", metavar="N",
                     help="mixar dispositivos (mic + loopback do sistema)")
    src.add_argument("--wav")
    src.add_argument("--demo", action="store_true")
    ap.add_argument("--db", default="ordem.db")
    ap.add_argument("--model", default="small")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute", default="int8")
    ap.add_argument("--mic-device", type=int, default=None)
    ap.add_argument("--aggressiveness", type=int, default=2)
    ap.add_argument("--padding-ms", type=int, default=550,
                    help="silêncio (ms) para fechar uma fala; maior = falas mais completas")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    _config.update(
        source=("devices" if args.devices else "auto" if args.auto_io else "mic" if args.mic
                else "wav" if args.wav else "demo"),
        devices=args.devices,
        wav=args.wav, db=args.db, model=args.model, device=args.device,
        compute=args.compute, mic_device=args.mic_device,
        aggressiveness=args.aggressiveness, padding_ms=args.padding_ms,
    )

    import uvicorn
    print(f"→ http://{args.host}:{args.port}  (fonte: {_config['source']})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
