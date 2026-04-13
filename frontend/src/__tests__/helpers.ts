import { createI18n } from 'vue-i18n'
import { mount, type MountingOptions } from '@vue/test-utils'
import type { Component } from 'vue'

export function createTestI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: {} },
    missingWarn: false,
    fallbackWarn: false,
  })
}

export function mountWithI18n<T extends Component>(
  component: T,
  options: MountingOptions<unknown> = {},
) {
  const i18n = createTestI18n()
  return mount(component, {
    ...options,
    global: {
      ...options.global,
      plugins: [...(options.global?.plugins || []), i18n],
    },
  })
}
