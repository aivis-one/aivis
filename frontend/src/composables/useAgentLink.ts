// =============================================================================
// AIVIS.ONE Frontend -- The integrator's one link
// =============================================================================
//
// An integrator has exactly one referral link. The platform issues it once,
// after the integrator-agent agreement is accepted; asking again returns the
// same link. This composable carries the whole of that:
//
//   - `agreement`: where the agreement stands for this person -- 'loading',
//     'unsigned' (the screen offers the one click), 'signed' or 'missing' (no
//     active document of that type; the link is then asked for directly);
//   - `accept()`: the one click -- records the acceptance of the agreement,
//     then asks the platform for the link;
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
import { useToast } from '@/composables/useToast'

export const AGENT_AGREEMENT_TYPE = 'agent_integrator_agreement'

export type AgreementState = 'loading' | 'unsigned' | 'signed' | 'missing' | 'error'

export function buildShareUrl(code: string, projectId?: string): string {
  const base = `${window.location.origin}${import.meta.env.BASE_URL}r/${code}`
  return projectId ? `${base}?p=${encodeURIComponent(projectId)}` : base
}

export function useAgentLink() {
  const { t } = useI18n()
  const { showToast } = useToast()
  const agentStore = useAgentStore()

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
      if (agreement.value === 'signed' || agreement.value === 'missing') {
        await issueLink()
      }
    } catch {
      agreement.value = 'error'
    }
  }

  /** The one click: accept the agreement, then take the link. */
  async function accept(): Promise<void> {
    if (accepting.value) return
    accepting.value = true
    try {
      const result = await acceptDocumentByType(AGENT_AGREEMENT_TYPE)
      agreement.value = result === 'missing' ? 'missing' : 'signed'
      await agentStore.createLink()
      void agentStore.fetchStats()
      showToast(t('agent.link.accepted'), 'success')
    } catch {
      showToast(t('agent.link.acceptError'), 'error')
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
