// =============================================================================
// platform/telegram -- the theme events of the host
// =============================================================================

import { afterEach, describe, expect, it, vi } from 'vitest'

import { telegramPlatform } from './telegram'
import { standalonePlatform } from './standalone'

afterEach(() => {
  delete window.Telegram
})

describe('onThemeChanged', () => {
  it('calls back with the colour scheme of the host when Telegram fires themeChanged, and stops on request', () => {
    const handlers: Array<() => void> = []
    const webApp = {
      colorScheme: 'dark',
      onEvent: vi.fn((_name: string, cb: () => void) => handlers.push(cb)),
      offEvent: vi.fn(),
    }
    window.Telegram = { WebApp: webApp as never }
    const seen: string[] = []
    const stop = telegramPlatform.onThemeChanged((theme) => seen.push(theme))
    expect(webApp.onEvent).toHaveBeenCalledWith('themeChanged', expect.any(Function))
    handlers[0]!()
    webApp.colorScheme = 'light'
    handlers[0]!()
    expect(seen).toEqual(['dark', 'light'])
    stop()
    expect(webApp.offEvent).toHaveBeenCalledWith('themeChanged', handlers[0])
  })

  it('does not throw on a client without the events', () => {
    window.Telegram = { WebApp: { colorScheme: 'light' } as never }
    expect(() => telegramPlatform.onThemeChanged(() => undefined)()).not.toThrow()
  })

  it('is a no-op in the browser', () => {
    const cb = vi.fn()
    standalonePlatform.onThemeChanged(cb)()
    expect(cb).not.toHaveBeenCalled()
  })
})
