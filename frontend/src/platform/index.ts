// =============================================================================
// CBSHOME Frontend -- Platform Auto-Detection
// =============================================================================
//
// Detects runtime environment by checking window.Telegram?.WebApp.
// Exports a singleton Platform instance used throughout the app.
// =============================================================================

import type { Platform } from '@/platform/types'
import { telegramPlatform } from '@/platform/telegram'
import { standalonePlatform } from '@/platform/standalone'

function detectPlatform(): Platform {
  if (window.Telegram?.WebApp) {
    return telegramPlatform
  }
  return standalonePlatform
}

export const platform: Platform = detectPlatform()
