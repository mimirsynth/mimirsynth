#!/usr/bin/env python3
"""Hook UserPromptSubmit de Claude Code: inyecta como contexto el recall de MimirSynth para el prompt del usuario.

Configuración (variables de entorno o ~/.config/mimirsynth/config.json con las mismas claves en minúsculas):
  MIMIRSYNTH_URL    https://mimirsynth.example.com
  MIMIRSYNTH_TOKEN  token de API del brain (créalo en Administración -> Tokens)
  MIMIRSYNTH_BRAIN  slug del brain
Falla en abierto: si algo no responde en pocos segundos, no inyecta nada y no bloquea el prompt.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

TIMEOUT = float(os.environ.get("MIMIRSYNTH_TIMEOUT", "4"))


def cfg(key: str) -> str:
    v = os.environ.get(f"MIMIRSYNTH_{key.upper()}")
    if v:
        return v
    f = Path.home() / ".config" / "mimirsynth" / "config.json"
    try:
        return json.loads(f.read_text()).get(key.lower(), "")
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    try:
        prompt = (json.load(sys.stdin).get("prompt") or "").strip()
    except Exception:  # noqa: BLE001
        return 0
    url, token, brain = cfg("url").rstrip("/"), cfg("token"), cfg("brain")
    if not (url and token and brain) or len(prompt) < 12 or prompt.startswith("/"):
        return 0
    req = urllib.request.Request(
        f"{url}/api/brains/{brain}/recall",
        data=json.dumps({"query": prompt[:1500], "facts": 6, "chunks": 3, "max_chars": 4000}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        ctx = json.load(urllib.request.urlopen(req, timeout=TIMEOUT)).get("context", "").strip()
    except Exception:  # noqa: BLE001
        return 0
    if ctx:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                  "additionalContext": f"<mimirsynth-memory>\n{ctx}\n</mimirsynth-memory>"}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
