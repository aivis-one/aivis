// =============================================================================
// AIVIS.ONE -- service worker add-on: open windows follow a new build
// =============================================================================
//
// Loaded by the generated sw.js through `workbox.importScripts`
// (vite.config.ts). H22, P-110.
//
// WHAT HOLDS AN OLD BUILD. The worker precaches index.html and answers every
// navigation from that cache, so HTTP headers never reach the entry document
// while an old worker is in control. The generated worker already calls
// skipWaiting() and clientsClaim() (vite-plugin-pwa does that for
// registerType 'autoUpdate'), so a new worker takes over as soon as it is
// installed -- but a page that is ALREADY OPEN keeps running the JavaScript it
// loaded. The registration vite-plugin-pwa injects (registerSW.js) only calls
// register(); it never reloads anything.
//
// WHY THIS LIVES IN THE WORKER AND NOWHERE ELSE. A page still on an older build
// runs that build's registration code. Of a new release it executes exactly
// one thing: the new sw.js. So the step that moves an open window onto the new
// build can only be taken from inside the worker. A second, page-side reload
// (virtual:pwa-register) would be a second mechanism for the same act and
// would reload twice.
//
// WHEN IT FIRES. Only when this worker REPLACES an active one. On a first
// install there is no older build to leave, and reloading a first-time
// visitor's page would cost them whatever they had typed. Whether this install
// is an update is known during `install` (registration.active is the old
// worker) and needed during `activate`; the worker may be stopped and restarted
// in between, so the answer is kept in Cache Storage, not in a variable.
//
// A reload loses unsaved input in a form. That is the accepted price (H22
// gate): the page reloads onto a build that agrees with the backend, instead
// of submitting to it from one that does not.
// =============================================================================

;(function (sw) {
  const MARKER_CACHE = 'aivis-sw-update'
  const MARKER_KEY = '/__aivis-sw-update__'

  sw.addEventListener('install', (event) => {
    const replacesActive = sw.registration.active !== null
    event.waitUntil(
      sw.caches
        .open(MARKER_CACHE)
        .then((cache) =>
          replacesActive ? cache.put(MARKER_KEY, new Response('update')) : cache.delete(MARKER_KEY),
        ),
    )
  })

  sw.addEventListener('activate', (event) => {
    // Claiming is part of activation. Navigating is NOT: a navigation is a
    // fetch this worker answers, and fetches wait until activation is over --
    // waiting for them inside waitUntil would wait for itself.
    const claimed = takeMarker().then((isUpdate) =>
      isUpdate ? sw.clients.claim().then(() => true) : false,
    )
    event.waitUntil(claimed)
    claimed.then((isUpdate) => (isUpdate ? reloadWindows() : undefined))
  })

  function takeMarker() {
    return sw.caches.open(MARKER_CACHE).then((cache) =>
      cache.match(MARKER_KEY).then((hit) => {
        if (!hit) return false
        return cache.delete(MARKER_KEY).then(() => true)
      }),
    )
  }

  function reloadWindows() {
    return sw.clients.matchAll({ type: 'window' }).then((windows) =>
      Promise.all(
        windows.map((win) =>
          // One window that cannot be navigated (closed meanwhile, or a
          // browser without WindowClient.navigate) must not stop the rest.
          Promise.resolve()
            .then(() => win.navigate(win.url))
            .catch(() => null),
        ),
      ),
    )
  }
})(self)
