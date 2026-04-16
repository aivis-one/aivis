// =============================================================================
// CBSHOME Frontend -- useAvatar Composable (Phase F3 fix)
// =============================================================================
//
// Avatar mode state management. Staff operates as another user.
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
//   - cbs_token in storage = avatar token (persisted via _persistToken)
//   - cbs_staff_token in sessionStorage = original staff token backup
//   - restoreSession() loads avatar token → fetchMe → target user
//   - App.vue checks isAvatarActive → shows banner
//
// Exit:
//   - Banner "Return to Staff" → endAvatarSession()
//   - Staff routes inaccessible during avatar (role != staff) — correct
// =============================================================================

import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setAuthToken, getAuthToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { startAvatar, endAvatar } from '@/api/admin'
import { useToast } from '@/composables/useToast'
import { getRoleDashboard } from '@/router/guards'

const STAFF_TOKEN_KEY = 'cbs_staff_token'
const TOKEN_KEY = 'cbs_token'

// Shared reactive flag — survives component unmount, reset on end/logout.
const _avatarActive = ref(!!sessionStorage.getItem(STAFF_TOKEN_KEY))

export function useAvatar() {
  const router = useRouter()
  const { t } = useI18n()
  const authStore = useAuthStore()
  const { showToast } = useToast()

  const loading = ref(false)

  /** Whether avatar mode is currently active. */
  const isAvatarActive = computed(() => _avatarActive.value)

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
      _avatarActive.value = true

      showToast(t('staff.avatar.started'), 'success')

      // 6. Redirect to target user's dashboard.
      const targetDashboard = getRoleDashboard(authStore.role)
      await router.push(targetDashboard)
    } catch {
      // Rollback: restore staff token on failure.
      const savedToken = sessionStorage.getItem(STAFF_TOKEN_KEY)
      if (savedToken) {
        setAuthToken(savedToken)
        sessionStorage.removeItem(STAFF_TOKEN_KEY)
      }
      _avatarActive.value = false
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
    try {
      // 1. Restore staff token BEFORE calling end (endpoint requires staff auth).
      const staffToken = sessionStorage.getItem(STAFF_TOKEN_KEY)
      if (!staffToken) throw new Error('No staff token in sessionStorage')
      setAuthToken(staffToken)

      // 2. Call end endpoint.
      await endAvatar()

      // 3. Persist staff token back to main storage.
      const storage = _getMainStorage()
      storage.setItem(TOKEN_KEY, staffToken)

      // 4. Cleanup sessionStorage.
      sessionStorage.removeItem(STAFF_TOKEN_KEY)
      _avatarActive.value = false

      // 5. Refresh user — now returns staff user.
      await authStore.fetchMe()

      showToast(t('staff.avatar.ended'), 'success')

      // 6. Redirect to staff dashboard.
      await router.push('/staff/dashboard')
    } catch {
      showToast(t('common.error'), 'error')
    } finally {
      loading.value = false
    }
  }

  /**
   * Get main token storage (mirrors auth store logic).
   */
  function _getMainStorage(): Storage {
    // Platform detection: Telegram uses sessionStorage, standalone uses localStorage.
    // Safe fallback: check where cbs_token currently lives.
    if (localStorage.getItem(TOKEN_KEY)) return localStorage
    if (sessionStorage.getItem(TOKEN_KEY)) return sessionStorage
    return localStorage
  }

  return {
    isAvatarActive,
    loading,
    startAvatarSession,
    endAvatarSession,
  }
}
