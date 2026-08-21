// =============================================================================
// CCheckbox -- THE KEYBOARD CONTRACT
// =============================================================================
//
// These are the assertions the browser harness structurally cannot make: it
// does not deliver key events to the page. CCheckbox was rewritten from a
// <div @click> onto a real <input type="checkbox"> precisely so the keyboard
// works, and that rewrite shipped on a code read. This is the check.
//
// Every test here was watched to FAIL before it was kept -- an assertion that
// has never failed has not been shown to assert anything.
// =============================================================================

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CCheckbox from './CCheckbox.vue'

describe('CCheckbox — structure', () => {
  it('renders a real checkbox input, not a div with a click handler', () => {
    const w = mount(CCheckbox, { props: { modelValue: false, label: 'Marketing' } })
    const input = w.find('input[type="checkbox"]')
    expect(input.exists()).toBe(true)
  })

  it('is NOT hidden with display:none or visibility:hidden', () => {
    // Both remove the control from the focus order and the accessibility tree,
    // which reproduces the original defect while looking fixed.
    const w = mount(CCheckbox, { props: { modelValue: false, label: 'x' } })
    const style = (w.find('input').element as HTMLElement).style
    expect(style.display).not.toBe('none')
    expect(style.visibility).not.toBe('hidden')
  })

  it('takes its accessible name from the wrapping label', () => {
    const w = mount(CCheckbox, { props: { modelValue: false, label: 'Marketing consent' } })
    const label = w.find('label')
    expect(label.exists()).toBe(true)
    expect(label.element.contains(w.find('input').element)).toBe(true)
    expect(label.text()).toContain('Marketing consent')
  })

  it('reflects modelValue in the input, not only in the drawn box', () => {
    const w = mount(CCheckbox, { props: { modelValue: true, label: 'x' } })
    expect((w.find('input').element as HTMLInputElement).checked).toBe(true)
  })
})

describe('CCheckbox — keyboard', () => {
  it('emits update:modelValue when activated', async () => {
    const w = mount(CCheckbox, { props: { modelValue: false, label: 'x' } })
    const input = w.find('input')
    ;(input.element as HTMLInputElement).checked = true
    await input.trigger('change')
    expect(w.emitted('update:modelValue')).toBeTruthy()
    expect(w.emitted('update:modelValue')![0]).toEqual([true])
  })

  it('emits false when unchecking', async () => {
    const w = mount(CCheckbox, { props: { modelValue: true, label: 'x' } })
    const input = w.find('input')
    ;(input.element as HTMLInputElement).checked = false
    await input.trigger('change')
    expect(w.emitted('update:modelValue')![0]).toEqual([false])
  })

  it('does not drift from the model when the parent rejects the change', async () => {
    // StaffUsersView binds :model-value one-way and updates through an API
    // call. A native checkbox flips its own `checked` on activation regardless,
    // so without the re-assert the input and the drawn box disagree. This was
    // measured happening before the guard was added.
    const w = mount(CCheckbox, { props: { modelValue: false, label: 'x' } })
    const input = w.find('input')
    ;(input.element as HTMLInputElement).checked = true
    await input.trigger('change')
    await w.vm.$nextTick()
    await w.vm.$nextTick()
    expect((input.element as HTMLInputElement).checked).toBe(false)
  })

  it('is not removed from the tab order', () => {
    // NOTE ON WHAT THIS CAN AND CANNOT SAY. In a real browser an enabled
    // <input type="checkbox"> with no tabindex attribute reports tabIndex 0 and
    // is tab-reachable; measured live on the stand, it is 0. happy-dom returns
    // -1 for any element with no explicit tabindex, so asserting tabIndex >= 0
    // here fails on the ENVIRONMENT, not on the component -- it did, which is
    // how this note came to exist.
    // What this environment CAN answer is the part we could get wrong: that the
    // control is a native enabled input and nothing has pushed it out of the
    // tab order with an explicit negative tabindex.
    const w = mount(CCheckbox, { props: { modelValue: false, label: 'x' } })
    const input = w.find('input').element as HTMLInputElement
    expect(input.tagName).toBe('INPUT')
    expect(input.hasAttribute('disabled')).toBe(false)
    expect(input.getAttribute('tabindex')).toBeNull()
  })
})

describe('CCheckbox — attribute pass-through', () => {
  it('puts a fallthrough attribute on the control, not on the wrapper', () => {
    const w = mount(CCheckbox, {
      props: { modelValue: false, label: 'x' },
      attrs: { 'aria-describedby': 'hint-1', name: 'consent' },
    })
    const input = w.find('input')
    expect(input.attributes('aria-describedby')).toBe('hint-1')
    expect(input.attributes('name')).toBe('consent')
    expect(w.find('label').attributes('aria-describedby')).toBeUndefined()
  })

  it('keeps class on the root so a consumer can still position the group', () => {
    const w = mount(CCheckbox, {
      props: { modelValue: false, label: 'x' },
      attrs: { class: 'my-spacing' },
    })
    expect(w.find('label').classes()).toContain('my-spacing')
  })
})
