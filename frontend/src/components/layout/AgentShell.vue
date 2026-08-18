<script setup lang="ts">
// Agent shell — layout wrapper for all /agent/* routes.
// Agent has access to all investor screens too (via routing).

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { AGENT_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="AGENT_TABS" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="AGENT_TABS" />
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
  max-width: var(--maxw);
  margin-inline: auto;
}

/* TIER SWITCH — the phone's bottom bar and the side menu are mutually
   exclusive at every width, which is why they land together: shipped apart,
   a desktop user would have no navigation at all for the length of one
   commit. Below 820 CSideNav renders nothing and CTabBar carries it; from
   820 up the body becomes a row and the bar is gone.

   --tab-bar-height goes to 0 in the same breakpoint rather than the bar
   merely being hidden, because that token is the declared source of truth
   for the floating CTAs that pin themselves above the bar
   (CompanyOverviewView). Hiding the bar alone would leave those CTAs
   floating 56px clear of nothing. */
.shell__body { display: contents; }

@media (min-width: 820px) {
  .shell { --tab-bar-height: 0px; }
  .shell__body { display: flex; flex: 1; min-height: 0; }
  .shell__content { flex: 1; min-width: 0; }
  .shell :deep(.c-tabbar) { display: none; }
}
</style>
