"""CLI-Viewer fuer trace.db — wird von trace.cmd aufgerufen.
Aufruf:
  python view.py          → letzte 20 Turns
  python view.py N        → letzte N Turns
  python view.py stats    → 7-Tage-Statistiken
  python view.py stats N  → N-Tage-Statistiken
"""
from __future__ import annotations
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DB = Path(__file__).parent / "trace.db"


def _conn():
    if not _DB.exists():
        print("trace.db nicht gefunden — noch keine Turns protokolliert.")
        sys.exit(0)
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    return c


def view(n: int = 20):
    with _conn() as c:
        rows = c.execute(
            "SELECT id,ts,channel,model,tools,summary,status,tokens_in,tokens_out,cost_usd "
            "FROM turns ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    if not rows:
        print("Keine Turns protokolliert.")
        return
    print(f"\nLetzte {len(rows)} Agent-Turns (neueste zuerst):\n")
    print(f"{'#':>5}  {'Zeit':19}  {'Kanal':10}  {'Modell':20}  {'Status':7}  {'$':8}  Summary")
    print("-" * 105)
    for r in rows:
        ts = r["ts"][:19].replace("T", " ")
        cost = f"${r['cost_usd']:.4f}" if r["cost_usd"] > 0 else "gratis"
        summary = (r["summary"] or "—")[:50]
        print(f"{r['id']:>5}  {ts}  {r['channel']:10}  {r['model']:20}  {r['status']:7}  {cost:8}  {summary}")
    total = sum(r["cost_usd"] for r in rows)
    if total > 0:
        print(f"\n  Kosten (angezeigt): ${total:.4f}")


def stats(days: int = 7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM turns WHERE ts >= ?", (since,)).fetchone()[0]
        if total == 0:
            print(f"Keine Turns in den letzten {days} Tagen.")
            return
        total_cost = c.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM turns WHERE ts >= ?", (since,)).fetchone()[0]
        errors = c.execute(
            "SELECT COUNT(*) FROM turns WHERE ts >= ? AND status != 'ok'", (since,)).fetchone()[0]
        by_ch = c.execute(
            "SELECT channel, COUNT(*) n FROM turns WHERE ts >= ? GROUP BY channel ORDER BY n DESC",
            (since,)).fetchall()
        by_md = c.execute(
            "SELECT model, COUNT(*) n, COALESCE(SUM(cost_usd),0) cost "
            "FROM turns WHERE ts >= ? GROUP BY model ORDER BY n DESC", (since,)).fetchall()
        tool_rows = c.execute(
            "SELECT tools FROM turns WHERE ts >= ? AND tools != ''", (since,)).fetchall()

    tc: dict[str, int] = {}
    for row in tool_rows:
        for t in (row[0] or "").split(","):
            t = t.strip()
            if t:
                tc[t] = tc.get(t, 0) + 1

    print(f"\nTRACE-STATISTIKEN (letzte {days} Tage)\n")
    print(f"  Gesamt:  {total} Turns  |  Fehler: {errors} ({errors/total*100:.1f}%)  |  Kosten: ${total_cost:.4f}\n")
    print("  Kanäle:")
    for r in by_ch:
        print(f"    {r[0]:15} {r[1]:>5}x")
    print("\n  Modelle:")
    for r in by_md:
        cost_str = f"  ${r[2]:.4f}" if r[2] > 0 else ""
        print(f"    {r[0]:28} {r[1]:>5}x{cost_str}")
    if tc:
        top = sorted(tc.items(), key=lambda x: -x[1])[:12]
        print("\n  Top-Tools:")
        for name, cnt in top:
            print(f"    {name:35} {cnt:>4}x")


def main():
    args = sys.argv[1:]
    if args and args[0].lower() == "stats":
        days = int(args[1]) if len(args) > 1 else 7
        stats(days)
    else:
        n = int(args[0]) if args and args[0].isdigit() else 20
        view(n)


if __name__ == "__main__":
    main()
