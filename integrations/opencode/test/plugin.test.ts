// The plugin's hooks as OpenCode calls them, against a fake MimirSynth (a transport that answers by route) or, for the timeouts, a real
// local server that never answers. Nothing here needs OpenCode or a MimirSynth instance; test/live.test.ts drives the same hooks
// against a real one.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import type { Transport, WireRequest } from "../../shared/typescript/src/index.ts";
import { IDLE_END, Mimir, otherMemory, patchedFiles } from "../src/core.ts";
import plugin from "../src/index.ts";
import { COMMANDS, createHooks, partId } from "../src/plugin.ts";

type Any = any; // eslint-disable-line @typescript-eslint/no-explicit-any
const GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8";
const PROMPT = "where does the production database run?";

interface Fake {
  calls: WireRequest[];
  transport: Transport;
}

/** A MimirSynth that answers by "METHOD /path" (without the /api/brains/<slug> prefix and the query). */
function fake(routes: Record<string, (req: WireRequest) => { status?: number; body?: unknown }> = {}): Fake {
  const calls: WireRequest[] = [];
  const defaults: typeof routes = {
    "POST /recall": (req) => ({ body: { context: `## Facts\n- the brain answers: ${JSON.parse(req.body ?? "{}").query}` } }),
    "POST /news": () => ({ body: { text: "## Learned\n- the database moved to db-02", added: 1, gone: 0 } }),
    "GET /whoami": (req) => ({
      body: { brain: "team", name: "Team", role: req.headers.Authorization === "Bearer mst_curator" ? "curator" : req.headers.Authorization === "Bearer mst_writer" ? "contributor" : "reader", version: "1.2.3", token: { name: "laptop", scopes: ["recall"], expires_at: null } },
    }),
    "POST /proposals": () => ({ body: { id: 7, status: "pending" } }),
  };
  const all = { ...defaults, ...routes };
  return {
    calls,
    transport: async (req) => {
      calls.push(req);
      const path = new URL(req.url).pathname.replace(/^\/api\/brains\/[^/]+/, "");
      const h = all[`${req.method} ${path}`];
      if (!h) return { status: 404, reason: "Not Found", body: '{"detail":"no such route"}' };
      const r = h(req);
      return { status: r.status ?? 200, reason: "", body: JSON.stringify(r.body ?? {}) };
    },
  };
}

function setup(conf: Record<string, unknown> = {}, routes: Parameters<typeof fake>[0] = {}, extra: Any = {}) {
  const dir = mkdtempSync(join(tmpdir(), "mimirsynth-opencode-"));
  const path = join(dir, "config.json");
  writeFileSync(path, JSON.stringify({ url: "https://mimir.example", brain: "team", token: "mst_reader", write_token: "mst_writer", ...conf }));
  const f = fake(routes);
  const toasts: string[] = [];
  const input: Any = {
    directory: join(dir, "project"),
    worktree: join(dir, "project"),
    client: { tui: { showToast: async ({ body }: Any) => void toasts.push(body.message) }, app: { log: async () => undefined } },
  };
  const opts = { env: {}, configPath: path, transport: f.transport, stateDir: join(dir, "sessions"), ...extra };
  const hooks: Any = createHooks(input, extra.options ?? {}, opts);
  return { dir, path, f, toasts, input, hooks, opts, state: join(dir, "sessions") };
}

function message(session = "ses_1", text = PROMPT): Any {
  return {
    message: { id: "msg_1", sessionID: session, role: "user" },
    parts: [{ id: "prt_000000000001aaaaaaaaaaaaaa", sessionID: session, messageID: "msg_1", type: "text", text }],
  };
}

async function prompt(hooks: Any, session = "ses_1", text = PROMPT): Promise<Any> {
  const out = message(session, text);
  await hooks["chat.message"]({ sessionID: session }, out);
  return out;
}

function injected(out: Any): string {
  return out.parts.filter((p: Any) => p.synthetic).map((p: Any) => p.text).join("\n");
}

async function turn(hooks: Any, session: string, answer: string, edits: string[] = []): Promise<void> {
  for (const f of edits) await hooks["tool.execute.after"]({ tool: "edit", sessionID: session, callID: "c", args: { filePath: f } }, {});
  await hooks.event({ event: { type: "message.updated", properties: { info: { id: `msg_a_${session}`, sessionID: session, role: "assistant" } } } });
  await hooks.event({ event: { type: "message.part.updated", properties: { part: { id: "prt_a", sessionID: session, messageID: `msg_a_${session}`, type: "text", text: answer } } } });
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: session } } });
}

