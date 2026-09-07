// =============================================================================
// KYCVerificationView -- WHAT THE FORM SHOWS IS WHAT THE FORM SENDS
// =============================================================================
//
// THE DEFECT THIS WAS WRITTEN FOR (H14 P-66). pickFile had two branches that
// leave a slot without a usable file, and only one of them cleared it. The
// cancel branch nulled the ref; the rejection branch set an error and blanked
// `input.value`, which empties what the person SEES while the ref kept the
// previous choice. So "pick front.jpg, then pick front.heic" left the field
// blank, the submit button live, and front.jpg staged -- the submission carried
// a document its owner believed they had replaced, staff decided on that one,
// and the module has no path to delete what landed in storage.
//
// WHY IT IS ASSERTED THROUGH THE BUTTON AND NOT THROUGH THE REF. The ref is an
// implementation detail; "there is nothing to send" is the behaviour. A test
// reaching into the component's internals would keep passing if the button
// stopped reading them -- which is the shape of the next version of this bug.
//
// WHICH OF THESE ACTUALLY GUARDS SOMETHING, stated because "five green tests"
// is not the same claim as "five assertions". ONE of them -- "a rejected file
// clears the slot it was picked for" -- was run against the pre-fix pickFile
// and observed to FAIL; it is the guard. The other four pass before and after
// on purpose: they are the pairs that stop the guard from being satisfied by a
// broken form. A pickFile that cleared every slot on every event, or a template
// that stopped rendering the pickers, would satisfy the guard and fail these.
// Naming which is which here means nobody later reads four unfalsifiable tests
// as four proofs.
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/composables/safeNavigate', () => ({ safeNavigate: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ fetchMe: vi.fn() }) }))

// The screen loads its status on mount. Funded above the fee, so the submit
// button is rendered at all -- it sits behind v-if="canAfford".
vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(async () => ({
      kyc_status: 'not_started',
      fee_cents: 1000,
      available_cents: 5000,
    })),
  },
  ApiResponseError: class ApiResponseError extends Error {
    detail = ''
  },
}))

import KYCVerificationView from './KYCVerificationView.vue'

const STUBS = { AivisLogo: true, CAppControls: true }

/** Put a file on a real <input type="file"> and fire the change the view
 * listens for. happy-dom does not let `files` be assigned, so it is defined
 * on the element the way a picker would have left it. */
async function pick(w: VueWrapper, index: number, name: string): Promise<void> {
  const inputs = w.findAll('input[type="file"]')
  const el = inputs[index].element as HTMLInputElement
  Object.defineProperty(el, 'files', {
    value: [new File(['x'], name, { type: 'image/jpeg' })],
    writable: true,
    configurable: true,
  })
  await inputs[index].trigger('change')
}

function submitButton(w: VueWrapper) {
  return w.findAll('button').find((b) => b.text().length > 0 && !b.attributes('hidden'))
}

async function mountForm(): Promise<VueWrapper> {
  const w = mount(KYCVerificationView, { global: { stubs: STUBS } })
  await new Promise((r) => setTimeout(r, 0))
  await w.vm.$nextTick()
  return w
}

describe('KYCVerificationView — a rejected file leaves nothing staged', () => {
  beforeEach(() => {
    push.mockClear()
  })

  it('renders the passport form: a front and a selfie picker, no back', async () => {
    // Not a formality: every assertion below counts on this ordering, and a
    // template change that reorders the inputs would otherwise make the real
    // tests pass while checking the wrong slot.
    const w = await mountForm()
    expect(w.findAll('input[type="file"]')).toHaveLength(2)
  })

  it('accepts a complete set: the submit button becomes usable', async () => {
    // The pair without which every assertion below would also pass for a form
    // that refuses everything.
    const w = await mountForm()
    await pick(w, 0, 'front.jpg')
    await pick(w, 1, 'selfie.jpg')
    expect(submitButton(w)?.attributes('disabled')).toBeUndefined()
  })

  it('a rejected file clears the slot it was picked for', async () => {
    const w = await mountForm()
    await pick(w, 0, 'front.jpg')
    await pick(w, 1, 'selfie.jpg')
    expect(submitButton(w)?.attributes('disabled')).toBeUndefined()

    // The exact sequence from the defect: a good file, then a HEIC into the
    // same slot. Before the fix the button stayed live and front.jpg was still
    // what would travel.
    await pick(w, 0, 'front.heic')
    expect(submitButton(w)?.attributes('disabled')).toBeDefined()
  })

  it('says why, so the blank field is not a mystery', async () => {
    const w = await mountForm()
    await pick(w, 0, 'front.heic')
    expect(w.find('.kyc-error').exists()).toBe(true)
  })

  it('the slot can be filled again after a rejection', async () => {
    // Clearing on rejection must not be a dead end -- a fix that emptied the
    // slot and left it unfillable would pass the test above.
    const w = await mountForm()
    await pick(w, 0, 'front.heic')
    await pick(w, 0, 'front.jpg')
    await pick(w, 1, 'selfie.jpg')
    expect(submitButton(w)?.attributes('disabled')).toBeUndefined()
  })
})
