<script setup lang="ts">
// 404 — page not found, on the auth shell (K33).
// Uses common.back key (exists) for button text.
// error.pageNotFound will show key string until i18n is added.

import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { safeNavigate } from '@/composables/safeNavigate'
import AuthShell from '@/components/layout/AuthShell.vue'
import { CButton } from '@/components/ui'

const { t } = useI18n()
const router = useRouter()

function goHome(): void {
  void safeNavigate(router.push('/'), '[NotFoundView] to home')
}
</script>

<template>
  <AuthShell>
    <h1 class="ds-auth__title">404</h1>
    <p class="ds-auth__subtitle">
      {{ t('error.pageNotFound') }}
    </p>
    <div class="ds-auth__form">
      <CButton @click="goHome">
        {{ t('common.back') }}
      </CButton>
    </div>
  </AuthShell>
</template>
