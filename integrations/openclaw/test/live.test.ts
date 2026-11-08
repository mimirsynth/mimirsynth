// The plugin's hooks, tools and commands against a real MimirSynth: api/tests/test_openclaw_plugin.py starts a test instance and runs
// this file with MIMIRSYNTH_CONTRACT_URL, _BRAIN, _READER, _CONTRIBUTOR, _CURATOR, _PROPOSE_ONLY (tokens) and _NEWS (1 when the instance
// has a graph); a disposable stack works the same way. Without MIMIRSYNTH_CONTRACT_URL every test is skipped.
import assert from "node:assert/strict";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { MARKER, type Json } from "../../shared/typescript/src/index.ts";
import { register, type PluginApi } from "../src/index.ts";

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
const QUESTION = "where does the production database run? (openclaw)";

type Handler = (event: any, ctx: any) => any;

/** The plugin registered on a stand-in for OpenClaw's API, with its own configuration file and records folder. */
function plugin(over: Record<string, unknown> = {}) {
  const dir = mkdtempSync(join(tmpdir(), "mimirsynth-openclaw-live-"));
  const path = join(dir, "config.json");
  writeFileSync(path, JSON.stringify({ url: URL_, brain: BRAIN, token: T.reader, write_token: T.contributor, timeout: 10, ...over }));
  const hooks = new Map<string, { handler: Handler; opts?: Record<string, unknown> }[]>();
  const tools: ((ctx: any) => any)[] = [];
  const commands: Record<string, any>[] = [];
  const logs: string[] = [];
  const api: PluginApi = {
    pluginConfig: {},
    config: { plugins: { entries: { mimirsynth: { hooks: { allowConversationAccess: true } } } } },
    logger: { info: (m) => logs.push(m), warn: (m) => logs.push(m), debug: (m) => logs.push(m) },
    on: (name, handler, opts) => hooks.set(name, [...(hooks.get(name) ?? []), { handler, opts }]),
    registerTool: (t) => tools.push(t),
    registerCommand: (c) => commands.push(c),
    registerCli: () => undefined,
  };
  register(api, { env: {}, path, stateDir: join(dir, "sessions") });
  const on = (name: string): Handler => {
    const all = hooks.get(name) ?? [];
    return (name === "before_prompt_build" ? all.find((h) => h.opts?.requiresToolAuthority) : all[0])!.handler;
  };
  return { on, tools, commands, logs, stateDir: join(dir, "sessions") };
}

const turn = (over: Record<string, unknown> = {}) => ({
  sessionId: "live-1",
  sessionKey: "agent:main:main",
  workspaceDir: join(tmpdir(), "infra"),
  toolAuthority: { allows: (t: string) => t === "mimirsynth_search", assertActive: () => undefined },
  ...over,
});

async function asCurator(path: string): Promise<Json> {
  const r = await fetch(`${URL_}/api/brains/${BRAIN}${path}`, { headers: { Authorization: `Bearer ${T.curator}` } });
  return (await r.json()) as Json;
}

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
  const p = plugin();
  const r = await p.on("before_prompt_build")({ prompt: QUESTION, currentUserMessage: QUESTION }, turn());
  assert.ok(r?.prependContext, "nothing injected");
  assert.ok(r.prependContext.startsWith(`<mimirsynth-memory brain="${BRAIN}">\n`), r.prependContext);
  assert.match(r.prependContext, /production database/i);
  assert.ok(r.prependContext.endsWith("</mimirsynth-memory>"));
});

test("a token that cannot recall is said, and nothing breaks when the server is away", { skip }, async () => {
  let r = await plugin({ token: T.proposeOnly }).on("before_prompt_build")({ currentUserMessage: QUESTION }, turn());
  assert.match(r.prependContext, /^<mimirsynth-notice>MimirSynth could not recall: .+/);
  r = await plugin({ token: "mst_" + "not-a-real-token" }).on("before_prompt_build")({ currentUserMessage: QUESTION }, turn());
  assert.match(r.prependContext, /<mimirsynth-notice>/);
  const away = plugin({ url: `http://127.0.0.1:${await freePort()}`, timeout: 2 });
  const started = Date.now();
  assert.equal(await away.on("before_prompt_build")({ currentUserMessage: QUESTION }, turn()), undefined);
  assert.ok(Date.now() - started < 5000);
  const [search] = away.tools.map((t) => t({ sessionKey: "agent:main:main" }));
  assert.match((await search.execute("1", { query: QUESTION })).content[0].text, /^Cannot reach MimirSynth/);
});

