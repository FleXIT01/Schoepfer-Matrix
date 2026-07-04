---
name: report-deliver
description: "Ein Thema recherchieren, als PDF zusammenfassen und ausliefern — per E-Mail (Outlook/Gmail) oder direkt als Telegram-Datei."
metadata:
  {
    "openclaw":
      {
        "emoji": "📨",
        "requires": { "mcp": ["research", "pdf", "mail"] }
      }
  }
---

# Report & Deliver — recherchieren → PDF → verschicken

Trigger: „recherchiere … und schick es mir als PDF", „fasse … als PDF zusammen und
maile es an <adresse>", „erstell einen Bericht über … und schick ihn per Telegram".

## Ablauf

1. RECHERCHE (Fakten mit Quellen sammeln):
   - Allgemein/aktuell: `research.deep_research(topic)` (Web, liefert Bericht + Quellen)
     oder `research.web_lookup(query)` für Einzelfakten.
   - **Aktualität beachten:** Bei „jetzig/aktuell/heute" NICHT aus dem Gedächtnis
     antworten — immer das Web nutzen, sonst droht veraltete Info.
   - Fachlich: `science.*` (PubMed/arXiv/…); Eigen-Korpus: `kb.kb_search`.

2. PDF ERZEUGEN:
   - `pdf.pdf_create(title, content, filename)` mit dem Recherche-Ergebnis als
     Markdown (`# Titel`, `## Abschnitt`, `- Punkte`, **fett**). Quellen als
     `## Quellen`-Abschnitt anhängen. Das Tool gibt den ABSOLUTEN PDF-Pfad zurück.

3. ZUSTELLEN (genau den vom Nutzer gewünschten Weg):
   - **E-Mail:** `mail.email_send(to=<adresse>, subject, body, attachment_path=<pdf-pfad>)`.
     Es gibt **keinen Standard-Empfänger** — wenn der Nutzer keine Adresse genannt hat,
     freundlich nach der Ziel-Adresse fragen (oder Telegram anbieten).
   - **Telegram („schick mir das"):** `mail.telegram_send(file_path=<pdf-pfad>, caption=…)`
     schickt die Datei direkt in den Chat (kein Empfänger nötig).
   - Unsicher, was eingerichtet ist? → `mail.delivery_status()`.

4. BESTÄTIGEN: konkret melden — Titel, PDF-Pfad und an wen/wohin zugestellt wurde.

## Fehlerfälle
- E-Mail meldet „nicht eingerichtet": dem Nutzer sagen, einmal **`mailcfg.cmd`**
  auszuführen (Konto + App-Passwort) und das Gateway neu zu starten; ersatzweise
  sofort per `telegram_send` ausliefern.
- SMTP-Login abgelehnt: bei Outlook/Gmail ist ein **App-Passwort** nötig (2FA);
  Schul-/Firmenkonten sperren SMTP oft — dann Telegram nutzen.
