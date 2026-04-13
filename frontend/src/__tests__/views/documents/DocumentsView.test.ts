import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import DocumentsView from '@/views/shared/DocumentsView.vue'
import { mountWithI18n } from '../../helpers'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/investor/documents' }),
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
  list: vi.fn().mockResolvedValue({ data: [], total: 0, page: 1, per_page: 10 }),
  get: vi.fn(),
  sign: vi.fn(),
}))
vi.mock('@/api/documents', () => ({ documentsApi: mockDocumentsApi }))

describe('DocumentsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockDocumentsApi.list.mockResolvedValue({ data: [], total: 0, page: 1, per_page: 10 })
  })

  it('renders title', () => {
    const wrapper = mountWithI18n(DocumentsView)
    expect(wrapper.find('.docs-view__title').exists()).toBe(true)
  })

  it('renders filter controls', () => {
    const wrapper = mountWithI18n(DocumentsView)
    expect(wrapper.findAll('.docs-view__select')).toHaveLength(2)
  })

  it('shows empty state when no documents', async () => {
    const wrapper = mountWithI18n(DocumentsView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.docs-view__empty').exists()).toBe(true)
  })

  it('renders document list when data loaded', async () => {
    mockDocumentsApi.list.mockResolvedValue({
      data: [
        {
          id: '1',
          title: 'Doc 1',
          type: 'contract',
          status: 'signed',
          description: '',
          file_url: null,
          file_size: null,
          created_at: '',
          updated_at: '',
          signed_at: null,
          expires_at: null,
        },
      ],
      total: 1,
      page: 1,
      per_page: 10,
    })

    const wrapper = mountWithI18n(DocumentsView)
    await nextTick()
    await nextTick()
    expect(wrapper.findAll('.docs-view__item')).toHaveLength(1)
  })
})
