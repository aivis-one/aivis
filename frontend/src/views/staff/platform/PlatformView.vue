<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PlatformView (iter 2.7 Block B1 scaffolding)
// =============================================================================
//
// Thin wrapper for the Staff Platform tab. Renders a horizontal
// chip-row navigation across the top-level subsections (News /
// Events / Companies / Settings) and a <router-view> for the
// selected one.
//
// FP-18 compliance: every router.push() goes through safeNavigate
// with a labelled context string for telemetry. FP-19 compliance:
// no <CHeader> here -- StaffShell provides the single header for
// the whole subtree.
//
// Permission gate: this view is reachable for any role=staff user, but
// its chip row is not uniform -- a subsection whose screen enforces a
// permission carries that key on its record and is not painted without
// it (H14 P-67). The internal CTAs in News / Events / Companies check
// per-permission flags through useStaffPermissions (Block B4).
//
// THE CHIP IS NOT THE LOCK, AND SINCE P-88 IT IS NOT ALONE EITHER. A
// deep link used to reach the screen, which then refused server-side --
// an empty page and a toast. The route record now carries the
// permission in its meta and the global guard turns a person without it
// away before the screen mounts. The chip row's job is what it always
// was: not offering a door that answers 403.
//
// AND IT ASKS THE ROUTER WHICH DOOR NEEDS WHICH KEY. The permission is
// declared once, on the route; this file resolves the path and reads it
// back. Repeating the key here would put one rule in two files, and the
// copy that drifts is always the one nobody is looking at.
// =============================================================================

import { computed } from 'vue'
import type { ComputedRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { safeNavigate } from '@/composables/safeNavigate'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import type { StaffPermissionKey } from '@/composables/useStaffPermissions'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { canDo } = useStaffPermissions()

interface Subsection {
  id: string
  path: string
  labelKey: string
}

// Subsection definitions. Path is matched as a prefix so deep links
// like /staff/platform/companies/:id/profile still light up the
// "Companies" chip.
const subsections: readonly Subsection[] = [
  { id: 'news', path: '/staff/platform/news', labelKey: 'staff.platform.tabs.news' },
  { id: 'events', path: '/staff/platform/events', labelKey: 'staff.platform.tabs.events' },
  { id: 'companies', path: '/staff/platform/companies', labelKey: 'staff.platform.tabs.companies' },
  { id: 'settings', path: '/staff/platform/settings', labelKey: 'staff.platform.tabs.settings' },
]

// The permission each subsection needs, asked of the router rather than
// written here. resolve() merges meta down the matched records, so this
// yields whatever the route declared -- and undefined for the ones that
// declare nothing, which is the honest answer for a screen open to any
// staff member.
function permissionForPath(path: string): StaffPermissionKey | undefined {
  return router.resolve(path).meta.permission
}

// Resolved once here rather than inside the filter below: canDo()
// creates a computed the first time it sees a key, and creating one
// during another computed's evaluation is a lifetime question nobody
// should have to answer while reading a nav bar.
const permissionOf = new Map<StaffPermissionKey, ComputedRef<boolean>>(
  subsections
    .map((s) => permissionForPath(s.path))
    .filter((p): p is StaffPermissionKey => p !== undefined)
    .map((p) => [p, canDo(p)]),
)

const visibleSubsections = computed<readonly Subsection[]>(() =>
  subsections.filter((s) => {
    const needed = permissionForPath(s.path)
    return needed === undefined || permissionOf.get(needed)?.value === true
  }),
)

// Deliberately derived from the FULL list, not the visible one. This
// answers "where am I", not "what may I see": a staff member who
// deep-links to a subsection they cannot open is still there, and
// computing it from the filtered list would light up the first chip
// instead -- pointing at a screen they are not on. No chip active is
// the honest picture.
const activeId = computed<string>(() => {
  const match = subsections.find((s) => route.path.startsWith(s.path))
  return match?.id ?? 'news'
})

function go(path: string): void {
  if (route.path === path) return
  void safeNavigate(router.push(path), `[PlatformView] to ${path}`)
}
</script>

<template>
  <div class="platform">
    <nav class="platform__nav" aria-label="Platform subsections">
      <button
        v-for="s in visibleSubsections"
        :key="s.id"
        type="button"
        class="platform__chip"
        :class="{ 'platform__chip--active': activeId === s.id }"
        @click="go(s.path)"
      >
        {{ t(s.labelKey) }}
      </button>
    </nav>

    <div class="platform__content">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.platform {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.platform__nav {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-page);
  position: sticky;
  top: 0;
  z-index: 10;
}
.platform__nav::-webkit-scrollbar {
  display: none;
}
.platform__nav {
  scrollbar-width: none;
}

.platform__chip {
  /* A5: pointer target floor. */
  min-height: var(--tap-min);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-default);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
}
.platform__chip:hover {
  background: var(--bg-subtle);
}
.platform__chip--active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.platform__content {
  flex: 1;
}
</style>
