"""Claude Code headless (`claude -p`). Con CLAUDE_CODE_OAUTH_TOKEN usa la suscripción Pro/Max: costo $0."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..config import Settings
from .base import LLM


class ClaudeCLI(LLM):
    name = "claude_cli"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.binary = shutil.which("claude")
        if not self.binary:
            raise RuntimeError("No encontré el binario `claude`. Instalá: npm i -g @anthropic-ai/claude-code")

    def complete(self, prompt, images=None, task="", context=None) -> str:
        images = [Path(p).resolve() for p in images or []]
        if images:
            listing = "\n".join(f"- {p}" for p in images)
            prompt = (
                "Usá la herramienta Read para mirar cada una de estas imágenes antes de responder:\n"
                f"{listing}\n\n{prompt}"
            )
        cmd = [self.binary, "-p", prompt, "--output-format", "json", "--max-turns", str(4 + len(images))]
        if images:
            cmd += ["--allowedTools", "Read"]
            for d in sorted({str(p.parent) for p in images}):
                cmd += ["--add-dir", d]
        else:
            cmd += ["--disallowedTools", "Bash,Edit,Write,WebFetch,WebSearch"]
        if model := self.settings.get("llm.model"):
            cmd += ["--model", model]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.settings.root,
            timeout=self.settings.get("llm.timeout_s", 600),
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p falló ({proc.returncode}): {proc.stderr[-800:] or proc.stdout[-800:]}")
        payload = json.loads(proc.stdout)
        if payload.get("is_error"):
            raise RuntimeError(f"claude -p devolvió error: {payload.get('result')}")
        return payload.get("result", "")
