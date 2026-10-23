// =============================================================================
// AIVIS.ONE Frontend -- The integrator's one link
// =============================================================================
//
// An integrator has exactly one referral link. The platform issues it once,
// after the agent-integrator agreement is accepted; asking again returns the
// same link. This composable carries the whole of that:
//
//   - `agreement`: where the agreement stands for this person -- 'loading',
//     'unsigned' (the acceptance screen is due), 'signed' or 'missing' (no
//     active document of that type; no link can be issued until it is
//     published);
//   - `accept()`: the acceptance -- records it, then asks the platform for the
//     link; true when both are done;
//   - `link`, `shareUrl()`, `copy()`, `share()`: the link as the screens use it.
//
// The share address is the cabinet's own capture route, `<origin><base>r/<code>`;
// with a project id it carries `?p=<id>` and the capture route lands the visitor
// on that project.
// =============================================================================

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { acceptDocumentByType, getDocumentByType } from '@/api/documents'
import { ApiResponseError } from '@/api/client'
import { useAgentStore } from '@/stores/agent'
import { AGENT_AGREEMENT_TYPE, useAgentAgreementStore } from '@/stores/agentAgreement'
import { useToast } from '@/composables/useToast'

export type AgreementState = 'loading' | 'unsigned' | 'signed' | 'missing' | 'error'

export function buildShareUrl(code: string, projectId?: string): string {
  const base = `${window.location.origin}${import.meta.env.BASE_URL}r/${code}`
  return projectId ? `${base}?p=${encodeURIComponent(projectId)}` : base
}

export function useAgentLink() {
  const { t } = useI18n()
  const { showToast } = useToast()
  const agentStore = useAgentStore()
  const agreementStore = useAgentAgreementStore()

  const agreement = ref<AgreementState>('loading')
  const accepting = ref(false)

  const link = computed(() => agentStore.myLink)
  const hasLink = computed(() => link.value !== null)

  async function issueLink(): Promise<void> {
    try {
      await agentStore.createLink()
    } catch (err) {
      // 403 before the agreement is accepted; the screen then shows the click.
      if (!(err instanceof ApiResponseError && err.status === 403)) throw err
      agreement.value = 'unsigned'
    }
  }

  /** Reads the agreement's state and the link; issues the link when it is due. */
  async function load(): Promise<void> {
    agreement.value = 'loading'
    try {
      await agentStore.fetchLinksFirstPage()
      if (agentStore.myLink) {
        agreement.value = 'signed'
        return
      }
      try {
        const doc = await getDocumentByType(AGENT_AGREEMENT_TYPE)
        agreement.value = doc.is_signed ? 'signed' : 'unsigned'
      } catch (err) {
        if (err instanceof ApiResponseError && err.status === 404) {
          agreement.value = 'missing'
        } else {
          throw err
        }
      }
      if (agreement.value === 'signed') {
        await issueLink()
      }
    } catch {
      agreement.value = 'error'
    }
  }

  /** The acceptance: record it, then take the link. True when both are done. */
  async function accept(): Promise<boolean> {
    if (accepting.value) return false
    accepting.value = true
    try {
      const result = await acceptDocumentByType(AGENT_AGREEMENT_TYPE)
      if (result === 'missing') {
        agreement.value = 'missing'
        agreementStore.markMissing()
        return false
      }
      await agentStore.createLink()
      agreement.value = 'signed'
      agreementStore.markSigned()
      void agentStore.fetchStats()
      showToast(t('agent.link.accepted'), 'success')
      return true
    } catch {
      showToast(t('agent.link.acceptError'), 'error')
      return false
    } finally {
      accepting.value = false
    }
  }

  function shareUrl(projectId?: string): string {
    return link.value ? buildShareUrl(link.value.code, projectId) : ''
  }

  async function copy(projectId?: string): Promise<void> {
    if (!link.value) return
    try {
      await navigator.clipboard.writeText(shareUrl(projectId))
      showToast(t(projectId ? 'agent.link.projectCopied' : 'agent.link.copied'), 'success')
    } catch {
      // The clipboard can be unavailable (an insecure context, permissions).
      showToast(t('agent.link.copyError'), 'error')
    }
  }

  /** The system share menu of the phone; falls back to copying. */
  async function share(projectId?: string): Promise<void> {
    if (!link.value) return
    const url = shareUrl(projectId)
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ title: t('agent.link.shareTitle'), url })
      } catch {
        // The person closed the menu: nothing to report.
      }
      return
    }
    await copy(projectId)
  }

  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

  return { agreement, accepting, link, hasLink, load, accept, shareUrl, copy, share, canShare }
}
