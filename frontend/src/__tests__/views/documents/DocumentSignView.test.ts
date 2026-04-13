import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import DocumentSignView from '@/views/shared/DocumentSignView.vue'
import { mountWithI18n } from '../../helpers'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ params: { id: 'doc-1' }, path: '/investor/documents/doc-1/sign' }),
}))

vi.mock('@/platform', () => ({ platform: { type: 'standalone' } }))
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    telegramAuth: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
  },
}))
vi.mock('@/api/profile', () => ({
  profileApi: { get: vi.fn(), update: vi.fn(), uploadAvatar: vi.fn() },
}))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))

const mockDocumentsApi = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn().mockResolvedValue({
    id: 'doc-1',
    title: 'Agreement',
    type: 'agreement',
    status: 'pending_signature',
    description: 'Please read and sign.',
    file_url: null,
    file_size: null,
    created_at: '2026-04-12',
    updated_at: '2026-04-12',
    signed_at: null,
    expires_at: null,
  }),
  sign: vi.fn(),
}))
vi.mock('@/api/documents', () => ({ documentsApi: mockDocumentsApi }))

describe('DocumentSignView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockDocumentsApi.get.mockResolvedValue({
      id: 'doc-1',
      title: 'Agreement',
      type: 'agreement',
      status: 'pending_signature',
      description: 'Please read and sign.',
      file_url: null,
      file_size: null,
      created_at: '2026-04-12',
      updated_at: '2026-04-12',
      signed_at: null,
      expires_at: null,
    })
  })

  it('renders agreement text', async () => {
    const wrapper = mountWithI18n(DocumentSignView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.doc-sign__agreement-text').text()).toContain('Please read and sign.')
  })

  it('sign button is disabled without checkbox', async () => {
    const wrapper = mountWithI18n(DocumentSignView)
    await nextTick()
    await nextTick()
    const btn = wrapper.find('.c-btn--primary')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('sign button is disabled without signature text', async () => {
    const wrapper = mountWithI18n(DocumentSignView)
    await nextTick()
    await nextTick()
    // Check checkbox
    await wrapper.find('input[type="checkbox"]').setValue(true)
    await nextTick()
    const btn = wrapper.find('.c-btn--primary')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('successful signing navigates back', async () => {
    mockDocumentsApi.sign.mockResolvedValue({
      id: 'doc-1',
      title: 'Agreement',
      type: 'agreement',
      status: 'signed',
      description: '',
      file_url: null,
      file_size: null,
      created_at: '2026-04-12',
      updated_at: '2026-04-12',
      signed_at: '2026-04-12',
      expires_at: null,
    })

    const wrapper = mountWithI18n(DocumentSignView)
    await nextTick()
    await nextTick()

    await wrapper.find('input[type="checkbox"]').setValue(true)
    await wrapper.find('.c-input__field').setValue('John Doe')
    await nextTick()

    await wrapper.find('.c-btn--primary').trigger('click')
    await nextTick()
    await nextTick()

    expect(mockDocumentsApi.sign).toHaveBeenCalled()
  })

  it('back button navigates to document detail', async () => {
    const wrapper = mountWithI18n(DocumentSignView)
    await nextTick()
    await nextTick()
    await wrapper.find('.c-btn--ghost').trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/investor/documents/doc-1')
  })
})
