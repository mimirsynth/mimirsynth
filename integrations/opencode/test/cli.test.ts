// The command-line tool: setup writes the shared configuration readable only by its owner and keeps what it does not ask about,
// install goes through OpenCode's own `opencode plugin`, and the other commands answer as the plugin's.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import type { Transport, WireRequest } from "../../shared/typescript/src/index.ts";
import { type Io, main } from "../src/cli.ts";

function io(answers: string[] = [], run: Io["run"] = () => 0) {
  const out: string[] = [];
  const asked: { label: string; secret: boolean }[] = [];
  const ran: string[] = [];
  const it: Io = {
    out: (s) => void out.push(s),
    ask: async (label, secret) => {
      asked.push({ label, secret });
      return answers.shift() ?? "";
    },
    run: (cmd, args) => {
      ran.push([cmd, ...args].join(" "));
      return run(cmd, args);
    },
  };
  return { it, out, asked, ran };
}

const calls: WireRequest[] = [];
const transport: Transport = async (req) => {
  calls.push(req);
  if (req.url.endsWith("/whoami")) return { status: 200, reason: "", body: JSON.stringify({ brain: "team", name: "Team", role: "reader", version: "1.2.3", token: { name: "cli", scopes: ["recall"] } }) };
  if (req.url.endsWith("/proposals")) return { status: 200, reason: "", body: JSON.stringify({ id: 3, status: "pending" }) };
  return { status: 200, reason: "", body: JSON.stringify({ context: "## Facts\n- found" }) };
};

function conf(data?: Record<string, unknown>): string {
  const p = join(mkdtempSync(join(tmpdir(), "mimirsynth-cli-")), "mimirsynth", "config.json");
  if (data) {
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, JSON.stringify(data));
  }
  return p;
}

test("setup asks for the tokens hidden and writes the shared file readable only by its owner", async () => {
  const path = conf();
  const t = io(["https://mimir.example/", "team", "mst_reader", "mst_writer", "draft"]);
  assert.equal(await main(["setup"], t.it, { env: {}, configPath: path, transport }), 0);
  assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), { url: "https://mimir.example", brain: "team", token: "mst_reader", write_token: "mst_writer", capture: "draft" });
  assert.deepEqual(t.asked.map((a) => a.secret), [false, false, true, true, false]);
  if (process.platform !== "win32") assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.ok(t.out.join("\n").includes("Recall token: «cli», role reader"));
  assert.ok(!t.out.join("\n").includes("mst_reader"), "a token is never printed");
});

test("setup keeps what it does not ask about and what the person leaves empty", async () => {
  const path = conf({ url: "https://old", brain: "team", token: "mst_old", projects: { "/work/infra": { brain: "infra" } }, max_chars: 2500 });
  const t = io(["", "", "", "send"]); // the URL comes as a flag: brain, token, write token and capture are asked
  assert.equal(await main(["setup", "--url", "https://new"], t.it, { env: {}, configPath: path, transport }), 0);
  const data = JSON.parse(readFileSync(path, "utf8"));
  assert.deepEqual(data, { url: "https://new", brain: "team", token: "mst_old", projects: { "/work/infra": { brain: "infra" } }, max_chars: 2500, capture: "send" });
  assert.ok(t.asked[0].label.includes("[team]"));
  assert.ok(t.asked[1].label.includes("leave empty to keep it") && !t.asked[1].label.includes("mst_old"));
});

test("an unknown capture mode is written as off", async () => {
  const path = conf();
  await main(["setup", "--url", "u", "--brain", "b", "--capture", "always"], io(["t", ""]).it, { env: {}, configPath: path, transport });
  assert.equal(JSON.parse(readFileSync(path, "utf8")).capture, "off");
});

test("install adds the plugin with OpenCode's own command, then runs setup", async () => {
  const path = conf();
  const t = io(["https://m", "b", "t", "", ""]);
  assert.equal(await main(["install"], t.it, { env: {}, configPath: path, transport }), 0);
  assert.deepEqual(t.ran, ["opencode plugin @mimirsynth/opencode --global"]);
  assert.equal(JSON.parse(readFileSync(path, "utf8")).url, "https://m");
  const missing = io([], () => null);
  assert.equal(await main(["install"], missing.it, { env: {}, configPath: conf(), transport }), 1);
  assert.match(missing.out.join("\n"), /OpenCode is not on the PATH/);
  const noSetup = io();
  assert.equal(await main(["install", "--no-setup"], noSetup.it, { env: {}, configPath: conf(), transport }), 0);
  assert.equal(noSetup.asked.length, 0);
});

test("status, search and remember from a terminal", async () => {
  const path = conf({ url: "https://m", brain: "team", token: "mst_r", write_token: "mst_w" });
  const o = { env: {}, configPath: path, transport };
  let t = io();
  assert.equal(await main(["status"], t.it, o), 0);
  assert.match(t.out[0], /Capture of what each session learned: off/);
  t = io();
  assert.equal(await main(["search", "the", "database"], t.it, o), 0);
  assert.deepEqual(t.out, ["## Facts\n- found"]);
  t = io();
  assert.equal(await main(["remember", "--title", "T", "--content", "C", "--confidence", "0.7"], t.it, o), 0);
  assert.deepEqual(t.out, ["Proposal #3: pending (waiting for a curator)"]);
  assert.equal(JSON.parse(calls.at(-1)!.body!).confidence, 0.7);
  t = io();
  assert.equal(await main(["remember", "--title", "T"], t.it, o), 2);
  assert.equal(await main(["status"], io().it, { env: {}, configPath: conf(), transport }), 1);
  assert.equal(await main(["nonsense"], io().it, o), 2);
  assert.equal(await main(["help"], io().it, o), 0);
});
