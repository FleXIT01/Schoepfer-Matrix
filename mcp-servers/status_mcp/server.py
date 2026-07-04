"""status-mcp — System-Ampel für die Schöpfer-Matrix.

N7: Zeigt den Gesundheitszustand aller Matrix-Dienste auf einen Blick.

Tools:
  - system_status()  → Ampel: Ollama · Gateway · WeKnora · Reranker · ComfyUI ·
                       VRAM · Disk · Cloud-Budget · Offene Pending-Actions

Start (stdio):  python server.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("status-mcp")

# ─── Konfiguration ─────────────────────────────────────────────────────────────

_PORTS = {
    "Ollama":    ("http://127.0.0.1:11434/api/tags", 3),
    "Gateway":   ("http://127.0.0.1:18789/",         3),
    "WeKnora":   ("http://127.0.0.1:8080/api/v1/health", 3),
    "Reranker":  (None, 8011),   # TCP-only
    "ComfyUI":   (None, 8188),   # TCP-only
}

_COSTS_DB = Path(__file__).parent.parent / "llm_mcp" / "costs.db"
_PENDING_DB = Path(__file__).parent.parent / "mail_mcp" / "pending.db"
_JOBS_DB = Path(__file__).parent.parent / "jobs_mcp" / "jobs.db"
_DISK_PATH = Path("n:/")
_DAILY_LIMIT_EUR = float(os.environ.get("CLOUD_DAILY_LIMIT_EUR", "2.0"))
_USD_TO_EUR = 0.92


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _http_check(url: str, timeout: float) -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "status-mcp"})
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def _tcp_check(port: int, timeout: float = 2.0) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False


def _vram_info() -> str:
    smi = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    if not Path(smi).exists():
        smi = r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
    if not Path(smi).exists():
        return "GPU: nvidia-smi nicht gefunden"
    try:
        env = dict(os.environ)
        env.setdefault("SystemRoot", r"C:\Windows")
        env.setdefault("windir", r"C:\Windows")
        out = subprocess.run(
            [smi, "--query-gpu=name,memory.used,memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8, env=env,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return "GPU: keine NVIDIA-GPU gefunden"
        lines = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                name, used, free, total = parts[:4]
                pct = int(float(used)) * 100 // max(int(float(total)), 1)
                bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
                lines.append(
                    f"  {name}: {used}/{total} MB  [{bar}] {pct}%"
                )
        return "GPU VRAM:\n" + "\n".join(lines) if lines else "GPU: keine Daten"
    except Exception as e:
        return f"GPU: Fehler ({e})"


def _disk_info(path: Path) -> str:
    try:
        stat = shutil.disk_usage(path)
        used_gb = stat.used / 1e9
        total_gb = stat.total / 1e9
        free_gb = stat.free / 1e9
        pct = int(stat.used * 100 / max(stat.total, 1))
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        return (f"Disk {path}: {used_gb:.0f}/{total_gb:.0f} GB  "
                f"[{bar}] {pct}%  (frei: {free_gb:.1f} GB)")
    except Exception as e:
        return f"Disk {path}: Fehler ({e})"


def _budget_info() -> str:
    if not _COSTS_DB.exists():
        return "Cloud-Budget: keine costs.db"
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with sqlite3.connect(_COSTS_DB) as con:
            row = con.execute(
                "SELECT SUM(cost_usd) FROM cloud_calls WHERE ts LIKE ? AND status='ok'",
                (f"{today}%",),
            ).fetchone()
        total_usd = float(row[0] or 0.0)
        total_eur = total_usd * _USD_TO_EUR
        pct = total_eur / _DAILY_LIMIT_EUR * 100 if _DAILY_LIMIT_EUR > 0 else 0
        bar = "█" * (int(pct) // 10) + "░" * (10 - int(pct) // 10)
        status = "✅" if pct < 70 else ("⚠️" if pct < 95 else "🔴")
        return (f"Cloud-Budget: {total_eur:.4f} € / {_DAILY_LIMIT_EUR:.2f} €  "
                f"[{bar}] {pct:.1f}%  {status}")
    except Exception as e:
        return f"Cloud-Budget: Fehler ({e})"


def _jobs_info() -> str:
    if not _JOBS_DB.exists():
        return "Jobs: keine jobs.db"
    try:
        with sqlite3.connect(_JOBS_DB) as con:
            pending = con.execute("SELECT COUNT(*) FROM jobs WHERE state='pending'").fetchone()[0]
            running = con.execute("SELECT COUNT(*) FROM jobs WHERE state='running'").fetchone()[0]
        if pending == 0 and running == 0:
            return "Jobs: keine aktiven"
        parts = []
        if running:
            parts.append(f"{running} laufend 🔄")
        if pending:
            parts.append(f"{pending} wartend ⏳")
        return f"Jobs: {', '.join(parts)}"
    except Exception:
        return "Jobs: nicht abfragbar"


def _pending_info() -> str:
    if not _PENDING_DB.exists():
        return "Pending-Actions: keine pending.db"
    try:
        with sqlite3.connect(_PENDING_DB) as con:
            n = con.execute(
                "SELECT COUNT(*) FROM pending WHERE status='pending'"
            ).fetchone()[0]
        if n == 0:
            return "Pending-Actions: keine"
        return f"Pending-Actions: {n} offene (GO <id> zum Ausführen)"
    except Exception:
        return "Pending-Actions: nicht abfragbar"


# ─── MCP Tool ───────────────────────────────────────────────────────────────────

@mcp.tool()
def system_status() -> str:
    """Zeigt den Systemstatus aller Matrix-Dienste (Ampel: grün/gelb/rot).
    Für: schneller Überblick ob alles läuft (Ollama, Gateway, WeKnora, Reranker,
    ComfyUI), plus VRAM-Auslastung, Disk-Platz und heutiges Cloud-Budget."""
    lines = [f"SCHÖPFER-MATRIX — SYSTEMSTATUS  ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n"]

    # ── Dienste ──────────────────────────────────────────────────────────────
    lines.append("DIENSTE:")
    service_checks = [
        ("Ollama   (11434)", _http_check, "http://127.0.0.1:11434/api/tags", 3),
        ("Gateway  (18789)", _http_check, "http://127.0.0.1:18789/",         3),
        ("WeKnora  (8080) ", _http_check, "http://127.0.0.1:8080/api/v1/health", 3),
        ("Reranker (8011) ", _tcp_check,  8011,                                2),
        ("ComfyUI  (8188) ", _tcp_check,  8188,                                2),
    ]
    for label, fn, target, timeout in service_checks:
        ok = fn(target, timeout)
        icon = "✅" if ok else "❌"
        lines.append(f"  {icon}  {label}")

    # ── Hardware ─────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(_vram_info())
    lines.append(_disk_info(_DISK_PATH))

    # ── Cloud-Budget ──────────────────────────────────────────────────────────
    lines.append("")
    lines.append(_budget_info())

    # ── Pending Actions ──────────────────────────────────────────────────────
    lines.append(_pending_info())

    # ── Jobs ──────────────────────────────────────────────────────────────────
    lines.append(_jobs_info())

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
