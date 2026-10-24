<script setup lang="ts">
// The product's own start page: the name and the version, on the auth shell (K33).

import { useI18n } from 'vue-i18n'
import AuthShell from '@/components/layout/AuthShell.vue'

const { t } = useI18n()
</script>

<template>
  <AuthShell>
    <h1 class="ds-auth__title">
      {{ t('app.name') }}
    </h1>
    <p class="ds-auth__subtitle">v0.1.0</p>
  </AuthShell>
</template>
