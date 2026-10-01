// =============================================================================
// AIVIS.ONE Frontend -- Document links (P-106)
// =============================================================================
//
// A document email links straight to ONE document:
//
//   /portfolio/<companyId>?doc=agreement&purchase=<purchaseId>
//   /portfolio/<companyId>?doc=ownership
//
// The address is built by the backend
// (backend/app/modules/purchases/document_utils.py::documents_link), which
// does not know the reader's role. The company position screen exists twice,
// under the investor shell and under the agent shell, so the address above is
// role-neutral: `/portfolio/:id` has no shell of its own and its beforeEnter
// hands the reader to the shell of the role they actually have, query intact
// (documentLinkTarget below). An anonymous reader meets globalGuard first and
// comes back here through `?next=` after signing in.
//
// The position screen then reads the query (parseDocumentQuery below) and
// opens the named document over itself.
//
// Both functions are pure so the whole contract is unit-testable without a
// router instance.
// =============================================================================

import type { LocationQuery, RouteLocationRaw } from 'vue-router'

import { getRoleDashboard } from './guards'

/** The document a link names. */
export type DocumentRequest = { kind: 'ownership' } | { kind: 'agreement'; purchaseId: string }

/**
 * Where `/portfolio/:id` sends a signed-in reader.
 *
 * investor -> /investor/portfolio/:id, agent -> /agent/portfolio/:id, both
 * with the query carried over unchanged. Any other role has no portfolio
 * and goes to its own dashboard -- the same answer globalGuard gives a role
 * a route does not serve.
 */
export function documentLinkTarget(
  role: string | null,
  companyId: string,
  query: LocationQuery,
): RouteLocationRaw {
  if (role === 'investor' || role === 'agent') {
    return { path: `/${role}/portfolio/${encodeURIComponent(companyId)}`, query }
  }
  return getRoleDashboard(role)
}

/** The single string value of a query key, or null when absent, empty or repeated. */
function single(query: LocationQuery, key: string): string | null {
  const raw = query[key]
  if (typeof raw !== 'string' || raw === '') return null
  return raw
}

/**
 * Which document the link asks to open, or null when it names none.
 *
 * A key given twice (`?doc=a&doc=b`) arrives from vue-router as an array and
 * is refused rather than guessed at. `doc=agreement` without a `purchase`
 * names no document, and a `purchase` without `doc` is not read.
 */
export function parseDocumentQuery(query: LocationQuery): DocumentRequest | null {
  const doc = single(query, 'doc')
  if (doc === 'ownership') return { kind: 'ownership' }
  if (doc === 'agreement') {
    const purchaseId = single(query, 'purchase')
    return purchaseId === null ? null : { kind: 'agreement', purchaseId }
  }
  return null
}
