// =============================================================================
// CBSHOME Frontend -- i18n Utilities (Phase F4.4 B0)
// =============================================================================
//
// Extracted in F4.4 B0 to consolidate the "translate with raw-token
// fallback" pattern that had organically appeared in five call-sites
// across BalanceView, TransactionsView, and TransactionDetailSheet
// (TD-F09b).
//
// The fallback is how the frontend stays forward-compatible with
// server-driven enums (payment status, transaction type, detail keys).
// When the backend adds a new value ahead of the i18n catalogue,
// the raw token renders through instead of a blank or the literal
// i18n key -- ugly but readable, which is better than a hole in the
// UI during the gap between a backend release and an i18n PR.
//
// The signature intentionally accepts a bare `(key: string) => string`
// rather than vue-i18n's full ComposerTranslation. This keeps the
// helper framework-agnostic (unit tests can pass a plain function)
// and sidesteps the overload gymnastics in vue-i18n's types -- the
// caller just passes `t` from useI18n() and TypeScript narrows it
// via structural compatibility.
// =============================================================================

/**
 * Return `t(key)` if it produced a real translation, otherwise return
 * `raw`. vue-i18n returns the key itself when no translation is found
 * in the active locale, which is the discriminator used here.
 *
 *   tOrRaw(t, 'inv.balance.status.confirmed', 'confirmed')
 *     -> 'Confirmed'   (if key exists in en.json)
 *     -> 'confirmed'   (if key missing)
 *
 * `raw` is caller-chosen: usually the source token itself, occasionally
 * a pre-humanised form (TransactionDetailSheet.keyLabel passes a
 * snake_case-to-Title-Case version so unknown detail keys still read
 * naturally).
 *
 * INVARIANT -- vue-i18n `missingWarn` / `fallbackWarn` default behaviour.
 * The `translated === key` check relies on vue-i18n returning the raw
 * key string when the key is not found. This is the default. Projects
 * that override missingWarn to a custom handler that swallows the key
 * (returns '' or null) would break this discriminator silently. AIVIS.ONE
 * keeps defaults in src/i18n/index.ts; do not change that without
 * updating tOrRaw to match.
 */
export function tOrRaw(
  t: (key: string) => string,
  key: string,
  raw: string,
): string {
  const translated = t(key)
  return translated === key ? raw : translated
}
