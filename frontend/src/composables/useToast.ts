// =============================================================================
// CBSHOME Frontend -- useToast Composable
// =============================================================================
//
// Singleton toast state. showToast() triggers CToast rendering.
// Auto-hides after 3 seconds.
// =============================================================================

import { ref } from 'vue'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

interface ToastState {
  message: string
  variant: ToastVariant
  visible: boolean
}

const state = ref<ToastState>({
  message: '',
  variant: 'info',
  visible: false,
})

let hideTimer: ReturnType<typeof setTimeout> | null = null

export function useToast() {
  function showToast(message: string, variant: ToastVariant = 'info'): void {
    if (hideTimer) clearTimeout(hideTimer)
    state.value = { message, variant, visible: true }
    hideTimer = setTimeout(() => {
      state.value.visible = false
    }, 3000)
  }

  function hideToast(): void {
    if (hideTimer) clearTimeout(hideTimer)
    state.value.visible = false
  }

  return { toastState: state, showToast, hideToast }
}
