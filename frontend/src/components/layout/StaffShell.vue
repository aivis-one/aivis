<script setup lang="ts">
// Staff shell — layout wrapper for all /staff/* routes.

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CToast from '@/components/ui/CToast.vue'
import { STAFF_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell">
    <CHeader />
    <main class="shell__content">
      <div class="shell__measure">
        <RouterView />
      </div>
    </main>
    <CTabBar :items="STAFF_TABS" />
    <CToast />
  </div>
</template>

<style scoped>
.shell { display: flex; flex-direction: column; min-height: 100vh; min-height: 100dvh; background: var(--bg-page); }
.shell__content { flex: 1; overflow-y: auto; }

/* CONTENT MEASURE — the design system's own widths, finally referenced. Before
   this, `main` ran to the full viewport at every width, so a text line reached
   1248px against a readable 600-700 (measured by the B-1 harness).

   Measure and centring ONLY, deliberately no gutter: 40 of the 62 views set
   their own padding on their root rule, so a gutter here would double up and
   cost 48px of a 390px phone. `.wrap` / `.wrap-wide` in global.css keep the
   gutter for content that does NOT pad itself. */
.shell__measure {
  width: 100%;
  max-width: var(--maxw-wide);
  margin-inline: auto;
}
</style>
