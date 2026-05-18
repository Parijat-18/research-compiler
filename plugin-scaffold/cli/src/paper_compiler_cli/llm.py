"""LLM backend abstraction.

Resolves which backend to call in this priority order:

1. ``ANTHROPIC_API_KEY`` set + ``anthropic`` SDK installed  → direct API call.
2. ``claude`` CLI on PATH                                   → headless ``claude -p``
   subprocess. Uses the user's Claude Code subscription auth (OAuth or keychain).
   No separate API key required.
3. Neither available                                        → returns ``None``.
   Callers must fall back to heuristics only.

Why option 2 exists: users running paper-compiler from inside a Claude Code
session already have Anthropic auth via their Claude Code subscription. Forcing
them to provision an API key separately is friction we don't need. We shell out
to ``claude -p`` which reuses the same auth.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from .config import Config


@dataclass
class LLMResult:
    text: str
    backend: str  # "anthropic" | "claude_cli"


class LLMUnavailable(Exception):
    pass


def _has_anthropic_sdk(cfg: Config) -> bool:
    if not cfg.llm.api_key:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _has_claude_cli() -> bool:
    return shutil.which("claude") is not None


def llm_backend(cfg: Config) -> Optional[str]:
    """Return ``"anthropic"``, ``"claude_cli"``, or ``None``."""
    if _has_anthropic_sdk(cfg):
        return "anthropic"
    if _has_claude_cli():
        return "claude_cli"
    return None


def call_llm(
    cfg: Config,
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 400,
    json_schema: Optional[dict] = None,
) -> Optional[LLMResult]:
    """Call the best available backend. Returns ``None`` on failure."""
    backend = llm_backend(cfg)
    if backend is None:
        return None
    model = model or cfg.llm.classifier_model

    if backend == "anthropic":
        return _call_anthropic(cfg, system, user, model=model, max_tokens=max_tokens)
    if backend == "claude_cli":
        return _call_claude_cli(system, user, model=model, max_tokens=max_tokens, json_schema=json_schema)
    return None


def _call_anthropic(cfg: Config, system: str, user: str, *, model: str, max_tokens: int) -> Optional[LLMResult]:
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    try:
        client = Anthropic(api_key=cfg.llm.api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return LLMResult(text=text, backend="anthropic")
    except Exception as e:  # noqa: BLE001
        print(f"anthropic call failed: {e}", file=sys.stderr)
        return None


def _call_claude_cli(
    system: str,
    user: str,
    *,
    model: str,
    max_tokens: int,
    json_schema: Optional[dict],
) -> Optional[LLMResult]:
    args = [
        "claude",
        "-p",
        "--system-prompt",
        system,
        "--tools",
        "",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--output-format",
        "json",
        "--model",
        model,
    ]
    if json_schema is not None:
        args += ["--json-schema", json.dumps(json_schema)]
    args.append(user)

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "CLAUDE_CODE_QUIET": "1"},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"claude -p call failed: {e}", file=sys.stderr)
        return None

    if proc.returncode != 0:
        print(f"claude -p exit {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
        return None

    raw = proc.stdout.strip()
    if not raw:
        return None

    # `claude -p --output-format json` returns a JSON envelope:
    # {"type":"result","result":"<assistant text>", ...}
    try:
        envelope = json.loads(raw)
        text = envelope.get("result") or envelope.get("text") or ""
        if not text and isinstance(envelope, list):
            # stream-json fallback
            for chunk in envelope:
                if chunk.get("type") == "text":
                    text += chunk.get("text", "")
    except json.JSONDecodeError:
        text = raw

    return LLMResult(text=text.strip(), backend="claude_cli")


def parse_json_object(text: str) -> Optional[dict]:
    """Extract the first JSON object from a model response."""
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        return None
