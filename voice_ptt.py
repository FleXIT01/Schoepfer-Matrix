"""voice_ptt.py — Freihändige Sprachsteuerung der Schöpfer-Matrix (Push-to-Talk).

Taste HALTEN (Standard: F8) → sprechen → loslassen:
  Mikrofon → faster-whisper (lokal, CPU) → Gateway /v1/chat/completions
  (gleicher Agent wie Telegram, mit allen Tools) → Antwort → Piper TTS → Lautsprecher.

Voraussetzungen:
  - Gateway läuft (gateway.cmd) und chatCompletions-Endpoint ist aktiviert
  - pip install keyboard sounddevice faster-whisper
  - Piper in <MATRIX_ROOT>\\piper\\ mit deutscher Stimme (wie voice_mcp)

Konfiguration (matrix.env, optional):
  VOICE_PTT_KEY=f8          Push-to-Talk-Taste
  VOICE_TTS_MAX_CHARS=500   längere Antworten werden nur gedruckt, nicht vorgelesen
  WHISPER_MODEL=small       faster-whisper-Modellgröße
Start: voice.cmd  (oder: python voice_ptt.py)
Beenden: Strg+C im Fenster.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# matrix.env + secrets.env laden (wie env.cmd, damit der Direktstart auch geht)
for envfile in (ROOT / "matrix.env", ROOT / "secrets.env"):
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

GATEWAY_URL = os.environ.get("VOICE_GATEWAY_URL", "http://127.0.0.1:18789").rstrip("/")
PTT_KEY = os.environ.get("VOICE_PTT_KEY", "f8").lower()
TTS_MAX = int(os.environ.get("VOICE_TTS_MAX_CHARS", "500"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
PIPER_DIR = Path(os.environ.get("PIPER_DIR", str(ROOT / "piper")))
PIPER_VOICE = os.environ.get("PIPER_VOICE", "de_DE-thorsten-medium")
SAMPLE_RATE = 16000
MIN_SECONDS = 0.4  # kürzere Aufnahmen = Fehltipps, werden verworfen
SESSION_KEY = "voice-ptt"


def _gateway_token() -> str:
    """Gateway-Token aus Umgebung oder der Gateway-Config — nie hartkodiert.
    WICHTIG: gateway.cmd setzt OPENCLAW_STATE_DIR auf openclaw-workspace/state —
    DORT liegt die echte Config; ~/.openclaw ist nur der Fallback."""
    tok = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
    if tok:
        return tok
    for cfg_path in (ROOT / "openclaw-workspace" / "state" / "openclaw.json",
                     Path.home() / ".openclaw" / "openclaw.json"):
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            tok = cfg.get("gateway", {}).get("auth", {}).get("token", "")
            if tok:
                return tok
        except Exception:
            continue
    return ""


def _beep(freq: int, ms: int) -> None:
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        pass


def _record_while_held(keyboard, sd) -> "list":
    """Nimmt auf, solange die PTT-Taste gehalten wird. Gibt Audio-Frames zurück."""
    frames: list = []

    def _cb(indata, _frames, _time, _status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        callback=_cb):
        while keyboard.is_pressed(PTT_KEY):
            time.sleep(0.03)
    return frames


def _save_wav(frames, path: Path) -> float:
    """Schreibt Frames als 16-kHz-Mono-WAV. Gibt die Dauer in Sekunden zurück."""
    import numpy as np
    audio = np.concatenate(frames, axis=0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return len(audio) / SAMPLE_RATE


def _ask_gateway(httpx, token: str, text: str) -> str:
    r = httpx.post(
        f"{GATEWAY_URL}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "x-openclaw-session-key": SESSION_KEY,  # eigene fortlaufende Voice-Session
        },
        json={"model": "openclaw", "messages": [{"role": "user", "content": text}]},
        timeout=httpx.Timeout(600.0, connect=10.0),  # Tool-Läufe dürfen dauern
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


_MD_JUNK = re.compile(r"```.*?```|`|[*_#>|]|\[([^\]]*)\]\([^)]*\)|https?://\S+", re.S)


def _speak(reply: str) -> None:
    """Antwort vorlesen (Piper). Markdown/Links raus, lange Antworten kürzen."""
    text = _MD_JUNK.sub(lambda m: m.group(1) or " ", reply).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return
    if len(text) > TTS_MAX:
        text = text[:TTS_MAX].rsplit(" ", 1)[0] + " … Rest steht im Fenster."
    piper = PIPER_DIR / "piper.exe"
    model = PIPER_DIR / f"{PIPER_VOICE}.onnx"
    if not piper.exists() or not model.exists():
        print("  [i] Piper nicht gefunden — Antwort nur als Text.")
        return
    out = Path(tempfile.gettempdir()) / "matrix_ptt_reply.wav"
    try:
        subprocess.run([str(piper), "--model", str(model), "--output_file", str(out)],
                       input=text.encode("utf-8"), capture_output=True, timeout=120,
                       cwd=str(PIPER_DIR))
        import winsound
        winsound.PlaySound(str(out), winsound.SND_FILENAME)
    except Exception as e:  # noqa: BLE001
        print(f"  [i] TTS übersprungen ({type(e).__name__}: {e})")


def main() -> int:
    print("=" * 62)
    print(" Schöpfer-Matrix — Voice Push-to-Talk")
    print(f" Taste [{PTT_KEY.upper()}] HALTEN und sprechen. Strg+C beendet.")
    print("=" * 62)

    try:
        import httpx
        import keyboard
        import sounddevice as sd
    except ImportError as e:
        print(f"[FEHLER] Paket fehlt: {e.name}. -> pip install keyboard sounddevice httpx")
        return 1

    token = _gateway_token()
    if not token:
        print("[FEHLER] Kein Gateway-Token gefunden (~/.openclaw/openclaw.json).")
        return 1

    # Gateway-Check: läuft es, ist der Endpoint an?
    try:
        r = httpx.get(f"{GATEWAY_URL}/v1/models",
                      headers={"Authorization": f"Bearer {token}"}, timeout=5)
        r.raise_for_status()
        print(f"[ok] Gateway erreichbar: {GATEWAY_URL}")
    except Exception as e:  # noqa: BLE001
        print(f"[FEHLER] Gateway nicht erreichbar ({type(e).__name__}). "
              f"Erst gateway.cmd starten. ({GATEWAY_URL}/v1/models)")
        return 1

    print(f"[..] Lade Whisper-Modell '{WHISPER_MODEL}' ({WHISPER_DEVICE}) ...")
    from faster_whisper import WhisperModel
    whisper = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type="int8")
    print("[ok] Bereit. Taste halten und sprechen.")

    wav = Path(tempfile.gettempdir()) / "matrix_ptt_input.wav"
    while True:
        try:
            keyboard.wait(PTT_KEY)
            _beep(880, 100)
            frames = _record_while_held(keyboard, sd)
            _beep(440, 100)
            if not frames:
                continue
            dur = _save_wav(frames, wav)
            if dur < MIN_SECONDS:
                continue

            segments, _info = whisper.transcribe(str(wav), language="de", vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
            if not text:
                print("  [i] Nichts verstanden.")
                continue
            print(f"\n🎤 Du: {text}")

            print("  [..] Matrix denkt ...")
            try:
                reply = _ask_gateway(httpx, token, text)
            except Exception as e:  # noqa: BLE001
                print(f"  [FEHLER] Gateway: {type(e).__name__}: {e}")
                _beep(220, 300)
                continue
            print(f"🧠 Matrix: {reply}\n")
            _speak(reply)
        except KeyboardInterrupt:
            print("\n[ok] Voice-PTT beendet.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
