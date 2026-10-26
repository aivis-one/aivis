<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffGiftsView (Finance > Gifts)
// =============================================================================
//
// The staff action that gives a gift of the company: parts of a project handed
// to a person from the list of the deed of gift, after that person has passed
// the paid identity check. The staff member picks the person and the project
// (and the project's offer, when it has more than one) and enters the number
// of PARTS of the project. The server counts lots (a lot holds the project's
// `shares_per_option` parts, read from the project), so the screen turns the
// parts into lots, takes only a whole number of lots and names the two nearest
// valid counts of parts otherwise; it shows the price of one part and the total
// of the gift. The list below shows each gift in parts too. The cabinet stores the
// gift as waiting for acceptance and forms the gift certificate. NOTHING IS
// CREDITED until the person presses "accept the gift" in their own cabinet --
// until then the gift can be cancelled here.
//
// POST /api/v1/staff/purchases/gifts        (needs financial_operations AND the administrator)
// POST /api/v1/staff/purchases/gifts/{id}/cancel
//
// THE LIMIT IS NOT CHECKED BY THE SYSTEM. The share of a project's parts that
// may be given from its reserve (10 percent) is controlled by the staff member
// by hand; the screen says so above the form, and the server refuses only what
// it can know (an inactive or unverified recipient, an inactive product).
//
// THE LIST OF GIFTS LASTS. It is read from the purchases (GET /api/v1/staff/purchases),
// so it is still there after a reload: the gifts that wait for acceptance (the server
// filters them by status, the newest hundred) and the gifts among the newest hundred purchases (the server
// has no filter by kind, so the screen picks them out). A gift waiting for acceptance
// carries its cancel; every gift of every date is in Finance > Purchases.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Gift } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CLoader, CModal, CSelect } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import UserPicker from '@/components/staff/UserPicker.vue'
import { ApiResponseError } from '@/api/client'
import { cancelGift, fetchStaffPurchases, grantGift } from '@/api/admin'
import { listProducts } from '@/api/products'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { formatDate, formatNumber } from '@/utils/format'
import { formatPartPriceExact, formatPartsCount, formatUsdCents, lotsForParts } from '@/utils/parts'
import type { StaffPurchaseItem } from '@/api/generated'
import type { PublicProductResponse, UserListItem } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'
import { useSharesPerOption } from '@/composables/useSharesPerOption'

const { t, locale } = useI18n()
const { showToast } = useToast()

// -- The products a gift can be from -----------------------------------------

const products = ref<PublicProductResponse[]>([])
const productsLoading = ref(true)
const productsError = ref(false)

async function loadProducts(): Promise<void> {
  productsLoading.value = true
  productsError.value = false
  try {
    products.value = (await listProducts({ per_page: 100 })).items
  } catch {
    productsError.value = true
  } finally {
    productsLoading.value = false
  }
}

// The projects, from the products on offer: one entry per project.
const projectOptions = computed(() => {
  const byId = new Map<string, string>()
  for (const p of products.value) {
    if (!byId.has(p.company_id)) byId.set(p.company_id, p.company_name)
  }
  return [...byId.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label))
})

// -- The form ---------------------------------------------------------------

const recipientId = ref('')
const recipient = ref<UserListItem | null>(null)
const projectId = ref('')
const productId = ref('')
const partsText = ref('')

const projectProducts = computed(() =>
  products.value.filter((p) => p.company_id === projectId.value),
)

// The project's offers: a picker only when the project has more than one.
const offerOptions = computed(() =>
  projectProducts.value.map((p) => ({ value: p.id, label: p.name })),
)
const showOfferPicker = computed(() => projectProducts.value.length > 1)

const selectedProject = computed(
  () => projectOptions.value.find((o) => o.value === projectId.value) ?? null,
)
const selectedProduct = computed(
  () => projectProducts.value.find((p) => p.id === productId.value) ?? null,
)

