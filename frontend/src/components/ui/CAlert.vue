<script setup lang="ts">
// A message the reader must see in context, on the design system's Alert
// (K09): a disc with the severity's icon, an optional title, the text (the default
// slot) and an optional actions slot (a Retry). Info and success are announced as
// a status, warning and danger as an alert.

import { computed } from 'vue'
import { AlertTriangle, Check, Info, ShieldAlert } from '@/components/ui/icons'

const props = withDefaults(
  defineProps<{ tone?: 'info' | 'success' | 'warning' | 'danger'; title?: string }>(),
  { tone: 'info' },
)

const ICONS = { info: Info, success: Check, warning: AlertTriangle, danger: ShieldAlert } as const
const icon = computed(() => ICONS[props.tone])
const live = computed(() =>
  props.tone === 'warning' || props.tone === 'danger' ? 'alert' : 'status',
)
</script>

<template>
  <div class="ds-alert" :class="'ds-alert--' + tone" :role="live">
    <span class="ds-alert__icon" aria-hidden="true"><component :is="icon" /></span>
    <div class="ds-alert__content">
      <p v-if="title" class="ds-alert__title">{{ title }}</p>
      <p v-if="$slots.default" class="ds-alert__text"><slot /></p>
      <div v-if="$slots.actions" class="ds-alert__actions"><slot name="actions" /></div>
    </div>
  </div>
</template>
