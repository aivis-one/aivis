// =============================================================================
// AIVIS.ONE Frontend -- the parts-per-lot of the projects a screen shows
// =============================================================================
//
// A purchase, an instalment plan, a gift or a ledger entry counts LOTS and names
// its project; the buyer sees PARTS (lots x the project's parts per lot). Where the
// answer does not carry the project's parts per lot, a screen asks the project
// once and keeps the answer: this composable does the asking and the keeping.
//
// While a project's figure is unknown (still loading, or the project could not be
// read) `partsPerLot` answers null and the screen shows no count rather than the
// lot count.
// =============================================================================

import { reactive } from 'vue'
import { getCompany } from '@/api/companies'

// One request per project for the life of the page.
const requests = new Map<string, Promise<number | null>>()

/** The project's parts per lot, null when it cannot be read. Asked once per project. */
export function loadSharesPerOption(companyId: string): Promise<number | null> {
  let request = requests.get(companyId)
  if (!request) {
    request = getCompany(companyId)
      .then((c) => (c.shares_per_option > 0 ? c.shares_per_option : null))
      .catch(() => null)
    requests.set(companyId, request)
  }
  return request
}

/** Forgets what was kept (a test starts from nothing). */
export function resetSharesPerOptionCache(): void {
  requests.clear()
}

export function useSharesPerOption() {
  const known = reactive<Record<string, number>>({})

  /** Asks for every project named; resolves when the answers are in. */
  async function ensure(companyIds: Iterable<string>): Promise<void> {
    const ids = [...new Set(companyIds)].filter((id) => known[id] === undefined)
    await Promise.all(
      ids.map(async (id) => {
        const n = await loadSharesPerOption(id)
        if (n !== null) known[id] = n
      }),
    )
  }

  /** The project's parts per lot, or null while it is unknown. */
  function partsPerLot(companyId: string | null | undefined): number | null {
    if (!companyId) return null
    return known[companyId] ?? null
  }

  return { ensure, partsPerLot }
}
