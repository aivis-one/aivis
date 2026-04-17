// =============================================================================
// CBSHOME Frontend -- Router Helpers (Phase F4.1.4 + F4.1.5 polish)
// =============================================================================
//
// Shared views (MarketView, ProductDetailView, and soon PurchaseView
// + InstallmentView) must pick role-aware route names based on the
// currently-active shell. These helpers read the `shell` tag that
// router/index.ts attaches to each shell wrapper's meta.
//
// Why meta, not path-matching? A future `/partner/market` shell that
// reuses the same views just needs its own meta.shell = 'partner',
// with zero edits in the shared views.
//
// F4.1.5 polish:
//   `RouteMeta.shell` is now declared in guards.ts's augmentation
//   block, so `route.meta.shell` is natively typed as
//   `Shell | undefined` -- no runtime cast needed here.
// =============================================================================

import type { RouteLocationNormalizedLoaded } from 'vue-router'

export type Shell = 'investor' | 'agent' | 'company' | 'staff'

/**
 * Read the `shell` meta attached to the current route's shell
 * wrapper. Vue Router merges meta from parent + child route records,
 * so the tag set once on the wrapper propagates to every nested view.
 *
 * Returns undefined for public / auth / onboarding routes that live
 * outside any shell.
 */
export function getShell(
  route: RouteLocationNormalizedLoaded,
): Shell | undefined {
  return route.meta.shell
}

/** True when the current route is nested under /agent. */
export function isAgentShell(
  route: RouteLocationNormalizedLoaded,
): boolean {
  return getShell(route) === 'agent'
}
