// =============================================================================
// CBSHOME Frontend -- i18n Module
// =============================================================================
//
// LAZY-LOADED LOCALES.
// Only the locale the user actually needs is fetched. Vite compiles
// each JSON into its own chunk; the main bundle contains none.
//
// LOCALE RESOLUTION.
//   1. localStorage['cbs-lang'] -- stored at login from user.language.
//      Written by setLocale().
//   2. DEFAULT_LOCALE ('en') -- anything else, including a brand new
//      device with no prior session.
// The browser language is intentionally NOT consulted.
//
// LIFECYCLE.
//   main.ts                -> await setupI18n()
//                             (resolves locale, loads JSON, applies
//                              dir/lang on <html>, sets active locale)
//   stores/auth.ts         -> setLocale(user.language)
//                             on restoreSession / login / register /
//                             telegram login. No-op if already active.
// =============================================================================

import { createI18n } from 'vue-i18n'

import {
  DEFAULT_LOCALE,
  getLocaleDir,
  isSupportedLocale,
  type SupportedLocale,
} from '@/i18n/locales.config'

const STORAGE_KEY = 'cbs-lang'

// Vite turns this into a map of lazy loaders, one per matched file.
// Only the JSON actually imported ends up in a runtime chunk.
const localeLoaders = import.meta.glob<{ default: Record<string, unknown> }>(
  './locales/*.json',
)

export const i18n = createI18n({
  legacy: false,
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  messages: {},
})

// Track already-loaded locales to keep loadLocaleMessages idempotent.
const loadedLocales = new Set<SupportedLocale>()

async function loadLocaleMessages(locale: SupportedLocale): Promise<void> {
  if (loadedLocales.has(locale)) return
  const loader = localeLoaders[`./locales/${locale}.json`]
  if (!loader) {
    throw new Error(`Locale file not found: locales/${locale}.json`)
  }
  const mod = await loader()
  i18n.global.setLocaleMessage(locale, mod.default)
  loadedLocales.add(locale)
}

function applyDir(locale: SupportedLocale): void {
  document.documentElement.dir = getLocaleDir(locale)
  document.documentElement.lang = locale
}

function readStoredLocale(): SupportedLocale {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && isSupportedLocale(stored)) return stored
  return DEFAULT_LOCALE
}

/**
 * Bootstrap i18n before the Vue app mounts.
 *
 * Resolves the initial locale from localStorage (or DEFAULT_LOCALE),
 * fetches its JSON, and applies the locale on the i18n instance and
 * on the <html> element. Must be awaited in main.ts -- an unresolved
 * setup would render with empty messages and keys would show through.
 */
export async function setupI18n(): Promise<void> {
  const locale = readStoredLocale()
  await loadLocaleMessages(locale)
  i18n.global.locale.value = locale
  applyDir(locale)
}

/**
 * Switch the UI language after the authoritative source -- the backend
 * via user.language -- becomes available.
 *
 * Called from the auth store on session establishment. No-op for
 * unsupported / empty input. Loads the target JSON once on first use,
 * then flips the active locale. Persists the choice in localStorage
 * regardless of whether it changed -- so a cold boot starts in the
 * right language even when the current locale already happens to match.
 *
 * On load failure (missing file, network error for chunk) logs an
 * error and leaves the UI on the previous locale. Never throws --
 * callers are fire-and-forget.
 */
export async function setLocale(
  locale: string | null | undefined,
): Promise<void> {
  if (!locale || !isSupportedLocale(locale)) return

  // Persist the authoritative choice up-front so the next cold boot
  // loads the right JSON, even if nothing actually switches this time
  // (current locale already matches, load fails, etc.).
  localStorage.setItem(STORAGE_KEY, locale)

  if (i18n.global.locale.value === locale) return

  try {
    await loadLocaleMessages(locale)
  } catch (err) {
    // Degrade gracefully: stay on the currently-active locale, report
    // the failure so devs can spot a missing/broken locale chunk.
    console.error(`Failed to load locale '${locale}':`, err)
    return
  }

  i18n.global.locale.value = locale
  applyDir(locale)
}
