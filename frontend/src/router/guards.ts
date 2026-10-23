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
//   4. Agreement — an integrator who has not accepted the agent-integrator
//      agreement sees the acceptance screen and nothing else
//
// Route meta flags:
//   public         — skip all checks, allow unauthenticated access
//   skipOnboarding — skip onboarding redirect (for onboarding routes)
//   roles          — allowed roles (string[]), empty = any authenticated
//   permission     — staff permission the route needs (P-88)
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
import { useStaffPermissions, type StaffPermissionKey } from '@/composables/useStaffPermissions'
import { useAuthStore } from '@/stores/auth'
import { useAgentAgreementStore } from '@/stores/agentAgreement'
import { avatarActive } from '@/composables/avatarState'
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
    /** Staff permission this route needs, on top of `roles` (P-88).
     *
     *  THE ROUTE'S PERMISSION IS A FACT ABOUT THE ROUTE, and this is
     *  the only place it is written. Hiding the nav entry was never a
     *  lock: a typed URL walked straight past it and the screen refused
     *  with a 403 after mounting -- an empty page and a toast. Anything
     *  that needs to know which permission a route wants (the platform
     *  tab bar, for one) reads it back off the route record rather than
     *  repeating the key. */
    permission?: StaffPermissionKey
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

// H10: verification is no longer a step in this funnel, so role_selected
// now leads straight to the documents page -- the destination kyc_done
// used to hold. A user who arrives on an old session carrying the
// removed step falls through to the role dashboard rather than to a
// route that no longer exists.
const ONBOARDING_REDIRECTS: Record<string, string> = {
  registered: '/verify',
  // No profile screen and no role card: an account left on either step is
  // brought to the documents step, which re-checks the step on its own.
  email_verified: '/onboarding/docs',
  profile_complete: '/onboarding/docs',
  role_selected: '/onboarding/docs',
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
// An integrator stays in the integrator shell
// ---------------------------------------------------------------------------

// The screens an integrator shares with a buyer exist under both shells. A
// link, a notification or a screen that names the buyer's route sends an
// integrator to the same screen in their own shell, with its own tab bar and
// menu -- never to the buyer's shell.
const SHARED_SCREENS: ReadonlySet<string> = new Set([
  'dashboard',
  'portfolio',
  'company-position',
  'companies',
  'company-overview',
  'company-products',
  'product-detail',
  'purchase',
  'installment',
  'installment-plans',
  'installment-plan-detail',
  'balance',
  'deposit',
  'transactions',
  'events',
  'news',
  'event',
  'post',
  'docs',
  'settings',
  'support',
  'faq',
  'notifications',
])

/** The acceptance screen an integrator is held on until the agreement is accepted. */
export const AGENT_WELCOME_ROUTE = 'agent-welcome'

/** The integrator-shell route for a buyer-shell route name, or null. */
export function agentCounterpart(name: unknown): string | null {
  if (typeof name !== 'string' || !name.startsWith('investor-')) return null
  const suffix = name.slice('investor-'.length)
  if (suffix === 'more') return 'agent-settings'
  return SHARED_SCREENS.has(suffix) ? `agent-${suffix}` : null
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
export async function globalGuard(to: RouteLocationNormalized): Promise<void | RouteLocationRaw> {
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
    if (authStore.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
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

  // --- An integrator never lands in the buyer's shell ---
  if (authStore.role === 'agent') {
    const counterpart = agentCounterpart(to.name)
    if (counterpart) {
      return { name: counterpart, params: to.params, query: to.query, hash: to.hash }
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

  // --- The agent-integrator agreement ---
  // Until it is accepted an integrator can do nothing in the cabinet but accept
  // it: every screen leads to the acceptance screen. When the document does not
  // exist (nothing can be accepted) the support screen stays open, so the
  // person can write to support. A staff member operating as the person only
  // looks and never accepts for them.
  if (authStore.role === 'agent' && !avatarActive.value) {
    const status = await useAgentAgreementStore().ensure()
    if (to.name === AGENT_WELCOME_ROUTE) {
      if (status === 'signed') return { name: 'agent-dashboard' }
    } else if (status !== 'signed') {
      if (status === 'missing' && to.name === 'agent-support') return
      return { name: AGENT_WELCOME_ROUTE }
    }
  }

  // --- Staff permission check (P-88) ---
  // Refused the same way a wrong role is: back to the dashboard, before
  // the screen mounts. The screen's own 403 stays where it is -- it
  // answers a server that refused a request, which is a different
  // event from "you may not go here" and survives a stale session this
  // guard cannot see.
  const needed = to.meta.permission
  if (needed) {
    const { canDo } = useStaffPermissions()
    if (!canDo(needed).value) {
      return getRoleDashboard(authStore.role)
    }
  }
}
