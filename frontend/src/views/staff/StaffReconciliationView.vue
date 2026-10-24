<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffReconciliationView (Finance > Money check)
// =============================================================================
//
// The administrator's check of the platform's money: every consistency check
// the server runs over the accounts, the purchases and the instalment plans,
// shown as one list with the failures first. Each check is named in plain
// words (not by its code alone) and shows the figures it counted, so a failure
// says what to look at.
//
// GET /api/v1/staff/consistency (needs financial_operations; this screen is the
// administrator's). Running it also writes a failing check to the server's
// audit log, which is why it is run by a press and on opening, never on a timer.
//
// A FAILED READ IS AN ERROR, NOT AN EMPTY LIST: a check that could not be run
// does not read as "all fine".
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import { ApiResponseError } from '@/api/client'
import { fetchConsistency } from '@/api/admin'
import { tOrRaw } from '@/utils/i18n'
import type { ConsistencyResponse } from '@/api/generated'

const { t } = useI18n()

const report = ref<ConsistencyResponse | null>(null)
const loading = ref(true)
const errorText = ref<string | null>(null)

async function run(): Promise<void> {
  loading.value = true
  errorText.value = null
  try {
    report.value = await fetchConsistency()
  } catch (err) {
    errorText.value = err instanceof ApiResponseError && err.detail ? err.detail : t('common.error')
  } finally {
    loading.value = false
  }
}

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1 }

/** The failures first, then by how serious the check is, then by code. */
const rows = computed(() => {
  const results = report.value?.results ?? []
  return [...results].sort((a, b) => {
    const fail = Number(b.status === 'fail') - Number(a.status === 'fail')
    if (fail !== 0) return fail
    const sev = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
    if (sev !== 0) return sev
    return a.name.localeCompare(b.name)
  })
})

function describe(name: string): string {
  return tOrRaw(t, `staff.reconciliation.checks.${name}`, name)
}

function severityLabel(severity: string): string {
  return tOrRaw(t, `staff.reconciliation.severity.${severity}`, severity)
}

function detailLines(details: Record<string, unknown> | null | undefined): [string, string][] {
  if (!details) return []
  return Object.entries(details).map(([key, value]) => [
    tOrRaw(t, `staff.reconciliation.details.${key}`, key),
    typeof value === 'object' ? JSON.stringify(value) : String(value),
  ])
}

onMounted(run)
</script>

<template>
  <div class="recon">
    <CAlert tone="info">
      {{ t('staff.reconciliation.hint') }}
    </CAlert>

    <CLoader v-if="loading" centered extent="page" />

    <CEmptyState v-else-if="errorText" tone="danger" :title="errorText">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="run">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <CEmptyState
      v-else-if="!report || !report.results.length"
      :title="t('staff.reconciliation.empty')"
    />

    <template v-else>
      <div class="recon__summary">
        <CBadge
          :variant="report.overall_status === 'pass' ? 'success' : 'danger'"
          :text="
            report.overall_status === 'pass'
              ? t('staff.reconciliation.allPassed')
              : t('staff.reconciliation.someFailed')
          "
        />
        <span class="recon__counts">
          {{
            t('staff.reconciliation.counts', {
              passed: report.passed,
              total: report.total,
              failed: report.failed,
            })
          }}
        </span>
        <CButton variant="outline" size="sm" inline @click="run">
          {{ t('staff.reconciliation.runAgain') }}
        </CButton>
      </div>

      <ul class="ds-rows">
        <li v-for="r in rows" :key="r.name" class="ds-row">
          <span class="ds-row__body">
            <span class="ds-row__title recon__code">{{ r.name }}</span>
            <span class="ds-row__meta">{{ severityLabel(r.severity) }}</span>
            <span class="recon__what">{{ describe(r.name) }}</span>
            <dl v-if="detailLines(r.details).length" class="ds-kv">
              <div v-for="[label, value] in detailLines(r.details)" :key="label" class="ds-kv__row">
                <dt>{{ label }}</dt>
                <dd>{{ value }}</dd>
              </div>
            </dl>
          </span>
          <span class="ds-row__trail">
            <CBadge
              :variant="r.status === 'pass' ? 'success' : 'danger'"
              :text="
                r.status === 'pass'
                  ? t('staff.reconciliation.pass')
                  : t('staff.reconciliation.fail')
              "
            />
          </span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.recon {
  display: grid;
  gap: var(--space-4);
  align-content: start;
}

.recon__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.recon__counts {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

/* A check's code is read and copied character by character: the mono family. */
.recon__code {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}

.recon__what {
  font-size: var(--fs-sm);
  color: var(--text-primary);
  max-inline-size: var(--maxw-prose);
}
</style>
