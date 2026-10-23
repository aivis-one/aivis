// =============================================================================
// AIVIS.ONE Frontend -- Re-reading the account when its role may have changed
// =============================================================================
//
// A buyer whose integrator application is approved becomes an integrator on
// the server. The cabinet learns it without a new sign-in:
//   - when a notification of type `agent_application.approved` arrives (the
//     unread badge rose and the newest notifications hold one), and
//   - whenever the app is opened again or brought back to the screen
//     (visibilitychange).
// Each time the account is read again (authStore.fetchMe); if the role is now
// the integrator's, the person is taken to the integrator's cabinet, where the
// router guard shows the agreement acceptance screen first.
//
// Only a buyer can become an integrator, so nothing is read for other roles.
// =============================================================================

import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listNotifications } from '@/api/notifications'
import { avatarActive } from '@/composables/avatarState'
import { safeNavigate } from '@/composables/safeNavigate'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'

export const APPROVED_NOTIFICATION_TYPE = 'agent_application.approved'

export function useRoleRefresh(): void {
  const router = useRouter()
  const authStore = useAuthStore()
  const notifications = useNotificationsStore()
  let busy = false

  // Read afresh: the account has been re-read since the role was last checked.
  const currentRole = (): string | null => authStore.role

  async function refreshAccount(): Promise<void> {
    if (busy || !authStore.isAuthenticated || authStore.role !== 'investor' || avatarActive.value) {
      return
    }
    busy = true
    try {
      await authStore.fetchMe()
      if (currentRole() === 'agent') {
        await safeNavigate(router.replace({ name: 'agent-dashboard' }), '[useRoleRefresh] to cabinet')
      }
    } catch {
      // A passive refresh: the next trigger tries again.
    } finally {
      busy = false
    }
  }

  async function approvalArrived(): Promise<boolean> {
    try {
      const page = await listNotifications({ limit: 10 })
      return page.items.some((n) => n.type === APPROVED_NOTIFICATION_TYPE && !n.read_at)
    } catch {
      return false
    }
  }

  function onVisibility(): void {
    if (document.visibilityState === 'visible') void refreshAccount()
  }

  watch(
    () => notifications.unreadCount,
    async (now, before) => {
      if (now <= before || authStore.role !== 'investor') return
      if (await approvalArrived()) await refreshAccount()
    },
  )

  onMounted(() => document.addEventListener('visibilitychange', onVisibility))
  onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisibility))
}
