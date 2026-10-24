<script setup lang="ts">
// A document with a download, on the design system's Document row (K44): a row of
// the Row list (K23) whose ONE link is the file. The link holds the title, the
// description and the file's name and size, so its accessible name carries the
// type and size in text; the whole row is the target and the trailing icon is
// decoration.
//
// In the cabinet a file has no fixed address: the app asks the API for a
// short-lived link and then navigates to it. A row given an `href` (a public
// document's own page) keeps the link form, its click handled here
// (`preventDefault`, then the caller's `download`); a row without one is K44's
// button form, a file the app fetches by its own handler (no href, no download).
// Either way the row says what it is doing in `data-state` and `aria-busy`:
// `downloading` while the link is asked for (a second activation is ignored),
// `downloaded` once the browser has been sent to it, and the state's word in the
// status text. A failed download puts the row back at rest and tells the caller
// through `failed` (the caller shows its toast).
import { computed, ref } from 'vue'
import type { Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, Download } from '@/components/ui/icons'

const props = defineProps<{
  title: string
  /** The file's name and size, one line (the link's name carries it). */
  meta: string
  description?: string | null
  icon: Component
  /** The document's own page, when it has one; without it the row is a button. */
  href?: string
  download: () => Promise<void>
}>()

const emit = defineEmits<{ failed: [error: unknown] }>()

const { t } = useI18n()

type RowState = 'rest' | 'downloading' | 'downloaded'
const state = ref<RowState>('rest')

const status = computed(() =>
  state.value === 'downloading'
    ? t('common.downloading')
    : state.value === 'downloaded'
      ? t('common.downloaded')
      : '',
)

async function onClick(event: MouseEvent): Promise<void> {
  // The file is reached through the API, not through an href.
  event.preventDefault()
  if (state.value === 'downloading') return
  state.value = 'downloading'
  try {
    await props.download()
    state.value = 'downloaded'
  } catch (err) {
    state.value = 'rest'
    emit('failed', err)
  }
}
</script>

<template>
  <li
    class="ds-row ds-docrow"
    :data-state="state === 'rest' ? undefined : state"
    :aria-busy="state === 'downloading' ? 'true' : undefined"
  >
    <span class="ds-row__lead"><component :is="icon" size="sm" /></span>
    <span class="ds-row__body">
      <a v-if="href" class="ds-row__link" :href="href" @click="onClick">
        <span class="ds-row__title">{{ title }}</span>
        <span v-if="description" class="ds-row__meta">{{ description }}</span>
        <span class="ds-row__meta">{{ meta }}</span>
      </a>
      <button v-else type="button" class="ds-row__link" @click="onClick">
        <span class="ds-row__title">{{ title }}</span>
        <span v-if="description" class="ds-row__meta">{{ description }}</span>
        <span class="ds-row__meta">{{ meta }}</span>
      </button>
    </span>
    <span class="ds-row__trail">
      <span class="ds-docrow__status ds-sr-only" role="status">{{ status }}</span>
      <span class="ds-docrow__state"
        ><Check v-if="state === 'downloaded'" size="sm" /><Download v-else size="sm"
      /></span>
    </span>
  </li>
</template>
