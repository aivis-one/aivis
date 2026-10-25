<script setup lang="ts">
// Three cards that tell a newcomer what the service is, where they are and
// what to do here. They show once, to the buyer only, at the first entry to the
// buyer's home screen after registration, e-mail confirmation and the documents
// (the route guard lets nobody onto the home screen before onboarding is complete,
// so the home screen itself is that moment). Mounted once, in App.vue.
// "Seen" is kept in localStorage; storage that throws (a private window,
// blocked site data) only means the cards may show again.
//
// The three cards are one size (the dialog's fixed body), and each has a media
// part (the media card's cover, K07) that holds the card's picture; until the
// pictures are designed the part shows its fallback tile with an icon.

import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CButton, CModal } from '@/components/ui'
import { Home, Layers, Rocket } from '@/components/ui/icons'
import { useAuthStore } from '@/stores/auth'

const SEEN_KEY = 'aivis_intro_seen'
const ROUTE = 'investor-dashboard'
const CARDS = ['what', 'where', 'how'] as const

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()

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
  () => !seen.value && authStore.role === 'investor' && route.name === ROUTE,
)
const card = computed(() => CARDS[step.value] ?? CARDS[0])
const last = computed<boolean>(() => step.value === CARDS.length - 1)

// A card's picture; null until the pictures exist (the media part then shows its fallback).
const PICTURES: Record<(typeof CARDS)[number], string | null> = {
  what: null,
  where: null,
  how: null,
}
const FALLBACK_ICON = { what: Layers, where: Home, how: Rocket } as const
const picture = computed(() => PICTURES[card.value])

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
  <CModal :open="open" fixed-body :title="t(`intro.${card}.title`)" @close="finish">
    <!-- The card's picture (K07 cover); the fallback tile until the pictures exist. -->
    <div class="ds-card__media" :class="{ 'ds-card__media--fallback': !picture }" data-size="sm">
      <img v-if="picture" :src="picture" alt="" />
      <component :is="FALLBACK_ICON[card]" v-else />
    </div>
    <!-- Step dots (K32); the list says the position in words. -->
    <ol class="ds-dots" :aria-label="t('intro.step', { n: step + 1, total: CARDS.length })">
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
    <template #actions>
      <CButton v-if="!last" variant="outline" size="sm" inline @click="finish">
        {{ t('intro.skip') }}
      </CButton>
      <CButton variant="primary" size="sm" inline @click="next">
        {{ last ? t('intro.start') : t('intro.next') }}
      </CButton>
    </template>
  </CModal>
</template>
