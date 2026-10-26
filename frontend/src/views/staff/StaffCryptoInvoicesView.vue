<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- StaffCryptoInvoicesView (Finance > Invoices)
// =============================================================================
//
// The administrator's list of the crypto top-up invoices clients created, and
// the one act on them: CONFIRM BY HAND. When the money did not arrive through
// the payments service (or arrived another way, by bank for example), the
// administrator opens the invoice and confirms it: the client's balance
// receives the invoice's stated amount, once. A required reason is kept with
// the payment. An invoice that is already credited (by the service or by hand)
// shows that and carries no button; the server refuses a second credit (409).
//
// Nothing else is offered here: no fee, no expiry rule, no amount other than
// the one the client asked for. The invoice status shown is the payments
// service's last word, kept as a cache; it decides nothing.
//
// A CLIENT'S REQUEST. A client who paid another way asks from the deposit
// screen for the invoice to be confirmed by hand; such an invoice carries a
// mark while it is not credited, and one chip keeps only those (the Home's
// counter opens the list with it, ?open_request=1). An invoice confirmed by
// hand shows the basis given at the confirmation.
//
// NOTES. The administrators write notes on an invoice at any time, before or
// after Confirm; they are listed oldest first with date and author, and are
// seen by staff only, never by the client.
//
// GET  /api/v1/staff/crypto-invoices (?status=, ?user_id=, ?open_request=, ?page=, ?per_page=)
// POST /api/v1/staff/crypto-invoices/{id}/confirm   { reason }
// POST /api/v1/staff/crypto-invoices/{id}/notes     { text }
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { CreditCard, Check } from '@/components/ui/icons'
import { CBadge, CButton, CEmptyState, CInput, CModal, CTextarea } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'
import CListSkeleton from '@/components/ui/CListSkeleton.vue'
import CPager from '@/components/ui/CPager.vue'
import { useUrlPage } from '@/components/ui/useUrlPage'
import UserPicker from '@/components/staff/UserPicker.vue'
import { useUrlUserFilter } from '@/composables/useUrlUserFilter'
import { useToast } from '@/composables/useToast'
import { ApiResponseError } from '@/api/client'
import { addCryptoInvoiceNote, confirmCryptoInvoice, fetchCryptoInvoices } from '@/api/admin'
import type { StaffCryptoInvoice } from '@/api/admin'
import { tOrRaw } from '@/utils/i18n'
import { formatDateTime, formatPrice } from '@/utils/format'

const { t, locale } = useI18n()
const { showToast } = useToast()

const items = ref<StaffCryptoInvoice[]>([])
const total = ref(0)
const page = useUrlPage()
const perPage = 20
const statusFilter = ref('')
// Only the invoices whose client asked for a manual confirmation and that are
// not credited yet; the Home's counter opens the list with ?open_request=1.
const route = useRoute()
const openRequestOnly = ref(route.query.open_request === '1')
// One person's invoices: the address names them (?user_id=), as in Payments.
const userFilter = useUrlUserFilter('user_id')
const loading = ref(true)
const error = ref(false)

const STATUSES = [
  'created',
  'awaiting_confirmations',
  'confirmed',
  'attempts_exhausted',
  'expired',
  'stalled',
] as const

// The confirm modal.
const showModal = ref(false)
const target = ref<StaffCryptoInvoice | null>(null)
const reason = ref('')
const confirming = ref(false)

// The notes modal.
const notesFor = ref<StaffCryptoInvoice | null>(null)
const noteText = ref('')
const addingNote = ref(false)
const noteValid = computed(() => noteText.value.trim().length >= 3)

const totalPages = computed(() => Math.ceil(total.value / perPage))
// The server wants 3 to 500 characters; the button waits for the 3.
const reasonValid = computed(() => reason.value.trim().length >= 3)

function statusLabel(status: string): string {
  return tOrRaw(t, `staff.invoices.statuses.${status}`, status)
}

function clientLabel(item: StaffCryptoInvoice): string {
  return item.user_name || item.user_email || `${item.user_id.slice(0, 8)}…`
}

