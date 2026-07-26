// =============================================================================
// AIVIS.ONE Frontend -- Platform Auto-Detection
// =============================================================================
//
// Detects runtime environment by checking window.Telegram?.WebApp.
// Exports a singleton Platform instance used throughout the app.
//
// NOTE: The Telegram SDK script (telegram-web-app.js) creates
// window.Telegram.WebApp even in a regular browser. We must also
// check initData — it's a non-empty string ONLY when running
// inside a real Telegram WebApp context.
// =============================================================================

import type { Platform } from '@/platform/types'
import { telegramPlatform } from '@/platform/telegram'
import { standalonePlatform } from '@/platform/standalone'

function detectPlatform(): Platform {
  const wa = window.Telegram?.WebApp
  if (wa && wa.initData) {
    return telegramPlatform
  }
  return standalonePlatform
}

export const platform: Platform = detectPlatform()
