// =============================================================================
// AIVIS.ONE Frontend -- the staff cabinet's rights, in one place
// =============================================================================
//
// What a staff member sees follows what they may do. Three things live here
// and nowhere else, so the tab bar, the section chips, the first section a hub
// opens on and the buttons of the permission card cannot drift apart:
//
//   1. THE SECTIONS of each hub (Users, Finance, Platform) with the right each
//      one needs. A section whose right the member lacks is not drawn, and a
//      hub opens on the first section the member may use.
//   2. THE PRESETS of the permission card: four named sets of ticks the
//      administrator marks with one press.
//   3. THE ADMINISTRATOR MARK: the rights only the administrator holds
//      (appoint staff, change rights, change an e-mail, take a member off
//      duty). The backend decides them by "every permission is on"; the
//      screen reads the same fact (useStaffPermissions().isAdmin).
//
// The backend re-checks every call. Hiding is what the member is OFFERED, not
// the lock.
// =============================================================================

import type { StaffPermissionKey } from '@/composables/useStaffPermissions'

/** What the rights of the signed-in member say, read once. */
export interface RightsContext {
  /** True when the member holds this permission. */
  can: (key: StaffPermissionKey) => boolean
  /** True when the member holds every permission (the administrator). */
  admin: boolean
}

/** One door of a hub. */
export interface StaffSection {
  id: string
  path: string
  labelKey: string
  /** The permission the screen needs; none = open to any staff member. */
  permission?: StaffPermissionKey
  /** True when the screen is the administrator's only. */
  admin?: boolean
}

/** True when the member may use the section. */
export function sectionAllowed(section: StaffSection, rights: RightsContext): boolean {
  if (section.admin && !rights.admin) return false
  if (section.permission && !rights.can(section.permission)) return false
  return true
}

/** The sections the member may use, in their order. */
export function allowedSections(
  sections: readonly StaffSection[],
  rights: RightsContext,
): StaffSection[] {
  return sections.filter((section) => sectionAllowed(section, rights))
}

/** The first section the member may use; null when there is none. */
export function firstAllowedSection(
  sections: readonly StaffSection[],
  rights: RightsContext,
): StaffSection | null {
  return allowedSections(sections, rights)[0] ?? null
}

// ---------------------------------------------------------------------------
// The hubs
// ---------------------------------------------------------------------------

/** Users: the people, identity checks, integrator applications, avatar, support. */
export const USERS_SECTIONS: readonly StaffSection[] = [
  { id: 'users', path: '/staff/users', labelKey: 'staff.hub.users.list' },
  {
    id: 'agent-apps',
    path: '/staff/users/agent-apps',
    labelKey: 'staff.hub.users.agentApps',
    permission: 'agent_application_review',
  },
  {
    id: 'avatar',
    path: '/staff/users/avatar',
    labelKey: 'staff.hub.users.avatar',
    permission: 'avatar_mode',
  },
  { id: 'support', path: '/staff/users/support', labelKey: 'staff.hub.users.support' },
]

/** Finance: payments with the top-up queue, withdrawals, gifts, the money check. */
export const FINANCE_SECTIONS: readonly StaffSection[] = [
  {
    id: 'payments',
    path: '/staff/finance/payments',
    labelKey: 'staff.hub.finance.payments',
    permission: 'payment_review',
  },
  {
    id: 'withdrawals',
    path: '/staff/finance/withdrawals',
    labelKey: 'staff.hub.finance.withdrawals',
    permission: 'payment_review',
  },
  {
    id: 'gifts',
    path: '/staff/finance/gifts',
    labelKey: 'staff.hub.finance.gifts',
    permission: 'financial_operations',
  },
  {
    id: 'reconciliation',
    path: '/staff/finance/reconciliation',
    labelKey: 'staff.hub.finance.reconciliation',
    permission: 'financial_operations',
    admin: true,
  },
]

/** Platform: news, events, projects, the platform's settings. */
export const PLATFORM_SECTIONS: readonly StaffSection[] = [
  {
    id: 'news',
    path: '/staff/platform/news',
    labelKey: 'staff.platform.tabs.news',
    permission: 'content_manage',
  },
  {
    id: 'events',
    path: '/staff/platform/events',
    labelKey: 'staff.platform.tabs.events',
    permission: 'content_manage',
  },
  {
    id: 'projects',
    path: '/staff/platform/projects',
    labelKey: 'staff.platform.tabs.projects',
    permission: 'company_manage',
  },
  {
    id: 'settings',
    path: '/staff/platform/settings',
    labelKey: 'staff.platform.tabs.settings',
    permission: 'kyc_approve',
  },
]

