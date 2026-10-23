// =============================================================================
// AIVIS.ONE Frontend -- useStaffRights
// =============================================================================
//
// The rights of the signed-in staff member as a plain object, read at the
// moment it is asked for. utils/staffRights.ts holds the rules (which section
// needs which right, which tab is drawn) as pure functions over a
// RightsContext; this composable builds that context from the auth store, so a
// router redirect, a guard and a component all read the rights the same way.
//
// `current()` reads the store each time it is called: call it inside a
// computed or a function, never once at setup, or a permission change in the
// same session is not seen.
// =============================================================================

import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { PERMISSION_KEYS, type RightsContext } from '@/utils/staffRights'

export function useStaffRights() {
  const { canDo, isAdmin } = useStaffPermissions()

  // Every permission's computed is made here, once, at setup -- not on the
  // first call of current(), which may run inside another computed.
  const byKey = new Map(PERMISSION_KEYS.map((key) => [key as string, canDo(key)]))

  function current(): RightsContext {
    return {
      can: (key) => byKey.get(key)?.value === true,
      admin: isAdmin.value,
    }
  }

  return { current }
}
