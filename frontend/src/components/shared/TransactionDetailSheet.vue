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
//   formatPrice, *_id values are shown as-is, tx_hash is shown whole as
//   a copyable value (K53), anything else is stringified.
//
// OWNERSHIP.
//   Backend 404s for events owned by another user. The sheet
//   surfaces this as a generic "could not load" message -- the
//   only path to trigger it is a deep-link attempt, which isn't
//   a flow we expose in F4.3.
// =============================================================================

import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Copy } from '@/components/ui/icons'

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

const isCompany = useRoute().meta.shell === 'company'

function typeLabel(type: string): string {
  const own = tOrRaw(t, `inv.transactions.type.${type}`, type)
  return isCompany ? tOrRaw(t, `comp.operations.type.${type}`, own) : own
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

// The line under a copyable value says what happened, in words (K53).
const copyStatus = ref('')

async function copyValue(value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    copyStatus.value = t('inv.transactions.detail.copied')
    showToast(copyStatus.value, 'success')
  } catch {
    copyStatus.value = t('inv.transactions.detail.copyError')
    showToast(copyStatus.value, 'error')
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
    <div v-if="loading" class="ds-empty">
      <CLoader :size="24" />
    </div>

    <CEmptyState
      v-else-if="errored"
      tone="danger"
      :title="t('inv.transactions.detail.loadError')"
    />

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

      <!-- Details: a key-value list (K49); the hash is a copyable value (K53) -->
      <dl v-if="hasDetails" class="ds-kv">
        <div v-for="[key, value] in detailEntries" :key="key" class="ds-kv__row">
          <dt>{{ keyLabel(key) }}</dt>
          <dd>
            <div v-if="key === 'tx_hash' && typeof value === 'string'" class="ds-copy">
              <div class="ds-copy__box">
                <p class="ds-copy__value">{{ value }}</p>
                <button
                  type="button"
                  class="ds-button ds-button--ghost ds-button--icon ds-copy__button"
                  data-size="sm"
                  :aria-label="t('inv.transactions.detail.copy')"
                  @click="copyValue(value)"
                >
                  <Copy size="sm" />
                </button>
              </div>
              <p class="ds-copy__status" role="status" aria-live="polite">{{ copyStatus }}</p>
            </div>
            <template v-else>
              {{ formatValue(key, value) }}
            </template>
          </dd>
        </div>
      </dl>
    </div>
  </CBottomSheet>
</template>

<style scoped>
.tds {
  display: grid;
  gap: var(--space-4-lg);
}

/* Summary: the type, the amount (credit or debit coloured, the sign in the text)
   and the date, centred. */
.tds__summary {
  display: grid;
  justify-items: center;
  gap: var(--space-2);
  text-align: center;
  padding-block: var(--space-1) var(--space-2);
}
.tds__type {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}
.tds__amount {
  font-size: var(--fs-2xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: var(--lh-tight);
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
</style>
