export type PlatformType = 'standalone' | 'telegram'

export interface Platform {
  readonly type: PlatformType
  init(): Promise<void>
  isReady(): boolean
  getTheme(): 'light' | 'dark'
  setHeaderColor(color: string): void
  hapticFeedback(type: 'light' | 'medium' | 'heavy'): void
  showAlert(message: string): Promise<void>
  showConfirm(message: string): Promise<boolean>
  close(): void
}
