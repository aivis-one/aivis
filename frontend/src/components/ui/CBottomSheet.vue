<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- CBottomSheet (Phase F4.1)
// =============================================================================
//
// Sheet from the bottom edge on a phone and a centred window at the reading width on
// the web (from the 640 width), on the design system's Dialog (K52), placement
// `wide`; closed by Escape, by a click on the scrim (if allowed) and by the close
// button. Used for filter pickers, action lists, and other sheets that should feel
// native on mobile.
//
// Structure:
//   - head (the optional `title` prop, or the `header` slot, and the close button)
//   - body (the default slot, scrollable)
//
// Matches CModal's API shape for familiarity: same `open` prop,
// same `close` event.
// =============================================================================

import { ref, toRef, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@/components/ui/icons'
import { useDialog } from '@/composables/useDialog'

const props = withDefaults(
  defineProps<{
    open: boolean
    closeOnOverlay?: boolean
    title?: string
  }>(),
  { closeOnOverlay: true },
)

const emit = defineEmits<{ close: [] }>()

function onOverlay(): void {
  if (props.closeOnOverlay) emit('close')
}

const { t } = useI18n()
const titleId = useId()

// A sheet must not depend on each caller remembering to supply the way out: the
// close button, Escape and the focus handling are the component's own.
const dialogEl = ref<HTMLElement | null>(null)
useDialog(toRef(props, 'open'), dialogEl, () => emit('close'))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="ds-dialog"
      data-variant="wide"
      :data-lock="closeOnOverlay ? undefined : 'true'"
      @click.self="onOverlay"
    >
      <div
        ref="dialogEl"
        class="ds-dialog__panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="title ? titleId : undefined"
        tabindex="-1"
      >
        <div class="ds-dialog__head">
          <slot name="header">
            <h2 v-if="title" :id="titleId" class="ds-dialog__title">{{ title }}</h2>
            <span v-else aria-hidden="true" />
          </slot>
          <button
            type="button"
            class="ds-button ds-button--ghost ds-button--icon"
            data-size="sm"
            :aria-label="t('common.close')"
            @click="emit('close')"
          >
            <X size="sm" />
          </button>
        </div>
        <div class="ds-dialog__body">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
