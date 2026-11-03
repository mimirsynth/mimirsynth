// Translation catalogues in fragments: a catalogue `name.json` plus the files a pull request adds in `name/*.json`, so two PRs that
// add texts never touch the same lines. The fragments are merged into the catalogue when a version is released (`--consolidate`).
import fs from "node:fs";
import path from "node:path";

/** The folder that holds the fragments of a catalogue: its path without `.json` (`en.json` → `en/`). */
export const fragmentsDir = (file) => file.replace(/\.json$/, "");

const fragmentFiles = (file) => {
  const dir = fragmentsDir(file);
  return fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => f.endsWith(".json")).sort().map((f) => path.join(dir, f)) : [];
};

const eolOf = (file) => (fs.existsSync(file) && fs.readFileSync(file, "utf8").includes("\r\n") ? "\r\n" : "\n");

const write = (file, entries, eol) => {
  const sorted = Object.fromEntries(Object.keys(entries).sort().map((k) => [k, entries[k]]));
  fs.writeFileSync(file, JSON.stringify(sorted, null, 1).replace(/\n/g, eol) + eol);
};

/** Reads a catalogue and its fragments. `problems` lists what the check must reject: a file out of alphabetical order, a key
 *  defined in two files, a file that is not valid JSON. */
export function readCatalog(file) {
  const merged = {};
  const owner = {};
  const problems = [];
  const files = [];
  for (const f of [file, ...fragmentFiles(file)]) {
    let entries;
    try { entries = JSON.parse(fs.readFileSync(f, "utf8")); } catch (e) { problems.push(`${f}: no es un JSON válido (${e.message})`); continue; }
    const keys = Object.keys(entries);
    files.push(f);
    if (keys.some((k, i) => k !== [...keys].sort()[i])) problems.push(`${f} no está en orden alfabético: ejecuta «node scripts/i18n.mjs --sort».`);
    for (const k of keys) {
      if (k in owner) problems.push(`la clave ${JSON.stringify(k)} está en ${owner[k]} y en ${f}`);
      else { owner[k] = f; merged[k] = entries[k]; }
    }
  }
  return { merged, files, problems };
}

/** Puts every file of the catalogue (the catalogue and each fragment) in alphabetical order. */
export function sortCatalog(file) {
  for (const f of [file, ...fragmentFiles(file)]) write(f, JSON.parse(fs.readFileSync(f, "utf8")), eolOf(f));
}

/** Merges the fragments into the catalogue, sorted, and removes them. Refuses while a key is in two files. */
export function consolidate(file) {
  const { merged, problems } = readCatalog(file);
  const clash = problems.filter((p) => p.startsWith("la clave"));
  if (clash.length) throw new Error(clash.join("\n"));
  const parts = fragmentFiles(file);
  write(file, merged, eolOf(file));
  for (const f of parts) fs.rmSync(f);
  return { keys: Object.keys(merged).length, fragments: parts.length };
}
