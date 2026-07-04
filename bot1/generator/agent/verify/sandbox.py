"""Subprozess-Sandbox: materialisiert ein Datei-Set in einem temp-Verzeichnis
und führt darin Python-Treiberskripte mit Timeout aus."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class RunResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False

    @property
    def output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


@contextlib.contextmanager
def materialized(files: dict[str, str]) -> Iterator[Path]:
    """Schreibt {relativer_pfad: inhalt} in ein temp-Verzeichnis und räumt danach auf."""
    tmp = Path(tempfile.mkdtemp(prefix="botgen_gate_"))
    try:
        for rel_path, content in files.items():
            target = tmp / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_python_file(project_dir: Path, rel_script: str, timeout: float) -> RunResult:
    """Führt eine bereits im project_dir liegende .py-Datei aus."""
    return _run([sys.executable, rel_script], project_dir, timeout)


def run_driver(project_dir: Path, driver_source: str, timeout: float) -> RunResult:
    """Schreibt ein Treiberskript in project_dir und führt es aus."""
    driver = project_dir / "__gate_driver__.py"
    driver.write_text(driver_source, encoding="utf-8")
    try:
        return _run([sys.executable, "__gate_driver__.py"], project_dir, timeout)
    finally:
        driver.unlink(missing_ok=True)


def run_inline(project_dir: Path, code: str, timeout: float) -> RunResult:
    """Führt Code via ``python -c`` mit cwd=project_dir aus."""
    return _run([sys.executable, "-c", code], project_dir, timeout)


def _run(cmd: list[str], cwd: Path, timeout: float) -> RunResult:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            ok=False,
            stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
            stderr=f"[Timeout nach {timeout}s]",
            returncode=-1,
            timed_out=True,
        )
    return RunResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        returncode=proc.returncode,
    )
