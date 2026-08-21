// =============================================================================
// AIVIS.ONE Frontend -- Vitest config
// =============================================================================
//
// SEPARATE from vite.config.ts on purpose: the build config is what ships, and
// a test block does not belong in it. Nothing here can affect a production
// build -- `npm run build` never reads this file.
//
// WHY THIS EXISTS AT ALL, and it is not tidiness. The browser harness this
// project is validated in DOES NOT DELIVER KEY EVENTS TO THE PAGE: a keydown
// listener on document records zero events while the driver reports a keypress,
// and sequential Tab does not advance. So the one thing that cannot be checked
// live is exactly the thing CCheckbox and useDialog are FOR -- Space toggling a
// control, Escape closing a dialog, focus returning to the opener, Tab wrapping
// inside a modal. Those components shipped on a code read.
//
// A component test can press a key. That is the whole argument.
// =============================================================================

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.spec.ts'],
    setupFiles: ['src/test-setup.ts'],
    globals: false,
  },
})
