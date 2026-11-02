**English** · [Español](README.es.md)

# CheckMK → MimirSynth

`mimirsynth.py` is a CheckMK notification script that sends each notification to a MimirSynth **incoming webhook** with the
**CheckMK** template. A problem opens an alert, its recovery closes it, and MimirSynth turns that into an episodic memory proposal
(«what happened and when»), grouping the repeated notices. See «Incoming webhooks» in the wiki.

## Install
1. In MimirSynth, Administration → Brain access → **Incoming webhooks** → **Create webhook**, template **CheckMK**. Copy its address
   and its secret (shown once).
2. On the CheckMK site, as the site user:
   ```bash
   cp mimirsynth.py ~/local/share/check_mk/notifications/mimirsynth.py
   chmod +x ~/local/share/check_mk/notifications/mimirsynth.py
   ```
3. Setup → Notifications → add a rule with the method **MimirSynth** and two parameters: the webhook address and its secret. Limit it
   to the hosts and services whose problems are worth remembering.

It only uses the standard library. It sends the notification context (`NOTIFY_*` variables) signed with HMAC-SHA256 in the
`X-Hub-Signature-256` header. Only `PROBLEM` and `RECOVERY` become memory; acknowledgements, downtimes and flapping are left out.
