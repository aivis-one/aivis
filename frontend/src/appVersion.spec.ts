import { describe, expect, it } from 'vitest'
import { DEFAULT_APP_VERSION, resolveAppVersion } from './appVersion'

describe('the version the cabinet shows', () => {
  it('is the build tag, not the package version', () => {
    expect(DEFAULT_APP_VERSION).toBe('cabinets-1.5')
    expect(resolveAppVersion(undefined)).toBe('cabinets-1.5')
    expect(resolveAppVersion('')).toBe('cabinets-1.5')
    expect(resolveAppVersion('   ')).toBe('cabinets-1.5')
  })

  it('takes the VITE_APP_VERSION of a build for another tag', () => {
    expect(resolveAppVersion('cabinets-1.6')).toBe('cabinets-1.6')
  })

  it('reaches the bundle: the tests are built with the default tag', () => {
    expect(__APP_VERSION__).toBe(DEFAULT_APP_VERSION)
  })
})
