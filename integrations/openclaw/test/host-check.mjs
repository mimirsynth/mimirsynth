// Checks what a real OpenClaw registered for the plugin: the JSON of `openclaw plugins inspect mimirsynth --runtime --json`, read from
// the file given as the first argument. Run by .github/workflows/plugin-openclaw.yml after installing the packed plugin with
// conversation access granted.
import { readFileSync } from "node:fs";

const report = JSON.parse(readFileSync(process.argv[2], "utf8"));
const plugin = report.plugin ?? {};
const problems = [];
const expect = (ok, what) => ok || problems.push(what);

expect(plugin.id === "mimirsynth", `plugin id is ${plugin.id}`);
expect(plugin.status === "loaded", `status is ${plugin.status}`);
expect(!plugin.kind, "the plugin must not take the exclusive memory slot");
for (const tool of ["mimirsynth_search", "mimirsynth_remember"]) expect(plugin.toolNames?.includes(tool), `tool ${tool} is not registered`);
expect(plugin.commands?.includes("mimirsynth"), "the chat command /mimirsynth is not registered");
expect(plugin.cliCommands?.includes("mimirsynth"), "the CLI command `openclaw mimirsynth` is not registered");
const hooks = (report.typedHooks ?? []).map((h) => h.name);
for (const hook of ["session_start", "before_prompt_build", "after_tool_call", "agent_end", "session_end"]) expect(hooks.includes(hook), `hook ${hook} is not registered (got ${hooks.join(", ")})`);
const errors = (report.diagnostics ?? []).filter((d) => d.pluginId === "mimirsynth" && d.level !== "info");
expect(errors.length === 0, `diagnostics: ${errors.map((d) => d.message).join("; ")}`);

if (problems.length) {
  console.error(problems.map((p) => `- ${p}`).join("\n"));
  process.exit(1);
}
console.log(`OpenClaw loaded mimirsynth ${plugin.version}: tools ${plugin.toolNames.join(", ")}; hooks ${hooks.join(", ")}`);
