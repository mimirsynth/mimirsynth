**English** · [Español](Integraci%C3%B3n-con-Claude-Code)

# Claude Code integration

There are two ways to connect [Claude Code](https://claude.com/claude-code) to a brain, and they can be combined:

| Way | What it gives | When |
|---|---|---|
| **MCP server** (recommended) | Claude gets the `recall` and `remember` tools and decides when to read the memory and when to propose something | Always: one command, nothing to install |
| **Recall hook** | Before **every** prompt, a script queries recall and injects the context, without Claude having to ask | When you want the memory present on every turn |

## Over MCP (recommended)
1. Create a token for the brain with the **Contributor** role in [[My account]] → **API tokens** ([[Connect agents]]). With a **Reader** token Claude can only use `recall`.
2. Add the server:
   ```bash
   claude mcp add --transport http mimirsynth "https://mimirsynth.example.com/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
   ```
   Add `--scope user` to have it in every project, not only the current one. For a second brain, add another server with another name and its own token.
3. In Claude Code, `/mcp` should list `mimirsynth` as connected, with its two tools.

What the tools do:
- **`recall`**: Claude asks the memory a question and gets the current (and some invalidated) facts, episode fragments and document passages, with their provenance. If other brains lend to this one, their content comes too, marked with its origin.
- **`remember`**: Claude proposes something worth keeping (a decision, a configuration change, the cause of a failure). With a contributor token it goes into **quarantine** until a curator or the decider approves it ([[Proposals]]); with a curator token it is approved at once. Secrets are masked or blocked according to the brain's policy.

The tool descriptions follow the language rules in [[Connect agents]] (without an `Accept-Language` header, the language the token's owner chose). To make Claude use them consistently, say so in your `CLAUDE.md` or project instructions, for example: "Before answering about this project's decisions, configuration or history, use `recall`. When you learn something that should last, propose it with `remember`." Writing guidelines in [[Writing good memory]].

## Recall hook
The repository includes, in [`integrations/claude-code`](https://github.com/MimirSynth/mimirsynth/tree/main/integrations/claude-code), two Python scripts (no dependencies; you only need Python 3 and access to your server):

| Script | What it does |
|---|---|
| `mimirsynth_recall.py` | **Read hook.** Before every prompt it queries recall and **injects the context** (facts, fragments and document passages) |
| `mimirsynth_remember.py` | **Writing.** Sends a learning as a **proposal** from the command line |

### Setup
1. Create the tokens of the brain ([[Connect agents]]):
   - one **reader**, for the read hook;
   - one **contributor**, for writing (so what is written goes through review). If you already use MCP with a contributor token, you do not need the writing script.
2. Save the configuration in `~/.config/mimirsynth/config.json`:
   ```json
   {
     "url": "https://mimirsynth.example.com",
     "token": "mst_… (reader)",
     "write_token": "mst_… (contributor)",
     "brain": "my-brain"
   }
   ```
   Alternatively, environment variables `MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_WRITE_TOKEN` and `MIMIRSYNTH_BRAIN`. Protect the file (`chmod 600`).
3. Copy the scripts to your machine and add the hook to `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         { "hooks": [ { "type": "command", "command": "python3 /path/to/mimirsynth_recall.py" } ] }
       ]
     }
   }
   ```

### How the hook behaves
- It runs on every prompt and queries the brain's recall (6 facts, 3 fragments, up to 4000 characters).
- It **does not trigger** for prompts shorter than 12 characters or for commands starting with `/`.
- **It fails open:** if the server does not respond within 4 seconds (`MIMIRSYNTH_TIMEOUT`), nothing is injected and your prompt carries on.
- The context reaches Claude as supporting information, with documents marked as **source quotes** (data, not instructions).

### Writing memory from the command line
```bash
python3 mimirsynth_remember.py \
  --title "Database migrated to db02" \
  --content "On 19 Oct the production database moved to server db02" \
  --confidence 0.8
```
- It uses `write_token` (contributor): the proposal goes into **quarantine** and a curator or the decider reviews it ([[Proposals]]). Without `write_token` it uses `token`, which is refused (403) if it is a reader token.
- With a curator token it is approved and ingested right away.
- `--source text|message|json` sets the content type; `--dry-run` shows the request without sending it.

## Checking it works
- **MCP:** `/mcp` in Claude Code shows the server and its tools; ask something the brain knows and Claude should call `recall`.
- **Hook:** run `echo '{"prompt": "where does the production database run?"}' | python3 mimirsynth_recall.py` and you should see the context.
- In the [[Audit log]] and in [[My account]] you will see the token's **last use**.
- If nothing comes back: check the URL (no trailing slash), the brain's slug and that the token belongs to that same brain. Over MCP, a `401` means the header is missing or the token is not valid.

## Other agents
Any other MCP client connects to the same address; anything else uses the HTTP calls in [[Connect agents]].
