import type { Router, RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useOnboardingStore } from '@/stores/onboarding'
import { platform } from '@/platform'

import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    roles?: string[]
    platform?: 'standalone' | 'telegram' | 'any'
    isPublic?: boolean
  }
}

export const ROLE_ROUTES: Record<string, string> = {
  investor: '/investor/dashboard',
  agent: '/agent/dashboard',
  company: '/company/dashboard',
  staff: '/staff/dashboard',
}

function getDashboardForRole(role: string | null): string {
  return ROLE_ROUTES[role ?? ''] || '/investor/dashboard'
}

function isOnboardingRelatedRoute(to: RouteLocationNormalized): boolean {
  return (
    to.path.includes('/profile/edit') || to.path.includes('/kyc') || to.path.includes('/documents')
  )
}

export function setupGuards(router: Router): void {
  router.beforeEach((to) => {
    const authStore = useAuthStore()

    // Public routes — always allow
    if (to.meta.isPublic) {
      // If already authenticated and going to login, redirect to dashboard
      if (authStore.isAuthenticated && to.path === '/auth/login') {
        return getDashboardForRole(authStore.userRole)
      }
      return true
    }

    // No auth required — allow
    if (!to.meta.requiresAuth) {
      return true
    }

    // Auth required but not authenticated — redirect to login with returnUrl
    if (!authStore.isAuthenticated) {
      return {
        path: '/auth/login',
        query: { returnUrl: to.fullPath },
      }
    }

    // Onboarding check — redirect to wizard if incomplete
    const onboardingStore = useOnboardingStore()
    if (!onboardingStore.isComplete && to.path !== '/onboarding' && !isOnboardingRelatedRoute(to)) {
      return '/onboarding'
    }
    // If onboarding is complete and user navigates to /onboarding, redirect to dashboard
    if (onboardingStore.isComplete && to.path === '/onboarding') {
      return getDashboardForRole(authStore.userRole)
    }

    // Role check — if route specifies allowed roles, verify
    if (to.meta.roles && to.meta.roles.length > 0) {
      const userRole = authStore.userRole
      if (!userRole || !to.meta.roles.includes(userRole)) {
        return getDashboardForRole(userRole)
      }
    }

    // Platform check
    if (to.meta.platform && to.meta.platform !== 'any') {
      if (to.meta.platform !== platform.type) {
        return getDashboardForRole(authStore.userRole)
      }
    }

    return true
  })
}
