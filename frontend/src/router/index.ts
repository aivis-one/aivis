import { createI18n } from 'vue-i18n'

import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import de from '@/i18n/locales/de.json'
import ar from '@/i18n/locales/ar.json'

const RTL_LOCALES = ['ar']

function detectLocale(): string {
  const stored = localStorage.getItem('cbs-lang')
  if (stored && ['en', 'ru', 'de', 'ar'].includes(stored)) return stored

  const nav = navigator.language?.split('-')[0]
  if (nav && ['en', 'ru', 'de', 'ar'].includes(nav)) return nav

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
