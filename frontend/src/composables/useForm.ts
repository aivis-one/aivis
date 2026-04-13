import { reactive, ref, computed, type Ref } from 'vue'
import { ValidationError } from '@/api/types'

interface UseFormOptions<T extends Record<string, unknown>> {
  initialValues: T
  validate?: (values: T) => Partial<Record<keyof T, string>>
  onSubmit: (values: T) => Promise<void>
}

export function useForm<T extends Record<string, unknown>>(options: UseFormOptions<T>) {
  const initialSnapshot = JSON.stringify(options.initialValues)
  const values = reactive({ ...options.initialValues }) as T
  const errors = reactive<Partial<Record<keyof T, string>>>({})
  const submitting = ref(false)
  const submitError = ref<string | null>(null)
  const touched: Ref<Record<string, boolean>> = ref({})

  const isValid = computed(() => {
    return Object.keys(errors).every((key) => !errors[key as keyof T])
  })

  const isDirty = computed(() => {
    return JSON.stringify(values) !== initialSnapshot
  })

  function clearErrors() {
    for (const key of Object.keys(errors)) {
      delete errors[key as keyof T]
    }
    submitError.value = null
  }

  function validateForm(): boolean {
    clearErrors()
    if (options.validate) {
      const result = options.validate(values)
      Object.assign(errors, result)
      return Object.keys(result).length === 0
    }
    return true
  }

  async function handleSubmit() {
    if (!validateForm()) return
    submitting.value = true
    submitError.value = null
    try {
      await options.onSubmit(values)
    } catch (e: unknown) {
      if (e instanceof ValidationError && e.details) {
        for (const [field, messages] of Object.entries(e.details)) {
          if (field in values) {
            ;(errors as Record<string, string>)[field] = messages[0]
          }
        }
      } else if (e instanceof Error) {
        submitError.value = e.message
      }
    } finally {
      submitting.value = false
    }
  }

  function markTouched(field: keyof T) {
    touched.value[field as string] = true
  }

  function setFieldValue(field: keyof T, value: unknown) {
    ;(values as Record<string, unknown>)[field as string] = value
    markTouched(field)
  }

  function reset() {
    Object.assign(values, options.initialValues)
    clearErrors()
    touched.value = {}
  }

  return {
    values,
    errors,
    submitting,
    submitError,
    isValid,
    isDirty,
    touched,
    handleSubmit,
    reset,
    clearErrors,
    markTouched,
    setFieldValue,
  }
}
