// The Action menu (K26) as the cabinet draws it: the menu button pattern, its keys, and
// the one event it emits.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CActionMenu from './CActionMenu.vue'

const ITEMS = [
  { value: 'download', label: 'Download' },
  { value: 'edit', label: 'Edit' },
  { value: 'gone', label: 'Gone', disabled: true },
  { value: 'delete', label: 'Delete', danger: true },
]

function mountMenu() {
  return mount(CActionMenu, {
    props: { label: 'Actions', items: ITEMS },
    attachTo: document.body,
  })
}

describe('CActionMenu', () => {
  it('is a menu button that names its list and starts closed', () => {
    const w = mountMenu()
    const button = w.find('button.ds-menu__button')
    expect(button.attributes('aria-haspopup')).toBe('menu')
    expect(button.attributes('aria-expanded')).toBe('false')
    const list = w.find('ul[role="menu"]')
    expect(button.attributes('aria-controls')).toBe(list.attributes('id'))
    expect(list.attributes('aria-labelledby')).toBe(button.attributes('id'))
    expect(list.attributes('hidden')).toBeDefined()
    w.unmount()
  })

  it('opens on a click, focuses the first item, and a pick emits its value and closes', async () => {
    const w = mountMenu()
    await w.find('button.ds-menu__button').trigger('click')
    expect(w.find('button.ds-menu__button').attributes('aria-expanded')).toBe('true')
    expect(w.find('ul[role="menu"]').attributes('hidden')).toBeUndefined()
    const items = w.findAll('[role="menuitem"]')
    expect(document.activeElement).toBe(items[0]?.element)
    await items[1]?.trigger('click')
    expect(w.emitted('select')).toEqual([['edit']])
    expect(w.find('button.ds-menu__button').attributes('aria-expanded')).toBe('false')
    w.unmount()
  })

  it('moves with the arrow keys, skips a disabled item and wraps', async () => {
    const w = mountMenu()
    await w.find('button.ds-menu__button').trigger('keydown', { key: 'ArrowDown' })
    const items = w.findAll('[role="menuitem"]')
    expect(document.activeElement).toBe(items[0]?.element)
    await items[0]?.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1]?.element)
    await items[1]?.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[3]?.element)
    await items[3]?.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[0]?.element)
    w.unmount()
  })

  it('closes on Escape and gives the focus back to the button', async () => {
    const w = mountMenu()
    await w.find('button.ds-menu__button').trigger('click')
    await w.findAll('[role="menuitem"]')[0]?.trigger('keydown', { key: 'Escape' })
    expect(w.find('button.ds-menu__button').attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(w.find('button.ds-menu__button').element)
    w.unmount()
  })

  it('draws the icon-only trigger as a ghost icon button named by its label, with no chevron', () => {
    const w = mount(CActionMenu, {
      props: {
        label: 'Actions for Agreement',
        items: ITEMS,
        iconKey: 'more',
        iconOnly: true,
        align: 'end',
      },
    })
    const button = w.find('button.ds-menu__button')
    expect(button.classes()).toEqual(
      expect.arrayContaining(['ds-button', 'ds-button--ghost', 'ds-button--icon']),
    )
    expect(button.classes()).not.toContain('ds-button--secondary')
    expect(button.attributes('aria-label')).toBe('Actions for Agreement')
    expect(button.text()).toBe('')
    expect(button.findAll('svg')).toHaveLength(1)
    expect(w.find('.ds-menu').attributes('data-align')).toBe('end')
  })

  it('does not emit for a disabled item', async () => {
    const w = mountMenu()
    await w.find('button.ds-menu__button').trigger('click')
    await w.findAll('[role="menuitem"]')[2]?.trigger('click')
    expect(w.emitted('select')).toBeUndefined()
    w.unmount()
  })
})
