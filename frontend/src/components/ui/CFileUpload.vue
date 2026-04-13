<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    modelValue?: File | File[] | null
    multiple?: boolean
    accept?: string
    maxSize?: number
    label?: string
    error?: string
    disabled?: boolean
  }>(),
  {
    modelValue: null,
    multiple: false,
    accept: '',
    maxSize: 5 * 1024 * 1024,
    label: '',
    error: '',
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: File | File[] | null]
  'validation-error': [message: string]
}>()

const { t } = useI18n()
const inputRef = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

const files = computed<File[]>(() => {
  if (!props.modelValue) return []
  return Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]
})

function openPicker() {
  if (!props.disabled) inputRef.value?.click()
}

function handleFiles(incoming: FileList | null) {
  if (!incoming || incoming.length === 0) return

  const selected = Array.from(incoming)

  for (const file of selected) {
    if (file.size > props.maxSize) {
      emit('validation-error', t('shared.fileUpload.invalidSize'))
      return
    }
    if (props.accept && !matchesAccept(file, props.accept)) {
      emit('validation-error', t('shared.fileUpload.invalidType'))
      return
    }
  }

  emit('update:modelValue', props.multiple ? selected : selected[0])
}

function matchesAccept(file: File, accept: string): boolean {
  const types = accept.split(',').map((s) => s.trim())
  return types.some((type) => {
    if (type.startsWith('.')) return file.name.toLowerCase().endsWith(type.toLowerCase())
    if (type.endsWith('/*')) return file.type.startsWith(type.replace('/*', '/'))
    return file.type === type
  })
}

function onInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  handleFiles(input.files)
  input.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  if (!props.disabled) handleFiles(event.dataTransfer?.files ?? null)
}

function removeFile(index: number) {
  const updated = files.value.filter((_, i) => i !== index)
  emit('update:modelValue', props.multiple ? updated : (updated[0] ?? null))
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isImage(file: File): boolean {
  return file.type.startsWith('image/')
}
</script>

<template>
  <div class="c-file-upload" :class="{ 'c-file-upload--disabled': disabled }">
    <label v-if="label" class="c-file-upload__label">{{ label }}</label>

    <div
      class="c-file-upload__zone"
      :class="{ 'c-file-upload__zone--drag': dragging }"
      @click="openPicker"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <span>{{ t('shared.fileUpload.dragDrop') }} </span>
      <span class="c-file-upload__browse">{{ t('shared.fileUpload.browse') }}</span>
    </div>

    <input
      ref="inputRef"
      type="file"
      class="c-file-upload__input"
      :multiple="multiple"
      :accept="accept"
      :disabled="disabled"
      @change="onInputChange"
    />

    <div v-if="files.length" class="c-file-upload__preview">
      <div v-for="(file, i) in files" :key="i" class="c-file-upload__file">
        <img
          v-if="isImage(file)"
          :src="URL.createObjectURL(file)"
          class="c-file-upload__thumb"
          alt=""
        />
        <div class="c-file-upload__info">
          <span class="c-file-upload__name">{{ file.name }}</span>
          <span class="c-file-upload__size">{{ formatSize(file.size) }}</span>
        </div>
        <button
          class="c-file-upload__remove"
          :aria-label="t('shared.fileUpload.remove')"
          @click.stop="removeFile(i)"
        >
          &times;
        </button>
      </div>
    </div>

    <span v-if="error" class="c-file-upload__error">{{ error }}</span>
  </div>
</template>

<style scoped>
.c-file-upload {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.c-file-upload__label {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.c-file-upload__zone {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-xs);
  padding: var(--space-lg);
  border: 2px dashed var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-caption);
  color: var(--text-secondary);
  transition:
    border-color 0.2s,
    background 0.2s;
}

.c-file-upload__zone:hover {
  border-color: var(--primary);
}

.c-file-upload__zone--drag {
  border-color: var(--accent);
  background: var(--o-tint-8);
}

.c-file-upload__browse {
  color: var(--primary);
  font-weight: 600;
  text-decoration: underline;
}

.c-file-upload__input {
  display: none;
}

.c-file-upload__preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.c-file-upload__file {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.c-file-upload__thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: var(--radius-sm);
}

.c-file-upload__info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.c-file-upload__name {
  font-size: var(--text-caption);
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.c-file-upload__size {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.c-file-upload__remove {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: var(--text-xl);
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.c-file-upload__remove:hover {
  color: var(--error);
}

.c-file-upload__error {
  font-size: var(--text-sm);
  color: var(--error);
}

.c-file-upload--disabled .c-file-upload__zone {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