// The project's parts per lot is read from the project (the product does not carry it).
const { ensure: ensureParts, partsPerLot } = useSharesPerOption()
const perLotLoading = ref(false)

// A project with one offer has it chosen by itself; a project with several waits for the pick.
watch(projectId, async (id) => {
  const list = products.value.filter((p) => p.company_id === id)
  productId.value = list.length === 1 ? list[0].id : ''
  if (!id) return
  perLotLoading.value = true
  try {
    await ensureParts([id])
  } finally {
    perLotLoading.value = false
  }
})

// The project's parts per lot; null while unknown.
const perLot = computed(() => partsPerLot(projectId.value))

// A whole number of parts, at least one.
const parts = computed<number | null>(() => {
  const text = partsText.value.trim()
  if (!/^\d+$/.test(text)) return null
  const n = Number(text)
  return Number.isSafeInteger(n) && n >= 1 ? n : null
})

// The parts made into the lots the server counts, or the two nearest valid counts of parts.
const conversion = computed(() => {
  if (parts.value === null || perLot.value === null) return null
  return lotsForParts(parts.value, perLot.value)
})

const MAX_LOTS = 1_000_000_000
const units = computed<number | null>(() => {
  const c = conversion.value
  return c && 'lots' in c && c.lots <= MAX_LOTS ? c.lots : null
})

const partsError = computed<string | undefined>(() => {
  if (partsText.value.trim() === '') return undefined
  if (parts.value === null) return t('staff.gifts.partsError')
  const c = conversion.value
  if (!c || !perLot.value) return undefined
  if ('lots' in c) return c.lots > MAX_LOTS ? t('staff.gifts.partsError') : undefined
  const per = formatNumber(perLot.value, locale.value)
  const above = formatNumber(c.above, locale.value)
  if (c.below === 0) return t('staff.gifts.partsTooFew', { per, above })
  return t('staff.gifts.partsNotWhole', {
    per,
    below: formatNumber(c.below, locale.value),
    above,
  })
})

const partPrice = computed(() =>
  selectedProduct.value && perLot.value
    ? formatPartPriceExact(selectedProduct.value.price_per_unit_cents, perLot.value, locale.value)
    : '',
)

const totalCents = computed(() =>
  selectedProduct.value && units.value !== null
    ? units.value * selectedProduct.value.price_per_unit_cents
    : null,
)

const canSubmit = computed(
  () => recipientId.value !== '' && selectedProduct.value !== null && units.value !== null,
)

function onRecipient(user: UserListItem | null): void {
  recipient.value = user
}

function recipientName(user: UserListItem | null): string {
  if (!user) return ''
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ')
  return name || (user.email ?? '')
}

// -- Granting ---------------------------------------------------------------

const showConfirm = ref(false)
const granting = ref(false)

// -- The list of gifts, read from the purchases ---------------------------------

const LIST_WINDOW = 100
const gifts = ref<StaffPurchaseItem[]>([])
const giftsLoading = ref(true)
const giftsError = ref(false)

async function loadGifts(): Promise<void> {
  giftsLoading.value = true
  giftsError.value = false
  try {
    const [waiting, recent] = await Promise.all([
      fetchStaffPurchases({ status: 'pending_acceptance', per_page: LIST_WINDOW }),
      fetchStaffPurchases({ per_page: LIST_WINDOW }),
    ])
    const byId = new Map<string, StaffPurchaseItem>()
    for (const row of [...waiting.items, ...recent.items]) {
      if (row.kind === 'gift') byId.set(row.id, row)
    }
    const list = [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at))
    // A gift counts lots; the list shows its parts, with the project's parts per lot.
    await ensureParts(list.map((g) => g.company_id))
    gifts.value = list
  } catch {
    giftsError.value = true
  } finally {
    giftsLoading.value = false
  }
}

function giftRecipient(row: StaffPurchaseItem): string {
  return row.buyer_name || row.buyer_email || row.buyer_id.slice(0, 8)
}

