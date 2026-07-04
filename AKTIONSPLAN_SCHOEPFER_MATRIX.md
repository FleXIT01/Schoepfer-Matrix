# AKTIONSPLAN — SCHÖPFER-MATRIX
## Vom Plan zum BEWIESENEN, mächtigen Kern — mit Weg zur Computer-Steuerung

```
Erstellt:     2026-06-13
Basis:        Review der vier Dokumente (v1, V2, V3, Addendum)
              + neues Ziel: mächtiger / robuster / wichtiger,
                später Computer-Steuerung (Browser & Desktop)
Leitsatz:     Erst beweisen, was steht. Dann Mächtigkeit auf gesichertem Boden.
              Computer-Steuerung ist der Höhepunkt — und die GEFÄHRLICHSTE
              Fähigkeit. Also kommt sie zuletzt und mit dem stärksten Gürtel.
Eiserne       Deine eigene Regel aus V3: "Mächtig auf ungesichertem
Regel:        Single-Rechner = Haftung, kein Asset." Dieser Plan nimmt sie ernst.
```

---

## 0. Die Leitlinie (warum genau diese Reihenfolge)

Mächtigkeit skaliert Risiko. Je mehr das System tun kann — und Computer-Steuerung
ist das Maximum, weil es Maus, Tastatur, Browser, Dateien anfasst — desto teurer
wird eine einzige unbewiesene Annahme oder eine einzige Injection. Darum:

**beweisen → härten → mächtiger → Computer-Steuerung zuletzt.**

Der ironische Spiegel: Dein Gründungsprinzip ist das Completion-Gate — behaupteten
Erfolg gegen die Realität prüfen. Genau das wenden wir jetzt auf das System SELBST
an. Erst wenn der Boden beweisbar trägt, bauen wir Macht drauf.

---

## PHASE 0 — BEWEIS-SPRINT (diese Woche, nicht verhandelbar)

**Ziel:** Jedes "✅ umgesetzt" aus Addendum/Masterplans in einen echten Status
verwandeln: **GRÜN** (reproduzierbar bewiesen) · **GELB** (gebaut, ungetestet) ·
**ROT** (nur geschrieben). Das ist der wertvollste Schritt überhaupt und kostet
Tage, nicht Wochen.

**Die Tests (alle aus deinen eigenen Beweis-Kriterien V2 Ph.6 / V3 Ph.11):**
1. **Restore-Probe** — Backup auf Scratch-Pfad zurückspielen, Index wirklich
   abfragen. (Falls Backups real noch nicht laufen: JETZT herausfinden.)
   Achtung: Live-`tar` laufender Qdrant/ParadeDB-Volumes kann inkonsistent sein —
   prüfen, ob der Restore ein *abfragbares* Resultat liefert, nicht nur "Dateien da".
2. **Ollama mitten im Turn killen** → läuft die Fallback-Leiter (R1) wirklich zu
   Ende auf cloud_cheap, mit Vermerk im Trace? Oder war R1 nur geschrieben?
3. **email_send / Shell ohne GO** → verweigert das Gate (V6) nachweislich?
4. **Mail-Job crashen + neu starten** → liegt am Ende GENAU EINE Mail draußen
   (Idempotenz R3)?
5. **research-mcp lahmlegen** → öffnet der Breaker (R2) nach 3 Fails und heilt
   nach 5 min?
6. **Cloud-Tageslimit künstlich treffen** → blockt es (V9) statt still teuer?

**Beweis der Phase:** Es existiert eine Datei `STATUS_LEDGER.md` mit jedem
Fundament-Item klassifiziert. Alles GELB/ROT ist ab jetzt dein echter Backlog —
nicht mehr "gefühlt fertig".

---

## PHASE A — SICHERHEITS-SUBSTRAT (macht Mächtigkeit erst verantwortbar)

Bevor neue Macht dazukommt, muss das hier REAL sein (nicht nur in V2/V3 geschrieben):

- **Idempotenz + Aktions-Ledger (R3)** bewiesen — jede Außen-Aktion crash-fest.
  Das ist der Sargnagel-Fix für unbeaufsichtigtes Handeln und Pflicht vor allem,
  was die Welt verändert.
