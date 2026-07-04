"""planner-mcp — Hardware-/Ressourcen-Berater als MCP-Server.

Gibt OpenClaw Auskunft über RAM, VRAM und GPU, damit das Hirn vor schweren
Schritten (großes Modell laden, ComfyUI starten) entscheiden kann, was lokal
passt. Ersetzt die Rolle von local-llm-planner als sauberer, self-contained
MCP-Dienst (psutil + nvidia-smi).

Start (stdio):  python server.py
"""
from __future__ import annotations

import shutil
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("planner-mcp")


def _find_nvidia_smi() -> str | None:
    """Findet nvidia-smi über PATH oder bekannte Windows-Pfade.
    (MCP-stdio-Subprozesse erben oft nur einen minimalen PATH.)"""
    found = shutil.which("nvidia-smi")
    if found:
        return found
    candidates = [
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    for c in candidates:
        if shutil.os.path.exists(c):
            return c
    return None


def _gpu_info() -> list[dict]:
    """Liest GPU-Daten via nvidia-smi (leere Liste, wenn keine NVIDIA-GPU)."""
    smi = _find_nvidia_smi()
    if not smi:
        return []
    try:
        # nvidia-smi.exe braucht SystemRoot, um Windows-DLLs zu laden — unter der
        # minimalen MCP-stdio-Umgebung fehlt das oft. Daher hier sicherstellen.
        import os
        env = dict(os.environ)
        env.setdefault("SystemRoot", r"C:\Windows")
        env.setdefault("windir", r"C:\Windows")
        out = subprocess.run(
            [smi,
             "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, env=env,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append({
                    "name": parts[0],
                    "vram_total_mb": int(float(parts[1])),
                    "vram_used_mb": int(float(parts[2])),
                    "vram_free_mb": int(float(parts[3])),
                    "gpu_util_percent": int(float(parts[4])),
                })
        return gpus
    except Exception:  # noqa: BLE001
        return []


@mcp.tool()
def get_resources() -> str:
    """Aktueller Hardware-Zustand: RAM, VRAM, GPU-Auslastung, CPU.
    Für: Entscheidung, ob ein Modell/Dienst lokal geladen werden kann."""
    import psutil

    vm = psutil.virtual_memory()
    lines = [
        "HARDWARE-RESSOURCEN:",
        f"  CPU-Auslastung: {psutil.cpu_percent(interval=0.3)}% ({psutil.cpu_count()} Kerne)",
        f"  RAM: {vm.used / 1e9:.1f} / {vm.total / 1e9:.1f} GB belegt "
        f"({vm.percent}%) — frei: {vm.available / 1e9:.1f} GB",
    ]
    gpus = _gpu_info()
    if gpus:
        for i, g in enumerate(gpus):
            lines.append(
                f"  GPU{i}: {g['name']} — VRAM {g['vram_used_mb']}/{g['vram_total_mb']} MB "
                f"belegt, frei: {g['vram_free_mb']} MB, Last: {g['gpu_util_percent']}%"
            )
    else:
        lines.append("  GPU: keine NVIDIA-GPU erkannt (nur CPU-Inferenz)")
    return "\n".join(lines)


@mcp.tool()
def can_load(required_gb: float, target: str = "vram") -> str:
    """Prüft, ob 'required_gb' GB im Ziel-Speicher frei sind (target: 'vram' oder 'ram').
    Für: vorab klären, ob ein Modell/Dienst gestartet werden kann."""
    import psutil

    if target == "vram":
        gpus = _gpu_info()
        if not gpus:
            return "Keine NVIDIA-GPU — VRAM-Prüfung nicht möglich (nutze RAM/CPU)."
        free_gb = gpus[0]["vram_free_mb"] / 1024
    else:
        free_gb = psutil.virtual_memory().available / 1e9

    ok = free_gb >= required_gb
    return (
        f"{'✅ PASST' if ok else '❌ ZU WENIG'}: benötigt {required_gb:.1f} GB {target.upper()}, "
        f"frei {free_gb:.1f} GB."
        + ("" if ok else f" Fehlen {required_gb - free_gb:.1f} GB — Dienste stoppen oder kleineres Modell wählen.")
    )


@mcp.tool()
def recommend(task: str = "coding") -> str:
    """Empfiehlt eine Modellgröße für die aktuelle Hardware und einen Task-Typ
    (coding|reasoning|routing|vision). Für: passende lokale Modellwahl."""
    gpus = _gpu_info()
    free_gb = gpus[0]["vram_free_mb"] / 1024 if gpus else 0.0

    # Grobe Faustregel: Q4-Quantisierung ~0.6 GB pro Mrd. Parameter
    if free_gb >= 18:
        size = "32B (z.B. qwen2.5:32b / gemma3:27b)"
    elif free_gb >= 9:
        size = "14B (z.B. qwen2.5:14b)"
    elif free_gb >= 5:
        size = "7-8B (z.B. llama3.1:8b / qwen2.5:7b)"
    elif free_gb > 0:
        size = "3-4B (kleines Modell) oder Cloud-API"
    else:
        size = "Cloud-API oder kleines CPU-Modell (keine GPU frei)"

    hint = {
        "routing": "Für Routing/Klassifikation reicht ein kleines, schnelles Modell.",
        "coding": "Für Code ein starkes Modell (codestral/qwen-coder) oder Cloud-API.",
        "reasoning": "Für Reasoning das größte Modell, das in den VRAM passt.",
        "vision": "Für Vision ein VL-Modell (qwen3-vl) — braucht mehr VRAM.",
    }.get(task, "")
    return f"Empfehlung für '{task}': {size} (frei: {free_gb:.1f} GB VRAM).\n{hint}"


if __name__ == "__main__":
    mcp.run()
