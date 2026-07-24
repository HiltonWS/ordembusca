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
from pathlib import Path
from typing import Iterator

import numpy as np
import webrtcvad

SAMPLE_RATE = 16000          # Whisper e webrtcvad
FRAME_MS = 30                # webrtcvad aceita 10/20/30 ms
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000       # 480
FRAME_BYTES = FRAME_SAMPLES * 2                      # int16 = 2 bytes


def _get_sounddevice():
    try:
        import sounddevice as sd
        return sd
    except OSError:
        raise SystemExit(
            "PortAudio nao encontrado. Instale com: sudo apt update && "
            "sudo apt install -y portaudio19-dev\n"
            "Em Codespaces web, captura de audio pode nao estar disponivel; "
            "use --wav ou --demo."
        ) from None


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
    """Frames de 30ms a partir de um WAV (convertido para 16kHz mono int16).

    Leitura em streaming para suportar arquivos grandes sem estourar memoria.
    """
    import soundfile as sf

    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Arquivo WAV não encontrado: {path}")
    if p.is_dir():
        raise SystemExit(
            f"{path!r} é uma pasta. Use um arquivo .wav, por exemplo: "
            "samples/videoplayback.wav"
        )

    pending = bytearray()
    with sf.SoundFile(str(p), "r") as f:
        sr = int(f.samplerate)
        block_frames = max(sr, FRAME_SAMPLES)  # ~1s por bloco na taxa nativa
        for block in f.blocks(blocksize=block_frames, dtype="int16", always_2d=True):
            mono = block[:, 0]  # canal 0 (mono)
            if sr != SAMPLE_RATE:
                mono = _resample_int16(mono, sr, SAMPLE_RATE)
            pending.extend(mono.tobytes())
            while len(pending) >= FRAME_BYTES:
                yield bytes(pending[:FRAME_BYTES])
                del pending[:FRAME_BYTES]

    # Fecha o arquivo emitindo um ultimo frame preenchido com silencio.
    if pending:
        pad = FRAME_BYTES - len(pending)
        pending.extend(b"\x00" * pad)
        yield bytes(pending)


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
    yield from frames_from_devices([device if device is not None else None])


# ---- Captura multi-dispositivo (mic + loopback do sistema) ---------------

def list_input_devices() -> list[dict]:
    """Dispositivos de entrada disponíveis, marcando prováveis loopbacks.

    Loopback = dispositivo que captura o que VOCÊ ESCUTA (saída do sistema:
    Discord, vídeos...). No Linux (Pulse/PipeWire) são os '*.monitor';
    no Windows, 'Stereo Mix' ou cabos virtuais (VB-Cable); no macOS,
    drivers como BlackHole.
    """
    sd = _get_sounddevice()

    marks = ("monitor", "loopback", "stereo mix", "mix", "blackhole",
             "vb-audio", "cable output", "what u hear")
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            name = d["name"]
            out.append({
                "index": i,
                "name": name,
                "samplerate": int(d.get("default_samplerate") or SAMPLE_RATE),
                "loopback": any(m in name.lower() for m in marks),
            })
    return out


def _choose_auto_devices(entries: list[dict], default_index: int | None) -> list[int]:
    """Escolhe dispositivos para capturar entrada e saida automaticamente.

    Prioridade:
    1) microfone (nao-loopback) + loopback
    2) entrada padrao
    3) primeiro dispositivo de entrada
    """
    if not entries:
        return []

    by_index = {int(d["index"]): d for d in entries}
    mics = [d for d in entries if not d["loopback"]]
    loops = [d for d in entries if d["loopback"]]

    if mics and loops:
        mic = next((d for d in mics if int(d["index"]) == default_index), mics[0])
        loop = next((d for d in loops if int(d["index"]) == default_index), loops[0])
        if int(loop["index"]) == int(mic["index"]):
            loop = next((d for d in loops if int(d["index"]) != int(mic["index"])), loop)
        return [int(mic["index"]), int(loop["index"])]

    if default_index is not None and default_index in by_index:
        return [int(default_index)]
    return [int(entries[0]["index"])]


def auto_select_devices(require_loopback: bool = False) -> list[int]:
    """Seleciona automaticamente entrada(s) para transcrever mesa online.

    Retorna [mic, loopback] quando possivel. Se nao houver loopback,
    retorna [mic] por padrao.
    """
    sd = _get_sounddevice()

    entries = list_input_devices()
    if not entries:
        raise SystemExit(
            "Nenhum dispositivo de entrada encontrado. "
            "No Codespaces web isso e comum; use --wav ou --demo."
        )

    default_index: int | None = None
    try:
        info = sd.query_devices(None, "input")
        default_index = int(info.get("index", sd.default.device[0]))
    except (ValueError, sd.PortAudioError, TypeError, IndexError):
        default_index = None

    chosen = _choose_auto_devices(entries, default_index)
    if require_loopback and len(chosen) < 2:
        raise SystemExit(
            "Nao encontrei dispositivo de loopback para capturar a saida do sistema. "
            "Use --list-mics e selecione manualmente --devices <mic> <loopback>."
        )
    return chosen


