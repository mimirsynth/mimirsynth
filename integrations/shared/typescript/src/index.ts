// MimirSynth's shared client library for JavaScript agent integrations (docs/AGENT_CLIENT.md): the configuration contract, the calls
// to a brain, secret redaction and the optional session capture. A thin port of integrations/shared/python/mimirsynth_agent; both pass
// integrations/shared/contract/cases.json. No dependencies: Node 22.6 or later (or Bun), which run the TypeScript sources as they are.
export * as capture from "./capture.ts";
export * as secretscan from "./secretscan.ts";
export {
  ApiError,
  Client,
  failOpen,
  fetchTransport,
  MARKER,
  QUERY_MAX,
  redact,
  request,
  urlFor,
  type CallOptions,
  type Json,
  type Outcome,
  type RecallOptions,
  type RememberOptions,
  type Transport,
  type WireRequest,
  type WireResponse,
} from "./client.ts";
export {
  CAPTURE_ALIASES,
  CAPTURE_MODES,
  Config,
  configPath,
  defaultPath,
  DEFAULTS,
  KEYS,
  load,
  type CaptureMode,
  type ConfigOptions,
  type Key,
  type Values,
} from "./config.ts";

export const CONTRACT_VERSION = 1; // bumped only when the configuration contract changes in a way an integration must follow
