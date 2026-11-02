#!/usr/bin/env python3
# MimirSynth
"""CheckMK notification script: sends each notification to a MimirSynth incoming webhook (template «CheckMK»).

Install it in ~/local/share/check_mk/notifications/ of the site (executable), and create a notification rule with the method
«MimirSynth». Parameters of the rule, in order:
  1. the webhook address, https://mimirsynth.example.com/api/brains/<slug>/hooks/<key>
  2. the webhook secret

It sends the notification context (the NOTIFY_* variables) as JSON, signed with HMAC-SHA256 in X-Hub-Signature-256. Only PROBLEM and
RECOVERY become memory; MimirSynth leaves acknowledgements, downtimes and flapping out. Standard library only.
"""
import hashlib
import hmac
import json
import os
import sys
import urllib.request

KEEP = ("WHAT", "NOTIFICATIONTYPE", "HOSTNAME", "HOSTALIAS", "SERVICEDESC", "HOSTSTATE", "SERVICESTATE", "HOSTOUTPUT", "SERVICEOUTPUT",
        "LONGDATETIME", "SHORTDATETIME", "MICROTIME")


def main() -> int:
    url, secret = os.environ.get("NOTIFY_PARAMETER_1", ""), os.environ.get("NOTIFY_PARAMETER_2", "")
    if not url or not secret:
        print("mimirsynth: falta la dirección o el secreto del webhook en los parámetros de la regla", file=sys.stderr)
        return 2
    body = json.dumps({f"NOTIFY_{k}": os.environ[f"NOTIFY_{k}"] for k in KEEP if f"NOTIFY_{k}" in os.environ}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"mimirsynth: {r.status}")
            return 0
    except Exception as e:  # noqa: BLE001  (CheckMK shows the message and retries per its own rules)
        print(f"mimirsynth: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
