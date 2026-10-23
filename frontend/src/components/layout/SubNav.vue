<script setup lang="ts">
// The sub-navigation of a hub (K25): links between the child screens of one area,
// in the Tabs look, scrolling sideways on a phone and kept under the header. It is
// navigation, so the links are real links and the current one is
// `aria-current="page"` (a link is current on its own route and inside it), not a
// tab role. Put it first in the screen.

import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

export interface SubNavItem {
  id: string
  to: RouteLocationRaw
  label: string
}

defineProps<{
  /** The accessible name of the navigation landmark. */
  label: string
  items: SubNavItem[]
}>()
</script>

<template>
  <nav class="ds-subnav" :aria-label="label">
    <ul class="ds-subnav__list">
      <li v-for="item in items" :key="item.id">
        <RouterLink v-slot="{ href, navigate, isActive }" :to="item.to" custom>
          <a
            class="ds-subnav__link"
            :href="href"
            :aria-current="isActive ? 'page' : undefined"
            @click="navigate"
          >
            {{ item.label }}
          </a>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>
