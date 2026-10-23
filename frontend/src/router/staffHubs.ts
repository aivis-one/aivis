// =============================================================================
// AIVIS.ONE Frontend -- the staff hubs, as the router uses them
// =============================================================================
//
// Two small helpers over utils/staffRights.ts for the staff route records:
//
//   sectionMeta(sections, id)  the meta a section's record carries -- the
//                              permission and the administrator mark, taken
//                              from the one table so the lock on the route and
//                              the chip in the hub are the same fact;
//   hubStart(sections)         where a hub opens: its first section the member
//                              may use, else the staff Home.
// =============================================================================

import type { RouteMeta } from 'vue-router'

import { useStaffRights } from '@/composables/useStaffRights'
import { firstAllowedSection } from '@/utils/staffRights'
import type { StaffSection } from '@/utils/staffRights'

export function sectionMeta(sections: readonly StaffSection[], id: string): RouteMeta {
  const section = sections.find((s) => s.id === id)
  if (!section) throw new Error(`staff section "${id}" is not in its hub`)
  const meta: RouteMeta = {}
  if (section.permission) meta.permission = section.permission
  if (section.admin) meta.admin = true
  return meta
}

export function hubStart(sections: readonly StaffSection[]): string {
  const { current } = useStaffRights()
  return firstAllowedSection(sections, current())?.path ?? '/staff/dashboard'
}
