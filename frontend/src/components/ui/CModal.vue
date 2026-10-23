<script setup lang="ts">
// Modal dialog, on the design system's Dialog (K52), placement `modal`: centred
// on a wide screen, capped at the system's form width. Closes on Escape, on a
// click on the scrim (if allowed), or on the close button.
//
// The caller's content is the dialog's body (the default slot). An optional
// `title` is the dialog's heading and names it; without one the content carries
// its own heading and the head holds the close button alone.

import { ref, toRef, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@/components/ui/icons'
import { useDialog } from '@/composables/useDialog'

const props = withDefaults(
  defineProps<{
    open: boolean
    closeOnOverlay?: boolean
    showClose?: boolean
    title?: string
  }>(),
  { closeOnOverlay: true, showClose: true },
)

const emit = defineEmits<{ close: [] }>()

function onOverlay(): void {
  if (props.closeOnOverlay) emit('close')
}

// A1: the close control is an icon with no text; its name must come from an
// aria-label.
const { t } = useI18n()
const titleId = useId()

// Escape, focus containment and focus restore. The click on the scrim was the only
// dismissal a keyboard could not perform.
const dialogEl = ref<HTMLElement | null>(null)
useDialog(toRef(props, 'open'), dialogEl, () => emit('close'))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="ds-dialog"
      data-variant="modal"
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
        <div v-if="title || showClose" class="ds-dialog__head">
          <h2 v-if="title" :id="titleId" class="ds-dialog__title">{{ title }}</h2>
          <span v-else aria-hidden="true" />
          <button
            v-if="showClose"
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
