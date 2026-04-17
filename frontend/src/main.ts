import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from '@/App.vue'
import { router } from '@/router'
import { i18n, setupI18n } from '@/i18n'

import '@/styles/variables.css'
import '@/styles/global.css'
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
