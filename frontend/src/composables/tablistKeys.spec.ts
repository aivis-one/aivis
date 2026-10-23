// The keys of a tab strip: Left and Right move and choose, Home and End go to the
// ends, a wrap goes round, a disabled tab is skipped, any other key is left alone.

import { describe, it, expect, afterEach } from 'vitest'
import { onTablistKeydown } from './tablistKeys'

function strip(disabledMiddle = false): { tabs: HTMLElement[]; clicks: number[] } {
  document.body.innerHTML = ''
  const list = document.createElement('div')
  list.setAttribute('role', 'tablist')
  list.addEventListener('keydown', onTablistKeydown)
  const clicks: number[] = []
  const tabs = [0, 1, 2].map((i) => {
    const b = document.createElement('button')
    b.setAttribute('role', 'tab')
    if (disabledMiddle && i === 1) b.disabled = true
    b.addEventListener('click', () => clicks.push(i))
    list.appendChild(b)
    return b
  })
  document.body.appendChild(list)
  return { tabs, clicks }
}

function press(el: HTMLElement, key: string): KeyboardEvent {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  el.dispatchEvent(e)
  return e
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('onTablistKeydown', () => {
  it('moves to the next tab, focuses it and chooses it', () => {
    const { tabs, clicks } = strip()
    tabs[0].focus()
    press(tabs[0], 'ArrowRight')
    expect(document.activeElement).toBe(tabs[1])
    expect(clicks).toEqual([1])
  })

  it('goes round at the ends', () => {
    const { tabs, clicks } = strip()
    press(tabs[2], 'ArrowRight')
    press(tabs[0], 'ArrowLeft')
    expect(clicks).toEqual([0, 2])
  })

  it('Home and End go to the ends', () => {
    const { tabs, clicks } = strip()
    press(tabs[1], 'End')
    press(tabs[1], 'Home')
    expect(clicks).toEqual([2, 0])
  })

  it('skips a disabled tab', () => {
    const { tabs, clicks } = strip(true)
    press(tabs[0], 'ArrowRight')
    expect(clicks).toEqual([2])
  })

  it('leaves every other key alone', () => {
    const { tabs, clicks } = strip()
    const e = press(tabs[0], 'a')
    expect(e.defaultPrevented).toBe(false)
    expect(clicks).toEqual([])
  })
})
