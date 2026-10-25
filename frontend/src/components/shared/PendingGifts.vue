<script setup lang="ts">
// The gifts staff granted to the buyer that wait for acceptance. Each one
// shows its parts and date, opens its gift certificate, and is accepted by
// one button: the parts are credited at once and the gift becomes a holding.
// Nothing renders while there is no pending gift or the list failed to load
// (the portfolio itself stays the screen's subject). Emits `accepted` so the
// parent refreshes its positions.

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Gift } from '@/components/ui/icons'
import { CButton } from '@/components/ui'
import AgreementSheet from '@/components/shared/AgreementSheet.vue'
import { ApiResponseError } from '@/api/client'
import { acceptGift, listPendingGifts } from '@/api/purchases'
import { useToast } from '@/composables/useToast'
import { formatDate, formatNumber } from '@/utils/format'
import type { PurchaseResponse } from '@/api/types'
import { useReloadOnLocale } from '@/composables/useReloadOnLocale'

const emit = defineEmits<{ accepted: [] }>()

const { t, locale } = useI18n()
const { showToast } = useToast()

const gifts = ref<PurchaseResponse[]>([])
const accepting = ref<string | null>(null)
const certificateId = ref<string | null>(null)

async function load(): Promise<void> {
  try {
    gifts.value = (await listPendingGifts()).items
  } catch {
    gifts.value = []
  }
}

async function accept(gift: PurchaseResponse): Promise<void> {
  if (accepting.value) return
  accepting.value = gift.id
  try {
    await acceptGift(gift.id)
    gifts.value = gifts.value.filter((g) => g.id !== gift.id)
    showToast(t('inv.portfolio.gifts.accepted'), 'success')
    emit('accepted')
  } catch (err) {
    // A verification that is no longer approved has its own message; the
    // KYC gate's 402 already opened the verification prompt.
    const kyc = err instanceof ApiResponseError && err.code === 'kyc_required'
    if (!(err instanceof ApiResponseError && err.status === 402)) {
      showToast(
        kyc ? t('inv.portfolio.gifts.kycRequired') : t('inv.portfolio.gifts.acceptError'),
        'error',
      )
    }
  } finally {
    accepting.value = null
  }
}

// H38: project data is in the reader's language -- re-read it on a switch.
useReloadOnLocale(() => load())

onMounted(() => {
  void load()
})
</script>

<template>
  <section v-if="gifts.length > 0" class="gifts">
    <h2 class="ds-section-title">
      {{ t('inv.portfolio.gifts.title') }}
    </h2>
    <ul class="ds-rows">
      <li v-for="gift in gifts" :key="gift.id" class="ds-row">
        <span class="ds-row__lead"><Gift size="sm" /></span>
        <span class="ds-row__body">
          <span class="ds-row__title">
            {{ t('inv.portfolio.gifts.units', { units: formatNumber(gift.units, locale) }) }}
          </span>
          <span class="ds-row__meta">{{ formatDate(gift.created_at, locale) }}</span>
        </span>
        <span class="ds-row__trail">
          <CButton variant="outline" size="sm" inline @click="certificateId = gift.id">
            {{ t('inv.portfolio.gifts.certificate') }}
          </CButton>
          <CButton
            variant="primary"
            size="sm"
            inline
            :loading="accepting === gift.id"
            :disabled="accepting !== null"
            @click="accept(gift)"
          >
            {{ t('inv.portfolio.gifts.accept') }}
          </CButton>
        </span>
      </li>
    </ul>

    <AgreementSheet
      :open="certificateId !== null"
      mode="agreement"
      :id="certificateId"
      legal-basis="gift"
      @close="certificateId = null"
    />
  </section>
</template>

<style scoped>
.gifts {
  display: grid;
  gap: var(--space-2);
}
</style>
