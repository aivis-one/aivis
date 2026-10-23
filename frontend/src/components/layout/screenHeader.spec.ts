// The screen header: one way for a screen to set what the frame's header shows.

import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useCurrentScreenHeader, useScreenHeader } from './screenHeader'
import type { ScreenHeaderSpec } from './screenHeader'

function screen(spec: ScreenHeaderSpec) {
  return defineComponent({
    setup() {
      useScreenHeader(spec)
      return () => h('div')
    },
  })
}

const reader = defineComponent({
  setup() {
    const header = useCurrentScreenHeader()
    return () => h('p', JSON.stringify({ title: header.value.title, lead: header.value.lead }))
  },
})

function current() {
  const w = mount(reader)
  const value = JSON.parse(w.text()) as { title?: string; lead?: string }
  w.unmount()
  return value
}

describe('useScreenHeader', () => {
  it('shows nothing until a screen sets it', () => {
    expect(current()).toEqual({})
  })

  it('shows the title and the lead line a screen sets, and drops them with the screen', () => {
    const w = mount(screen({ title: () => 'Portfolio', lead: 'Your holdings' }))
    expect(current()).toEqual({ title: 'Portfolio', lead: 'Your holdings' })
    w.unmount()
    expect(current()).toEqual({})
  })

  it('follows a ref the screen passes', () => {
    const title = ref('One')
    const w = mount(screen({ title }))
    expect(current().title).toBe('One')
    title.value = 'Two'
    expect(current().title).toBe('Two')
    w.unmount()
  })

  it('lets a section inside a hub override the hub, and gives the hub back when it closes', () => {
    const hub = mount(screen({ title: 'Hub' }))
    const section = mount(screen({ title: 'Section' }))
    expect(current().title).toBe('Section')
    section.unmount()
    expect(current().title).toBe('Hub')
    hub.unmount()
  })
})
