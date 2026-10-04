"""Extracción robusta de JSON desde respuestas de LLM."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str):
    """Devuelve el primer objeto/array JSON válido que aparezca en el texto."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        cand = cand.strip()
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            end = cand.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(cand[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError(f"No encontré JSON válido en la respuesta: {text[:300]!r}")
