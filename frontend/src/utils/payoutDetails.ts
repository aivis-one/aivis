// =============================================================================
// AIVIS.ONE Frontend -- payout details, read as a person reads them
// =============================================================================
//
// A withdrawal carries a snapshot of the payout details the person saved: a
// free-form object on the server whose two fields in use are the NETWORK and
// the WALLET. Staff decide on a withdrawal by looking at where it goes, so the
// screen shows the network and the wallet as two labelled lines -- never the
// raw object. Any other field a snapshot may carry follows them as its own
// line, named by its key, so nothing the person saved is hidden.
// =============================================================================

/** One line of the payout details. */
export interface PayoutLine {
  /** `network`, `wallet`, or any other key of the snapshot. */
  key: string
  value: string
}

/** True for the two fields the screen has a name for. */
export function isKnownPayoutKey(key: string): key is 'network' | 'wallet' {
  return key === 'network' || key === 'wallet'
}

function asText(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() === '' ? null : value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

/**
 * The lines of a payout snapshot: the network, then the wallet, then any other
 * simple field in the order the snapshot has them. A nested value is shown as
 * its JSON text on its own line rather than dropped.
 */
export function payoutLines(snapshot: Record<string, unknown> | null | undefined): PayoutLine[] {
  if (!snapshot) return []
  const lines: PayoutLine[] = []
  for (const key of ['network', 'wallet']) {
    const text = asText(snapshot[key])
    if (text !== null) lines.push({ key, value: text })
  }
  for (const [key, value] of Object.entries(snapshot)) {
    if (isKnownPayoutKey(key)) continue
    const text = asText(value) ?? (value == null ? null : JSON.stringify(value))
    if (text !== null) lines.push({ key, value: text })
  }
  return lines
}
