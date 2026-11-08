// What the OpenCode plugin and its command-line tool share, on top of the shared client library (integrations/shared/typescript,
// docs/AGENT_CLIENT.md): the blocks injected into a session, the local record of each session for the optional capture, and the text
// of the commands (status, search, remember, drafts). Nothing here is OpenCode's own API: the plugin (plugin.ts) wires it to OpenCode's
// hooks and the command-line tool (cli.ts) to a terminal.
//
// Nothing here throws at its caller when MimirSynth is away or answers with an error: every call has the configured timeout and fails
// open, and an expired, revoked or under-scoped token is said rather than silently ignored.
import { existsSync } from "node:fs";
import { basename, isAbsolute, relative, resolve } from "node:path";

import { ApiError, capture, Client, Config, configPath, failOpen, fetchTransport, redact, urlFor } from "../../shared/typescript/src/index.ts";
import type { Json, Transport } from "../../shared/typescript/src/index.ts";

export const AGENT = "OpenCode"; // how a captured session's proposal names the agent, for people
export const SOURCE = "opencode"; // and for machines; also the folder of its session records
export const PROMPT_MIN = 12; // a shorter prompt («ok», «go on») is not worth a recall
export const IDLE_END = 30 * 60; // seconds without a new prompt after which a session counts as finished (OpenCode has no «session end»)
export const NEWS_LIMIT = 20;
export const NEWS_CHARS = 4000;
export const FIRST_PROMPT_CHARS = 1500;
export const ANSWER_CHARS = 6000;
// other plugins or MCP servers that look like they inject memory too
export const MEMORY_NAMES = /memor|cognee|mem0|graphiti|letta|zep\b|supermemory|recall/i;

export type Env = Record<string, string | undefined>;

export interface Options {
  /** The environment (process.env by default): MIMIRSYNTH_* values win over the file. */
  env?: Env;
  /** The configuration file; by default ~/.config/mimirsynth/config.json or MIMIRSYNTH_CONFIG. */
  configPath?: string;
  /** How requests are made (fetch by default); tests replace it. */
  transport?: Transport;
  /** Where session records are kept; by default ~/.config/mimirsynth/state/opencode/sessions. */
  stateDir?: string;
  /** Seconds since the epoch, for tests. */
  now?: () => number;
}

/** What a hook gives back: context for the model, and messages for the person (never for the model). */
export interface Injection {
  context: string;
  messages: string[];
}

export type Record_ = capture.SessionRecord & { updated?: number };

function cut(s: string, n: number): string {
  return Array.from(s).slice(0, n).join("");
}

function errorText(e: unknown): string {
  if (e instanceof ApiError) return `MimirSynth answered ${e.status}: ${e.detail}`;
  const cause = e instanceof Error && e.cause instanceof Error ? ` (${e.cause.message})` : "";
  return `cannot reach MimirSynth: ${e instanceof Error ? e.message : String(e)}${cause}`;
}

/** The plugin's state that does not belong to one session: the configuration, read again on every call so a change applies at once. */
export class Mimir {
  readonly env: Env;
  readonly path: string;
  readonly transport: Transport;
  readonly stateDir: string | null;
  readonly now: () => number;

  constructor(opts: Options = {}) {
    this.env = opts.env ?? process.env;
    this.path = opts.configPath ?? configPath(this.env);
    this.transport = opts.transport ?? fetchTransport;
    this.stateDir = opts.stateDir ?? null;
    this.now = opts.now ?? (() => Date.now() / 1000);
  }

  config(cwd?: string | null): Config {
    return new Config({ path: this.path, env: this.env, cwd: cwd ?? null });
  }

  client(cwd?: string | null): Client {
    return new Client(this.config(cwd), this.transport);
  }

  store(): capture.Sessions {
    return new capture.Sessions(this.stateDir ?? capture.defaultDir(SOURCE, this.path));
  }

  // --- injected into a session -------------------------------------------------------------------------------------------------------

  /** The recall for a prompt, inside <mimirsynth-memory>; nothing when recall is off, the prompt is too short or the server is away. The
   * prompt is redacted before it leaves the machine. */
  async recall(prompt: string, cwd?: string | null): Promise<Injection> {
    const out: Injection = { context: "", messages: [] };
    const conf = this.config(cwd);
    const text = (prompt ?? "").trim();
    if (!conf.configured() || !conf.get("recall") || Array.from(text).length < PROMPT_MIN || text.startsWith("/")) return out;
    const { value, error } = await failOpen(() => new Client(conf, this.transport).recall(redact(text)));
    if (error?.auth) out.messages.push(`MimirSynth could not recall: ${error.detail}`);
    const ctx = String(value?.context ?? "").trim();
    if (ctx) out.context = `<mimirsynth-memory brain="${conf.get("brain")}">\n${ctx}\n</mimirsynth-memory>`;
    return out;
  }

