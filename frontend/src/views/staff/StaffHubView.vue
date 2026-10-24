<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffHubView
// =============================================================================
//
// The frame of the three staff tabs that hold several sections: Users,
// Finance and Platform. The sub-navigation across the top (one link per section
// the member may use) and the section's own screen below it.
//
// WHICH HUB IT IS is read off the route record (`meta.hub`), and which
// sections the hub has, with the right each one needs, off
// utils/staffRights.ts -- the same table the tab bar and the router read. The
// sub-navigation draws only the sections the member has the right to; a section
// they may not use is not offered (the router guard also turns away a typed
// address, and the server still refuses).
//
// THE SUB-NAVIGATION is the frame's (K25): links, the current one marked by the
// router (`aria-current="page"` on its own route and inside it). A section the
// member may not use is not a link, so a deep link into one lights none.
//
// A hub with one section the member may use draws no sub-navigation: a choice of
// one is not a choice.
// =============================================================================

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import SubNav from '@/components/layout/SubNav.vue'
import type { SubNavItem } from '@/components/layout/SubNav.vue'
import { useStaffRights } from '@/composables/useStaffRights'
import { TAB_SECTIONS, allowedSections } from '@/utils/staffRights'
import type { StaffSection } from '@/utils/staffRights'

const { t } = useI18n()
const route = useRoute()
const { current } = useStaffRights()

const allSections = computed<readonly StaffSection[]>(() => {
  const hub = route.meta.hub
  return hub ? (TAB_SECTIONS[hub] ?? []) : []
})

const visibleSections = computed<StaffSection[]>(() =>
  allowedSections(allSections.value, current()),
)

const subNavItems = computed<SubNavItem[]>(() =>
  visibleSections.value.map((s) => ({ id: s.id, to: s.path, label: t(s.labelKey) })),
)
</script>

<template>
  <div class="hub">
    <SubNav v-if="subNavItems.length > 1" :label="t('staff.hub.nav')" :items="subNavItems" />

    <RouterView />
  </div>
</template>

<style scoped>
.hub {
  display: grid;
  gap: var(--space-5);
  align-content: start;
}
</style>