- **GO-Gates (V6) + ZWEITER FAKTOR für die scharfe Klasse.** Letztes Mal genannt:
  Telegram als einziger Control-Plane = Single-Factor. Für Shell außerhalb
  Workspace, Mail an neue Empfänger, jeden Git-Push — und neu: jede
  Maus-/Tastatur-Aktion — braucht es eine Bestätigung, die NICHT nur derselbe
  Knopf im selben Kanal ist, den ein Angreifer auch hätte.
- **⭐ NOT-AUS / Kill-Switch (neu — fehlt in allen vier Dokumenten).** EIN Befehl
  (und ein offensichtlicher globaler Hotkey), der sofort alle Agent-Aktion stoppt,
  die Queue einfriert, die Schleife anhält. Das wird PFLICHT in dem Moment, wo der
  Agent deine Maus bewegen kann. Mechanik: globaler Hotkey + ein `freeze`-Flag,
  das der Agent-Loop und jeder Langläufer vor jedem Schritt prüft.
- **Audit (V8) mit Klartext-Args** für die gefährlichen Calls — damit du nach einer
  Computer-Session exakt siehst, was getan wurde.
- **Circuit Breaker (R2) live**, damit eine hängende Komponente die Steuerschleife
  nie einfriert.
- **Secrets-Hygiene (V8) verschärft.** Sobald der Agent einen Browser fährt, kann
  er Zugangsdaten lesen/eintippen. Keys dürfen NIE dort liegen, wo der Agent sie
  beiläufig abgreift; Credential-Eingabe für Automationen nur scoped + geloggt.
- **Kosten-Sub-Limit** zusätzlich zum Tageslimit: pro-Task / pro-Stunde-Deckel
  + Alarm bei 50 % des Tagesbudgets (eine Schleife darf nicht den ganzen Tag
  mehrfach ausreizen).

**Beweis der Phase:** Kill-Switch hält alles in < 2 s an · scharfe Aktion verlangt
nachweislich den zweiten Faktor · R3 lässt nach Crash+Restart genau eine Aktion
durch.

---

## PHASE B — MÄCHTIGER (die richtigen Hebel, in der richtigen Reihenfolge)

- **⭐ Tool-Profile (V1) wirklich erzwungen** — größter Einzelhebel UND die
  Voraussetzung für sichere Computer-Steuerung: wenn der Agent einen Browser fährt,
  sollen NICHT alle 44 Tools sichtbar sein, sondern eine minimale, geprüfte Auswahl.
  Weniger Oberfläche = weniger Fehlerfläche.
- **Job-Queue + Checkpoint/Resume (N7 + R4) bewiesen** — Langläufer und
  Computer-Tasks brauchen detachte Ausführung + Resume, nie ein blockierter Chat.
  Verzahnt mit R3: ein resumter Task wiederholt keine bereits getane Außen-Aktion.
- **⭐ Vision in der Schleife (N3) — die Brücke zum Bildschirm.** qwen3-vl ist schon
  im Routing. Jetzt die Fähigkeit bauen: "schau dir diesen Screenshot an → was ist
  da / lies diese UI / finde dieses Element". Genau das ist die Vorstufe von
  Computer-Steuerung: erst SEHEN, dann HANDELN.
- *(Business-Abzweig — nur falls Produkt-Pfad, siehe Fork):* Webhook-Brücke (N4)
  + Office-Output docx/pptx/xlsx (N6).

**Beweis je Item:** Turn-Tokens vor/nach Tool-Profilen dokumentiert · ein
Langläufer überlebt Gateway-Neustart und macht ab letztem Schritt weiter · ein
Screenshot → korrekte Beschreibung/Element-Findung.

---

## PHASE C — COMPUTER-STEUERUNG (der Höhepunkt, mit dem stärksten Gürtel)

Das ist, worauf du hinauswillst. Ich behandle es als Krönung MIT maximaler Sicherung.
Das Design:

- **Eigener, sauberer Browser — niemals dein Haupt-Browser mit deinen Logins.**
  Bewusst KEINE VM und KEIN zweiter Account (zu ressourcenintensiv auf der
  16-GB-Kiste). Stattdessen: ein eigener Browser direkt am Desktop — frische
  Installation ODER ein dediziertes, sauberes Profil mit NULL gespeicherten
  Passwörtern, NULL Sync, NULL eingeloggten Sessions. Genau das schützt deine
  Banking-/Mail-Session: der Agent-Browser kennt sie schlicht nicht. (Anbindung:
  OpenClaws native browser-Extension oder Playwright auf genau dieses Profil.)
