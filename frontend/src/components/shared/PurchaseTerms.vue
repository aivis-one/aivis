<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- PurchaseTerms
// =============================================================================
//
// What the buyer meets before paying, on the purchase screen and on the
// instalment confirmation:
//
//   1. the pre-purchase disclosure sheet, SHORT on the screen -- one line for
//      each of its sections, taken from the sheet itself -- with the full text
//      one tap away (the cabinet's own document window; the static file stays
//      the link that can be saved);
//   2. ONE tick, "I accept the agreement", with the buyer agreement behind a
//      link to its full text.
//
// It is the terms group of the Purchase block (K55): the parent draws it inside
// the block, above the block's buttons.
//
// The tick is the parent's (v-model). The parent records the acceptance of the
// buyer agreement (documents/by-type + sign) when the button is pressed, and
// keeps the button shut while the tick is empty.
//
// The short form is read from the same static file the full window shows
// (public/legal/<lang>/pre_purchase_disclosure.html): the first sentence of
// each numbered section's opening paragraph. Nothing is rendered as HTML.
// =============================================================================

import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LegalDocModal from '@/components/legal/LegalDocModal.vue'
import { CCheckbox } from '@/components/ui'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const { t, locale } = useI18n()

const docLang = computed(() => (locale.value === 'ru' ? 'ru' : 'en'))

function docUrl(type: string): string {
  return `${import.meta.env.BASE_URL}legal/${docLang.value}/${type}.html`
}

// ---------------------------------------------------------------------------
// The short form of the disclosure sheet
// ---------------------------------------------------------------------------

interface DigestRow {
  heading: string
  line: string
}

const SENTENCE_LIMIT = 170

const digest = ref<DigestRow[]>([])
const digestFailed = ref(false)

// A later language switch must not be overwritten by an earlier, slower fetch.
let epoch = 0

function firstSentence(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  const cut = flat.search(/[.!?](\s|$)/)
  const sentence = cut >= 0 ? flat.slice(0, cut + 1) : flat
  return sentence.length > SENTENCE_LIMIT ? `${sentence.slice(0, SENTENCE_LIMIT - 1)}…` : sentence
}

async function loadDigest(): Promise<void> {
  const mine = ++epoch
  digestFailed.value = false
  try {
    const resp = await fetch(docUrl('pre_purchase_disclosure'))
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const dom = new DOMParser().parseFromString(await resp.text(), 'text/html')
    const rows: DigestRow[] = []
    dom.querySelectorAll('h2').forEach((h) => {
      let node = h.nextElementSibling
      while (node && node.tagName !== 'P') node = node.nextElementSibling
      if (!node) return
      // The paragraph opens with its own number ("1.1.").
      const body = (node.textContent ?? '').replace(/^\s*\d+(\.\d+)*\.\s*/, '')
      rows.push({
        heading: (h.textContent ?? '').replace(/^\s*\d+\.\s*/, '').trim(),
        line: firstSentence(body),
      })
    })
    if (mine === epoch) digest.value = rows
  } catch {
    if (mine === epoch) {
      digest.value = []
      digestFailed.value = true
    }
  }
}

onMounted(loadDigest)
watch(docLang, loadDigest)

// ---------------------------------------------------------------------------
// The two document windows
// ---------------------------------------------------------------------------

const openDoc = ref<'pre_purchase_disclosure' | 'buyer_agreement' | null>(null)

const openTitle = computed(() =>
  openDoc.value === 'buyer_agreement'
    ? t('inv.terms.agreementTitle')
    : t('inv.terms.disclosureTitle'),
)
</script>

<template>
  <div class="ds-purchase__terms">
    <p class="ds-purchase__title">
      {{ t('inv.terms.title') }}
    </p>

    <ul v-if="digest.length > 0" class="pt__list">
      <li v-for="row in digest" :key="row.heading" class="ds-note">
        <strong>{{ row.heading }}.</strong>
        {{ row.line }}
      </li>
    </ul>
    <p v-else-if="digestFailed" class="ds-note">
      {{ t('inv.terms.digestFailed') }}
    </p>

    <div>
      <a
        class="ds-button ds-button--ghost"
        data-size="sm"
        :href="docUrl('pre_purchase_disclosure')"
        target="_blank"
        rel="noopener"
        @click.prevent="openDoc = 'pre_purchase_disclosure'"
        >{{ t('inv.terms.readFull') }}</a
      >
    </div>

    <CCheckbox :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
      {{ t('inv.terms.acceptPrefix') }}
      <a
        :href="docUrl('buyer_agreement')"
        target="_blank"
        rel="noopener"
        @click.prevent="openDoc = 'buyer_agreement'"
        >{{ t('inv.terms.agreementLink') }}</a
      >
    </CCheckbox>

    <LegalDocModal
      :open="openDoc !== null"
      :title="openTitle"
      :lang="docLang"
      :type="openDoc ?? 'pre_purchase_disclosure'"
      @close="openDoc = null"
    />
  </div>
</template>

<style scoped>
/* The short form of the sheet: one line per section, the section's name in the
   text colour. */
.pt__list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.pt__list strong {
  color: var(--text-primary);
}
</style>
