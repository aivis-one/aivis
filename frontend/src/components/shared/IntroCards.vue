<script setup lang="ts">
// Three cards that tell a newcomer what the service is, where they are and
// what to do here, shown once before the first entry: on the sign-in and
// registration screens, and on the buyer's home screen for a first entry
// from Telegram, which skips those screens. Mounted once, in App.vue.
// "Seen" is kept in localStorage; storage that throws (a private window,
// blocked site data) only means the cards may show again.

import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CButton, CModal } from '@/components/ui'

const SEEN_KEY = 'aivis_intro_seen'
const ROUTES = new Set(['login', 'register', 'investor-dashboard'])
const CARDS = ['what', 'where', 'how'] as const

const { t } = useI18n()
const route = useRoute()

function readSeen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === '1'
  } catch {
    return false
  }
}

const seen = ref<boolean>(readSeen())
const step = ref<number>(0)

const open = computed<boolean>(
  () => !seen.value && typeof route.name === 'string' && ROUTES.has(route.name),
)
const card = computed(() => CARDS[step.value] ?? CARDS[0])
const last = computed<boolean>(() => step.value === CARDS.length - 1)

function finish(): void {
  seen.value = true
  try {
    localStorage.setItem(SEEN_KEY, '1')
  } catch {
    // Storage unavailable: the cards close for this visit only.
  }
}

function next(): void {
  if (last.value) finish()
  else step.value += 1
}
</script>

<template>
  <CModal :open="open" :title="t(`intro.${card}.title`)" @close="finish">
    <!-- Step dots (K32); their spoken position needs a line of the translation tables. -->
    <ol class="ds-dots" aria-hidden="true">
      <li
        v-for="(c, i) in CARDS"
        :key="c"
        class="ds-dots__dot"
        :aria-current="i === step ? 'step' : undefined"
      />
    </ol>
    <p class="ds-dialog__text">
      {{ t(`intro.${card}.text`) }}
    </p>
    <div class="ds-dialog__actions">
      <CButton v-if="!last" variant="outline" size="sm" inline @click="finish">
        {{ t('intro.skip') }}
      </CButton>
      <CButton variant="primary" size="sm" inline @click="next">
        {{ last ? t('intro.start') : t('intro.next') }}
      </CButton>
    </div>
  </CModal>
</template>
