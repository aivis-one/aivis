<script setup lang="ts">
// Colored icon square. Wraps a slot (Lucide icon) in a tinted background square.
//
// VARIANTS ARE NAMED FOR THEIR ROLE, NOT THEIR COLOUR (2026-08-18). They read
// `teal` and `orange` until then -- the RETIRED brand's colour words, still in
// the API a month after those colours were replaced by azure and amber, so the
// name said one thing and the token underneath said another.
// The `blue` variant is REMOVED: a raw hex in no palette -- the only hardcoded
// colour in a component built entirely of tokens -- and nothing used it. The
// value is not quoted here on purpose: this comment ships, and naming a colour
// you just deleted makes every future search for it hit its own obituary.
// (Third time today. index.html and global.css had the same self-inflicted hit.)

defineProps<{
  variant?: 'primary' | 'accent' | 'success' | 'warning' | 'danger' | 'neutral'
}>()
</script>

<template>
  <div class="c-icon-box" :class="'c-icon-box--' + (variant ?? 'neutral')">
    <slot />
  </div>
</template>

<style scoped>
.c-icon-box {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.c-icon-box :deep(svg) {
  width: 22px;
  height: 22px;
}

.c-icon-box--primary { background: var(--primary-subtle); color: var(--primary); }
.c-icon-box--accent { background: var(--accent-subtle); color: var(--accent); }
.c-icon-box--success { background: var(--success-subtle); color: var(--success); }
.c-icon-box--warning { background: var(--warning-subtle); color: var(--warning); }
.c-icon-box--danger { background: var(--danger-subtle); color: var(--danger); }
.c-icon-box--neutral { background: var(--bg-subtle); color: var(--text-secondary); }
</style>
