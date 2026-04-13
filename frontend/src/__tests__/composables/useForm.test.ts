import { describe, it, expect, vi } from 'vitest'
import { useForm } from '@/composables/useForm'
import { ValidationError } from '@/api/types'

function createTestForm(overrides = {}) {
  return useForm({
    initialValues: { name: '', email: '' },
    validate(v) {
      const errs: Record<string, string> = {}
      if (!v.name) errs.name = 'Name is required'
      if (!v.email) errs.email = 'Email is required'
      return errs
    },
    onSubmit: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  })
}

describe('useForm', () => {
  it('initializes with provided values', () => {
    const form = createTestForm()
    expect(form.values.name).toBe('')
    expect(form.values.email).toBe('')
    expect(form.submitting.value).toBe(false)
    expect(form.submitError.value).toBeNull()
  })

  it('validates and sets errors', () => {
    const form = createTestForm()
    form.handleSubmit()
    expect(form.errors.name).toBe('Name is required')
    expect(form.errors.email).toBe('Email is required')
  })

  it('clears errors with clearErrors', () => {
    const form = createTestForm()
    form.handleSubmit()
    expect(form.errors.name).toBeTruthy()
    form.clearErrors()
    expect(form.errors.name).toBeUndefined()
    expect(form.submitError.value).toBeNull()
  })

  it('handles async submit success', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const form = createTestForm({ onSubmit })
    form.values.name = 'John'
    form.values.email = 'john@test.com'
    await form.handleSubmit()
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'John', email: 'john@test.com' }),
    )
    expect(form.submitting.value).toBe(false)
  })

  it('handles async submit with API ValidationError', async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      new ValidationError('Validation failed', {
        email: ['Email already taken'],
      }),
    )
    const form = createTestForm({ onSubmit })
    form.values.name = 'John'
    form.values.email = 'taken@test.com'
    await form.handleSubmit()
    expect(form.errors.email).toBe('Email already taken')
  })

  it('sets submitting state during async submit', async () => {
    let resolveSubmit: () => void
    const onSubmit = vi.fn().mockReturnValue(
      new Promise<void>((r) => {
        resolveSubmit = r
      }),
    )
    const form = createTestForm({ onSubmit })
    form.values.name = 'John'
    form.values.email = 'john@test.com'
    const promise = form.handleSubmit()
    expect(form.submitting.value).toBe(true)
    resolveSubmit!()
    await promise
    expect(form.submitting.value).toBe(false)
  })

  it('sets submitError on generic Error', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('Network error'))
    const form = createTestForm({ onSubmit })
    form.values.name = 'John'
    form.values.email = 'john@test.com'
    await form.handleSubmit()
    expect(form.submitError.value).toBe('Network error')
  })

  it('resets values and errors to initial state', () => {
    const form = createTestForm()
    form.values.name = 'Changed'
    form.handleSubmit()
    expect(form.errors.email).toBeTruthy()
    form.reset()
    expect(form.values.name).toBe('')
    expect(form.errors.email).toBeUndefined()
  })

  it('tracks isDirty when values change', () => {
    const form = createTestForm()
    expect(form.isDirty.value).toBe(false)
    form.values.name = 'Changed'
    expect(form.isDirty.value).toBe(true)
  })

  it('tracks isDirty as false after reset', () => {
    const form = createTestForm()
    form.values.name = 'Changed'
    expect(form.isDirty.value).toBe(true)
    form.reset()
    expect(form.isDirty.value).toBe(false)
  })

  it('tracks touched fields via markTouched', () => {
    const form = createTestForm()
    expect(form.touched.value.name).toBeUndefined()
    form.markTouched('name')
    expect(form.touched.value.name).toBe(true)
  })

  it('tracks touched fields via setFieldValue', () => {
    const form = createTestForm()
    form.setFieldValue('email', 'new@test.com')
    expect(form.values.email).toBe('new@test.com')
    expect(form.touched.value.email).toBe(true)
  })

  it('resets touched on reset', () => {
    const form = createTestForm()
    form.markTouched('name')
    form.markTouched('email')
    form.reset()
    expect(form.touched.value).toEqual({})
  })

  it('isValid reflects validation state', () => {
    const form = createTestForm()
    expect(form.isValid.value).toBe(true)
    form.handleSubmit()
    expect(form.isValid.value).toBe(false)
    form.clearErrors()
    expect(form.isValid.value).toBe(true)
  })
})
