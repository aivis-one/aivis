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
  define: {
    // The build's version (vite.config.ts writes the real one); the tests read a fixed one.
    __APP_VERSION__: JSON.stringify('0.0.0-test'),
  },
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
    // The API origin the code under test is built for. A reserved domain
    // (RFC 2606): tests carry no deployment address (checks/deploy_addresses.py).
    env: {
      VITE_API_BASE_URL: 'https://api.example.com',
    },
  },
})
