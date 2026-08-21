// =============================================================================
// The kit's form controls and CButton
// =============================================================================
//
// Every assertion here corresponds to a defect that was actually found in this
// codebase, not to a generic checklist:
//
//   * CSelect carried no attribute pass-through, so an aria-label written on it
//     landed on the wrapper <div> and named nothing. The one remedy a reader
//     reaches for was a silent no-op.
//   * CButton replaced its slot with a spinner while loading, leaving the
//     button with no accessible name at all.
//   * A visible label is not an accessible name unless it is ASSOCIATED; these
//     three controls pair label and control through useId().
//
// A regression in any of these is invisible on screen, which is exactly why it
// needs a test rather than an eye.
// =============================================================================

import { describe, it, expect } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import CInput from './CInput.vue'
import CSelect from './CSelect.vue'
import CTextarea from './CTextarea.vue'
import CButton from './CButton.vue'

const OPTIONS = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
]

describe('label ↔ control pairing', () => {
  it.each([
    ['CInput', CInput, {}, 'input'],
    ['CTextarea', CTextarea, {}, 'textarea'],
    ['CSelect', CSelect, { options: OPTIONS }, 'select'],
  ])('%s associates its label with the control by id', (_name, Comp, extra, tag) => {
    const w = mount(Comp as never, { props: { label: 'Full name', ...extra } as never })
    const label = w.find('label')
    const control = w.find(tag)
    expect(label.exists()).toBe(true)
    expect(control.attributes('id')).toBeTruthy()
    expect(label.attributes('for')).toBe(control.attributes('id'))
  })

  it.each([
    ['CInput', CInput, {}],
    ['CTextarea', CTextarea, {}],
    ['CSelect', CSelect, { options: OPTIONS }],
  ])('%s gives two instances on ONE page different ids', (_name, Comp, extra) => {
    // useId() must be unique per instance; duplicate ids would silently point
    // every label at the first control on the page.
    // ⚠ Two separate mount() calls are two separate Vue APPS, and useId's
    // counter is per-app -- both legitimately produce "v-0". That is not the
    // product's situation, which has one app. So both controls are mounted
    // inside ONE wrapper, which is the case that actually matters.
    const Wrapper = defineComponent({
      components: { Comp: Comp as never },
      setup: () => () =>
        h('div', [
          h(Comp as never, { label: 'x', ...extra }),
          h(Comp as never, { label: 'y', ...extra }),
        ]),
    })
    const w = mount(Wrapper)
    const ids = w.findAll('label').map((l) => l.attributes('for'))
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBeTruthy()
    expect(ids[0]).not.toBe(ids[1])
  })
})

describe('attribute pass-through reaches the control, not the wrapper', () => {
  it.each([
    ['CInput', CInput, {}, 'input'],
    ['CTextarea', CTextarea, {}, 'textarea'],
    ['CSelect', CSelect, { options: OPTIONS }, 'select'],
  ])('%s puts aria-label on the %s', (_name, Comp, extra, tag) => {
    const w = mount(Comp as never, {
      props: { ...extra } as never,
      attrs: { 'aria-label': 'Search' },
    })
    expect(w.find(tag).attributes('aria-label')).toBe('Search')
    // and NOT on the group wrapper, where it would name nothing
    expect(w.find('.c-input-group').attributes('aria-label')).toBeUndefined()
  })

  it.each([
    ['CInput', CInput, {}, 'input'],
    ['CTextarea', CTextarea, {}, 'textarea'],
    ['CSelect', CSelect, { options: OPTIONS }, 'select'],
  ])('%s passes disabled to the %s', (_name, Comp, extra, tag) => {
    const w = mount(Comp as never, { props: { ...extra } as never, attrs: { disabled: true } })
    expect(w.find(tag).attributes('disabled')).toBeDefined()
  })

  it.each([
    ['CInput', CInput, {}],
    ['CTextarea', CTextarea, {}],
    ['CSelect', CSelect, { options: OPTIONS }],
  ])('%s keeps class on the root so a consumer can position the group', (_name, Comp, extra) => {
    const w = mount(Comp as never, { props: { ...extra } as never, attrs: { class: 'my-spacing' } })
    expect(w.find('.c-input-group').classes()).toContain('my-spacing')
  })
})

describe('value model', () => {
  it('CInput emits update:modelValue on input', async () => {
    const w = mount(CInput, { props: { modelValue: '' } })
    const el = w.find('input')
    ;(el.element as HTMLInputElement).value = 'hello'
    await el.trigger('input')
    expect(w.emitted('update:modelValue')![0]).toEqual(['hello'])
  })

  it('CTextarea emits update:modelValue on input', async () => {
    const w = mount(CTextarea, { props: { modelValue: '' } })
    const el = w.find('textarea')
    ;(el.element as HTMLTextAreaElement).value = 'body'
    await el.trigger('input')
    expect(w.emitted('update:modelValue')![0]).toEqual(['body'])
  })

  it('CSelect emits update:modelValue on change', async () => {
    const w = mount(CSelect, { props: { modelValue: '', options: OPTIONS } })
    const el = w.find('select')
    ;(el.element as HTMLSelectElement).value = 'b'
    await el.trigger('change')
    expect(w.emitted('update:modelValue')![0]).toEqual(['b'])
  })

  it('CSelect renders every option', () => {
    const w = mount(CSelect, { props: { modelValue: '', options: OPTIONS } })
    const texts = w.findAll('option').map((o) => o.text())
    expect(texts).toContain('Alpha')
    expect(texts).toContain('Beta')
  })
})

describe('CButton', () => {
  it('keeps its accessible name while loading', () => {
    // The spinner used to REPLACE the slot, leaving no name at all.
    const w = mount(CButton, { props: { loading: true }, slots: { default: 'Load more' } })
    expect(w.text()).toContain('Load more')
  })

  it('marks itself busy and disabled while loading', () => {
    const w = mount(CButton, { props: { loading: true }, slots: { default: 'Load more' } })
    expect(w.attributes('aria-busy')).toBe('true')
    expect(w.attributes('disabled')).toBeDefined()
  })

  it('is not busy when idle', () => {
    const w = mount(CButton, { slots: { default: 'Save' } })
    expect(w.attributes('aria-busy')).toBeUndefined()
    expect(w.attributes('disabled')).toBeUndefined()
    expect(w.text()).toContain('Save')
  })

  it('applies the variant class', () => {
    const w = mount(CButton, { props: { variant: 'danger' }, slots: { default: 'Delete' } })
    expect(w.classes()).toContain('c-btn--danger')
  })

  it('is a real <button>, so Enter and Space come from the platform', () => {
    const w = mount(CButton, { slots: { default: 'Save' } })
    expect(w.element.tagName).toBe('BUTTON')
  })
})