def describe_devices(indices: list[int]) -> str:
    """Texto curto com nome dos dispositivos selecionados."""
    sd = _get_sounddevice()

    parts: list[str] = []
    for idx in indices:
        try:
            info = sd.query_devices(idx)
            parts.append(f"[{idx}] {info.get('name', 'desconhecido')}")
        except (ValueError, sd.PortAudioError):
            parts.append(f"[{idx}] desconhecido")
    return " + ".join(parts)


def mix_float_blocks(blocks: "list[np.ndarray]") -> bytes:
    """Soma blocos float32 [-1,1] de mesmo tamanho e converte p/ PCM16.

    Puro e testável: é o coração da mixagem mic+loopback.
    """
    if not blocks:
        return b""
    mix = np.sum(np.stack(blocks, axis=0), axis=0)
    mix = np.clip(mix, -1.0, 1.0)
    return (mix * 32767.0).astype(np.int16).tobytes()


def _resolve_input_device(device):
    """Resolve (índice, info) de um dispositivo de ENTRADA.

    - device=None: usa a entrada padrão do sistema; se não houver,
      cai para o primeiro dispositivo de entrada disponível.
    - índice inválido ou de saída: erro claro listando as entradas.
    """
    sd = _get_sounddevice()

    if device is None:
        try:
            info = sd.query_devices(None, "input")
            return info.get("index", sd.default.device[0]), info
        except (ValueError, sd.PortAudioError):
            for d in list_input_devices():
                return d["index"], sd.query_devices(d["index"])
            raise SystemExit(
                "Nenhum dispositivo de ENTRADA de áudio encontrado. "
                "Verifique se o microfone está conectado e se o PortAudio "
                "está instalado (Linux: sudo apt install portaudio19-dev)."
            ) from None
    try:
        return device, sd.query_devices(device, "input")
    except (ValueError, sd.PortAudioError) as e:
        entradas = "\n  ".join(
            f"[{d['index']}] {d['name']}" + ("  [LOOPBACK]" if d["loopback"] else "")
            for d in list_input_devices()
        ) or "(nenhuma)"
        raise SystemExit(
            f"O dispositivo {device!r} não é um dispositivo de ENTRADA válido "
            f"({e}).\nEntradas disponíveis:\n  {entradas}\n"
            "Dica: use os índices mostrados por --list-mics; para capturar o "
            "que você escuta, escolha um marcado como [LOOPBACK] (no Linux, "
            "'Monitor of ...')."
        ) from e


class _DeviceReader:
    """Lê um dispositivo em thread própria e entrega float32 mono 16kHz."""

    def __init__(self, device: int | str | None):
        import threading

        sd = _get_sounddevice()

        index, info = _resolve_input_device(device)
        self.native_sr = SAMPLE_RATE          # ajustado após abrir o stream
        self._buf = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

        def callback(indata, frames, time_info, status):  # noqa: ANN001
            mono = indata.mean(axis=1) if indata.ndim > 1 else indata[:, 0]
            data = mono.astype(np.float32)
            if self.native_sr != SAMPLE_RATE:
                data = _resample_f32(data, self.native_sr, SAMPLE_RATE)
            with self._cv:
                self._buf = np.concatenate([self._buf, data])
                self._cv.notify()

        try:
            # samplerate=None deixa o PortAudio escolher a taxa nativa do
            # dispositivo (evita erro em placas que não aceitam 16 kHz).
            self.stream = sd.InputStream(
                device=index,
                channels=max(1, min(2, int(info["max_input_channels"]))),
                samplerate=None, dtype="float32",
                blocksize=0, callback=callback,
            )
        except sd.PortAudioError as e:
            raise SystemExit(
                f"Falha ao abrir o dispositivo [{index}] {info.get('name')}: {e}"
            ) from e
        self.native_sr = int(self.stream.samplerate)

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()
        self.stream.close()

    def pop(self, n: int, wait: bool) -> np.ndarray:
        """Retira n amostras. wait=True bloqueia até ter; wait=False completa
        com zeros (dispositivos secundários não devem travar o fluxo)."""
        with self._cv:
            if wait:
                while len(self._buf) < n:
                    self._cv.wait(timeout=0.5)
            take = self._buf[:n]
            self._buf = self._buf[n:]
        if len(take) < n:
            take = np.concatenate([take, np.zeros(n - len(take), np.float32)])
        return take


def _resample_f32(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(data) == 0:
        return data
    n_out = int(round(len(data) * sr_out / sr_in))
    x_old = np.linspace(0, 1, len(data), endpoint=False)
    x_new = np.linspace(0, 1, n_out, endpoint=False)
    return np.interp(x_new, x_old, data).astype(np.float32)


def frames_from_devices(devices: list) -> Iterator[bytes]:
    """Frames de 30ms mixando 1+ dispositivos de entrada.

    Uso típico: [índice_do_microfone, índice_do_loopback] para transcrever
    o que você fala E o que você escuta (os outros jogadores no Discord).
    O primeiro dispositivo dita o ritmo; os demais entram com o que tiverem
    (zeros se atrasados), evitando travas por drift de clock.
    """
    readers = [_DeviceReader(d) for d in devices]
    for r in readers:
        r.start()
    try:
        while True:
            blocks = [readers[0].pop(FRAME_SAMPLES, wait=True)]
            for r in readers[1:]:
                blocks.append(r.pop(FRAME_SAMPLES, wait=False))
            yield mix_float_blocks(blocks)
    finally:
        for r in readers:
            r.stop()


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
