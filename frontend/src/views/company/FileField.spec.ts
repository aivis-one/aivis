// The File input (K30) as the cabinet draws it: a real input inside the button's label,
// the limits as text, and one item for the file the field stands for.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import FileField from './FileField.vue'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { common: { clear: 'Clear' } } },
  })
}

function mountField(props: Record<string, unknown> = {}) {
  return mount(FileField, {
    props: { label: 'Cover', buttonLabel: 'Choose file', ...props },
    global: { plugins: [makeI18n()] },
  })
}

describe('FileField', () => {
  it('draws the label, the button around a real file input and no item without a file', () => {
    const w = mountField({ accept: 'image/png', hint: 'PNG, up to 10 MB' })
    expect(w.find('.ds-field__label').text()).toBe('Cover')
    const input = w.find('label.ds-button.ds-file__pick input.ds-file__input[type="file"]')
    expect(input.exists()).toBe(true)
    expect(input.attributes('accept')).toBe('image/png')
    expect(input.attributes('aria-describedby')).toBe(w.find('.ds-field__hint').attributes('id'))
    expect(w.find('li.ds-file__item').exists()).toBe(false)
  })

  it('emits the picked file', async () => {
    const w = mountField()
    const file = new File(['x'], 'cover.png', { type: 'image/png' })
    const input = w.find('input').element as HTMLInputElement
    Object.defineProperty(input, 'files', { value: [file], configurable: true })
    await w.find('input').trigger('change')
    expect(w.emitted('select')).toEqual([[file]])
  })

  it('shows a picked file as a selected item and a stored one as done, uploading while busy', async () => {
    const file = new File(['abc'], 'a.pdf', { type: 'application/pdf' })
    const picked = mountField({ file })
    expect(picked.find('li.ds-file__item').attributes('data-state')).toBe('selected')
    expect(picked.find('.ds-file__name').text()).toBe('a.pdf')
    const stored = mountField({ current: 'b.pdf', currentMeta: '2 KB' })
    expect(stored.find('li.ds-file__item').attributes('data-state')).toBe('done')
    expect(stored.find('.ds-file__meta').text()).toBe('2 KB')
    await stored.setProps({ busy: true })
    expect(stored.find('li.ds-file__item').attributes('data-state')).toBe('uploading')
  })

  it('names its remove button after the file and emits remove', async () => {
    const w = mountField({ current: 'b.pdf', removable: true })
    const remove = w.find('button.ds-file__remove')
    expect(remove.attributes('aria-label')).toBe('Clear b.pdf')
    await remove.trigger('click')
    expect(w.emitted('remove')).toHaveLength(1)
  })
})
