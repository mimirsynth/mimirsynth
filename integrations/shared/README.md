**English** · [Español](README.es.md)

# Shared client library for agent integrations

What every MimirSynth agent plugin (`integrations/<agent>/`) is built on: the shared configuration (`~/.config/mimirsynth/config.json`), the calls to a brain (recall, news, whoami, proposals), secret redaction with the server's own detector, fail-open timeouts and the optional session capture. The contract and the API are documented in [`docs/AGENT_CLIENT.md`](../../docs/AGENT_CLIENT.md).

| Folder | What |
|---|---|
| `python/mimirsynth_agent/` | The library in Python, standard library only. The source of truth |
| `typescript/` | Its TypeScript port for JavaScript agents (`npm test` runs the contract cases, `npm run check` the types) |
| `contract/cases.json` | The cases every implementation must pass |
| `vendor.py` | Copies the Python library into each plugin (`--check` lists the stale copies) |

A Python plugin carries an exact copy of `python/mimirsynth_agent/`, because an agent installs only the plugin's folder. After changing the library, or `api/mimirsynth/secretscan.py`, run:

```bash
python integrations/shared/vendor.py
```
