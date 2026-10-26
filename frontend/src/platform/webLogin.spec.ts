// =============================================================================
// platform/webLogin -- the mark of a started website sign-in (H45)
// =============================================================================

import { describe, it, expect, beforeEach } from 'vitest'
import { LOGIN_MARK_KEY, newMark, rememberLoginMark, takeLoginMark } from './webLogin'

describe('the mark of a website sign-in', () => {
  beforeEach(() => localStorage.clear())

  it('is 43 base64url characters and new every time', () => {
    const a = newMark()
    const b = newMark()
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/)
    expect(b).not.toBe(a)
  })

  it('is taken once: read and removed', () => {
    rememberLoginMark({ state: 'S1', mark: 'M1' })
    expect(takeLoginMark()).toEqual({ state: 'S1', mark: 'M1' })
    expect(localStorage.getItem(LOGIN_MARK_KEY)).toBeNull()
    expect(takeLoginMark()).toBeNull()
  })

  it.each([
    ['not JSON', '{'],
    ['no state', JSON.stringify({ mark: 'M1' })],
    ['an empty mark', JSON.stringify({ state: 'S1', mark: '' })],
    ['numbers', JSON.stringify({ state: 1, mark: 2 })],
    ['null', 'null'],
  ])('reads %s as no mark, and still removes it', (_name, raw) => {
    localStorage.setItem(LOGIN_MARK_KEY, raw)
    expect(takeLoginMark()).toBeNull()
    expect(localStorage.getItem(LOGIN_MARK_KEY)).toBeNull()
  })
})
