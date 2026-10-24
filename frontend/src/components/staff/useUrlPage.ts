// =============================================================================
// The page of a staff list, carried in the address (the Pager, K17)
// =============================================================================
//
// A page is an address: the pager's links name `?page=n`, and a list opened on
// that address, or reloaded, shows that page. The ref holds the page number; a
// change of it writes `page` into the address with `history.replaceState`
// (the entry is replaced, so the browser's back button is not made to walk the
// pages) and keeps the router's own state object in the entry. Page 1 leaves the
// address bare.
//
// The reads and the writes touch `window.location` and `history` only, so a list
// keeps working in a test that mounts it without a router.

import { ref, watch } from 'vue'
import type { Ref } from 'vue'

export const PAGE_KEY = 'page'

/** The page named by an address' query string: a whole number from 1, else 1. */
export function pageFromSearch(search: string, key: string = PAGE_KEY): number {
  const raw = new URLSearchParams(search).get(key)
  const n = raw === null ? NaN : Number(raw)
  return Number.isInteger(n) && n >= 1 ? n : 1
}

/** The query string that names page `n`, the other parameters kept. */
export function searchForPage(search: string, n: number, key: string = PAGE_KEY): string {
  const params = new URLSearchParams(search)
  if (n > 1) params.set(key, String(n))
  else params.delete(key)
  const text = params.toString()
  return text ? `?${text}` : ''
}

export function useUrlPage(key: string = PAGE_KEY): Ref<number> {
  const page = ref(typeof window === 'undefined' ? 1 : pageFromSearch(window.location.search, key))
  watch(page, (n) => {
    if (typeof window === 'undefined') return
    const search = searchForPage(window.location.search, n, key)
    if (search === window.location.search) return
    const { pathname, hash } = window.location
    window.history.replaceState(window.history.state, '', `${pathname}${search}${hash}`)
  })
  return page
}
