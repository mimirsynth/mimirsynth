// The plugin's hooks, as OpenCode calls them, against a test instance: api/tests/test_opencode_plugin.py starts it and runs this file
// with MIMIRSYNTH_CONTRACT_URL, _BRAIN, _READER, _CONTRIBUTOR, _CURATOR, _PROPOSE_ONLY (tokens) and _NEWS (1 when the instance has a
// graph), as for the shared library (docs/AGENT_CLIENT.md, «Contract tests»). Without MIMIRSYNTH_CONTRACT_URL every test is skipped.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import type { Json } from "../../shared/typescript/src/index.ts";
import { createHooks } from "../src/plugin.ts";

type Any = any; // eslint-disable-line @typescript-eslint/no-explicit-any
const env = process.env;
const URL_ = env.MIMIRSYNTH_CONTRACT_URL ?? "";
const BRAIN = env.MIMIRSYNTH_CONTRACT_BRAIN ?? "";
const T = {
  reader: env.MIMIRSYNTH_CONTRACT_READER ?? "",
  contributor: env.MIMIRSYNTH_CONTRACT_CONTRIBUTOR ?? "",
  curator: env.MIMIRSYNTH_CONTRACT_CURATOR ?? "",
  proposeOnly: env.MIMIRSYNTH_CONTRACT_PROPOSE_ONLY ?? "",
};
const skip = URL_ ? false : "no test instance (MIMIRSYNTH_CONTRACT_URL)";
const GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8";
const PROMPT = "where does the production database run? (opencode)";

/** The plugin as one OpenCode would load it, with its own configuration file and records folder. */
function opencode(over: Record<string, unknown> = {}, dir = mkdtempSync(join(tmpdir(), "mimirsynth-opencode-live-"))) {
  const data = { url: URL_, brain: BRAIN, token: T.reader, write_token: T.contributor, timeout: 10, ...over };
  writeFileSync(join(dir, "config.json"), JSON.stringify(data));
  const toasts: string[] = [];
  const input: Any = {
    directory: join(dir, "project"),
    worktree: join(dir, "project"),
    client: { tui: { showToast: async ({ body }: Any) => void toasts.push(body.message) }, app: { log: async () => undefined } },
  };
  const opts = { env: {}, configPath: join(dir, "config.json"), stateDir: join(dir, "sessions") };
  return { dir, toasts, state: opts.stateDir, hooks: createHooks(input, {}, opts) as Any, again: () => createHooks(input, {}, opts) as Any };
}

async function prompt(hooks: Any, session: string, text: string): Promise<string> {
  const out: Any = { message: { id: `msg_${session}`, sessionID: session }, parts: [{ id: "prt_000000000001aaaaaaaaaaaaaa", type: "text", text }] };
  await hooks["chat.message"]({ sessionID: session }, out);
  return out.parts.filter((p: Any) => p.synthetic).map((p: Any) => p.text).join("\n");
}

async function turn(hooks: Any, session: string, answer: string, file: string): Promise<void> {
  await hooks["tool.execute.after"]({ tool: "write", sessionID: session, callID: "c1", args: { filePath: file } }, {});
  await hooks.event({ event: { type: "message.updated", properties: { info: { id: `msg_a_${session}`, sessionID: session, role: "assistant" } } } });
  await hooks.event({ event: { type: "message.part.updated", properties: { part: { id: "prt_a", sessionID: session, messageID: `msg_a_${session}`, type: "text", text: answer } } } });
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: session } } });
}

async function asCurator(path: string): Promise<Json> {
  const r = await fetch(`${URL_}/api/brains/${BRAIN}${path}`, { headers: { Authorization: `Bearer ${T.curator}` } });
  return (await r.json()) as Json;
}

const proposals = async () => Number((await asCurator("/proposals")).total);
const tick = () => new Promise((ok) => setTimeout(ok, 50));

async function freePort(): Promise<number> {
  return new Promise((ok) => {
    const s = createServer();
    s.listen(0, "127.0.0.1", () => {
      const port = (s.address() as { port: number }).port;
      s.close(() => ok(port));
    });
  });
}

test("recall is injected before the prompt", { skip }, async () => {
  const { hooks } = opencode({ news: false });
  const ctx = await prompt(hooks, "ses_recall", PROMPT);
  assert.match(ctx, new RegExp(`^<mimirsynth-memory brain="${BRAIN}">\\n`));
  assert.match(ctx, /the contract brain answers: where does the production database/);
});

