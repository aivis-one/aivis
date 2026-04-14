// =============================================================================
// CBSHOME Frontend -- Standalone Platform (Browser PWA)
// =============================================================================
//
// Full implementation for standalone browser mode.
// Token stored in localStorage (persists across tabs/restarts).
// =============================================================================

import type { HapticStyle, Platform } from '@/platform/types'

export const standalonePlatform: Platform = {
  name: 'standalone',

  async init(): Promise<void> {
    // No SDK to initialize in browser mode.
  },

  getInitData(): string | null {
    // Standalone has no Telegram initData.
    return null
  },

  getTheme(): 'light' | 'dark' {
    const stored = localStorage.getItem('cbs-theme')
    if (stored === 'dark' || stored === 'light') return stored
    if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
    return 'light'
  },

  hapticFeedback(_style: HapticStyle): void {
    // Haptic feedback not available in browser.
  },

  showBackButton(cb: () => void): void {
    // Fallback: use browser history navigation.
    cb()
  },

  hideBackButton(): void {
    // No-op in browser mode.
  },

  close(): void {
    // Cannot close a browser tab programmatically (security restriction).
    window.history.back()
  },

  getStorageDriver() {
    return 'localStorage'
  },

  getStartParam(): string | null {
    // Standalone uses ?ref= URL param, handled in useAuth composable.
    return null
  },
}
