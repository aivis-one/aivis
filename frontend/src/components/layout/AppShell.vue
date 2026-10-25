<script setup lang="ts">
// The frame (K25): ONE shell for every role. `.ds-shell` is the grid of the banner
// row, the header, the main region and the menu; the system alone decides how it
// lies at each width (the bar below 880, the rail from 880, the rail with labels
// from 1120). The role is read from the route record's `meta.shell`; the four
// cabinets get the menu of their tabs, a route without one (the public storefront)
// gets the nav-less variant: banner, header and main.
//
// WHAT A SCREEN GIVES THE FRAME: its title, back target and actions through
// `useScreenHeader` (./screenHeader); the lead line it sets is drawn here, as the
// first element of main. The staff cabinet's tables and lists take the wide
// measure; the other cabinets keep the standard one.
//
// The toast region and the pieces that are not the screen's (the banner of staff
// acting as a user, the storefront's Register and Sign in) are the frame's too.

import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppNav from '@/components/layout/AppNav.vue'
import AvatarBanner from '@/components/layout/AvatarBanner.vue'
import PublicHeaderActions from '@/components/layout/PublicHeaderActions.vue'
import { useCurrentScreenHeader } from '@/components/layout/screenHeader'
import CToast from '@/components/ui/CToast.vue'
import { useStaffRights } from '@/composables/useStaffRights'
import { extraTabsFor, tabsFor } from '@/router/tabs'
import { tabAllowed } from '@/utils/staffRights'

const route = useRoute()
const { current } = useStaffRights()
const header = useCurrentScreenHeader()

// A staff tab that opens a hub is drawn only when the member has the right to at
// least one of the hub's sections.
// The web menu folds to icons only (the system's data-nav="collapsed"); the choice is
// kept in the browser, per viewer. Storage that throws only means it is not kept.
const NAV_KEY = 'aivis_nav_collapsed'
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_KEY) === '1'
  } catch {
    return false
  }
}
const navCollapsed = ref<boolean>(readCollapsed())
function toggleNav(): void {
  navCollapsed.value = !navCollapsed.value
  try {
    localStorage.setItem(NAV_KEY, navCollapsed.value ? '1' : '0')
  } catch {
    // Not kept: the menu stays folded or open for this visit.
  }
}

// The sections that have no tab; the staff member's rights decide nothing for them
// (the screens check their own rights).
const extras = computed(() => extraTabsFor(route.meta.shell))

const tabs = computed(() => {
  const list = tabsFor(route.meta.shell)
  if (!list) return undefined
  if (route.meta.shell !== 'staff') return list
  const rights = current()
  return list.filter((tab) => tabAllowed(tab.id, rights))
})
</script>

<template>
  <div
    class="ds-shell"
    :class="{ 'ds-shell--navless': !tabs }"
    :data-nav="tabs && navCollapsed ? 'collapsed' : undefined"
  >
    <AvatarBanner />
    <AppHeader>
      <template v-if="!tabs" #right>
        <PublicHeaderActions />
      </template>
    </AppHeader>
    <main
      id="main"
      class="ds-shell__main"
      :data-measure="route.meta.shell === 'staff' ? 'wide' : undefined"
    >
      <p v-if="header.lead" class="ds-shell__lead">{{ header.lead }}</p>
      <RouterView />
    </main>
    <AppNav
      v-if="tabs"
      :items="tabs"
      :extra="extras"
      :collapsed="navCollapsed"
      @toggle="toggleNav"
    />
    <CToast />
  </div>
</template>
