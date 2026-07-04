"""Deterministischer LLM-Stub für Smoke-Tests.

Wird in den Subprozess-Treiber eingebettet, damit Gates ohne laufendes Modell
und ohne echte API-Calls funktionieren. Der Stub erfüllt dieselbe Schnittstelle
wie der generierte ``LLMClient``: ``chat(messages, system=None) -> str``.
"""
from __future__ import annotations

# Variante A: antwortet immer mit reinem Text (kein Tool-Aufruf) → respond() endet sofort.
MOCK_LLM_PLAIN_SOURCE = '''
class MockLLM:
    """Gibt deterministisch reinen Text zurück (kein Tool-Aufruf)."""

    def __init__(self, *args, **kwargs):
        self.calls = 0

    def chat(self, messages, system=None, temperature=0.0, max_tokens=0):
        self.calls += 1
        return "Dies ist eine deterministische Testantwort."
'''

# Variante B: erzwingt im 1. Schritt einen Tool-Aufruf, danach reinen Text.
# Erlaubt einen End-to-End-Test der Laufzeit-Tool-Schleife ohne echtes Modell.
MOCK_LLM_TOOL_SOURCE = '''
import json as _json


class MockLLM:
    """Erster Aufruf -> Tool-JSON, danach reiner Text. Testet die Tool-Schleife."""

    def __init__(self, tool_name, tool_args):
        self._tool_name = tool_name
        self._tool_args = tool_args
        self.calls = 0

    def chat(self, messages, system=None, temperature=0.0, max_tokens=0):
        self.calls += 1
        if self.calls == 1:
            return _json.dumps({"tool": self._tool_name, "args": self._tool_args})
        return "Fertig — Tool-Ergebnis verarbeitet."
'''