function serverReason(err: unknown, fallbackKey: string): string {
  if (err instanceof ApiResponseError && err.detail) return err.detail
  return t(fallbackKey)
}

async function handleGrant(): Promise<void> {
  if (!canSubmit.value || units.value === null || !selectedProduct.value) return
  granting.value = true
  try {
    // The server counts lots: the parts entered, made into whole lots.
    await grantGift({
      user_id: recipientId.value,
      product_id: selectedProduct.value.id,
      units: units.value,
    })
    showToast(t('staff.gifts.granted'), 'success')
    showConfirm.value = false
    partsText.value = ''
    await loadGifts()
  } catch (err) {
    showToast(serverReason(err, 'staff.gifts.grantError'), 'error')
    showConfirm.value = false
  } finally {
    granting.value = false
  }
}

// -- Cancelling a gift that has not been accepted ------------------------------

const cancellingId = ref<string | null>(null)

async function handleCancel(row: StaffPurchaseItem): Promise<void> {
  if (cancellingId.value) return
  cancellingId.value = row.id
  try {
    await cancelGift(row.id)
    showToast(t('staff.gifts.cancelled'), 'success')
    await loadGifts()
  } catch (err) {
    showToast(serverReason(err, 'staff.gifts.cancelError'), 'error')
  } finally {
    cancellingId.value = null
  }
}

function statusLabel(status: string): string {
  return tOrRaw(t, `staff.gifts.statuses.${status}`, status)
}

function statusVariant(status: string) {
  if (status === 'pending_acceptance') return 'warning'
  if (status === 'active') return 'success'
  if (status === 'cancelled') return 'neutral'
  return 'neutral'
}

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => loadProducts())

onMounted(() => {
  void loadProducts()
  void loadGifts()
})
</script>

