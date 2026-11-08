// Builds what npm publishes: dist/index.js (the plugin OpenCode loads) and dist/cli.js (the command-line tool), each one file with the
// shared client library (integrations/shared/typescript) inside, so the package needs nothing from this repository. Only
// @opencode-ai/plugin stays outside: OpenCode installs it with the plugin.
import { build } from "esbuild";
import { rmSync } from "node:fs";

rmSync(new URL("./dist", import.meta.url), { recursive: true, force: true });
const common = { bundle: true, platform: "node", format: "esm", target: "node18", external: ["@opencode-ai/plugin"], logLevel: "info" };
await build({ ...common, entryPoints: ["src/index.ts"], outfile: "dist/index.js" });
await build({ ...common, entryPoints: ["src/cli.ts"], outfile: "dist/cli.js", banner: { js: "#!/usr/bin/env node" } });
