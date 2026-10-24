<script setup lang="ts">
// =============================================================================
// CFileField -- the design system's File input (K30), for one file
// =============================================================================
//
// `.ds-field.ds-file`: a visible label, the button (a real input type=file inside
// the label that draws it), the limits as text under it, and a list holding the
// file the field stands for: the one just picked (`selected`), the one being
// uploaded (`uploading`), or the one already stored (`done`). The screen does the
// work (checks, upload, remove); this piece draws the state and reports the pick.
//
//   file      the file just picked and not yet sent (a create form), or null
//   current   the name of the file already stored, shown as an item
//   preview   the address of a picture for the item's thumb (an image)
//   busy      the stored file is being replaced (`uploading`)
//   removable show the item's remove button; the screen answers `remove`
//
// A stored file (`done`) also carries K30's success badge in the item's aside; the
// sizes of a picked file are written with the locale's units (common.file.units).
// =============================================================================

import { computed, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, Upload, X } from '@/components/ui/icons'

const props = defineProps<{
  label: string
  /** The text on the button. */
  buttonLabel: string
  accept?: string
  /** The limits and the allowed types, as text (never only in `accept`). */
  hint?: string
  file?: File | null
  current?: string
  /** A second line under the stored file's name (its size, for example). */
  currentMeta?: string
  preview?: string
  busy?: boolean
  removable?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  /** A file was picked; the input is emptied so the same file can be picked again. */
  select: [file: File]
  remove: []
}>()

const { t } = useI18n()
const labelId = useId()
const hintId = useId()
const input = ref<HTMLInputElement | null>(null)

// The size units are words of the locale (common.file.units), like the state words.
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} ${t('common.file.units.b')}`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} ${t('common.file.units.kb')}`
  return `${(bytes / (1024 * 1024)).toFixed(1)} ${t('common.file.units.mb')}`
}

const itemName = computed<string>(() => props.file?.name ?? props.current ?? '')
const itemState = computed<'selected' | 'uploading' | 'done'>(() => {
  if (props.busy) return 'uploading'
  return props.file ? 'selected' : 'done'
})
// The item's second line: its size, then its state in words (K30: every item state
// is shown) -- ready to upload when picked, uploaded when stored.
const itemMeta = computed<string>(() => {
  const size = props.file ? formatBytes(props.file.size) : (props.currentMeta ?? '')
  const word =
    itemState.value === 'selected'
      ? t('common.file.ready')
      : itemState.value === 'done'
        ? t('common.file.uploaded')
        : ''
  return [size, word].filter(Boolean).join(' · ')
})

function onChange(e: Event): void {
  const el = e.target as HTMLInputElement
  const picked = el.files?.[0]
  el.value = ''
  if (picked) emit('select', picked)
}

function onRemove(): void {
  if (input.value) input.value.value = ''
  emit('remove')
}
</script>

<template>
  <div class="ds-field ds-file" :data-disabled="disabled ? 'true' : undefined">
    <span :id="labelId" class="ds-field__label">{{ label }}</span>
    <label class="ds-button ds-button--secondary ds-file__pick">
      <Upload size="sm" />
      <span>{{ buttonLabel }}</span>
      <input
        ref="input"
        class="ds-file__input"
        type="file"
        :accept="accept"
        :disabled="disabled || busy"
        :aria-labelledby="labelId"
        :aria-describedby="hint ? hintId : undefined"
        @change="onChange"
      />
    </label>
    <p v-if="hint" :id="hintId" class="ds-field__hint">{{ hint }}</p>
    <ul class="ds-file__list" aria-live="polite">
      <li v-if="itemName" class="ds-file__item" :data-state="itemState">
        <span class="ds-file__thumb">
          <img v-if="preview" :src="preview" alt="" />
          <FileText v-else size="sm" />
        </span>
        <span class="ds-file__body">
          <span class="ds-file__name">{{ itemName }}</span>
          <span v-if="itemMeta" class="ds-file__meta ds-file__status">{{ itemMeta }}</span>
        </span>
        <span class="ds-file__aside">
          <span v-if="itemState === 'done'" class="ds-badge ds-badge--success">{{
            t('common.file.uploaded')
          }}</span>
          <button
            v-if="removable"
            type="button"
            class="ds-file__remove"
            :aria-label="t('common.file.remove', { name: itemName })"
            :disabled="busy"
            @click="onRemove"
          >
            <X size="sm" />
          </button>
        </span>
      </li>
    </ul>
  </div>
</template>
