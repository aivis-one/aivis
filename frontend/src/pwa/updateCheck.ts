// =============================================================================
// Ask the browser to look for a new service worker -- H22, P-110
// =============================================================================
//
// A browser checks for a new sw.js on its own only when a DOCUMENT is loaded
// (and on a few worker events). A tab that stays open -- the Telegram Mini App,
// an installed PWA -- moves between screens through the router and never loads
// a document, so on its own it would keep an old build for as long as it stays
// open. This asks for the check at the two moments a person arrives somewhere:
// after every route change, and when the tab becomes visible again.
//
// What happens when a new worker IS found is not decided here: the worker
// installs, activates and reloads the open windows itself (public/sw-update.js).
// Because the check runs on arrival, that reload lands just after a screen was
// entered rather than while it is being filled in.
//
// NO THROTTLE, on purpose (H22 gate): the browser queues update() calls into one
// job, and sw.js is served `no-cache`, so a check that finds nothing is a 304.
//
// The registration itself is injected by vite-plugin-pwa (registerSW.js, on
// window `load`). Before it exists getRegistration() resolves undefined and the
// check does nothing; a failed check (offline) is dropped -- the next arrival
// asks again.
// =============================================================================

import type { Router } from 'vue-router'

export function installUpdateCheck(
  router: Router,
  nav: Navigator = navigator,
  doc: Document = document,
): void {
  if (!('serviceWorker' in nav)) return
  const container = nav.serviceWorker

  const check = (): void => {
    container
      .getRegistration()
      .then((registration) => registration?.update())
      .catch(() => undefined)
  }

  router.afterEach(() => {
    check()
  })
  doc.addEventListener('visibilitychange', () => {
    if (doc.visibilityState === 'visible') check()
  })
}