const tick = () => new Promise((ok) => setTimeout(ok, 20));

test("the package's entry point is an OpenCode plugin module", () => {
  assert.equal(plugin.id, "mimirsynth");
  assert.equal(typeof plugin.server, "function");
});

test("config adds the four commands and the brain's MCP server, without replacing what the person has", async () => {
  const { hooks } = setup();
  const cfg: Any = { command: { "mimirsynth-search": { template: "mine" } }, mcp: {}, plugin: ["opencode-supermemory", "@mimirsynth/opencode"] };
  await hooks.config(cfg);
  assert.deepEqual(Object.keys(cfg.command).sort(), Object.keys(COMMANDS).sort());
  assert.equal(cfg.command["mimirsynth-search"].template, "mine");
  assert.deepEqual(cfg.mcp.mimirsynth, {
    type: "remote", url: "https://mimir.example/api/brains/team/mcp", headers: { Authorization: "Bearer mst_reader" }, oauth: false, enabled: true, timeout: 5000,
  });
  const mine: Any = { mcp: { mimirsynth: { type: "remote", url: "https://elsewhere/mcp" } } };
  await hooks.config(mine);
  assert.equal(mine.mcp.mimirsynth.url, "https://elsewhere/mcp");
});

test("config can leave out the MCP server and the commands, and adds no server while MimirSynth is not configured", async () => {
  const off = setup({}, {}, { options: { mcp: false, commands: false } });
  const cfg: Any = {};
  await off.hooks.config(cfg);
  assert.equal(cfg.mcp, undefined);
  assert.equal(cfg.command, undefined);
  const bare = setup({ url: "", token: "" });
  const cfg2: Any = {};
  await bare.hooks.config(cfg2);
  assert.equal(cfg2.mcp, undefined);
  assert.ok(cfg2.command["mimirsynth-setup"]);
});

