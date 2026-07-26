// =============================================================================
// AIVIS.ONE Frontend -- safeNavigate Composable (iter 2.7 batch D)
// =============================================================================
//
// Canonical wrapper around router.push / router.replace that swallows benign
// NavigationFailure types (duplicated / cancelled / aborted) and logs any
// other failure to console.error with a caller-supplied context prefix.
//
// Established in iter 2.6 (R20-R27 review cycle) as the canonical pattern for
// every navigation in the app; extracted from 55+ byte-identical inline
// .catch blocks in iter 2.7 sweep batches A1/A2/A3.
//
// CONTRACT.
//   const result = await safeNavigate(router.push({ name: 'foo' }), '[FooView]')
//   // ^ resolves to undefined on success or benign failure
//   // ^ resolves to undefined and logs to console.error on hard failure
//   // ^ NEVER throws. NEVER rethrows.
//
// USAGE.
//   await safeNavigate(router.push('/'), '[LoginView] post-auth')
//   await safeNavigate(router.replace({ name: 'verify' }), '[RegisterView]')
//   safeNavigate(router.push(tab.path), `[CTabBar] tab ${tab.id}`)  // fire-and-forget OK
//
// NO-RETHROW CONTRACT (CRITICAL).
//   safeNavigate is deliberately no-throw. It DOES NOT rethrow benign or hard
//   NavigationFailure types. When a call site sits inside a try/catch designed
//   for ApiResponseError / ApiNetworkError handling, this contract prevents a
//   stray NavigationFailure from being misinterpreted as an API error and
//   surfacing as an "operation failed" toast on top of an actual success.
//
//   This is the exact scenario closed by BUG-28-01 and BUG-29-01 in review:
//   InstallmentView/PurchaseView/onboarding-views all had `await router.push`
//   inside a try-block; on benign NavigationFailure the outer catch fired and
//   the user saw a generic-error toast right after a successful transaction.
//
//   If a caller ever needs to know that navigation failed (e.g. to retry or
//   fall back), that is a different requirement and SHOULD NOT be added to
//   safeNavigate. Add a new helper instead (safeNavigateWithFallback, ...).
//   Keeping safeNavigate narrow protects every existing call site.
//
// LOG LEVEL.
//   Hard failures (unknown route, thrown guard, runtime error in the resolver)
//   surface as console.error -- they indicate a bug or broken assumption.
//   Benign failures (duplicated double-tap, cancelled by a newer navigation,
//   aborted by a guard) stay silent: they are part of normal router operation
//   and emitting a log every time would be noise.
//
// SPECIAL CASES KEPT INLINE.
//   useAvatar.ts:133 -- the zombie-staff-token guard path INTENTIONALLY treats
//   `aborted` as the expected outcome (the staff role guard is rejecting the
//   redirect on purpose) and logs at warn level for everything else. That is
//   a different filter shape and is not collapsed into this helper.
//
// =============================================================================

import { isNavigationFailure, NavigationFailureType } from 'vue-router'
import type { NavigationFailure } from 'vue-router'

/**
 * Wrap a router.push/replace promise so benign NavigationFailures are
 * silently swallowed and any other failure is logged with a context prefix.
 *
 * @param navigation - the Promise returned by router.push(...) or
 *                     router.replace(...). Pass the call directly so the
 *                     navigation target stays visible at the call site.
 * @param context    - prefix used in console.error on hard failure. By
 *                     convention `[ComponentName]` plus a short description,
 *                     e.g. `[LoginView] post-auth`. The helper appends
 *                     " navigation failed:" automatically.
 *
 * @returns A promise that resolves to undefined on success or on any
 *          NavigationFailure. NEVER throws.
 */
export async function safeNavigate(
  navigation: Promise<NavigationFailure | void | undefined>,
  context: string,
): Promise<void> {
  await navigation.catch((err: unknown) => {
    if (
      isNavigationFailure(err, NavigationFailureType.duplicated)
      || isNavigationFailure(err, NavigationFailureType.cancelled)
      || isNavigationFailure(err, NavigationFailureType.aborted)
    ) {
      return
    }
    console.error(`${context} navigation failed:`, err)
  })
}
