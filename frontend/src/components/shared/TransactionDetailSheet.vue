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

import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Check, Copy } from '@/components/ui/icons'

import CBottomSheet from '@/components/ui/CBottomSheet.vue'
import { CEmptyState, CLoader } from '@/components/ui'
import { getTransaction } from '@/api/transactions'
import { formatDateTime, formatNumber, formatPrice, formatSignedPrice } from '@/utils/format'
import { formatPartPrice, partsOf } from '@/utils/parts'
import { useSharesPerOption } from '@/composables/useSharesPerOption'
import { tOrRaw } from '@/utils/i18n'
import type { TransactionResponse } from '@/api/types'

const props = defineProps<{
  open: boolean
  transactionId: string | null
}>()

const emit = defineEmits<{ close: [] }>()

const { t, locale } = useI18n()

const txn = ref<TransactionResponse | null>(null)
const loading = ref(false)
const errored = ref(false)

// Epoch guard -- if the user taps a new row before the previous
// fetch resolves, the older resolve must not overwrite the newer
// one. Same pattern as stores/transactions.ts.
let fetchEpoch = 0

// Entries to render in the key-value table. Filters out null/
// undefined values so an empty field doesn't render as a blank row.
const { ensure: ensureParts, partsPerLot } = useSharesPerOption()

// A purchase entry counts lots and the lot's price; the buyer sees parts and the
// price of a part. Both lines wait for the project's parts per lot and are left
// out until it is known (the lot figures are never shown in their place).
const LOT_KEYS = ['units', 'price_per_unit_cents'] as const

function detailsProjectId(): string | null {
  const id = txn.value?.details?.company_id
  return typeof id === 'string' ? id : null
}

const detailEntries = computed<[string, unknown][]>(() => {
  const d = txn.value?.details
  if (!d) return []
  const parts = partsPerLot(detailsProjectId())
  return Object.entries(d).filter(
    ([k, v]) =>
      v !== null &&
      v !== undefined &&
      !((LOT_KEYS as readonly string[]).includes(k) && parts === null),
  )
})

const hasDetails = computed<boolean>(() => detailEntries.value.length > 0)

const signedAmount = computed<string>(() => {
  if (!txn.value) return ''
  return formatSignedPrice(txn.value.amount_cents, txn.value.currency)
})

const amountTone = computed<'success' | 'danger' | undefined>(() => {
  if (!txn.value) return undefined
  if (txn.value.amount_cents > 0) return 'success'
  if (txn.value.amount_cents < 0) return 'danger'
  return undefined
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
  const perLot = partsPerLot(detailsProjectId())
  if (perLot !== null && typeof value === 'number') {
    if (key === 'units') return formatNumber(partsOf(value, perLot), locale.value)
    if (key === 'price_per_unit_cents') return formatPartPrice(value, perLot, locale.value)
  }
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
const copied = ref(false)
let copyStatusTimer: ReturnType<typeof setTimeout> | undefined

function tellCopy(text: string, ok: boolean): void {
  copyStatus.value = text
  copied.value = ok
  clearTimeout(copyStatusTimer)
  copyStatusTimer = setTimeout(() => {
    copyStatus.value = ''
    copied.value = false
  }, 3000)
}

onUnmounted(() => clearTimeout(copyStatusTimer))

async function copyValue(value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    tellCopy(t('inv.transactions.detail.copied'), true)
  } catch {
    tellCopy(t('inv.transactions.detail.copyError'), false)
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
    const projectId = detailsProjectId()
    if (projectId) void ensureParts([projectId])
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
    <CLoader v-if="loading" centered />

    <CEmptyState
      v-else-if="errored"
      tone="danger"
      :title="t('inv.transactions.detail.loadError')"
    />

    <div v-else-if="txn" class="tds">
      <!-- Summary header -->
      <div class="tds__summary">
        <div class="ds-label" data-size="md">
          {{ typeLabel(txn.type) }}
        </div>
        <div class="ds-amount" :data-tone="amountTone">
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
                  <Check v-if="copied" size="sm" />
                  <Copy v-else size="sm" />
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

/* Summary: the type, the amount (credit or debit toned, the sign in the text)
   and the date, centred. */
.tds__summary {
  display: grid;
  justify-items: center;
  gap: var(--space-2);
  text-align: center;
  padding-block: var(--space-1) var(--space-2);
}
.tds__date {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}
</style>
