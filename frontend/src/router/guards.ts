// =============================================================================
// AIVIS.ONE Frontend -- Router Guards (Phase F2.2 + F4.1.5 polish
//                                     + iter 2.6 batch 2)
// =============================================================================
//
// Global navigation guard registered as router.beforeEach().
// Handles three concerns in order:
//   1. Auth — unauthenticated users → /login (with ?next= propagation)
//   2. Onboarding — incomplete onboarding → appropriate step
//   3. Role — wrong role → role-specific dashboard
//
// Route meta flags:
//   public         — skip all checks, allow unauthenticated access
//   skipOnboarding — skip onboarding redirect (for onboarding routes)
//   roles          — allowed roles (string[]), empty = any authenticated
//   shell          — which shell wraps this route; read by shared views
//                    via router/helpers.ts (F4.1.5)
//
// iter 2.6 batch 2:
//   The unauthenticated branch (step 1) now preserves the requested
//   `fullPath` as `?next=` on the redirect. LoginView reads `next` and
//   replace()s back to it after a successful sign-in, so a deep-linked
//   anonymous visit -> login -> intended page is one round-trip instead
//   of dumping the user on their dashboard. The root path (`/`) is
//   excluded -- redirecting to /login?next=/ would replace back to /
//   after auth, which then bounces via root.beforeEnter anyway. Public
//   routes are handled by the earlier branch; this propagation only
//   fires for protected routes.
// =============================================================================

import type { RouteLocationNormalized, RouteLocationRaw } from 'vue-router'

import { useAuth } from '@/composables/useAuth'
import { useAuthStore } from '@/stores/auth'
import type { Shell } from './helpers'

// ---------------------------------------------------------------------------
// Route meta augmentation
// ---------------------------------------------------------------------------

declare module 'vue-router' {
  interface RouteMeta {
    /** Route accessible without authentication. */
    public?: boolean
    /** Allowed user roles. Empty/undefined = any authenticated role. */
    roles?: string[]
    /** Skip onboarding redirect (for onboarding routes themselves). */
    skipOnboarding?: boolean
    /** Which shell wraps this route. Set on shell wrapper records
     *  and inherited by nested views via vue-router meta merge. */
    shell?: Shell
  }
}

// ---------------------------------------------------------------------------
// Onboarding step → redirect path
// ---------------------------------------------------------------------------

const ONBOARDING_REDIRECTS: Record<string, string> = {
  registered: '/verify',
  email_verified: '/onboarding/profile',
  profile_complete: '/onboarding/role',
  role_selected: '/onboarding/kyc',
  kyc_done: '/onboarding/docs',
}

// ---------------------------------------------------------------------------
// Role → default dashboard path
// ---------------------------------------------------------------------------

const ROLE_DASHBOARDS: Record<string, string> = {
  investor: '/investor/dashboard',
  agent: '/agent/dashboard',
  company: '/company/dashboard',
  staff: '/staff/dashboard',
}

/** Get the default dashboard path for a given role. Falls back to /login. */
export function getRoleDashboard(role: string | null): string {
  if (!role) return '/login'
  return ROLE_DASHBOARDS[role] ?? '/investor/dashboard'
}

// ---------------------------------------------------------------------------
// Global beforeEach guard
// ---------------------------------------------------------------------------

/**
 * Single global guard that handles auth, onboarding, and role checks.
 *
 * Returning `undefined` allows navigation to proceed.
 * Returning a RouteLocationRaw triggers a redirect.
 */
export async function globalGuard(
  to: RouteLocationNormalized,
): Promise<void | RouteLocationRaw> {
  const { waitUntilReady } = useAuth()
  const authStore = useAuthStore()

  // Always wait for auth initialization before making decisions.
  try {
    await waitUntilReady()
  } catch {
    // Auth init timed out — allow public routes, block everything else.
    if (to.meta.public) return
    return { name: 'login' }
  }

  // --- Public routes ---
  if (to.meta.public) {
    // Redirect authenticated users away from login/register.
    if (
      authStore.isAuthenticated
      && (to.name === 'login' || to.name === 'register')
    ) {
      return getRoleDashboard(authStore.role)
    }
    return
  }

  // --- Auth check ---
  if (!authStore.isAuthenticated) {
    // Preserve the requested URL as `?next=` so LoginView can replace()
    // back to it after a successful sign-in. Skip the root edge case
    // (`/` -> /login?next=/ is a pointless round-trip; root.beforeEnter
    // resolves the destination on its own once authed).
    const next = to.fullPath !== '/' ? to.fullPath : undefined
    return {
      name: 'login',
      query: next ? { next } : undefined,
    }
  }

  // --- Onboarding check (skip for onboarding routes themselves) ---
  if (!to.meta.skipOnboarding) {
    const step = authStore.user?.onboarding_step
    if (step && step in ONBOARDING_REDIRECTS) {
      const target = ONBOARDING_REDIRECTS[step]
      // Avoid infinite redirect loop.
      if (to.path !== target) {
        return target
      }
    }
  }

  // --- Role check ---
  const allowedRoles = to.meta.roles
  if (allowedRoles && allowedRoles.length > 0) {
    const userRole = authStore.role
    if (!userRole || !allowedRoles.includes(userRole)) {
      return getRoleDashboard(userRole)
    }
  }
}
