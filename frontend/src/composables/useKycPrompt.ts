// =============================================================================
// AIVIS.ONE Frontend -- The "pass identity verification" prompt
// =============================================================================
//
// One rule for the four actions the KYC gate closes (buying, an instalment
// plan, a withdrawal, the integrator application): pressing one without a
// passed verification shows a message and a button to the verification screen.
// The gate's 402 reaches main.ts, which opens this prompt instead of moving
// the person away from the page they pressed the button on.
//
// Module-level state, because the 402 handler lives outside any component.
// =============================================================================

import { ref } from 'vue'

export type KycPromptAction = 'purchase' | 'installment' | 'generic'

const open = ref(false)
const action = ref<KycPromptAction>('generic')

/** The prompt's action, read from the name of the route the person pressed on. */
export function kycActionForRoute(routeName: unknown): KycPromptAction {
  if (typeof routeName !== 'string') return 'generic'
  if (routeName.endsWith('-purchase') || routeName.endsWith('-product-detail')) return 'purchase'
  if (routeName.endsWith('-installment')) return 'installment'
  return 'generic'
}

export function showKycPrompt(next: KycPromptAction): void {
  action.value = next
  open.value = true
}

export function closeKycPrompt(): void {
  open.value = false
}

export function useKycPrompt() {
  return { open, action, close: closeKycPrompt }
}
