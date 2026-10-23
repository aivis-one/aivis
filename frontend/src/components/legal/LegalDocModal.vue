<script setup lang="ts">
// The cabinet's own document window: fetches the static legal HTML the cabinet
// ships (BASE_URL + legal/<lang>/<type>.html), keeps only the <body> content and
// shows it in a CModal. Used by the onboarding signing screen and by the consent
// line on the registration screen. The legal folder ships with our own repo, so
// the body is rendered with v-html without sanitising.

import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CLoader, CModal } from '@/components/ui'

const props = defineProps<{
  open: boolean
  title: string
  lang: string
  type: string
}>()

const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

const content = ref('')
const loading = ref(false)
const error = ref('')

// A later open must not be overwritten by an earlier, slower fetch.
let epoch = 0

async function load(): Promise<void> {
  const mine = ++epoch
  content.value = ''
  error.value = ''
  loading.value = true
  try {
    const resp = await fetch(`${import.meta.env.BASE_URL}legal/${props.lang}/${props.type}.html`)
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const raw = await resp.text()
    // Pull the body innerHTML so the mounted node holds just the legal
    // content, not <html>, <head>, <title>, <meta>.
    const dom = new DOMParser().parseFromString(raw, 'text/html')
    if (mine === epoch) content.value = dom.body.innerHTML
  } catch {
    if (mine === epoch) error.value = t('common.error')
  } finally {
    if (mine === epoch) loading.value = false
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      void load()
    } else {
      epoch++
      content.value = ''
      error.value = ''
      loading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <CModal :open="open" @close="emit('close')">
    <h3 class="doc-modal__title">
      {{ title }}
    </h3>
    <div class="doc-modal__body">
      <div v-if="loading" class="doc-modal__center">
        <CLoader />
      </div>
      <p v-else-if="error" class="doc-modal__error">
        {{ error }}
      </p>
      <!-- Trusted content: HTML authored in our own repo. -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-else class="doc-modal__content" v-html="content" />
    </div>
    <div class="doc-modal__actions">
      <button
        type="button"
        class="doc-modal__close ds-button ds-button--primary"
        @click="emit('close')"
      >
        {{ t('common.close') }}
      </button>
    </div>
  </CModal>
</template>

<style scoped>
.doc-modal__title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
  padding-inline-end: var(--space-5); /* room for close button */
  overflow-wrap: anywhere;
}
.doc-modal__body {
  min-block-size: var(--center-sm);
  max-block-size: 60vh;
  overflow-y: auto;
  border: thin solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: var(--space-4);
  background: var(--bg-subtle);
  margin-block-end: var(--space-4);
}
.doc-modal__center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-sm);
}

.doc-modal__error {
  font-size: var(--fs-xs);
  color: var(--danger);
  text-align: center;
  margin: 0;
}
.doc-modal__content {
  font-size: var(--fs-sm);
  color: var(--text-primary);
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.doc-modal__content :deep(h1) {
  font-size: var(--fs-lg);
  margin: 0 0 var(--space-3);
}
.doc-modal__content :deep(h2) {
  font-size: var(--fs-body);
  margin: var(--space-4) 0 var(--space-2);
}
.doc-modal__content :deep(p) {
  margin: 0 0 var(--space-3);
}
.doc-modal__content :deep(ul),
.doc-modal__content :deep(ol) {
  margin: 0 0 var(--space-3);
  padding-inline-start: var(--space-4-lg);
}
.doc-modal__content :deep(li) {
  margin-block-end: var(--space-1);
}
.doc-modal__content :deep(table) {
  display: block;
  max-inline-size: 100%;
  overflow-x: auto;
}

.doc-modal__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
