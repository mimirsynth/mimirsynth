// The package's entry point for OpenCode: a plugin module ({id, server}), as OpenCode 1.x loads it from npm or from a file.
import { ID, server } from "./plugin.ts";

export default { id: ID, server };
