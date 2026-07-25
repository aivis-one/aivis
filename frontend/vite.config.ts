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
        // Fonts are downloaded to public/fonts/ by install_aivis.sh
        // and served from /fonts/<filename>.woff2 -- no external CDN needed.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//],
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
