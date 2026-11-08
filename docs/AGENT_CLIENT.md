**English** · [Español](es/AGENT_CLIENT.md)

# Agent integrations: the configuration contract and the shared client library

Every native agent plugin (Claude Code today; Codex, OpenCode, Hermes Agent and OpenClaw on the way) reads **one configuration** and is built on **one client library**, so that a single `setup` serves every agent on a machine and they all behave the same way: recall before each prompt, what changed at session start, `setup` / `status` / `search` / `remember`, and a session capture that is off by default.

This page freezes that contract (**version 1**) and documents the library. For tokens, roles and the API itself, see [AGENTS.md](AGENTS.md).

## Where it lives

| Path | What |
|---|---|
| `integrations/shared/python/mimirsynth_agent/` | The library in Python (standard library only, Python 3.8 or later). The source of truth |
| `integrations/shared/typescript/` | Its TypeScript port, for agents that run JavaScript (OpenCode, OpenClaw). No runtime dependencies |
| `integrations/shared/contract/cases.json` | The cases every implementation must pass |
| `integrations/shared/vendor.py` | Copies the Python library into each plugin that carries it |
| `integrations/<agent>/` | Each plugin |

The library lives in `integrations/shared/`, next to the plugins and versioned with the server, because it is not an agent of its own and every plugin depends on it. A Python plugin cannot import it from there: an agent installs a plugin's folder and nothing outside it (Claude Code copies the plugin into its cache). So each Python plugin carries an **exact copy** (for Claude Code, `plugin/scripts/mimirsynth_agent/`), written by `python integrations/shared/vendor.py`, and a test fails if a copy differs. The library in turn carries the server's own secret detector, `api/mimirsynth/secretscan.py`, byte for byte, so a client masks exactly what the server would. A JavaScript plugin imports the TypeScript sources directly or bundles them when it is built.

## The configuration file

`~/.config/mimirsynth/config.json`, on every system (Windows included), or the file named by **`MIMIRSYNTH_CONFIG`**. It holds tokens, so whoever writes it makes it readable only by its owner (`0600`). Example:

```json
{
  "url": "https://mimirsynth.example.com",
  "brain": "team",
  "token": "mst_…",
  "write_token": "mst_…",
  "capture": "off",
  "projects": {
    "/home/me/work/infra": {"brain": "infra", "token": "mst_…", "write_token": "mst_…"}
  }
}
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `url` | string | — | The server, `https://…` (a trailing `/` does not matter) |
| `brain` | string | — | The brain's slug |
| `token` | string | — | An API token for that brain. **Reader** with the Recall scope is enough to recall |
| `write_token` | string | `token` | A **contributor** token, to propose. The capture never sends with a curator token |
| `timeout` | number | `4` | Seconds a call may take before it gives up (more than 0) |
| `max_chars` | integer | `4000` | Most characters the recall before each prompt injects (more than 0) |
| `recall` | boolean | `true` | Recall before each prompt |
| `news` | boolean | `true` | What changed in the brain, at session start |
| `capture` | `off` · `draft` · `send` | `off` | What happens to what a session learned (below) |
| `capture_confidence` | number | `0.3` | The confidence a captured proposal declares (0 to 1) |
| `projects` | object | — | Other values for some folders (below) |

`url`, `brain` and `token` are what an integration needs to work at all; without them it does nothing and says so in `status`. Auth is always a per-brain API token, never the browser session.

### Where a value comes from

The first one that gives it wins:
1. the environment variable **`MIMIRSYNTH_<KEY>`** (`MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_BRAIN`, `MIMIRSYNTH_WRITE_TOKEN`, `MIMIRSYNTH_CAPTURE`…);
2. the entry of `projects` for the working directory;
3. the top level of the file;
4. the default.

An empty value (a variable that is unset or blank, `""` or `null` in the file) counts as not given, so the next one applies. A file that is missing, is not valid JSON or is not an object counts as empty.

### How values are read

A value that cannot be read as its type falls back to the default: a typo never stops an agent.
- **Strings** are trimmed. A number in the file is taken as its digits (`"brain": 42` is the brain `42`).
- **Booleans:** `false`, `off`, `no` and `0` (any case, surrounding spaces ignored) and the number `0` are false; any other word or number is true. Anything else (a list, an object) is the default.
- **Numbers:** a JSON number, or a string with a decimal number (`"2.5"`, `"1e3"` for `timeout`); `max_chars` only takes whole numbers in a string and cuts a fractional JSON number (`2500.9` is `2500`). Out of range, infinite or `true` is the default.
- **`capture`:** `off`, `draft` or `send`, any case. `drafts` is read as `draft` and `auto` as `send`. Anything else is `off`.

