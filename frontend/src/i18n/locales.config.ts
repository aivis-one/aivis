// =============================================================================
// AIVIS.ONE Frontend -- Locales Config
// =============================================================================
//
// Single source of truth for supported UI languages.
//
// To add a new language:
//   1. Drop frontend/src/i18n/locales/<code>.json
//   2. Add one row to SUPPORTED_LOCALES below
//
// No other file in the project hard-codes the list of locales -- the
// profile picker, dynamic loader and RTL detection all derive from
// this array. A new language lights up across the whole app with no
// extra code changes.
// =============================================================================

export interface LocaleConfig {
  /** ISO 639-1 code, e.g. 'en', 'ru', 'ar'. Matches locales/<code>.json. */
  code: string
  /** Native name, shown in the profile language picker. */
  label: string
  /** Text direction applied to <html dir>. */
  dir: 'ltr' | 'rtl'
}

export const SUPPORTED_LOCALES = [
  { code: 'en', label: 'English', dir: 'ltr' },
  { code: 'ru', label: 'Русский', dir: 'ltr' },
  { code: 'de', label: 'Deutsch',  dir: 'ltr' },
  { code: 'ar', label: 'العربية',  dir: 'rtl' },
] as const satisfies readonly LocaleConfig[]

export type SupportedLocale = typeof SUPPORTED_LOCALES[number]['code']

/** Fallback when the backend has no stored language for the user. */
export const DEFAULT_LOCALE: SupportedLocale = 'en'

export function isSupportedLocale(value: string): value is SupportedLocale {
  return SUPPORTED_LOCALES.some((l) => l.code === value)
}

export function getLocaleDir(locale: SupportedLocale): 'ltr' | 'rtl' {
  return SUPPORTED_LOCALES.find((l) => l.code === locale)?.dir ?? 'ltr'
}