test("recall before a prompt is added as a synthetic part, with the prompt redacted", async () => {
  const { hooks, f } = setup();
  const out = await prompt(hooks, "ses_1", `${PROMPT} the token is ${GITHUB}`);
  const recall = f.calls.find((c) => c.url.endsWith("/recall"))!;
  const body = JSON.parse(recall.body!);
  assert.equal(recall.headers.Authorization, "Bearer mst_reader");
  assert.ok(!body.query.includes(GITHUB) && body.query.includes("[secret removed]"));
  assert.deepEqual([body.facts, body.chunks, body.max_chars], [6, 3, 4000]);
  const part = out.parts.at(-1);
  assert.equal(part.synthetic, true);
  assert.equal(part.type, "text");
  assert.equal(part.messageID, "msg_1");
  assert.equal(part.sessionID, "ses_1");
  assert.ok(part.id > out.parts[0].id, "the part sorts after the prompt");
  assert.match(part.text, /<mimirsynth-memory brain="team">\n## Facts\n- the brain answers: where does/);
  assert.match(part.text, /<\/mimirsynth-memory>/);
});

test("no recall for a short prompt, with recall off, or before the plugin is configured", async () => {
  for (const [conf, text] of [[{}, "go on"], [{ recall: "off" }, PROMPT], [{ token: "" }, PROMPT]] as const) {
    const { hooks, f } = setup({ news: false, ...conf });
    const out = await prompt(hooks, "ses_1", text);
    assert.equal(f.calls.filter((c) => c.url.includes("/recall")).length, 0);
    assert.equal(injected(out), "");
  }
});

test("what changed at session start comes with the first message, once", async () => {
  const { hooks, f } = setup({ recall: false });
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_1" } } } });
  const first = await prompt(hooks);
  assert.match(injected(first), /<mimirsynth-news brain="team">\n## Learned\n- the database moved to db-02\n<\/mimirsynth-news>/);
  const news = f.calls.find((c) => c.url.includes("/news"))!;
  assert.ok(news.url.endsWith("/api/brains/team/news?limit=20&max_chars=4000"));
  assert.equal(injected(await prompt(hooks)), "");
  assert.equal(f.calls.filter((c) => c.url.includes("/news")).length, 1);
});

test("nothing for subagent sessions, and no news when nothing changed", async () => {
  const { hooks, f } = setup({}, { "POST /news": () => ({ body: { text: "nothing", added: 0, gone: 0 } }) });
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_child", parentID: "ses_1" } } } });
  assert.equal(injected(await prompt(hooks, "ses_child")), "");
  assert.equal(f.calls.length, 0);
  const out = await prompt(hooks, "ses_1");
  assert.ok(!injected(out).includes("mimirsynth-news"));
});

test("an invalid token is said to the person, never to the model; a server that is away is not", async () => {
  const { hooks, toasts } = setup({}, { "POST /recall": () => ({ status: 401, body: { detail: "this token was revoked" } }), "POST /news": () => ({ status: 401, body: { detail: "this token was revoked" } }) });
  const out = await prompt(hooks);
  await tick();
  assert.equal(injected(out), "");
  assert.ok(toasts.includes("MimirSynth could not recall: this token was revoked"), toasts.join("|"));
  assert.ok(toasts.includes("MimirSynth: this token was revoked"));
  const away = setup({}, {}, { transport: async () => { throw new TypeError("fetch failed"); } });
  const out2 = await prompt(away.hooks);
  await tick();
  assert.equal(injected(out2), "");
  assert.deepEqual(away.toasts, []);
});

async function silentServer(): Promise<{ url: string; server: Server }> {
  const server = createServer(() => undefined); // accepts and never answers
  await new Promise<void>((ok) => server.listen(0, "127.0.0.1", ok));
  return { url: `http://127.0.0.1:${(server.address() as Any).port}`, server };
}

test("a server that never answers costs at most the timeout, and the prompt goes on", async () => {
  const { url, server } = await silentServer();
  try {
    const { hooks } = setup({ url, timeout: 1 }, {}, { transport: undefined });
    const started = Date.now();
    await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_1" } } } });
    const out = await prompt(hooks);
    const took = Date.now() - started;
    assert.equal(injected(out), "");
    assert.ok(took < 3500, `took ${took} ms`);
  } finally {
    server.close();
  }
});

test("with capture off nothing about the session is written or sent", async () => {
  const { hooks, f, state } = setup();
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_1" } } } });
  await prompt(hooks, "ses_1", `rotate the deploy key ${GITHUB}`);
  await turn(hooks, "ses_1", "Done: the key lives in Vaultwarden. ".repeat(20), ["ops/deploy.sh"]);
  await hooks.dispose();
  assert.ok(!existsSync(state) || readdirSync(state).length === 0);
  assert.equal(f.calls.filter((c) => c.url.includes("/proposals") || c.url.includes("/whoami")).length, 0);
});

test("capture send: a finished session becomes one redacted proposal in quarantine at the next session start", async () => {
  const one = setup({ capture: "send", news: false, recall: false });
  await one.hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_1" } } } });
  await prompt(one.hooks, "ses_1", `rotate the deploy key, the old one is ${GITHUB}`);
  await turn(one.hooks, "ses_1", "Done: the key lives in Vaultwarden.", [join(one.input.directory, "ops", "deploy.sh")]);
  const rec = JSON.parse(readFileSync(join(one.state, "ses_1.json"), "utf8"));
  assert.ok(!rec.first_prompt.includes(GITHUB) && rec.first_prompt.includes("[secret removed]"));
  assert.deepEqual(rec.files, ["ops/deploy.sh"]);
  assert.equal(rec.turns, 1);
  assert.equal(rec.ended, false);
  assert.equal(one.f.calls.length, 0, "nothing leaves the machine during the session");
  await one.hooks.dispose();
  assert.equal(JSON.parse(readFileSync(join(one.state, "ses_1.json"), "utf8")).ended, true);

  const two: Any = createHooks(one.input, {}, one.opts); // the next OpenCode
  await two.event({ event: { type: "session.created", properties: { info: { id: "ses_2" } } } });
  await prompt(two, "ses_2", "next task: check the backups");
  const calls = one.f.calls.map((c) => `${c.method} ${new URL(c.url).pathname}`);
  assert.deepEqual(calls, ["GET /api/brains/team/whoami", "POST /api/brains/team/proposals"]);
  const sent = JSON.parse(one.f.calls[1].body!);
  assert.equal(one.f.calls[1].headers.Authorization, "Bearer mst_writer");
  assert.equal(sent.origin, "auto");
  assert.equal(sent.confidence, 0.3);
  assert.equal(sent.source_description, "opencode session");
  assert.match(sent.name, /^OpenCode: project — rotate the deploy key/);
  assert.ok(sent.body.includes("ops/deploy.sh") && !sent.body.includes(GITHUB));
  assert.equal(JSON.parse(readFileSync(join(one.state, "ses_1.json"), "utf8")).sent.id, 7);
  const three: Any = createHooks(one.input, {}, one.opts);
  await three.event({ event: { type: "session.created", properties: { info: { id: "ses_3" } } } });
  await prompt(three, "ses_3", "and another task, a third one");
  assert.equal(one.f.calls.filter((c) => c.url.includes("/proposals")).length, 1, "at most one proposal per session");
});

test("what a subagent changed is recorded in the session that started it", async () => {
  const { hooks, state } = setup({ capture: "draft", news: false, recall: false });
  await prompt(hooks, "ses_1", "refactor the deploy scripts please");
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_sub", parentID: "ses_1" } } } });
  await hooks["tool.execute.after"]({ tool: "apply_patch", sessionID: "ses_sub", callID: "c", args: { patchText: "*** Begin Patch\n*** Update File: ops/deploy.sh\n*** End Patch" } }, {});
  assert.deepEqual(readdirSync(state), ["ses_1.json"]);
  assert.deepEqual(JSON.parse(readFileSync(join(state, "ses_1.json"), "utf8")).files, ["ops/deploy.sh"]);
});

test("a session left idle for long counts as finished even if OpenCode never said so", async () => {
  let now = 1_800_000_000;
  const one = setup({ capture: "send", news: false, recall: false }, {}, { now: () => now });
  await prompt(one.hooks, "ses_1", "rotate the deploy key please");
  await turn(one.hooks, "ses_1", "Done.", ["ops/deploy.sh"]);
  const two: Any = createHooks(one.input, {}, one.opts);
  await prompt(two, "ses_2", "another task in another window");
  assert.equal(one.f.calls.filter((c) => c.url.includes("/proposals")).length, 0, "still going");
  now += IDLE_END + 1;
  const three: Any = createHooks(one.input, {}, one.opts);
  await prompt(three, "ses_3", "a third task some time later");
  assert.equal(one.f.calls.filter((c) => c.url.includes("/proposals")).length, 1);
});

test("the capture never sends with a curator token, and says why", async () => {
  const one = setup({ capture: "send", news: false, recall: false, write_token: "mst_curator" });
  await prompt(one.hooks, "ses_1", "rotate the deploy key please");
  await turn(one.hooks, "ses_1", "Done.", ["ops/deploy.sh"]);
  await one.hooks.dispose();
  const two: Any = createHooks(one.input, {}, one.opts);
  await prompt(two, "ses_2", "the next task for today");
  await tick();
  assert.equal(one.f.calls.filter((c) => c.url.includes("/proposals")).length, 0);
  assert.ok(one.toasts.some((t) => t.includes("only sends with a contributor token")), one.toasts.join("|"));
});

test("capture draft: sessions wait on this machine, /mimirsynth-remember lists them and the tools send or forget them", async () => {
  const one = setup({ capture: "draft", news: false, recall: false });
  await prompt(one.hooks, "ses_1", "rotate the deploy key please");
  await turn(one.hooks, "ses_1", "Done: the key lives in Vaultwarden.", ["ops/deploy.sh"]);
  await one.hooks.dispose();
  const two: Any = createHooks(one.input, {}, one.opts);
  await prompt(two, "ses_2", "the next task for today");
  await tick();
  assert.ok(one.toasts.some((t) => t.includes("1 session draft(s) waiting")));
  assert.equal(one.f.calls.filter((c) => c.url.includes("/proposals")).length, 0);
  const out: Any = { parts: [{ type: "text", text: "template" }] };
  await two["command.execute.before"]({ command: "mimirsynth-remember", sessionID: "ses_2", arguments: "" }, out);
  assert.match(out.parts[1].text, /=== ses_1 · .*\nOpenCode: project — rotate the deploy key please/);
  assert.equal(await two.tool.mimirsynth_send_draft.execute({ session: "nope" }, {}), "No such draft.");
  assert.equal(await two.tool.mimirsynth_send_draft.execute({ session: "ses_1" }, {}), "Proposal #7: pending");
  const out2: Any = { parts: [] };
  await two["command.execute.before"]({ command: "mimirsynth-remember", sessionID: "ses_2", arguments: "" }, out2);
  assert.match(out2.parts[0].text, /No drafts waiting/);
});

test("the commands run inside OpenCode and add their output; the message they expand to gets no recall", async () => {
  const { hooks, f } = setup({ news: false });
  const status: Any = { parts: [{ type: "text", text: COMMANDS["mimirsynth-status"].template }] };
  await hooks["command.execute.before"]({ command: "mimirsynth-status", sessionID: "ses_1", arguments: "" }, status);
  assert.match(status.parts[1].text, /Server: https:\/\/mimir.example · brain: team\nRecall token: «laptop», role reader, scopes recall, does not expire/);
  assert.match(status.parts[1].text, /Capture of what each session learned: off \(nothing about the sessions is written or sent\)/);
  const out = await prompt(hooks, "ses_1", status.parts.map((p: Any) => p.text).join("\n"));
  assert.ok(!injected(out).includes("mimirsynth-memory"));
  assert.equal(f.calls.filter((c) => c.url.includes("/recall")).length, 0);

  const search: Any = { parts: [] };
  await hooks["command.execute.before"]({ command: "mimirsynth-search", sessionID: "ses_1", arguments: "the database" }, search);
  const body = JSON.parse(f.calls.find((c) => c.url.includes("/recall"))!.body!);
  assert.deepEqual([body.query, body.facts, body.chunks, body.max_chars], ["the database", 12, 6, 12000]);
  assert.match(search.parts[0].text, /the brain answers: the database/);
  await prompt(hooks, "ses_1", "the message the command expands to");

  const setupOut: Any = { parts: [] };
  await hooks["command.execute.before"]({ command: "mimirsynth-setup", sessionID: "ses_1", arguments: "" }, setupOut);
  assert.match(setupOut.parts[0].text, /npx -y @mimirsynth\/opencode setup/);
  assert.ok(!setupOut.parts[0].text.includes("mst_reader"), "a token never goes into the conversation");
  await prompt(hooks, "ses_1", "the message the command expands to");

  const other: Any = { parts: [] };
  await hooks["command.execute.before"]({ command: "review", sessionID: "ses_1", arguments: "" }, other);
  assert.deepEqual(other.parts, []);
  assert.equal(f.calls.filter((c) => c.url.includes("/recall")).length, 1, "only the search recalled");
  assert.ok(injected(await prompt(hooks)).includes("mimirsynth-memory"), "the next prompt has recall again");
});

test("mimirsynth_propose_memory proposes the memory redacted, with the write token", async () => {
  const { hooks, f } = setup();
  const r = await hooks.tool.mimirsynth_propose_memory.execute({ title: "Deploy key moved", content: `It lives in Vaultwarden; the old one ${GITHUB} was revoked.`, confidence: 0.8 }, {});
  assert.equal(r, "Proposal #7: pending (waiting for a curator)");
  const call = f.calls.find((c) => c.url.includes("/proposals"))!;
  const body = JSON.parse(call.body!);
  assert.equal(call.headers.Authorization, "Bearer mst_writer");
  assert.ok(!body.body.includes(GITHUB) && body.body.includes("[secret removed]"));
  assert.deepEqual([body.origin, body.source, body.source_description, body.confidence], ["agent", "text", "opencode", 0.8]);
  const refused = setup({}, { "POST /proposals": () => ({ status: 403, body: { detail: "this token can only read" } }) });
  assert.equal(await refused.hooks.tool.mimirsynth_propose_memory.execute({ title: "t", content: "c" }, {}), "MimirSynth answered 403: this token can only read");
});

test("the files an edit touched: edit, write and apply_patch, inside the project relative to it", () => {
  assert.deepEqual(patchedFiles("*** Begin Patch\n*** Update File: src/a.ts\n@@\n*** Add File: b.md\n*** Delete File: c.txt\n*** End Patch"), ["src/a.ts", "b.md", "c.txt"]);
  const dir = mkdtempSync(join(tmpdir(), "mimirsynth-opencode-"));
  writeFileSync(join(dir, "c.json"), JSON.stringify({ url: "u", brain: "b", token: "t", capture: "draft" }));
  const m = new Mimir({ env: {}, configPath: join(dir, "c.json"), stateDir: join(dir, "s") });
  m.recordFile("s1", join(dir, "proj", "src", "a.ts"), join(dir, "proj"));
  m.recordFile("s1", "src/a.ts", join(dir, "proj"));
  m.recordFile("s1", join(dir, "elsewhere", "x.ts"), join(dir, "proj"));
  assert.deepEqual(m.store().load("s1").files, ["src/a.ts", "x.ts"]);
});

test("other memory plugins and MCP servers are noticed, MimirSynth's own are not", () => {
  assert.deepEqual(otherMemory({ plugin: ["opencode-supermemory", ["opencode-mem0", {}], "@mimirsynth/opencode", "opencode-wakatime"], mcp: { graphiti: {}, cognee: { enabled: false }, mimirsynth: {} } }), [
    "MCP graphiti", "opencode-mem0", "opencode-supermemory",
  ]);
});

test("part ids look like OpenCode's and keep their order", () => {
  const ids = Array.from({ length: 50 }, () => partId());
  for (const id of ids) assert.match(id, /^prt_[0-9a-f]{12}[0-9A-Za-z]{14}$/);
  assert.deepEqual([...ids].sort(), ids);
});
