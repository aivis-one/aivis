// =============================================================================
// MediaImageField -- A PICTURE AS A FILE (H36 P-131)
// =============================================================================
//
// Axes: a file of a refused TYPE and one over the SIZE limit never leave the
// field (a toast says why); a file that may go is emitted as it is. A stored
// picture is drawn as the item's thumb with a remove that asks first; without a
// stored picture there is no item and no remove (EMPTINESS).
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const showToast = vi.fn()
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast }) }))

import MediaImageField from './MediaImageField.vue'

const URL_ = 'https://files.example.org/logo.png?sig=1'

function mountField(props: Record<string, unknown> = {}) {
  return mount(MediaImageField, {
    attachTo: document.body,
    props: { label: 'Logo', url: null, maxBytes: 1024, ...props },
  })
}

async function pick(wrapper: ReturnType<typeof mountField>, file: File): Promise<void> {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

beforeEach(() => {
  showToast.mockReset()
  document.body.innerHTML = ''
})

describe('MediaImageField', () => {
  it('accepts only the server types, as the input says', () => {
    const w = mountField()
    expect(w.find('input[type="file"]').attributes('accept')).toBe(
      'image/png,image/jpeg,image/webp',
    )
    w.unmount()
  })

  it('emits a file that may go', async () => {
    const w = mountField()
    const file = new File(['png'], 'logo.png', { type: 'image/png' })
    await pick(w, file)
    expect(w.emitted('select')).toEqual([[file]])
    expect(showToast).not.toHaveBeenCalled()
    w.unmount()
  })

  it('keeps a file of another type and says why', async () => {
    const w = mountField()
    await pick(w, new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' }))
    expect(w.emitted('select')).toBeUndefined()
    expect(showToast).toHaveBeenCalledWith('common.media.errorType', 'error')
    w.unmount()
  })

  it('keeps a file over the limit and says why; one at the limit goes', async () => {
    const w = mountField({ maxBytes: 4 })
    await pick(w, new File(['12345'], 'big.png', { type: 'image/png' }))
    expect(w.emitted('select')).toBeUndefined()
    expect(showToast).toHaveBeenCalledWith('common.media.errorSize', 'error')
    const exact = new File(['1234'], 'ok.png', { type: 'image/png' })
    await pick(w, exact)
    expect(w.emitted('select')).toEqual([[exact]])
    w.unmount()
  })

  it('has no item and no remove without a stored picture', () => {
    const w = mountField()
    expect(w.find('li.ds-file__item').exists()).toBe(false)
    expect(w.find('.ds-file__remove').exists()).toBe(false)
    w.unmount()
  })

  it('draws a stored picture and asks before removing it', async () => {
    const w = mountField({ url: URL_ })
    expect(w.find('.ds-file__thumb img').attributes('src')).toBe(URL_)
    await w.find('.ds-file__remove').trigger('click')
    await flushPromises()
    expect(w.emitted('remove')).toBeUndefined()
    const confirm = Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find(
      (b) => b.textContent?.includes('common.media.remove'),
    ) as HTMLButtonElement
    confirm.click()
    await flushPromises()
    expect(w.emitted('remove')).toEqual([[]])
    w.unmount()
  })

  it('offers no remove to a viewer who may not change it', () => {
    const w = mountField({ url: URL_, disabled: true })
    expect(w.find('.ds-file__remove').exists()).toBe(false)
    expect(w.find('input[type="file"]').attributes('disabled')).toBeDefined()
    w.unmount()
  })
})
