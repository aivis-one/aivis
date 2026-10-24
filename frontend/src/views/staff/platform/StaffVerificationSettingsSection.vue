<script setup lang="ts">
// =============================================================================
// AIVIS.ONE Frontend -- Verification mode setting (H12)
// =============================================================================
//
// THE FIRST STAFF-EDITABLE PLATFORM SETTING in this product, and the
// shape the next ones will copy: read the current value on mount,
// write it with one PUT, say what changed. Everything else
// configurable lives in the backend's environment and needs a restart.
//
// THE SWITCH DOES NOT CHANGE WHO DECIDES YET, AND THE SCREEN SAYS SO.
// The provider integration is a later pass; until it lands, an
// application submitted under either value is decided by a staff
// member. The setting is stored and stamped onto every application at
// submit time, so the pass that adds the provider has nothing to
// backfill. A control that silently did nothing would be worse than no
// control -- hence the notice, which is not a placeholder and is meant
// to be deleted by the provider pass, not by a tidy-up.
//
// PERMISSION: kyc_approve, the same one that gates reading identity
// documents and deciding applications. Not a design choice so much as
// the cheapest correct one -- a permission key of its own would flip
// is_admin() to False for every staff profile created before it
// existed (backend migration 0043 exists because of exactly that).
// =============================================================================

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchVerificationMode, saveVerificationMode } from '@/api/kyc'
import { useToast } from '@/composables/useToast'
import { CButton, CLoader } from '@/components/ui'
import CAlert from '@/components/ui/CAlert.vue'

const { t } = useI18n()
const { showToast } = useToast()

type Mode = 'manual' | 'automatic'

const loading = ref(true)
const saving = ref(false)
// What the server holds, kept apart from what the radio shows: the
// Save button is only meaningful while the two disagree.
const storedMode = ref<Mode>('manual')
const selectedMode = ref<Mode>('manual')

async function load(): Promise<void> {
  loading.value = true
  try {
    const { mode } = await fetchVerificationMode()
    storedMode.value = mode
    selectedMode.value = mode
  } catch {
    showToast(t('staff.platform.verification.error'), 'error')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const { mode } = await saveVerificationMode(selectedMode.value)
    storedMode.value = mode
    selectedMode.value = mode
    showToast(t('staff.platform.verification.saved'), 'success')
  } catch {
    // Put the control back on what the server actually holds. Leaving
    // it on the failed choice would show a mode that is not in effect.
    selectedMode.value = storedMode.value
    showToast(t('staff.platform.verification.error'), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="verification">
    <p class="ds-note verification__text">
      {{ t('staff.platform.verification.description') }}
    </p>

    <CLoader v-if="loading" centered />

    <template v-else>
      <!-- The mode (K05: a fieldset with a legend, one radio per mode) -->
      <fieldset class="ds-fieldset">
        <legend class="ds-fieldset__legend">{{ t('staff.platform.verification.title') }}</legend>
        <label class="ds-radio">
          <input v-model="selectedMode" class="ds-radio__input" type="radio" value="manual" />
          <span class="ds-radio__dot" aria-hidden="true"></span>
          <span>{{ t('staff.platform.verification.manual') }}</span>
        </label>
        <label class="ds-radio">
          <input v-model="selectedMode" class="ds-radio__input" type="radio" value="automatic" />
          <span class="ds-radio__dot" aria-hidden="true"></span>
          <span>{{ t('staff.platform.verification.automatic') }}</span>
        </label>
      </fieldset>

      <CAlert tone="warning">
        {{ t('staff.platform.verification.notice') }}
      </CAlert>

      <div>
        <CButton
          variant="primary"
          size="sm"
          inline
          :disabled="saving || selectedMode === storedMode"
          @click="save"
        >
          {{ t('staff.platform.verification.save') }}
        </CButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.verification {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}

.verification__text {
  max-inline-size: var(--maxw-prose);
}
</style>
