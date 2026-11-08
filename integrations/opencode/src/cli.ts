// The MimirSynth plugin's command-line tool, for a terminal (Node.js 18 or later): `npx -y @mimirsynth/opencode <command>`.
//
//   install                         adds the plugin to OpenCode's global configuration (opencode plugin … --global), then runs setup
//   setup [--url U] [--brain B] [--capture off|draft|send]
//                                   asks for the server, the brain and the tokens (hidden) and writes ~/.config/mimirsynth/config.json
//   status                          connection, brain, role and expiry of each token, server version, capture mode, drafts
//   search <query…>                 recall on demand, with more results than before each prompt
//   remember --title T --content C [--confidence X]
//                                   proposes a memory with the write token (redacted first)
//   drafts                          the sessions the capture recorded and has not sent (capture = draft)
//   send-draft <session>            proposes one of them; drop-draft <session> forgets it
//
// Tokens are only ever typed here, never in a conversation with the agent.
import { spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

import { CAPTURE_MODES } from "../../shared/typescript/src/index.ts";
import { Mimir, type Options } from "./core.ts";

export const PACKAGE = "@mimirsynth/opencode";

export interface Io {
  out: (s: string) => void;
  /** Asks a question; `secret` hides what is typed. Resolves to the answer, without the line end. */
  ask: (label: string, secret: boolean) => Promise<string>;
  /** Runs a command (install): its exit code, or null when it could not start. */
  run: (cmd: string, args: string[]) => number | null;
}

function parse(argv: string[]): { cmd: string; pos: string[]; flags: Record<string, string> } {
  const [cmd = "", ...rest] = argv;
  const pos: string[] = [];
  const flags: Record<string, string> = {};
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a.startsWith("--")) {
      const [k, v] = a.slice(2).split(/=(.*)/s, 2);
      if (v !== undefined) flags[k] = v;
      else if (i + 1 < rest.length && !rest[i + 1].startsWith("--")) flags[k] = rest[++i];
      else flags[k] = "true";
    } else {
      pos.push(a);
    }
  }
  return { cmd, pos, flags };
}

async function setup(m: Mimir, flags: Record<string, string>, io: Io): Promise<number> {
  let c: Record<string, unknown> = {};
  try {
    const data: unknown = JSON.parse(readFileSync(m.path, "utf8"));
    if (data && typeof data === "object" && !Array.isArray(data)) c = data as Record<string, unknown>;
  } catch {
    // a new file
  }
  const cur = (k: string) => (typeof c[k] === "string" ? (c[k] as string) : "");
  const ask = async (label: string, key: string, secret = false) => {
    const hint = cur(key) ? (secret ? " (leave empty to keep it)" : ` [${cur(key)}]`) : "";
    return (await io.ask(`${label}${hint}: `, secret)).trim() || cur(key);
  };
  c.url = (flags.url || (await ask("MimirSynth URL (https://…)", "url"))).replace(/\/+$/, "");
  c.brain = flags.brain || (await ask("Brain (its slug)", "brain"));
  c.token = await ask("Reader token for recall (mst_…)", "token", true);
  c.write_token = await ask("Contributor token to propose (optional)", "write_token", true);
  const mode = (flags.capture || (await ask("Capture what each session learned: off, draft or send", "capture")) || "off").toLowerCase();
  c.capture = (CAPTURE_MODES as readonly string[]).includes(mode) ? mode : "off";
  mkdirSync(dirname(m.path), { recursive: true });
  const clean = Object.fromEntries(Object.entries(c).filter(([, v]) => v !== "" && v !== undefined && v !== null));
  writeFileSync(m.path, JSON.stringify(clean, null, 2), { encoding: "utf8", mode: 0o600 });
  try {
    chmodSync(m.path, 0o600);
  } catch {
    // not every file system keeps permissions
  }
  io.out(`Saved in ${m.path}. Restart OpenCode so it picks it up.\n`);
  return status(m, io);
}

async function status(m: Mimir, io: Io): Promise<number> {
  const r = await m.status(process.cwd());
  io.out(r.text);
  return r.ok ? 0 : 1;
}

async function install(m: Mimir, flags: Record<string, string>, io: Io): Promise<number> {
  io.out(`Adding ${PACKAGE} to OpenCode's global configuration…`);
  const code = io.run("opencode", ["plugin", PACKAGE, "--global"]);
  if (code !== 0) {
    io.out(code === null
      ? "OpenCode is not on the PATH. Install it (https://opencode.ai) and run: opencode plugin @mimirsynth/opencode --global"
      : `opencode plugin ${PACKAGE} --global failed (exit ${code}). Add "${PACKAGE}" to "plugin" in ~/.config/opencode/opencode.json by hand.`);
    if (code === null) return 1;
  }
  if (flags["no-setup"] === "true") return code === 0 ? 0 : 1;
  io.out("");
  return setup(m, flags, io);
}

