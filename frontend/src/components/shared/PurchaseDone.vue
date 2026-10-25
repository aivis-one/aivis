<script setup lang="ts">
// The done screen of the buying path (step 3): the same Purchase block (K55) under
// a success Alert (K09) whose title is the congratulation. The summary lines come
// in the default slot (the screen that made the purchase owns the figures); the
// documents the purchase issued are Row list rows (K23) that open the cabinet's
// document sheet, and the one action is "To my portfolio".
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CAlert, CButton } from '@/components/ui'
import AgreementSheet from '@/components/shared/AgreementSheet.vue'
import PurchaseStepLine from '@/components/shared/PurchaseStepLine.vue'

export interface DoneDocument {
  /** A purchase's agreement (its id and legal basis), or the project's ownership certificate. */
  kind: 'agreement' | 'ownership'
  /** The purchase id for an agreement; unused for the ownership certificate. */
  id?: string
  legalBasis?: string
}

const props = defineProps<{
  projectName: string
  companyId: string
  documents: DoneDocument[]
}>()

defineEmits<{ portfolio: []; storefront: [] }>()

const { t } = useI18n()

const openAgreement = ref<DoneDocument | null>(null)
const ownershipOpen = ref(false)

function titleOf(doc: DoneDocument): string {
  if (doc.kind === 'ownership') return t('inv.agreement.title.ownership')
  switch (doc.legalBasis) {
    case 'sale':
      return t('inv.agreement.title.purchaseAgreement')
    case 'gift':
      return t('inv.agreement.title.giftCertificate')
    case 'installment_tranche':
      return t('inv.agreement.title.installmentSubcontract')
    default:
      return t('inv.agreement.title.document')
  }
}

function open(doc: DoneDocument): void {
  if (doc.kind === 'ownership') ownershipOpen.value = true
  else openAgreement.value = doc
}

const rows = computed(() => props.documents.map((d, i) => ({ key: `${d.kind}-${d.id ?? i}`, d })))
</script>

<template>
  <article class="ds-card">
    <div class="ds-card__body ds-purchase">
      <PurchaseStepLine :step="3" />
      <CAlert tone="success" :title="t('buy.congratsTitle', { project: projectName })">
        {{ t('buy.congratsText') }}
      </CAlert>
      <slot />
      <ul v-if="rows.length > 0" class="ds-rows" :aria-label="t('buy.documents')">
        <li v-for="row in rows" :key="row.key" class="ds-row">
          <span class="ds-row__body">
            <button type="button" class="ds-row__link" @click="open(row.d)">
              <span class="ds-row__title">{{ titleOf(row.d) }}</span>
            </button>
          </span>
        </li>
      </ul>
      <CButton variant="primary" @click="$emit('portfolio')">
        {{ t('buy.toPortfolio') }}
      </CButton>
      <CButton variant="outline" @click="$emit('storefront')">
        {{ t('buy.toStorefront') }}
      </CButton>
    </div>
  </article>

  <AgreementSheet
    mode="agreement"
    :open="openAgreement !== null"
    :id="openAgreement?.id ?? null"
    :legal-basis="openAgreement?.legalBasis"
    :company-name="projectName"
    @close="openAgreement = null"
  />
  <AgreementSheet
    mode="ownership"
    :open="ownershipOpen"
    :id="companyId"
    :company-name="projectName"
    @close="ownershipOpen = false"
  />
</template>
