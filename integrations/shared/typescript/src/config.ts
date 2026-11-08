// The configuration contract every MimirSynth agent integration shares (docs/AGENT_CLIENT.md): the TypeScript port of
// integrations/shared/python/mimirsynth_agent/config.py. Both pass integrations/shared/contract/cases.json.
//
// One file, ~/.config/mimirsynth/config.json (or the path in MIMIRSYNTH_CONFIG), serves every agent. A value is looked up, first hit
// wins, in: the environment variable MIMIRSYNTH_<KEY>; the entry of `projects` whose folder holds the working directory (the deepest);
// the top level of the file; the default. An empty value counts as not given; a value that cannot be read falls back to the default.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve, sep } from "node:path";

export const ENV_PREFIX = "MIMIRSYNTH_";
export const PATH_ENV = "MIMIRSYNTH_CONFIG";
export const CAPTURE_MODES = ["off", "draft", "send"] as const;
export type CaptureMode = (typeof CAPTURE_MODES)[number];
export const CAPTURE_ALIASES: Record<string, CaptureMode> = { drafts: "draft", auto: "send" };

export interface Values {
  url: string;
  brain: string;
  token: string;
  write_token: string;
  timeout: number;
  max_chars: number;
  recall: boolean;
  news: boolean;
  capture: CaptureMode;
  capture_confidence: number;
}
export type Key = keyof Values;
export type Source = "env" | "project" | "file" | "default";
export type Env = Record<string, string | undefined>;

export const DEFAULTS: Readonly<Values> = Object.freeze({
  url: "",
  brain: "",
  token: "",
  write_token: "",
  timeout: 4,
  max_chars: 4000,
  recall: true,
  news: true,
  capture: "off",
  capture_confidence: 0.3,
});
export const KEYS = Object.keys(DEFAULTS) as Key[];
const FALSE = ["0", "false", "off", "no"];
const INTEGERS: ReadonlySet<string> = new Set(["max_chars"]);
const INT = /^\s*[+-]?\d+\s*$/;
const FLOAT = /^\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\s*$/;
const VALID: Record<string, (n: number) => boolean> = {
  timeout: (n) => n > 0,
  max_chars: (n) => n > 0,
  capture_confidence: (n) => n >= 0 && n <= 1,
};

function expandHome(p: string): string {
  return p === "~" || p.startsWith("~/") || p.startsWith("~\\") ? join(homedir(), p.slice(1)) : p;
}

export function defaultPath(): string {
  return join(homedir(), ".config", "mimirsynth", "config.json");
}

/** The file: MIMIRSYNTH_CONFIG when set, otherwise ~/.config/mimirsynth/config.json (on every system, Windows included). */
export function configPath(env: Env = process.env): string {
  const p = (env[PATH_ENV] ?? "").trim();
  return p ? expandHome(p) : defaultPath();
}

/** The file's JSON object; {} when it is missing, unreadable or not an object. */
export function readFile(path: string): Record<string, unknown> {
  try {
    const data: unknown = JSON.parse(readFileSync(path, "utf8"));
    return data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function norm(p: string): string {
  const abs = resolve(expandHome(p));
  return process.platform === "win32" ? abs.toLowerCase() : abs;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

/** The entry of `projects` whose folder is `cwd` or holds it; the deepest one wins. */
export function projectEntry(data: Record<string, unknown>, cwd?: string | null): Record<string, unknown> {
  const projects = data.projects;
  if (!cwd || !isObject(projects)) return {};
  const here = norm(cwd);
  let best: Record<string, unknown> = {};
  let depth = -1;
  for (const [root, entry] of Object.entries(projects)) {
    if (!root.trim() || !isObject(entry)) continue;
    const r = norm(root.trim());
    const inside = here === r || here.startsWith(r.replace(/[\\/]+$/, "") + sep);
    if (inside && r.length > depth) {
      best = entry;
      depth = r.length;
    }
  }
  return best;
}

function given(v: unknown): boolean {
  return v !== undefined && v !== null && !(typeof v === "string" && !v.trim());
}

/** `value` read as the type of `key`'s default; the default when it is not given or cannot be read. */
export function coerce<K extends Key>(key: K, value: unknown): Values[K];
export function coerce(key: string, value: unknown): unknown;
export function coerce(key: string, value: unknown): unknown {
  const d = (DEFAULTS as unknown as Record<string, unknown>)[key] ?? "";
  if (!given(value)) return d;
  if (key === "capture") {
    let m = typeof value === "string" ? value.trim().toLowerCase() : "";
    m = CAPTURE_ALIASES[m] ?? m;
    return (CAPTURE_MODES as readonly string[]).includes(m) ? m : "off";
  }
  if (typeof d === "boolean") {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") return !FALSE.includes(value.trim().toLowerCase());
    return d;
  }
  if (typeof d === "number") {
    const integer = INTEGERS.has(key);
    let n: number;
    if (typeof value === "number") n = value;
    else if (typeof value === "string" && (integer ? INT : FLOAT).test(value)) n = Number(value.trim());
    else return d;
    if (!Number.isFinite(n)) return d;
    if (integer) n = Math.trunc(n);
    return (VALID[key] ?? (() => true))(n) ? n : d;
  }
  if (typeof value === "string") return value.trim();
  if (typeof value === "number") return String(value);
  return d;
}

export interface ConfigOptions {
  /** The file; by default configPath(env). */
  path?: string;
  /** The environment; by default process.env. */
  env?: Env;
  /** The working directory, for `projects`. */
  cwd?: string | null;
}

/** The configuration as one agent sees it from one working directory. Read once when built: build another to see changes. */
export class Config {
  readonly env: Env;
  readonly path: string;
  readonly file: Record<string, unknown>;
  readonly cwd: string | null;
  readonly project: Record<string, unknown>;

  constructor(opts: ConfigOptions = {}) {
    this.env = { ...(opts.env ?? process.env) };
    this.path = opts.path ?? configPath(this.env);
    this.file = readFile(this.path);
    this.cwd = opts.cwd ? String(opts.cwd) : null;
    this.project = projectEntry(this.file, this.cwd);
  }

  /** [raw value, where it came from]. */
  lookup(key: string): [unknown, Source] {
    const k = key.toLowerCase();
    const v = this.env[ENV_PREFIX + k.toUpperCase()];
    if (given(v)) return [v, "env"];
    if (k !== "projects") {
      if (given(this.project[k])) return [this.project[k], "project"];
      if (given(this.file[k])) return [this.file[k], "file"];
    }
    return [undefined, "default"];
  }

  get<K extends Key>(key: K): Values[K] {
    return coerce(key, this.lookup(key)[0]);
  }

  source(key: string): Source {
    return this.lookup(key)[1];
  }

  captureMode(): CaptureMode {
    return this.get("capture");
  }

  /** Enough to recall: a server, a brain and a token. */
  configured(): boolean {
    return !!(this.get("url") && this.get("brain") && this.get("token"));
  }

  values(): Values {
    return Object.fromEntries(KEYS.map((k) => [k, this.get(k)])) as unknown as Values;
  }
}

export function load(opts: ConfigOptions = {}): Config {
  return new Config(opts);
}

