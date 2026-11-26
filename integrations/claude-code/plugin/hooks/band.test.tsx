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

test('without HOME the config is found under USERPROFILE, and with neither nothing is read from a guessed path', async ($, on) => {
  let home: string | undefined = undefined
  const read: string[] = []
  on('env.get', (_, e) => ({ value: e.name === 'USERPROFILE' ? home : undefined }))
  on('fs.read', (_, e) => {
    read.push(e.path)
    return { value: JSON.stringify(STATUS) }
  })
  on('classic.UserPromptSubmit', () => ({}))

  await $.classic.UserPromptSubmit({ prompt: 'a prompt long enough', session_id: 's1' })
  expect(read).toEqual([])

  home = 'C:\\Users\\x'
  await $.classic.UserPromptSubmit({ prompt: 'a prompt long enough', session_id: 's1' })
  // the engine resolves the path for the machine it runs on: on this test's Linux a `C:\` path is relative
  expect(read.length).toBe(1)
  expect(read[0]?.endsWith('C:\\Users\\x/.config/mimirsynth/status/s1.json')).toBe(true)
})

for (const surface of ['terminal', 'desktop'] as const) {
  test(`${surface}: the credit line at the end of an answer is drawn as a note under it`, async $ => {
    const text = 'Port 4000.\n\n> ◉ MimirSynth: the API port: it answered the question'
    const ui = await $.ui.mount({ plugin: 'mimirsynth', surface, component: 'AssistantMessage', props: { text, isFirstOfReply: true } as never })
    const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text)
    expect(texts).toContain('the API port: it answered the question')
    expect(texts.some(t => t.includes('> ◉ MimirSynth'))).toBe(false)
    await ui.unmount()
  })
}

test('an answer with no credit line, or a phone, keeps the answer as it is', async $ => {
  const ui = await $.ui.mount({ plugin: 'mimirsynth', surface: 'mobile', component: 'AssistantMessage', props: { text: 'x\n> ◉ MimirSynth: y', isFirstOfReply: true } as never })
  expect((await ui.findAll({ type: 'Text' })).map(t => t.text)).not.toContain('y')
  await ui.unmount()
})
