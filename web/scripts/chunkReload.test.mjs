// A screen whose chunk fails to load after an update (src/ui/chunkReload.ts, issue 429): recognising the error, and reloading the page
// once without ever looping.
//   node --experimental-strip-types --test scripts/
import assert from "node:assert/strict";
import test from "node:test";
import { isChunkLoadError, RELOAD_KEY, RELOAD_WINDOW_MS, reloadOnce } from "../src/ui/chunkReload.ts";

test("a chunk that failed to load is recognised in every browser's words", () => {
  for (const message of [
    "Failed to fetch dynamically imported module: http://mimir.local/assets/Overview-DukBSKGN.js",  // Chromium, as in the issue
    "error loading dynamically imported module: http://mimir.local/assets/Overview-DukBSKGN.js",    // Firefox
    "Importing a module script failed.",                                                              // Safari
    "Loading chunk 42 failed.",
    "Loading CSS chunk Overview-DukBSKGN failed",
    "Unable to preload CSS for /assets/Overview-DukBSKGN.css",
  ]) {
    assert.equal(isChunkLoadError(new TypeError(message)), true, message);
  }
});

test("Vite's vite:preloadError carries the error in its payload", () => {
  const event = { type: "vite:preloadError", payload: new TypeError("Failed to fetch dynamically imported module: /assets/x-1.js") };
  assert.equal(isChunkLoadError(event), true);
});

test("any other failure of a screen is not taken for an update", () => {
  assert.equal(isChunkLoadError(new TypeError("Cannot read properties of undefined (reading 'map')")), false);
  assert.equal(isChunkLoadError(new Error("Failed to fetch")), false);  // the API not answering is not a new version
  assert.equal(isChunkLoadError(null), false);
  assert.equal(isChunkLoadError(undefined), false);
  assert.equal(isChunkLoadError({}), false);
});

function memory() {
  const data = new Map();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)) };
}

test("the first failure reloads the page and keeps when it did", () => {
  const store = memory();
  let reloads = 0;
  assert.equal(reloadOnce(store, 1_000_000, () => reloads++), true);
  assert.equal(reloads, 1);
  assert.equal(store.data.get(RELOAD_KEY), "1000000");
});

test("failing again right after that reload does not reload again: no loop", () => {
  const store = memory();
  let reloads = 0;
  const t0 = 1_000_000;
  reloadOnce(store, t0, () => reloads++);
  // the reloaded page fails too (the new version is broken, or the chunk really is missing): it stops and the screen offers Reload
  assert.equal(reloadOnce(store, t0 + 2_000, () => reloads++), false);
  assert.equal(reloadOnce(store, t0 + RELOAD_WINDOW_MS - 1, () => reloads++), false);
  assert.equal(reloads, 1);
});

test("a later update in the same tab reloads once more", () => {
  const store = memory();
  let reloads = 0;
  const t0 = 1_000_000;
  reloadOnce(store, t0, () => reloads++);
  assert.equal(reloadOnce(store, t0 + RELOAD_WINDOW_MS, () => reloads++), true);
  assert.equal(reloads, 2);
});

test("without storage it never reloads by itself, since nothing could stop a loop", () => {
  let reloads = 0;
  assert.equal(reloadOnce(null, 1_000_000, () => reloads++), false);
  const refusing = { getItem: () => { throw new Error("SecurityError"); }, setItem: () => { throw new Error("SecurityError"); } };
  assert.equal(reloadOnce(refusing, 1_000_000, () => reloads++), false);
  assert.equal(reloads, 0);
});

test("a stored time that is not a number, or in the future, does not block the reload", () => {
  for (const stored of ["garbage", String(5_000_000)]) {
    const store = memory();
    store.data.set(RELOAD_KEY, stored);
    let reloads = 0;
    assert.equal(reloadOnce(store, 1_000_000, () => reloads++), true, stored);
    assert.equal(reloads, 1);
  }
});
