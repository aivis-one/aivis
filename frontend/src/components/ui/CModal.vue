<script setup lang="ts">
// Modal dialog, on the design system's Dialog (K52), placement `wide`: on the web
// (from the 640 width) a centred window at the reading width, on a phone the bottom
// sheet. Closes on Escape, on a click on the scrim (if allowed), or on the close
// button. `fixedBody` gives the body one height (the system's data-body="fixed"), for
// a dialog that changes its content step by step and must not jump between steps.
//
// The caller's content is the dialog's body (the default slot). An optional
// `title` is the dialog's heading and names it (a `title` slot may draw it with an icon
// before the words); without one the content carries
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
    fixedBody?: boolean
  }>(),
  { closeOnOverlay: true, showClose: true, fixedBody: false },
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
      data-variant="wide"
      :data-body="fixedBody ? 'fixed' : undefined"
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
          <h2 v-if="title" :id="titleId" class="ds-dialog__title">
            <slot name="title">{{ title }}</slot>
          </h2>
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
        <!-- The actions row, when the caller fills it: it stands outside the body, so a
             fixed body keeps it at the same place at every step. -->
        <div v-if="$slots.actions" class="ds-dialog__actions">
          <slot name="actions" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
