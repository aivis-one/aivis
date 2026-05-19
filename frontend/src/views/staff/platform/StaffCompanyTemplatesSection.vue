<script setup lang="ts">
// =============================================================================
// CBSHOME Frontend -- StaffCompanyTemplatesSection (iter 2.7 Block C stub)
// =============================================================================
//
// SCAFFOLDING. Real content lands in Block C.
//
// Read-only inspection of per-company templates (R2 §6.3). Tab bar per kind (purchase_agreement / gift_certificate / installment_subcontract / ownership_certificate). MinIO deep-link for editing -- no in-app editor in MVP.
//
// FP-24 lazy-import stub policy: this file exists so the router
// import in /staff/platform/* resolves at build time. The block
// that owns the view replaces this stub wholesale -- no partial
// implementations in the stub.
// =============================================================================

import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="staff-platform-stub">
    <h2 class="staff-platform-stub__title">{{ t('staff.platform.company.tabs.templates') }}</h2>
    <p class="staff-platform-stub__placeholder">
      {{ t('staff.platform.scaffolding.placeholder') }}
    </p>
  </div>
</template>

<style scoped>
.staff-platform-stub {
  padding: var(--space-md, 16px);
}
.staff-platform-stub__title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 8px;
}
.staff-platform-stub__placeholder {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}
</style>
