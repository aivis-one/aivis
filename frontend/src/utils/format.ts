// =============================================================================
// CBSHOME Frontend -- Format Utilities (Phase F4.1.4 + F4.4 B0)
// =============================================================================
//
// Shared formatters extracted from ProductCard + ProductDetailView
// (TD-F04 closed). Consumers today:
//   - formatPrice:        ProductCard, ProductDetailView, PurchaseView,
//                         InstallmentView, BalanceView, and the filter
//                         sheet label.
//   - formatSignedPrice:  TransactionsView list amount, TransactionDetailSheet
//                         summary amount. Extracted in F4.4 B0 to collapse
//                         two diverging implementations (TD-F09a).
//   - formatNumber:       ProductCard, ProductDetailView, PurchaseView.
//   - resolveCoverImage:  ProductCard, ProductDetailView.
// =============================================================================

/**
 * Cents -> price string.
 *
 *   formatPrice(1234)           -> "$12.34"
 *   formatPrice(1234, 'USD')    -> "$12.34"
 *   formatPrice(1234, 'EUR')    -> "12.34 EUR"
 *
 * Currency is optional because the backend does not yet emit this
 * field on Public* responses (TD-F03). Defaults to USD; once the
 * backend lands a real `currency` field the call-site just passes
 * `product.currency` through.
 */
export function formatPrice(cents: number, currency?: string): string {
  const c = (currency ?? 'USD').toUpperCase()
  const amount = (cents / 100).toFixed(2)
  if (c === 'USD') return `$${amount}`
  return `${amount} ${c}`
}

/**
 * Signed cents -> price string with an explicit sign for non-zero values.
 *
 *   formatSignedPrice(1234)         -> "+$12.34"
 *   formatSignedPrice(-1234)        -> "-$12.34"
 *   formatSignedPrice(0)            -> "$0.00"
 *   formatSignedPrice(-1234, 'EUR') -> "-12.34 EUR"
 *
 * Zero carries no sign -- a zero-amount movement has no credit/debit
 * direction to signal. This consolidates TransactionsView.formatAmount
 * (previously rendered "+$0.00" -- a minor bug) and
 * TransactionDetailSheet.signedAmount (already correct) onto one
 * shared implementation (TD-F09a).
 */
export function formatSignedPrice(cents: number, currency?: string): string {
  const base = formatPrice(Math.abs(cents), currency)
  if (cents > 0) return `+${base}`
  if (cents < 0) return `-${base}`
  return base
}

/**
 * Integer -> locale-aware number string with thousands separator.
 * Matches the rest of the UI's numeric conventions per locale.
 */
export function formatNumber(n: number, locale: string): string {
  return n.toLocaleString(locale)
}

/**
 * Resolve a cover image CSS value for a product-like source.
 *
 * Fallback chain:
 *   1. cover_url           -- product-level cover if set
 *   2. company_logo_url    -- company logo as a neutral fallback
 *   3. null                -- consumer renders an icon placeholder
 *
 * Returns a ready-to-use `url("...")` string with encodeURI applied
 * so stray characters in staff-provided URLs cannot break the inline
 * background-image style. Returns null when both fields are null;
 * the consumer then switches to a fallback class / element.
 */
export function resolveCoverImage(source: {
  cover_url: string | null
  company_logo_url: string | null
}): string | null {
  const raw = source.cover_url ?? source.company_logo_url
  return raw ? `url("${encodeURI(raw)}")` : null
}
