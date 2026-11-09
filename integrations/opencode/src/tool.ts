// The `tool` helper of @opencode-ai/plugin, kept here so the published package declares no dependencies. Upstream it is only
// `(input) => input` with `tool.schema = z`, but importing it puts @opencode-ai/plugin among the runtime dependencies, and with it the
// exact versions of zod and effect it pins (zod 4.1.8, and toml through effect, both with high-severity advisories that npm audit and
// Socket report against this package). build.mjs bundles this file with the zod of devDependencies instead, at a fixed version.
//
// OpenCode wraps a tool's args in an object of its own zod (4.1.8 in OpenCode 1.19.5). Validating a call runs each arg's own schema,
// so the bounds hold (a confidence of 3 is refused). The JSON Schema the model sees is made by OpenCode's zod, which does not read
// what another copy of zod registered: .describe() was already lost with the previous build, and now minimum and maximum are too.
// A zod that shares its registry and check format with this one (OpenCode on zod 4.6) gets both back with no change here.
// `schema` holds only the builders the plugin uses, so the bundle leaves out the rest of zod (its locales alone are ~700 KB).
import { number, string, type z } from "zod";
import type { ToolContext, ToolDefinition, ToolResult } from "@opencode-ai/plugin";

export function tool<Args extends z.ZodRawShape>(input: {
  description: string;
  args: Args;
  execute(args: z.infer<z.ZodObject<Args>>, context: ToolContext): Promise<ToolResult>;
}): ToolDefinition {
  return input as unknown as ToolDefinition;
}
tool.schema = { number, string };
