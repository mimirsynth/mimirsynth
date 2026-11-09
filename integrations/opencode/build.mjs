// Builds what npm publishes: dist/index.js (the plugin OpenCode loads) and dist/cli.js (the command-line tool), each one file with the
// shared client library (integrations/shared/typescript) and zod (src/tool.ts) inside, so the package needs nothing from this
// repository and installs no dependencies. From @opencode-ai/plugin only the types are used: it stays external and the build fails if
// a value import of it comes back, which would need it at runtime and bring the versions of zod and effect it pins.
import { build } from "esbuild";
import { readFileSync, rmSync } from "node:fs";

rmSync(new URL("./dist", import.meta.url), { recursive: true, force: true });
const common = { bundle: true, platform: "node", format: "esm", target: "node18", external: ["@opencode-ai/plugin"], logLevel: "info" };
await build({ ...common, entryPoints: ["src/index.ts"], outfile: "dist/index.js" });
await build({ ...common, entryPoints: ["src/cli.ts"], outfile: "dist/cli.js", banner: { js: "#!/usr/bin/env node" } });
for (const out of ["dist/index.js", "dist/cli.js"]) {
  if (readFileSync(new URL(out, import.meta.url), "utf8").includes("@opencode-ai/plugin")) {
    throw new Error(`${out} imports @opencode-ai/plugin at runtime; import only its types (src/tool.ts has the tool helper)`);
  }
}
