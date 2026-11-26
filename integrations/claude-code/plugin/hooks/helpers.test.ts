import { expect, test } from 'claude-code/testing'

import { dirOf, splitCredit } from './register'

test('the config folder is found as Python finds it, with / or \\ and for a bare file name', () => {
  expect(dirOf('/home/x/.config/mimirsynth/config.json')).toBe('/home/x/.config/mimirsynth')
  expect(dirOf('C:\\Users\\x\\mimir\\config.json')).toBe('C:\\Users\\x\\mimir')
  expect(dirOf('config.json')).toBe('.')
  expect(dirOf('/config.json')).toBe('/')
})

test('the credit line is split off the end of an answer, quoted or not, and nowhere else', () => {
  expect(splitCredit('Port 4000.\n\n> ◉ MimirSynth: the API port: it answered the question\n')).toEqual({
    body: 'Port 4000.',
    note: 'the API port: it answered the question',
  })
  expect(splitCredit('◉ MimirSynth: x')).toEqual({ body: '', note: 'x' })
  expect(splitCredit('> ◉ MimirSynth: x\nmore text after it')).toBe(null)
  expect(splitCredit('An answer with no credit.')).toBe(null)
  expect(splitCredit('> ◉ MimirSynth:   ')).toBe(null)
})
