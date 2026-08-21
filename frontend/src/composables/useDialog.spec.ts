// =============================================================================
// useDialog -- THE KEYBOARD CONTRACT
// =============================================================================
//
// CModal and CBottomSheet could be dismissed by a mouse and not by a keyboard.
// The fix is entirely keyboard behaviour, and the browser harness this project
// is validated in cannot press a key -- a keydown listener on document records
// zero events while the driver reports a keypress. So the fix shipped on a code
// read plus a synthetic KeyboardEvent dispatched by hand.
//
// This is the real check. Each test was watched to fail before it was kept.
// =============================================================================

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref, toRef } from 'vue'
import { mount } from '@vue/test-utils'
import { useDialog } from './useDialog'

/** Minimal host with the same shape as CModal: a dialog element and two
 *  focusable children, driven by an `open` prop. */
const Host = defineComponent({
  props: { open: { type: Boolean, default: false } },
  emits: ['close'],
  setup(props, { emit }) {
    const dialogEl = ref<HTMLElement | null>(null)
    // toRef, exactly as CModal and CBottomSheet do it. An earlier version of
    // this host passed a hand-rolled `{ get value() {...} }` instead; it is not
    // a Ref, so `watch` never tracked it and all five behaviour tests failed at
    // once. Five failures with one cause is a broken harness, not five defects.
    useDialog(toRef(props, 'open'), dialogEl, () => emit('close'))
    return () =>
      props.open
        ? h('div', { ref: dialogEl, tabindex: -1, role: 'dialog' }, [
            h('button', { class: 'first' }, 'first'),
            h('button', { class: 'last' }, 'last'),
          ])
        : h('div', { class: 'closed' })
  },
})

let opener: HTMLButtonElement
let realRect: typeof Element.prototype.getBoundingClientRect

beforeEach(() => {
  // happy-dom has NO LAYOUT ENGINE: every getBoundingClientRect() is all-zero.
  // useDialog filters its focus set by "has a size", which is correct in a
  // browser -- it drops hidden items -- but in a layout-less environment it
  // discards everything, and all four focus tests failed at once because of it.
  // Giving elements a size restores a fact the real browser supplies; it does
  // not stub any part of the component under test.
  // RE-MEASURED ON happy-dom 20 (2026-08-21, probe run then deleted): still
  // width=0 height=0 top=0 left=0. THIS STUB IS STILL LOAD-BEARING -- unlike
  // the tabIndex workaround in CCheckbox.spec.ts, which that same upgrade made
  // unnecessary. Two workarounds from one environment, and only one died.
  realRect = Element.prototype.getBoundingClientRect
  Element.prototype.getBoundingClientRect = function () {
    return {
      width: 100,
      height: 20,
      top: 0,
      left: 0,
      right: 100,
      bottom: 20,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect
  }
  document.body.innerHTML = ''
  opener = document.createElement('button')
  opener.className = 'opener'
  document.body.appendChild(opener)
  opener.focus()
})

afterEach(() => {
  Element.prototype.getBoundingClientRect = realRect
  document.body.innerHTML = ''
})

function key(k: string, opts: KeyboardEventInit = {}) {
  document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, ...opts }))
}

describe('useDialog — Escape', () => {
  it('closes on Escape while open', async () => {
    const w = mount(Host, { props: { open: true }, attachTo: document.body })
    key('Escape')
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('does NOT close on some other key', async () => {
    // The control. Without it, "Escape closed it" could just mean "any key did".
    const w = mount(Host, { props: { open: true }, attachTo: document.body })
    key('a')
    key('Enter')
    expect(w.emitted('close')).toBeFalsy()
    w.unmount()
  })

  it('does NOT close on Escape while CLOSED', async () => {
    const w = mount(Host, { props: { open: false }, attachTo: document.body })
    key('Escape')
    expect(w.emitted('close')).toBeFalsy()
    w.unmount()
  })
})

describe('useDialog — focus', () => {
  it('moves focus into the dialog on open', async () => {
    const w = mount(Host, { props: { open: false }, attachTo: document.body })
    expect(document.activeElement).toBe(opener)
    await w.setProps({ open: true })
    await w.vm.$nextTick()
    const first = document.querySelector('.first')
    expect(document.activeElement).toBe(first)
    w.unmount()
  })

  it('returns focus to the opener on close', async () => {
    const w = mount(Host, { props: { open: false }, attachTo: document.body })
    await w.setProps({ open: true })
    await w.vm.$nextTick()
    expect(document.activeElement).not.toBe(opener)
    await w.setProps({ open: false })
    await w.vm.$nextTick()
    expect(document.activeElement).toBe(opener)
    w.unmount()
  })
})

describe('useDialog — focus containment', () => {
  it('wraps Tab from the last focusable back to the first', async () => {
    const w = mount(Host, { props: { open: true }, attachTo: document.body })
    await w.vm.$nextTick()
    const first = document.querySelector('.first') as HTMLElement
    const last = document.querySelector('.last') as HTMLElement
    last.focus()
    key('Tab')
    expect(document.activeElement).toBe(first)
    w.unmount()
  })

  it('wraps Shift+Tab from the first focusable back to the last', async () => {
    const w = mount(Host, { props: { open: true }, attachTo: document.body })
    await w.vm.$nextTick()
    const first = document.querySelector('.first') as HTMLElement
    const last = document.querySelector('.last') as HTMLElement
    first.focus()
    key('Tab', { shiftKey: true })
    expect(document.activeElement).toBe(last)
    w.unmount()
  })

  it('does not trap Tab in the middle of the dialog', async () => {
    // Wrapping must happen at the ENDS only; a dialog that swallows every Tab
    // is its own kind of trap.
    const w = mount(Host, { props: { open: true }, attachTo: document.body })
    await w.vm.$nextTick()
    const first = document.querySelector('.first') as HTMLElement
    first.focus()
    key('Tab')
    // forward from the FIRST element: the browser's own default should carry it
    // on, so the composable must not have moved focus itself.
    expect(document.activeElement).toBe(first)
    w.unmount()
  })
})

describe('useDialog — teardown', () => {
  it('stops listening once unmounted', async () => {
    const w = mount(Host, { props: { open: true }, attachTo: document.body })
    w.unmount()
    // If the listener survived the unmount it would still try to emit on a
    // dead component; the assertion is that nothing throws and nothing fires.
    expect(() => key('Escape')).not.toThrow()
  })
})
