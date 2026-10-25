// The support feed re-reads itself only while something is translating:
// every three seconds, for at most two minutes, then never again until the
// feed stops showing a translation in flight; nothing at all for a feed with
// nothing translating, and nothing after the screen is gone (H39 P-129).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import {
  TRANSLATING_LEASE_MS,
  TRANSLATING_POLL_MS,
  useTranslationPoll,
} from './useTranslationPoll'

function host(translating: { value: boolean }, refresh: () => Promise<void>) {
  let restart: () => void = () => undefined
  const Comp = defineComponent({
    setup() {
      ;({ restart } = useTranslationPoll({
        translating: () => translating.value,
        refresh,
      }))
      return () => null
    },
  })
  const wrapper = mount(Comp)
  return { wrapper, restart: () => restart() }
}

async function tick(ms: number): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms)
}

describe('useTranslationPoll', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not poll a feed with nothing in translation', async () => {
    const translating = ref(false)
    const refresh = vi.fn(async () => undefined)
    host(translating, refresh)
    await tick(TRANSLATING_POLL_MS * 5)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('re-reads every three seconds while something translates, and stops when it is done', async () => {
    const translating = ref(true)
    const refresh = vi.fn(async () => undefined)
    host(translating, refresh)
    await tick(TRANSLATING_POLL_MS)
    expect(refresh).toHaveBeenCalledTimes(1)
    await tick(TRANSLATING_POLL_MS)
    expect(refresh).toHaveBeenCalledTimes(2)
    translating.value = false
    await nextTick()
    await tick(TRANSLATING_POLL_MS * 5)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('gives up after two minutes of translating, and a restart renews the lease', async () => {
    const translating = ref(true)
    const refresh = vi.fn(async () => undefined)
    const { restart } = host(translating, refresh)
    await tick(TRANSLATING_LEASE_MS + TRANSLATING_POLL_MS * 3)
    const spent = refresh.mock.calls.length
    expect(spent).toBe(TRANSLATING_LEASE_MS / TRANSLATING_POLL_MS)
    await tick(TRANSLATING_POLL_MS * 5)
    expect(refresh).toHaveBeenCalledTimes(spent)
    restart()
    await tick(TRANSLATING_POLL_MS)
    expect(refresh).toHaveBeenCalledTimes(spent + 1)
  })

  it('a failed re-read is not the end: the next tick tries again', async () => {
    const translating = ref(true)
    const refresh = vi.fn(async () => {
      throw new Error('offline')
    })
    host(translating, refresh)
    await tick(TRANSLATING_POLL_MS * 2)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('stops when the screen is gone', async () => {
    const translating = ref(true)
    const refresh = vi.fn(async () => undefined)
    const { wrapper } = host(translating, refresh)
    wrapper.unmount()
    await tick(TRANSLATING_POLL_MS * 3)
    expect(refresh).not.toHaveBeenCalled()
  })
})
