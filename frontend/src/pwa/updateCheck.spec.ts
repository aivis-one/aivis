// installUpdateCheck -- H22, P-110. The tab asks for a new worker on arrival:
// after a route change and when it becomes visible again. What the worker
// does with an update is tested in swUpdate.spec.ts.
import { describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

import { installUpdateCheck } from './updateCheck'

function fakeRouter() {
  const hooks: Array<() => void> = []
  const router = { afterEach: (hook: () => void) => hooks.push(hook) } as unknown as Router
  return { router, navigate: () => hooks.forEach((hook) => hook()), hooks }
}

function fakeDoc() {
  const listeners: Array<() => void> = []
  const doc = {
    visibilityState: 'visible' as DocumentVisibilityState,
    addEventListener: (type: string, fn: () => void) => {
      if (type === 'visibilitychange') listeners.push(fn)
    },
  }
  const show = (state: DocumentVisibilityState) => {
    doc.visibilityState = state
    listeners.forEach((fn) => fn())
  }
  return { doc: doc as unknown as Document, show }
}

function fakeNav(registration: { update: () => Promise<unknown> } | undefined) {
  const getRegistration = vi.fn(() => Promise.resolve(registration))
  return {
    nav: { serviceWorker: { getRegistration } } as unknown as Navigator,
    getRegistration,
  }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('installUpdateCheck', () => {
  it('asks for an update after every route change -- no throttle', async () => {
    const update = vi.fn(() => Promise.resolve())
    const { nav } = fakeNav({ update })
    const { router, navigate } = fakeRouter()
    installUpdateCheck(router, nav, fakeDoc().doc)

    navigate()
    navigate()
    await settle()
    expect(update).toHaveBeenCalledTimes(2)
  })

  it('asks when the tab becomes visible, and not when it is hidden', async () => {
    const update = vi.fn(() => Promise.resolve())
    const { nav } = fakeNav({ update })
    const { doc, show } = fakeDoc()
    installUpdateCheck(fakeRouter().router, nav, doc)

    show('hidden')
    await settle()
    expect(update).not.toHaveBeenCalled()
    show('visible')
    await settle()
    expect(update).toHaveBeenCalledTimes(1)
  })

  it('does nothing before the injected registration exists', async () => {
    const { nav, getRegistration } = fakeNav(undefined)
    const { router, navigate } = fakeRouter()
    installUpdateCheck(router, nav, fakeDoc().doc)

    navigate()
    await settle()
    expect(getRegistration).toHaveBeenCalledTimes(1)
  })

  it('drops a failed check (offline) instead of raising it', async () => {
    const update = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))
    const { nav } = fakeNav({ update })
    const { router, navigate } = fakeRouter()
    const unhandled = vi.fn()
    process.on('unhandledRejection', unhandled)
    try {
      installUpdateCheck(router, nav, fakeDoc().doc)
      navigate()
      await settle()
      await settle()
      expect(update).toHaveBeenCalledTimes(1)
      expect(unhandled).not.toHaveBeenCalled()
    } finally {
      process.off('unhandledRejection', unhandled)
    }
  })

  it('installs nothing in a browser without service workers', () => {
    const { router, hooks } = fakeRouter()
    installUpdateCheck(router, {} as Navigator, fakeDoc().doc)
    expect(hooks).toHaveLength(0)
  })
})
