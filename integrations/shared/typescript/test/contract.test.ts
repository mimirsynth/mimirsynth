// The TypeScript port passes the contract cases every implementation must pass (integrations/shared/contract/cases.json), and its
// secret detector has the same rules as the server's.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { ApiError, capture, Client, Config, CONTRACT_VERSION, DEFAULTS, failOpen, redact, secretscan } from "../src/index.ts";
import type { Key, Transport, WireRequest } from "../src/index.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..", "..", "..");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;
const CASES: Any = JSON.parse(readFileSync(join(ROOT, "integrations", "shared", "contract", "cases.json"), "utf8"));

function text(v: Any): Any {
  if (Array.isArray(v)) return v.join("");
  if (v && typeof v === "object" && "repeat" in v) return String(v.repeat).repeat(v.times);
  return v;
}

function rooted(v: Any, root: string): Any {
  if (typeof v === "string") return v.replaceAll("{root}", root);
  if (Array.isArray(v)) return v.map((x) => rooted(x, root));
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [rooted(k, root), rooted(x, root)]));
  return v;
}

function tmp(): string {
  return mkdtempSync(join(tmpdir(), "mimirsynth-contract-"));
}

for (const c of CASES.config) {
  test(`config: ${c.name}`, () => {
    const root = tmp();
    for (const [rel, content] of Object.entries(c.files)) {
      const p = join(root, rel);
      mkdirSync(dirname(p), { recursive: true });
      writeFileSync(p, typeof content === "string" ? content : JSON.stringify(rooted(content, root)));
    }
    const env = rooted(c.env, root);
    if (c.path === null) assert.ok("MIMIRSYNTH_CONFIG" in env); // never the real file
    const conf = new Config({ path: c.path ? join(root, c.path) : undefined, env, cwd: rooted(c.cwd ?? null, root) });
    for (const [key, want] of Object.entries(c.expect)) {
      const got = conf.get(key as Key);
      assert.deepEqual(got, want, key);
      assert.equal(typeof got, typeof DEFAULTS[key as Key], key);
    }
    for (const [key, want] of Object.entries(c.sources ?? {})) assert.equal(conf.source(key), want, key);
    if ("configured" in c) assert.equal(conf.configured(), c.configured);
  });
}

for (const c of CASES.redact) {
  test(`redact: ${c.name}`, () => assert.equal(redact(text(c.text)), c.expect));
}

CASES.worth.forEach((c: Any, i: number) => {
  test(`worth and drafts: case ${i + 1}`, () => {
    const rec = Object.fromEntries(Object.entries(c.record).map(([k, v]) => [k, text(v)]));
    if ("worth" in c) assert.equal(capture.worth(rec), c.worth);
    if ("draft" in c) assert.equal(capture.isDraft(rec), c.draft);
  });
});

for (const c of CASES.proposal) {
  test(`proposal: ${c.name}`, () => {
    const p = capture.proposal(c.record, c.agent, c.source, c.confidence);
    for (const [key, want] of Object.entries(c.expect)) assert.deepEqual(p[key], want, key);
  });
}

/** A transport that records every request and answers from a table (path → [status, reason, body], or an Error to throw). */
function wire(answers: Record<string, [number, string, string] | Error> = {}) {
  const calls: Any[] = [];
  const transport: Transport = async (req: WireRequest) => {
    calls.push({ method: req.method, url: req.url, auth: req.headers.Authorization ?? null, timeout: req.timeout, body: req.body ? JSON.parse(req.body) : null });
    const path = req.url.split("/api/brains/b1")[1].split("?")[0];
    const a = answers[path] ?? [200, "OK", "{}"];
    if (a instanceof Error) throw a;
    return { status: a[0], reason: a[1], body: a[2] };
  };
  return { calls, transport };
}

function conf(over: Any = {}): Config {
  const root = tmp();
  writeFileSync(join(root, "config.json"), JSON.stringify({ ...CASES.requests.config, ...over }));
  return new Config({ path: join(root, "config.json"), env: {} });
}

function camel(args: Any): Any {
  const names: Record<string, string> = { max_chars: "maxChars", source_description: "sourceDescription" };
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [names[k] ?? k, text(v)]));
}

