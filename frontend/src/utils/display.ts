import type { KycStatus, DocumentStatus } from '@/api/types'

export function getKycStatusColor(status: KycStatus): string {
  switch (status) {
    case 'approved':
      return 'var(--success)'
    case 'rejected':
      return 'var(--error)'
    case 'pending':
    case 'in_review':
      return 'var(--warning)'
    default:
      return 'var(--text-secondary)'
  }
}

export function getKycStatusIcon(status: KycStatus): string {
  switch (status) {
    case 'approved':
      return 'check-circle'
    case 'rejected':
      return 'x-circle'
    case 'pending':
    case 'in_review':
      return 'clock'
    default:
      return 'file-question'
  }
}

export function getDocumentStatusColor(status: DocumentStatus): string {
  const map: Record<DocumentStatus, string> = {
    draft: 'var(--text-secondary)',
    pending_signature: 'var(--warning)',
    signed: 'var(--success)',
    expired: 'var(--text-tertiary)',
    rejected: 'var(--error)',
  }
  return map[status] ?? 'var(--text-secondary)'
}

export function getDocumentStatusIcon(status: DocumentStatus): string {
  const map: Record<DocumentStatus, string> = {
    draft: 'file-edit',
    pending_signature: 'pen-tool',
    signed: 'file-check',
    expired: 'clock',
    rejected: 'file-x',
  }
  return map[status] ?? 'file'
}
