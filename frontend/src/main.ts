import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '@/App.vue'
import { setOnKycRequired } from '@/api/client'
import { router } from '@/router'
import { i18n, setupI18n } from '@/i18n'
import { installUpdateCheck } from '@/pwa/updateCheck'
import { kycActionForRoute, showKycPrompt } from '@/composables/useKycPrompt'

import iconSprite from '@/assets/icons/ds-icons.svg?raw'

import '@/styles/variables.css'
import '@/styles/global.css'
// telegram.css AFTER global.css: it is platform skinning laid over the system.
import '@/styles/telegram.css'

// Bootstrap sequence:
//   1. Resolve the active locale and load its JSON (setupI18n).
//      Without this, the first render would show raw i18n keys.
//   2. Create the app and wire Pinia, Router, i18n.
//   3. Mount.
async function bootstrap(): Promise<void> {
  // The design system's icon sprite, once, before anything draws an icon.
  document.body.insertAdjacentHTML('afterbegin', iconSprite)
  await setupI18n()

  const app = createApp(App)

  app.use(createPinia())
  app.use(router)
  app.use(i18n)

  // H10, turned over in H21 P-111: the KYC gate answers 402 only on the
  // money routes -- buying, an installment plan, a withdrawal, the agent
  // application. Everything else in the product is open before
  // verification. A 402 can still arrive from several screens, so the
  // response is registered once here rather than in every caller's
  // catch block, and those callers return on a 402 without a toast of
  // their own. Wired at bootstrap and not inside the auth store, which
  // must not import the router -- the router imports every view and
  // every view imports the store.
  //
  // THE ONE RULE FOR THE FOUR CLOSED ACTIONS: the person stays on the page
  // they pressed the button on and is told, in a message with a button to the
  // verification screen, that identity verification (and its cost) comes first
  // (components/shared/KycRequiredPrompt.vue). Nothing moves them away.
  //
  // The session is left alone, unlike the 401 path: the person is
  // signed in and simply not verified.
  setOnKycRequired(() => {
    const current = router.currentRoute.value
    if (current.path === '/verification') return
    showKycPrompt(kycActionForRoute(current.name))
  })

  // H22 (P-110): an open tab asks for a new service worker whenever the
  // person arrives on a screen; the worker itself moves the tab onto a new
  // build (src/pwa/updateCheck.ts, public/sw-update.js).
  installUpdateCheck(router)

  app.mount('#app')
}

// Fail-visibly instead of a silent white screen if bootstrap rejects
// (e.g. locale chunk missing or network error on cold start).
bootstrap().catch((err) => {
  console.error('Bootstrap failed:', err)
  const root = document.getElementById('app')
  if (root) {
    root.textContent = 'Failed to start app. Please reload the page.'
  }
})
