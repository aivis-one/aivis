<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffGiftsView (Finance > Gifts)
// =============================================================================
//
// The staff action that gives a gift of the company: parts of a project handed
// to a person from the list of the deed of gift, after that person has passed
// the paid identity check. The staff member picks the person, picks the
// project's product and enters the number of parts; the cabinet stores the
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

import { computed, onMounted, ref } from 'vue'
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
import { formatDate, formatNumber, formatPrice } from '@/utils/format'
import type { StaffPurchaseItem } from '@/api/generated'
import type { PublicProductResponse, UserListItem } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

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

const productOptions = computed(() =>
  products.value.map((p) => ({ value: p.id, label: `${p.company_name} — ${p.name}` })),
)

// -- The form ---------------------------------------------------------------

const recipientId = ref('')
const recipient = ref<UserListItem | null>(null)
const productId = ref('')
const unitsText = ref('')

const selectedProduct = computed(() => products.value.find((p) => p.id === productId.value) ?? null)

// A whole number of parts, at least one.
const units = computed<number | null>(() => {
  const text = unitsText.value.trim()
  if (!/^\d+$/.test(text)) return null
  const n = Number(text)
  return Number.isSafeInteger(n) && n >= 1 && n <= 1_000_000_000 ? n : null
})

const canSubmit = computed(
  () => recipientId.value !== '' && productId.value !== '' && units.value !== null,
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
    gifts.value = [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at))
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
    await grantGift({
      user_id: recipientId.value,
      product_id: productId.value,
      units: units.value,
    })
    showToast(t('staff.gifts.granted'), 'success')
    showConfirm.value = false
    unitsText.value = ''
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
        v-model="productId"
        :label="t('staff.gifts.product')"
        :placeholder="t('staff.gifts.productPlaceholder')"
        :options="productOptions"
      />
      <p v-if="selectedProduct" class="ds-field__hint">
        {{
          t('staff.gifts.priceNote', {
            price: formatPrice(selectedProduct.price_per_unit_cents, 'USD'),
          })
        }}
      </p>

      <CInput
        v-model="unitsText"
        inputmode="numeric"
        autocomplete="off"
        :label="t('staff.gifts.units')"
        :placeholder="t('staff.gifts.unitsPlaceholder')"
        :error="unitsText.trim() !== '' && units === null ? t('staff.gifts.unitsError') : undefined"
      />

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
              {{ t('staff.gifts.partsCount', { n: formatNumber(row.units, locale) }) }}
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
      <dl v-if="selectedProduct && units !== null" class="ds-kv">
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.recipient') }}</dt>
          <dd>{{ recipientName(recipient) }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.product') }}</dt>
          <dd>{{ selectedProduct.company_name }} — {{ selectedProduct.name }}</dd>
        </div>
        <div class="ds-kv__row">
          <dt>{{ t('staff.gifts.units') }}</dt>
          <dd>{{ formatNumber(units, locale) }}</dd>
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

.gifts__list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
}

.gifts__list-note {
  max-inline-size: var(--maxw-prose);
}
</style>
