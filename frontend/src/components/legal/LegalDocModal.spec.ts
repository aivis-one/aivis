// LegalDocModal -- fetches legal/<lang>/<type>.html, shows only the body, and
// closes by the close button (the document viewer, K36).

import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LegalDocModal from './LegalDocModal.vue'

const PAGE = '<html><head><title>X</title></head><body><h1>Terms</h1><p>Body text</p></body></html>'

function stubFetch(ok = true): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 404, text: async () => PAGE })
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const props = { open: true, title: 'Cabinet Terms', lang: 'en', type: 'cabinet_terms' }

describe('LegalDocModal', () => {
  it('fetches the document under the base and renders only the body', async () => {
    const fetchFn = stubFetch()
    const w = mount(LegalDocModal, { props, attachTo: document.body })
    await flushPromises()
    expect(fetchFn).toHaveBeenCalledWith(`${import.meta.env.BASE_URL}legal/en/cabinet_terms.html`)
    expect(document.body.textContent).toContain('Cabinet Terms')
    expect(document.body.querySelector('.ds-docviewer__body h1')?.textContent).toBe('Terms')
    expect(document.body.textContent).not.toContain('<title>')
    w.unmount()
  })

  it('does not fetch while closed', async () => {
    const fetchFn = stubFetch()
    const w = mount(LegalDocModal, { props: { ...props, open: false } })
    await flushPromises()
    expect(fetchFn).not.toHaveBeenCalled()
    w.unmount()
  })

  it('shows an error when the fetch fails', async () => {
    stubFetch(false)
    const w = mount(LegalDocModal, { props, attachTo: document.body })
    await flushPromises()
    expect(document.body.querySelector('.ds-alert--danger')).not.toBeNull()
    expect(document.body.querySelector('.ds-docviewer__body h1')).toBeNull()
    w.unmount()
  })

  it('emits close from the close button', async () => {
    stubFetch()
    const w = mount(LegalDocModal, { props, attachTo: document.body })
    await flushPromises()
    ;(document.body.querySelector('.ds-docviewer__actions .ds-button') as HTMLElement).click()
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })
})
