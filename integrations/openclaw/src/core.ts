// What the plugin's hooks, tools and commands share, on top of the shared client library (integrations/shared/typescript, bundled
// into dist/index.js when the package is built): the configuration as one session sees it, the client, the local session records of
// the optional capture, and the rule on which turns may see the brain.
import { capture, Client, Config, fetchTransport, type Transport } from "../../shared/typescript/src/index.ts";

export const PLUGIN_ID = "mimirsynth";
export const AGENT = "OpenClaw"; // how a captured session's proposal names the agent, for people
export const SOURCE = "openclaw"; // and for machines (source_description «openclaw session», the state folder)
export const SEARCH_TOOL = "mimirsynth_search";
export const REMEMBER_TOOL = "mimirsynth_remember";

/** What tests (and nothing else) replace: the environment, the configuration file, the transport and the folder of the records. */
export interface Options {
  env?: Record<string, string | undefined>;
  path?: string;
  transport?: Transport;
  stateDir?: string;
}

/** The plugin's own settings, in OpenClaw's `plugins.entries.mimirsynth.config`. Everything else is the shared configuration. */
export interface PluginSettings {
  /** Recall, news, tools and capture also in turns with other people (group chats, other senders). Off by default. */
  conversations: boolean;
}

export function settings(raw: unknown): PluginSettings {
  const o = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  return { conversations: o.conversations === true };
}

export interface MemoryAudienceLike {
  kind?: string;
}

/** A turn may see the brain when it is the owner's own (or the host does not say whose it is), or when `conversations` is on. A turn
 * with other people has a `conversation` audience; incognito sessions never see it. */
export function allowed(s: PluginSettings, audience: MemoryAudienceLike | undefined, sessionKey?: string): boolean {
  if (incognito(sessionKey)) return false;
  return s.conversations || audience?.kind !== "conversation";
}

const INCOGNITO = /^agent:[^:]+:(?:dashboard|subagent|internal-session-effects):incognito-[^:]+$/u;

/** OpenClaw's process-only sessions, which keep nothing (the host's own test, copied to avoid importing its runtime). */
export function incognito(sessionKey?: string): boolean {
  const k = (sessionKey ?? "").trim().toLowerCase();
  return !!k && INCOGNITO.test(k);
}

export class Mimir {
  readonly opts: Options;

  constructor(opts: Options = {}) {
    this.opts = opts;
  }

  /** The configuration as of now, for a working directory (`projects`): the file is read again each time, so a change applies at once. */
  config(cwd?: string | null): Config {
    return new Config({ env: this.opts.env, path: this.opts.path, cwd: cwd ?? null });
  }

  client(cwd?: string | null): Client {
    return new Client(this.config(cwd), this.opts.transport ?? fetchTransport);
  }

  /** The capture's records: ~/.config/mimirsynth/state/openclaw/sessions, next to the configuration file. */
  store(): capture.Sessions {
    return new capture.Sessions(this.opts.stateDir ?? capture.defaultDir(SOURCE, this.config().path));
  }
}

/** Runs tasks with the same key one after another, so two hooks of one session never write its record at once. */
export class Serial {
  private tails = new Map<string, Promise<unknown>>();

  run<T>(key: string, task: () => Promise<T>): Promise<T> {
    const prev = this.tails.get(key) ?? Promise.resolve();
    const next = prev.then(task, task);
    const tail = next.catch(() => undefined);
    this.tails.set(key, tail);
    void tail.then(() => {
      if (this.tails.get(key) === tail) this.tails.delete(key);
    });
    return next;
  }
}