function creditedLabel(item: StaffCryptoInvoice): string {
  if (item.credited_by === 'manual') return t('staff.invoices.creditedManual')
  if (item.credited_by === 'service') return t('staff.invoices.creditedService')
  return t('staff.invoices.notCredited')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = false
  try {
    const resp = await fetchCryptoInvoices({
      status: statusFilter.value || undefined,
      user_id: userFilter.value || undefined,
      open_request: openRequestOnly.value || undefined,
      page: page.value,
      per_page: perPage,
    })
    items.value = resp.items
    total.value = resp.total
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

function goToPage(n: number): void {
  page.value = n
  void load()
}

function setStatusFilter(s: string): void {
  statusFilter.value = s
  page.value = 1
}

function toggleOpenRequest(): void {
  openRequestOnly.value = !openRequestOnly.value
  page.value = 1
}

function noteMeta(note: StaffCryptoInvoice['notes'][number]): string {
  const when = formatDateTime(note.created_at, locale.value)
  return note.author_name ? `${note.author_name} \u2022 ${when}` : when
}

function openNotes(item: StaffCryptoInvoice): void {
  notesFor.value = item
  noteText.value = ''
}

async function handleAddNote(): Promise<void> {
  const item = notesFor.value
  if (!item || !noteValid.value || addingNote.value) return
  addingNote.value = true
  try {
    const note = await addCryptoInvoiceNote(item.id, { text: noteText.value.trim() })
    item.notes = [...(item.notes ?? []), note]
    noteText.value = ''
    showToast(t('staff.invoices.noteAdded'), 'success')
  } catch (err) {
    showToast(err instanceof ApiResponseError && err.detail ? err.detail : t('common.error'), 'error')
  } finally {
    addingNote.value = false
  }
}

function openConfirm(item: StaffCryptoInvoice): void {
  target.value = item
  reason.value = ''
  showModal.value = true
}

async function handleConfirm(): Promise<void> {
  if (!target.value || !reasonValid.value) return
  confirming.value = true
  try {
    await confirmCryptoInvoice(target.value.id, { reason: reason.value.trim() })
    showToast(t('staff.invoices.confirmed'), 'success')
    showModal.value = false
    await load()
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 409) {
      showToast(t('staff.invoices.alreadyCredited'), 'error')
      showModal.value = false
      await load()
    } else {
      showToast(err instanceof ApiResponseError && err.detail ? err.detail : t('common.error'), 'error')
    }
  } finally {
    confirming.value = false
  }
}

watch(statusFilter, () => void load())
watch(openRequestOnly, () => void load())

// A person chosen or cleared starts the list again from the first page.
watch(userFilter, () => {
  page.value = 1
  void load()
})

onMounted(() => void load())
</script>

<template>
  <div class="staff-inv">
    <CAlert tone="info">
      {{ t('staff.invoices.hint') }}
    </CAlert>

    <section class="staff-inv__section">
      <h2 class="ds-section-title">
        {{ t('staff.invoices.listTitle') }}
      </h2>

      <UserPicker
        v-model="userFilter"
        class="staff-inv__user"
        :label="t('staff.invoices.filterUser')"
      />

      <div class="ds-chip-row" role="group" :aria-label="t('staff.invoices.invoiceStatus')">
        <button
          class="ds-chip"
          :aria-pressed="!statusFilter"
          type="button"
          @click="setStatusFilter('')"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('common.all') }}</span>
        </button>
        <button
          v-for="s in STATUSES"
          :key="s"
          class="ds-chip"
          :aria-pressed="statusFilter === s"
          type="button"
          @click="setStatusFilter(s)"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ statusLabel(s) }}</span>
        </button>
      </div>

      <!-- The clients' requests for a manual confirmation, not credited yet -->
      <div class="ds-chip-row" role="group" :aria-label="t('staff.invoices.requestsFilter')">
        <button
          class="ds-chip inv-open-filter"
          :aria-pressed="openRequestOnly"
          type="button"
          @click="toggleOpenRequest"
        >
          <Check class="ds-chip__check" size="sm" />
          <span>{{ t('staff.invoices.manualRequested') }}</span>
        </button>
      </div>

      <CListSkeleton v-if="loading" />

      <CEmptyState v-else-if="error" tone="danger" :title="t('common.error')">
        <template #actions>
          <CButton variant="secondary" size="sm" inline @click="load">
            {{ t('common.retry') }}
          </CButton>
        </template>
      </CEmptyState>

      <CEmptyState v-else-if="!items.length" :title="t('staff.invoices.empty')">
        <template #icon>
          <CreditCard />
        </template>
      </CEmptyState>

      <template v-else>
        <ul class="ds-rows inv-list">
          <li v-for="item in items" :key="item.id" class="ds-row inv-item">
            <span class="ds-row__body">
              <span class="ds-row__title">{{ clientLabel(item) }}</span>
              <span class="ds-row__meta">
                {{ item.network }} &bull; {{ formatDateTime(item.created_at, locale) }}
              </span>
              <span class="ds-row__meta">
                {{ t('staff.invoices.invoiceStatus') }}: {{ statusLabel(item.status) }}
              </span>
              <span v-if="item.manual_requested_at" class="ds-row__meta">
                {{
                  t('staff.invoices.requestedAt', {
                    date: formatDateTime(item.manual_requested_at, locale),
                  })
                }}
              </span>
              <span v-if="item.confirm_reason" class="ds-row__meta inv-item__basis">
                {{ t('staff.invoices.confirmBasis') }}: {{ item.confirm_reason }}
              </span>
            </span>
            <span class="ds-row__trail">
              <span class="ds-row__value">{{ formatPrice(item.amount_cents) }}</span>
              <CBadge
                v-if="item.manual_request_open"
                class="inv-item__requested"
                variant="warning"
                :text="t('staff.invoices.manualRequested')"
              />
              <CBadge
                :variant="item.credited ? 'success' : 'neutral'"
                :text="creditedLabel(item)"
              />
              <CButton
                variant="outline"
                size="sm"
                inline
                class="inv-item__notes"
                @click="openNotes(item)"
              >
                {{ t('staff.invoices.notes') }} ({{ item.notes?.length ?? 0 }})
              </CButton>
              <button
                v-if="!item.credited"
                type="button"
                class="ds-button inv-item__confirm"
                data-size="sm"
                @click="openConfirm(item)"
              >
                <span>{{ t('staff.invoices.confirm') }}</span>
              </button>
            </span>
          </li>
        </ul>

        <CPager :page="page" :total-pages="totalPages" @update:page="goToPage" />
      </template>
    </section>

    <CModal
      :open="notesFor !== null"
      :title="t('staff.invoices.notesTitle')"
      @close="notesFor = null"
    >
      <template v-if="notesFor">
        <p class="ds-dialog__text inv-modal__client">
          {{ t('staff.invoices.client') }}: {{ clientLabel(notesFor) }}
        </p>
        <p class="ds-dialog__text">{{ t('staff.invoices.notesHint') }}</p>
        <ul v-if="notesFor.notes?.length" class="ds-rows inv-notes">
          <li v-for="note in notesFor.notes" :key="note.id" class="ds-row inv-note">
            <span class="ds-row__body">
              <span class="ds-row__title">{{ note.text }}</span>
              <span class="ds-row__meta">{{ noteMeta(note) }}</span>
            </span>
          </li>
        </ul>
        <p v-else class="ds-dialog__text">{{ t('staff.invoices.notesEmpty') }}</p>
      </template>
      <CTextarea
        v-model="noteText"
        :label="t('staff.invoices.noteLabel')"
        :placeholder="t('staff.invoices.noteHint')"
        :rows="3"
        :maxlength="500"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="notesFor = null">
          {{ t('common.close') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          class="inv-notes__add"
          :loading="addingNote"
          :disabled="!noteValid"
          @click="handleAddNote"
        >
          {{ t('staff.invoices.addNote') }}
        </CButton>
      </div>
    </CModal>

    <CModal
      :open="showModal"
      :title="t('staff.invoices.confirmTitle')"
      @close="showModal = false"
    >
      <p class="ds-dialog__text">
        {{ t('staff.invoices.confirmText') }}
      </p>
      <template v-if="target">
        <p class="ds-dialog__text inv-modal__client">
          {{ t('staff.invoices.client') }}: {{ clientLabel(target) }}
        </p>
        <p class="ds-amount" data-size="sm">
          {{ t('staff.invoices.amount') }}: {{ formatPrice(target.amount_cents) }}
        </p>
      </template>
      <CInput
        v-model="reason"
        :label="t('staff.invoices.reason')"
        :placeholder="t('staff.invoices.reasonHint')"
        :maxlength="500"
      />
      <div class="ds-dialog__actions">
        <CButton variant="outline" size="sm" inline @click="showModal = false">
          {{ t('common.cancel') }}
        </CButton>
        <CButton
          variant="primary"
          size="sm"
          inline
          :loading="confirming"
          :disabled="!reasonValid"
          @click="handleConfirm"
        >
          {{ t('common.confirm') }}
        </CButton>
      </div>
    </CModal>
  </div>
</template>

<style scoped>
.staff-inv {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-5);
  align-content: start;
}

.staff-inv__section {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
}
</style>
