<script setup lang="ts">
// 404 — page not found.
// Uses common.back key (exists) for button text.
// error.pageNotFound will show key string until i18n is added.

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import { CButton } from '@/components/ui'

const { t } = useI18n()
const router = useRouter()

function goHome(): void {
  void safeNavigate(router.push('/'), '[NotFoundView] to home')
}
</script>

<template>
  <div class="not-found">
    <h1 class="not-found__code">404</h1>
    <p class="not-found__text">{{ t('error.pageNotFound') }}</p>
    <CButton inline @click="goHome">
      {{ t('common.back') }}
    </CButton>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  padding: var(--space-5);
  text-align: center;
}

.not-found__code {
  font-size: var(--fs-hero);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  line-height: 1;
}

.not-found__text {
  font-size: var(--fs-body);
  color: var(--text-secondary);
  margin: var(--space-4) 0 var(--space-6);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.not-found__text { max-width: var(--maxw-prose); }
</style>