### A brain per project: `projects`

`projects` maps a folder to an object with any of the keys above. When the agent works in that folder or below it, its values take the place of the top level ones; the deepest folder wins when several hold the working directory. Folders are absolute (a leading `~` is the home folder), compared without following links and, on Windows, without case. A folder whose name only starts the same does not count (`/work` does not hold `/workshop`). Environment variables still win over it.

Because each token is valid for one brain, an entry that changes `brain` should bring that brain's `token` (and `write_token`): otherwise the top level token is used and the server answers 403. Tokens stay in this one file, readable only by its owner, never in the repository.

### Capture of what a session learned

| `capture` | What happens |
|---|---|
| `off` | The default. Nothing about the sessions is written or sent |
| `draft` | Each session is kept on this machine, already redacted, until the person reviews it (`remember` with no title) |
| `send` | At the **next** session start, each finished session worth it becomes one proposal, in quarantine |

The rules every integration follows:
- **Which sessions:** only those that changed files, or ended with an answer of at least 400 characters; at most **one proposal per session**.
- **What it holds:** the task (the first prompt, up to 500 characters), the outcome (the last answer, up to 3000) and the files changed (the first 20). Never the transcript.
- **The proposal:** `name` «`<Agent>: <project> — <first line of the task>`», `source` `text`, `source_description` «`<agent-id> session`», `origin` `auto` and `confidence` `capture_confidence`.
- **Only with a contributor token:** before sending, the integration asks `whoami`; with any other role it refuses and says so, because a curator's proposal would skip quarantine.
- **Secrets:** everything is redacted before it is written to disk or sent, with the server's own detector (sure and possible findings alike, replaced by `[secret removed]`). It works by patterns and is not infallible.
- **Where the records live:** one JSON file per session, readable only by its owner, in `~/.config/mimirsynth/state/<agent-id>/sessions/` unless the agent gives the plugin a data folder of its own. Records older than 14 days are deleted. Claude Code keeps them in its plugin data folder (`$CLAUDE_PLUGIN_DATA/sessions`), or in `~/.config/mimirsynth/state/sessions/`.

## What every integration does

- **Recall before each prompt** (when `recall` is on and the prompt is not a command): `POST /recall` with the prompt (up to 1500 characters), `facts` 6, `chunks` 3 and `max_chars`, with `token`. The context goes inside `<mimirsynth-memory brain="<slug>">…</mimirsynth-memory>`.
- **What changed at session start** (when `news` is on): `POST /news?limit=20&max_chars=4000`, inside `<mimirsynth-news brain="<slug>">…</mimirsynth-news>` when something was added or is gone.
- **Fail open:** every call has `timeout`; when the server cannot be reached, nothing is injected and the agent carries on. When the server answers 401 or 403 (an expired or revoked token, or a missing scope), the integration says so with the server's message, so it does not stop remembering without anyone noticing.
- **Commands:** `setup` (asks for the tokens hidden, in a terminal, never through the conversation, and writes the file with `0600`), `status` (connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts), `search` (recall with more results) and `remember` (a proposal with `origin` `agent`, redacted, with `write_token`).

The API routes, under `{url}/api/brains/{brain}`, always with `Authorization: Bearer <token>`:

| Route | Token | Answer |
|---|---|---|
| `POST /recall` | `token` (Recall scope) | `{"context": …}` among others |
| `POST /news?limit=&max_chars=` | `token` (Recall scope) | `{"text", "added", "gone"}` |
| `GET /whoami` | any | `{"brain", "name", "role", "version", "token": {"name", "scopes", "expires_at"}}` |
| `POST /proposals` | `write_token` (Propose scope) | `{"id", "status"}`; `pending` with a contributor token |

An error answer carries `{"detail": …}`; the library gives it as a string (JSON when it is not one, as for a 422).

## The library

### Python

```python
import mimirsynth_agent as mimir
from mimirsynth_agent import capture

conf = mimir.Config(cwd=project_folder)          # path=…, env=… for tests
client = mimir.Client(conf)
answer, error = mimir.fail_open(client.recall, prompt)
if answer and answer.get("context"):
    inject(answer["context"])
elif error and error.auth:
    tell_the_person(error.detail)
```

