"""totp.py — TOTP-Zweifaktor fuer die scharfe Klasse der Schoepfer-Matrix (Phase A).

Secret: n:/allinall/openclaw-workspace/state/totp_secret.json
Setup:  totp.setup() -> gibt otpauth:// URI zurueck -> in Authenticator-App scannen
Pruefen: totp.verify("123456") -> True/False

Scharfe Klasse (sharp=True im gate_middleware):
  - Mail an neue / unbekannte Empfaenger
  - Shell ausserhalb des Workspace
  - Git-Push, PR-Erstellung
"""
from __future__ import annotations

import json
from pathlib import Path

_SECRET_FILE = Path(r"n:\allinall\openclaw-workspace\state\totp_secret.json")
_ISSUER = "Schoepfer-Matrix"
_ACCOUNT = "felix@matrix"


def _load_secret() -> str | None:
    if _SECRET_FILE.exists():
        try:
            return json.loads(_SECRET_FILE.read_text(encoding="utf-8")).get("secret")
        except Exception:
            return None
    return None


def is_ready() -> bool:
    """True wenn ein TOTP-Secret eingerichtet ist."""
    return _load_secret() is not None


def setup() -> str:
    """Neuen TOTP-Secret generieren und speichern. Gibt Setup-String zurueck."""
    try:
        import pyotp
    except ImportError:
        return "[Fehler: pyotp nicht installiert. pip install pyotp ausfuehren.]"
    secret = pyotp.random_base32()
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_text(json.dumps({"secret": secret}), encoding="utf-8")
    uri = pyotp.TOTP(secret).provisioning_uri(name=_ACCOUNT, issuer_name=_ISSUER)
    return (
        f"TOTP eingerichtet.\n"
        f"Secret: {secret}\n"
        f"URI fuer Authenticator-App:\n{uri}\n\n"
        f"In Google Authenticator / Aegis / Bitwarden Authenticator einscannen.\n"
        f"Danach: totp_verify('123456') testen."
    )


def verify(code: str) -> bool:
    """6-stelligen TOTP-Code pruefen. False wenn kein Secret oder Code falsch."""
    secret = _load_secret()
    if not secret:
        return False
    try:
        import pyotp
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False


if __name__ == "__main__":
    print("TOTP-Status:", "bereit" if is_ready() else "kein Secret (setup() ausfuehren)")
    if not is_ready():
        print(setup())
