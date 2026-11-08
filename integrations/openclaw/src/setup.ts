// `openclaw mimirsynth setup`: asks, in a terminal and never through a chat, for the server, the brain, the tokens (without showing
// them) and the capture mode, and writes the shared configuration file readable only by its owner (docs/AGENT_CLIENT.md).
import { chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { createInterface } from "node:readline";
import { Writable } from "node:stream";

import { CAPTURE_ALIASES, CAPTURE_MODES } from "../../shared/typescript/src/index.ts";

export type Ask = (label: string, secret: boolean) => Promise<string>;

interface Reader {
  close(): void;
  lines: string[];
  waiters: ((line: string | null) => void)[];
  closed: boolean;
  muted: boolean;
}

let reader: Reader | null = null;

/** One reader for every question, so the answers piped to a non-interactive run are not lost between questions. */
function lineReader(): Reader {
  if (reader) return reader;
  const r: Reader = { close: () => undefined, lines: [], waiters: [], closed: false, muted: false };
  const output = new Writable({
    write(chunk, encoding, done) {
      if (!r.muted) process.stdout.write(chunk, encoding);
      done();
    },
  });
  const rl = createInterface({ input: process.stdin, output, terminal: !!process.stdin.isTTY });
  rl.on("line", (line) => {
    const w = r.waiters.shift();
    if (w) w(line);
    else r.lines.push(line);
  });
  rl.on("close", () => {
    r.closed = true;
    for (const w of r.waiters.splice(0)) w(null);
  });
  r.close = () => rl.close();
  reader = r;
  return r;
}

/** Lets the process end once the questions are over. */
export function closeTerminal(): void {
  reader?.close();
  reader = null;
}

/** A question in the terminal; a secret one does not echo what is typed. */
export const terminalAsk: Ask = async (label, secret) => {
  const r = lineReader();
  process.stdout.write(label);
  r.muted = secret && !!process.stdin.isTTY;
  const line = r.lines.length ? (r.lines.shift() as string) : r.closed ? null : await new Promise<string | null>((ok) => r.waiters.push(ok));
  if (r.muted || line === null) process.stdout.write("\n");
  r.muted = false;
  return line ?? "";
};

export interface SetupFlags {
  url?: string;
  brain?: string;
  capture?: string;
}

function captureMode(v: string): string {
  const s = v.trim().toLowerCase();
  const mode = CAPTURE_ALIASES[s] ?? s;
  return (CAPTURE_MODES as readonly string[]).includes(mode) ? mode : "off";
}

/** Asks what is missing, keeps what the file already has when the answer is empty, and writes the file with 0600. */
export async function setup(path: string, flags: SetupFlags, ask: Ask = terminalAsk): Promise<string> {
  let c: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(readFileSync(path, "utf8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) c = parsed as Record<string, unknown>;
  } catch {
    // a new file
  }
  const str = (k: string) => (typeof c[k] === "string" || typeof c[k] === "number" ? String(c[k]) : "");
  const q = async (label: string, current: string, secret = false) => {
    const hint = current ? (secret ? " (leave empty to keep it)" : ` [${current}]`) : "";
    return (await ask(`${label}${hint}: `, secret)).trim() || current;
  };
  c.url = (flags.url || (await q("MimirSynth URL (https://…)", str("url")))).replace(/\/+$/, "");
  c.brain = flags.brain || (await q("Brain (its slug)", str("brain")));
  c.token = await q("Reader token for recall (mst_…)", str("token"), true);
  c.write_token = await q("Contributor token to propose (optional)", str("write_token"), true);
  c.capture = captureMode(flags.capture || (await q("Capture what each session learned: off, draft or send", str("capture") || "off")));
  const out = Object.fromEntries(Object.entries(c).filter(([, v]) => v !== "" && v !== undefined && v !== null));
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(out, null, 2), { encoding: "utf8", mode: 0o600 });
  try {
    chmodSync(path, 0o600);
  } catch {
    // not every file system keeps permissions
  }
  return `Saved in ${path}.`;
}
