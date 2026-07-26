// =============================================================================
// AIVIS.ONE Frontend -- useAvatar Composable (Phase F3 + F5.1 B1)
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
//      call POST /staff/avatar/start, persist avatar token to aivis_token,
//      fetchMe (now returns target user), redirect to target dashboard.
//   2. endAvatarSession() — restore staff token from sessionStorage,
//      call POST /staff/avatar/end (uses staff token), fetchMe,
//      redirect to /staff/dashboard.
//
// Reload resilience:
//   - aivis_token in storage = avatar token (persisted)
//   - aivis_staff_token in sessionStorage = original staff token backup
//   - restoreSession() loads avatar token → fetchMe → target user
//   - App.vue checks isAvatarActive → shows banner
//
// F5.1 B1 -- data store reset on identity flip.
//   Both transitions call resetAllDataStores() right before fetchMe().
//   Without this, dashboard/portfolio/transactions etc. carry the
//   PREVIOUS identity's data through the token swap until the next
//   view's onMounted refresh fires. That window was visible on slow
//   networks (200ms+ between fetchMe resolve and the destination
//   view mounting). Reset before fetchMe means:
//     - the new identity's first render is from a clean baseline
//     - any in-flight fetch from the previous identity (each store's
//       reset bumps its FP-17 epoch first) drops silently on resolve
//   Catch paths reset too: token may have been swapped before the
//   error fired, leaving stores keyed against a different identity
//   than the restored token.
// =============================================================================

import { computed, ref } from 'vue'
import {
  isNavigationFailure,
  NavigationFailureType,
  useRouter,
} from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setAuthToken, getAuthToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { startAvatar, endAvatar } from '@/api/admin'
import { useToast } from '@/composables/useToast'
import { safeNavigate } from '@/composables/safeNavigate'
import { getRoleDashboard } from '@/router/guards'
import { platform } from '@/platform'
import { avatarActive, setAvatarActive, STAFF_TOKEN_KEY } from '@/composables/avatarState'
import { resetAllDataStores } from '@/stores/sessionReset'

const TOKEN_KEY = 'aivis_token'

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

      // 3. Persist avatar token to aivis_token storage (so reload works).
      const storage = _getMainStorage()
      storage.setItem(TOKEN_KEY, resp.session_token)
      setAuthToken(resp.session_token)

      // 4. Reset data stores BEFORE fetchMe -- staff's prior state
      // (if any) must not leak into target user's first render. See
      // file header "F5.1 B1".
      resetAllDataStores()

      // 5. Refresh user — now returns target user.
      await authStore.fetchMe()

      // 6. Update reactive flag.
      setAvatarActive(true)

      showToast(t('staff.avatar.started'), 'success')

      // 7. Redirect to target user's dashboard.
      // safeNavigate is no-throw by contract -- critical here so a
      // benign NavigationFailure does NOT bubble into the outer
      // rollback `catch` below, which would restore the staff token
      // despite a fully successful API call and token swap.
      const targetDashboard = getRoleDashboard(authStore.role)
      await safeNavigate(
        router.push(targetDashboard),
        '[useAvatar] to target dashboard',
      )
    } catch {
      // Rollback: restore staff token on failure (memory + storage).
      const savedToken = sessionStorage.getItem(STAFF_TOKEN_KEY)
      if (savedToken) {
        setAuthToken(savedToken)
        _getMainStorage().setItem(TOKEN_KEY, savedToken)
      }
      setAvatarActive(false)
      // The token may already have been swapped to the avatar's by
      // the time the error fired. Reset so a successful login that
      // follows starts from a clean baseline rather than from
      // whichever identity the in-flight fetchMe was reaching for.
      resetAllDataStores()
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
      // SPECIAL CASE -- intentionally NOT using safeNavigate here.
      // The general helper treats `aborted` as a benign type to silently
      // ignore; here `aborted` is the EXPECTED outcome (staff role guard
      // rejecting the redirect because the role is now gone), and any
      // other failure should log at warn level (not error) since the
      // user-facing impact is bounded -- they stay on the current view
      // with a toast already shown. Different filter shape -> inline.
      await router.push('/staff/dashboard').catch((err: unknown) => {
        if (isNavigationFailure(err, NavigationFailureType.aborted)) {
          return
        }
        console.warn('[useAvatar] zombie-flag navigation failed:', err)
      })
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

      // 5. Reset data stores BEFORE fetchMe -- target user's
      // dashboard/portfolio/transactions data must not survive into
      // the staff session. See file header "F5.1 B1".
      resetAllDataStores()

      // 6. Refresh user — now returns staff user.
      await authStore.fetchMe()

      showToast(t('staff.avatar.ended'), 'success')

      // 7. Redirect to staff dashboard.
      // safeNavigate is no-throw by contract -- critical here so a
      // benign NavigationFailure does NOT bubble into the outer
      // rollback `catch` below, which would re-restore the staff
      // token and reset stores despite a fully successful endAvatar.
      await safeNavigate(
        router.push('/staff/dashboard'),
        '[useAvatar] to staff dashboard',
      )
    } catch {
      // Even if endAvatar API call fails, restore staff token to prevent desync.
      // The backend avatar session will expire by TTL.
      setAuthToken(staffToken)
      _getMainStorage().setItem(TOKEN_KEY, staffToken)
      setAvatarActive(false)
      // Clear any target-user state that might have been loaded
      // before the error fired. fetchMe in this catch is best-effort
      // and we want stores to start from a clean baseline regardless
      // of whether it succeeds.
      resetAllDataStores()
      await authStore.fetchMe().catch(() => { /* best effort */ })
      // We are already inside the outer rollback `catch` -- any rejection
      // from this push would otherwise become an unhandled rejection.
      // safeNavigate's no-throw contract guarantees containment here.
      await safeNavigate(
        router.push('/staff/dashboard'),
        '[useAvatar] rollback to staff dashboard',
      )
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
