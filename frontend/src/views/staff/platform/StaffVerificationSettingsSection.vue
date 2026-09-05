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

import {
  fetchVerificationMode,
  saveVerificationMode,
} from '@/api/kyc'
import { useToast } from '@/composables/useToast'
import { CButton } from '@/components/ui'

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
    <h3 class="verification__title">
      {{ t('staff.platform.verification.title') }}
    </h3>
    <p class="verification__text">
      {{ t('staff.platform.verification.description') }}
    </p>

    <div v-if="loading" class="verification__text">{{ t('common.loading') }}</div>

    <template v-else>
      <label class="verification__option">
        <input v-model="selectedMode" type="radio" value="manual" />
        <span>{{ t('staff.platform.verification.manual') }}</span>
      </label>
      <label class="verification__option">
        <input v-model="selectedMode" type="radio" value="automatic" />
        <span>{{ t('staff.platform.verification.automatic') }}</span>
      </label>

      <p class="verification__notice">
        {{ t('staff.platform.verification.notice') }}
      </p>

      <div class="verification__actions">
        <CButton
          variant="primary"
          size="sm"
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
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
}

.verification__title {
  font-size: var(--fs-lg);
  font-weight: 600;
}

.verification__text,
.verification__notice {
  color: var(--text-secondary);
  font-size: var(--fs-sm);
}

.verification__option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.verification__actions {
  display: flex;
  gap: var(--space-2);
}
</style>
