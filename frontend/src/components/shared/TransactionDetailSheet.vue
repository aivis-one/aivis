<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- TransactionDetailSheet (Phase F4.3 B3)
// =============================================================================
//
// Bottom-sheet with the full detail of a single transaction event.
// Triggered by tapping a row in TransactionsView.
//
// DATA FLOW.
//   Parent owns `selectedId` and passes it via `transaction-id`
//   together with `open`. The sheet fetches on open transition --
//   it cannot lean on the list payload because GET /transactions
//   returns the same shape, but a dedicated request keeps
//   future-proofing clean (backend may add larger payloads to
//   the detail endpoint specifically).
//
// KEY RENDERING STRATEGY (variant (c), per B3 scope decision).
//   Generic key-value iteration over `details` JSONB with two
//   escape hatches:
//     1. Known keys get human labels from
//        inv.transactions.detail.keys.{key}. Maintained by hand,
//        covers today's backend vocabulary.
//     2. Unknown keys fall back to a humanised version of the raw
//        snake_case token (trigger_tranche_number ->
//        "Trigger Tranche Number") so no future backend addition
//        renders as a raw identifier.
//   Values get minimal formatting: *_cents keys run through
//   formatPrice, *_id values are shown as-is, tx_hash gets the
//   truncate + copy treatment, anything else is stringified.
//
// OWNERSHIP.
//   Backend 404s for events owned by another user. The sheet
//   surfaces this as a generic "could not load" message -- the
//   only path to trigger it is a deep-link attempt, which isn't
//   a flow we expose in F4.3.
// =============================================================================

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Copy } from 'lucide-vue-next'

import CBottomSheet from '@/components/ui/CBottomSheet.vue'
import { CEmptyState, CLoader } from '@/components/ui'
import { getTransaction } from '@/api/transactions'
import { useToast } from '@/composables/useToast'
import { formatDateTime, formatPrice, formatSignedPrice } from '@/utils/format'
import { tOrRaw } from '@/utils/i18n'
import type { TransactionResponse } from '@/api/types'

const props = defineProps<{
  open: boolean
  transactionId: string | null
}>()

const emit = defineEmits<{ close: [] }>()

const { t, locale } = useI18n()
const { showToast } = useToast()

const txn = ref<TransactionResponse | null>(null)
const loading = ref(false)
const errored = ref(false)

// Epoch guard -- if the user taps a new row before the previous
// fetch resolves, the older resolve must not overwrite the newer
// one. Same pattern as stores/transactions.ts.
let fetchEpoch = 0

// Entries to render in the key-value table. Filters out null/
// undefined values so an empty field doesn't render as a blank row.
const detailEntries = computed<[string, unknown][]>(() => {
  const d = txn.value?.details
  if (!d) return []
  return Object.entries(d).filter(([, v]) => v !== null && v !== undefined)
})

const hasDetails = computed<boolean>(() => detailEntries.value.length > 0)

const signedAmount = computed<string>(() => {
  if (!txn.value) return ''
  return formatSignedPrice(txn.value.amount_cents, txn.value.currency)
})

const amountClass = computed<string>(() => {
  if (!txn.value) return ''
  if (txn.value.amount_cents > 0) return 'tds__amount--credit'
  if (txn.value.amount_cents < 0) return 'tds__amount--debit'
  return ''
})

function typeLabel(type: string): string {
  return tOrRaw(t, `inv.transactions.type.${type}`, type)
}

function keyLabel(key: string): string {
  // Humanise snake_case as the raw fallback: 'trigger_tranche_number'
  // -> 'Trigger Tranche Number'. tOrRaw then prefers a real
  // translation if the key is in the catalogue, otherwise returns
  // the humanised form so unknown backend additions stay readable.
  const humanised = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return tOrRaw(t, `inv.transactions.detail.keys.${key}`, humanised)
}

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return ''
  // *_cents -> currency string. Picked up by suffix so every
  // price_per_unit_cents / amount_cents / total_cents future
  // addition formats correctly without an allow-list.
  if (typeof value === 'number' && key.endsWith('_cents')) {
    return formatPrice(value, txn.value?.currency)
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function truncateHash(value: string): string {
  // Middle-truncate so both the prefix (network marker) and the
  // checksum tail remain visible. Threshold 18 keeps short hashes
  // intact on desktop.
  if (value.length <= 18) return value
  return `${value.slice(0, 8)}…${value.slice(-6)}`
}

async function copyValue(value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    showToast(t('inv.transactions.detail.copied'), 'success')
  } catch {
    showToast(t('inv.transactions.detail.copyError'), 'error')
  }
}

