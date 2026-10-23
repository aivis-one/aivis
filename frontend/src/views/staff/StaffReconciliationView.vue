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
import { ShieldCheck } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CLoader } from '@/components/ui'
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
    <p class="recon__hint">
      <ShieldCheck :size="16" />
      {{ t('staff.reconciliation.hint') }}
    </p>

    <div v-if="loading" class="recon__center">
      <CLoader :size="32" />
    </div>

    <div v-else-if="errorText" class="recon__center">
      <p class="recon__error">{{ errorText }}</p>
      <CButton variant="secondary" size="sm" @click="run">
        {{ t('common.retry') }}
      </CButton>
    </div>

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
        <CButton variant="outline" size="sm" @click="run">
          {{ t('staff.reconciliation.runAgain') }}
        </CButton>
      </div>

      <ul class="recon__list">
        <li v-for="r in rows" :key="r.name" class="recon__row">
          <div class="recon__row-head">
            <span class="recon__code">{{ r.name }}</span>
            <CBadge
              :variant="r.status === 'pass' ? 'success' : 'danger'"
              :text="
                r.status === 'pass'
                  ? t('staff.reconciliation.pass')
                  : t('staff.reconciliation.fail')
              "
            />
            <span class="recon__severity">{{ severityLabel(r.severity) }}</span>
          </div>
          <div class="recon__what">{{ describe(r.name) }}</div>
          <dl v-if="detailLines(r.details).length" class="recon__details">
            <template v-for="[label, value] in detailLines(r.details)" :key="label">
              <dt>{{ label }}</dt>
              <dd>{{ value }}</dd>
            </template>
          </dl>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.recon {
  padding: var(--space-4);
}

.recon__hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  margin: 0 0 var(--space-4);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-inline-size: var(--maxw-prose);
}

.recon__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-block-size: var(--center-md);
  gap: var(--space-4);
}

.recon__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

.recon__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-block-end: var(--space-4);
}

.recon__counts {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}

.recon__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recon__row {
  padding: var(--space-3) 0;
  border-block-end: thin solid var(--border-default);
}

.recon__row-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.recon__code {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--text-primary);
}

.recon__severity {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.recon__what {
  margin-block-start: var(--space-1);
  font-size: var(--fs-sm);
  color: var(--text-primary);
  max-inline-size: var(--maxw-prose);
}

.recon__details {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0 var(--space-3);
  margin: var(--space-2) 0 0;
  font-size: var(--fs-xs);
}
.recon__details dt {
  color: var(--text-tertiary);
}
.recon__details dd {
  margin: 0;
  color: var(--text-primary);
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}
</style>