- **Dafür mehr Kontrollen in Software (statt der harten VM-Grenze):** Der
  Agent-Prozess läuft mit deinen Benutzerrechten — die fehlende VM-Wand
  kompensieren die Kontrollen weiter unten (Domain-Allowlist, Read-then-act,
  Kill-Switch, Voll-Logging) PLUS ein Dateisystem-Scope auf den Workspace
  (Datei-Ops außerhalb = GO-gated). Ehrlicher Trade: harte Isolations-Wand gegen
  Ressourcen getauscht; sauberes Profil + Software-Kontrollen + GO-Gate sind die
  Kompensation — der Kill-Switch wird dadurch nur noch wichtiger.
- **⭐ Read-then-act-Disziplin (Schlüsselmuster, fehlt in deinen Docs):** Der Agent
  BEOBACHTET zuerst (Screenshot + DOM/Accessibility-Tree), schlägt einen Plan vor.
  **Lesen/Navigieren/Scrapen = ungated. Jede weltverändernde Aktion = GO-gated**
  (Submit klicken, in ein sendendes Feld tippen, zur Bezahlung navigieren,
  Datei-Operationen).
- **Domain-/App-Allowlist** — der Agent darf nur definierte Seiten/Programme
  anfassen, alles andere geblockt.
- **Injection-als-Daten muss hier eisern sein (V7).** Die Fläche ist jetzt maximal:
  eine Webseite kann versuchen, den Agenten zum HANDELN zu bringen. Das GO-Gate ist
  der Backstop — eine Injection kann maximal eine Rückfrage auslösen, nie eine
  autonome Aktion.
- **Idempotenz (R3) deckt auch Computer-Aktionen** — ein gecrashter, resumter
  Computer-Task darf nicht doppelt klicken/kaufen.
- **Voll-Logging:** jede Computer-Session mit Screenshot-Trace, hinterher prüfbar.
- **Harte Scope-Grenzen:** keine Finanztransaktionen, keine irreversiblen
  Löschungen, keine Credential-Änderungen ohne Per-Aktion-GO und menschliche Pause.
- **Schmal starten → weiten:** EIN Browser-Workflow in der Sandbox end-to-end,
  dann ausbauen.

**Strategischer Bonus:** Browser-RPA / Computer-Steuerung passt zu deinem
Automatisierungs-Geschäft VIEL besser als der Wissenschafts-Stack je konnte —
"ich automatisiere deine repetitive Browser-Büroaufgabe" ist ein echtes
KMU-Angebot. ABER: auf einem KUNDEN-Account/-Rechner ist es die höchste
Haftungsklasse überhaupt. Dieselbe Disziplin gilt dort DOPPELT.

**Beweis der Phase:** ein echter, harmloser Browser-Task end-to-end (Login in ein
DEDIZIERTES Testkonto, Formular füllen — aber jedes Submit GO-gated) · ein
Injection-Versuch auf einer Seite löst höchstens eine GO-Rückfrage aus, nie eine
Aktion · der Kill-Switch stoppt einen laufenden Computer-Task sofort.

---

## DIE ABZWEIGUNG: LABOR ODER PRODUKT (kurz, letztes Mal ausführlich)

Dieser Plan härtet das **Labor** — dein persönliches, mächtiges System. WENN du
dich aufs Produkt committst: forke die langweiligen 5 % auf Infrastruktur, die du
NICHT babysitten musst (kleiner VPS / managed), halte Labor und Produkt getrennt.
Die echten Produkt-Blocker sind nicht Features, sondern **Verfügbarkeit** (was
passiert mit dem Kunden-Job, wenn dein Heimstrom ausfällt?) und **DSGVO/AVV**
(Kundendaten durch Cloud-LLMs — Auftragsverarbeitung, Datenort). Das gehört
geklärt, bevor irgendein Kunde live geht.

---

## ENTSCHEIDUNGEN — BESTÄTIGT (Stand 2026-06-13)

