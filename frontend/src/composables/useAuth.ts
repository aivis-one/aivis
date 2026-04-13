import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ROLE_ROUTES } from '@/router/guards'

export function useAuth() {
  const store = useAuthStore()
  const router = useRouter()

  const isAuthenticated = computed(() => store.isAuthenticated)
  const user = computed(() => store.user)
  const userRole = computed(() => store.userRole)
  const loading = computed(() => store.loading)
  const error = computed(() => store.error)

  async function login(email: string, password: string) {
    await store.login(email, password)
    redirectByRole()
  }

  async function logout() {
    await store.logout()
    router.push('/auth/login')
  }

  function redirectByRole() {
    // Check for returnUrl from guard redirect
    const returnUrl = router.currentRoute.value.query.returnUrl as string | undefined
    if (returnUrl && returnUrl.startsWith('/')) {
      router.push(returnUrl)
      return
    }

    const role = store.userRole
    router.push(ROLE_ROUTES[role ?? ''] || '/investor/dashboard')
  }

  return {
    isAuthenticated,
    user,
    userRole,
    loading,
    error,
    login,
    logout,
    redirectByRole,
  }
}
