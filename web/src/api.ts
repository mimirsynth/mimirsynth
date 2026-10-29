import i18n from "i18next";
import { locale, translateServer } from "./i18n";
export type Fact = {
  uuid: string; name: string; fact: string; status: "current" | "invalidated" | "future";
  valid_at: string | null; invalid_at: string | null; expired_at: string | null; created_at: string;
  source: string; target: string; source_uuid: string; target_uuid: string; episodes: string[];
};
export type TimelineEvent = Fact & { event: "learned" | "invalidated"; at: string };
export type Episode = {
  uuid: string; name: string; source: string; description: string; created_at: string; valid_at: string;
  snippet?: string; content?: string; facts: number | Fact[];
};
export type GNode = { uuid: string; name: string; labels: string[]; summary: string; degree: number; x?: number; y?: number };
export type GLink = { uuid: string; name: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; source: any; target: any };
export type GraphData = { nodes: GNode[]; links: GLink[]; truncated: boolean };
export type Overview = {
  entities: number; episodes: number; facts_total: number; facts_invalidated: number; communities: number;
  by_label: { label: string; count: number }[]; last_episode: { name: string; created_at: string } | null; first_episode_at: string | null;
};

const SCOPED = new Set(["overview", "episodes", "facts", "timeline", "graph", "vocabulary", "vocab", "docs", "query", "index", "jobs"]);

function url(path: string, params: Record<string, string | number | boolean | undefined>) {
  const { graph, ...rest } = params; // `graph` = slug del brain activo
  const qs = new URLSearchParams();
  Object.entries(rest).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)));
  const base = SCOPED.has(path.split("/")[0]) ? `/api/brains/${graph}/${path}` : `/api/${path}`;
  return `${base}${qs.toString() ? `?${qs}` : ""}`;
}

export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }

async function check(r: Response) {
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail ?? m; } catch { /* sin cuerpo */ } throw new ApiError(r.status, translateServer(m)); }
  return r.json();
}

/** El servidor responde (errores incluidos) en el idioma que tiene activo la interfaz, no en el del navegador. */
export const langHeaders = (): Record<string, string> => ({ "Accept-Language": i18n.language });

export async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
  return check(await fetch(url(path, params), { credentials: "include", headers: langHeaders() }));
}
export async function send<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown, params: Record<string, string | undefined> = {}): Promise<T> {
  return check(await fetch(url(path, params), { method, credentials: "include", headers: { "Content-Type": "application/json", ...langHeaders() }, body: body === undefined ? undefined : JSON.stringify(body) }));
}

export type Brain = { slug: string; name: string; description: string; graph_name: string; role: string };
export type Me = { id: number; name: string; email: string | null; is_admin: boolean; auth_mode: string; avatar?: string; account_url?: string; has_password?: boolean; must_change_password?: boolean; totp_enabled?: boolean; must_setup_2fa?: boolean; locale?: string };

export const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString(locale(), { dateStyle: "short", timeStyle: "short" }) : "—");
