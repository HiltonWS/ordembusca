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
import collections
import json
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

WEB_DIR = Path(__file__).parent / "web"
THUMBNAIL_DIR = Path(__file__).parent / ".ordem-thumbnails"
THUMBNAIL_DIR.mkdir(exist_ok=True)
ENV_CONFIG = "ORDEM_SERVER_CONFIG"
APP_VERSION = f"{os.getpid()}:{time.time_ns()}"

app = FastAPI(title="Ordem — Detector de Mecânicas")
app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")

_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None
_config: dict = {}
_pipeline = None            # criado lazy (evita carregar Whisper em demo)
_history: collections.deque[dict] = collections.deque(maxlen=300)
_transcript_store = None
_thumbnail_resolver = None
_storyboard = None


def _load_config_from_env() -> None:
    raw = os.environ.get(ENV_CONFIG)
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(data, dict):
        _config.update(data)


_load_config_from_env()


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


def get_thumbnail_resolver():
    global _thumbnail_resolver
    if _thumbnail_resolver is None:
        from ordem.thumbnails import ThumbnailResolver
        roots = ["tokens", "extras", ".ordem-drive/books"]
        roots.extend(_config.get("asset_dirs") or [])
        _thumbnail_resolver = ThumbnailResolver(
            get_pipeline().lexicon,
            asset_roots=roots,
            source_roots=["livros", ".ordem-drive/books"],
            cache_dir=THUMBNAIL_DIR,
        )
    return _thumbnail_resolver


def get_storyboard():
    global _storyboard
    if _storyboard is None:
        from ordem.story import StoryBoard
        _storyboard = StoryBoard(max_scenes=int(_config.get("story_limit", 120)))
        transcript = _config.get("story_transcript")
        if transcript:
            _storyboard.load_jsonl(transcript)
    return _storyboard


async def _broadcast(event: dict) -> None:
    if event.get("type") == "event":
        resolver = get_thumbnail_resolver()
        for detection in event.get("detections") or []:
            thumbnail = resolver.resolve(detection)
            if thumbnail:
                detection["thumbnail"] = thumbnail
        event["story_scene"] = get_storyboard().add_event(event)
    if _transcript_store is not None and event.get("type") == "event":
        _transcript_store.append(event, event.get("origin", "unknown"))
    _history.append(event)
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
    from ordem.audio import (
        auto_select_devices,
        describe_devices,
        frames_from_devices,
        frames_from_mic,
        frames_from_wav,
    )

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
        _emit_from_thread({"type": "event", "origin": "audio", **ev.to_json()})
    _emit_from_thread({"type": "end"})


@app.on_event("startup")
async def _startup() -> None:
    global _loop, _transcript_store
    _loop = asyncio.get_running_loop()
    transcript_log = _config.get("transcript_log")
    if transcript_log and _transcript_store is None:
        from ordem.transcripts import TranscriptStore
        _transcript_store = TranscriptStore(transcript_log)
        print(f"Transcrições: {_transcript_store.markdown_path}")
    if _config.get("source") in ("mic", "wav", "devices"):
        threading.Thread(target=_audio_worker, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "version": APP_VERSION, "source": _config.get("source"),
            "clients": len(_clients), "transcript_log": _transcript_store is not None}


@app.get("/story")
async def story() -> dict:
    return {"scenes": get_storyboard().to_json()}


@app.post("/simulate")
async def simulate(inp: SimulateIn) -> dict:
    """Detecta mecânicas num texto e transmite como evento (teste sem áudio)."""
    ev = get_pipeline().detect_text(inp.text)
    await _broadcast({"type": "event", "origin": "manual", **ev.to_json()})
    return {"detections": len(ev.detections)}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    await websocket.send_text(json.dumps({"type": "hello",
                                          "source": _config.get("source")}))
    for ev in _history:
        await websocket.send_text(json.dumps(ev, ensure_ascii=False))
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
    ap.add_argument("--transcript-log", metavar="DIRETORIO",
                    help="salva JSONL e Markdown para revisão (desativado por padrão)")
    ap.add_argument("--assets-dir", action="append", default=[], metavar="DIRETORIO",
                    help="pasta extra de tokens/imagens; pode ser repetido")
    ap.add_argument("--story-transcript", metavar="JSONL",
                    help="carrega uma transcrição JSONL anterior na aba História")
    ap.add_argument("--story-limit", type=int, default=120,
                    help="máximo de cenas mantidas em memória (default: 120)")
    ap.add_argument("--reload", action="store_true",
                    help="recarrega o servidor quando arquivos .py/.html mudarem")
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
        transcript_log=args.transcript_log,
        asset_dirs=args.assets_dir,
        story_transcript=args.story_transcript, story_limit=max(1, args.story_limit),
    )

    os.environ[ENV_CONFIG] = json.dumps(_config, ensure_ascii=False)

    import uvicorn
    print(f"→ http://{args.host}:{args.port}  (fonte: {_config['source']})")
    if args.reload:
        uvicorn.run("server:app", host=args.host, port=args.port,
                    log_level="warning", reload=True,
                    reload_dirs=[str(Path(__file__).parent)],
                    reload_includes=["*.py", "*.html"],
                    reload_excludes=["*.pyc", "__pycache__/*"])
    else:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
