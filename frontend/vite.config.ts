import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath } from 'node:url'

export default defineConfig({
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
})
