// =============================================================================
// CBSHOME Frontend -- useAvatar Composable (Phase F3)
// =============================================================================
//
// Avatar mode state management. Staff operates as another user.
//
// State flag lives in composables/avatarState.ts (shared with stores/auth.ts
// to avoid circular imports). Auth store calls setAvatarActive(false) on
// _clearSession — prevents zombie flag after 401/logout.
//
// Token swap mechanic:
//   1. startAvatarSession() — save staff token to sessionStorage,
//      call POST /staff/avatar/start, persist avatar token to cbs_token,
//      fetchMe (now returns target user), redirect to target dashboard.
//   2. endAvatarSession() — restore staff token from sessionStorage,
//      call POST /staff/avatar/end (uses staff token), fetchMe,
//      redirect to /staff/dashboard.
//
// Reload resilience:
//   - cbs_token in storage = avatar token (persisted)
//   - cbs_staff_token in sessionStorage = original staff token backup
//   - restoreSession() loads avatar token → fetchMe → target user
//   - App.vue checks isAvatarActive → shows banner
// =============================================================================

import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setAuthToken, getAuthToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { startAvatar, endAvatar } from '@/api/admin'
import { useToast } from '@/composables/useToast'
import { getRoleDashboard } from '@/router/guards'
import { platform } from '@/platform'
import { avatarActive, setAvatarActive, STAFF_TOKEN_KEY } from '@/composables/avatarState'

const TOKEN_KEY = 'cbs_token'

export function useAvatar() {
  const router = useRouter()
  const { t } = useI18n()
  const authStore = useAuthStore()
  const { showToast } = useToast()

  const loading = ref(false)

  /** Whether avatar mode is currently active. */
  const isAvatarActive = computed(() => avatarActive.value)

  /**
   * Start avatar session.
   * Called from StaffAvatarView while staff token is active.
   */
  async function startAvatarSession(targetUserId: string): Promise<void> {
    loading.value = true
    try {
      // 1. Save current staff token.
      const currentToken = getAuthToken()
      if (!currentToken) throw new Error('No auth token')
      sessionStorage.setItem(STAFF_TOKEN_KEY, currentToken)

      // 2. Call start endpoint (uses staff token).
      const resp = await startAvatar(targetUserId)

      // 3. Persist avatar token to cbs_token storage (so reload works).
      const storage = _getMainStorage()
      storage.setItem(TOKEN_KEY, resp.session_token)
      setAuthToken(resp.session_token)

      // 4. Refresh user — now returns target user.
      await authStore.fetchMe()

      // 5. Update reactive flag.
      setAvatarActive(true)

      showToast(t('staff.avatar.started'), 'success')

      // 6. Redirect to target user's dashboard.
      const targetDashboard = getRoleDashboard(authStore.role)
      await router.push(targetDashboard)
    } catch {
      // Rollback: restore staff token on failure (memory + storage).
      const savedToken = sessionStorage.getItem(STAFF_TOKEN_KEY)
      if (savedToken) {
        setAuthToken(savedToken)
        _getMainStorage().setItem(TOKEN_KEY, savedToken)
      }
      setAvatarActive(false)
      showToast(t('common.error'), 'error')
    } finally {
      loading.value = false
    }
  }

  /**
   * End avatar session.
   * Called from avatar banner (any page).
   */
  async function endAvatarSession(): Promise<void> {
    loading.value = true

    // Guard: if staff token is gone (zombie flag after 401 → re-login),
    // just reset flag and redirect — don't call backend.
    const staffToken = sessionStorage.getItem(STAFF_TOKEN_KEY)
    if (!staffToken) {
      setAvatarActive(false)
      showToast(t('staff.avatar.ended'), 'warning')
      await router.push('/staff/dashboard').catch(() => { /* may not have staff role */ })
      loading.value = false
      return
    }

    try {
      // 1. Restore staff token BEFORE calling end (endpoint requires staff auth).
      setAuthToken(staffToken)

      // 2. Call end endpoint.
      await endAvatar()

      // 3. Persist staff token back to main storage.
      _getMainStorage().setItem(TOKEN_KEY, staffToken)

      // 4. Cleanup.
      setAvatarActive(false)

      // 5. Refresh user — now returns staff user.
      await authStore.fetchMe()

      showToast(t('staff.avatar.ended'), 'success')

      // 6. Redirect to staff dashboard.
      await router.push('/staff/dashboard')
    } catch {
      // Even if endAvatar API call fails, restore staff token to prevent desync.
      // The backend avatar session will expire by TTL.
      setAuthToken(staffToken)
      _getMainStorage().setItem(TOKEN_KEY, staffToken)
      setAvatarActive(false)
      await authStore.fetchMe().catch(() => { /* best effort */ })
      await router.push('/staff/dashboard')
      showToast(t('common.error'), 'error')
    } finally {
      loading.value = false
    }
  }

  /**
   * Get main token storage — uses platform detection (same as auth store).
   */
  function _getMainStorage(): Storage {
    return platform.getStorageDriver() === 'sessionStorage'
      ? sessionStorage
      : localStorage
  }

  return {
    isAvatarActive,
    loading,
    startAvatarSession,
    endAvatarSession,
  }
}
