import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Live } from '../types'

const live = atom({ plugin: 'mimirsynth', key: 'live' } as const, {
  phase: 'idle',
  brain: null,
  role: null,
  action: null,
} as Live)

const BLOCK = /<mimirsynth-memory brain="([^"]*)">([\s\S]*?)<\/mimirsynth-memory>/
// The model's last line when a recalled fact shaped its answer, as `mimir.CREDIT` asks for it (`mimir.CREDIT_LINE` there):
// up to 3 spaces (4 make a code line), an optional quote mark, and markdown the model may wrap the label in.
const CREDIT = /^ {0,3}[`*]*(?:>\s*)?[`*]*\s*◉\s*\**MimirSynth\**:\s*(.+)$/u
// control and format (invisible, bidi) characters, as `mimir.clean` drops them
const CONTROL = /[\p{Cc}\p{Cf}\u2028\u2029]/gu

/** The answer without its credit line, and the line's note as plain text; null when the text does not end with one. */
export function splitCredit(text: string): { body: string; note: string } | null {
  const lines = text.replace(/\s+$/u, '').split('\n')
  const m = CREDIT.exec(lines[lines.length - 1] ?? '')
  const note = (m?.[1] ?? '').replace(CONTROL, '').replace(/[`*]+/g, '').trim()
  if (!note) return null
  return { body: lines.slice(0, -1).join('\n').replace(/\s+$/u, ''), note }
}

/** The folder of a path written with `/` or `\` (Windows), `.` for a bare file name: what Python's `Path.parent` gives. */
export function dirOf(path: string): string {
  const i = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  return i < 0 ? '.' : i === 0 ? path.slice(0, 1) : path.slice(0, i)
}

async function readJson($: EngineInterface, path: string): Promise<Record<string, unknown>> {
  try {
    const v: unknown = JSON.parse(await $.fs.read(path))
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

// The shared configuration, as `config_path` in the scripts finds it: MIMIRSYNTH_CONFIG (a leading ~ expanded), else
// ~/.config/mimirsynth/config.json. Null when it cannot be told (no HOME nor USERPROFILE): nothing is read from a guessed path.
async function configPath($: EngineInterface): Promise<string | null> {
  // Python's Path.home(): USERPROFILE on Windows, HOME elsewhere
  const [h, u] = [await $.env.get('HOME'), await $.env.get('USERPROFILE')]
  const home = (((await $.env.get('OS')) === 'Windows_NT' ? u || h : h || u) ?? '').trim() || null
  const set = (await $.env.get('MIMIRSYNTH_CONFIG'))?.trim()
  if (set) return /^~([/\\]|$)/.test(set) ? (home ? home + set.slice(1) : null) : set
  return home ? `${home}/.config/mimirsynth/config.json` : null
}

// What hook.py wrote for this session (`mimir.status`): brain, role, health and the last action.
async function status($: EngineInterface, sid: string): Promise<Record<string, unknown>> {
  const conf = await configPath($)
  return conf ? readJson($, `${dirOf(conf)}/status/${sid}.json`) : {}
}

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const phaseOf = (health: unknown): Live['phase'] => (health && health !== 'ok' ? 'error' : 'done')

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    const s = await status($, await $.session.id())
    await update($, live, (): Live => ({
      phase: s.health ? phaseOf(s.health) : 'idle',
      brain: str(s.brain),
      role: str(s.role),
      action: str(s.action),
    }))
    return r
  })

  on('classic.UserPromptSubmit', async ($, e, next) => {
    await update($, live, (l): Live => ({ ...l, phase: 'recalling' }))
    const r = await next(e)
    const ctx = ('additionalContext' in r ? r.additionalContext ?? [] : []).join('\n')
    const m = BLOCK.exec(ctx)
    const s = await status($, e.session_id)
    const phase = phaseOf(s.health)
    await update($, live, l => ({
      phase,
      brain: str(s.brain) ?? m?.[1] ?? l.brain,
      role: str(s.role) ?? l.role,
      action: str(s.action) ?? l.action,
    }))
    return r
  }).catch(async ($, e, next) => {
    // A failure of ours never blocks the prompt: the hooks beneath decide (replayed if already run).
    await update($, live, (l): Live => ({ ...l, phase: 'idle' }))
    return next(e)
  })

  // The credit line the model ends an answer with is drawn under it as a quote: a rule down its left edge, the mark and the
  // note, dimmer than the answer. Elsewhere (Remote Control's apps) it stays a markdown quote inside the answer.
  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (e.props.isSummary || (e.surface !== 'desktop' && e.surface !== 'terminal')) return next(e)
    const split = splitCredit(e.props.text)
    if (!split) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const answer = split.body ? await next({ ...e, props: { ...e.props, text: split.body } }) : null
    return (
      <Box flexDirection="column">
        {answer}
        <Box flexDirection="row" marginTop={1}>
          <Box width={1} flexShrink={0} backgroundColor="gray" />
          <Text>  </Text>
          <Text color="magenta">◉ </Text>
          <Text dimColor>{split.note}</Text>
        </Box>
      </Box>
    )
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    const l = await read($, live)
    if (l.phase !== 'recalling') return next(e)
    return next({ ...e, props: { ...e.props, message: `${e.props.message ?? e.props.word} · recalling` } })
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const l = await read($, live)
    if (e.props.hasSurvey || !l.brain) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const dot = l.phase === 'error' ? 'red' : l.phase === 'recalling' ? 'yellow' : 'green'
    const what = l.phase === 'recalling' ? 'recalling…' : l.action
    return (
      <Box>
        <Text color={dot}>● </Text>
        <Text bold>mimirsynth</Text>
        <Text dimColor>
          {' · '}
          {l.brain}
          {l.role ? ` · ${l.role}` : ''}
          {what ? ` · ${what}` : ''}
        </Text>
      </Box>
    )
  })
}
