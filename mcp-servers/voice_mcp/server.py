"""voice-mcp — Lokaler Voice-Loop (N2): Transkription + Sprachsynthese.

Tools:
  transcribe(audio_file, language)  — Audio → Text  (faster-whisper, lokal)
  speak(text, output_file, voice)   — Text → Audio   (Piper TTS, lokal)

Beide Tools laufen komplett lokal ohne Cloud-Key.

INSTALLATION (einmalig):
  pip install faster-whisper
  # Piper-Binary: https://github.com/rhasspy/piper/releases
  # z.B. piper_windows_amd64.zip entpacken nach n:/allinall/piper/
  # Deutsche Stimme: de_DE-thorsten-medium.onnx + .json ins gleiche Verzeichnis
  #   https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium
  # ffmpeg: winget install ffmpeg  (für .ogg -> .wav Konvertierung)

Start (stdio):  python server.py
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("voice-mcp")

_PIPER_DIR = Path(os.environ.get("PIPER_DIR", r"n:\allinall\piper"))
_PIPER_EXE = _PIPER_DIR / "piper.exe"
_DEFAULT_VOICE = os.environ.get("PIPER_VOICE", "de_DE-thorsten-medium")
_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
_WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
_OUTPUT_DIR = Path(r"n:\allinall\openclaw-workspace\output")

_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Whisper-Modell wird lazy geladen (erster Aufruf)
_whisper = None


def _get_whisper():
    global _whisper
    if _whisper is not None:
        return _whisper
    try:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(_WHISPER_MODEL, device=_WHISPER_DEVICE,
                                compute_type="int8")
        return _whisper
    except ImportError:
        return None


def _to_wav(audio_path: Path) -> Path:
    """Konvertiert beliebiges Audioformat nach WAV (via ffmpeg)."""
    if audio_path.suffix.lower() == ".wav":
        return audio_path
    wav_path = audio_path.with_suffix(".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), str(wav_path)],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
        return wav_path
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg nicht gefunden. Installation: winget install ffmpeg"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg-Konvertierung fehlgeschlagen: {e.stderr.decode()[:200]}")


@mcp.tool()
def transcribe(audio_file: str, language: str = "de") -> str:
    """Transkribiert eine Audiodatei lokal via faster-whisper.

    Args:
        audio_file: Absoluter Pfad zur Audiodatei (.ogg, .wav, .mp3, .m4a)
        language:   Sprache (Standard: 'de' für Deutsch)

    Returns:
        Transkribierter Text oder Fehlermeldung.
    """
    model = _get_whisper()
    if model is None:
        return (
            "[voice-mcp] faster-whisper nicht installiert.\n"
            "Installation: pip install faster-whisper\n"
            "Danach Gateway neu starten."
        )

    audio_path = Path(audio_file)
    if not audio_path.exists():
        return f"[voice-mcp] Datei nicht gefunden: {audio_file}"

    try:
        wav = _to_wav(audio_path)
        segments, info = model.transcribe(
            str(wav), language=language, beam_size=5, vad_filter=True
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        lang_detected = info.language
        return (
            f"[Transkription ({lang_detected}, {info.duration:.1f}s)]\n{text}"
            if text else "[voice-mcp] Keine Sprache erkannt (leise oder stille Aufnahme?)"
        )
    except RuntimeError as e:
        return f"[voice-mcp] Fehler: {e}"
    except Exception as e:
        return f"[voice-mcp] Unerwarteter Fehler: {e}"


@mcp.tool()
def speak(text: str, output_file: str = "", voice: str = "") -> str:
    """Synthetisiert Text zu einer Sprachdatei via Piper TTS.

    Args:
        text:        Zu sprechender Text (Deutsch)
        output_file: Ausgabepfad (.wav); leer = automatischer Pfad in output/
        voice:       Piper-Stimme (leer = Standard de_DE-thorsten-medium)

    Returns:
        Pfad zur erzeugten WAV-Datei oder Fehlermeldung.
    """
    if not _PIPER_EXE.exists():
        return (
            f"[voice-mcp] Piper nicht gefunden: {_PIPER_EXE}\n"
            "Download: https://github.com/rhasspy/piper/releases\n"
            "Entpacken nach n:\\allinall\\piper\\ und deutsche Stimme mitladen:\n"
            "  de_DE-thorsten-medium.onnx + .json aus:\n"
            "  https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium"
        )

    voice_name = voice or _DEFAULT_VOICE
    voice_model = _PIPER_DIR / f"{voice_name}.onnx"
    if not voice_model.exists():
        return (
            f"[voice-mcp] Stimme nicht gefunden: {voice_model}\n"
            "Bitte .onnx + .json von HuggingFace laden (rhasspy/piper-voices)."
        )

    if output_file:
        out_path = Path(output_file)
    else:
        import time
        out_path = _OUTPUT_DIR / f"speech_{int(time.time())}.wav"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        proc = subprocess.run(
            [
                str(_PIPER_EXE),
                "--model", str(voice_model),
                "--output_file", str(out_path),
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return f"[voice-mcp] Piper-Fehler: {proc.stderr.decode()[:300]}"
        return str(out_path)
    except subprocess.TimeoutExpired:
        return "[voice-mcp] Piper-Timeout (Text zu lang?)"
    except Exception as e:
        return f"[voice-mcp] Fehler: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
