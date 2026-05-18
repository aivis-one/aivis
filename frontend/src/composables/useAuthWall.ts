// =============================================================================
// CBSHOME Frontend -- useAuthWall Composable (iter 2.6 R1 §1.6.5)
// =============================================================================
//
// Gating helper for public-flow views. Wraps the "if not authenticated,
// bounce to register with ?next= and ?intent=" pattern so every public
// CTA shares one canonical implementation.
//
// CONTRACT.
//   const { requireAuth } = useAuthWall()
//   function buyNow() {
//     if (!requireAuth('purchase')) return  // navigation already fired
//     // ... authenticated path: open purchase flow
//   }
//
//   - Returns true when the visitor is already authenticated -- caller
//     proceeds to the action.
//   - Returns false after pushing onto the router; caller short-circuits.
//
// REDIRECT TARGET.
//   `register` (NOT `login`). A visitor arriving from a marketing link
//   most commonly does not yet have an account; the Register screen
//   carries a "already have an account?" link to LoginView, and
//   LoginView propagates the `?next=` query (iter 2.6 Batch 2). Pushing
//   straight to login for the no-account-yet majority would force an
//   extra tap.
//
// QUERY PARAMETERS.
//   next   = route.fullPath of the public page the visitor was on
//            (e.g. `/public/products/abc-123`). LoginView (Batch 2)
//            reads this after a successful sign-in and `router.replace`s
//            to it. RegisterView in this iteration does NOT honour
//            `next` -- a deliberate simplification (iter 2.6 plan, §A4):
//            after register + multi-step onboarding the visitor lands
//            on their role dashboard, not back on the public page. The
//            indirection through onboarding is not worth the moving
//            parts at this stage; we can wire it later if a real UX
//            pain point shows up.
//   intent = the `action` string from the caller, e.g. 'purchase'.
//            Plumbed through end-to-end so future flows can branch on
//            it (e.g. intent='apply_agent' could land the visitor on
//            an agent application form instead of the storefront).
//            iter 2.6 does not consume this value -- it is preserved
//            as a forward-compatible passthrough only.
//
// NO SIDE EFFECTS WHEN AUTHED.
//   Calling requireAuth() on an authenticated visitor is a pure check
//   -- no navigation, no toast, no flag flip. The caller's `return`
//   path is fully responsible for what happens next.
//
// R20 FIX (STYLE-20-01).
//   router.push() returns a Promise that rejects on navigation failures.
//   Previously this Promise was discarded via `void`, silencing real
//   bugs (missing route, guard rejection, ...) as well as benign ones.
//   We now `.catch` it and log only the real bugs. NavigationFailure
//   of type `duplicated` / `cancelled` / `aborted` is expected on
//   rapid double-tap or guard pre-emption and would otherwise drown
//   out useful diagnostics.
// =============================================================================

import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { safeNavigate } from '@/composables/safeNavigate'

export function useAuthWall() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()

  /**
   * Gate a privileged action behind authentication.
   *
   * @param action - intent tag for the auth-wall navigation. Stored
   *                 in the `?intent=` query parameter for downstream
   *                 consumers (forward-compatible; unused in iter 2.6).
   * @returns true  - visitor is authenticated; caller proceeds.
   * @returns false - visitor is anonymous; navigation to /register has
   *                  been pushed; caller must short-circuit.
   */
  function requireAuth(action: string): boolean {
    if (auth.isAuthenticated) return true
    void safeNavigate(
      router.push({
        name: 'register',
        query: {
          next: route.fullPath,
          intent: action,
        },
      }),
      '[useAuthWall] to register',
    )
    return false
  }

  return { requireAuth }
}
