// public/sw-update.js -- H22, P-110. The worker add-on runs in a service worker
// global, so it is evaluated here against a fake one: its own `self`, Cache
// Storage, clients and extendable events. The file is taken as text exactly as
// it ships and evaluated against that fake.
import { describe, expect, it, vi } from 'vitest'

// ?raw: Vite hands over the file's text, byte for byte, without evaluating it.
import SOURCE from '../../public/sw-update.js?raw'

type Listener = (event: { waitUntil: (p: Promise<unknown>) => void }) => void

interface FakeWindow {
  url: string
  navigate?: (url: string) => Promise<unknown>
}

// Cache Storage outlives a worker restart, so it is shared between instances.
function fakeCaches() {
  const stores = new Map<string, Map<string, Response>>()
  return {
    open: async (name: string) => {
      if (!stores.has(name)) stores.set(name, new Map())
      const store = stores.get(name)!
      return {
        put: async (key: string, value: Response) => void store.set(key, value),
        delete: async (key: string) => store.delete(key),
        match: async (key: string) => store.get(key),
      }
    },
  }
}

function startWorker(opts: {
  caches: ReturnType<typeof fakeCaches>
  replacesActive: boolean
  windows?: FakeWindow[]
}) {
  const listeners = new Map<string, Listener>()
  const claim = vi.fn(() => Promise.resolve())
  const self = {
    registration: { active: opts.replacesActive ? {} : null },
    caches: opts.caches,
    clients: { claim, matchAll: vi.fn(async () => opts.windows ?? []) },
    addEventListener: (type: string, fn: Listener) => listeners.set(type, fn),
  }
  new Function('self', SOURCE)(self)

  const fire = async (type: 'install' | 'activate') => {
    const waited: Promise<unknown>[] = []
    listeners.get(type)!({ waitUntil: (p) => waited.push(p) })
    await Promise.all(waited)
  }
  return { fire, claim, matchAll: self.clients.matchAll }
}

const settle = async () => {
  for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0))
}

function windowAt(url: string): FakeWindow & { navigate: ReturnType<typeof vi.fn> } {
  return { url, navigate: vi.fn(() => Promise.resolve()) }
}

describe('sw-update.js', () => {
  it('reloads every open window onto its own URL when it replaces an active worker', async () => {
    const a = windowAt('https://app.test/investor/dashboard')
    const b = windowAt('https://app.test/company/posts')
    const worker = startWorker({ caches: fakeCaches(), replacesActive: true, windows: [a, b] })

    await worker.fire('install')
    await worker.fire('activate')
    await settle()

    expect(worker.claim).toHaveBeenCalledTimes(1)
    expect(a.navigate).toHaveBeenCalledWith('https://app.test/investor/dashboard')
    expect(b.navigate).toHaveBeenCalledWith('https://app.test/company/posts')
  })

  it('reloads nothing on a first install -- there is no older build to leave', async () => {
    const a = windowAt('https://app.test/register')
    const worker = startWorker({ caches: fakeCaches(), replacesActive: false, windows: [a] })

    await worker.fire('install')
    await worker.fire('activate')
    await settle()

    expect(worker.claim).not.toHaveBeenCalled()
    expect(a.navigate).not.toHaveBeenCalled()
  })

  it('keeps the answer across a worker restart between install and activate', async () => {
    const caches = fakeCaches()
    const a = windowAt('https://app.test/')
    await startWorker({ caches, replacesActive: true, windows: [a] }).fire('install')

    // A fresh instance: nothing survives in memory, Cache Storage does.
    const restarted = startWorker({ caches, replacesActive: true, windows: [a] })
    await restarted.fire('activate')
    await settle()

    expect(a.navigate).toHaveBeenCalledTimes(1)
  })

  it('consumes the answer -- a second activation of the same install reloads nothing', async () => {
    const caches = fakeCaches()
    const a = windowAt('https://app.test/')
    const worker = startWorker({ caches, replacesActive: true, windows: [a] })

    await worker.fire('install')
    await worker.fire('activate')
    await settle()
    await startWorker({ caches, replacesActive: true, windows: [a] }).fire('activate')
    await settle()

    expect(a.navigate).toHaveBeenCalledTimes(1)
  })

  it('a first install after an unfinished update does not inherit its answer', async () => {
    const caches = fakeCaches()
    const a = windowAt('https://app.test/')
    await startWorker({ caches, replacesActive: true, windows: [a] }).fire('install')

    const fresh = startWorker({ caches, replacesActive: false, windows: [a] })
    await fresh.fire('install')
    await fresh.fire('activate')
    await settle()

    expect(a.navigate).not.toHaveBeenCalled()
  })

  it('does not hold activation on the navigations it starts', async () => {
    // A navigation is a fetch the worker answers, and fetches wait for the
    // end of activation: waiting for one inside waitUntil would never end.
    const hanging = { url: 'https://app.test/', navigate: vi.fn(() => new Promise(() => {})) }
    const worker = startWorker({ caches: fakeCaches(), replacesActive: true, windows: [hanging] })

    await worker.fire('install')
    await worker.fire('activate') // resolves although navigate never does
    await settle()

    expect(hanging.navigate).toHaveBeenCalledTimes(1)
  })

  it('one window that cannot be navigated does not stop the rest', async () => {
    const refused = {
      url: 'https://app.test/a',
      navigate: vi.fn(() => Promise.reject(new TypeError('gone'))),
    }
    const unsupported: FakeWindow = { url: 'https://app.test/b' } // no navigate at all
    const fine = windowAt('https://app.test/c')
    const worker = startWorker({
      caches: fakeCaches(),
      replacesActive: true,
      windows: [refused, unsupported, fine],
    })

    await worker.fire('install')
    await worker.fire('activate')
    await settle()

    expect(refused.navigate).toHaveBeenCalledTimes(1)
    expect(fine.navigate).toHaveBeenCalledWith('https://app.test/c')
  })

  it('an update with no open window claims and navigates nothing, without error', async () => {
    const worker = startWorker({ caches: fakeCaches(), replacesActive: true, windows: [] })

    await worker.fire('install')
    await worker.fire('activate')
    await settle()

    expect(worker.claim).toHaveBeenCalledTimes(1)
    expect(worker.matchAll).toHaveBeenCalledTimes(1)
  })
})
