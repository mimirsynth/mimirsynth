// What the plugin's commands answer, the same from the terminal (`openclaw mimirsynth …`), from a chat (`/mimirsynth …`) and, for
// search and remember, from the agent's tools: plain text, never an exception.
import { existsSync } from "node:fs";

import { ApiError, capture, failOpen, type Json } from "../../shared/typescript/src/index.ts";
import { AGENT, Mimir, PLUGIN_ID, type PluginSettings, SOURCE } from "./core.ts";

/** What the status says about OpenClaw's own configuration (the host's `openclaw.json`). */
export interface HostFacts {
  conversationAccess?: boolean; // plugins.entries.mimirsynth.hooks.allowConversationAccess
  promptInjection?: boolean; // plugins.entries.mimirsynth.hooks.allowPromptInjection (allowed unless false)
  memorySlot?: string; // plugins.slots.memory
}

export function hostFacts(openclawConfig: unknown): HostFacts {
  const plugins = (openclawConfig as { plugins?: Record<string, unknown> } | undefined)?.plugins ?? {};
  const entry = ((plugins.entries as Record<string, unknown> | undefined)?.[PLUGIN_ID] ?? {}) as { hooks?: Record<string, unknown> };
  const slots = (plugins.slots ?? {}) as Record<string, unknown>;
  return {
    conversationAccess: entry.hooks?.allowConversationAccess === true,
    promptInjection: entry.hooks?.allowPromptInjection !== false,
    memorySlot: typeof slots.memory === "string" ? slots.memory : "memory-core",
  };
}

export const GRANT = `openclaw config set plugins.entries.${PLUGIN_ID}.hooks.allowConversationAccess true`;

async function who(m: Mimir, label: string, token: string): Promise<string[]> {
  if (!token) return [`${label}: not set`];
  const { value, error } = await failOpen(() => m.client().whoami(token));
  if (error) return [`${label}: MimirSynth answered ${error.status}: ${error.detail}`];
  if (!value) return [`${label}: cannot reach MimirSynth at ${m.config().get("url")}`];
  const t = (value.token ?? {}) as Json;
  const scopes = Array.isArray(t.scopes) ? t.scopes.join(", ") : "";
  const exp = t.expires_at ? `, expires ${String(t.expires_at).slice(0, 10)}` : ", does not expire";
  return [`${label}: «${String(t.name ?? "?")}», role ${String(value.role)}, scopes ${scopes}${exp}`, `  brain «${String(value.name)}» (${String(value.brain)}), server ${String(value.version)}`];
}

/** Connection, brain, the role, scopes and expiry of each token, server version, what is on, capture mode and drafts. */
export async function status(m: Mimir, host: HostFacts, s: PluginSettings): Promise<string> {
  const conf = m.config();
  const lines = [`Configuration: ${conf.path}` + (existsSync(conf.path) ? "" : " (missing: run «openclaw mimirsynth setup», or set MIMIRSYNTH_* variables)")];
  if (!(conf.get("url") && conf.get("brain"))) return [...lines, "Not configured: url and brain are missing."].join("\n");
  lines.push(`Server: ${conf.get("url")} · brain: ${conf.get("brain")}`);
  lines.push(...(await who(m, "Recall token", conf.get("token"))));
  if (conf.get("write_token")) lines.push(...(await who(m, "Write token", conf.get("write_token"))));
  lines.push(
    `Recall before each prompt: ${conf.get("recall") ? "on" : "off"} (up to ${conf.get("max_chars")} characters, ${conf.get("timeout")} s) · ` +
      `what changed at session start: ${conf.get("news") ? "on" : "off"}`,
  );
  lines.push(
    s.conversations
      ? "With other people (group chats, other senders): on — they can get what the brain knows"
      : "With other people (group chats, other senders): off — only your own conversations see the brain",
  );
  if (host.conversationAccess === false) {
    lines.push(`OpenClaw has not granted this plugin conversation access, so there is no recall and no capture. Grant it with:\n  ${GRANT}`);
  }
  if (host.promptInjection === false) lines.push("OpenClaw blocks this plugin's prompt injection (hooks.allowPromptInjection is false): no recall.");
  if (host.memorySlot && host.memorySlot !== "memory-core") lines.push(`OpenClaw's memory slot: ${host.memorySlot} (it may inject memory too)`);
  const mode = conf.captureMode();
  lines.push(`Capture of what each session learned: ${mode}` + (mode === "off" ? " (nothing about the sessions is written or sent)" : ""));
  if (mode !== "off") {
    const recs = m.store().all();
    lines.push(`  sessions recorded on this machine: ${recs.length}; drafts waiting: ${recs.filter((r) => capture.isDraft(r)).length}`);
  }
  return lines.join("\n");
}

function answered(e: ApiError | null, url: string): string {
  return e ? `MimirSynth answered ${e.status}: ${e.detail}` : `Cannot reach MimirSynth at ${url}.`;
}

