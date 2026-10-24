<script setup lang="ts">
// Full-screen loading view displayed during auth initialization, on the auth
// shell (K33): the logo is the shell's, the screen is a title and the Loader (K20).

import { useI18n } from 'vue-i18n'
import AuthShell from '@/components/layout/AuthShell.vue'
import CLoader from '@/components/ui/CLoader.vue'

const { t } = useI18n()
</script>

<template>
  <AuthShell>
    <div class="ds-auth__icon">
      <CLoader />
    </div>
    <h1 class="ds-auth__title">
      {{ t('common.loading') }}
    </h1>
  </AuthShell>
</template>
