// =============================================================================
// CBSHOME Frontend -- Query String Helper (Phase F4.3, TD-F08e close)
// =============================================================================
//
// Single-source `URLSearchParams` wrapper for typed API clients.
//
// Returns a fully-formed query component (`?a=1&b=2`) or the empty
// string when all values are absent -- so call sites compose as
// `${path}${buildQueryString(params)}` without any ternary noise.
//
// Filter policy (matches the legacy inline pattern in api/*.ts):
//   - undefined, null, and '' are skipped (absent filter)
//   - 0 (number) IS emitted -- valid for future range filters like
//     `amount_min=0`. Previous inline calls used `if (params?.page)`
//     which swallowed 0 too, but none of today's callers pass 0,
//     so this widens behaviour without regressing any current path.
//   - everything else is coerced via String() (numbers, dates already
//     serialised as ISO strings by the caller).
//
// Keys are emitted in insertion order, which matches the ordering
// the inline callers produced. This keeps backend request logs and
// snapshot tests stable across the B1.1 migration.
//
// Extracted when F4.3 Transactions became the 5th consumer
// (threshold documented in TD-F08e). Migration of the four legacy
// consumers (products, companies, installments, admin) lands in
// batch B1.1 of the same phase.
// =============================================================================

export type QueryValue = string | number | undefined | null

export type QueryParams = Record<string, QueryValue>

/**
 * Build a leading-`?` query string from a plain object.
 *
 * Returns '' when every value is absent, so template literals like
 * `/api/v1/foo${buildQueryString(params)}` stay clean.
 */
export function buildQueryString(params: QueryParams): string {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    q.set(key, String(value))
  }
  const qs = q.toString()
  return qs ? `?${qs}` : ''
}
