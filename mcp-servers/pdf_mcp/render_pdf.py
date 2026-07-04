#!/usr/bin/env python
"""Standalone-PDF-Renderer — läuft als SUBPROZESS des pdf-MCP-Servers.

Hintergrund: fpdf2/fontTools geben beim Font-Subsetting viel aus und vertragen sich
im selben Prozess nicht mit dem laufenden MCP-stdio-Eventloop (zerschießt das
JSON-RPC). Als eigener Prozess ist die Ausgabe vollständig isoliert (der Server
fängt sie mit capture_output ab und verwirft sie).

Aufruf:  python render_pdf.py <input.json>
  input.json = {"title": str, "content": str, "out": absoluter_pfad}
Schreibt eine JSON-Zeile auf stdout: {"pages": N}  oder  {"error": "..."}.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_WIN_FONTS = {
    "": r"C:\Windows\Fonts\arial.ttf",
    "B": r"C:\Windows\Fonts\arialbd.ttf",
    "I": r"C:\Windows\Fonts\ariali.ttf",
    "BI": r"C:\Windows\Fonts\arialbi.ttf",
}


def render(title: str, content: str, out_path: Path) -> int:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    # Unicode-Schrift (Arial) registrieren; Fallback Helvetica (nur Latin-1).
    fam, styles = "Helvetica", {""}
    reg = []
    for style, fpath in _WIN_FONTS.items():
        if os.path.exists(fpath):
            try:
                pdf.add_font("Doc", style, fpath)
                reg.append(style)
            except Exception:  # noqa: BLE001
                pass
    if "" in reg:
        fam, styles = "Doc", set(reg)
    md_ok = fam == "Doc" and {"B", "I"} <= styles

    def line(txt: str, size: int, *, bold: bool = False, bullet: bool = False):
        pdf.set_font(fam, "B" if (bold and "B" in styles) else "", size)
        body = ("•  " + txt) if bullet else txt
        if fam == "Helvetica":
            body = body.encode("latin-1", "replace").decode("latin-1")
        pdf.set_x(pdf.l_margin)
        kw = dict(new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        try:
            pdf.multi_cell(0, size * 0.55, body, markdown=md_ok and not bold, **kw)
        except Exception:  # noqa: BLE001
            try:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, size * 0.55, body, markdown=False, **kw)
            except Exception:  # noqa: BLE001
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, size * 0.55, body[:1000], markdown=False, **kw)

    line(title.strip() or "Dokument", 18, bold=True)
    pdf.ln(2)
    pdf.set_draw_color(160, 160, 160)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    for raw in content.replace("\r\n", "\n").split("\n"):
        s = raw.rstrip()
        if not s.strip():
            pdf.ln(2)
            continue
        if s.startswith("### "):
            pdf.ln(1); line(s[4:], 12, bold=True)
        elif s.startswith("## "):
            pdf.ln(1); line(s[3:], 13, bold=True)
        elif s.startswith("# "):
            pdf.ln(1); line(s[2:], 15, bold=True)
        elif s.lstrip().startswith(("- ", "* ")):
            line(s.lstrip()[2:], 11, bullet=True)
        else:
            line(s, 11)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return pdf.page_no()


def main() -> int:
    try:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        pages = render(data["title"], data.get("content", ""), Path(data["out"]))
        sys.stdout.write(json.dumps({"pages": pages}))
        return 0
    except Exception as e:  # noqa: BLE001
        sys.stdout.write(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