/** The sections of the hub that the tab with this id opens; none for the other tabs. */
export const TAB_SECTIONS: Readonly<Record<string, readonly StaffSection[]>> = {
  users: USERS_SECTIONS,
  finance: FINANCE_SECTIONS,
  platform: PLATFORM_SECTIONS,
}

/**
 * True when the tab is drawn: a tab that opens a hub is drawn only when the
 * member may use at least one of the hub's sections; the other tabs (Home,
 * Settings) are drawn for every staff member.
 */
export function tabAllowed(tabId: string, rights: RightsContext): boolean {
  const sections = TAB_SECTIONS[tabId]
  if (!sections) return true
  return firstAllowedSection(sections, rights) !== null
}

// ---------------------------------------------------------------------------
// The permission card's presets
// ---------------------------------------------------------------------------

/** Every permission key the card shows, in the order it shows them. */
export const PERMISSION_KEYS = [
  'avatar_mode',
  'user_block',
  'kyc_approve',
  'agent_application_review',
  'payment_review',
  'financial_operations',
  'content_manage',
  'company_manage',
  'project_manage',
  'translation_edit',
] as const satisfies readonly StaffPermissionKey[]

// Compile-time exhaustiveness: a permission added to the backend schema and
// forgotten here fails the type check (the same guard the card had before).
type _PermissionKeysExhaustive =
  Exclude<StaffPermissionKey, (typeof PERMISSION_KEYS)[number]> extends never
    ? true
    : { readonly error: 'PERMISSION_KEYS misses a key of UpdatePermissionsRequest' }
const _permissionKeysExhaustive: _PermissionKeysExhaustive = true
void _permissionKeysExhaustive

/**
 * The keys the permission card draws: every key but translation_edit, which
 * the backend keeps and which governs nothing, so it is not offered.
 */
export const PERMISSION_CARD_KEYS: readonly StaffPermissionKey[] = PERMISSION_KEYS.filter(
  (key) => key !== 'translation_edit',
)

/** A named set of ticks the administrator marks with one press. */
export interface PermissionPreset {
  id: 'support' | 'verification' | 'finance' | 'content'
  labelKey: string
  keys: readonly StaffPermissionKey[]
}

/**
 * The four sets. "Support": the avatar, blocking users. "Verification":
 * approving identity checks, integrator applications. "Finance": checking
 * payments, financial operations. "Content and projects": content, managing
 * projects (both rights the platform tab uses).
 *
 * What only the administrator holds -- appointing staff, rights, changing an
 * e-mail, taking a member off duty -- is not a set: it follows from holding
 * every permission.
 */
export const PERMISSION_PRESETS: readonly PermissionPreset[] = [
  {
    id: 'support',
    labelKey: 'staff.rights.presets.support',
    keys: ['avatar_mode', 'user_block'],
  },
  {
    id: 'verification',
    labelKey: 'staff.rights.presets.verification',
    keys: ['kyc_approve', 'agent_application_review'],
  },
  {
    id: 'finance',
    labelKey: 'staff.rights.presets.finance',
    keys: ['payment_review', 'financial_operations'],
  },
  {
    id: 'content',
    labelKey: 'staff.rights.presets.content',
    keys: ['content_manage', 'company_manage', 'project_manage'],
  },
]

/**
 * The permission update one preset press sends: every key the card shows, on
 * for the keys of the set and off for the rest. A press MARKS THE SET -- the
 * member holds exactly the set's rights afterwards -- because a new member
 * starts with a broad default and a press that only added ticks would leave
 * that default standing under the name of a narrower role.
 */
export function presetPatch(preset: PermissionPreset): Record<StaffPermissionKey, boolean> {
  const patch = {} as Record<StaffPermissionKey, boolean>
  for (const key of PERMISSION_KEYS) patch[key] = preset.keys.includes(key)
  return patch
}

/**
 * The preset whose set is exactly what the member holds, if any -- the button
 * the card draws as pressed.
 */
export function matchingPreset(
  permissions: Readonly<Record<string, unknown>> | null | undefined,
): PermissionPreset | null {
  if (!permissions) return null
  for (const preset of PERMISSION_PRESETS) {
    const exact = PERMISSION_KEYS.every(
      (key) => (permissions[key] === true) === preset.keys.includes(key),
    )
    if (exact) return preset
  }
  return null
}

/** True when every permission is on (the administrator). */
export function holdsEveryPermission(
  permissions: Readonly<Record<string, unknown>> | null | undefined,
): boolean {
  if (!permissions) return false
  return PERMISSION_KEYS.every((key) => permissions[key] === true)
}
