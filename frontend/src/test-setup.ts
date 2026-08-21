// =============================================================================
// Vitest global setup
// =============================================================================
//
// Several kit components call useI18n() (CInput's password-toggle label,
// CModal's close button, CBottomSheet's close button). Mounting them without an
// i18n instance throws, so one is installed globally for every test.
//
// The catalogue here is deliberately MINIMAL and not the product's en.json: a
// test should fail when a component stops rendering, not when a translator
// rewords a string. Keys resolve to themselves when missing, which is enough
// for structural assertions and keeps missing-key noise out of the output.
// =============================================================================

import { config } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      common: { close: 'Close', showPassword: 'Show password', hidePassword: 'Hide password' },
    },
  },
})

config.global.plugins = [i18n]
