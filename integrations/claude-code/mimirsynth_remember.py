#!/usr/bin/env python3
"""Envía un aprendizaje a MimirSynth como propuesta (cuarentena si el token es de colaborador).

Uso:
  mimirsynth_remember.py --title "Base de datos migrada a db02" --content "El 19-oct la base de datos de producción pasó al servidor db02" [--confidence 0.8] [--source text|message|json] [--dry-run]

Configuración (variables MIMIRSYNTH_* o ~/.config/mimirsynth/config.json, claves en minúsculas):
  url, brain, write_token (token de API con rol colaborador o superior; si falta se usa `token`, que normalmente es de lector)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def cfg(key: str) -> str:
    v = os.environ.get(f"MIMIRSYNTH_{key.upper()}")
    if v:
        return v
    try:
        return json.loads((Path.home() / ".config" / "mimirsynth" / "config.json").read_text()).get(key.lower(), "")
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--confidence", type=float)
    ap.add_argument("--source", default="text", choices=["text", "message", "json"])
    ap.add_argument("--description", default="claude-code")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    url, brain = cfg("url").rstrip("/"), cfg("brain")
    token = cfg("write_token") or cfg("token")
    if not (url and brain and token):
        print("falta configuración: url, brain y write_token (o token)", file=sys.stderr)
        return 2
    payload = {"name": a.title, "body": a.content, "source": a.source, "source_description": a.description}
    if a.confidence is not None:
        payload["confidence"] = a.confidence
    if a.dry_run:
        print(json.dumps({"url": f"{url}/api/brains/{brain}/proposals", "payload": payload}, ensure_ascii=False, indent=2))
        return 0
    req = urllib.request.Request(f"{url}/api/brains/{brain}/proposals", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            body = json.loads(body).get("detail") or body  # p. ej. «token caducado el …: crea uno nuevo, o rótalo antes de que caduque»
        except ValueError:
            pass
        print(f"MimirSynth respondió {e.code}: {str(body)[:300]}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"no se pudo contactar con MimirSynth: {e}", file=sys.stderr)
        return 1
    print(f"propuesta #{r['id']} {r['status']} ({'pendiente de un curador' if r['status'] == 'pending' else 'aprobada; se ingiere en segundo plano'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
