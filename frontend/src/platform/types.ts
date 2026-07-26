// =============================================================================
// AIVIS.ONE Frontend -- Platform Abstraction Types
// =============================================================================
//
// Common interface for Telegram WebApp and Standalone (browser) modes.
// 9 methods: init, getInitData, getTheme, hapticFeedback, showBackButton,
// hideBackButton, close, getStorageDriver, getStartParam.
// =============================================================================

// ---------------------------------------------------------------------------
// Platform interface
// ---------------------------------------------------------------------------

export type PlatformName = 'telegram' | 'standalone'
export type StorageDriver = 'localStorage' | 'sessionStorage'
export type HapticStyle = 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'

export interface Platform {
  readonly name: PlatformName
  init(): Promise<void>
  getInitData(): string | null
  getTheme(): 'light' | 'dark'
  hapticFeedback(style: HapticStyle): void
  showBackButton(cb: () => void): void
  hideBackButton(): void
  close(): void
  getStorageDriver(): StorageDriver
  getStartParam(): string | null
}

// ---------------------------------------------------------------------------
// Telegram WebApp SDK type declarations (subset we use)
// ---------------------------------------------------------------------------

export interface TelegramBackButton {
  show(): void
  hide(): void
  onClick(cb: () => void): void
  offClick(cb: () => void): void
}

export interface TelegramHapticFeedback {
  impactOccurred(style: string): void
}

export interface TelegramWebApp {
  ready(): void
  expand(): void
  close(): void
  setHeaderColor(color: string): void
  setBackgroundColor(color: string): void
  initData: string
  initDataUnsafe: {
    start_param?: string
    user?: {
      id: number
      first_name: string
      last_name?: string
      username?: string
      language_code?: string
    }
  }
  colorScheme: 'light' | 'dark'
  BackButton: TelegramBackButton
  HapticFeedback: TelegramHapticFeedback
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp
    }
  }
}