export async function main(argv: string[], io: Io = terminal(), opts: Options = {}): Promise<number> {
  const m = new Mimir(opts);
  const { cmd, pos, flags } = parse(argv);
  const cwd = process.cwd();
  switch (cmd) {
    case "install":
      return install(m, flags, io);
    case "setup":
      return setup(m, flags, io);
    case "status":
      return status(m, io);
    case "search": {
      const r = await m.search(pos.join(" "), cwd);
      io.out(r.text);
      return r.ok ? 0 : pos.length ? 1 : 2;
    }
    case "remember": {
      const confidence = flags.confidence !== undefined ? Number(flags.confidence) : null;
      if (!flags.title || !flags.content || (confidence !== null && !(confidence >= 0 && confidence <= 1))) {
        io.out("Usage: remember --title T --content C [--confidence 0..1]");
        return 2;
      }
      const r = await m.remember(flags.title, flags.content, confidence, cwd);
      io.out(r.text);
      return r.ok ? 0 : 1;
    }
    case "drafts":
      io.out(m.drafts(cwd));
      return 0;
    case "send-draft": {
      if (!pos[0]) break;
      const r = await m.sendDraft(pos[0], cwd);
      io.out(r.text);
      return r.ok ? 0 : r.text === "No such draft." ? 2 : 1;
    }
    case "drop-draft":
      if (!pos[0]) break;
      io.out(m.dropDraft(pos[0]));
      return 0;
  }
  io.out([
    `Usage: npx -y ${PACKAGE} <command>`,
    "  install                     add the plugin to OpenCode, then setup",
    "  setup                       configure the server, the brain and the tokens",
    "  status                      what is configured and whether it works",
    "  search <query…>             search the memory",
    "  remember --title T --content C [--confidence X]",
    "  drafts | send-draft <session> | drop-draft <session>",
  ].join("\n"));
  return cmd === "help" || cmd === "--help" || cmd === "-h" ? 0 : 2;
}

/** Reads one line from a terminal without showing it; from a pipe, a plain line. */
function hidden(label: string): Promise<string> {
  const stdin = process.stdin;
  if (!stdin.isTTY) return line(label);
  return new Promise((ok) => {
    process.stdout.write(label);
    let value = "";
    stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding("utf8");
    const done = (v: string) => {
      stdin.setRawMode(false);
      stdin.pause();
      stdin.removeListener("data", onData);
      process.stdout.write("\n");
      ok(v);
    };
    const onData = (chunk: string) => {
      for (const ch of chunk) {
        if (ch === "\r" || ch === "\n") return done(value);
        if (ch === "\u0003") {
          stdin.setRawMode(false);
          process.stdout.write("\n");
          process.exit(130);
        }
        if (ch === "\u007f" || ch === "\b") value = value.slice(0, -1);
        else if (ch >= " ") value += ch;
      }
    };
    stdin.on("data", onData);
  });
}

let pending: string[] | null = null; // lines read ahead from a pipe
let waiting: ((l: string) => void)[] = [];

function line(label: string): Promise<string> {
  process.stdout.write(label);
  if (!pending) {
    pending = [];
    const rl = createInterface({ input: process.stdin, terminal: false });
    rl.on("line", (l) => {
      const w = waiting.shift();
      if (w) w(l);
      else pending!.push(l);
    });
    rl.on("close", () => {
      for (const w of waiting) w("");
      waiting = [];
    });
  }
  if (pending.length) return Promise.resolve(pending.shift()!);
  if (process.stdin.readableEnded) return Promise.resolve("");
  return new Promise((ok) => waiting.push(ok));
}

export function terminal(): Io {
  return {
    out: (s) => process.stdout.write(s + "\n"),
    ask: (label, secret) => (secret ? hidden(label) : line(label)),
    run: (cmd, args) => {
      if (!commandExists(cmd)) return null;
      // on Windows opencode is a .cmd shim, which only a shell runs; the arguments are fixed, never the person's input
      const r = spawnSync(cmd, args, { stdio: "inherit", shell: process.platform === "win32" });
      return r.error ? null : r.status;
    },
  };
}

function commandExists(cmd: string): boolean {
  const r = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], { stdio: "ignore", shell: false });
  return r.status === 0;
}

function isMain(): boolean {
  try {
    return !!process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (isMain()) {
  main(process.argv.slice(2)).then((code) => process.exit(code), (e: unknown) => {
    process.stderr.write(`${e instanceof Error ? e.message : String(e)}\n`);
    process.exit(1);
  });
}
