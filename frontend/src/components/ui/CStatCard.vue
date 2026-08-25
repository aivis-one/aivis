<script setup lang="ts">
// Numeric stat card from mockup stats-grid pattern.
//
// A5 / keyboard reach: a stat card carrying a @click IS a control, and until
// 2026-08-21 it rendered a bare <div>. Four of them were the staff dashboard's
// route to Users, the KYC queue, Payments and Agent applications, and none of
// the four could be reached or activated from a keyboard. They survived the
// accessibility sweep because that sweep's scanner excluded every component tag
// by construction, so 168 component-hosted clicks -- more than half the
// clickable surface -- sat outside its denominator.
//
// THE SIGNAL IS THE LISTENER, NOT A PROP. A prop can be forgotten at a call
// site, and forgetting at a call site is exactly how this defect was made. If a
// parent attaches @click, the root becomes a NATIVE <button>: Enter and Space
// then come from the platform instead of from a hand-rolled ARIA imitation, the
// global :focus-visible rule in global.css already covers `button`, and there is
// no role="button" to keep in step with its own key handlers.
//
// The 11 display-only call sites (15 in total, 4 clickable) stay <div>s and stay
// out of the tab order -- which is why this is a signal and not a blanket change.
import { computed, useAttrs } from 'vue'

defineProps<{
  value: string
  label: string
  sub?: string
  change?: string
  changeDir?: 'up' | 'down'
}>()

const attrs = useAttrs()
const interactive = computed(() => attrs.onClick !== undefined)
</script>

<template>
  <component
    :is="interactive ? 'button' : 'div'"
    :type="interactive ? 'button' : undefined"
    class="c-stat"
    :class="{ 'c-stat--interactive': interactive }"
  >
    <div class="c-stat__icon">
      <slot name="icon" />
    </div>
    <div class="c-stat__label">
      {{ label }}
    </div>
    <div class="c-stat__value">
      {{ value }}
    </div>
    <div v-if="change" class="c-stat__change" :class="'c-stat__change--' + (changeDir ?? 'up')">
      {{ change }}
    </div>
    <div v-if="sub" class="c-stat__sub">
      {{ sub }}
    </div>
  </component>
</template>

<style scoped>
.c-stat {
  background: var(--bg-page);
  box-shadow: var(--shadow-1);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  transition: all 0.2s;
}
/* Button chrome reset. `text-align: start` rather than `left` because the app
   ships an RTL locale and a button's default `center` would re-centre every
   line the <div> form left-aligns. */
.c-stat--interactive {
  display: block;
  width: 100%;
  text-align: start;
  font: inherit;
  color: inherit;
  border: none;
  cursor: pointer;
}
.c-stat:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-2);
}
.c-stat__icon {
  margin-bottom: var(--space-2);
}
.c-stat__label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin-bottom: var(--space-1);
}
.c-stat__value {
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-primary);
}
.c-stat__change {
  font-size: var(--fs-xs);
  font-weight: 600;
  margin-top: var(--space-1);
}
.c-stat__change--up {
  color: var(--success);
}
.c-stat__change--down {
  color: var(--danger);
}
.c-stat__sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.c-stat__sub {
  max-width: var(--maxw-prose);
}
</style>
