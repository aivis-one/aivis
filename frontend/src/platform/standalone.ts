import type { Platform } from './types'

export class StandalonePlatform implements Platform {
  readonly type = 'standalone' as const

  async init(): Promise<void> {
    // Standalone needs no initialization
  }

  isReady(): boolean {
    return true
  }

  getTheme(): 'light' | 'dark' {
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark'
    }
    return 'light'
  }

  setHeaderColor(color: string): void {
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) {
      meta.setAttribute('content', color)
    }
  }

  hapticFeedback(_type: 'light' | 'medium' | 'heavy'): void {
    // No haptic feedback in browser
  }

  async showAlert(message: string): Promise<void> {
    window.alert(message)
  }

  async showConfirm(message: string): Promise<boolean> {
    return window.confirm(message)
  }

  close(): void {
    window.close()
  }
}
