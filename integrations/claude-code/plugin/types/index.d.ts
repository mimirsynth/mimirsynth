export type Live = {
  phase: 'idle' | 'recalling' | 'done' | 'error'
  brain: string | null
  role: string | null
  action: string | null
}

declare module 'claude-code' {
  interface PluginState {
    'mimirsynth': { live: Live }
  }
}
