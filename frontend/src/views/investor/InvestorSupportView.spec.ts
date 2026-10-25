// =============================================================================
// InvestorSupportView -- one conversation, a form and a composer (H40);
// the greeting of an empty conversation, the composer's line, the server's own words (F7)
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {}, meta: { shell: 'investor' }, matched: [] }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/support', async (importActual) => ({
  ...(await importActual<typeof import('@/api/support')>()),
  getSupportMessages: vi.fn(),
  markSupportRead: vi.fn(),
  createSupportTicket: vi.fn(),
  sendSupportMessage: vi.fn(),
}))

import * as api from '@/api/support'
import { ApiResponseError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import InvestorSupportView from './InvestorSupportView.vue'

const feed = vi.mocked(api.getSupportMessages)
const read = vi.mocked(api.markSupportRead)
const create = vi.mocked(api.createSupportTicket)
const send = vi.mocked(api.sendSupportMessage)

const MESSAGE = {
  id: 'm1',
  thread_id: 't1',
  sender: 'me',
  body: 'hi',
  created_at: null,
  translation: null,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  read.mockResolvedValue({ unread: 0 })
  const auth = useAuthStore()
  auth.user = { id: 'me', role: 'investor' } as unknown as typeof auth.user
})

describe('the support conversation', () => {
  it('an empty conversation is the form, with every topic and no composer', async () => {
    feed.mockResolvedValue({ items: [], next_cursor: null })
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    expect(wrapper.text()).toContain('inv.support.form.title')
    const topics = wrapper
      .findAll('option')
      .map((o) => o.attributes('value'))
      .filter(Boolean)
    expect(topics).toEqual([...api.SUPPORT_TOPICS])
    expect(wrapper.find('#isup-message').exists()).toBe(false)
    wrapper.unmount()
  })

  it('a submit without a topic asks for one and sends nothing', async () => {
    feed.mockResolvedValue({ items: [], next_cursor: null })
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    await wrapper.find('form textarea').setValue('my money is gone')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('inv.support.form.topicRequired')
    wrapper.unmount()
  })

  it('the form sends the topic and the text, then shows the conversation', async () => {
    feed.mockResolvedValueOnce({ items: [], next_cursor: null })
    feed.mockResolvedValue({ items: [MESSAGE], next_cursor: null })
    create.mockResolvedValue({ ticket: {} as never, message: MESSAGE })
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    await wrapper.find('select').setValue('withdrawal')
    await wrapper.find('form textarea').setValue('my money is gone')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledWith('withdrawal', 'my money is gone', expect.any(String))
    expect(wrapper.find('#isup-message').exists()).toBe(true)
    expect(wrapper.text()).toContain('hi')
    wrapper.unmount()
  })

  it('a failed appeal keeps what was typed', async () => {
    feed.mockResolvedValue({ items: [], next_cursor: null })
    create.mockRejectedValue(new ApiResponseError(502, 'down'))
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    await wrapper.find('select').setValue('kyc')
    const text = wrapper.find('form textarea')
    await text.setValue('my documents')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect((text.element as HTMLTextAreaElement).value).toBe('my documents')
    expect(wrapper.text()).toContain('inv.support.errorUnavailable')
    wrapper.unmount()
  })

  it('a message in the conversation goes to the conversation, not to a form', async () => {
    feed.mockResolvedValue({ items: [MESSAGE], next_cursor: null })
    send.mockResolvedValue(MESSAGE)
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    expect(wrapper.text()).not.toContain('inv.support.form.title')
    await wrapper.find('#isup-message').setValue('one more thing')
    await wrapper.find('.ds-composer').trigger('submit')
    await flushPromises()
    expect(send).toHaveBeenCalledWith('one more thing', expect.any(String))
    expect(create).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("support's replies are signed Support, the person's own are not", async () => {
    feed.mockResolvedValue({
      items: [
        { ...MESSAGE, id: 'm2', sender: 'op', body: 'we are on it' },
        { ...MESSAGE, id: 'm1' },
      ],
      next_cursor: null,
    })
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    const authors = wrapper.findAll('.ds-message__author').map((a) => a.text())
    expect(authors).toEqual(['inv.support.sender.operator'])
    wrapper.unmount()
  })

  it('a failed first load is an error, never the empty form', async () => {
    feed.mockRejectedValue(new ApiResponseError(502, 'down'))
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    expect(wrapper.text()).toContain('inv.support.feedErrorTitle')
    expect(wrapper.text()).not.toContain('inv.support.form.title')
    wrapper.unmount()
  })
})

describe('the support screen of F7', () => {
  it('an empty conversation opens with the greeting of support above the form', async () => {
    feed.mockResolvedValue({ items: [], next_cursor: null })
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    const first = wrapper.get('.ds-thread__feed .ds-message[data-from="other"]')
    expect(first.text()).toContain('inv.support.welcome')
    expect(first.text()).toContain('inv.support.sender.operator')
    expect(wrapper.text()).toContain('inv.support.form.title')
    wrapper.unmount()
  })

  it('words the greeting and the place in both languages', () => {
    expect(en.inv.support.welcome).toBe('Hello! Write to us below, we are glad to answer.')
    expect(ru.inv.support.welcome).toBe('Здравствуйте! Напишите нам ниже — мы рады ответить.')
    expect(en.inv.support.lead).toBe(
      'This is your chat with AIVIS support: questions about your purchases, documents and account.',
    )
    expect(ru.inv.support.lead).toBe(
      'Это ваш чат с поддержкой AIVIS: вопросы о покупках, документах и аккаунте.',
    )
  })

  it('keeps the composer field and the Send button on one line, the error above them', async () => {
    feed.mockResolvedValue({ items: [MESSAGE], next_cursor: null })
    send.mockRejectedValue(new ApiResponseError(409, 'Support is not reachable yet'))
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    await wrapper.get('#isup-message').setValue('Hello')
    await wrapper.get('form.ds-composer').trigger('submit')
    await flushPromises()
    expect(wrapper.get('#isup-message-error').text()).toBe('Support is not reachable yet')
    expect(wrapper.get('form.ds-composer').find('.ds-field__error').exists()).toBe(false)
    expect(wrapper.get('form.ds-composer').find('button').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows the unavailable text, not a raw status line, for a non-JSON answer', async () => {
    feed.mockResolvedValue({ items: [MESSAGE], next_cursor: null })
    send.mockRejectedValue(new ApiResponseError(502, 'HTTP 502: non-JSON response'))
    const wrapper = mount(InvestorSupportView)
    await flushPromises()
    await wrapper.get('#isup-message').setValue('Hello')
    await wrapper.get('form.ds-composer').trigger('submit')
    await flushPromises()
    expect(wrapper.get('#isup-message-error').text()).toBe('inv.support.errorUnavailable')
    wrapper.unmount()
  })
})
