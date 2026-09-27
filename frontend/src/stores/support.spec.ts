// =============================================================================
// stores/support -- ONE PRESS OF SEND, ONE Idempotency-Key (H23 P-112)
// =============================================================================
//
// comms stores a message once per key. The store mints the key when the
// person presses send and keeps it with the draft until comms confirms,
// so a retry after a failure or a timeout goes out under the SAME key and
// comms answers with the message it already has. A new key per HTTP
// attempt would store a second message and ping a second time.
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/support', () => ({
  sendSupportMessage: vi.fn(),
  replyToStaffSupportThread: vi.fn(),
}))

import { sendSupportMessage, replyToStaffSupportThread } from '@/api/support'
import { useSupportStore } from './support'

const send = vi.mocked(sendSupportMessage)
const reply = vi.mocked(replyToStaffSupportThread)
const MESSAGE = { id: 'm1', thread_id: 't1', sender: 'u1', body: 'hi', created_at: null }

function keysOf(mock: typeof send | typeof reply, keyIndex: number): string[] {
  return mock.mock.calls.map((call) => call[keyIndex] as string)
}

describe('support store -- the Idempotency-Key of a message', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    send.mockReset()
    reply.mockReset()
  })

  it('reuses the key when the same text is retried after a failure', async () => {
    const store = useSupportStore()
    send.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce(MESSAGE)

    await store.sendMessage('hi')
    await store.sendMessage('hi')

    const keys = keysOf(send, 1)
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
  })

  it('mints a new key for another text, and after a confirmed send', async () => {
    const store = useSupportStore()
    send.mockRejectedValueOnce(new Error('timeout')).mockResolvedValue(MESSAGE)

    await store.sendMessage('hi')
    await store.sendMessage('hello') // edited after the failure: another message
    await store.sendMessage('hello') // confirmed above: a new message

    const keys = keysOf(send, 1)
    expect(new Set(keys).size).toBe(3)
  })

  it('does not send twice for a press while the first is in flight', async () => {
    const store = useSupportStore()
    let release: (value: typeof MESSAGE) => void = () => {}
    send.mockReturnValueOnce(new Promise((resolve) => (release = resolve)))

    const first = store.sendMessage('hi')
    await store.sendMessage('hi')
    release(MESSAGE)
    await first

    expect(send).toHaveBeenCalledTimes(1)
  })

  it('keeps one pending key per thread on the operator side', async () => {
    const store = useSupportStore()
    reply.mockRejectedValueOnce(new Error('timeout')).mockResolvedValue(MESSAGE)

    await store.replyToThread('t1', 'on it')
    await store.replyToThread('t1', 'on it')

    const keys = keysOf(reply, 2)
    expect(keys[1]).toBe(keys[0])
  })
})
