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

   WHERE IT ACTUALLY SHOWS, RE-MEASURED 2026-08-25 AFTER THE WIDE BOUNDARY MOVED
   TO 1472. The side nav is 72px from 820 and 232px only from 1472, so below 1472
   the column is min(cap, viewport - 72). The difference between the roles is
   exactly 0 up to 1152, is 1px at 1153, and reaches its full 160px at 1312 —
   after which it never grows further, because staff are capped at --maxw-wide.
   On a 1440 laptop the visible difference is now 160px.

   EVERY NUMBER IN THIS PARAGRAPH USED TO BE DIFFERENT (0 below 1313, full 160
   only at 1472, 128 on a 1440 laptop) AND ALL OF THEM WERE CORRECT AT THE TIME.
   They were measured against a rail that stepped at 1280. The boundary moved and
   they moved with it: this is what a comment full of measured constants costs,
   and it is still cheaper than a reader re-deriving the ruling from scratch.

   THE 1280 STEP WAS ALSO WHY THIS RULE APPEARED TO BE WORTH NOTHING AT THE
   BOUNDARY: at 1280 the rail took 160px at exactly the width the wide tier was
   supposed to give room, so BOTH roles dropped to 1048 and staff lost 159px
   against their own 1279. That is fixed at the source, in CSideNav.

   checks/breakpoints.py holds --bp-tier-lg and the literal in CSideNav in step;
   a media query cannot read a custom property, so nothing else can.

   checks/shell_layout.py asserts this override still exists, so a refactor
   cannot fold it into one value silently. What that check cannot say is WHY,
   which is what this comment is for. */
.shell__measure {
  max-width: var(--maxw-wide);
}
</style>
