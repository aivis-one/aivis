/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

declare module '*.json' {
  const value: Record<string, string | Record<string, string>>
  export default value
}

interface ImportMetaEnv {
  // Set by the build (frontend/Dockerfile) or by .env in development; never
  // defaulted. Typed as possibly absent because it can be -- client.ts checks.
  readonly VITE_API_BASE_URL: string | undefined
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** The version of this build: its tag (src/appVersion.ts), written into the bundle by vite.config.ts. */
declare const __APP_VERSION__: string
