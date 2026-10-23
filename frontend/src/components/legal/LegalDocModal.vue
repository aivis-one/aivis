<script setup lang="ts">
// The cabinet's own document window, on the design system's Document sheet and
// viewer (K36), placement `modal`: fetches the static legal HTML the cabinet ships
// (BASE_URL + legal/<lang>/<type>.html), keeps only the <body> content and shows it
// in the viewer's scrollable body. Used by the onboarding signing screen and by the
// consent line on the registration screen. The legal folder ships with our own
// repo, so the body is rendered with v-html without sanitising.
//
// States: loading (the body is busy, with a Loader), loaded, error (an Alert with a
// Retry). Escape, the close buttons and a click on the scrim close it.

import { ref, toRef, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CLoader } from '@/components/ui'
import { AlertTriangle, X } from '@/components/ui/icons'
import { useDialog } from '@/composables/useDialog'

const props = defineProps<{
  open: boolean
  title: string
  lang: string
  type: string
}>()

const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const titleId = useId()

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

// Escape, focus containment and focus restore.
const dialogEl = ref<HTMLElement | null>(null)
useDialog(toRef(props, 'open'), dialogEl, () => emit('close'))

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
  <Teleport to="body">
    <div v-if="open" class="ds-docviewer" data-variant="modal" @click.self="emit('close')">
      <div
        ref="dialogEl"
        class="ds-docviewer__dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <div class="ds-docviewer__head">
          <h2 :id="titleId" class="ds-docviewer__title">{{ title }}</h2>
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
        <div
          class="ds-docviewer__body"
          tabindex="0"
          role="region"
          :aria-labelledby="titleId"
          :aria-busy="loading ? 'true' : undefined"
        >
          <CLoader v-if="loading" />
          <div v-else-if="error" class="ds-alert ds-alert--danger" role="alert">
            <span class="ds-alert__icon" aria-hidden="true"><AlertTriangle size="sm" /></span>
            <div class="ds-alert__content">
              <p class="ds-alert__text">{{ error }}</p>
              <div class="ds-alert__actions">
                <button
                  type="button"
                  class="ds-button ds-button--secondary"
                  data-size="sm"
                  @click="load"
                >
                  {{ t('common.retry') }}
                </button>
              </div>
            </div>
          </div>
          <!-- Trusted content: HTML authored in our own repo. -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-else v-html="content" />
        </div>
        <div class="ds-docviewer__actions">
          <button type="button" class="ds-button ds-button--primary" @click="emit('close')">
            {{ t('common.close') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
