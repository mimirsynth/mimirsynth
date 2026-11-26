**English** · [Español](Integraci%C3%B3n-con-Claude-Code)

# Claude Code integration

There are two ways to connect [Claude Code](https://claude.com/claude-code) to a brain, and they work side by side:

| Way | What it gives | When |
|---|---|---|
| **Plugin** (recommended) | What changed at session start, recall before every prompt, `/mimirsynth:status`, `:search` and `:remember`, and an optional capture of what each session learned | When you use Claude Code every day: the memory is there on every turn without Claude having to ask |
| **MCP server** | Claude gets the brain's tools (`recall`, `remember`, `facts_about`…) and decides when to read the memory and when to propose something | On its own, with nothing to install, or next to the plugin so Claude can ask again with other words |

## The plugin

### Install
In Claude Code:
```
/plugin marketplace add mimirsynth/mimirsynth
/plugin install mimirsynth@mimirsynth
```
The hooks need `python3` on the `PATH`.

### Setup
Run `/mimirsynth:setup`, which shows the command that configures it in your terminal:
```bash
python3 ~/.claude/plugins/…/mimirsynth/scripts/cli.py setup
```
It asks for the URL and the brain, a **reader** token for recall, optionally a **contributor** token to propose, and the capture mode, and writes the shared file ([[Agent plugin configuration]]). Tokens never go through the conversation. If MimirSynth is already set up for another agent on this machine, there is nothing to do.

### What it does
| When | What |
|---|---|
| Session start | The facts learned and invalidated since the last session, inside `<mimirsynth-news>`. With capture on `send`, the finished sessions are proposed |
| Every prompt | The recall for the prompt, inside `<mimirsynth-memory>`, as context, not as instructions. Prompts shorter than 12 characters and slash commands are skipped |
| After an edit, and when Claude stops | With capture on, the files changed and the last answer are noted for the session |
| Session end | Only closes the session's record: Claude Code gives a plugin 1.5 s, so nothing leaves the machine until the next start |

If MimirSynth does not answer within `timeout`, nothing is injected and the prompt carries on; an expired or revoked token is said.

### Commands
| Command | What it does |
|---|---|
| `/mimirsynth:setup` | Tells you how to configure it, and offers the status row |
| `/mimirsynth:status` | Connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts, other memory hooks on this machine, the last thing the memory did and whether the status row is on |
| `/mimirsynth:search <query>` | Recall on demand, with more results |
| `/mimirsynth:remember [title]` | Claude writes a memory from the conversation and sends it once you agree; with no title, it reviews the drafts the capture left |

### Capture
Off by default; `capture` decides it, with the same rules in every plugin ([[Agent plugin configuration]]).

### Status row
MimirSynth can show a row in Claude Code's status line, so you can tell what the memory did without asking:
```
● mimirsynth  my-brain · contributor · capture off · recall: 4 facts
```
- **The dot:** green when the last call worked, amber when the recall token expires within 7 days (the row says how many), red when MimirSynth could not be reached (`offline`), rejected the token or failed (`server error`, `unexpected answer`), grey before anything was asked (`ready`: the role came from the hour's cache and nothing at this start reached the server).
- **Then:** the brain, the recall token's role, the capture mode and the drafts waiting, and **what the memory last did**: `recall: 4 facts, 2 passages`, `recall: nothing relevant`, `recall: offline`, `recall: token rejected (401)`, `recall: server error 503`, `proposal #12 queued for review`, `connected`. A failed recall shows here instead of passing unnoticed, and the prompt still carries on.

A plugin cannot add a status line by itself. `/mimirsynth:setup` offers it, or run:
```bash
python3 ~/.claude/plugins/…/mimirsynth/scripts/cli.py statusline
```
It copies the row's script to `~/.config/mimirsynth/statusline.py`, a path that does not change when the plugin updates (each session start keeps the copy current), and adds `statusLine` to `~/.claude/settings.json`. **If you already have a status line it is left alone**, and the command prints what your own script can call to add MimirSynth's row. `cli.py statusline --remove` takes out only MimirSynth's. The row reads only files the hooks wrote, so it makes no network call. `/whoami` is asked at session start, at most once an hour, and not at all with `recall` and `news` both off; if it cannot reach the server, that start asks nothing else. What the server sends is shown without control characters. `NO_COLOR` turns the colours off.

### In the interface
Where Claude Code draws a plugin's interface (the terminal, or the desktop app on a local session), the plugin also shows, with nothing to set up:
- **A band above the prompt**, `● mimirsynth · my-brain · contributor · recall: 4 facts`, which says `recalling…` with an amber dot while the recall runs and turns red when it fails. It reads the same per-session file as the status row.
- **`· recalling`** after the spinner's word while the recall runs (terminal).
- **A line under the answer** saying which recalled fact helped and what for. With the recalled block the model is asked to end an answer a recalled fact shaped with `> ◉ MimirSynth: <the fact>: <what it was used for>`, and to leave it out otherwise; the plugin draws that line under the answer as a quote, `◉ the API port: it answered the question`. It costs no extra call, only a sentence of instructions in each recall. In a session the apps follow over Remote Control the line stays a quote inside the answer. Set `explain` off (`"explain": false` in the configuration file, `MIMIRSYNTH_EXPLAIN=off`, or a `projects` entry) to stop asking for it.

A session started from somewhere with no interface attached (`claude -p`, a cloud session followed from the web) shows neither the band nor the spinner, and a credit line the model writes stays part of the answer's text (it is asked to leave it out of output meant for a program, such as JSON). It needs a Claude Code version that loads plugin hooks modules; older versions ignore it and keep the rest of the plugin working.

### What it writes on your machine
- `~/.config/mimirsynth/config.json`, the shared configuration (by `setup`).
- With capture on: one file per session in the plugin's data folder (`$CLAUDE_PLUGIN_DATA/sessions`), or in `~/.config/mimirsynth/state/sessions/`, readable only by you, deleted after 14 days.
- For the status row, in `~/.config/mimirsynth/status/` (deleted after 7 days): one small file per session with the brain, the token's role and expiry, the capture mode, the drafts and the last action (never a token, a prompt or a fact); `_shared.json`, the last proposal sent with `/mimirsynth:remember`; and `_whoami.json`, the recall token's role and expiry under a short hash of the server, the brain and the token. With `cli.py statusline`, the row's script in `~/.config/mimirsynth/statusline.py` and the `statusLine` entry in `~/.claude/settings.json`.

If another plugin or hook also injects memory, the session start says so; it does not block anything, and MimirSynth's blocks are marked so you can tell them apart.

### Update and remove
- Update: `claude plugin marketplace update mimirsynth`, then `claude plugin update mimirsynth@mimirsynth` (or **Update now** under `/plugin` → Installed), then `/reload-plugins`.
- Remove: `/plugin uninstall mimirsynth@mimirsynth`.

## Over MCP
1. Create a token for the brain with the **Contributor** role in [[My account]] → **API tokens** ([[Connect agents]]). With a **Reader** token Claude can only read.
2. Add the server:
   ```bash
   claude mcp add --transport http mimirsynth "https://mimirsynth.example.com/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
   ```
   Add `--scope user` to have it in every project, not only the current one. For a second brain, add another server with another name and its own token.
3. In Claude Code, `/mcp` should list `mimirsynth` as connected, with its tools.

What the main tools do (the full list is in [[Connect agents]]):
- **`recall`**: Claude asks the memory a question and gets the current (and some invalidated) facts, episode fragments and document passages, with their provenance. If other brains lend to this one, their content comes too, marked with its origin.
- **`remember`**: Claude proposes something worth keeping (a decision, a configuration change, the cause of a failure). With a contributor token it goes into **quarantine** until a curator or the decider approves it ([[Proposals]]); with a curator token it is approved at once. Secrets are masked or blocked according to the brain's policy.

The tool descriptions follow the language rules in [[Connect agents]] (without an `Accept-Language` header, the language the token's owner chose). To make Claude use them consistently, say so in your `CLAUDE.md` or project instructions, for example: "Before answering about this project's decisions, configuration or history, use `recall`. When you learn something that should last, propose it with `remember`." Writing guidelines in [[Writing good memory]].

## Migrating from the loose hook
Before the plugin, the recall hook was a loose script, `mimirsynth_recall.py`, added by hand to `~/.claude/settings.json`, with `mimirsynth_remember.py` to propose from the command line. Both are still in [`integrations/claude-code`](https://github.com/mimirsynth/mimirsynth/tree/main/integrations/claude-code) and keep working, but the plugin does the same and more:
1. Install the plugin. Your `~/.config/mimirsynth/config.json` keeps working, with the same keys.
2. Remove the `mimirsynth_recall.py` hook from `~/.claude/settings.json`, or the context is injected twice. `/mimirsynth:status` warns while it is there.
3. `mimirsynth_remember.py` can stay for scripts. Inside Claude Code, `/mimirsynth:remember` does the same.

## Checking it works
- **Plugin:** `/mimirsynth:status` checks each token against the server; then ask something the brain knows and the answer should use it.
- **MCP:** `/mcp` in Claude Code shows the server and its tools; ask something the brain knows and Claude should call `recall`.
- In the [[Audit log]] and in [[My account]] you will see the token's **last use**.

## Troubleshooting
| Symptom | What to do |
|---|---|
| No memory before the prompts | `/mimirsynth:status`: `url`, `brain` or `token` are missing, or `recall` is off |
| «python3: command not found» in the hooks | Install Python 3 and put it on the `PATH` |
| The context appears twice | The loose `mimirsynth_recall.py` hook is still in `settings.json`: remove it |
| Nothing comes back | Check the URL (no trailing slash), the brain's slug and that the token belongs to that same brain. Over MCP, a `401` means the header is missing or the token is not valid |
| «token expired» or «revoked» | Create or rotate the token ([[Connect agents]]) and run `setup` again |
| The status row says `recall: offline` or the dot is red | MimirSynth did not answer within `timeout`, rejected the token or failed: `/mimirsynth:status` says which |

Full detail: [the plugin's README](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/claude-code/README.md).

## Other agents
Codex, OpenCode, Hermes Agent and OpenClaw have native plugins of their own, with the same configuration: see [2. Pick your agent](Connect-agents#2-pick-your-agent). Any other MCP client connects to the same address; anything else uses the HTTP API in [[Connect agents]].
