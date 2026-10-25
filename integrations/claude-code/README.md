**English** · [Español](README.es.md)

# MimirSynth for Claude Code

A `UserPromptSubmit` hook that queries MimirSynth before every prompt and injects the relevant facts and fragments. Read-only (token role `reader`).

1. In MimirSynth: My account → API tokens → create a token with the *Reader* role for your brain.
2. Save the configuration in `~/.config/mimirsynth/config.json`:
   ```json
   {"url": "https://mimirsynth.example.com", "token": "mst_...", "brain": "my-brain"}
   ```
3. Add the hook in `~/.claude/settings.json`:
   ```json
   {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 /path/to/mimirsynth_recall.py"}]}]}}
   ```
If the server does not respond within 4 s, nothing is injected and the prompt carries on.

## Writing memory (proposals)

`mimirsynth_remember.py` sends a learning as a proposal:

```bash
python3 mimirsynth_remember.py --title "Database moved to db02" --content "On 19 Oct the production database moved to server db02" --confidence 0.8
```

- It uses `write_token` from `~/.config/mimirsynth/config.json` (an API token with the **contributor** role: it goes into quarantine and a curator or the decider approves it). Without it, it uses `token`, which returns 403 if it is a reader token.
- With a curator token it is approved and ingested right away. Contributor is recommended for agents.
- `--dry-run` shows the request without sending it.

## Documents in recall

With document memory, the context returned by `/recall` can include a `## Documents` section with up to 2 cited passages (title, section, `[doc N, chunk M]`). It only appears if there is a really relevant passage, it does not exceed ~600 tokens and it is omitted if the search takes longer than 0.6 s. The agent can ask for more context with `GET /api/brains/{slug}/docs/{N}/context?chunk={M}` or the original with `/docs/{N}/file`. To disable it for one request, use `"docs": 0`; the threshold (Administration → Recall → "Minimum similarity of a passage") must be recalibrated if the embedding model changes.
