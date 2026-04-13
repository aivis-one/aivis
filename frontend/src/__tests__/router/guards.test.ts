import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ROLE_ROUTES } from '@/router/guards'
import type { RouteLocationNormalized } from 'vue-router'

// Hoisted mock for auth store state
const mockAuthState = vi.hoisted(() => ({
  isAuthenticated: false,
  userRole: null as string | null,
  user: null as { onboarding_step: string } | null,
}))

const mockOnboardingState = vi.hoisted(() => ({
  isComplete: true,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => mockAuthState,
}))

vi.mock('@/stores/onboarding', () => ({
  useOnboardingStore: () => mockOnboardingState,
}))

vi.mock('@/platform', () => ({
  platform: { type: 'standalone' },
}))

function makeRoute(overrides: Partial<RouteLocationNormalized> = {}): RouteLocationNormalized {
  return {
    path: '/test',
    fullPath: '/test',
    name: 'test',
    hash: '',
    query: {},
    params: {},
    matched: [],
    redirectedFrom: undefined,
    meta: {},
    ...overrides,
  } as RouteLocationNormalized
}

// Extract the guard function by capturing it from router.beforeEach
let guardFn: (
  to: RouteLocationNormalized,
) => ReturnType<ReturnType<(typeof import('vue-router'))['createRouter']>['beforeEach']>

// We need to capture the beforeEach callback from setupGuards
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
  }
})

describe('router guards', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    // Reset mock state
    mockAuthState.isAuthenticated = false
    mockAuthState.userRole = null
    mockAuthState.user = null

    // Re-import to get fresh guard setup
    vi.resetModules()

    // Dynamically import the guards module and capture the beforeEach callback
    const guardsModule = await import('@/router/guards')

    // Create a mock router to capture the guard
    const capturedGuards: ((to: RouteLocationNormalized) => unknown)[] = []
    const mockRouter = {
      beforeEach: (fn: (to: RouteLocationNormalized) => unknown) => {
        capturedGuards.push(fn)
      },
    }

    guardsModule.setupGuards(mockRouter as never)
    guardFn = capturedGuards[0] as typeof guardFn
  })

  describe('ROLE_ROUTES', () => {
    it('maps all 4 roles to dashboard paths', () => {
      expect(ROLE_ROUTES.investor).toBe('/investor/dashboard')
      expect(ROLE_ROUTES.agent).toBe('/agent/dashboard')
      expect(ROLE_ROUTES.company).toBe('/company/dashboard')
      expect(ROLE_ROUTES.staff).toBe('/staff/dashboard')
    })
  })

  describe('public routes', () => {
    it('allows unauthenticated access', () => {
      const to = makeRoute({ meta: { isPublic: true }, path: '/auth/register' })
      expect(guardFn(to)).toBe(true)
    })

    it('redirects authenticated user from login to role dashboard', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      const to = makeRoute({ meta: { isPublic: true }, path: '/auth/login' })
      expect(guardFn(to)).toBe('/investor/dashboard')
    })

    it('allows authenticated user on non-login public routes', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      const to = makeRoute({ meta: { isPublic: true }, path: '/auth/register' })
      expect(guardFn(to)).toBe(true)
    })
  })

  describe('no auth required', () => {
    it('allows access when requiresAuth is not set', () => {
      const to = makeRoute({ meta: {} })
      expect(guardFn(to)).toBe(true)
    })
  })

  describe('auth required', () => {
    it('redirects to login with returnUrl when not authenticated', () => {
      const to = makeRoute({
        meta: { requiresAuth: true },
        fullPath: '/investor/dashboard',
      })
      const result = guardFn(to)
      expect(result).toEqual({
        path: '/auth/login',
        query: { returnUrl: '/investor/dashboard' },
      })
    })
  })

  describe('onboarding check', () => {
    it('redirects to onboarding when incomplete', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = false

      const to = makeRoute({
        meta: { requiresAuth: true },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe('/onboarding')
    })

    it('allows access when onboarding is complete', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe(true)
    })

    it('allows access to onboarding route even if incomplete', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = false

      const to = makeRoute({
        meta: { requiresAuth: true },
        path: '/onboarding',
      })
      expect(guardFn(to)).toBe(true)
    })

    it('allows onboarding-related routes when incomplete', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = false

      const profileEdit = makeRoute({
        meta: { requiresAuth: true },
        path: '/investor/profile/edit',
      })
      expect(guardFn(profileEdit)).toBe(true)

      const kyc = makeRoute({ meta: { requiresAuth: true }, path: '/investor/kyc' })
      expect(guardFn(kyc)).toBe(true)

      const docs = makeRoute({ meta: { requiresAuth: true }, path: '/investor/documents' })
      expect(guardFn(docs)).toBe(true)
    })

    it('redirects to dashboard when complete and navigating to /onboarding', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({ meta: { requiresAuth: true }, path: '/onboarding' })
      expect(guardFn(to)).toBe('/investor/dashboard')
    })
  })

  describe('role check', () => {
    it('allows access when user role is in allowed roles', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true, roles: ['investor', 'agent'] },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe(true)
    })

    it('redirects to dashboard when role not in allowed list', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'company'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true, roles: ['investor', 'agent'] },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe('/company/dashboard')
    })

    it('redirects to investor dashboard for unknown role', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = null
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true, roles: ['investor'] },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe('/investor/dashboard')
    })

    it('allows access when no roles specified in meta', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'staff'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true },
        path: '/some/route',
      })
      expect(guardFn(to)).toBe(true)
    })
  })

  describe('platform check', () => {
    it('allows access when platform matches', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true, platform: 'standalone' },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe(true)
    })

    it('redirects when platform does not match', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true, platform: 'telegram' },
        path: '/some/route',
      })
      expect(guardFn(to)).toBe('/investor/dashboard')
    })

    it('allows access when platform is any', () => {
      mockAuthState.isAuthenticated = true
      mockAuthState.userRole = 'investor'
      mockAuthState.user = { onboarding_step: '' }
      mockOnboardingState.isComplete = true

      const to = makeRoute({
        meta: { requiresAuth: true, platform: 'any' },
        path: '/investor/dashboard',
      })
      expect(guardFn(to)).toBe(true)
    })
  })
})
