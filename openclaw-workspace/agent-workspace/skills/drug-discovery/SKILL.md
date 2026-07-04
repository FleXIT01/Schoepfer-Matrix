---
name: drug-discovery
description: "Wirkstoffe/Targets gegen eine Krankheit oder ein Protein finden: Literatur, Moleküle, Targets, 3D-Struktur, Interaktionen, Pathways — als Bericht."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧬",
        "requires": { "mcp": ["science"] }
      }
  }
---

# Drug Discovery — Bio-Wissenschafts-Pipeline

Trigger: „finde Inhibitoren gegen X", „Moleküle/Wirkstoffe gegen Krankheit Y",
„analysiere Protein/Gen Z", „Target für …". Nutzt die MCP-Tools des `science`-Servers.

## Ablauf

1. LITERATUR (parallel):
   - `science.pubmed_search(query)` — klinisch/medizinisch
   - `science.europepmc_search(query, preprints_only=true)` — neueste Preprints
   - `science.openalex_search(query)` — breite Übersicht + Zitationen

2. MOLEKÜLE & TARGETS:
   - `science.chembl_search(query, search_type="compound")` — bekannte Wirkstoffe
   - `science.chembl_search(query, search_type="target")` — Proteintargets

3. PROTEIN-VERTIEFUNG (wenn ein Gen/Protein erkennbar, z.B. EGFR, BRCA2, TP53):
   - `science.ensembl_lookup(symbol)` — Gen-Annotation
   - `science.alphafold_fetch(uniprot_id)` — vorhergesagte 3D-Struktur
     (bekannte IDs: EGFR=P00533, TP53=P04637, BRCA2=P51587, KRAS=P01116)
   - `science.rcsb_pdb(gene)` — experimentelle Strukturen
   - `science.string_db(gene)` — Interaktionspartner / Netzwerk
   - `science.reactome_search(query)` — beteiligte Signalwege

4. SICHERHEIT (falls konkreter Wirkstoff):
   - `science.openfda_search(drug, data_type="label")` — Indikation/Warnungen
   - `science.openfda_search(drug, data_type="event")` — Nebenwirkungen

5. SYNTHESE: Ergebnisse zu einem strukturierten Bericht zusammenfassen
   (## Zusammenfassung / ## Targets & Moleküle / ## Struktur / ## Aktuelle Forschung
   / ## Empfehlung). Quellen-Links beibehalten. Auf Wunsch als Datei speichern und
   danach Existenz prüfen, bevor „fertig" gemeldet wird.
