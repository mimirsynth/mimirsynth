// The «Connect an agent» panel (#362): what each agent is told to run or paste, prefilled with the server, the brain and the token, and
// when the panel says an agent is connected.
//   node --experimental-strip-types --test scripts/
import assert from "node:assert/strict";
import test from "node:test";
import { AGENTS, AGENT_NAME, CONFIG_PATH, configJson, connectedSince, mcpUrl, serverUrl, snippets, TOKEN_PLACEHOLDER } from "../src/pages/connectSnippets.ts";

const C = { url: "https://mimir.example.com/", brain: "team-ops", token: "mst_AbC-123_xyz" };
const MCP = "https://mimir.example.com/api/brains/team-ops/mcp";
const kinds = (a, c = C) => snippets(a, c).map((b) => b.kind);
const block = (a, kind, c = C) => snippets(a, c).find((b) => b.kind === kind)?.code;

test("the picker lists the five native plugins and then any MCP client", () => {
  assert.deepEqual(AGENTS, ["claude-code", "codex", "opencode", "hermes", "openclaw", "mcp"]);
  assert.deepEqual(AGENTS.map((a) => AGENT_NAME[a]), ["Claude Code", "Codex", "OpenCode", "Hermes Agent", "OpenClaw", "MCP"]);
});

test("the address has no trailing slash and the MCP endpoint is the brain's", () => {
  assert.equal(serverUrl(" https://x.test/// "), "https://x.test");
  assert.equal(mcpUrl(C), MCP);
  assert.equal(CONFIG_PATH, "~/.config/mimirsynth/config.json");
});

test("every native plugin gets the shared file first, prefilled, then its one-line install", () => {
  for (const a of ["claude-code", "codex", "opencode", "hermes", "openclaw"]) {
    const [first, second] = snippets(a, C);
    assert.equal(first.kind, "config", a);
    assert.deepEqual(JSON.parse(first.code), { url: "https://mimir.example.com", brain: "team-ops", token: "mst_AbC-123_xyz" }, a);
    assert.equal(second.kind, "install", a);
    assert.ok(!second.code.includes("\n"), `${a}: one line`);
    assert.ok(!second.code.includes("mst_"), `${a}: the token never goes in a command that stays in the shell history`);
  }
});

test("each plugin's install is the one its README and the wiki give", () => {
  assert.equal(block("claude-code", "install"), "claude plugin marketplace add mimirsynth/mimirsynth && claude plugin install mimirsynth@mimirsynth");
  assert.equal(block("codex", "install"), "codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth");
  assert.equal(block("opencode", "install"), "opencode plugin @mimirsynth/opencode --global");
  assert.equal(block("hermes", "install"), "hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth");
  assert.equal(block("openclaw", "install"), "openclaw plugins install @mimirsynth/openclaw && openclaw mimirsynth setup");
});

test("Claude Code and Codex can also add the brain's MCP server from the command line", () => {
  assert.deepEqual(kinds("claude-code"), ["config", "install", "mcp"]);
  assert.equal(block("claude-code", "mcp"), `claude mcp add --transport http mimirsynth "${MCP}" --header "Authorization: Bearer mst_AbC-123_xyz"`);
  assert.deepEqual(kinds("codex"), ["config", "install", "mcp"]);
  assert.equal(block("codex", "mcp"), `codex mcp add mimirsynth --url "${MCP}" --bearer-token-env-var MIMIRSYNTH_TOKEN`);
  for (const a of ["opencode", "hermes", "openclaw"]) assert.deepEqual(kinds(a), ["config", "install"], a);
});

test("another MCP client gets the mcpServers entry and the bare address and header", () => {
  assert.deepEqual(kinds("mcp"), ["mcp-json", "mcp-raw"]);
  assert.deepEqual(JSON.parse(block("mcp", "mcp-json")),
    { mcpServers: { mimirsynth: { type: "http", url: MCP, headers: { Authorization: "Bearer mst_AbC-123_xyz" } } } });
  assert.equal(block("mcp", "mcp-raw"), `${MCP}\nAuthorization: Bearer mst_AbC-123_xyz`);
});

test("without the secret (a token made before) every snippet carries a placeholder, never an empty token", () => {
  const old = { ...C, token: "  " };
  for (const a of AGENTS) {
    for (const b of snippets(a, old)) assert.ok(!/Bearer "|Bearer $|"token": ""/m.test(b.code), `${a} ${b.kind}`);
  }
  assert.equal(JSON.parse(block("opencode", "config", old)).token, TOKEN_PLACEHOLDER);
  assert.ok(block("claude-code", "mcp", old).endsWith(`Bearer ${TOKEN_PLACEHOLDER}"`));
  assert.ok(block("mcp", "mcp-raw", old).endsWith(`Bearer ${TOKEN_PLACEHOLDER}`));
  assert.equal(configJson(old), JSON.stringify({ url: "https://mimir.example.com", brain: "team-ops", token: TOKEN_PLACEHOLDER }, null, 2));
});

test("a brain slug is escaped in the MCP address", () => {
  assert.equal(mcpUrl({ ...C, brain: "a b" }), "https://mimir.example.com/api/brains/a%20b/mcp");
});

test("connected: the first call of a new token, or a call after the one the panel saw first", () => {
  assert.equal(connectedSince(null, null), false);                       // a new token, not used yet
  assert.equal(connectedSince(null, "2026-11-08T10:00:00Z"), true);       // its first authenticated call
  assert.equal(connectedSince("2026-11-08T10:00:00Z", "2026-11-08T10:00:00Z"), false);  // an old token, nothing new
  assert.equal(connectedSince("2026-11-08T10:00:00Z", "2026-11-08T10:00:01.5+00:00"), true);
  assert.equal(connectedSince("2026-11-08T11:00:00+01:00", "2026-11-08T10:00:00Z"), false);  // the same instant in another zone
});
