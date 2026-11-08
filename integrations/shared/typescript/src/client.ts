// Calls to a brain's API with an API token: recall, news, whoami and proposals (docs/AGENT_CLIENT.md). The TypeScript port of
// integrations/shared/python/mimirsynth_agent/client.py.
//
// Every call has the configured timeout (4 s) and rejects: with ApiError when the server answered with an error, with anything else
// when it could not be reached. A hook must never break its agent, so it wraps calls in failOpen.
import { Config } from "./config.ts";
import { redactFindings, scan } from "./secretscan.ts";

export const QUERY_MAX = 1500; // characters of a prompt sent as a recall query
export const MARKER = "[secret removed]";

export type Json = Record<string, unknown>;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** The token is missing, expired, revoked or lacks the scope: worth telling the person, unlike a server that is away. */
  get auth(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

/** One HTTP request as the client makes it; `timeout` in seconds. */
export interface WireRequest {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
  timeout: number;
}

/** The answer: its status, the reason phrase and the raw body. */
export interface WireResponse {
  status: number;
  reason: string;
  body: string;
}

export type Transport = (req: WireRequest) => Promise<WireResponse>;

/** The default transport: fetch (Node 18 or later, Bun, Deno), aborted after the timeout. */
export const fetchTransport: Transport = async (req) => {
  const r = await fetch(req.url, {
    method: req.method,
    headers: req.headers,
    body: req.body ?? undefined,
    signal: AbortSignal.timeout(Math.max(1, Math.round(req.timeout * 1000))),
  });
  return { status: r.status, reason: r.statusText, body: await r.text() };
};

function detail(raw: string, reason: string): string {
  let d: unknown;
  try {
    const parsed: unknown = JSON.parse(raw || "{}");
    d = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Json).detail : undefined;
  } catch {
    d = undefined;
  }
  if (d === undefined || d === null || d === "") return reason;
  return typeof d === "string" ? d : JSON.stringify(d);
}

/** `{url}/api/brains/{brain}{path}`, or `{url}/api{path without one slash}` when `path` starts with `//`. */
export function urlFor(conf: Config, path: string, query: string | Record<string, string | number> = ""): string {
  const base = conf.get("url").replace(/\/+$/, "");
  const full = path.startsWith("//") ? `${base}/api${path.slice(1)}` : `${base}/api/brains/${conf.get("brain")}${path}`;
  const q = typeof query === "string" ? query : new URLSearchParams(Object.entries(query).map(([k, v]): [string, string] => [k, String(v)])).toString();
  return full + (q ? `?${q}` : "");
}

export interface CallOptions {
  body?: Json | null;
  token?: string | null;
  timeout?: number | null; // seconds; the configured one when not given
  query?: string | Record<string, string | number>;
}

/** One call. Resolves to the JSON answer ({} when empty); rejects with ApiError, with the server's message, on an HTTP error. */
export async function request(conf: Config, method: string, path: string, opts: CallOptions = {}, transport: Transport = fetchTransport): Promise<Json> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  const r = await transport({
    method,
    url: urlFor(conf, path, opts.query ?? ""),
    headers,
    body: opts.body !== undefined && opts.body !== null ? JSON.stringify(opts.body) : null,
    timeout: opts.timeout || conf.get("timeout"),
  });
  if (r.status >= 400) throw new ApiError(r.status, detail(r.body, r.reason));
  return r.body ? (JSON.parse(r.body) as Json) : {};
}

export interface Outcome<T> {
  value: T | null;
  error: ApiError | null;
}

/** Runs a call that must not break the agent: its value, the ApiError when the server answered with an error, or neither when it could
 * not be reached or anything else went wrong. Never rejects. */
export async function failOpen<T>(fn: () => Promise<T>): Promise<Outcome<T>> {
  try {
    return { value: await fn(), error: null };
  } catch (e) {
    return { value: null, error: e instanceof ApiError ? e : null };
  }
}

/** The text with everything the server's detector finds, sure or possible, replaced by a marker. By patterns: not infallible. */
export function redact(text: string | null | undefined): string {
  const t = text ?? "";
  const found = scan(t);
  return found.length ? redactFindings(t, found, MARKER, true) : t;
}

export interface RecallOptions {
  facts?: number;
  chunks?: number;
  maxChars?: number | null;
  timeout?: number | null;
}

export interface RememberOptions {
  confidence?: number | null;
  sourceDescription?: string;
  origin?: "agent" | "auto";
  timeout?: number | null;
}

/** The calls an agent integration makes, with the tokens of one configuration. */
export class Client {
  readonly conf: Config;
  readonly transport: Transport;

  constructor(conf: Config = new Config(), transport: Transport = fetchTransport) {
    this.conf = conf;
    this.transport = transport;
  }

  call(method: string, path: string, opts: CallOptions = {}): Promise<Json> {
    return request(this.conf, method, path, opts, this.transport);
  }

  writeToken(): string {
    return this.conf.get("write_token") || this.conf.get("token");
  }

  /** POST /recall with the reader token: {context, …}. maxChars defaults to the configured one. */
  recall(query: string, opts: RecallOptions = {}): Promise<Json> {
    const body = {
      query: Array.from(query ?? "").slice(0, QUERY_MAX).join(""),
      facts: opts.facts ?? 6,
      chunks: opts.chunks ?? 3,
      max_chars: Math.trunc(opts.maxChars ?? this.conf.get("max_chars")),
    };
    return this.call("POST", "/recall", { body, token: this.conf.get("token"), timeout: opts.timeout });
  }

  /** POST /news: what changed since this token last asked, {text, added, gone}. */
  news(limit = 20, maxChars = 4000): Promise<Json> {
    return this.call("POST", "/news", { token: this.conf.get("token"), query: `limit=${Math.trunc(limit)}&max_chars=${Math.trunc(maxChars)}` });
  }

  /** GET /whoami: the brain, the role, the server's version and the token's name, scopes and expiry. */
  whoami(token?: string | null): Promise<Json> {
    return this.call("GET", "/whoami", { token: token ?? this.conf.get("token") });
  }

  /** POST /proposals with the write token, as given: redact it first (see remember). */
  propose(body: Json, token?: string | null, timeout: number | null = 20): Promise<Json> {
    return this.call("POST", "/proposals", { body, token: token || this.writeToken(), timeout });
  }

  /** A memory an agent chose to write, redacted, as one proposal: {id, status} (pending with a contributor token). */
  remember(title: string, content: string, opts: RememberOptions = {}): Promise<Json> {
    const body: Json = {
      name: Array.from(redact(title)).slice(0, 255).join(""),
      body: redact(content),
      source: "text",
      source_description: opts.sourceDescription ?? "",
      origin: opts.origin ?? "agent",
    };
    if (opts.confidence !== undefined && opts.confidence !== null) body.confidence = opts.confidence;
    return this.propose(body, null, opts.timeout === undefined ? 20 : opts.timeout);
  }
}
