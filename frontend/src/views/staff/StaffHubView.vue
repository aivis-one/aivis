<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffHubView
// =============================================================================
//
// The frame of the three staff tabs that hold several sections: Users,
// Finance and Platform. A row of chips across the top (one per section the
// member may use) and the section's own screen below it.
//
// WHICH HUB IT IS is read off the route record (`meta.hub`), and which
// sections the hub has, with the right each one needs, off
// utils/staffRights.ts -- the same table the tab bar and the router read. The
// chip row draws only the sections the member has the right to; a section
// they may not use is not offered (the router guard also turns away a typed
// address, and the server still refuses).
//
// THE ACTIVE CHIP answers "where am I", not "what may I see", so it is found
// among ALL the hub's sections by the longest path that is a prefix of the
// current address: a deep link into a section the member cannot use lights no
// chip rather than the wrong one.
//
// A hub with one section the member may use draws no chip row: a choice of one
// is not a choice.
// =============================================================================

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { safeNavigate } from '@/composables/safeNavigate'
import { useStaffRights } from '@/composables/useStaffRights'
import { TAB_SECTIONS, allowedSections } from '@/utils/staffRights'
import type { StaffSection } from '@/utils/staffRights'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { current } = useStaffRights()

const allSections = computed<readonly StaffSection[]>(() => {
  const hub = route.meta.hub
  return hub ? (TAB_SECTIONS[hub] ?? []) : []
})

const visibleSections = computed<StaffSection[]>(() =>
  allowedSections(allSections.value, current()),
)

function inside(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`)
}

const activeId = computed<string | null>(() => {
  let best: StaffSection | null = null
  for (const section of allSections.value) {
    if (!inside(route.path, section.path)) continue
    if (!best || section.path.length > best.path.length) best = section
  }
  return best?.id ?? null
})

function go(path: string): void {
  if (route.path === path) return
  void safeNavigate(router.push(path), `[StaffHubView] to ${path}`)
}
</script>

<template>
  <div class="hub">
    <nav v-if="visibleSections.length > 1" class="hub__nav" :aria-label="t('staff.hub.nav')">
      <button
        v-for="s in visibleSections"
        :key="s.id"
        type="button"
        class="hub__chip"
        :class="{ 'hub__chip--active': activeId === s.id }"
        @click="go(s.path)"
      >
        {{ t(s.labelKey) }}
      </button>
    </nav>

    <div class="hub__content">
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.hub {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.hub__nav {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-page);
  position: sticky;
  top: 0;
  z-index: 10;
  scrollbar-width: none;
}
.hub__nav::-webkit-scrollbar {
  display: none;
}

.hub__chip {
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
.hub__chip:hover {
  background: var(--bg-subtle);
}
.hub__chip--active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
}

.hub__content {
  flex: 1;
}
</style>