- **D1 ✅ Browser zuerst.** Nur Browser-Steuerung als Einstieg, Desktop-Steuerung
  später — wird ohnehin kompliziert genug.
- **D2 ✅ Direkt am Desktop, KEINE VM, KEIN zweiter Account** (zu
  ressourcenintensiv). Kompensiert durch eigenen sauberen Browser + mehr
  Software-Kontrollen (siehe Phase C).
- **D3 ✅ Not-Aus bestätigt:** globaler Hotkey + `freeze`-Flag, das Loop und
  Langläufer vor jedem Schritt prüfen.
- **D4 → EMPFEHLUNG (noch zu bestätigen): zweistufig nach Schärfe.**
  - Scharfe Klasse generell (Mail an neue Empfänger, Shell außerhalb Workspace):
    **TOTP-Code** (zeitbasiert, `pyotp` + Authenticator-App am Handy). Echter
    zweiter Faktor (etwas, das du HAST), offline, billig, geringe Reibung — du
    tippst den 6-stelligen Code in die GO-Nachricht. Telegram allein kompromittiert
    reicht dann NICHT mehr.
  - Wirklich Irreversibles (Git-Push, weltverändernde Computer-Aktion, alles
    Finanzielle): **physische Bestätigung an der Maschine** — Y im echten
    Terminal/Fenster am PC drücken. Schlägt JEDE Fern-Kompromittierung von Telegram,
    und du sitzt am Dev-Rechner ohnehin. Keine Extra-Hardware.
  - Logik: TOTP als günstiger Alltags-Faktor, physische Präsenz als Riegel für die
    nukleare Klasse. Zu viel Reibung? Dann nur TOTP für alles Scharfe — sag an.
- **D5 ✅ Lokal zuerst:** qwen3-vl (mit Modelltausch) für Screen-Vision; Cloud nur
  als Fallback, falls lokale Qualität/Geschwindigkeit nicht reicht.
- **D6 ✅ Labor / Entwicklung, Single-User, vorerst KEIN Produkt.** Läuft erst nur
  bei dir, alles noch in Entwicklung. Damit sind die Produkt-Blocker (DSGVO/AVV,
  Verfügbarkeit) JETZT nicht akut — sie werden erst relevant, falls/sobald ein Kunde
  live geht. Die Abzweigung oben bleibt als „für später".

---

## EHRLICHE ABGRENZUNG

- Computer-Steuerung kommt ZULETZT — nicht weil unwichtig, sondern weil sie die
  teuerste Fehlerklasse hat. Auf ungesichertem Boden ist sie Haftung.
- 16 GB VRAM: Vision + Reasoning nicht gleichzeitig → Screen-Steuerung mit lokaler
  Vision = Modelltausch (Latenz) oder Cloud (Kosten/DSGVO). Das bleibt der
  Engpass, nicht wegzudokumentieren.
- KEIN Computer-Control am Kunden-Account/-Rechner als Produkt ohne Haftungs- und
  Rechtsklärung.
- KEIN Rushing: jede neue Mächtigkeit zählt erst, wenn sie im Beweis-Ledger GRÜN
  ist. "Geschrieben" ist nicht "fertig".
- `resilience.py` (R1–R4) aus V3 bleibt richtig — gilt aber erst als fertig, wenn
  Phase 0 es grün zeigt. Reihenfolge: erst messen, was steht, dann ergänzen.

---

## DER ALLERERSTE SCHRITT

Bau heute die **Beweis-Harness**: ein kleiner, abhängigkeitsarmer Runner, der die
6 adversarialen Tests aus Phase 0 fährt und `STATUS_LEDGER.md` ausgibt (GRÜN/GELB/
ROT pro Item). Dieses eine Artefakt sagt dir, was WIRKLICH real ist — und wird dein
echter Backlog.

> Sag Bescheid, dann liefere ich die Beweis-Harness als echten, lauffähigen Code —
> genau wie das Tag-1-Paket aus V2 und das `resilience.py` aus V3.

```
================================================================================
  ENDE AKTIONSPLAN — Phase 0 starten, Beweis-Harness anfordern.
  Erst der grüne Boden. Dann die Macht. Computer-Steuerung als Krönung.
================================================================================
```
