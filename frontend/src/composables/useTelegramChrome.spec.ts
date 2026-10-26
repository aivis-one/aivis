// =============================================================================
// useTelegramChrome -- Telegram's Back button and theme, nothing in a browser
// =============================================================================
//
// Axes: INSIDE Telegram and in a plain BROWSER (the web must be unchanged); a
// tab ROOT and a page BELOW it; a press with history behind and without.
// =============================================================================

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive } from 'vue'
import { mount as mountComponent } from '@vue/test-utils'

const route = reactive({ path: '/staff/dashboard', meta: { shell: 'staff' } as { shell?: string } })
const router = { back: vi.fn(), replace: vi.fn() }
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => router,
}))

const platformMock = vi.hoisted(() => ({
  name: 'telegram' as 'telegram' | 'standalone',
  showBackButton: vi.fn(),
  hideBackButton: vi.fn(),
  getTheme: vi.fn(() => 'dark' as 'light' | 'dark'),
  onThemeChanged: vi.fn(),
}))
vi.mock('@/platform', () => ({ platform: platformMock }))

import { backPlan, useTelegramChrome } from './useTelegramChrome'
import { useTheme } from './useTheme'

// Every mounted host is unmounted after its test: a host left standing would go on
// answering the shared route of the next test.
const mounted: Array<{ unmount: () => void }> = []
function mount(component: typeof Host) {
  const wrapper = mountComponent(component)
  mounted.push(wrapper)
  return wrapper
}

const Host = defineComponent({
  setup() {
    useTelegramChrome()
    return () => h('div')
  },
})

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
})

beforeEach(() => {
  vi.clearAllMocks()
  platformMock.name = 'telegram'
  platformMock.getTheme.mockReturnValue('dark')
  platformMock.onThemeChanged.mockReturnValue(() => undefined)
  route.path = '/staff/dashboard'
  route.meta = { shell: 'staff' }
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  useTheme().followHost(null)
  useTheme().set('auto')
})

describe('which pages are the root of a tab', () => {
  it('a tab path and a hub section of the staff cabinet are roots', () => {
    expect(backPlan('/staff/dashboard', 'staff').root).toBe(true)
    expect(backPlan('/staff/settings', 'staff').root).toBe(true)
    expect(backPlan('/staff/finance/payments', 'staff').root).toBe(true)
    expect(backPlan('/staff/docs', 'staff').root).toBe(true)
  })

  it('a page below a section, or outside every tab, is not a root and falls back to a tab', () => {
    expect(backPlan('/staff/users/support/abc', 'staff')).toEqual({
      root: false,
      home: '/staff/users',
    })
    expect(backPlan('/staff/platform/projects/p1/profile', 'staff').root).toBe(false)
    expect(backPlan('/staff/notifications', 'staff')).toEqual({
      root: false,
      home: '/staff/dashboard',
    })
  })

  it('in another cabinet only the tab path itself is a root', () => {
    expect(backPlan('/investor/portfolio', 'investor').root).toBe(true)
    expect(backPlan('/investor/portfolio/holding-1', 'investor').root).toBe(false)
  })

  it('a page with no cabinet has no Back', () => {
    expect(backPlan('/login', undefined).root).toBe(true)
  })
})

describe('inside Telegram', () => {
  it('hides the Back button on a tab root', () => {
    mount(Host)
    expect(platformMock.hideBackButton).toHaveBeenCalled()
    expect(platformMock.showBackButton).not.toHaveBeenCalled()
  })

  it('shows it below the root, and hides it again on the way back', async () => {
    mount(Host)
    route.path = '/staff/users/support/abc'
    await nextTick()
    expect(platformMock.showBackButton).toHaveBeenCalledTimes(1)
    route.path = '/staff/users'
    await nextTick()
    expect(platformMock.hideBackButton).toHaveBeenCalledTimes(2)
  })

  it('a press goes back one step when the app has history behind it', () => {
    route.path = '/staff/users/support/abc'
    window.history.replaceState({ back: '/staff/users/support' }, '')
    mount(Host)
    const press = platformMock.showBackButton.mock.calls[0]![0] as () => void
    press()
    expect(router.back).toHaveBeenCalled()
    expect(router.replace).not.toHaveBeenCalled()
  })

  it('a press goes to the root of the tab when the app was opened on the deep page', () => {
    route.path = '/staff/users/support/abc'
    window.history.replaceState({ back: null }, '')
    mount(Host)
    const press = platformMock.showBackButton.mock.calls[0]![0] as () => void
    press()
    expect(router.replace).toHaveBeenCalledWith('/staff/users')
    expect(router.back).not.toHaveBeenCalled()
  })

  it('follows the theme of Telegram while the choice is automatic, and again when it changes', () => {
    let notify: (theme: 'light' | 'dark') => void = () => undefined
    platformMock.onThemeChanged.mockImplementation((cb: typeof notify) => {
      notify = cb
      return () => undefined
    })
    mount(Host)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(useTheme().effective.value).toBe('dark')
    notify('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    // Nothing is stored: it is the theme of Telegram, not the person's choice.
    expect(localStorage.getItem('aivis-theme')).toBeNull()
  })

  it("leaves the person's own choice alone", () => {
    useTheme().set('light')
    mount(Host)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(useTheme().effective.value).toBe('light')
  })

  it('stops following and hides the button when the app goes away', () => {
    const stop = vi.fn()
    platformMock.onThemeChanged.mockReturnValue(stop)
    const wrapper = mount(Host)
    wrapper.unmount()
    expect(stop).toHaveBeenCalled()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
})

describe('in a plain browser', () => {
  it('does nothing at all', () => {
    platformMock.name = 'standalone'
    route.path = '/staff/users/support/abc'
    mount(Host)
    expect(platformMock.showBackButton).not.toHaveBeenCalled()
    expect(platformMock.hideBackButton).not.toHaveBeenCalled()
    expect(platformMock.onThemeChanged).not.toHaveBeenCalled()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
})