  /** At session start: with capture on, the sessions that finished become proposals (send) or wait as drafts (draft); then what changed
   * in the brain since this token last asked, inside <mimirsynth-news>. `others` are other memory plugins found in OpenCode's config. */
  async sessionStart(current: string, cwd?: string | null, others: string[] = []): Promise<Injection> {
    const out: Injection = { context: "", messages: [] };
    if (others.length) {
      out.messages.push(`MimirSynth: other memory plugins also inject context here (${others.join("; ")}). ` +
        "MimirSynth's blocks are marked <mimirsynth-memory> and <mimirsynth-news>.");
    }
    const conf = this.config(cwd);
    if (!conf.configured()) return out;
    // both at once, so a slow proposal does not hold back what changed
    const [captured, news] = await Promise.all([this.captureAtStart(conf, current), this.news(conf)]);
    out.messages.push(...captured, ...news.messages);
    out.context = news.context;
    return out;
  }

  /** With capture on, what the sessions that finished become: proposals (send), or drafts waiting (draft). Messages for the person. */
  private async captureAtStart(conf: Config, current: string): Promise<string[]> {
    const mode = conf.captureMode();
    if (mode === "off") return [];
    const messages: string[] = [];
    const store = this.store();
    let waiting = 0;
    for (const rec of store.all() as Record_[]) {
      if (rec.session === current || rec.sent) continue;
      if (!rec.ended) {
        if (!this.idleLongEnough(rec)) continue; // still going, here or in another OpenCode
        rec.ended = true;
        store.save(rec);
      }
      if (!capture.worth(rec)) {
        store.drop(rec.session);
      } else if (mode === "send") {
        try {
          await capture.send(new Client(conf, this.transport), store, rec, AGENT, SOURCE);
        } catch (e) {
          if (e instanceof ApiError) messages.push(`MimirSynth did not propose the last session: ${e.detail}`);
          break; // the server is away: it is tried again at the next start
        }
      } else {
        waiting += 1;
      }
    }
    if (waiting) messages.push(`MimirSynth: ${waiting} session draft(s) waiting; review them with /mimirsynth-remember.`);
    return messages;
  }

  /** What changed in the brain since this token last asked, inside <mimirsynth-news>; nothing when nothing did or news is off. */
  private async news(conf: Config): Promise<Injection> {
    const out: Injection = { context: "", messages: [] };
    if (!conf.get("news")) return out;
    const { value, error } = await failOpen(() => new Client(conf, this.transport).news(NEWS_LIMIT, NEWS_CHARS));
    if (error?.auth) out.messages.push(`MimirSynth: ${error.detail}`);
    if (value && (Number(value.added) || Number(value.gone))) {
      out.context = `<mimirsynth-news brain="${conf.get("brain")}">\n${String(value.text ?? "").trim()}\n</mimirsynth-news>`;
    }
    return out;
  }

  idleLongEnough(rec: Record_): boolean {
    const last = Number(rec.updated ?? rec.started ?? 0);
    return !!(rec.turns || rec.files?.length) && this.now() - last >= IDLE_END;
  }

  // --- the local record of a session (only when capture is on) ---------------------------------------------------------------------

  captureOn(cwd?: string | null): boolean {
    return this.config(cwd).captureMode() !== "off";
  }

  private touch(session: string, cwd: string | null | undefined, change: (rec: Record_) => boolean | void): void {
    if (!session || !this.captureOn(cwd)) return;
    const store = this.store();
    const rec = store.load(session) as Record_;
    if (change(rec) === false) return;
    if (cwd) {
      rec.cwd ??= cwd;
      rec.project ??= basename(resolve(cwd));
    }
    rec.updated = this.now();
    store.save(rec);
  }

  /** A prompt: the first one is the session's task, redacted. A new prompt also means the session is not over. */
  recordPrompt(session: string, prompt: string, cwd?: string | null): void {
    const text = (prompt ?? "").trim();
    if (!text || text.startsWith("/")) return;
    this.touch(session, cwd, (rec) => {
      if (!rec.first_prompt) rec.first_prompt = redact(cut(text, FIRST_PROMPT_CHARS));
      rec.ended = false;
    });
  }

