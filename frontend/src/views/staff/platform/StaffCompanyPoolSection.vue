<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCompanyPoolSection (a project's pool of parts)
// =============================================================================
//
// The pool is the part of the project's parts that is offered for sale. It is
// read here (how many parts it holds, how many are sold, how many are left)
// and created here when the project has none yet: a project can have products
// only after it has a pool.
//
// In the standard division 25 percent of the parts are for sale, so 25 is what
// the creation form starts with. A pool is created once; this screen has no
// control that makes it larger afterwards -- parts for sale are not added.
//
// GET  /api/v1/staff/companies/{id}/pool   (company_manage)
// POST /api/v1/staff/companies/{id}/pool   (project_manage AND financial_operations)
//
// The pool's percentage is the server's number (Decimal); this screen shows it
// as it came and does no arithmetic on it.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CBadge, CButton, CEmptyState, CLoader, CModal } from '@/components/ui'
import { ApiResponseError } from '@/api/client'
import { createStaffCompanyPool, fetchStaffCompanyPool } from '@/api/staff-companies'
import { useStaffPermissions } from '@/composables/useStaffPermissions'
import { useToast } from '@/composables/useToast'
import { formatNumber } from '@/utils/format'
import type { PoolResponse } from '@/api/types'

const { t, locale } = useI18n()
const route = useRoute()
const { showToast } = useToast()
const { canDo } = useStaffPermissions()

// Creating the pool is a financial act: both rights, as the server asks.
const canManage = canDo('project_manage')
const canFinancial = canDo('financial_operations')
const canCreate = computed<boolean>(() => canManage.value && canFinancial.value)

const companyId = computed<string>(() => {
  const raw = route.params.id
  return typeof raw === 'string' ? raw : ''
})

const pool = ref<PoolResponse | null>(null)
const loading = ref(true)
const error = ref(false)

async function load(): Promise<void> {
  const id = companyId.value
  if (!id) return
  loading.value = true
  error.value = false
  try {
    pool.value = await fetchStaffCompanyPool(id)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

// -- Creating the pool --------------------------------------------------------

const showCreate = ref(false)
const percentDraft = ref('25')
const saving = ref(false)

// A percentage above 0 and up to 100, with up to four decimals (the server's).
const percentValid = computed<boolean>(() => {
  const text = percentDraft.value.trim()
  if (!/^\d{1,3}(\.\d{1,4})?$/.test(text)) return false
  const n = Number(text)
  return n > 0 && n <= 100
})

function openCreate(): void {
  if (!canCreate.value) return
  percentDraft.value = '25'
  showCreate.value = true
}

async function handleCreate(): Promise<void> {
  if (!canCreate.value || !percentValid.value) return
  saving.value = true
  try {
    pool.value = await createStaffCompanyPool(companyId.value, {
      equity_percent: '25',
    })
    showCreate.value = false
    showToast(t('staff.platform.pool.created'), 'success')
  } catch (err) {
    showToast(
      err instanceof ApiResponseError && err.detail ? err.detail : t('common.error'),
      'error',
    )
  } finally {
    saving.value = false
  }
}

watch(companyId, () => void load())
onMounted(load)
</script>

<template>
  <div class="scpool">
    <div v-if="loading" class="scpool__center">
      <CLoader />
    </div>

    <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="load">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <template v-else-if="pool">
      <p class="scpool__hint">{{ t('staff.platform.pool.hint') }}</p>
      <!-- The pool's facts (K49) -->
      <dl class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.pool.status') }}</dt>
          <dd>
            <CBadge
              :variant="pool.status === 'active' ? 'success' : 'neutral'"
              :text="pool.status === 'active' ? t('staff.platform.pool.active') : pool.status"
            />
          </dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.pool.share') }}</dt>
          <dd>{{ pool.equity_percent }}%</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.pool.total') }}</dt>
          <dd>{{ formatNumber(pool.total_options, locale) }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.pool.sold') }}</dt>
          <dd>{{ formatNumber(pool.consumed, locale) }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.platform.pool.left') }}</dt>
          <dd>{{ formatNumber(pool.remaining, locale) }}</dd>
        </div>
      </dl>
      <p class="scpool__hint">{{ t('staff.platform.pool.fixedNote') }}</p>
    </template>

    <template v-else>
      <p class="scpool__hint">{{ t('staff.platform.pool.none') }}</p>
      <div v-if="canCreate">
        <CButton variant="primary" size="sm" inline @click="openCreate">
          {{ t('staff.platform.pool.create') }}
        </CButton>
      </div>
    </template>

    <CModal
      :open="showCreate"
      :title="t('staff.platform.pool.createTitle')"
      @close="showCreate = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.platform.pool.createHint') }}
      </p>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showCreate = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="saving"
          :disabled="saving"
          @click="handleCreate"
        >
          {{ t('staff.platform.pool.create') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.scpool {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.scpool__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-sm);
  gap: var(--space-3);
}

.scpool__hint {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  max-inline-size: var(--maxw-prose);
}
</style>