/** Recall on demand, with more results than before each prompt. */
export async function search(m: Mimir, query: string, cwd?: string | null): Promise<{ ok: boolean; text: string }> {
  const q = query.trim();
  if (!q) return { ok: false, text: "Say what to look for." };
  const conf = m.config(cwd);
  if (!conf.configured()) return { ok: false, text: "MimirSynth is not configured: run «openclaw mimirsynth setup»." };
  const { value, error } = await failOpen(() =>
    m.client(cwd).recall(q, { facts: 12, chunks: 6, maxChars: 12000, timeout: Math.max(conf.get("timeout"), 15) }),
  );
  if (!value) return { ok: false, text: answered(error, conf.get("url")) };
  return { ok: true, text: String(value.context ?? "").trim() || "MimirSynth has nothing on that." };
}

/** A memory the agent or the person chose to write, redacted, as one proposal with the write token. */
export async function remember(m: Mimir, title: string, content: string, confidence?: number | null, cwd?: string | null): Promise<{ ok: boolean; text: string; id?: unknown; status?: unknown }> {
  if (!title.trim() || !content.trim()) return { ok: false, text: "A memory needs a title and a content." };
  const conf = m.config(cwd);
  if (!(conf.get("url") && conf.get("brain") && (conf.get("write_token") || conf.get("token")))) {
    return { ok: false, text: "MimirSynth is not configured: run «openclaw mimirsynth setup»." };
  }
  const { value, error } = await failOpen(() => m.client(cwd).remember(title, content, { confidence: confidence ?? null, sourceDescription: SOURCE }));
  if (!value) return { ok: false, text: answered(error, conf.get("url")) };
  const pending = value.status === "pending" ? " (waiting for a curator)" : "";
  return { ok: true, text: `Proposal #${String(value.id)}: ${String(value.status)}${pending}`, id: value.id, status: value.status };
}

function when(seconds: unknown): string {
  const d = new Date(Number(seconds || 0) * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** The sessions the capture recorded and has not sent (capture = draft), each as the proposal it would become. */
export function drafts(m: Mimir): string {
  const ds = m.store().all().filter((r) => capture.isDraft(r));
  if (!ds.length) return "No drafts waiting.";
  const conf = m.config();
  return ds
    .map((r) => {
      const p = capture.proposal(r, AGENT, SOURCE, conf.get("capture_confidence"));
      return `=== ${r.session} · ${when(r.started)}\n${String(p.name)}\n\n${String(p.body)}`;
    })
    .join("\n\n");
}

export async function sendDraft(m: Mimir, session: string): Promise<{ ok: boolean; text: string }> {
  const store = m.store();
  const rec = store.all().find((r) => r.session === session && capture.isDraft(r));
  if (!rec) return { ok: false, text: "No such draft." };
  const { value, error } = await failOpen(() => capture.send(m.client(rec.cwd ?? null), store, rec, AGENT, SOURCE));
  if (!value) return { ok: false, text: answered(error, m.config().get("url")) };
  return { ok: true, text: `Proposal #${String(value.id)}: ${String(value.status)}` };
}

export function dropDraft(m: Mimir, session: string): string {
  m.store().drop(session);
  return "Forgotten.";
}

export const SETUP_HINT =
  "Tokens never go through a chat. On the machine where OpenClaw's Gateway runs, run «openclaw mimirsynth setup» in a terminal: " +
  "it asks for the MimirSynth URL, the brain, a reader token for recall and, optionally, a contributor token to propose (hidden), " +
  "and the capture mode, and writes ~/.config/mimirsynth/config.json readable only by you. Every MimirSynth integration on that " +
  "machine reads the same file.";

export const CHAT_HELP = [
  "MimirSynth commands:",
  "/mimirsynth status — connection, brain, tokens, capture",
  "/mimirsynth search <what to look for> — recall on demand",
  "/mimirsynth drafts — the sessions the capture keeps for review",
  "/mimirsynth send-draft <session> · /mimirsynth drop-draft <session>",
  "/mimirsynth setup — how to configure it",
  "To propose a memory, ask the agent to remember it: it uses the mimirsynth_remember tool, and the proposal waits for a curator.",
].join("\n");

/** The chat command `/mimirsynth <subcommand> …`. */
export async function chat(m: Mimir, args: string, host: HostFacts, s: PluginSettings): Promise<string> {
  const [sub = "", ...rest] = args.trim().split(/\s+/);
  const tail = args.trim().slice(sub.length).trim();
  switch (sub.toLowerCase()) {
    case "status":
      return status(m, host, s);
    case "search":
      return (await search(m, tail)).text;
    case "drafts":
      return drafts(m);
    case "send-draft":
      return rest[0] ? (await sendDraft(m, rest[0])).text : "Say which draft: /mimirsynth send-draft <session>.";
    case "drop-draft":
      return rest[0] ? dropDraft(m, rest[0]) : "Say which draft: /mimirsynth drop-draft <session>.";
    case "setup":
      return SETUP_HINT;
    default:
      return CHAT_HELP;
  }
}
