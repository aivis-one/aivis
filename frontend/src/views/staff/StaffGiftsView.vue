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
// A gift just granted is listed here with its cancel while it waits; every gift
// of every date, cancel included, is in Finance > Purchases (GET /api/v1/staff/purchases).
// =============================================================================

import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Gift } from '@/components/ui/icons'
import { CBadge, CButton, CInput, CLoader, CModal, CSelect } from '@/components/ui'
import UserPicker from '@/components/staff/UserPicker.vue'
import { ApiResponseError } from '@/api/client'
import { cancelGift, grantGift } from '@/api/admin'
import { listProducts } from '@/api/products'
import { useToast } from '@/composables/useToast'
import { tOrRaw } from '@/utils/i18n'
import { formatNumber, formatPrice } from '@/utils/format'
import type { PurchaseResponse } from '@/api/generated'
import type { PublicProductResponse, UserListItem } from '@/api/types'

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

interface GrantedGift {
  gift: PurchaseResponse
  recipient: string
  product: string
}
const granted = ref<GrantedGift[]>([])

function serverReason(err: unknown, fallbackKey: string): string {
  if (err instanceof ApiResponseError && err.detail) return err.detail
  return t(fallbackKey)
}

async function handleGrant(): Promise<void> {
  if (!canSubmit.value || units.value === null || !selectedProduct.value) return
  granting.value = true
  try {
    const gift = await grantGift({
      user_id: recipientId.value,
      product_id: productId.value,
      units: units.value,
    })
    granted.value.unshift({
      gift,
      recipient: recipientName(recipient.value),
      product: `${selectedProduct.value.company_name} — ${selectedProduct.value.name}`,
    })
    showToast(t('staff.gifts.granted'), 'success')
    showConfirm.value = false
    unitsText.value = ''
  } catch (err) {
    showToast(serverReason(err, 'staff.gifts.grantError'), 'error')
    showConfirm.value = false
  } finally {
    granting.value = false
  }
}

// -- Cancelling a gift that has not been accepted ------------------------------

const cancellingId = ref<string | null>(null)

