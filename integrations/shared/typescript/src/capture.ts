// The optional capture of what a session learned (docs/AGENT_CLIENT.md), off unless `capture` says otherwise. The TypeScript port of
// integrations/shared/python/mimirsynth_agent/capture.py.
//
//   off    (the default) nothing about a session is written or sent
//   draft  each session is kept on this machine, already redacted, until the person reviews it
//   send   at the next session start, each finished session worth it becomes one proposal, in quarantine
import { chmodSync, mkdirSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

import { ApiError, type Client, type Json } from "./client.ts";
import { configPath } from "./config.ts";

export const KEEP_DAYS = 14; // local session records older than this are dropped
export const WORTH_CHARS = 400; // a session without edits is only worth proposing if its last answer says this much

export interface SessionRecord {
  session: string;
  files: string[];
  turns: number;
  started: number; // seconds since the epoch
  ended: boolean;
  sent: { id?: unknown; status?: unknown; at: number } | null;
  project?: string;
  cwd?: string;
  first_prompt?: string;
  last_message?: string;
  [extra: string]: unknown;
}

/** Where an integration keeps its session records unless its agent gives it a folder: ~/.config/mimirsynth/state/<agent>/sessions. */
export function defaultDir(agent: string, confPath: string = configPath()): string {
  return join(dirname(confPath), "state", agent, "sessions");
}

/** The session records of one integration, one file each, readable only by the person. The folder is created when first used. */
export class Sessions {
  readonly base: string;

  constructor(directory: string) {
    this.base = directory;
  }

  dir(): string {
    mkdirSync(this.base, { recursive: true });
    return this.base;
  }

  path(session: string): string {
    const name = Array.from((session || "unknown").replace(/[^\p{L}\p{N}_.-]/gu, "_")).slice(0, 120).join("");
    return join(this.dir(), `${name}.json`);
  }

  load(session: string): SessionRecord {
    try {
      return JSON.parse(readFileSync(this.path(session), "utf8")) as SessionRecord;
    } catch {
      return { session, files: [], turns: 0, started: Date.now() / 1000, ended: false, sent: null };
    }
  }

  save(rec: SessionRecord): void {
    const p = this.path(rec.session);
    writeFileSync(p, JSON.stringify(rec), { encoding: "utf8", mode: 0o600 });
    try {
      chmodSync(p, 0o600);
    } catch {
      // not every file system keeps permissions
    }
  }

  /** Every record, by file name; those older than KEEP_DAYS are deleted on the way. */
  all(): SessionRecord[] {
    const out: SessionRecord[] = [];
    for (const name of readdirSync(this.dir()).filter((n) => n.endsWith(".json")).sort()) {
      const p = join(this.base, name);
      let rec: SessionRecord;
      try {
        rec = JSON.parse(readFileSync(p, "utf8")) as SessionRecord;
      } catch {
        continue;
      }
      if (Date.now() / 1000 - Number(rec.started || 0) > KEEP_DAYS * 86400) {
        try {
          unlinkSync(p);
        } catch {
          // already gone
        }
        continue;
      }
      out.push(rec);
    }
    return out;
  }

  drop(session: string): void {
    try {
      unlinkSync(this.path(session));
    } catch {
      // already gone
    }
  }
}

/** Only sessions that changed something, or ended with a substantial answer, are proposed. */
export function worth(rec: Partial<SessionRecord>): boolean {
  return !!rec.files?.length || Array.from(rec.last_message ?? "").length >= WORTH_CHARS;
}

/** A finished session worth proposing that has not been sent. */
export function isDraft(rec: Partial<SessionRecord>): boolean {
  return !!(rec.ended && !rec.sent && worth(rec));
}

function day(seconds: number): string {
  const d = new Date(seconds * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function cut(s: string, n: number): string {
  return Array.from(s).slice(0, n).join("");
}

/** The proposal a session becomes: the task, the outcome and the files it changed, already redacted when recorded. `agent` names the
 * agent for people («OpenCode»), `source` for machines («opencode»). */
export function proposal(rec: Partial<SessionRecord>, agent: string, source: string, confidence: number): Json {
  const project = rec.project || "?";
  const task = (rec.first_prompt ?? "").trim();
  const files = rec.files ?? [];
  const body = [`${agent} session in «${project}» (${day(Number(rec.started || Date.now() / 1000))}).`];
  if (task) body.push("", `Task: ${cut(task, 500)}`);
  if (rec.last_message) body.push("", "Outcome:", cut(rec.last_message, 3000));
  if (files.length) body.push("", "Files changed: " + files.slice(0, 20).join(", ") + (files.length > 20 ? ` and ${files.length - 20} more` : ""));
  const first = task ? cut(task.split(/\r\n|\r|\n/)[0], 80) : "session";
  return {
    name: cut(`${agent}: ${project} — ${first}`, 255),
    body: body.join("\n"),
    source: "text",
    source_description: `${source} session`,
    origin: "auto",
    confidence: Number(confidence),
  };
}

/** Sends a recorded session as one proposal, only with a contributor token: a curator's would be approved at once. */
export async function send(client: Client, store: Sessions, rec: SessionRecord, agent: string, source: string): Promise<Json> {
  const conf = client.conf;
  const token = client.writeToken();
  const who = await client.whoami(token);
  if (who.role !== "contributor") {
    throw new ApiError(403, `the capture only sends with a contributor token, and this one is ${String(who.role)}: its proposals would not wait in quarantine`);
  }
  const r = await client.propose(proposal(rec, agent, source, conf.get("capture_confidence")), token, Math.max(conf.get("timeout"), 10));
  rec.sent = { id: r.id, status: r.status, at: Date.now() / 1000 };
  store.save(rec);
  return r;
}
