---
name: mol-viz
description: "Proteine und Moleküle interaktiv in 3D visualisieren (als HTML-Datei, im Browser drehbar)."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧬",
        "requires": { "mcp": ["molviz"] }
      }
  }
---

# Mol-Viz — 3D-Visualisierung von Strukturen

Trigger: „zeig mir die Struktur von …", „visualisiere Protein/Molekül …",
„3D-Ansicht von PDB … / AlphaFold … / SMILES …".

Self-contained via `molviz`-MCP (3Dmol.js, keine Installation). Erzeugt eine
HTML-Datei, die im Browser interaktiv (drehbar/zoombar) ist.

## Ablauf

1. PROTEIN: `molviz.protein_3d(identifier)` — `identifier` = PDB-ID (z.B. `1TUP`)
   ODER UniProt-ID (AlphaFold, z.B. `P04637`). `style="surface"` für Oberfläche.
2. MOLEKÜL: `molviz.molecule_3d(smiles)` — kleine Moleküle aus SMILES
   (z.B. aus `science.chembl_search` → SMILES → 3D-Ansicht).
3. Den zurückgegebenen HTML-Pfad nennen / die Datei dem Nutzer geben.

## Kombination (Drug-Discovery)
`science.alphafold_fetch`/`rcsb_pdb` → Ziel-Protein in 3D (`protein_3d`),
`science.chembl_search` → Wirkstoff-SMILES in 3D (`molecule_3d`). So werden
Target und Ligand anschaulich.
