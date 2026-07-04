#!/usr/bin/env python
"""Interaktiver Mail-Konto-Schalter der Schöpfer-Matrix.

Schreibt `mail_account.json` neben dem mail-mcp-Server. Damit stellt man den
E-Mail-Versand bequem auf Outlook / Gmail / Office365 / eigenen SMTP um — einfach
erneut ausführen, um zu wechseln. Das Passwort (App-Passwort!) wird versteckt
eingegeben und nur LOKAL in dieser Datei gespeichert (geht nie durch den Chat).

Aufruf:  mailcfg.cmd   (oder:  python configure.py)
"""
from __future__ import annotations

import getpass
import json
from pathlib import Path

OUT = Path(__file__).parent / "mail_account.json"

# provider -> (anzeige, host, port, starttls)
PRESETS = {
    "1": ("outlook", "smtp-mail.outlook.com", 587, True),
    "2": ("gmail", "smtp.gmail.com", 587, True),
    "3": ("office365", "smtp.office365.com", 587, True),
}


def main() -> int:
    print("=" * 60)
    print("  Schöpfer-Matrix — E-Mail-Versand einrichten / umstellen")
    print("=" * 60)
    print("  1 = Outlook.com (privat)   smtp-mail.outlook.com:587")
    print("  2 = Gmail                  smtp.gmail.com:587")
    print("  3 = Office365 / Schule     smtp.office365.com:587  (SMTP oft gesperrt)")
    print("  4 = Eigener SMTP-Server")
    print("-" * 60)
    choice = input("Provider wählen [1/2/3/4]: ").strip()

    if choice in PRESETS:
        provider, host, port, starttls = PRESETS[choice]
    elif choice == "4":
        provider = "custom"
        host = input("SMTP-Host: ").strip()
        port = int(input("Port [587]: ").strip() or "587")
        starttls = (input("STARTTLS? [J/n]: ").strip().lower() or "j") in ("j", "y", "ja", "yes")
    else:
        print("Abgebrochen (keine gültige Auswahl).")
        return 1

    print(f"\nProvider: {provider}  ({host}:{port}, STARTTLS={starttls})")
    if provider in ("outlook", "gmail", "office365"):
        print("Hinweis: Hier ist meist ein APP-PASSWORT nötig (2FA aktivieren, dann")
        print("         unter den Kontosicherheits-Einstellungen ein App-Passwort erzeugen).")
    user = input("\nAbsender-E-Mail-Adresse (das Konto, von dem gesendet wird): ").strip()
    if not user:
        print("Abgebrochen (keine Adresse).")
        return 1
    pw = getpass.getpass("App-Passwort (Eingabe wird verborgen): ")
    pw = (pw or "").replace(" ", "").strip()  # App-Passwoerter werden oft mit Leerzeichen angezeigt
    if not pw:
        print("Abgebrochen (kein Passwort).")
        return 1
    # Frueh-Warnung: Ein Gmail-App-Passwort hat GENAU 16 Zeichen. Ist es kuerzer,
    # wurde fast sicher das NORMALE Google-Passwort eingegeben -> SMTP lehnt ab.
    if provider == "gmail" and len(pw) != 16:
        print(f"\n[!] Achtung: Eingabe hat {len(pw)} Zeichen, ein Gmail-APP-Passwort hat genau 16.")
        print("    Das normale Google-Passwort funktioniert NICHT fuer SMTP.")
        print("    App-Passwort erzeugen: https://myaccount.google.com/apppasswords (2FA noetig).")
        if input("    Trotzdem speichern und testen? [j/N]: ").strip().lower() not in ("j", "y", "ja", "yes"):
            print("Abgebrochen. Bitte ein 16-stelliges App-Passwort erzeugen und erneut ausfuehren.")
            return 1

    OUT.write_text(json.dumps({
        "provider": provider,
        "host": host,
        "port": port,
        "starttls": starttls,
        "user": user,
        "password": pw,
        "from": user,  # Absender = das angemeldete Konto (sonst lehnen Server ab)
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[ok] Gespeichert in:", OUT)

    # SOFORT-TEST: echten SMTP-Login probieren, damit man JETZT weiss ob es geht,
    # statt es erst spaeter ueber den Bot zu merken ("E-Mail geht nicht").
    print("\n[..] Teste SMTP-Login bei", f"{host}:{port} ...")
    import smtplib
    import ssl
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            s = smtplib.SMTP(host, port, timeout=30)
            s.ehlo()
            if starttls:
                s.starttls(context=ctx)
                s.ehlo()
        s.login(user, pw)
        s.quit()
        print("[OK] LOGIN ERFOLGREICH — der Mailversand funktioniert ab jetzt.")
        print("     Kein Neustart noetig (die Konfig wird bei jedem Versand frisch gelesen).")
        print("     Test im Chat z.B.: \"Schick eine Test-Mail an <adresse>\".")
    except smtplib.SMTPAuthenticationError as e:
        print("[FEHLER] LOGIN ABGELEHNT:", str(e)[:200])
        if provider == "gmail":
            print("     -> Bei Gmail braucht es ein 16-stelliges APP-PASSWORT (NICHT das")
            print("        normale Passwort): https://myaccount.google.com/apppasswords (2FA an).")
        elif provider in ("outlook", "office365"):
            print("     -> Microsoft hat SMTP-Basic-Auth meist GESPERRT. Nutze stattdessen")
            print("        Gmail (Option 2) oder den Telegram-Versand.")
        print("     Die Datei wurde gespeichert, aber der Versand wird so NICHT klappen.")
        print("     Bitte mailcfg.cmd erneut ausfuehren und korrekte Daten eingeben.")
    except Exception as e:  # noqa: BLE001
        print("[FEHLER] Verbindung/Server-Problem:", type(e).__name__, str(e)[:200])
        print("     Pruefe Host/Port/Internet. Datei wurde gespeichert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
