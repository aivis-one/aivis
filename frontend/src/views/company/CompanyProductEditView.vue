<script setup lang="ts">
// Stub — will be replaced with full implementation in F5.2.
// Product detail (readonly, editing via Staff).

import { useI18n } from 'vue-i18n'
import { CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'

const { t } = useI18n()

// The frame's header carries the title.
useScreenHeader({ title: () => t('nav.comp.product_edit') })
</script>

<template>
  <CEmptyState :title="t('nav.comp.product_edit')" />
</template>
