<script setup lang="ts">
// Staff shell — layout wrapper for all /staff/* routes.

import CHeader from '@/components/layout/CHeader.vue'
import CTabBar from '@/components/layout/CTabBar.vue'
import CSideNav from '@/components/layout/CSideNav.vue'
import CToast from '@/components/ui/CToast.vue'
import { STAFF_TABS } from '@/router/tabs'
</script>

<template>
  <div class="shell shell--tabbed">
    <CHeader />
    <div class="shell__body">
      <CSideNav :items="STAFF_TABS" />
      <main class="shell__content">
        <div class="shell__measure">
          <RouterView />
        </div>
      </main>
    </div>
    <CTabBar :items="STAFF_TABS" />
    <CToast />
  </div>
</template>

<style scoped>
/* The ONLY shell rule that is not shared: staff screens cap content at
   --maxw-wide (1240px) where the other four cap at --maxw (1080px).

   ✅ THIS IS DELIBERATE — owner-ruled 2026-08-25 (B-3.3). The reason, so that
   nobody tidies it away as drift: staff screens are TABLES and lists, the other
   four roles are mostly text and cards, and the right width for those two things
   is not the same number. The design system already holds that distinction in a
   token — --maxw-prose is 680px, narrower than either, because reading width and
   layout width are different questions. Widening everyone to 1240 would make text
   worse to read; narrowing staff to 1080 costs a column of data to the one role
   that lives in lists.

   WHERE IT ACTUALLY SHOWS, measured rather than assumed: the side nav is 232px
   from 1280 up, so the column is min(cap, viewport - 232). Below 1313px BOTH
   roles are limited by the container and the difference is exactly 0 — at the
   1280 tier boundary this rule has no effect at all. From 1313 it grows, and it
   reaches its full 160px at 1472px and never grows further. On a 1440 laptop the
   visible difference is 128px, not 160.

   checks/shell_layout.py asserts this override still exists, so a refactor
   cannot fold it into one value silently. What that check cannot say is WHY,
   which is what this comment is for. */
.shell__measure {
  max-width: var(--maxw-wide);
}
</style>
