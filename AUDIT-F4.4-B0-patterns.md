# Audit F4.4 B0 — label / format patterns

## Summary

- Scanned: `frontend/src/**/*.{ts,vue}` (106 files; excluded `node_modules`, `dist`, `public`, `mockups`, tests)
- Total findings: **16** (P0: 0, P1: 5, P2: 7, P3: 2, P4a: 0, P4b: 0, P4c: 3)
- Clean categories: **P0** (B0 regressions), **P4a** (querystring in `api/*`), **P4b** (inline `useI18n().t`)
- **Important preamble:** at the time of this audit, the B0 helpers do not yet exist in the tree — there is no `formatSignedPrice` in `frontend/src/utils/format.ts` and no `frontend/src/utils/i18n.ts` at all. Therefore the P1 / P3 / P4c findings below are **pre-migration call-sites** (the actual targets B0 is supposed to migrate), not regressions. They are reported so the migration branch can diff against them.

## P0 — B0 migration regressions

None. (B0 has not yet landed — see preamble. Nothing to regress against.)

## P1 — TD-F09b exact idiom

| # | File | Lines | Function | Snippet | Suggested migration |
|---|------|-------|----------|---------|---------------------|
| 1 | `frontend/src/components/shared/TransactionDetailSheet.vue` | 94–98 | `typeLabel` | `return translated === key ? type : translated` | Replace body with `return tOrRaw(t, \`inv.transactions.type.${type}\`, type)` |
| 2 | `frontend/src/components/shared/TransactionDetailSheet.vue` | 100–110 | `keyLabel` | `if (translated !== i18nKey) return translated` + humanise fallback | Partial: use `tOrRaw` for the translation step; keep the snake_case humaniser as the final fallback. Not a pure TD-F09b replacement. |
| 3 | `frontend/src/views/investor/TransactionsView.vue` | 104–108 | `typeLabel` | `return translated === key ? type : translated` | Replace body with `return tOrRaw(t, \`inv.transactions.type.${type}\`, type)` |
| 4 | `frontend/src/views/investor/BalanceView.vue` | 86–92 | `statusLabel` | `return translated === key ? s : translated` | Replace body with `return tOrRaw(t, \`inv.balance.status.${s}\`, s)` |
| 5 | `frontend/src/views/investor/BalanceView.vue` | 94–98 | `typeLabel` | `return translated === key ? type : translated` | Replace body with `return tOrRaw(t, \`inv.balance.type.${type}\`, type)` |

Finding #2 (`keyLabel`) is flagged separately because it is a hybrid: the first half is the TD-F09b idiom, but the second half adds a snake_case humaniser as a secondary fallback — that behaviour must be preserved after migration, so `tOrRaw` alone is insufficient. See also Out-of-scope observations.

## P2 — Server enums rendered raw (no i18n)

| # | File | Lines | Binding | Field | Type per `api/types.ts` | Suggested action |
|---|------|-------|---------|-------|-------------------------|------------------|
| 1 | `frontend/src/views/staff/StaffPaymentsView.vue` | 141 | mustache | `item.payment_type` | `PaymentType \| string` (`'crypto' \| 'card' \| 'bank' \| string`) | Wrap in `tOrRaw(t, 'staff.payments.type.' + item.payment_type, item.payment_type)` |
| 2 | `frontend/src/views/staff/StaffPaymentsView.vue` | 141 | mustache | `item.provider` | `string` (backend enum-like token, e.g. `stripe`, `coinbase`) | Wrap in `tOrRaw(t, 'staff.payments.provider.' + item.provider, item.provider)` |
| 3 | `frontend/src/views/staff/StaffPaymentsView.vue` | 147 | `:text` on CBadge | `item.status` | `PaymentStatusType \| string` | Wrap in `tOrRaw(t, 'staff.payments.status.' + item.status, item.status)` |
| 4 | `frontend/src/views/staff/StaffAgentAppsView.vue` | 119 | mustache | `item.status` | `string` (on `AgentApplicationResponse`) | Wrap in `tOrRaw(t, 'staff.agentApps.status.' + item.status, item.status)` |
| 5 | `frontend/src/views/staff/StaffUsersView.vue` | 212 | mustache | `item.role` | `UserRole` (`'investor' \| 'agent' \| 'company' \| 'staff' \| 'platform'`) | Wrap in `tOrRaw(t, 'staff.users.role.' + item.role, item.role)` |
| 6 | `frontend/src/views/staff/StaffUsersView.vue` | 216, 260 | `:text` on CBadge | `item.kyc_status` / `detailUser.kyc_status` | `KycStatus` (`'not_started' \| 'submitted' \| 'approved' \| 'rejected'`) | Wrap in `tOrRaw(t, 'staff.users.kycStatus.' + x.kyc_status, x.kyc_status)` (two call-sites) |
| 7 | `frontend/src/views/staff/StaffUsersView.vue` | 249 | `:text` on CBadge | `detailUser.role` | `UserRole` | Wrap in `tOrRaw(t, 'staff.users.role.' + detailUser.role, detailUser.role)` |

