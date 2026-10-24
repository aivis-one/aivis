// =============================================================================
// The screen header: ONE way for a screen to set what the frame's header shows
// =============================================================================
//
// The frame (AppShell) draws one header (K25): a leading back control, one h1,
// the actions. A screen does not draw any of that itself; it says what it wants
// by calling `useScreenHeader` once in its setup:
//
//   useScreenHeader({
//     title: () => t('inv.portfolio.title'),     // the h1, in the cabinet's language
//     lead: () => t('inv.portfolio.subtitle'),   // the line under the title (K25 lead line)
//     back: { name: 'investor-portfolio' },      // a route, `true` for "one step back", or { handler }
//     actions: () => [{ id: 'edit', label: t('common.edit'), icon: Pencil, onClick: edit }],
//   })
//
// Every field is optional and may be a plain value, a ref or a getter; a getter
// that reads `t(...)` follows the language. The call lasts as long as the screen:
// when the screen goes, its entry goes, and the header falls back to the entry
// below it (a section inside a hub overrides the hub's, and the hub's returns
// when the section is closed). A screen that sets no title gets the label of the
// tab it belongs to, else the product name (AppHeader).
//
// The frame's own actions (the figure chips, the bell, the language and theme
// controls, the storefront's right slot) are not set here; `actions` are the
// screen's own icon buttons, drawn between the bell and the controls.
// =============================================================================

import { computed, getCurrentScope, onScopeDispose, shallowRef, toValue } from 'vue'
import type { Component, MaybeRefOrGetter } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

/** A back that calls the screen's own handler; the control is then a button. */
export interface BackHandler {
  handler: () => void
}

/** One icon button of the screen's own, in the header's action row. */
export interface HeaderAction {
  id: string
  /** The accessible name (the button has no text). */
  label: string
  icon: Component
  onClick?: () => void
  /** A route to open, instead of `onClick`. */
  to?: RouteLocationRaw
}

export interface ScreenHeaderSpec {
  /** The screen's h1, in the cabinet's language. */
  title?: MaybeRefOrGetter<string | undefined>
  /** The line under the title (K25 lead line). */
  lead?: MaybeRefOrGetter<string | undefined>
  /**
   * The back control: a route to open, `true` for one step back, or `{ handler }`, a
   * handler the control calls (it is then a button), as a value or from a getter:
   * `back: () => (open.value ? { handler: closeThread } : undefined)`. A bare function
   * is refused by the type, since it would be read as the getter itself.
   */
  back?: MaybeRefOrGetter<RouteLocationRaw | true | BackHandler | undefined>
  actions?: MaybeRefOrGetter<HeaderAction[] | undefined>
}

interface Entry {
  id: number
  spec: ScreenHeaderSpec
}

const entries = shallowRef<Entry[]>([])
let sequence = 0

/** Set the header for the lifetime of the calling screen. Call it in `setup`. */
export function useScreenHeader(spec: ScreenHeaderSpec): void {
  const entry: Entry = { id: ++sequence, spec }
  entries.value = [...entries.value, entry]
  if (getCurrentScope()) {
    onScopeDispose(() => {
      entries.value = entries.value.filter((e) => e.id !== entry.id)
    })
  }
}

/** What the header shows now: the newest screen entry's values. */
export function useCurrentScreenHeader() {
  return computed(() => {
    const spec = entries.value[entries.value.length - 1]?.spec
    return {
      title: toValue(spec?.title) || undefined,
      lead: toValue(spec?.lead) || undefined,
      back: toValue(spec?.back),
      actions: toValue(spec?.actions) ?? [],
    }
  })
}
