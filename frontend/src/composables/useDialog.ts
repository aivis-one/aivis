// =============================================================================
// AIVIS.ONE Frontend -- useDialog
// =============================================================================
//
// Shared modal behaviour for CModal and CBottomSheet. Both were overlays that
// a mouse could dismiss and a keyboard could not: no Escape handler, no dialog
// role, no focus containment, and no focus restore. CBottomSheet had no close
// control of its own at all, so one of its six call sites -- the read-only
// TransactionDetailSheet on /investor/transactions -- could not be closed from
// a keyboard by any means.
//
// Written once here rather than twice in the components, because the two
// differ only in how they are painted.
//
// WHAT IT DOES WHILE OPEN:
//   * Escape closes.
//   * Tab and Shift+Tab wrap inside the dialog instead of walking the page
//     behind it (WCAG 2.1.2: content behind a modal must not be reachable).
//   * Focus moves into the dialog on open and returns to whatever had it on
//     close -- otherwise focus falls back to <body> and a keyboard user
//     restarts from the top of the document.
// =============================================================================

import { watch, nextTick, onBeforeUnmount, type Ref } from 'vue'

/** Elements that can hold focus. `[tabindex="-1"]` is focusable by script but
 *  deliberately out of the Tab order, so it is excluded from the wrap set. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'

function focusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => {
    if (el.hasAttribute('disabled') || el.getAttribute('aria-hidden') === 'true') return false
    const r = el.getBoundingClientRect()
    return r.width > 0 || r.height > 0
  })
}

export function useDialog(
  open: Ref<boolean>,
  dialogEl: Ref<HTMLElement | null>,
  close: () => void,
): void {
  let previouslyFocused: HTMLElement | null = null

  function onKeydown(e: KeyboardEvent): void {
    if (!open.value) return

    if (e.key === 'Escape') {
      e.stopPropagation()
      close()
      return
    }

    if (e.key !== 'Tab') return
    const root = dialogEl.value
    if (!root) return
    const items = focusable(root)
    if (!items.length) {
      // Nothing to focus inside: keep focus on the dialog rather than letting
      // it escape to the page behind.
      e.preventDefault()
      root.focus()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement as HTMLElement | null
    if (e.shiftKey && (active === first || active === root || !root.contains(active))) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  function teardown(): void {
    document.removeEventListener('keydown', onKeydown, true)
  }

  watch(
    open,
    (isOpen, wasOpen) => {
      if (isOpen) {
        previouslyFocused = document.activeElement as HTMLElement | null
        document.addEventListener('keydown', onKeydown, true)
        void nextTick(() => {
          const root = dialogEl.value
          if (!root) return
          const items = focusable(root)
          ;(items[0] ?? root).focus()
        })
      } else if (wasOpen) {
        teardown()
        previouslyFocused?.focus?.()
        previouslyFocused = null
      }
    },
    { immediate: true },
  )

  onBeforeUnmount(teardown)
}
