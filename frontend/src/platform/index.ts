import type { Platform } from './types'
import { StandalonePlatform } from './standalone'
import { TelegramPlatform } from './telegram'

let instance: Platform | null = null

export function detectPlatform(): Platform {
  if (instance) return instance

  if (window.Telegram?.WebApp) {
    instance = new TelegramPlatform()
  } else {
    instance = new StandalonePlatform()
  }

  return instance
}

export const platform = detectPlatform()

export type { Platform, PlatformType } from './types'
