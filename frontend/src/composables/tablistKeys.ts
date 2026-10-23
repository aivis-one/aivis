// =============================================================================
// Keys of a tab strip, for the design system's Tabs (K12)
// =============================================================================
//
// The system's `components.js` carries the keys a tab strip needs (Left and Right
// move between tabs and choose, Home and End go to the ends, direction aware);
// the cabinet draws its tabs in Vue, so the same keys live here. Bind it on the
// element that holds the tabs: `<div role="tablist" @keydown="onTablistKeydown">`,
// with `role="tab"` and `tabindex` (0 on the selected tab, -1 on the others) on
// each tab. A tab is chosen by the key as by a click (the tab's own click runs).

export function onTablistKeydown(e: KeyboardEvent): void {
  const strip = e.currentTarget as HTMLElement | null
  if (!strip) return
  const tabs = Array.from(strip.querySelectorAll<HTMLElement>('[role="tab"]:not(:disabled)'))
  const current = tabs.indexOf(e.target as HTMLElement)
  if (current < 0 || tabs.length === 0) return
  const rtl = getComputedStyle(strip).direction === 'rtl'
  let next = -1
  if (e.key === 'ArrowRight') next = current + (rtl ? -1 : 1)
  else if (e.key === 'ArrowLeft') next = current + (rtl ? 1 : -1)
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = tabs.length - 1
  else return
  e.preventDefault()
  const target = tabs[(next + tabs.length) % tabs.length]
  target.focus()
  target.click()
}
