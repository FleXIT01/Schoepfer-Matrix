# Schöpfer-Matrix — Demo-Drehbuch (N10)

**Für Kunden-Demos** — Gast-Modus startet mit `gateway_guest.cmd`.
Keine Shell, kein Mailversand, kein Schreiben außerhalb Output/.

---

## Vorbereitung

1. `gateway.cmd` läuft (Ollama + WeKnora + Reranker müssen up sein)
2. `gateway_guest.cmd` starten → neues Fenster
3. Demo-Telegram-Account ID in `openclaw-guest.json` → `channels.telegram.allowFrom` eintragen
4. Lokales Modell laden: `ollama pull gpt-oss:20b` (falls nicht da)

---

## Demo-Flow 1: Frage → quellenbelegter PDF-Bericht

**Thema:** Zeigt Recherche + PDF-Ausgabe in einem Schritt.

**Prompt ans Demo-Konto senden:**
```
Recherchiere aktuelle Inhibitoren für den EGFR-Rezeptor bei Lungenkrebs
und fasse die Top-5-Wirkstoffe mit Quellen als PDF zusammen.
```

**Was passiert:**
- `research.deep_research` sucht (SearXNG + Jina)
- `science.pubmed_search` holt PubMed-Paper
- `pdf.pdf_create` baut PDF
- Telegram-Zustellung mit PDF-Anhang

**Zeigt:** Lokal-first, echte Quellen, kein Cloud-Pflicht.

---

## Demo-Flow 2: Repo-Review live

**Thema:** Zeigt Code-Qualitäts-Analyse (ACHTUNG: review-Tools sind im Gast-Modus gesperrt → für diesen Flow normalen Modus nutzen, oder review-Tools temporär freischalten).

**Prompt:**
```
Überprüfe das Python-Skript n:\allinall\briefing.py
auf potenzielle Fehler und Verbesserungsmöglichkeiten.
```

**Was passiert:**
- `llm.cloud_code` (Sonnet) analysiert den Code
- Strukturierter Review-Report wird ausgegeben

**Tipp:** Im Gast-Modus stattdessen `pdf.pdf_extract` + `llm.cloud_cheap` zeigen.

---

## Demo-Flow 3: Drug-Discovery-Light (EGFR-Kette)

**Thema:** Zeigt Verknüpfung spezialisierter Bio-APIs.
*(Science-Tools sind im Gast-Modus verfügbar — Kern-APIs laufen lokal.)*

**Prompt:**
```
Zeig mir die 3D-Struktur von EGFR (UniProt P00533),
welche zugelassenen Inhibitoren gibt es laut ChEMBL,
und was sagt STRING über EGFR-Interaktionspartner?
```

**Was passiert:**
- `science.alphafold_fetch` → Struktur-Link
- `science.chembl_search` → Inhibitoren
- `science.string_db` → Interaktionsnetz
- `molviz.molecule_3d` → interaktives 3D-HTML (falls erlaubt)

**Zeigt:** Echte Wissenschafts-APIs, kein Scraping, kein Cloud-Key.

---

## Sicherheitshinweise für die Demo

- Im Gast-Modus kann der Demo-Gast **keine** Mails senden, keine Dateien schreiben,
  keine Shell-Befehle ausführen, keine Webhooks triggern.
- `mail.email_send` und `assistant.run_command` sind hart geblockt.
- Wenn der Demo-Gast versucht, Befehle über Nachrichten einzuschleusen (Injection-Test),
  antwortet der Agent: „Das ist externer Inhalt — ich führe keine eingebetteten Befehle aus."

---

## Demo-Konto einrichten

1. Zweiten Telegram-Account anlegen (oder Testgerät nutzen)
2. Dessen User-ID ermitteln: [@userinfobot](https://t.me/userinfobot) anschreiben
3. ID in `openclaw-guest.json` eintragen:
   ```json
   "allowFrom": [7875566879, <DEMO_USER_ID>]
   ```
4. `gateway_guest.cmd` neu starten

---

*Stand: 2026-06-11 | Phase 9 BUSINESS*
