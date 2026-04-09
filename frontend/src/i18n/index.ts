import { createI18n } from 'vue-i18n'

import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import de from '@/i18n/locales/de.json'
import ar from '@/i18n/locales/ar.json'

export const SUPPORTED_LOCALES = ['en', 'ru', 'de', 'ar'] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

const RTL_LOCALES: readonly string[] = ['ar']

function detectLocale(): SupportedLocale {
  const stored = localStorage.getItem('cbs-lang')
  if (stored && SUPPORTED_LOCALES.includes(stored as SupportedLocale)) return stored as SupportedLocale

  const nav = navigator.language?.split('-')[0]
  if (nav && SUPPORTED_LOCALES.includes(nav as SupportedLocale)) return nav as SupportedLocale

  return 'en'
}

export function applyDir(locale: string): void {
  const dir = RTL_LOCALES.includes(locale) ? 'rtl' : 'ltr'
  document.documentElement.dir = dir
  document.documentElement.lang = locale
}

const locale = detectLocale()
applyDir(locale)

export const i18n = createI18n({
  legacy: false,
  locale,
  fallbackLocale: 'en',
  messages: { en, ru, de, ar },
})