test("the MCP server the plugin adds answers tools/list with the recall token: read-only tools", { skip }, async () => {
  const { hooks } = opencode();
  const cfg: Any = {};
  await hooks.config(cfg);
  const mcp = cfg.mcp.mimirsynth;
  assert.equal(mcp.url, `${URL_}/api/brains/${BRAIN}/mcp`);
  const r = await fetch(mcp.url, {
    method: "POST",
    headers: { ...mcp.headers, "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
  });
  assert.equal(r.status, 200, await r.clone().text());
  const text = await r.text();
  const body = JSON.parse(text.startsWith("{") ? text : text.split("\n").find((l) => l.startsWith("data:"))!.slice(5));
  const tools = body.result.tools.map((t: Any) => t.name);
  for (const name of ["recall", "facts_about", "timeline", "whats_new"]) assert.ok(tools.includes(name), tools.join(", "));
  assert.ok(!tools.includes("remember"), "read-only: writing goes through mimirsynth_propose_memory, which redacts first and uses the write token");
});

test("the status command says who each token is", { skip }, async () => {
  const { hooks } = opencode();
  const out: Any = { parts: [] };
  await hooks["command.execute.before"]({ command: "mimirsynth-status", sessionID: "ses_status", arguments: "" }, out);
  assert.match(out.parts[0].text, /Recall token: «reader», role reader, scopes recall/);
  assert.match(out.parts[0].text, /Write token: «contributor», role contributor/);
});

test("remember creates a redacted proposal in quarantine", { skip }, async () => {
  const { hooks } = opencode();
  const r = await hooks.tool.mimirsynth_propose_memory.execute({ title: "Deploy key moved (opencode)", content: `It lives in Vaultwarden; the old one ${GITHUB} was revoked.` }, {});
  const id = /Proposal #(\d+): pending/.exec(r)?.[1];
  assert.ok(id, r);
  const p = await asCurator(`/proposals/${id}`);
  assert.equal(p.status, "pending");
  assert.equal(p.origin, "agent");
  assert.equal(p.source_description, "opencode");
  assert.ok(!String(p.body).includes(GITHUB) && String(p.body).includes("[secret removed]"));
});

test("capture is off by default: a whole session writes and sends nothing", { skip }, async () => {
  const one = opencode();
  const before = await proposals();
  await one.hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_off" } } } });
  await prompt(one.hooks, "ses_off", "rotate the deploy key, please");
  await turn(one.hooks, "ses_off", "Done: the key lives in Vaultwarden. ".repeat(20), "ops/deploy.sh");
  await one.hooks.dispose();
  const two = one.again();
  await two.event({ event: { type: "session.created", properties: { info: { id: "ses_off_2" } } } });
  await prompt(two, "ses_off_2", "the next task for today");
  assert.ok(!existsSync(one.state) || readdirSync(one.state).length === 0);
  assert.equal(await proposals(), before);
});

test("capture send proposes a finished session once into quarantine, and never with a curator token", { skip }, async () => {
  const curator = opencode({ capture: "send", news: false, recall: false, write_token: T.curator });
  const before = await proposals();
  await prompt(curator.hooks, "ses_c", "rotate the deploy key, please");
  await turn(curator.hooks, "ses_c", "Done.", "ops/deploy.sh");
  await curator.hooks.dispose();
  await prompt(curator.again(), "ses_c2", "the next task for today");
  await tick();
  assert.equal(await proposals(), before);
  assert.ok(curator.toasts.some((t) => t.includes("contributor")), curator.toasts.join("|"));

  const one = opencode({ capture: "send", news: false, recall: false });
  await prompt(one.hooks, "ses_s", `rotate the deploy key, the old one was ${GITHUB}`);
  await turn(one.hooks, "ses_s", "Done: the key lives in Vaultwarden.", "ops/deploy.sh");
  await one.hooks.dispose();
  assert.equal(await proposals(), before, "nothing leaves the machine before the next session start");
  await prompt(one.again(), "ses_s2", "the next task for today");
  await prompt(one.again(), "ses_s3", "and the one after that");
  assert.equal(await proposals(), before + 1);
  const list = (await asCurator("/proposals")).items as Json[];
  const mine = list.find((p) => String(p.source_description) === "opencode session")!;
  const p = await asCurator(`/proposals/${mine.id}`);
  assert.equal(p.status, "pending");
  assert.equal(p.origin, "auto");
  assert.equal(p.confidence, 0.3);
  assert.ok(String(p.body).includes("ops/deploy.sh") && !String(p.body).includes(GITHUB));
});

test("an invalid token is said, and a server that is away never stops the prompt", { skip }, async () => {
  const bad = opencode({ token: T.proposeOnly, news: false });
  assert.equal(await prompt(bad.hooks, "ses_bad", PROMPT), "");
  await tick();
  assert.ok(bad.toasts.some((t) => t.startsWith("MimirSynth could not recall:")), bad.toasts.join("|"));
  const away = opencode({ url: `http://127.0.0.1:${await freePort()}`, timeout: 2 });
  const started = Date.now();
  await away.hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_away" } } } });
  assert.equal(await prompt(away.hooks, "ses_away", PROMPT), "");
  assert.ok(Date.now() - started < 5000);
  await tick();
  assert.deepEqual(away.toasts, []);
});

test("what changed at session start", { skip: skip || (env.MIMIRSYNTH_CONTRACT_NEWS === "1" ? false : "the instance has no graph") }, async () => {
  const { hooks, toasts } = opencode({ recall: false });
  await hooks.event({ event: { type: "session.created", properties: { info: { id: "ses_news" } } } });
  assert.equal(await prompt(hooks, "ses_news", PROMPT), "", "a fresh brain has nothing new");
  await tick();
  assert.deepEqual(toasts, []);
});
