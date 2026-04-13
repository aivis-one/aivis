<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  small?: boolean
}>()

const { t } = useI18n()
</script>

<template>
  <div class="cbs-logo" :class="{ 'cbs-logo--small': small }">
    <img src="/logo.svg" :alt="t('app.name')" />
  </div>
</template>

<style scoped>
.cbs-logo {
  display: flex;
  align-items: center;
  justify-content: center;
}

.cbs-logo img {
  height: 48px;
  width: auto;
}

.cbs-logo--small img {
  height: 32px;
}
</style>
