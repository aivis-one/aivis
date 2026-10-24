// =============================================================================
// StaffHubView -- THE CHIPS ARE THE SECTIONS THE MEMBER MAY USE, AND NO OTHERS
// =============================================================================
//
// The hub is the frame of the Users, Finance and Platform tabs. The chips come
// from the table in utils/staffRights.ts filtered by the member's rights; a
// section without the right is not drawn, and a hub with a single section
// draws no chip row.
//
// Axes: a member with ONE right (one chip: no row), with TWO (two chips), the
// ADMINISTRATOR (every chip, the money check among them), and a member with
// the right to a LATER section only (the chip of the earlier one is absent).
// The labels are the translation KEYS here: the test catalogue is empty on
// purpose (see test-setup.ts), so a reworded string cannot fail the test.
// =============================================================================

import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import type { Router } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'
import StaffHubView from './StaffHubView.vue'

const Blank = { template: '<div />' }

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/staff/platform',
        component: StaffHubView,
        meta: { hub: 'platform' },
        children: [{ path: 'news', component: Blank }],
      },
      {
        path: '/staff/finance',
        component: StaffHubView,
        meta: { hub: 'finance' },
        children: [{ path: 'payments', component: Blank }],
      },
      {
        path: '/staff/users',
        component: StaffHubView,
        meta: { hub: 'users' },
        children: [{ path: '', component: Blank }],
      },
    ],
  })
}

function signInAsStaff(held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id: 's1',
    role: 'staff',
    staff_profile: {
      permissions: Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)])),
    },
  } as unknown as typeof auth.user
}

async function chipsAt(path: string): Promise<string[]> {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  // The hub is a ROUTE component: it is mounted by the router view, as in the app.
  const wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper.findAll('.ds-subnav__link').map((chip) => chip.text())
}

describe('the staff hub chips', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('draws a chip for each Platform section the member may use', async () => {
    signInAsStaff(['content_manage', 'company_manage'])
    expect(await chipsAt('/staff/platform/news')).toEqual([
      'staff.platform.tabs.news',
      'staff.platform.tabs.events',
      'staff.platform.tabs.projects',
    ])
  })

  it('leaves out the sections of a right the member lacks, and the earlier chip with it', async () => {
    signInAsStaff(['company_manage', 'kyc_approve'])
    const chips = await chipsAt('/staff/platform/news')
    expect(chips).toEqual(['staff.platform.tabs.projects', 'staff.platform.tabs.settings'])
    expect(chips).not.toContain('staff.platform.tabs.news')
  })

  it('draws a row for two sections and no row for a single one', async () => {
    signInAsStaff(['payment_review'])
    // Payments and withdrawals both need payment_review: two chips here.
    expect(await chipsAt('/staff/finance/payments')).toEqual([
      'staff.hub.finance.payments',
      'staff.hub.finance.withdrawals',
    ])
    signInAsStaff(['kyc_approve'])
    expect(await chipsAt('/staff/platform/news')).toEqual([])
  })

  it('shows the money check only to the administrator', async () => {
    signInAsStaff(['payment_review', 'financial_operations'])
    expect(await chipsAt('/staff/finance/payments')).not.toContain(
      'staff.hub.finance.reconciliation',
    )
    signInAsStaff([...PERMISSION_KEYS])
    expect(await chipsAt('/staff/finance/payments')).toContain('staff.hub.finance.reconciliation')
  })

  it('shows the Users sections open to every member and the avatar only with its right', async () => {
    signInAsStaff([])
    expect(await chipsAt('/staff/users')).toEqual([
      'staff.hub.users.list',
      'staff.hub.users.support',
    ])
    signInAsStaff(['avatar_mode'])
    expect(await chipsAt('/staff/users')).toContain('staff.hub.users.avatar')
  })
})
