// =============================================================================
// AIVIS.ONE Frontend -- Query String Helper (Phase F4.3, TD-F08e close)
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
//   - boolean is coerced via String() -> "true" / "false", which
//     FastAPI parses back into a bool query param. Added in iter 2.7
//     Block B for the ?is_published= / ?upcoming= staff filters.
//   - everything else is coerced via String() (numbers, dates already
//     serialised as ISO strings by the caller).
//   - an array is a REPEATED key, one `key=value` per element in order
//     (`?category=a&category=b`) -- FastAPI's form of a list query param
//     (H40: the staff ticket list's category filter). Its elements follow
//     the rules above; an empty array, like an absent value, emits nothing.
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

export type QueryScalar = string | number | boolean | undefined | null

export type QueryValue = QueryScalar | readonly QueryScalar[]

export type QueryParams = Record<string, QueryValue>

/**
 * Build a leading-`?` query string from a plain object.
 *
 * Returns '' when every value is absent, so template literals like
 * `/api/v1/foo${buildQueryString(params)}` stay clean.
 */
export function buildQueryString(params: QueryParams): string {
  const q = new URLSearchParams()
  const present = (v: QueryScalar): v is string | number | boolean =>
    v !== undefined && v !== null && v !== ''
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      for (const item of value as readonly QueryScalar[]) {
        if (present(item)) q.append(key, String(item))
      }
      continue
    }
    if (present(value as QueryScalar)) q.set(key, String(value))
  }
  const qs = q.toString()
  return qs ? `?${qs}` : ''
}
