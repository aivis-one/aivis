// =============================================================================
// AIVIS.ONE Frontend -- staffQueues store (the staff Home's counters)
// =============================================================================
//
// One counter for every queue a staff member works from: identity checks to
// decide, top-ups still in their hour, withdrawals waiting, integrator
// applications waiting, support requests nobody has taken, and -- for the
// administrator -- the clients' requests to confirm a top-up by hand.
//
// A FAILED READ IS AN ERROR, NEVER A ZERO. Each queue is read on its own and
// keeps its own state -- `loading`, `ready` or `error` -- so one failing read
// leaves the others standing and shows as a failure on its own card, where
// the old screen turned a failed read into an empty list and a "0" that said
// nothing was waiting.
//
// A queue the member has no right to is not read (the server would refuse the
// read) and is not drawn: `visibleQueues` is the queues the member may work.
// =============================================================================

import { defineStore } from 'pinia'

import { fetchAgentApplications, fetchDashboardStats, fetchWithdrawalsStaff } from '@/api/admin'
import { listStaffTickets } from '@/api/support'
import type { StaffPermissionKey } from '@/composables/useStaffPermissions'

export type QueueKey = 'kyc' | 'topups' | 'withdrawals' | 'agentApps' | 'support' | 'manualTopups'

export type QueueStatus = 'loading' | 'ready' | 'error'

export interface QueueState {
  status: QueueStatus
  count: number
  /** True when the count is a floor (a longer list than one page was read). */
  more: boolean
}

export interface QueueSpec {
  key: QueueKey
  /** The right the queue needs; none = every staff member works it. */
  permission?: StaffPermissionKey
  /** True when the queue is the administrator's alone (the right is not enough). */
  admin?: boolean
  /** Where a press on the card leads. */
  path: string
  labelKey: string
}

/** The queues, in the order the Home shows them. */
export const QUEUES: readonly QueueSpec[] = [
  {
    key: 'kyc',
    permission: 'kyc_approve',
    path: '/staff/users?kyc_status=submitted',
    labelKey: 'staff.home.queues.kyc',
  },
  {
    key: 'topups',
    permission: 'payment_review',
    path: '/staff/finance/payments',
    labelKey: 'staff.home.queues.topups',
  },
  {
    key: 'withdrawals',
    permission: 'payment_review',
    path: '/staff/finance/withdrawals',
    labelKey: 'staff.home.queues.withdrawals',
  },
  {
    key: 'agentApps',
    permission: 'agent_application_review',
    path: '/staff/users/agent-apps',
    labelKey: 'staff.home.queues.agentApps',
  },
  {
    key: 'support',
    path: '/staff/users/support',
    labelKey: 'staff.home.queues.support',
  },
  {
    // Crypto invoices whose client asked for a manual confirmation and that
    // are not credited yet; the card opens the list filtered to them.
    key: 'manualTopups',
    permission: 'financial_operations',
    admin: true,
    path: '/staff/finance/invoices?open_request=1',
    labelKey: 'staff.home.queues.manualTopups',
  },
]

/** True when a member with these rights works the queue. */
export function queueAllowed(
  q: QueueSpec,
  can: (key: StaffPermissionKey) => boolean,
  admin: boolean,
): boolean {
  return (!q.permission || can(q.permission)) && (!q.admin || admin)
}

/** How many support rows one read looks at; more than this shows as "N+". */
const SUPPORT_WINDOW = 100

/** The server's `users_by_role` as whole numbers; a value that is not a number is dropped. */
function countsByRole(raw: Record<string, unknown> | null | undefined): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [role, count] of Object.entries(raw ?? {})) {
    if (typeof count === 'number' && Number.isFinite(count)) out[role] = count
  }
  return out
}

function blank(): QueueState {
  return { status: 'loading', count: 0, more: false }
}

