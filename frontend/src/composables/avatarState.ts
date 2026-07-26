// =============================================================================
// AIVIS.ONE Frontend -- Avatar State (shared module)
// =============================================================================
//
// Extracted from useAvatar to break circular import:
//   useAvatar → stores/auth (for fetchMe)
//   stores/auth → avatarState (for cleanup on _clearSession)
//
// Both useAvatar.ts and stores/auth.ts import from here — no cycle.
// =============================================================================

import { ref } from 'vue'

export const STAFF_TOKEN_KEY = 'cbs_staff_token'

/** Shared reactive flag — true when staff is operating as another user. */
export const avatarActive = ref(!!sessionStorage.getItem(STAFF_TOKEN_KEY))

/** Set avatar active state. When deactivating, also cleans sessionStorage. */
export function setAvatarActive(value: boolean): void {
  avatarActive.value = value
  if (!value) {
    sessionStorage.removeItem(STAFF_TOKEN_KEY)
  }
}
