<script setup lang="ts">
// Product detail (readonly, editing via Staff).

import { useI18n } from 'vue-i18n'
import { CEmptyState } from '@/components/ui'
import { useScreenHeader } from '@/components/layout/screenHeader'

const { t } = useI18n()

// The frame's header carries the title and the way back to the product list.
useScreenHeader({
  title: () => t('nav.comp.product_edit'),
  back: () => (window.history.state?.back ? true : { name: 'company-products' }),
})
</script>

<template>
  <CEmptyState :title="t('nav.comp.product_edit')" />
</template>
