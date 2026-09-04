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

  // H10: a 402 from the KYC gate can arrive from any screen, so the
  // response is registered once here rather than in every caller's
  // catch block. Wired at bootstrap and not inside the auth store,
  // which must not import the router -- the router imports every view
  // and every view imports the store.
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