`BalanceView.vue:311` passes `statusLabel(item.status)` (already wrapped via the tOrRaw-style helper in P1 #4), so it is **not** a P2 finding.

## P3 — Money formatting duplicates

| # | File | Lines | Construct | Current output | Proposed replacement |
|---|------|-------|-----------|----------------|----------------------|
| 1 | `frontend/src/views/staff/StaffPaymentsView.vue` | 41–43 | `function formatCents(cents, currency)` returns `\`${(cents / 100).toFixed(2)} ${currency.toUpperCase()}\`` | `12.34 USD` (no `$` even for USD) | Delete `formatCents`; call `formatPrice(item.amount_cents, item.currency)` from `@/utils/format`. Note this is a semantic change for USD (`$12.34` vs `12.34 USD`); confirm with designer before migrating. |
| 2 | `frontend/src/views/investor/TransactionsView.vue` | 110–115 | `function formatAmount(cents, currency)` with `formatPrice(Math.abs(cents), …)` + manual `+` / `-` prefix | `+$12.34`, `-$12.34`, `$0.00` | Delete `formatAmount`; call `formatSignedPrice(cents, currency)` once the helper exists. (Overlaps with P4c #2.) |

## P4a — Querystring leftovers

No findings inside `frontend/src/api/**` — all API wrappers are on `buildQueryString`. The single remaining `new URLSearchParams(...)` in the tree is `frontend/src/composables/useAuth.ts:123`, which parses the browser address bar (`window.location.search`) for a `?ref=` query param — legitimate, out of scope per the prompt.

## P4b — Inline `useI18n().t`

None. `rg 'useI18n\(\)\.'` returns zero hits across `frontend/src/`.

## P4c — B0 trace cleanliness

The prompt asks that after B0 there should be no `function formatAmount`, no `formatPrice(Math.abs(cents), …)`, no remaining TD-F09b inline idioms. Because B0 has not landed, these are all still present. Listed for completeness as "what B0 must remove":

| # | File | Line | Construct |
|---|------|------|-----------|
| 1 | `frontend/src/views/investor/TransactionsView.vue` | 110 | `function formatAmount(cents: number, currency?: string): string` |
| 2 | `frontend/src/views/investor/TransactionsView.vue` | 113 | `formatPrice(Math.abs(cents), currency)` with manual signed prefix on line 114 |
| 3 | `frontend/src/components/shared/TransactionDetailSheet.vue` | 81 | `formatPrice(Math.abs(cents), txn.value.currency)` with manual `+`/`-` branches on lines 82–83 |

All three disappear when the two call-sites adopt `formatSignedPrice`.

## Out-of-scope observations

A few items that don't fit the six categories cleanly but may matter when B0 lands.
(1) `TransactionDetailSheet.vue:100–110` (`keyLabel`) is not a pure TD-F09b idiom: after the translation-or-raw step it falls through to a snake_case→Title-Case humaniser. If `tOrRaw` is designed to return *only* the raw key on miss, the humaniser must be preserved separately — either keep the current manual shape here, or extend `tOrRaw` to accept an optional `transform: (raw) => string` callback. Listed under P1 #2 as well so it isn't lost, but flagged here because the judgement call belongs to whoever designs `tOrRaw`'s signature.
(2) Bundle of P2 hits in `StaffPaymentsView.vue:141` shows two raw enums (`payment_type`, `provider`) in the same template expression; consider adding all three (type/provider/status) catalogue branches together when you add i18n keys for this view, so the migration is a single translation-catalogue commit. Same thought for `StaffUsersView.vue` (role + kyc_status used together on lines 212/216 and 249/260).
(3) `formatCents` in `StaffPaymentsView.vue` emits `12.34 USD` while `formatPrice` emits `$12.34` for USD — they are *not* interchangeable for USD. Whoever migrates P3 #1 needs a product decision, not just a code swap.
