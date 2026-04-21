// =============================================================================
// CBSHOME Frontend -- useTheme Composable (Phase F4.4 B5)
// =============================================================================
//
// Three-state theme toggle: 'auto' | 'light' | 'dark'.
//
// STORAGE & FLUSH.
//   'light' / 'dark' -> localStorage['cbs-theme'] + data-theme attr on
//   <html>. 'auto' -> key removed, attr removed; CSS falls back to
//   `@media (prefers-color-scheme)`. Matches the pre-init logic in
//   public/theme-init.js (which runs before Vue mounts to avoid FOUC).
//
// STATE MODEL.
//   Module-level `ref` + module-level `MediaQueryList` listener means
//   every useTheme() consumer sees the same `current` and `effective`
//   values. The listener is attached once on module load and reacts
//   to OS-level theme changes while we're in 'auto' mode -- callers
//   that render theme-dependent artwork get reactive updates without
//   any extra wiring.
//
// SSR / NON-BROWSER.
//   Guards around `window` / `localStorage` keep SSR harmless; the
//   initial value defaults to 'auto' on the server. The app currently
//   ships client-only, but the guards cost nothing and prevent a
//   future SSR experiment from crashing module load.
// =============================================================================

import { computed, ref } from 'vue'

export type ThemeMode = 'auto' | 'light' | 'dark'
export type EffectiveTheme = 'light' | 'dark'

const STORAGE_KEY = 'cbs-theme'

// ---------------------------------------------------------------------------
// Module-level singleton state
// ---------------------------------------------------------------------------

function _isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof document !== 'undefined'
}

function _readStored(): ThemeMode {
  if (!_isBrowser()) return 'auto'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // localStorage unavailable (private mode, disabled) -- default to auto.
  }
  return 'auto'
}

function _systemPrefersDark(): boolean {
  if (!_isBrowser()) return false
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

const current = ref<ThemeMode>(_readStored())
// Tracks the OS-level scheme only. Updated by the media query listener
// below; consumed by `effective` when current === 'auto'.
const systemDark = ref<boolean>(_systemPrefersDark())

// Attach the OS-scheme listener exactly once. Using addEventListener
// over the deprecated addListener API; the `?.` guard keeps Safari <14
// from throwing (it ships matchMedia but not addEventListener on the
// MQL). In that legacy case we simply never react to OS changes --
// acceptable tradeoff, the user can always toggle manually.
if (_isBrowser()) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener?.('change', (e: MediaQueryListEvent) => {
    systemDark.value = e.matches
  })
}

function _apply(mode: ThemeMode): void {
  if (!_isBrowser()) return
  const html = document.documentElement
  if (mode === 'auto') {
    try {
      window.localStorage.removeItem(STORAGE_KEY)
    } catch {
      // noop
    }
    html.removeAttribute('data-theme')
  } else {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode)
    } catch {
      // noop -- the UI still reflects the choice via data-theme,
      // the persistence just won't survive a reload.
    }
    html.setAttribute('data-theme', mode)
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function useTheme() {
  function set(mode: ThemeMode): void {
    current.value = mode
    _apply(mode)
  }

  /**
   * The concrete theme actually being rendered right now. Differs
   * from `current` only when current === 'auto', in which case we
   * resolve via prefers-color-scheme. Useful for code that needs to
   * pick a light/dark asset (e.g. logo variant).
   */
  const effective = computed<EffectiveTheme>(() => {
    if (current.value === 'light') return 'light'
    if (current.value === 'dark') return 'dark'
    return systemDark.value ? 'dark' : 'light'
  })

  return { current, effective, set }
}
