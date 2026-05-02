// =============================================================================
// CBSHOME Frontend -- Installment Plan Utilities (Phase F4.2.2)
// =============================================================================
//
// Shared parsing + tranche math for installment plans. Extracted
// after two consumers (ProductDetailView, InstallmentView) grew
// their own inline helpers with slightly different strictness levels
// and F4.4 Portfolio is about to become a third consumer.
//
// Source of truth for `plan_config` shape:
//   backend/app/modules/products/constants.py::validate_plan_config
//
// Canonical shape:
//   {
//     "tranches": [{"amount_cents": int, "units_percent": int}, ...],
//     "bonus_units": int,
//     "agent_bonus_units": int
//   }
//
// Parsing is defensive -- backend ships plan_config as JSONB
// (Record<string, unknown> on the wire) and we never trust the
// structure blindly. A malformed config returns null from
// parsePlanConfig; callers must guard.
// =============================================================================

import type { InstallmentResponse } from '@/api/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TrancheConfig {
  amount_cents: number
  units_percent: number
}

export interface PlanConfig {
  tranches: TrancheConfig[]
  bonus_units: number
  agent_bonus_units: number
}

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

/**
 * Parse `plan_config` JSONB into a typed PlanConfig.
 *
 * Returns null if:
 *   - tranches is missing / not an array / empty / < 2 entries
 *   - any tranche lacks numeric amount_cents / units_percent
 *
 * bonus_units / agent_bonus_units default to 0 if absent or malformed
 * (non-breaking: a plan with legit tranches but no bonus metadata is
 * still a valid plan to render).
 */
export function parsePlanConfig(
  cfg: Record<string, unknown>,
): PlanConfig | null {
  const rawTranches = cfg['tranches']
  if (!Array.isArray(rawTranches)) return null

  const tranches: TrancheConfig[] = []
  for (const t of rawTranches) {
    if (typeof t !== 'object' || t === null) return null
    const rec = t as Record<string, unknown>
    const amount = rec['amount_cents']
    const percent = rec['units_percent']
    if (typeof amount !== 'number' || typeof percent !== 'number') return null
    tranches.push({ amount_cents: amount, units_percent: percent })
  }
  if (tranches.length < 2) return null

  const bu = cfg['bonus_units']
  const abu = cfg['agent_bonus_units']
  return {
    tranches,
    bonus_units: typeof bu === 'number' ? bu : 0,
    agent_bonus_units: typeof abu === 'number' ? abu : 0,
  }
}

/**
 * Safe accessor for completion bonus_units on a plan template.
 * Used by ProductDetailView card chips and InstallmentView summary.
 * Returns 0 when plan_config is malformed or lacks the field.
 */
export function getPlanBonus(plan: InstallmentResponse): number {
  const cfg = parsePlanConfig(plan.plan_config)
  return cfg?.bonus_units ?? 0
}

// ---------------------------------------------------------------------------
// Tranche math
// ---------------------------------------------------------------------------

/**
 * Units unlocked by tranche `index` (0-based).
 *
 * Mirrors the backend scheduler:
 *   - non-last tranche: floor(total_units * units_percent / 100)
 *   - last tranche:     total_units - sum(previous)
 *
 * The floor + remainder split is how the backend prevents rounding
 * loss when decomposing a plan's total_units into integer tranche slices (see
 * backend/app/modules/products/constants.py::validate_plan_config --
 * the invariant `sum(units_unlocked) == product_units` holds by
 * construction there and must hold here too).
 *
 * TD-F11: once the backend exposes `/installments/preview` (or
 * similar) returning the materialised tranche list, the UI should
 * consume that instead of recomputing -- mirroring the scheduler
 * in two languages is a drift liability.
 */
export function getTrancheUnits(
  config: PlanConfig,
  totalUnits: number,
  index: number,
): number {
  const list = config.tranches
  if (index < 0 || index >= list.length) return 0

  if (index < list.length - 1) {
    return Math.floor((totalUnits * list[index].units_percent) / 100)
  }

  // Last tranche -- take whatever remains so the sum equals totalUnits.
  let consumed = 0
  for (let i = 0; i < list.length - 1; i += 1) {
    consumed += Math.floor((totalUnits * list[i].units_percent) / 100)
  }
  return totalUnits - consumed
}