test("the search tool and the status", { skip }, async () => {
  const p = plugin();
  const [search] = p.tools.map((t) => t({ sessionKey: "agent:main:main" }));
  assert.match((await search.execute("1", { query: QUESTION })).content[0].text, /production database/i);
  const st = (await p.commands[0].handler({ args: "status" })).text as string;
  assert.match(st, /Recall token: «reader», role reader, scopes recall/);
  assert.match(st, /Write token: «contributor», role contributor/);
  assert.match(st, /Capture of what each session learned: off/);
});

test("remember creates a proposal in quarantine, redacted", { skip }, async () => {
  const p = plugin();
  const [, remember] = p.tools.map((t) => t({ sessionKey: "agent:main:main" }));
  const before = Number((await asCurator("/proposals")).total);
  const r = await remember.execute("1", { title: "Deploy key moved (openclaw)", content: `The deploy key now lives in Vaultwarden; the old one ${GITHUB} was revoked.` });
  assert.equal(r.details.status, "pending");
  assert.match(r.content[0].text, /waiting for a curator/);
  assert.equal(Number((await asCurator("/proposals")).total), before + 1);
  const prop = await asCurator(`/proposals/${String(r.details.id)}`);
  assert.equal(prop.status, "pending");
  assert.equal(prop.origin, "agent");
  assert.equal(prop.source_description, "openclaw");
  assert.ok(!String(prop.body).includes(GITHUB) && String(prop.body).includes(MARKER));
});

async function aSession(p: ReturnType<typeof plugin>, id: string) {
  const ctx = turn({ sessionId: id });
  p.on("after_tool_call")({ toolName: "write", params: { path: join(ctx.workspaceDir as string, "deploy", "db.yml") } }, ctx);
  await p.on("agent_end")(
    { success: true, messages: [{ role: "user", content: "move the database to pg-2" }, { role: "assistant", content: "Done: the database runs on pg-2." }] },
    ctx,
  );
  await p.on("session_end")({ sessionId: id, reason: "new" }, ctx);
}

test("capture is off by default: a session leaves nothing on disk and sends nothing", { skip }, async () => {
  const p = plugin();
  const before = Number((await asCurator("/proposals")).total);
  await aSession(p, "live-off");
  await p.on("session_start")({ sessionId: "live-next" }, {});
  let files: string[] = [];
  try {
    files = readdirSync(p.stateDir);
  } catch {
    // never created
  }
  assert.deepEqual(files, []);
  assert.equal(Number((await asCurator("/proposals")).total), before);
});

test("capture send: the session becomes one proposal in quarantine at the next start, never with a curator token", { skip }, async () => {
  const curator = plugin({ capture: "send", write_token: T.curator });
  const before = Number((await asCurator("/proposals")).total);
  await aSession(curator, "live-curator");
  await curator.on("session_start")({ sessionId: "live-next" }, {});
  assert.equal(Number((await asCurator("/proposals")).total), before);
  assert.ok(curator.logs.some((l) => l.includes("contributor")));

  const p = plugin({ capture: "send" });
  await aSession(p, "live-send");
  await p.on("session_start")({ sessionId: "live-next" }, {});
  const after = await asCurator("/proposals?status=pending");
  assert.equal(Number((await asCurator("/proposals")).total), before + 1);
  const mine = (after.items as Json[]).find((x) => String(x.name).startsWith("OpenClaw: infra — move the database to pg-2"));
  assert.ok(mine, JSON.stringify(after.items));
  assert.equal(mine.origin, "auto");
  assert.equal(mine.source_description, "openclaw session");
  await p.on("session_start")({ sessionId: "live-later" }, {});
  assert.equal(Number((await asCurator("/proposals")).total), before + 1, "one proposal per session");
});

test("what changed in the brain at the start of a session", { skip: skip || (env.MIMIRSYNTH_CONTRACT_NEWS === "1" ? false : "the instance has no graph") }, async () => {
  const p = plugin();
  await p.on("session_start")({ sessionId: "live-news" }, {});
  const r = await p.on("before_prompt_build")({ currentUserMessage: "ok" }, turn({ sessionId: "live-news" }));
  // a fresh brain has nothing new: the call is made and nothing is injected
  assert.equal(r, undefined);
});