  /** A file an edit touched, relative to the project when inside it, redacted. */
  recordFile(session: string, file: string, cwd?: string | null): void {
    if (!file) return;
    this.touch(session, cwd, (rec) => {
      const abs = resolve(cwd ?? ".", file);
      const rel = cwd ? relative(resolve(cwd), abs) : "";
      const name = redact(rel && !rel.startsWith("..") && !isAbsolute(rel) ? rel.replaceAll("\\", "/") : basename(abs));
      if (rec.files.includes(name)) return false;
      rec.files.push(name);
    });
  }

  /** The end of a turn: one more turn, and the last answer, redacted. */
  recordAnswer(session: string, answer: string, cwd?: string | null): void {
    this.touch(session, cwd, (rec) => {
      rec.turns = Number(rec.turns || 0) + 1;
      const text = (answer ?? "").trim();
      if (text) rec.last_message = redact(cut(text, ANSWER_CHARS));
    });
  }

  /** Sessions that are over (deleted, or OpenCode closed): they are proposed at the next session start. */
  endSessions(sessions: Iterable<string>, cwd?: string | null): void {
    for (const s of sessions) {
      this.touch(s, cwd, (rec) => {
        if (!rec.turns && !rec.files.length) return false;
        rec.ended = true;
      });
    }
  }

  // --- commands ----------------------------------------------------------------------------------------------------------------------

  private async who(label: string, token: string, conf: Config): Promise<string[]> {
    if (!token) return [`${label}: not set`];
    try {
      const w = await new Client(conf, this.transport).whoami(token);
      const t = (w.token ?? {}) as Json;
      const scopes = Array.isArray(t.scopes) ? t.scopes.join(", ") : "";
      const exp = t.expires_at ? `, expires ${String(t.expires_at).slice(0, 10)}` : ", does not expire";
      return [`${label}: «${String(t.name ?? "?")}», role ${String(w.role)}, scopes ${scopes}${exp}`,
        `  brain «${String(w.name)}» (${String(w.brain)}), server ${String(w.version)}`];
    } catch (e) {
      return [`${label}: ${errorText(e)}`];
    }
  }

  /** Connection, brain, role, scopes and expiry of each token, server version, what is on, capture mode and drafts. */
  async status(cwd?: string | null, others: string[] = []): Promise<{ ok: boolean; text: string }> {
    const conf = this.config(cwd);
    const lines = [`Configuration: ${this.path}` + (existsSync(this.path) ? "" : " (missing: run setup, or set MIMIRSYNTH_* variables)")];
    if (!(conf.get("url") && conf.get("brain"))) {
      lines.push("Not configured: url and brain are missing.");
      return { ok: false, text: lines.join("\n") };
    }
    lines.push(`Server: ${conf.get("url")} · brain: ${conf.get("brain")}` + (conf.source("brain") === "project" ? " (this project's)" : ""));
    lines.push(...(await this.who("Recall token", conf.get("token"), conf)));
    if (conf.get("write_token")) lines.push(...(await this.who("Write token", conf.get("write_token"), conf)));
    lines.push(`Recall before each prompt: ${conf.get("recall") ? "on" : "off"} (up to ${conf.get("max_chars")} characters, ` +
      `${conf.get("timeout")} s) · what changed at session start: ${conf.get("news") ? "on" : "off"}`);
    const mode = conf.captureMode();
    lines.push(`Capture of what each session learned: ${mode}` + (mode === "off" ? " (nothing about the sessions is written or sent)" : ""));
    if (mode !== "off") {
      const recs = this.store().all();
      lines.push(`  sessions recorded on this machine: ${recs.length}; drafts waiting: ${recs.filter((r) => capture.isDraft(r)).length}`);
    }
    if (others.length) lines.push("Other memory plugins here: " + others.join("; "));
    return { ok: true, text: lines.join("\n") };
  }

  /** Recall on demand, with more results than before each prompt. */
  async search(query: string, cwd?: string | null): Promise<{ ok: boolean; text: string }> {
    const q = (query ?? "").trim();
    if (!q) return { ok: false, text: "Say what to look for." };
    const conf = this.config(cwd);
    if (!conf.configured()) return { ok: false, text: "MimirSynth is not configured: run setup." };
    try {
      const r = await new Client(conf, this.transport).recall(redact(q), { facts: 12, chunks: 6, maxChars: 12000, timeout: Math.max(conf.get("timeout"), 15) });
      return { ok: true, text: String(r.context ?? "").trim() || "MimirSynth has nothing on that." };
    } catch (e) {
      return { ok: false, text: errorText(e) };
    }
  }

