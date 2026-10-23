<script setup lang="ts">
// Global toast notification, on the design system's Toast (K16): a live region
// that exists from the start, holds the toast while it is shown, with a dismiss
// button. Place once in App.vue or a shell. Driven by useToast().

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { AlertTriangle, Check, Info, ShieldAlert, X } from '@/components/ui/icons'

const { toastState, hideToast } = useToast()
const { t } = useI18n()

// The cabinet's `error` is the system's `danger`.
const status = computed(() => (toastState.value.variant === 'error' ? 'danger' : toastState.value.variant))
const glyph = computed(
  () => ({ info: Info, success: Check, warning: AlertTriangle, danger: ShieldAlert })[status.value],
)
</script>

<template>
  <Teleport to="body">
    <div class="ds-toast-region" aria-live="polite" aria-atomic="false">
      <div
        v-if="toastState.visible"
        class="ds-toast"
        :class="'ds-toast--' + status"
        :role="status === 'danger' ? 'alert' : 'status'"
      >
        <span class="ds-alert__icon" aria-hidden="true">
          <component :is="glyph" size="sm" />
        </span>
        <div class="ds-alert__content">
          <p class="ds-alert__text">{{ toastState.message }}</p>
        </div>
        <button type="button" class="ds-alert__close" :aria-label="t('common.close')" @click="hideToast()">
          <X size="sm" />
        </button>
      </div>
    </div>
  </Teleport>
</template>