- `Config(path=None, env=None, cwd=None)`: `get(key)`, `source(key)` (`env`, `project`, `file` or `default`), `capture_mode()`, `configured()`, `values()`. Also `config_path()`, `DEFAULTS`, `KEYS`, `CAPTURE_MODES`, `CAPTURE_ALIASES`.
- `Client(conf)`: `recall(query, facts=6, chunks=3, max_chars=None, timeout=None)`, `news(limit=20, max_chars=4000)`, `whoami(token=None)`, `propose(body, token=None)`, `remember(title, content, confidence=None, source_description="", origin="agent")` and `call(method, path, …)`. They raise `ApiError` (`status`, `detail`, `auth`) when the server answers with an error, and anything else when it cannot be reached.
- `fail_open(fn, *args)`: `(answer, None)`, `(None, ApiError)` or `(None, None)`; never raises.
- `redact(text)`: the text with every finding replaced by `[secret removed]`.
- `capture`: `Sessions(folder)` (`load`, `save`, `all`, `drop`), `worth(rec)`, `is_draft(rec)`, `proposal(rec, agent, source, confidence)`, `send(client, store, rec, agent, source)` and `default_dir(agent)`.

### TypeScript

```ts
import { Client, Config, failOpen } from "../../shared/typescript/src/index.ts";

const client = new Client(new Config({ cwd: projectFolder }));
const { value, error } = await failOpen(() => client.recall(prompt));
```

The same API with JavaScript names (`captureMode()`, `failOpen`, `capture.isDraft`, `capture.defaultDir`, options objects such as `recall(query, { maxChars })` and `remember(title, content, { confidence, sourceDescription })`), all calls asynchronous. `Client` takes a second argument, the transport (`fetch` by default), which tests replace. It needs Node 22.6 or later, or Bun, which run the TypeScript sources as they are; the secret detector is a port of the server's, kept equal by the contract cases and by a test that compares the rules.

## Contract tests

- **Cases** (`integrations/shared/contract/cases.json`): how the configuration is read (layers, empty values, types, `projects`, capture aliases), redaction, which sessions are worth proposing, the proposal a session becomes, the exact request of each call, how an error answer is read, and that the capture refuses a curator token. `api/tests/test_agent_client.py` runs them on the Python library and `npm test` on the TypeScript port. An implementation in another language must pass them too.
- **Against a test instance** (`api/tests/test_agent_contract.py`): the `agent_instance` fixture starts a real MimirSynth on a local port with a fresh brain and one token per role (reader, contributor, curator, and a contributor that can only propose). Both libraries then check recall and `whoami`, a 401 and a 403 said, fail open when the server is away, `remember` redacted into quarantine, and the capture refused with a curator token and sent once with a contributor one; with a graph (`MIMIRSYNTH_TEST_FALKOR`), `news` too. The TypeScript checks are `integrations/shared/typescript/test/live.test.ts`, run with `MIMIRSYNTH_CONTRACT_URL`, `_BRAIN`, `_READER`, `_CONTRIBUTOR`, `_CURATOR`, `_PROPOSE_ONLY` and `_NEWS`.
- **In the CI:** the `api` job runs both (it has FalkorDB and Node), and the `agent-client` job type-checks the TypeScript port and runs its cases.

A new plugin:
1. **Python:** add its folder to `TARGETS` in `integrations/shared/vendor.py` and run it; the existing test then keeps its copy equal. Its own end-to-end tests can take the `agent_instance` fixture.
2. **JavaScript:** import `integrations/shared/typescript/src/index.ts` (or bundle it); its end-to-end tests can read the same `MIMIRSYNTH_CONTRACT_*` variables, set by a test in `api/tests` that uses `agent_instance`, as `test_the_typescript_port_against_a_test_instance` does.

## Releasing a plugin change

An agent only updates an installed plugin when the version in its manifest changes (for Claude Code, `version` in `plugin/.claude-plugin/plugin.json`): with the same version, `/plugin update` and the marketplace refresh report it as current and existing installs keep the old scripts. So **any change under a plugin's folder bumps its version**, the vendored copy of this library included (running `vendor.py` after changing the library changes every plugin that carries it). Follow semantic versioning: a fix bumps the patch, a new feature or a new key of the contract the minor version. The `plugin-version` check of every pull request (`scripts/plugin_versions.py`) fails when a plugin's folder changed and its version did not go up; a new plugin adds its folder and manifest to `PLUGINS` there.

## Changing the contract

Version 1 is frozen: integrations rely on it. Adding a key with a default, or a capture alias, is compatible. Renaming or removing a key, or changing a default, the order of the layers or how a value is read, is not: it bumps `CONTRACT_VERSION` in both libraries and in `cases.json`, updates this page in both languages, and every plugin is checked against it.