async function load(id: string): Promise<void> {
  const epoch = ++fetchEpoch
  loading.value = true
  errored.value = false
  txn.value = null
  try {
    const resp = await getTransaction(id)
    if (epoch !== fetchEpoch) return
    txn.value = resp
  } catch {
    if (epoch !== fetchEpoch) return
    errored.value = true
  } finally {
    if (epoch === fetchEpoch) {
      loading.value = false
    }
  }
}

// Fetch when the sheet transitions to open with a non-null id.
// Using a two-arg watch keeps the behaviour tied to both signals
// instead of reacting to every id change even while closed.
watch(
  () => [props.open, props.transactionId] as const,
  ([open, id]) => {
    if (open && id) {
      void load(id)
    }
    if (!open) {
      // Reset so a subsequent open on the same id still refetches
      // (avoids showing stale data if the record changed server-side
      // between views -- cheap, transactions are small).
      txn.value = null
      errored.value = false
      fetchEpoch++ // invalidate any in-flight fetch on close
    }
  },
  { immediate: true },
)

function onClose(): void {
  emit('close')
}
</script>

<template>
  <CBottomSheet :open="open" :title="t('inv.transactions.detail.title')" @close="onClose">
    <div v-if="loading" class="tds__center">
      <CLoader :size="24" />
    </div>

    <div v-else-if="errored" class="tds__center">
      <CEmptyState :title="t('inv.transactions.detail.loadError')" />
    </div>

    <div v-else-if="txn" class="tds">
      <!-- Summary header -->
      <div class="tds__summary">
        <div class="tds__type">
          {{ typeLabel(txn.type) }}
        </div>
        <div class="tds__amount" :class="amountClass">
          {{ signedAmount }}
        </div>
        <div class="tds__date">
          {{ formatDateTime(txn.created_at, locale) }}
        </div>
      </div>

      <!-- Details key-value -->
      <div v-if="hasDetails" class="tds__details">
        <div v-for="[key, value] in detailEntries" :key="key" class="tds__row">
          <span class="tds__key">{{ keyLabel(key) }}</span>
          <span class="tds__value">
            <template v-if="key === 'tx_hash' && typeof value === 'string'">
              <span class="tds__hash" :title="value">
                {{ truncateHash(value) }}
              </span>
              <button
                class="tds__copy"
                type="button"
                :aria-label="t('inv.transactions.detail.copy')"
                @click="copyValue(value)"
              >
                <Copy :size="16" />
              </button>
            </template>
            <template v-else>
              {{ formatValue(key, value) }}
            </template>
          </span>
        </div>
      </div>
    </div>
  </CBottomSheet>
</template>

<style scoped>
.tds {
  display: flex;
  flex-direction: column;
  gap: var(--space-4-lg);
}

.tds__center {
  display: flex;
  justify-content: center;
  padding: var(--space-5) 0;
}

/* Summary */
.tds__summary {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  text-align: center;
  padding: var(--space-1) 0 var(--space-2);
}
.tds__type {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.tds__amount {
  font-size: var(--fs-2xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
  word-break: break-word;
}
.tds__amount--credit {
  color: var(--success);
}
.tds__amount--debit {
  color: var(--danger);
}
.tds__date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

/* Details table */
.tds__details {
  display: flex;
  flex-direction: column;
  gap: 0;
  border-top: 1px solid var(--border-default);
}
.tds__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
  font-size: var(--fs-sm);
}
.tds__key {
  color: var(--text-secondary);
  font-weight: 600;
  flex-shrink: 0;
}
.tds__value {
  color: var(--text-primary);
  text-align: end;
  font-family: inherit;
  word-break: break-word;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  justify-content: flex-end;
}

.tds__hash {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-primary);
  user-select: all;
}

.tds__copy {
  background: none;
  border: none;
  padding: var(--space-1);
  color: var(--text-tertiary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.tds__copy:hover {
  color: var(--primary);
  background: var(--bg-subtle);
}

/* READING MEASURE — descriptive text only. --maxw-prose (680px) is a CEILING,
   so this rule cannot bind until the container is already wider than a
   comfortable line: on a phone it does nothing at all, which is why it needs
   no media query. Measured at 1280 before applying: `event-card__desc` ran to
   932px and `staff-dash__role-count` to 901. Names, figures and table cells
   are deliberately NOT capped — a name is not prose, and capping it would only
   leave dead space in its row. */
.tds__summary {
  max-width: var(--maxw-prose);
}
</style>
