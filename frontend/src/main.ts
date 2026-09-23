import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '@/App.vue'
import { setOnKycRequired } from '@/api/client'
import { router } from '@/router'
import { i18n, setupI18n } from '@/i18n'

import '@/styles/variables.css'
import '@/styles/global.css'
// shell.css AFTER global.css: it is layout chrome that must win a same-specificity
// tie against the reset, and BEFORE telegram.css, which is platform skinning.
import '@/styles/shell.css'
import '@/styles/telegram.css'

// Bootstrap sequence:
//   1. Resolve the active locale and load its JSON (setupI18n).
//      Without this, the first render would show raw i18n keys.
//   2. Create the app and wire Pinia, Router, i18n.
//   3. Mount.
async function bootstrap(): Promise<void> {
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
  // NO TOAST HERE: /verification is a standalone auth card with no
  // CToast mounted, so a toast raised on the way there would never be
  // seen. The explanation lives on the verification screen itself.
  //
  // The session is left alone, unlike the 401 path: the person is
  // signed in and simply not verified.
  setOnKycRequired(() => {
    if (router.currentRoute.value.path !== '/verification') {
      void router.push('/verification').catch(() => undefined)
    }
  })

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
