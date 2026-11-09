// What the «Connect an agent» panel (issue 362) tells someone to run or paste for each agent, prefilled with the server, the brain and the token.
// Pure functions with no imports, so web/scripts/connect.test.mjs tests them with node and the panel only translates the words around them.
// The commands come from what is merged: integrations/*/README, docs/wiki/Connect-agents.md and docs/AGENT_CLIENT.md (the shared file).

export type AgentId = "claude-code" | "codex" | "opencode" | "hermes" | "openclaw" | "mcp";

/** The agents of the picker, in its order: the five with a native plugin, then any other client that speaks MCP. */
export const AGENTS: AgentId[] = ["claude-code", "codex", "opencode", "hermes", "openclaw", "mcp"];

/** Product names: not translated. */
export const AGENT_NAME: Record<AgentId, string> = {
  "claude-code": "Claude Code", codex: "Codex", opencode: "OpenCode", hermes: "Hermes Agent", openclaw: "OpenClaw", mcp: "MCP",
};

/** What a snippet is filled with. An empty token (one created earlier, whose secret is not shown again) leaves a placeholder. */
export type Conn = { url: string; brain: string; token: string };

/** `config`: the file every plugin shares; `install`: the plugin's one line; `mcp`: a command that adds the brain's MCP server;
 *  `mcp-json`: the server in the `mcpServers` form most MCP clients read; `mcp-raw`: the address and the header, for any other. */
export type BlockKind = "config" | "install" | "mcp" | "mcp-json" | "mcp-raw";
export type Block = { kind: BlockKind; code: string };

export const TOKEN_PLACEHOLDER = "mst_…";
export const CONFIG_PATH = "~/.config/mimirsynth/config.json";

/** The server's address as the agents need it: no trailing slash. */
export function serverUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export function mcpUrl(c: Conn): string {
  return `${serverUrl(c.url)}/api/brains/${encodeURIComponent(c.brain)}/mcp`;
}

const token = (c: Conn) => c.token.trim() || TOKEN_PLACEHOLDER;

/** The shared configuration (docs/AGENT_CLIENT.md): `url`, `brain` and `token` are all an integration needs. One contributor token
 *  recalls and proposes (`write_token` defaults to `token`); the capture stays off until the person turns it on. */
export function configJson(c: Conn): string {
  return JSON.stringify({ url: serverUrl(c.url), brain: c.brain, token: token(c) }, null, 2);
}

/** The blocks of one agent, in the order the panel shows them: first the file (so the setup that comes with some plugins finds every
 *  answer already there), then the plugin's one line, then the brain's MCP server when that agent can add it from the command line. */
export function snippets(agent: AgentId, c: Conn): Block[] {
  const config: Block = { kind: "config", code: configJson(c) };
  const url = mcpUrl(c);
  switch (agent) {
    case "claude-code":
      return [config,
        { kind: "install", code: "claude plugin marketplace add mimirsynth/mimirsynth && claude plugin install mimirsynth@mimirsynth" },
        { kind: "mcp", code: `claude mcp add --transport http mimirsynth "${url}" --header "Authorization: Bearer ${token(c)}"` }];
    case "codex":
      return [config,
        { kind: "install", code: "codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth" },
        { kind: "mcp", code: `codex mcp add mimirsynth --url "${url}" --bearer-token-env-var MIMIRSYNTH_TOKEN` }];
    case "opencode":
      // what `npx -y @mimirsynth/opencode install` runs before its setup; with the file written there is nothing left to ask
      return [config, { kind: "install", code: "opencode plugin @mimirsynth/opencode --global" }];
    case "hermes":
      // `hermes memory setup` also makes MimirSynth the profile's memory provider; it offers the file's values, Enter keeps each one
      return [config, { kind: "install", code: "hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth" }];
    case "openclaw":
      // the setup also grants the conversation access OpenClaw asks for before it runs a plugin's recall hook
      return [config, { kind: "install", code: "openclaw plugins install npm:@mimirsynth/openclaw && openclaw mimirsynth setup" }];
    case "mcp":
      return [
        { kind: "mcp-json", code: JSON.stringify({ mcpServers: { mimirsynth: { type: "http", url, headers: { Authorization: `Bearer ${token(c)}` } } } }, null, 2) },
        { kind: "mcp-raw", code: `${url}\nAuthorization: Bearer ${token(c)}` }];
  }
}

/** Whether a token has been used since the panel started watching it: its first authenticated call, or one after the time the panel saw
 *  last (a token that was already in use before). Dates are the server's, so the browser's clock does not matter. */
export function connectedSince(baseline: string | null | undefined, lastUsed: string | null | undefined): boolean {
  if (!lastUsed) return false;
  if (!baseline) return true;
  return new Date(lastUsed).getTime() > new Date(baseline).getTime();
}