async function handleCancel(entry: GrantedGift): Promise<void> {
  if (cancellingId.value) return
  cancellingId.value = entry.gift.id
  try {
    entry.gift = await cancelGift(entry.gift.id)
    showToast(t('staff.gifts.cancelled'), 'success')
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

onMounted(loadProducts)
</script>

<template>
  <div class="gifts">
    <p class="gifts__hint">
      <Gift :size="16" />
      {{ t('staff.gifts.hint') }}
    </p>
    <p class="gifts__limit">
      {{ t('staff.gifts.limit') }}
    </p>

    <div v-if="productsLoading" class="gifts__center">
      <CLoader :size="28" />
    </div>
    <div v-else-if="productsError" class="gifts__center">
      <p class="gifts__error">{{ t('common.error') }}</p>
      <CButton variant="secondary" size="sm" @click="loadProducts">
        {{ t('common.retry') }}
      </CButton>
    </div>

    <form v-else class="gifts__form" @submit.prevent="showConfirm = canSubmit">
      <div class="gifts__field">
        <span class="gifts__label">{{ t('staff.gifts.recipient') }}</span>
        <UserPicker v-model="recipientId" role-filter="investor" @select="onRecipient" />
      </div>

      <CSelect
        v-model="productId"
        :label="t('staff.gifts.product')"
        :placeholder="t('staff.gifts.productPlaceholder')"
        :options="productOptions"
      />
      <p v-if="selectedProduct" class="gifts__product-note">
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

      <CButton type="submit" variant="primary" size="sm" :disabled="!canSubmit">
        {{ t('staff.gifts.grant') }}
      </CButton>
    </form>

    <!-- The gifts granted in this session -->
    <section v-if="granted.length" class="gifts__list" :aria-label="t('staff.gifts.sessionTitle')">
      <h3 class="gifts__list-title">
        {{ t('staff.gifts.sessionTitle') }}
      </h3>
      <p class="gifts__list-note">{{ t('staff.gifts.listPointer') }}</p>
      <div v-for="entry in granted" :key="entry.gift.id" class="gifts__row">
        <div class="gifts__row-info">
          <div class="gifts__row-main">
            {{ entry.recipient }} &mdash;
            {{ t('staff.gifts.partsCount', { n: formatNumber(entry.gift.units, locale) }) }}
          </div>
          <div class="gifts__row-sub">{{ entry.product }}</div>
        </div>
        <div class="gifts__row-right">
          <CBadge
            :variant="statusVariant(entry.gift.status)"
            :text="statusLabel(entry.gift.status)"
          />
          <button
            v-if="entry.gift.status === 'pending_acceptance'"
            type="button"
            class="gifts__cancel"
            :disabled="cancellingId === entry.gift.id"
            @click="handleCancel(entry)"
          >
            {{ t('staff.gifts.cancel') }}
          </button>
        </div>
      </div>
    </section>

    <!-- Confirmation: a gift is given in the company's name -->
    <CModal :open="showConfirm" @close="showConfirm = false">
      <h3 class="gifts__modal-title">
        {{ t('staff.gifts.confirmTitle') }}
      </h3>
      <p class="gifts__modal-text">
        {{ t('staff.gifts.confirmBody') }}
      </p>
      <dl v-if="selectedProduct && units !== null" class="gifts__summary">
        <dt>{{ t('staff.gifts.recipient') }}</dt>
        <dd>{{ recipientName(recipient) }}</dd>
        <dt>{{ t('staff.gifts.product') }}</dt>
        <dd>{{ selectedProduct.company_name }} — {{ selectedProduct.name }}</dd>
        <dt>{{ t('staff.gifts.units') }}</dt>
        <dd>{{ formatNumber(units, locale) }}</dd>
      </dl>
      <div class="gifts__modal-actions">
        <CButton variant="outline" size="sm" @click="showConfirm = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton variant="primary" size="sm" :loading="granting" @click="handleGrant">
          {{ t('staff.gifts.grant') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.gifts {
  padding: var(--space-4);
}

.gifts__hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  margin: 0 0 var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  max-width: var(--maxw-prose);
}

.gifts__limit {
  margin: 0 0 var(--space-4);
  padding: var(--space-3);
  background: var(--warning-subtle);
  border-radius: var(--radius-md);
  font-size: var(--fs-xs);
  color: var(--text-primary);
  max-width: var(--maxw-prose);
}

.gifts__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: var(--center-sm);
  gap: var(--space-3);
}

.gifts__error {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--danger);
}

.gifts__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: var(--maxw-prose);
}

.gifts__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.gifts__label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.gifts__product-note {
  margin: calc(-1 * var(--space-2)) 0 0;
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.gifts__list {
  margin-top: var(--space-5);
}

.gifts__list-title {
  font-size: var(--fs-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-1);
}

.gifts__list-note {
  margin: 0 0 var(--space-3);
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
  max-width: var(--maxw-prose);
}

.gifts__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}

.gifts__row-info {
  flex: 1;
  min-width: 0;
}

.gifts__row-main {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.gifts__row-sub {
  font-size: var(--fs-xs);
  color: var(--text-tertiary);
}

.gifts__row-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-1);
  flex-shrink: 0;
}

.gifts__cancel {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--danger);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) 0;
  text-decoration: underline;
}
.gifts__cancel:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.gifts__modal-title {
  font-size: var(--fs-h4);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}

.gifts__modal-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-3);
  max-width: var(--maxw-prose);
}

.gifts__summary {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-1) var(--space-3);
  margin: 0 0 var(--space-4);
  font-size: var(--fs-sm);
}
.gifts__summary dt {
  color: var(--text-secondary);
}
.gifts__summary dd {
  margin: 0;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.gifts__modal-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
</style>
