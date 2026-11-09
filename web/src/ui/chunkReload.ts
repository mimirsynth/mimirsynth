// A screen whose code (a chunk with a hash in its name) fails to load usually means MimirSynth was updated: the page still runs the
// previous version, whose chunks the new image no longer has (#429). Reloading gets the new version. Without React or the DOM, so
// `node --test` covers it (scripts/chunkReload.test.mjs). Only erasable TypeScript here: Node strips the types to run it.

/** What each browser and bundler says when a dynamic import or a preloaded file of the build cannot be fetched. */
const CHUNK_ERRORS = [
  /Failed to fetch dynamically imported module/i,    // Chromium
  /error loading dynamically imported module/i,      // Firefox
  /Importing a module script failed/i,               // Safari
  /Loading (CSS )?chunk [^\s]+ failed/i,             // webpack-style wording
  /Unable to preload CSS/i,                          // Vite's preload of a chunk's CSS
];

/** True for an error that says a chunk of the build could not be loaded, whatever wraps it (Vite's `vite:preloadError` passes it in
 *  `payload`). Anything else is an ordinary failure of the screen. */
export function isChunkLoadError(error: unknown): boolean {
  const e = error as { message?: unknown; payload?: unknown; name?: unknown } | null | undefined;
  if (!e) return false;
  if (e.payload !== undefined && e.payload !== error && isChunkLoadError(e.payload)) return true;
  const text = typeof error === "string" ? error : typeof e.message === "string" ? e.message : "";
  return CHUNK_ERRORS.some((re) => re.test(text));
}

export const RELOAD_KEY = "mimirsynth.chunk-reload";
/** A reload within this time of the previous one is not tried again: the new page failed too, so reloading would only loop. */
export const RELOAD_WINDOW_MS = 60_000;

export type ReloadStore = { getItem(key: string): string | null; setItem(key: string, value: string): void };

/** Reloads the page once for a chunk that failed to load, and says whether it did. A second failure within RELOAD_WINDOW_MS of that
 *  reload does not reload again: the caller shows «MimirSynth was updated» with a Reload button instead. The time of the reload is kept
 *  in sessionStorage, so it survives the reload and is per tab. Without storage (a private window that refuses it) it never reloads by
 *  itself, since nothing could stop a loop. */
export function reloadOnce(store: ReloadStore | null | undefined, now: number, reload: () => void): boolean {
  if (!store) return false;
  try {
    const last = Number(store.getItem(RELOAD_KEY));
    if (last && now - last >= 0 && now - last < RELOAD_WINDOW_MS) return false;
    store.setItem(RELOAD_KEY, String(now));
  } catch {
    return false;
  }
  reload();
  return true;
}

/** The browser's sessionStorage, or null where reading it throws. */
export function sessionStore(): ReloadStore | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

/** For a chunk that failed to load: reload this tab once, guarded against a loop. */
export function reloadForUpdate(): boolean {
  return reloadOnce(sessionStore(), Date.now(), () => window.location.reload());
}
