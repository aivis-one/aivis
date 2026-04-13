import { describe, it, expect } from 'vitest'
import CFileUpload from '@/components/ui/CFileUpload.vue'
import { mountWithI18n } from '../../helpers'

function createFile(name: string, size: number, type: string): File {
  const content = new Array(size).fill('a').join('')
  return new File([content], name, { type })
}

describe('CFileUpload', () => {
  it('renders with label', () => {
    const wrapper = mountWithI18n(CFileUpload, {
      props: { label: 'Upload document' },
    })
    expect(wrapper.find('.c-file-upload__label').text()).toBe('Upload document')
  })

  it('renders drop zone', () => {
    const wrapper = mountWithI18n(CFileUpload)
    expect(wrapper.find('.c-file-upload__zone').exists()).toBe(true)
  })

  it('emits update:modelValue on file select', async () => {
    const wrapper = mountWithI18n(CFileUpload)
    const file = createFile('doc.pdf', 100, 'application/pdf')

    const input = wrapper.find('.c-file-upload__input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0][0]).toEqual(file)
  })

  it('validates file size and emits validation-error', async () => {
    const wrapper = mountWithI18n(CFileUpload, {
      props: { maxSize: 50 },
    })
    const file = createFile('big.pdf', 100, 'application/pdf')

    const input = wrapper.find('.c-file-upload__input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')

    expect(wrapper.emitted('validation-error')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  it('validates file type and emits validation-error', async () => {
    const wrapper = mountWithI18n(CFileUpload, {
      props: { accept: 'image/*' },
    })
    const file = createFile('doc.pdf', 100, 'application/pdf')

    const input = wrapper.find('.c-file-upload__input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')

    expect(wrapper.emitted('validation-error')).toBeTruthy()
  })

  it('accepts valid file type', async () => {
    const wrapper = mountWithI18n(CFileUpload, {
      props: { accept: 'image/*' },
    })
    const file = createFile('photo.png', 100, 'image/png')

    const input = wrapper.find('.c-file-upload__input')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
  })

  it('shows preview for selected files', async () => {
    const file = createFile('doc.pdf', 100, 'application/pdf')
    const wrapper = mountWithI18n(CFileUpload, {
      props: { modelValue: file },
    })
    expect(wrapper.find('.c-file-upload__file').exists()).toBe(true)
    expect(wrapper.find('.c-file-upload__name').text()).toBe('doc.pdf')
  })

  it('removes file on remove button click', async () => {
    const file = createFile('doc.pdf', 100, 'application/pdf')
    const wrapper = mountWithI18n(CFileUpload, {
      props: { modelValue: file },
    })
    await wrapper.find('.c-file-upload__remove').trigger('click')
    expect(wrapper.emitted('update:modelValue')![0][0]).toBeNull()
  })

  it('applies disabled state', () => {
    const wrapper = mountWithI18n(CFileUpload, {
      props: { disabled: true },
    })
    expect(wrapper.find('.c-file-upload--disabled').exists()).toBe(true)
    expect(wrapper.find('.c-file-upload__input').attributes('disabled')).toBeDefined()
  })

  it('handles dragover and dragleave events', async () => {
    const wrapper = mountWithI18n(CFileUpload)
    const zone = wrapper.find('.c-file-upload__zone')

    await zone.trigger('dragover')
    expect(zone.classes()).toContain('c-file-upload__zone--drag')

    await zone.trigger('dragleave')
    expect(zone.classes()).not.toContain('c-file-upload__zone--drag')
  })
})
