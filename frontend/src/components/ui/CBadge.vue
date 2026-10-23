<script setup lang="ts">
// Status badge, on the design system's Badge (K08).
import { computed } from 'vue'

const props = defineProps<{
  variant?: 'success' | 'warning' | 'danger' | 'primary' | 'accent' | 'neutral'
  text: string
}>()

// The cabinet's names on the system's Badge (K08): primary is `info`; the
// system has no accent badge (its colours equal the warning badge's), so accent
// is `warning`; neutral is the badge with no modifier.
const LOOKS = {
  success: 'ds-badge--success',
  warning: 'ds-badge--warning',
  danger: 'ds-badge--danger',
  primary: 'ds-badge--info',
  accent: 'ds-badge--warning',
  neutral: undefined,
} as const
const look = computed(() => LOOKS[props.variant ?? 'neutral'])
</script>

<template>
  <span class="ds-badge" :class="look">{{ text }}</span>
</template>
