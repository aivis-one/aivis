import { defineConfig, loadEnv, type UserConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath } from 'node:url'
import { readFileSync } from 'node:fs'
import { requireOrigin } from './src/api/deployOrigin'

// The version the staff cabinet shows is the one this build is made from:
// package.json's, read at build time and written into the bundle.
const APP_VERSION = (
  JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
    version: string
  }
).version

const config: UserConfig = {
  // Row 31: the cabinet is served under the site's /app/. Vite prefixes every
  // asset URL and import.meta.env.BASE_URL becomes '/app/'.
  base: '/app/',
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
  plugins: [
    vue(),
    // PWA — Sprint F0.4
    VitePWA({
      registerType: 'autoUpdate',
      manifest: false, // Using public/manifest.json directly
      workbox: {
        // Precache all static assets including self-hosted woff2 fonts.
        // Fonts are TRACKED IN THE REPO under public/fonts/ and served from
        // /fonts/<filename>.woff2 -- no external CDN needed.
        // (This said "downloaded by install_aivis.sh" until 2026-08-17. That
        // script contains no font logic: `grep -ic font` -> 0 over 2,113
        // lines, control `frontend` -> 72. The same false claim sat in
        // src/styles/fonts.css's own header.)
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//],
        // H22 (P-110): the add-on that moves every open window onto a new
        // build the moment a new worker replaces an old one. It has to live
        // INSIDE the worker: a page that is still running an older build runs
        // that build's registration code, and only the new sw.js reaches it.
        // See public/sw-update.js.
        importScripts: ['sw-update.js'],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
  build: {
    target: 'es2022',
    sourcemap: false,
  },
}

export default defineConfig(({ command, mode }) => {
  // H35 P-127: a production bundle is built for ONE deployment, whose API
  // origin it is given (frontend/Dockerfile build arg; .env for a local
  // build). Without it, or with a value that is not an exact https origin,
  // the build stops here with the variable's name -- there is no default.
  // `vite serve` is not checked here: client.ts checks at load and accepts
  // http:// there, for a backend on localhost.
  if (command === 'build') {
    const env = loadEnv(mode, process.cwd(), 'VITE_')
    requireOrigin('VITE_API_BASE_URL', env.VITE_API_BASE_URL, { allowHttp: false })
  }
  return config
})
