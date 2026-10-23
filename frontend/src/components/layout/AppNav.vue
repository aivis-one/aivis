<script setup lang="ts">
// The frame's one menu (K25): `nav.ds-nav` holding the role's items as links. The
// system draws it as the tab bar below 880, the icon rail from 880 and the rail
// with labels from 1120; nothing here switches between them. From 880 the mark of
// AIVIS stands at the head of the list (the system hides it on the phone).
//
// The items come from router/tabs.ts, the same list for every width. The current
// item is `aria-current="page"`; an item is current under its own path, so a
// screen inside a tab keeps its tab marked.

import type { Component } from 'vue'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  BarChart3,
  Briefcase,
  Home,
  LayoutGrid,
  Newspaper,
  Package,
  Settings,
  Store,
  Users,
  Wallet,
} from '@/components/ui/icons'
import { getRoleDashboard } from '@/router/guards'
import type { TabItem } from '@/router/tabs'
import { useAuthStore } from '@/stores/auth'

defineProps<{ items: TabItem[] }>()

const route = useRoute()
const { t } = useI18n()
const authStore = useAuthStore()

// A tab's `icon` is the name of one of these exports.
const iconMap: Record<string, Component> = {
  BarChart3,
  Briefcase,
  Home,
  LayoutGrid,
  Newspaper,
  Package,
  Settings,
  Store,
  Users,
  Wallet,
}

const homeRoute = computed(() => getRoleDashboard(authStore.role))
const markSrc = `${import.meta.env.BASE_URL}aivis-mark.svg`

function isActive(tab: TabItem): boolean {
  return route.path.startsWith(tab.path)
}
</script>

<template>
  <nav class="ds-nav" :aria-label="t('common.primaryNav')">
    <ul class="ds-nav__list">
      <li class="ds-nav__brand">
        <RouterLink v-slot="{ href, navigate }" :to="homeRoute" custom>
          <a class="ds-nav__logo" :href="href" aria-label="AIVIS" @click="navigate">
            <img class="ds-nav__mark" :src="markSrc" alt="" />
          </a>
        </RouterLink>
      </li>
      <li v-for="tab in items" :key="tab.id">
        <RouterLink v-slot="{ href, navigate }" :to="tab.path" custom>
          <a
            class="ds-navitem"
            :href="href"
            :aria-current="isActive(tab) ? 'page' : undefined"
            @click="navigate"
          >
            <component :is="iconMap[tab.icon]" />
            <span class="ds-navitem__label">{{ t(tab.labelKey) }}</span>
          </a>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>