<template>
  <div class="gifts">
    <CAlert tone="info">
      {{ t('staff.gifts.hint') }}
    </CAlert>
    <CAlert tone="warning">
      {{ t('staff.gifts.limit') }}
    </CAlert>

    <CLoader v-if="productsLoading" centered />
    <CEmptyState v-else-if="productsError" tone="danger" :title="t('common.error')">
      <template #actions>
        <CButton variant="secondary" size="sm" inline @click="loadProducts">
          {{ t('common.retry') }}
        </CButton>
      </template>
    </CEmptyState>

    <form v-else class="gifts__form" @submit.prevent="showConfirm = canSubmit">
      <UserPicker
        v-model="recipientId"
        :label="t('staff.gifts.recipient')"
        role-filter="investor"
        @select="onRecipient"
      />

      <CSelect
        v-model="projectId"
        class="gifts__project"
        :label="t('staff.gifts.project')"
        :placeholder="t('staff.gifts.projectPlaceholder')"
        :options="projectOptions"
      />

      <!-- The project's offer: asked only when the project has more than one -->
      <CSelect
        v-if="showOfferPicker"
        v-model="productId"
        class="gifts__offer"
        :label="t('staff.gifts.offer')"
        :placeholder="t('staff.gifts.offerPlaceholder')"
        :options="offerOptions"
      />

      <p v-if="projectId && !perLotLoading && perLot === null" class="ds-field__hint" role="alert">
        {{ t('staff.gifts.perLotError') }}
      </p>

      <CInput
        v-model="partsText"
        inputmode="numeric"
        autocomplete="off"
        :label="t('staff.gifts.parts')"
        :placeholder="t('staff.gifts.partsPlaceholder')"
        :error="partsError"
      />

      <!-- What the gift is, read-only: parts, lots, the price of one part, the total -->
      <dl v-if="selectedProduct && perLot !== null" class="ds-kv gifts__sum">
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.parts') }}</dt>
          <dd>
            {{ parts !== null ? formatNumber(parts, locale) : '—' }}
            <span v-if="units !== null" class="ds-note ds-note--xs gifts__lots">
              {{ t('staff.gifts.lots', { n: formatNumber(units, locale) }) }}
            </span>
          </dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.partPrice') }}</dt>
          <dd class="gifts__part-price">{{ partPrice }}</dd>
        </div>
        <div class="ds-kv__row ds-kv__row--total">
          <dt>{{ t('staff.gifts.total') }}</dt>
          <dd class="gifts__total">
            {{ totalCents !== null ? formatUsdCents(totalCents, locale) : '—' }}
          </dd>
        </div>
      </dl>

      <div>
        <CButton type="submit" variant="primary" size="sm" inline :disabled="!canSubmit">
          {{ t('staff.gifts.grant') }}
        </CButton>
      </div>
    </form>

    <!-- The gifts: read from the purchases, so the list is still here after a reload (K23 rows) -->
    <section class="gifts__list" :aria-label="t('staff.gifts.listTitle')">
      <h2 class="ds-section-title">
        {{ t('staff.gifts.listTitle') }}
      </h2>
      <p class="ds-note gifts__list-note">{{ t('staff.gifts.listPointer') }}</p>
      <CLoader v-if="giftsLoading" centered />
      <CEmptyState v-else-if="giftsError" tone="danger" :title="t('common.error')">
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="loadGifts">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>
      <p v-else-if="!gifts.length" class="ds-note">{{ t('staff.gifts.listEmpty') }}</p>
      <ul v-else class="ds-rows">
        <li v-for="row in gifts" :key="row.id" class="ds-row">
          <span class="ds-row__lead"><Gift size="sm" /></span>
          <span class="ds-row__body">
            <span class="ds-row__title">
              {{ giftRecipient(row) }} &mdash;
              {{
                t('staff.gifts.partsCount', {
                  n: formatPartsCount(row.units, partsPerLot(row.company_id), locale),
                })
              }}
            </span>
            <span class="ds-row__meta">
              {{ formatDate(row.created_at, locale) }} &bull; {{ row.company_name }} &mdash;
              {{ row.product_name }}
            </span>
          </span>
          <span class="ds-row__trail">
            <CBadge :variant="statusVariant(row.status)" :text="statusLabel(row.status)" />
            <button
              v-if="row.status === 'pending_acceptance'"
              type="button"
              class="ds-button ds-button--secondary"
              data-size="sm"
              :disabled="cancellingId === row.id"
              @click="handleCancel(row)"
            >
              <span>{{ t('staff.gifts.cancel') }}</span>
            </button>
          </span>
        </li>
      </ul>
    </section>

    <!-- Confirmation: a gift is given in the company's name -->
    <CModal :open="showConfirm" :title="t('staff.gifts.confirmTitle')" @close="showConfirm = false">
      <p class="ds-dialog__text">
        {{ t('staff.gifts.confirmBody') }}
      </p>
      <dl v-if="selectedProduct && units !== null && parts !== null" class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.recipient') }}</dt>
          <dd>{{ recipientName(recipient) }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.project') }}</dt>
          <dd>{{ selectedProject?.label }}</dd>
        </div>
        <div v-if="showOfferPicker" class="ds-kv__row">
          <dt>{{ t('staff.gifts.offer') }}</dt>
          <dd>{{ selectedProduct.name }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.parts') }}</dt>
          <dd>{{ formatNumber(parts, locale) }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.partPrice') }}</dt>
          <dd>{{ partPrice }}</dd>
        </div>
        <div v-if="totalCents !== null" class="ds-kv__row ds-kv__row--total">
          <dt>{{ t('staff.gifts.total') }}</dt>
          <dd>{{ formatUsdCents(totalCents, locale) }}</dd>
        </div>
      </dl>
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showConfirm = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" inline :loading="granting" @click="handleGrant">
          {{ t('staff.gifts.grant') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.gifts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  align-content: start;
}

.gifts__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
  max-inline-size: var(--maxw-prose);
}

.gifts__lots {
  display: block;
}

.gifts__list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
}

.gifts__list-note {
  max-inline-size: var(--maxw-prose);
}
</style>
