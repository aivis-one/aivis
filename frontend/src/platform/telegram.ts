// =============================================================================
// AIVIS.ONE Frontend -- Telegram WebApp Platform
// =============================================================================
//
// Wraps window.Telegram.WebApp SDK. Used when the app runs inside
// Telegram as a WebApp. Token stored in sessionStorage (cleared on close).
// =============================================================================

import type { HapticStyle, Platform, TelegramWebApp } from '@/platform/types'

function getWebApp(): TelegramWebApp {
  const wa = window.Telegram?.WebApp
  if (!wa) {
    throw new Error('Telegram WebApp SDK not available')
  }
  return wa
}

// Track current BackButton callback for cleanup.
let _backButtonCb: (() => void) | null = null

export const telegramPlatform: Platform = {
  name: 'telegram',

  async init(): Promise<void> {
    const wa = getWebApp()
    wa.ready()
    wa.expand()
    wa.setHeaderColor('#1A6B6A')
    wa.setBackgroundColor('#F5F5F5')
  },

  getInitData(): string | null {
    const wa = getWebApp()
    return wa.initData || null
  },

  getTheme(): 'light' | 'dark' {
    const wa = getWebApp()
    return wa.colorScheme || 'light'
  },

  hapticFeedback(style: HapticStyle): void {
    try {
      const wa = getWebApp()
      wa.HapticFeedback.impactOccurred(style)
    } catch {
      // Silently ignore -- haptic not available on all devices.
    }
  },

  showBackButton(cb: () => void): void {
    const wa = getWebApp()
    // Remove previous callback to prevent stacking.
    if (_backButtonCb) {
      wa.BackButton.offClick(_backButtonCb)
    }
    _backButtonCb = cb
    wa.BackButton.onClick(cb)
    wa.BackButton.show()
  },

  hideBackButton(): void {
    const wa = getWebApp()
    if (_backButtonCb) {
      wa.BackButton.offClick(_backButtonCb)
      _backButtonCb = null
    }
    wa.BackButton.hide()
  },

  close(): void {
    const wa = getWebApp()
    wa.close()
  },

  getStorageDriver() {
    return 'sessionStorage'
  },

  getStartParam(): string | null {
    const wa = getWebApp()
    return wa.initDataUnsafe?.start_param || null
  },
}
