// =============================================================================
// AIVIS.ONE Frontend -- re-read a support feed while a translation is on its way
// =============================================================================
//
// H39 P-129. A support message is translated by a model that comms calls
// (backend modules/support/translation.py); the translation appears in the
// feed a few seconds after the message, and nothing pushes it to the
// screen. So while the feed shows a message as "translating", the screen
// re-reads it every TRANSLATING_POLL_MS -- and only then: a feed with
// nothing in translation is not polled at all (the screens keep their
// manual refresh).
//
// THE LEASE. A translation that has not arrived in TRANSLATING_LEASE_MS
// is not going to arrive in the next three seconds either -- comms gives a
// job fifteen minutes before it calls it expired -- so after two minutes of
// "translating" the re-reads stop, and the manual refresh is the way on.
// The lease is renewed when the feed stops showing anything in
// translation: the next message sent starts a fresh two minutes.
//
// Silent by contract: `refresh` must not show a loader or an error screen
// (the stores' `silent` reads) -- the person is reading the feed while it
// runs.
// =============================================================================

import { onBeforeUnmount, watch } from 'vue'

export const TRANSLATING_POLL_MS = 3_000
export const TRANSLATING_LEASE_MS = 2 * 60_000

export interface TranslationPollOptions {
  /** True while the feed on screen shows anything still in translation. */
  translating: () => boolean
  /** A SILENT re-read of that feed. */
  refresh: () => Promise<void>
  /** The clock; injectable for tests. */
  now?: () => number
}

export function useTranslationPoll(options: TranslationPollOptions): { restart: () => void } {
  const now = options.now ?? (() => Date.now())
  let timer: ReturnType<typeof setTimeout> | null = null
  let since: number | null = null
  let stopped = false

  function clear(): void {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function schedule(): void {
    clear()
    if (stopped) return
    if (!options.translating()) {
      since = null
      return
    }
    const at = now()
    if (since === null) since = at
    if (at - since >= TRANSLATING_LEASE_MS) return
    timer = setTimeout(() => {
      timer = null
      void options
        .refresh()
        .catch(() => undefined)
        .then(() => schedule())
    }, TRANSLATING_POLL_MS)
  }

  /** A fresh lease: another conversation was opened, or a message sent. */
  function restart(): void {
    since = null
    schedule()
  }

  watch(options.translating, () => schedule(), { immediate: true })

  onBeforeUnmount(() => {
    stopped = true
    clear()
  })

  return { restart }
}
