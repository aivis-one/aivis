<script setup lang="ts">
// 404 — page not found.
// Uses common.back key (exists) for button text.
// error.pageNotFound will show key string until i18n is added.

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'

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
    <button class="not-found__btn" @click="goHome">
      {{ t('common.back') }}
    </button>
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

.not-found__btn {
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-md);
  /* --primary, not --accent: this is the screen's PRIMARY action. The owner
     found eight of these and they were fixed; the sweep found this one
     outside that pass's scope. `background: var(--accent)` resolves
     perfectly, so no token audit can ever see it -- only reading the
     selector name against the token name does. */
  background: var(--primary);
  color: var(--on-primary);
  font-weight: 600;
  font-size: var(--fs-sm);
  border: none;
  cursor: pointer;
  font-family: inherit;
}
</style>
