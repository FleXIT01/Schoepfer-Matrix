from __future__ import annotations

import contextlib
from typing import Iterator

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown


class CLI:
    """Rich display/input layer."""

    def __init__(self) -> None:
        self.console = Console()

    def display(self, text: str, markdown: bool = False) -> None:
        if markdown:
            self.console.print(Markdown(text))
        else:
            self.console.print(text)

    def display_header(self, title: str) -> None:
        self.console.print()
        self.console.print(Panel(f"[bold]{title}[/bold]", style="blue", expand=False))

    def display_section(self, block_num: int, title: str, total: int = 5) -> None:
        self.console.print(f"\n[bold cyan][{block_num}/{total}][/bold cyan] Generiere: {title}...")

    def display_progress(self, message: str) -> None:
        self.console.print(f"  [dim]> {message}[/dim]")

    def display_success(self, output_path: str) -> None:
        self.console.print()
        self.console.print(
            Panel(
                f"Ausgabe: [green]{output_path}[/green]",
                title="✅ Generierung abgeschlossen!",
                border_style="green",
                expand=False,
            )
        )
        self.console.print()

    def display_error(self, message: str) -> None:
        self.console.print(f"\n[bold red][FEHLER][/bold red] {message}\n")

    def prompt_input(self, prompt: str = "> ") -> str:
        try:
            return self.console.input(f"[bold yellow]{prompt}[/bold yellow]").strip()
        except (KeyboardInterrupt, EOFError):
            self.console.print()
            return ""

    @contextlib.contextmanager
    def status(self, message: str) -> Iterator[None]:
        """Shows a spinner while running the enclosed block."""
        with self.console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots"):
            yield
