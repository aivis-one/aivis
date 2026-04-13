import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import DocumentDetailView from '@/views/shared/DocumentDetailView.vue'
import { mountWithI18n } from '../../helpers'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ params: { id: 'doc-1' }, path: '/investor/documents/doc-1' }),
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
    title: 'Investment Agreement',
    type: 'agreement',
    status: 'pending_signature',
    description: 'Agreement content',
    file_url: 'https://cdn/doc.pdf',
    file_size: 2048,
    created_at: '2026-04-12',
    updated_at: '2026-04-12',
    signed_at: null,
    expires_at: '2027-04-12',
  }),
  sign: vi.fn(),
}))
vi.mock('@/api/documents', () => ({ documentsApi: mockDocumentsApi }))

describe('DocumentDetailView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockDocumentsApi.get.mockResolvedValue({
      id: 'doc-1',
      title: 'Investment Agreement',
      type: 'agreement',
      status: 'pending_signature',
      description: 'Agreement content',
      file_url: 'https://cdn/doc.pdf',
      file_size: 2048,
      created_at: '2026-04-12',
      updated_at: '2026-04-12',
      signed_at: null,
      expires_at: '2027-04-12',
    })
  })

  it('fetches document on mount', async () => {
    mountWithI18n(DocumentDetailView)
    await nextTick()
    expect(mockDocumentsApi.get).toHaveBeenCalledWith('doc-1')
  })

  it('renders document title', async () => {
    const wrapper = mountWithI18n(DocumentDetailView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.doc-detail__title').text()).toBe('Investment Agreement')
  })

  it('shows sign button for pending_signature', async () => {
    const wrapper = mountWithI18n(DocumentDetailView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.c-btn--primary').exists()).toBe(true)
  })

  it('hides sign button for signed status', async () => {
    mockDocumentsApi.get.mockResolvedValue({
      id: 'doc-1',
      title: 'Signed Doc',
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

    const wrapper = mountWithI18n(DocumentDetailView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.c-btn--primary').exists()).toBe(false)
  })

  it('back button navigates to documents list', async () => {
    const wrapper = mountWithI18n(DocumentDetailView)
    await nextTick()
    await nextTick()
    await wrapper.find('.c-btn--ghost').trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/investor/documents')
  })
})
