// The TypeScript port against a test instance: the same checks as api/tests/test_agent_contract.py, which starts the instance and runs
// this file with MIMIRSYNTH_CONTRACT_URL, _BRAIN, _READER, _CONTRIBUTOR, _CURATOR, _PROPOSE_ONLY (tokens) and _NEWS (1 when the
// instance has a graph). Without MIMIRSYNTH_CONTRACT_URL every test is skipped.
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ApiError, capture, Client, Config, failOpen, MARKER } from "../src/index.ts";
import type { Json } from "../src/index.ts";

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

function conf(over: Record<string, unknown> = {}): Config {
  const dir = mkdtempSync(join(tmpdir(), "mimirsynth-live-"));
  const data = { url: URL_, brain: BRAIN, token: T.reader, write_token: T.contributor, timeout: 10, ...over };
  writeFileSync(join(dir, "config.json"), JSON.stringify(data));
  return new Config({ path: join(dir, "config.json"), env: {} });
}

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

test("recall and whoami", { skip }, async () => {
  const c = new Client(conf());
  const who = await c.whoami();
  assert.equal(who.role, "reader");
  assert.equal(who.brain, BRAIN);
  assert.equal((await c.whoami(T.contributor)).role, "contributor");
  const r = await c.recall("where does the production database run? (typescript)");
  assert.match(String(r.context), /the contract brain answers: where does the production database/);
});

test("what the server says when a token cannot, and failOpen when it is away", { skip }, async () => {
  let o = await failOpen(() => new Client(conf({ token: T.proposeOnly })).recall("where does the production database run?"));
  assert.ok(o.value === null && o.error instanceof ApiError && o.error.status === 403 && o.error.auth && o.error.detail);
  o = await failOpen(() => new Client(conf({ token: "mst_" + "not-a-real-token" })).recall("where does the production database run?"));
  assert.ok(o.error?.status === 401 && o.error.auth);
  const away = new Client(conf({ url: `http://127.0.0.1:${await freePort()}`, timeout: 2 }));
  const started = Date.now();
  assert.deepEqual(await failOpen(() => away.recall("where does the production database run?")), { value: null, error: null });
  assert.ok(Date.now() - started < 5000);
});

test("remember proposes redacted into quarantine", { skip }, async () => {
  const r = await new Client(conf()).remember("Deploy key moved", `The deploy key now lives in Vaultwarden; the old one ${GITHUB} was revoked.`, {
    confidence: 0.8,
    sourceDescription: "contract",
  });
  assert.equal(r.status, "pending");
  const p = await asCurator(`/proposals/${r.id}`);
  assert.ok(!String(p.body).includes(GITHUB) && String(p.body).includes(MARKER));
  assert.equal(p.origin, "agent");
  assert.equal(p.confidence, 0.8);
});

test("capture sends one quarantined proposal, only with a contributor token", { skip }, async () => {
  const store = new capture.Sessions(join(mkdtempSync(join(tmpdir(), "mimirsynth-live-")), "sessions"));
  const rec: capture.SessionRecord = {
    session: "s1", files: ["ops/deploy.sh"], turns: 3, started: Date.now() / 1000, ended: true, sent: null, project: "infra",
    first_prompt: "rotate the deploy key", last_message: "Done: the key lives in Vaultwarden.",
  };
  const before = Number((await asCurator("/proposals")).total);
  await assert.rejects(capture.send(new Client(conf({ write_token: T.curator })), store, rec, "Contract", "contract"), (e: unknown) => {
    return e instanceof ApiError && e.status === 403 && e.detail.includes("contributor");
  });
  assert.equal(rec.sent, null);
  assert.equal(Number((await asCurator("/proposals")).total), before);
  const r = await capture.send(new Client(conf()), store, rec, "Contract", "contract");
  assert.equal(r.status, "pending");
  assert.equal(store.load("s1").sent?.id, r.id);
  assert.equal(Number((await asCurator("/proposals")).total), before + 1);
  const p = await asCurator(`/proposals/${r.id}`);
  assert.equal(p.origin, "auto");
  assert.equal(p.confidence, 0.3);
  assert.equal(p.source_description, "contract session");
  assert.ok(String(p.body).includes("ops/deploy.sh"));
});

test("news", { skip: skip || (env.MIMIRSYNTH_CONTRACT_NEWS === "1" ? false : "the instance has no graph") }, async () => {
  const r = await new Client(conf()).news();
  assert.equal(r.added, 0);
  assert.equal(r.gone, 0);
  assert.ok(r.text);
});
