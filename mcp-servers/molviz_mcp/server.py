"""molviz-mcp — 3D-Visualisierung von Proteinen & Molekülen als MCP-Server.

Erzeugt interaktive 3D-Ansichten als eigenständige HTML-Datei (3Dmol.js):
  - Proteine: Struktur per PDB-ID (RCSB) oder UniProt-ID (AlphaFold)
  - Kleine Moleküle: aus SMILES (3D-Koordinaten via NCI CACTUS)

KEINE schwere Installation (kein PyMOL/RDKit nötig) — die Strukturdaten werden
serverseitig geholt und in eine HTML-Datei eingebettet, die im Browser drehbar/
zoombar ist. Ersetzt die Rolle von PyMOL/Foldseek für die Alltags-Visualisierung.

Tools:
  - protein_3d(identifier)  -> HTML-Datei mit interaktiver Protein-3D-Ansicht
  - molecule_3d(smiles)     -> HTML-Datei mit interaktiver Molekül-3D-Ansicht

Start (stdio):  python server.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("molviz-mcp")

_OUTDIR = Path(os.environ.get("MOLVIZ_OUTDIR",
                              r"n:/allinall/openclaw-workspace/molviz"))

_HTML = """<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><title>{title}</title>
<script src="https://3Dmol.org/build/3Dmol-min.js"></script>
<style>html,body{{margin:0;height:100%}}#v{{width:100vw;height:100vh;position:relative}}
#cap{{position:fixed;top:8px;left:8px;font:14px sans-serif;background:#fff8;padding:4px 8px;border-radius:4px}}</style>
</head><body>
<div id="cap">{title}</div><div id="v"></div>
<script>
var data = `{data}`;
var viewer = $3Dmol.createViewer("v", {{backgroundColor:"white"}});
viewer.addModel(data, "{fmt}");
{style}
viewer.zoomTo(); viewer.render();
</script></body></html>"""


def _fetch(url: str) -> tuple[str, str]:
    """(text, fehler). Holt Strukturdaten per HTTP."""
    import httpx
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        return "", f"Abruf fehlgeschlagen: {e}"
    if r.status_code != 200 or not r.text.strip():
        return "", f"HTTP {r.status_code} bei {url}"
    return r.text, ""


def _write_html(name: str, title: str, data: str, fmt: str, style_js: str) -> str:
    _OUTDIR.mkdir(parents=True, exist_ok=True)
    html = _HTML.format(title=title, data=data.replace("`", "'"), fmt=fmt, style=style_js)
    out = _OUTDIR / f"{name}.html"
    out.write_text(html, encoding="utf-8")
    return str(out)


@mcp.tool()
def protein_3d(identifier: str, style: str = "cartoon") -> str:
    """Erzeugt eine interaktive 3D-Ansicht einer Proteinstruktur als HTML-Datei.
    `identifier` = PDB-ID (4 Zeichen, z.B. '1TUP') ODER UniProt-ID (AlphaFold,
    z.B. 'P04637'). `style` = 'cartoon' (Standard) oder 'surface'. Gibt den Pfad
    zur HTML-Datei zurück — im Browser öffnen zum Drehen/Zoomen."""
    ident = identifier.strip()
    is_pdb = bool(re.fullmatch(r"[0-9][A-Za-z0-9]{3}", ident))
    if is_pdb:
        url = f"https://files.rcsb.org/download/{ident.upper()}.pdb"
        src = f"RCSB PDB {ident.upper()}"
    else:
        url = f"https://alphafold.ebi.ac.uk/files/AF-{ident.upper()}-F1-model_v4.pdb"
        src = f"AlphaFold {ident.upper()}"
    data, err = _fetch(url)
    if err:
        return (f"[Fehler: Struktur '{ident}' nicht gefunden ({err}). "
                f"Bei UniProt-IDs ohne AlphaFold-Modell ggf. PDB-ID nutzen.]")
    if style == "surface":
        style_js = ("viewer.setStyle({}, {cartoon:{color:'spectrum'}});"
                    "viewer.addSurface($3Dmol.SurfaceType.VDW, {opacity:0.7,color:'white'});")
    else:
        style_js = "viewer.setStyle({}, {cartoon:{color:'spectrum'}});"
    path = _write_html(f"protein_{ident.upper()}", f"{src}", data, "pdb", style_js)
    return (f"3D-Ansicht erzeugt: {path}\nQuelle: {src}\n"
            f"Im Browser öffnen — drehbar (Maus), zoombar (Scroll). Stil: {style}.")


@mcp.tool()
def molecule_3d(smiles: str, name: str = "molekuel") -> str:
    """Erzeugt eine interaktive 3D-Ansicht eines kleinen Moleküls aus seinem SMILES.
    `smiles` = SMILES-String (z.B. 'CC(=O)Oc1ccccc1C(=O)O' für Aspirin),
    `name` = Dateiname-Basis. 3D-Koordinaten kommen von NCI CACTUS. Gibt den Pfad
    zur HTML-Datei zurück — im Browser öffnen (Sticks-Darstellung, drehbar)."""
    from urllib.parse import quote
    url = f"https://cactus.nci.nih.gov/chemical/structure/{quote(smiles, safe='')}/file?format=sdf&get3d=true"
    data, err = _fetch(url)
    if err or "V2000" not in data and "V3000" not in data:
        return (f"[Fehler: konnte kein 3D-Modell für SMILES '{smiles}' erzeugen "
                f"({err or 'kein gültiges SDF'}). SMILES prüfen.]")
    style_js = ("viewer.setStyle({}, {stick:{radius:0.15}, sphere:{scale:0.25}});")
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40] or "molekuel"
    path = _write_html(f"mol_{safe}", f"Molekül: {smiles}", data, "sdf", style_js)
    return (f"3D-Ansicht erzeugt: {path}\nSMILES: {smiles}\n"
            f"Im Browser öffnen — drehbar (Maus), zoombar (Scroll).")


if __name__ == "__main__":
    mcp.run()
