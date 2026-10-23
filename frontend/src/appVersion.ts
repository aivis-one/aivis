// =============================================================================
// AIVIS.ONE Frontend -- the version the cabinet shows
// =============================================================================
//
// The cabinet's version is the build tag, written into the bundle once at build
// time as __APP_VERSION__ (vite.config.ts). The tag is this one constant; a
// release build for another tag sets VITE_APP_VERSION. package.json's own
// version field is the npm package's and is not shown.
// =============================================================================

/** The build tag of this cabinet. */
export const DEFAULT_APP_VERSION = 'cabinets-1.5'

/** The version to write into the bundle: the VITE_APP_VERSION override, else the build tag. */
export function resolveAppVersion(override: string | undefined): string {
  const value = (override ?? '').trim()
  return value === '' ? DEFAULT_APP_VERSION : value
}
