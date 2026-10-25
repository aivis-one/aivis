<script setup lang="ts">
// =============================================================================
// MediaImageField -- one picture of a project, as a file (H36 P-131)
// =============================================================================
//
// The design system's File input (K30, CFileField) for one stored picture: a
// project's logo, its dark logo, its cover, or a product's cover. Shows the
// stored picture as the item's thumb, takes a new file, and asks before the
// stored one is removed. It checks the type and the size of a picked file
// against the server's limits (api/media.ts) and reports a refusal with a toast;
// only a file that may go is emitted.
//
// The screen does the work: on `select` it uploads (the stored picture is
// replaced), on `remove` it deletes. Both are immediate, not tied to a form's
// Save -- the pictures have their own endpoints.
//
//   label     the field's name ("Logo", "Cover", ...)
//   url       the stored picture's link, or null when there is none
//   maxBytes  the server's size limit for this picture
//   busy      an upload or a removal is in flight
//   disabled  the viewer may not change it
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import CFileField from '@/components/ui/CFileField.vue'
import { CButton, CModal } from '@/components/ui'
import { useToast } from '@/composables/useToast'
import { MEDIA_IMAGE_ACCEPT, checkMediaImage } from '@/api/media'

const props = defineProps<{
  label: string
  url: string | null
  maxBytes: number
  busy?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [file: File]
  remove: []
}>()

const { t } = useI18n()
const { showToast } = useToast()

const sizeMb = computed<string>(() =>
  String(Math.round((props.maxBytes / (1024 * 1024)) * 10) / 10),
)
const hint = computed<string>(() => t('common.media.hint', { size: sizeMb.value }))

function onSelect(file: File): void {
  const refused = checkMediaImage(file, props.maxBytes)
  if (refused === 'type') {
    showToast(t('common.media.errorType'), 'error')
    return
  }
  if (refused === 'size') {
    showToast(t('common.media.errorSize', { size: sizeMb.value }), 'error')
    return
  }
  emit('select', file)
}

const confirmRemove = ref(false)

function onRemoveConfirmed(): void {
  confirmRemove.value = false
  emit('remove')
}
</script>

<template>
  <CFileField
    :label="label"
    :button-label="url ? t('common.media.replace') : t('common.media.upload')"
    :accept="MEDIA_IMAGE_ACCEPT"
    :hint="hint"
    :current="url ? label : undefined"
    :preview="url ?? undefined"
    :busy="busy"
    :removable="!!url && !disabled"
    :disabled="disabled"
    @select="onSelect"
    @remove="confirmRemove = true"
  />
  <CModal
    :open="confirmRemove"
    :title="t('common.media.removeTitle', { name: label })"
    @close="confirmRemove = false"
  >
    <p class="ds-dialog__text">{{ t('common.media.removeBody') }}</p>
    <div class="ds-dialog__actions">
      <CButton variant="outline" size="sm" inline @click="confirmRemove = false">
        {{ t('common.cancel') }}
      </CButton>
      <CButton variant="primary" size="sm" inline :loading="busy" @click="onRemoveConfirmed">
        {{ t('common.media.remove') }}
      </CButton>
    </div>
  </CModal>
</template>
