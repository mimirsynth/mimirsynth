import { expect, test } from 'claude-code/testing'

import { dirOf, isOn, noteOf } from './register'

test('the config folder is found as Python finds it, with / or \\ and for a bare file name', () => {
  expect(dirOf('/home/x/.config/mimirsynth/config.json')).toBe('/home/x/.config/mimirsynth')
  expect(dirOf('C:\\Users\\x\\mimir\\config.json')).toBe('C:\\Users\\x\\mimir')
  expect(dirOf('config.json')).toBe('.')
  expect(dirOf('/config.json')).toBe('/')
})

test('explain is off for every value the scripts read as off', () => {
  for (const v of [false, 0, '0', 'false', 'OFF', ' no ']) expect(isOn(v)).toBe(false)
  for (const v of [undefined, true, 1, 'on', 'yes']) expect(isOn(v)).toBe(true)
})

test('the judge reply becomes one clean line, or nothing when it names no fact', () => {
  expect(noteOf('NONE')).toBe(null)
  expect(noteOf('**NONE**.')).toBe(null)
  expect(noteOf('  \n`NONE`\n')).toBe(null)
  expect(noteOf('')).toBe(null)
  expect(noteOf('Port 4000 answered it.\nSecond line')).toBe('Port 4000 answered it.')
  expect(noteOf('a\u0007b\u202ec')).toBe('abc')
  expect(noteOf('x'.repeat(500))?.length).toBe(300)
})
