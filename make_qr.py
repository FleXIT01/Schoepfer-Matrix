# Erzeugt aus der `openclaw qr --json` Ausgabe ein scannbares QR-PNG.
# Robust gegen UTF-8/UTF-16/BOM (cmd.exe vs PowerShell Redirection).
import json
import os
import sys

import qrcode

OUT = r"n:\allinall\openclaw-workspace\output"
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "ocqr.json")

raw = open(src, "rb").read()
# Null-Bytes (UTF-16) entfernen + BOM weg, dann als Text lesen.
text = raw.replace(b"\x00", b"").decode("utf-8", errors="ignore").lstrip("﻿")
# Nur den JSON-Block herausschneiden (falls Banner davor/danach stehen).
block = text[text.find("{"): text.rfind("}") + 1]
code = json.loads(block)["setupCode"]

os.makedirs(OUT, exist_ok=True)
qrcode.make(code).save(os.path.join(OUT, "clawhub_pairing_qr.png"))
open(os.path.join(OUT, "clawhub_setupcode.txt"), "w", encoding="utf-8").write(code)
print("Setup-Code:", code)
