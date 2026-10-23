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

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppNav from '@/components/layout/AppNav.vue'
import AvatarBanner from '@/components/layout/AvatarBanner.vue'
import PublicHeaderActions from '@/components/layout/PublicHeaderActions.vue'
import { useCurrentScreenHeader } from '@/components/layout/screenHeader'
import CToast from '@/components/ui/CToast.vue'
import { useStaffRights } from '@/composables/useStaffRights'
import { tabsFor } from '@/router/tabs'
import { tabAllowed } from '@/utils/staffRights'

const route = useRoute()
const { current } = useStaffRights()
const header = useCurrentScreenHeader()

// A staff tab that opens a hub is drawn only when the member has the right to at
// least one of the hub's sections.
const tabs = computed(() => {
  const list = tabsFor(route.meta.shell)
  if (!list) return undefined
  if (route.meta.shell !== 'staff') return list
  const rights = current()
  return list.filter((tab) => tabAllowed(tab.id, rights))
})
</script>

<template>
  <div class="ds-shell" :class="{ 'ds-shell--navless': !tabs }">
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
    <AppNav v-if="tabs" :items="tabs" />
    <CToast />
  </div>
</template>
