<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- PlatformView (iter 2.7 Block B1 scaffolding)
// =============================================================================
//
// Thin wrapper for the Staff Platform tab. Renders a horizontal
// chip-row navigation across the three top-level subsections (News
// / Events / Companies) and a <router-view> for the selected one.
//
// FP-18 compliance: every router.push() goes through safeNavigate
// with a labelled context string for telemetry. FP-19 compliance:
// no <CHeader> here -- StaffShell provides the single header for
// the whole subtree.
//
// Permission gate: this view is reachable for any role=staff user.
// The internal CTAs in News / Events / Companies sections check
// per-permission flags through useStaffPermissions (Block B4).
// =============================================================================

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { safeNavigate } from '@/composables/safeNavigate'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// Subsection definitions. Path is matched as a prefix so deep links
// like /staff/platform/companies/:id/profile still light up the
// "Companies" chip.
const subsections = [
  { id: 'news',      path: '/staff/platform/news',      labelKey: 'staff.platform.tabs.news' },
  { id: 'events',    path: '/staff/platform/events',    labelKey: 'staff.platform.tabs.events' },
  { id: 'companies', path: '/staff/platform/companies', labelKey: 'staff.platform.tabs.companies' },
] as const

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
        v-for="s in subsections"
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
  gap: 8px;
  overflow-x: auto;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  position: sticky;
  top: 0;
  z-index: 10;
}
.platform__nav::-webkit-scrollbar { display: none; }
.platform__nav { scrollbar-width: none; }

.platform__chip {
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.platform__chip:hover {
  background: var(--bg-subtle);
}
.platform__chip--active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.platform__content {
  flex: 1;
}
</style>