export const useStaffQueuesStore = defineStore('staffQueues', {
  state: () => ({
    queues: {
      kyc: blank(),
      topups: blank(),
      withdrawals: blank(),
      agentApps: blank(),
      support: blank(),
      manualTopups: blank(),
    } as Record<QueueKey, QueueState>,
    /** All users of the platform (a figure, not a queue). */
    users: { status: 'loading', count: 0 } as { status: QueueStatus; count: number },
    /**
     * The administrator's two extra figures from the same read of the statistics:
     * the users by role and the avatar sessions open now.
     */
    overview: { status: 'loading', byRole: {}, avatarSessions: 0 } as {
      status: QueueStatus
      byRole: Record<string, number>
      avatarSessions: number
    },
  }),

  getters: {
    /** True when any read failed. */
    anyFailed: (state): boolean =>
      state.users.status === 'error' ||
      state.overview.status === 'error' ||
      Object.values(state.queues).some((q) => q.status === 'error'),
  },

  actions: {
    /**
     * Read the queues the member may work, each on its own. `can` says whether
     * the member holds a right and `admin` whether they are an administrator; a
     * queue they may not work is left out of the reads (and is not drawn by the
     * screen).
     */
    async loadAll(can: (key: StaffPermissionKey) => boolean, admin = false): Promise<void> {
      const allowed = (q: QueueSpec) => queueAllowed(q, can, admin)
      const wants = (key: QueueKey) => QUEUES.some((q) => q.key === key && allowed(q))

      for (const q of QUEUES) {
        if (allowed(q)) this.queues[q.key] = blank()
      }
      this.users = { status: 'loading', count: 0 }
      this.overview = { status: 'loading', byRole: {}, avatarSessions: 0 }

      const reads: Promise<void>[] = []

      // The identity-check queue, the top-ups in their hour and the user count
      // come from one read of the platform's statistics.
      reads.push(
        (async () => {
          try {
            const stats = await fetchDashboardStats()
            this.users = { status: 'ready', count: stats.total_users }
            this.overview = {
              status: 'ready',
              byRole: countsByRole(stats.users_by_role),
              avatarSessions: Number(stats.active_avatar_sessions) || 0,
            }
            if (wants('kyc')) {
              this.queues.kyc = { status: 'ready', count: stats.pending_kyc_count, more: false }
            }
            if (wants('topups')) {
              this.queues.topups = {
                status: 'ready',
                count: stats.frozen_payments_count,
                more: false,
              }
            }
            if (wants('manualTopups')) {
              this.queues.manualTopups = {
                status: 'ready',
                count: stats.manual_topup_requests_count,
                more: false,
              }
            }
          } catch {
            this.users = { status: 'error', count: 0 }
            this.overview = { status: 'error', byRole: {}, avatarSessions: 0 }
            if (wants('kyc')) this.queues.kyc = { status: 'error', count: 0, more: false }
            if (wants('topups')) this.queues.topups = { status: 'error', count: 0, more: false }
            if (wants('manualTopups')) {
              this.queues.manualTopups = { status: 'error', count: 0, more: false }
            }
          }
        })(),
      )

      if (wants('withdrawals')) {
        reads.push(
          this.read('withdrawals', async () => {
            const page = await fetchWithdrawalsStaff({ status: 'pending', page: 1, per_page: 1 })
            return { count: page.total, more: false }
          }),
        )
      }

      if (wants('agentApps')) {
        reads.push(
          this.read('agentApps', async () => {
            const page = await fetchAgentApplications({ page: 1, per_page: 1 })
            return { count: page.total, more: false }
          }),
        )
      }

      if (wants('support')) {
        reads.push(
          this.read('support', async () => {
            // H40: open tickets nobody has taken. The list has no "not
            // taken" filter, so one window of open tickets is read and
            // counted here; a longer list shows as a floor ("N+").
            const page = await listStaffTickets({ status: 'open', limit: SUPPORT_WINDOW })
            const unclaimed = page.items.filter((row) => row.claimed_by === null).length
            return { count: unclaimed, more: page.next_cursor !== null }
          }),
        )
      }

      await Promise.all(reads)
    },

    async read(key: QueueKey, fn: () => Promise<{ count: number; more: boolean }>): Promise<void> {
      try {
        const { count, more } = await fn()
        this.queues[key] = { status: 'ready', count, more }
      } catch {
        this.queues[key] = { status: 'error', count: 0, more: false }
      }
    },
  },
})
