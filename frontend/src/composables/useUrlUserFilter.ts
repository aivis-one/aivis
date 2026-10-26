// =============================================================================
// The user a staff list is filtered by, carried in the address
// =============================================================================
//
// The lists of payments, withdrawals and purchases can be narrowed to one
// person. The person is an address parameter (`?user_id=`, `?buyer_id=`), so
// the user card can open a list already filtered, and a reload keeps the filter.
// The ref holds the user's id ('' = nobody); a change of it writes the
// parameter into the address with `history.replaceState`, the other parameters
// kept, as the pager does (components/ui/useUrlPage.ts).
//
// The reads and the writes touch `window.location` and `history` only, so a list
// keeps working in a test that mounts it without a router.

import { ref, watch } from 'vue'
import type { Ref } from 'vue'

/** The user id named by an address' query string; '' when the parameter is absent. */
export function userFromSearch(search: string, key: string): string {
  return new URLSearchParams(search).get(key)?.trim() ?? ''
}

/** The query string that names the user (or none), the other parameters kept. */
export function searchForUser(search: string, id: string, key: string): string {
  const params = new URLSearchParams(search)
  if (id) params.set(key, id)
  else params.delete(key)
  const text = params.toString()
  return text ? `?${text}` : ''
}

export function useUrlUserFilter(key: string): Ref<string> {
  const id = ref(typeof window === 'undefined' ? '' : userFromSearch(window.location.search, key))
  watch(id, (value) => {
    if (typeof window === 'undefined') return
    const search = searchForUser(window.location.search, value, key)
    if (search === window.location.search) return
    const { pathname, hash } = window.location
    window.history.replaceState(window.history.state, '', `${pathname}${search}${hash}`)
  })
  return id
}
