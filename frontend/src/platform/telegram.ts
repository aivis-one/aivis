import type { Platform } from './types'

declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        ready(): void
        expand(): void
        close(): void
        isReady: boolean
        colorScheme: 'light' | 'dark'
        setHeaderColor(color: string): void
        showAlert(message: string, callback?: () => void): void
        showConfirm(message: string, callback?: (ok: boolean) => void): void
        HapticFeedback: {
          impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void
        }
      }
    }
  }
}

export class TelegramPlatform implements Platform {
  readonly type = 'telegram' as const

  private get webapp() {
    return window.Telegram!.WebApp
  }

  async init(): Promise<void> {
    this.webapp.ready()
    this.webapp.expand()
  }

  isReady(): boolean {
    return this.webapp.isReady
  }

  getTheme(): 'light' | 'dark' {
    return this.webapp.colorScheme
  }

  setHeaderColor(color: string): void {
    try {
      this.webapp.setHeaderColor(color)
    } catch {
      // Some SDK versions reject invalid colors
    }
  }

  hapticFeedback(type: 'light' | 'medium' | 'heavy'): void {
    try {
      this.webapp.HapticFeedback.impactOccurred(type)
    } catch {
      // Haptics not available on all devices
    }
  }

  async showAlert(message: string): Promise<void> {
    return new Promise((resolve) => {
      this.webapp.showAlert(message, () => resolve())
    })
  }

  async showConfirm(message: string): Promise<boolean> {
    return new Promise((resolve) => {
      this.webapp.showConfirm(message, (ok) => resolve(ok))
    })
  }

  close(): void {
    this.webapp.close()
  }
}
