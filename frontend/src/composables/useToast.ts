import { ref, type Ref } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  type: ToastType
  message: string
  duration: number
}

interface ToastState {
  toasts: Ref<Toast[]>
  addToast: (type: ToastType, message: string, duration?: number) => number
  removeToast: (id: number) => void
  clearAll: () => void
}

const toasts = ref<Toast[]>([])
let nextId = 1

export function useToast(): ToastState {
  const addToast = (type: ToastType, message: string, duration = 4000): number => {
    const id = nextId++
    toasts.value.push({ id, type, message, duration })

    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }

    return id
  }

  const removeToast = (id: number) => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  const clearAll = () => {
    toasts.value = []
  }

  return { toasts, addToast, removeToast, clearAll }
}
