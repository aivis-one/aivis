// The text field (K03): the hint under the control, tied to it by aria-describedby.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CInput from './CInput.vue'

function mountInput(props: Record<string, unknown> = {}) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: {} }, missingWarn: false })
  return mount(CInput, { props: { label: 'Name', ...props }, global: { plugins: [i18n] } })
}

describe('CInput hint', () => {
  it('draws no hint and no description without one', () => {
    const w = mountInput()
    expect(w.find('.ds-field__hint').exists()).toBe(false)
    expect(w.find('input').attributes('aria-describedby')).toBeUndefined()
  })

  it('draws the hint as ds-field__hint and describes the control by it', () => {
    const w = mountInput({ hint: 'As in your passport.' })
    const hint = w.find('p.ds-field__hint')
    expect(hint.text()).toBe('As in your passport.')
    expect(w.find('input').attributes('aria-describedby')).toBe(hint.attributes('id'))
  })

  it('describes the control by the hint and then the error when both stand', () => {
    const w = mountInput({ hint: 'As in your passport.', error: 'Required' })
    const hintId = w.find('.ds-field__hint').attributes('id')
    const errorId = w.find('.ds-field__error').attributes('id')
    expect(w.find('input').attributes('aria-describedby')).toBe(`${hintId} ${errorId}`)
    expect(w.find('input').attributes('aria-invalid')).toBe('true')
  })

  it('describes the control by the error alone as before', () => {
    const w = mountInput({ error: 'Required' })
    expect(w.find('input').attributes('aria-describedby')).toBe(
      w.find('.ds-field__error').attributes('id'),
    )
  })
})
