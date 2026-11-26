import { expect, test } from 'claude-code/testing'

const STATUS = { brain: 'seismenos', role: 'contributor', health: 'ok', action: 'recall: 2 facts' }

for (const surface of ['terminal', 'desktop'] as const) {
  test(`${surface}: the band shows brain, role and the recall after a prompt`, async ($, on) => {
    on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/x' : undefined }))
    on('fs.read', (_, e) => {
      expect(e.path).toBe('/home/x/.config/mimirsynth/status/s1.json')
      return { value: JSON.stringify(STATUS) }
    })
    on('classic.UserPromptSubmit', () => ({
      additionalContext: ['<mimirsynth-memory brain="seismenos">\n## Hechos vigentes\n- LXC 200 es el nodo Ansible\n</mimirsynth-memory>'],
    }))

    await $.classic.UserPromptSubmit({ prompt: 'aplícalo también en NuVu', session_id: 's1' })

    const ui = await $.ui.mount({ plugin: 'mimirsynth', surface, component: 'AbovePrompt', props: {} as never })
    const line = (await ui.findAll({ type: 'Text' })).map(t => t.text).join('')
    expect(line).toBe('● mimirsynth · seismenos · contributor · recall: 2 facts')
    await ui.unmount()
  })
}

test('a failed recall turns the dot red, and the brain comes from the recalled block when no status file exists', async ($, on) => {
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/x' : undefined }))
  let calls = 0
  on('fs.read', () => {
    calls += 1
    if (calls === 1) throw new Error('ENOENT')
    return { value: JSON.stringify({ ...STATUS, health: 'offline', action: 'recall: offline' }) }
  })
  on('classic.UserPromptSubmit', () => ({ additionalContext: ['<mimirsynth-memory brain="other">\n- x\n</mimirsynth-memory>'] }))

  await $.classic.UserPromptSubmit({ prompt: 'first prompt here', session_id: 's1' })
  let ui = await $.ui.mount({ plugin: 'mimirsynth', surface: 'terminal', component: 'AbovePrompt', props: {} as never })
  expect((await ui.findAll({ type: 'Text' })).map(t => t.text).join('')).toBe('● mimirsynth · other')
  await ui.unmount()

  await $.classic.UserPromptSubmit({ prompt: 'second prompt here', session_id: 's1' })
  ui = await $.ui.mount({ plugin: 'mimirsynth', surface: 'terminal', component: 'AbovePrompt', props: {} as never })
  const dot = await ui.find({ type: 'Text' })
  expect(dot?.props.color).toBe('red')
  expect((await ui.findAll({ type: 'Text' })).map(t => t.text).join('')).toBe('● mimirsynth · seismenos · contributor · recall: offline')
  await ui.unmount()
})
