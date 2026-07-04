---
name: supervisor
description: "Großes/mehrstufiges Ziel in Teilaufgaben zerlegen und an die richtigen Skills/MCP-Tools verteilen, unabhängige Teile parallel, mit Verifikations-Gates."
metadata:
  {
    "openclaw":
      {
        "emoji": "🧠",
        "requires": { "mcp": ["science", "factory", "review", "planner", "kb"] }
      }
  }
---

# Supervisor — Mehr-Agenten-Orchestrierung

Der Meta-Workflow der Schöpfer-Matrix. Nutze ihn NUR, wenn ein Ziel mehrere
Fähigkeiten braucht (Recherche + Code + Medien + Deploy). Bei einer einzigen
Fähigkeit den passenden Spezial-Skill/Tool direkt aufrufen (kein Overhead).

## Ablauf

0. PLAYBOOK HOLEN (G1 — IMMER zuerst): Aufgaben-Signatur bilden
   (`kategorie+stichwort`, z.B. `repo-review+python`, `android-app+protein`)
   und `kb.playbook_lookup(signature)` aufrufen.
   - Treffer → Playbook als STARTPLAN laden und an die aktuelle Lage ANPASSEN
     (Vorschlag, kein Dogma — bei anderer Lage abweichen, D16).
   - Kein Treffer → normal planen (Schritt 1).

1. ZERLEGEN: Liste die benötigten Fähigkeiten auf und bilde einen Teilaufgaben-Graph.
   Typische Fähigkeiten -> Ziel:
   - Wissen/Literatur ......... Skill `deep-research` oder MCP `science.*`
   - Bio/Moleküle/Targets ..... Skill `drug-discovery` (MCP `science.*`)
   - Bot/Software bauen ........ Skill `build-bot` (MCP `factory.*`)
   - Code prüfen .............. MCP `review.scan_repo` / Skill `repo-review`
   - Bild/Mockup .............. Extension `comfy` / `fal`
   - Browser/Web-Test ......... Extension `browser`
   - Wissensfrage (Korpus) .... Skill `knowledge-ask`
   - Hardware/Modellwahl ...... MCP `planner.get_resources` / `planner.recommend`

2. RESSOURCEN PRÜFEN: Vor schweren Schritten `planner.get_resources` /
   `planner.can_load(required_gb)` aufrufen. Bei zu wenig VRAM kleineres Modell
   oder Cloud-API wählen.

3. AUSFÜHREN: Unabhängige Teilaufgaben PARALLEL an die jeweiligen Skills/Tools.
   Abhängige Teilaufgaben in Reihenfolge (z.B. erst recherchieren, dann coden).

4. GATES (Pflicht): Nach jedem Code-Schritt `review.scan_repo(path)` ODER
   `factory.verify_package(path)`. Bei „NICHT BESTANDEN" / Syntaxfehler:
   reparieren und erneut prüfen, bevor es weitergeht.

5. WAHRHEIT VOR ERFOLG: Niemals „fertig" melden, ohne das Ergebnis real geprüft
   zu haben (Datei existiert? Build grün? Review bestanden?). Halluzinierten
   Erfolg ablehnen.

6. ZUSAMMENFÜHREN: Teilergebnisse zu einer Antwort/Lieferung bündeln und über
   den ursprünglichen Kanal zurückgeben.

7. REFLEXION (G1 — nur bei BESTANDENEM Gate): Nach erfolgreichem Abschluss
   das Verfahren destillieren und speichern:
   ```
   kb.playbook_save(
       signature="<kategorie+stichwort>",
       title="<kurze Aufgabenbeschreibung>",
       content="## Schritte\n1. ...\n## Tools+Parameter\n...\n## Stolperstellen\n- <Problem>: <Umgehung>"
   )
   ```
   NUR speichern, wenn die Gates wirklich bestanden wurden — sonst lernt das
   System Murks. Bei fehlgeschlagenen Läufen NICHTS speichern.

## Beispiel: „Baue eine Android-App zur Protein-Faltungserkennung"

- [recherche] `science.pubmed_search` + `science.alphafold_fetch`  (parallel)
- [mockup]    `comfy` UI-Design                                    (parallel)
- [code]      `build-bot` / `coding-agent`        (nach recherche/mockup)
- [review]    `review.scan_repo` + `browser`-Test (nach code, Gate)
- [deploy]    Android/Firebase-Schritte           (nach Gate grün)
- [doku]      `repo-to-wiki`                       (nach code)
