import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useToast } from '@/composables/useToast'

describe('useToast', () => {
  beforeEach(() => {
    const { clearAll } = useToast()
    clearAll()
    vi.useRealTimers()
  })

  it('starts with empty toasts array', () => {
    const { toasts } = useToast()
    expect(toasts.value).toEqual([])
  })

  it('addToast adds a toast with correct type and message', () => {
    const { toasts, addToast } = useToast()
    addToast('success', 'Item saved')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].type).toBe('success')
    expect(toasts.value[0].message).toBe('Item saved')
  })

  it('addToast returns unique IDs', () => {
    const { addToast } = useToast()
    const id1 = addToast('info', 'First')
    const id2 = addToast('info', 'Second')
    expect(id1).not.toBe(id2)
  })

  it('removeToast removes specific toast', () => {
    const { toasts, addToast, removeToast } = useToast()
    const id1 = addToast('info', 'Keep')
    const id2 = addToast('error', 'Remove')
    removeToast(id2)
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].id).toBe(id1)
  })

  it('clearAll removes all toasts', () => {
    const { toasts, addToast, clearAll } = useToast()
    addToast('info', 'First')
    addToast('error', 'Second')
    clearAll()
    expect(toasts.value).toEqual([])
  })

  it('auto-dismiss removes toast after duration', () => {
    vi.useFakeTimers()
    const { toasts, addToast } = useToast()
    addToast('success', 'Auto dismiss', 2000)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(2000)
    expect(toasts.value).toHaveLength(0)
  })

  it('duration 0 does not auto-dismiss', () => {
    vi.useFakeTimers()
    const { toasts, addToast } = useToast()
    addToast('info', 'Permanent', 0)
    vi.advanceTimersByTime(10000)
    expect(toasts.value).toHaveLength(1)
  })
})