for (const c of CASES.requests.cases) {
  test(`request: ${c.name}`, async () => {
    const w = wire();
    const client = new Client(conf(c.config ?? {}), w.transport);
    const a = camel(c.args);
    if (c.call === "recall") await client.recall(a.query, a);
    else if (c.call === "news") await client.news();
    else if (c.call === "whoami") await client.whoami(a.token);
    else if (c.call === "remember") await client.remember(a.title, a.content, a);
    else assert.fail(`unknown call ${c.call}`);
    const want = { ...c.expect };
    if (want.body?.query) want.body = { ...want.body, query: text(want.body.query) };
    assert.deepEqual(w.calls, [want]);
  });
}

for (const c of CASES.answers) {
  test(`answer: ${c.name}`, async () => {
    const w = wire({ "/whoami": [c.status, c.reason, c.body] });
    const client = new Client(conf(), w.transport);
    if ("value" in c.expect) {
      assert.deepEqual(await client.whoami(), c.expect.value);
      return;
    }
    await assert.rejects(client.whoami(), (e: Any) => {
      assert.ok(e instanceof ApiError);
      assert.deepEqual([e.status, e.detail, e.auth], [c.expect.status, c.expect.detail, c.expect.auth]);
      return true;
    });
  });
}

for (const c of CASES.send) {
  test(`send: ${c.name}`, async () => {
    const w = wire({ "/whoami": [200, "OK", JSON.stringify(c.whoami)], "/proposals": [201, "Created", JSON.stringify(c.proposals ?? {})] });
    const store = new capture.Sessions(join(tmp(), "sessions"));
    const rec: Any = { session: "s1", files: ["a.py"], ended: true, sent: null, started: 1794139200, project: "p", turns: 1 };
    const want = c.expect;
    if ("error" in want) {
      await assert.rejects(capture.send(new Client(conf(), w.transport), store, rec, "OpenCode", "opencode"), (e: Any) => e.status === want.error);
    } else {
      await capture.send(new Client(conf(), w.transport), store, rec, "OpenCode", "opencode");
      assert.equal(w.calls.at(-1).auth, want.auth);
      assert.equal(w.calls.at(-1).timeout, want.timeout);
    }
    assert.deepEqual(w.calls.map((x) => `${x.method} ${x.url.split("/api/brains/b1")[1]}`), want.calls);
    if (want.sent) {
      assert.deepEqual({ id: rec.sent.id, status: rec.sent.status }, want.sent);
      assert.equal(store.load("s1").sent?.id, want.sent.id);
    } else assert.ok(!rec.sent);
  });
}

test("the cases are for this version of the contract", () => assert.equal(CASES.contract_version, CONTRACT_VERSION));

test("failOpen turns a network error into nothing and keeps what the server said", async () => {
  const down = new Client(conf(), wire({ "/recall": new Error("timed out") }).transport);
  assert.deepEqual(await failOpen(() => down.recall("where does the database run?")), { value: null, error: null });
  const revoked = new Client(conf(), wire({ "/recall": [401, "Unauthorized", '{"detail": "token revoked"}'] }).transport);
  const o = await failOpen(() => revoked.recall("where does the database run?"));
  assert.equal(o.value, null);
  assert.ok(o.error?.auth && o.error.detail === "token revoked");
});

test("the default file and the session folder", () => {
  const store = new capture.Sessions(join(tmp(), "s"));
  store.save({ session: "a/b c", started: 0, files: [], turns: 0, ended: false, sent: null });
  assert.deepEqual(store.all(), []); // older than KEEP_DAYS: dropped on the way
  assert.match(capture.defaultDir("opencode", "/x/.config/mimirsynth/config.json").replaceAll("\\", "/"), /\/x\/\.config\/mimirsynth\/state\/opencode\/sessions$/);
});

test("the detector has the server's rules, in the same order", () => {
  const server = readFileSync(join(ROOT, "api", "mimirsynth", "secretscan.py"), "utf8");
  const ids = [...server.matchAll(/^\s+Rule\("([a-z_]+)"/gm)].map((m) => m[1]);
  assert.ok(ids.length > 10);
  assert.deepEqual(secretscan.RULES.map((r) => r.id), ids);
});
