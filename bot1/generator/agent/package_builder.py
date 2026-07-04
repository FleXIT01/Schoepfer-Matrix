"""Deterministischer Bauplan des generierten Bot-Pakets.

Erzeugt aus einer BotSpec + aufgelösten Tools ein Datei-Set
({relativer_pfad: inhalt}). Komplett ohne LLM — diese Basis besteht von sich
aus alle Gates. Die Agenten (Phase C/D) ersetzen anschließend Tool-Bodies und
verfeinern den System-Prompt, jeweils gegen dieselben Gates abgesichert.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..models.bot_spec import BotSpec
from .tools import library


@dataclass
class ResolvedTool:
    name: str
    func_source: str            # eigenständiger module-level `def name(...):`
    definition: dict            # {"name","description","input_schema"}
    sample_input: dict = field(default_factory=dict)
    from_library: bool = False
    is_stub: bool = False


# ---------------------------------------------------------------------------
# Tool-Auflösung
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip().lower()).strip("_")
    s = re.sub(r"_+", "_", s)
    return s or "bot"


def _stub_tool(name: str, description: str) -> ResolvedTool:
    """Sicherer Platzhalter, der einen String zurückgibt (besteht den tool_gate)."""
    src = (
        f"def {name}(query: str = \"\") -> str:\n"
        f"    \"\"\"{description or name}\"\"\"\n"
        f"    # TODO: echte Implementierung — wird vom CoderAgent ersetzt\n"
        f"    return \"[Tool '{name}' noch nicht implementiert. Eingabe: \" + str(query) + \"]\"\n"
    )
    definition = {
        "name": name,
        "description": description or name,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Eingabe für das Tool"}},
            "required": ["query"],
        },
    }
    return ResolvedTool(name=name, func_source=src, definition=definition,
                        sample_input={"query": "test"}, from_library=False, is_stub=True)


def resolve_skeleton_tools(spec: BotSpec) -> list[ResolvedTool]:
    """Baseline-Auflösung (kein LLM): Bibliothek wenn Name passt, sonst Stub."""
    resolved: list[ResolvedTool] = []
    for tool in spec.tools:
        entry = library.get(tool.name)
        if entry is not None:
            resolved.append(ResolvedTool(
                name=entry.name,
                func_source=entry.func_source,
                definition=entry.definition,
                sample_input=entry.sample_input,
                from_library=True,
            ))
        else:
            resolved.append(_stub_tool(_slug(tool.name), tool.description))
    return resolved


# ---------------------------------------------------------------------------
# Datei-Erzeugung
# ---------------------------------------------------------------------------

def build_package(spec: BotSpec, tools: list[ResolvedTool]) -> dict[str, str]:
    slug = _slug(spec.name)
    model = spec.llm.model or ("llama3.1" if spec.llm.provider == "ollama" else "")
    files = {
        "bot/__init__.py": '"""Generiertes Bot-Paket."""\n',
        "bot/config.py": _config_py(spec, slug, model),
        "bot/memory.py": _memory_py(spec),
        "bot/llm_client.py": _llm_client_py(),
        "bot/tools.py": _tools_py(tools),
        "bot/runner.py": _runner_py(spec, tools),
        "run.py": _run_py(),
        "test_smoke.py": _test_smoke_py(),
        "requirements.txt": _requirements_txt(spec),
        ".env.example": _env_example(spec),
    }
    return files


def _config_py(spec: BotSpec, slug: str, model: str) -> str:
    return f'''from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BotConfig:
    """Zentrale Konfiguration für {spec.name}."""

    name: str = {spec.name!r}
    provider: str = {spec.llm.provider!r}
    model: str = {model!r}
    temperature: float = {spec.llm.temperature}
    max_tokens: int = {spec.llm.max_tokens}
    language: str = {spec.language!r}
    api_base_url: str = "http://localhost:11434"
    api_key: str = ""
    max_tool_steps: int = 5
    memory_path: str = ".{slug}_memory.json"
'''


def _memory_py(spec: BotSpec) -> str:
    persistent = spec.memory_strategy.value in ("persistent_json", "persistent_db")
    autoload = "True" if persistent else "False"
    return f'''from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BotMemory:
    """Gesprächsverlauf + Zustand. Strategie: {spec.memory_strategy.value}"""

    persistent = {autoload}

    def __init__(self, config) -> None:
        self.config = config
        self.conversation_history: list[dict] = []
        self.state: dict[str, Any] = {{}}
        self._path = Path(getattr(config, "memory_path", ".bot_memory.json"))

    def add_message(self, role: str, content: str) -> None:
        self.conversation_history.append({{"role": role, "content": content}})

    def get_context_window(self, max_turns: int = 12) -> list[dict]:
        return self.conversation_history[-(max_turns * 2):]

    def set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def clear(self) -> None:
        self.conversation_history.clear()
        self.state.clear()

    def save(self) -> None:
        data = {{"history": self.conversation_history, "state": self.state}}
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self.conversation_history = data.get("history", [])
            self.state = data.get("state", {{}})
'''


def _llm_client_py() -> str:
    return '''from __future__ import annotations

import os


class LLMClient:
    """Eigenständiger, provider-agnostischer LLM-Client.

    Schnittstelle: chat(messages, system=None) -> str
    messages: list[{"role": str, "content": str}]
    """

    def __init__(self, config) -> None:
        self.config = config
        self._client = None

    def chat(self, messages, system=None, temperature=None, max_tokens=None):
        provider = (self.config.provider or "ollama").lower()
        temperature = self.config.temperature if temperature is None else temperature
        max_tokens = self.config.max_tokens if max_tokens is None else max_tokens

        if provider == "ollama":
            return self._chat_ollama(messages, system, temperature, max_tokens)
        if provider == "anthropic":
            return self._chat_anthropic(messages, system, temperature, max_tokens)
        if provider in ("openai", "lmstudio", "openai-compat", "openai_compat", "custom"):
            return self._chat_openai(messages, system, temperature, max_tokens, provider)
        raise RuntimeError(f"Unbekannter Provider: {provider}")

    def _chat_ollama(self, messages, system, temperature, max_tokens):
        import httpx

        if self._client is None:
            self._client = httpx.Client(base_url=self.config.api_base_url, timeout=120.0)
        api_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
        payload = {
            "model": self.config.model or "llama3.1",
            "messages": api_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        resp = self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _chat_anthropic(self, messages, system, temperature, max_tokens):
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self.config.api_key or os.environ.get("ANTHROPIC_API_KEY") or None
            )
        resp = self._client.messages.create(
            model=self.config.model or "claude-sonnet-4-6",
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=list(messages),
        )
        return resp.content[0].text

    def _chat_openai(self, messages, system, temperature, max_tokens, provider):
        import openai

        if self._client is None:
            base_url = self.config.api_base_url
            if provider in ("lmstudio",) and not base_url.endswith("/v1"):
                base_url = "http://localhost:1234/v1"
            kwargs = {"api_key": self.config.api_key or os.environ.get("OPENAI_API_KEY") or "no-key"}
            if provider != "openai":
                kwargs["base_url"] = base_url
            self._client = openai.OpenAI(**kwargs)
        api_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
        resp = self._client.chat.completions.create(
            model=self.config.model or "gpt-4o",
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
'''


def _tools_py(tools: list[ResolvedTool]) -> str:
    parts = ["from __future__ import annotations", ""]
    for t in tools:
        parts.append(t.func_source.rstrip("\n"))
        parts.append("")

    def _func_identifier(rt: "ResolvedTool") -> str:
        import ast as _ast
        try:
            tree = _ast.parse(rt.func_source)
            for node in tree.body:
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    return node.name
        except SyntaxError:
            pass
        return rt.name

    func_map = "\n".join(f"    {t.name!r}: {_func_identifier(t)}," for t in tools)
    definitions = ",\n".join("    " + json.dumps(t.definition, ensure_ascii=False) for t in tools)

    parts.append(f"_TOOL_FUNCS = {{\n{func_map}\n}}" if tools else "_TOOL_FUNCS = {}")
    parts.append("")
    parts.append(f"_TOOL_DEFINITIONS = [\n{definitions}\n]" if tools else "_TOOL_DEFINITIONS = []")
    parts.append("")
    parts.append('''

class BotTools:
    """Tool-Registry + Dispatch für den generierten Bot."""

    def __init__(self, config) -> None:
        self.config = config

    def dispatch(self, name: str, args: dict) -> str:
        fn = _TOOL_FUNCS.get(name)
        if fn is None:
            return f"[Fehler: unbekanntes Tool '{name}']"
        if not isinstance(args, dict):
            return f"[Fehler: args muss ein Objekt sein, war {type(args).__name__}]"
        try:
            return str(fn(**args))
        except TypeError as exc:
            return f"[Fehler: falsche Argumente für '{name}': {exc}]"
        except Exception as exc:  # noqa: BLE001
            return f"[Tool-Fehler '{name}': {exc}]"

    def get_tool_definitions(self) -> list[dict]:
        return list(_TOOL_DEFINITIONS)

    def tool_names(self) -> list[str]:
        return list(_TOOL_FUNCS.keys())
'''.strip("\n"))
    return "\n".join(parts) + "\n"


def _runner_py(spec: BotSpec, tools: list[ResolvedTool]) -> str:
    has_tools = bool(tools)
    tool_lines = "\n".join(
        f"- {t.definition.get('name', t.name)}: {t.definition.get('description', '')}"
        for t in tools
    )
    base_prompt = spec.system_prompt or f"Du bist {spec.name}."

    if has_tools:
        tool_instructions = (
            "\\n\\nDu hast Zugriff auf folgende Tools:\\n"
            + tool_lines.replace("\n", "\\n")
            + "\\n\\nUm ein Tool zu nutzen, antworte AUSSCHLIESSLICH mit JSON in genau dieser Form:\\n"
            + '{\\"tool\\": \\"<name>\\", \\"args\\": {...}}\\n'
            + "Brauchst du kein Tool, antworte normal in Textform. "
            + "Nach einer Zeile, die mit [TOOL-ERGEBNIS beginnt, gib die finale Antwort "
            + "oder rufe ein weiteres Tool auf."
        )
    else:
        tool_instructions = ""

    return f'''from __future__ import annotations

import json
import re

from bot.config import BotConfig
from bot.memory import BotMemory
from bot.tools import BotTools
from bot.llm_client import LLMClient

_BASE_SYSTEM_PROMPT = {base_prompt!r}
_TOOL_INSTRUCTIONS = "{tool_instructions}"


def _parse_tool_call(text: str, known: list) -> tuple | None:
    """Findet ein {{\"tool\":..., \"args\":...}} JSON-Objekt im Text."""
    start = text.find("{{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{{":
                depth += 1
            elif text[i] == "}}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict) and obj.get("tool") in known:
                        args = obj.get("args", {{}})
                        return obj["tool"], (args if isinstance(args, dict) else {{}})
                    break
        start = text.find("{{", start + 1)
    return None


class BotRunner:
    """Haupt-Bot mit Laufzeit-Tool-Schleife für {spec.name}."""

    def __init__(self, config: BotConfig | None = None, llm_client=None) -> None:
        self.config = config or BotConfig()
        self.memory = BotMemory(self.config)
        self.tools = BotTools(self.config)
        self.llm = llm_client if llm_client is not None else LLMClient(self.config)

    def _system_prompt(self) -> str:
        return _BASE_SYSTEM_PROMPT + _TOOL_INSTRUCTIONS

    def respond(self, user_message: str) -> str:
        self.memory.add_message("user", user_message)
        known = self.tools.tool_names()
        for _ in range(max(1, self.config.max_tool_steps)):
            raw = self.llm.chat(self.memory.get_context_window(), system=self._system_prompt())
            call = _parse_tool_call(raw, known) if known else None
            if call is None:
                self.memory.add_message("assistant", raw)
                return raw
            name, args = call
            result = self.tools.dispatch(name, args)
            self.memory.add_message("assistant", raw)
            self.memory.add_message("user", f"[TOOL-ERGEBNIS {{name}}]: {{result}}")
        final = self.llm.chat(
            self.memory.get_context_window() + [
                {{"role": "user", "content": "Fasse jetzt OHNE weiteres Tool die finale Antwort zusammen."}}
            ],
            system=self._system_prompt(),
        )
        self.memory.add_message("assistant", final)
        return final

    def run_interactive(self) -> None:
        print(f"Bot '{{self.config.name}}' gestartet. Tippe 'exit' zum Beenden.")
        print("-" * 60)
        if self.memory.persistent:
            self.memory.load()
        while True:
            try:
                user_input = input("Du: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\\nBot beendet.")
                break
            if user_input.lower() in ("exit", "quit", "beenden"):
                print("Bot beendet.")
                break
            if not user_input:
                continue
            try:
                reply = self.respond(user_input)
                print(f"\\nBot: {{reply}}\\n")
            except Exception as exc:  # noqa: BLE001
                print(f"\\n[FEHLER] {{exc}}\\n")
        if self.memory.persistent:
            self.memory.save()
'''


def _run_py() -> str:
    return '''from __future__ import annotations

from bot.config import BotConfig
from bot.runner import BotRunner


def main() -> None:
    runner = BotRunner(BotConfig())
    runner.run_interactive()


if __name__ == "__main__":
    main()
'''


def _test_smoke_py() -> str:
    return '''"""Offline-Smoke-Test: prüft den Bot mit einem gemockten LLM (kein Modell nötig)."""
from __future__ import annotations

from bot.config import BotConfig
from bot.runner import BotRunner


class _MockLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, system=None, temperature=None, max_tokens=None):
        self.calls += 1
        return "Deterministische Testantwort."


def test_respond_returns_string():
    bot = BotRunner(config=BotConfig(), llm_client=_MockLLM())
    out = bot.respond("Hallo")
    assert isinstance(out, str) and out.strip()


if __name__ == "__main__":
    test_respond_returns_string()
    print("SMOKE_OK")
'''


def _requirements_txt(spec: BotSpec) -> str:
    provider = spec.llm.provider.lower()
    deps = ["httpx>=0.27.0"]
    if provider == "anthropic":
        deps.append("anthropic>=0.40.0")
    elif provider in ("openai", "lmstudio", "openai-compat", "openai_compat", "custom"):
        deps.append("openai>=1.30.0")
    return "\n".join(deps) + "\n"


def _env_example(spec: BotSpec) -> str:
    provider = spec.llm.provider.lower()
    if provider == "anthropic":
        return "ANTHROPIC_API_KEY=sk-ant-...\n"
    if provider in ("openai", "lmstudio", "openai-compat", "openai_compat", "custom"):
        return "OPENAI_API_KEY=sk-...\n"
    return "# Ollama braucht keinen API-Key. Stelle sicher, dass 'ollama serve' läuft.\n"
