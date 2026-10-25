// =============================================================================
// pickThemedLogo -- WHICH LOGO A THEME SHOWS (H36 P-131)
// =============================================================================
//
// Every pair of (light logo, dark logo) presence, in both themes. The dark logo
// is taken only in the dark theme; it never stands in for a missing light logo
// in the light theme, where it may vanish on the background.
// =============================================================================

import { describe, expect, it } from 'vitest'
import { pickThemedLogo } from './useThemedLogo'

const L = 'https://files.example.org/logo.png?sig=1'
const D = 'https://files.example.org/logo-dark.png?sig=2'

describe('pickThemedLogo', () => {
  it('takes the dark logo in the dark theme when there is one', () => {
    expect(pickThemedLogo(L, D, 'dark')).toBe(D)
  })

  it('takes the ordinary logo in the light theme even when a dark one exists', () => {
    expect(pickThemedLogo(L, D, 'light')).toBe(L)
  })

  it('falls back to the ordinary logo in the dark theme without a dark one', () => {
    expect(pickThemedLogo(L, null, 'dark')).toBe(L)
    expect(pickThemedLogo(L, undefined, 'dark')).toBe(L)
  })

  it('shows nothing in the light theme when only the dark logo exists', () => {
    expect(pickThemedLogo(null, D, 'light')).toBeNull()
    expect(pickThemedLogo(undefined, D, 'light')).toBeNull()
  })

  it('shows the dark logo in the dark theme when it is the only one', () => {
    expect(pickThemedLogo(null, D, 'dark')).toBe(D)
  })

  it('shows nothing without either logo, in either theme', () => {
    expect(pickThemedLogo(null, null, 'light')).toBeNull()
    expect(pickThemedLogo(null, null, 'dark')).toBeNull()
    expect(pickThemedLogo(undefined, undefined, 'dark')).toBeNull()
  })
})
