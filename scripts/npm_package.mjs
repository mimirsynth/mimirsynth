#!/usr/bin/env node
// The agent plugins published to npm (integrations/opencode, integrations/openclaw) are a package npm would publish as it is: what CI
// checks on every pull request and the release checks again right before `npm publish` (.github/workflows/release.yml).
//
//   node scripts/npm_package.mjs integrations/opencode [integrations/openclaw …]
//
// For each folder, with its dependencies installed (`npm ci`), it runs `npm pack --dry-run` (which builds it through `prepack`) and fails
// when:
// - the name is not in the @mimirsynth scope, or the version is not a semantic version;
// - `repository` does not point at this repository and this folder: `npm publish --provenance` refuses a package whose repository is
//   not the one the workflow runs in;
// - a file that package.json points at (main, exports, bin, and for OpenClaw its extensions and openclaw.plugin.json) or the README is
//   not in the package, or sources and tests are.
// Node's standard library only.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPOSITORY = "git+https://github.com/mimirsynth/mimirsynth.git";
const SEMVER = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$/;

/** Every file path a package.json value points at: a string, or the strings inside an object or array (exports conditions, bin). */
function targets(value) {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(targets);
  if (value && typeof value === "object") return Object.values(value).flatMap(targets);
  return [];
}

const normal = (p) => path.posix.normalize(p.replaceAll("\\", "/")).replace(/^\.\//, "");

/** Why the package in `folder` is not fit to publish, one line per problem (empty when it is). */
export function problems(folder, pkg, files) {
  const out = [];
  if (!/^@mimirsynth\/[a-z0-9][a-z0-9._-]*$/.test(pkg.name ?? "")) out.push(`name ${JSON.stringify(pkg.name)} is not in the @mimirsynth scope`);
  if (!SEMVER.test(pkg.version ?? "")) out.push(`version ${JSON.stringify(pkg.version)} is not a semantic version`);
  if (!pkg.license) out.push("no license");
  const repo = pkg.repository ?? {};
  if (repo.url !== REPOSITORY) out.push(`repository.url is ${JSON.stringify(repo.url)}, not ${REPOSITORY} (npm publish --provenance needs it)`);
  if (repo.directory !== folder) out.push(`repository.directory is ${JSON.stringify(repo.directory)}, not ${folder}`);

  const packed = new Set(files.map(normal));
  const needed = [
    "package.json",
    "README.md",
    ...targets(pkg.main),
    ...targets(pkg.exports),
    ...targets(pkg.bin),
    ...(pkg.openclaw ? ["openclaw.plugin.json", ...targets(pkg.openclaw.extensions), ...targets(pkg.openclaw.runtimeExtensions)] : []),
  ];
  for (const f of new Set(needed.map(normal))) if (!packed.has(f)) out.push(`${f} is not in the package`);
  for (const f of packed) if (/^(src|test)\//.test(f)) out.push(`${f}: sources and tests do not go in the package`);
  return out;
}

function check(folder) {
  const dir = path.resolve(ROOT, folder);
  const rel = path.relative(ROOT, dir).replaceAll("\\", "/");
  const pkg = JSON.parse(readFileSync(path.join(dir, "package.json"), "utf8"));
  // the build's own output goes to stderr, so stdout is only the JSON
  const json = execFileSync("npm", ["pack", "--dry-run", "--json"], { cwd: dir, encoding: "utf8", shell: process.platform === "win32", stdio: ["ignore", "pipe", "inherit"] });
  const files = JSON.parse(json)[0].files.map((f) => f.path);
  const found = problems(rel, pkg, files);
  console.log(`${pkg.name}@${pkg.version} (${rel}): ${files.length} files\n  ${files.sort().join("\n  ")}`);
  for (const p of found) console.log(`::error::${pkg.name}: ${p}`);
  return found.length === 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const folders = process.argv.slice(2);
  if (!folders.length) {
    console.error("usage: node scripts/npm_package.mjs <folder> [<folder> …]");
    process.exit(2);
  }
  const ok = folders.map(check).every(Boolean);
  process.exit(ok ? 0 : 1);
}