  /** A memory, redacted, as one proposal with the write token: it waits for a curator. */
  async remember(title: string, content: string, confidence?: number | null, cwd?: string | null): Promise<{ ok: boolean; text: string }> {
    if (!(title ?? "").trim() || !(content ?? "").trim()) return { ok: false, text: "A memory needs a title and a content." };
    const conf = this.config(cwd);
    if (!conf.configured()) return { ok: false, text: "MimirSynth is not configured: run setup." };
    try {
      const r = await new Client(conf, this.transport).remember(title.trim(), content.trim(), { confidence, sourceDescription: SOURCE });
      return { ok: true, text: `Proposal #${String(r.id)}: ${String(r.status)}` + (r.status === "pending" ? " (waiting for a curator)" : "") };
    } catch (e) {
      return { ok: false, text: errorText(e) };
    }
  }

  /** The sessions the capture recorded and has not sent, as the proposals they would become. */
  drafts(cwd?: string | null): string {
    const conf = this.config(cwd);
    if (conf.captureMode() === "off") return "No drafts: the capture is off.";
    const ds = this.store().all().filter((r) => capture.isDraft(r));
    if (!ds.length) return "No drafts waiting.";
    return ds.map((r) => {
      const p = capture.proposal(r, AGENT, SOURCE, conf.get("capture_confidence"));
      const when = new Date(Number(r.started || 0) * 1000).toISOString().slice(0, 16).replace("T", " ");
      return `=== ${r.session} · ${when}\n${String(p.name)}\n\n${String(p.body)}\n`;
    }).join("\n");
  }

  async sendDraft(session: string, cwd?: string | null): Promise<{ ok: boolean; text: string }> {
    const store = this.store();
    const rec = store.all().find((r) => r.session === session && capture.isDraft(r));
    if (!rec) return { ok: false, text: "No such draft." };
    try {
      const r = await capture.send(this.client(cwd), store, rec, AGENT, SOURCE);
      return { ok: true, text: `Proposal #${String(r.id)}: ${String(r.status)}` };
    } catch (e) {
      return { ok: false, text: errorText(e) };
    }
  }

  dropDraft(session: string): string {
    this.store().drop(session);
    return "Forgotten.";
  }

  /** The MCP server OpenCode adds for on-demand tools (recall, facts_about, timeline, whats_new…), with the recall token; null when
   * MimirSynth is not configured. The token stays in MimirSynth's own file: it is never written to opencode.json. */
  mcpServer(cwd?: string | null): Json | null {
    const conf = this.config(cwd);
    if (!conf.configured()) return null;
    return {
      type: "remote",
      url: urlFor(conf, "/mcp"),
      headers: { Authorization: `Bearer ${conf.get("token")}` },
      oauth: false,
      enabled: true,
      timeout: Math.round(Math.max(conf.get("timeout"), 5) * 1000),
    };
  }
}

/** Other plugins and MCP servers in OpenCode's configuration that look like memory. */
export function otherMemory(cfg: { plugin?: unknown; mcp?: unknown } | null | undefined): string[] {
  const found = new Set<string>();
  for (const p of Array.isArray(cfg?.plugin) ? cfg.plugin : []) {
    const name = Array.isArray(p) ? String(p[0]) : String(p);
    if (MEMORY_NAMES.test(name) && !/mimirsynth/i.test(name)) found.add(name);
  }
  const mcp = cfg?.mcp && typeof cfg.mcp === "object" ? (cfg.mcp as Record<string, unknown>) : {};
  for (const [name, entry] of Object.entries(mcp)) {
    const on = !(entry && typeof entry === "object" && (entry as Json).enabled === false);
    if (on && MEMORY_NAMES.test(name) && !/mimirsynth/i.test(name)) found.add(`MCP ${name}`);
  }
  return [...found].sort();
}

/** The files a patch (OpenCode's apply_patch tool) adds, changes or deletes. */
export function patchedFiles(patch: string): string[] {
  const out: string[] = [];
  for (const m of (patch ?? "").matchAll(/^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm)) out.push(m[1].trim());
  for (const m of (patch ?? "").matchAll(/^\*\*\* Move to: (.+)$/gm)) out.push(m[1].trim());
  return out;
}
