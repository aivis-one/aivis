// =============================================================================
// AIVIS.ONE Frontend -- useStaffPermissions Composable (iter 2.7 Block A4)
// =============================================================================
//
// Reads the effective staff permission dict surfaced on
// authStore.user.staff_profile.permissions (iter 2.6c B6 -- backend
// merges DEFAULT_STAFF_PERMISSIONS with per-staff overrides before
// returning, so the dict always carries every known permission key
// with a definitive boolean value).
//
// API.
//   const { canDo, requireStaff } = useStaffPermissions()
//
//   canDo('content_manage')   // ComputedRef<boolean>, true iff staff
//                             // AND effective permission is true.
//   requireStaff.value         // boolean -- truthy iff user has a
//                             // staff_profile at all (master gate
//                             // for the Platform tab and every other
//                             // staff-only surface).
//
// USAGE.
//   <template>
//     <!-- FP-23 template guard: hide the CTA when permission is
//          missing rather than letting the user tap it and get a 403
//          toast a second later. -->
//     <CButton
//       v-if="canDoContentManage"
//       :label="t('staff.platform.news.createCta')"
//       @click="onCreate"
//     />
//   </template>
//
//   <script setup lang="ts">
//   import { useStaffPermissions } from '@/composables/useStaffPermissions'
//
//   const { canDo } = useStaffPermissions()
//   const canDoContentManage = canDo('content_manage')
//
//   // FP-23 defensive check: belt-and-braces in case the template
//   // guard regresses or the user races a session change. console.warn
//   // lands in logs without throwing.
//   function onCreate() {
//     if (!canDoContentManage.value) {
//       console.warn('[StaffNewsView] onCreate blocked: no content_manage')
//       return
//     }
//     // ... real handler ...
//   }
//   </script>
//
// PERMISSION KEY TYPE.
//   StaffPermissionKey = keyof Required<UpdatePermissionsRequest> --
//   the full set of permission keys the backend schema accepts on
//   write. As of iter 2.7 A6 that includes content_manage (the A6
//   schema-sync mini-iter added it to UpdatePermissionsRequest, so
//   the earlier `| 'content_manage'` extension term is no longer
//   needed -- keyof already yields it). The effective dict surfaced
//   via /users/me always carries every key with a definitive
//   boolean, so any of them is safe to read through canDo().
//
// MEMOIZATION.
//   `canDo` returns a `computed` -- multiple template references to
//   the same permission share the same reactive computation. The
//   composable itself caches one computed per key inside a Map so
//   repeated calls to canDo('content_manage') from different views
//   in the same setup() instance still return the same ref.
// =============================================================================

import { computed, type ComputedRef } from 'vue'

import { useAuthStore } from '@/stores/auth'
import type { UpdatePermissionsRequest } from '@/api/types'

/**
 * Permission keys readable through canDo().
 *
 * Derived from the backend UpdatePermissionsRequest schema, which
 * since iter 2.7 A6 carries all nine keys (content_manage included).
 * The effective dict on /users/me mirrors DEFAULT_STAFF_PERMISSIONS,
 * so every key resolves to a definitive boolean at read time.
 */
export type StaffPermissionKey = keyof Required<UpdatePermissionsRequest>

/**
 * Read-only access to the current user's effective staff permissions.
 *
 * The hook is plain -- it does not register watchers, does not fetch
 * anything, does not subscribe to a store event. It pulls from
 * authStore.user reactively and returns derived computeds. Calling it
 * many times in the same component is cheap; the cached canDo Map
 * makes repeated reads of the same key share the same ref.
 */
export function useStaffPermissions() {
  const authStore = useAuthStore()

  /** True iff the user has a staff_profile (= role 'staff', master gate). */
  const requireStaff: ComputedRef<boolean> = computed(() => authStore.user?.staff_profile != null)

  // Per-key memoization. Vue's `computed` is cheap but each canDo call
  // would otherwise create a fresh ref. Caching by key means a view
  // that templates the same permission multiple times keeps the same
  // computed instance.
  const cache = new Map<StaffPermissionKey, ComputedRef<boolean>>()

  /**
   * Compute the effective state of a single permission key.
   *
   * Returns a ComputedRef so the template can react to login/logout
   * or to a permission patch in the same session. Always false when
   * the user is not staff (no staff_profile = no permissions).
   */
  function canDo(key: StaffPermissionKey): ComputedRef<boolean> {
    const cached = cache.get(key)
    if (cached) return cached

    const ref = computed<boolean>(() => {
      const profile = authStore.user?.staff_profile
      if (!profile) return false
      // The effective dict surfaced by build_user_response() always
      // carries every known key with a definitive boolean. We index
      // by string -- the TS type tells the caller which keys are
      // valid; the runtime accepts a missing key as `undefined` and
      // !!undefined === false, so a stale frontend reading a
      // permission removed on the backend degrades to "denied"
      // rather than crashing.
      return profile.permissions?.[key] === true
    })

    cache.set(key, ref)
    return ref
  }

  return {
    requireStaff,
    canDo,
  }
}
