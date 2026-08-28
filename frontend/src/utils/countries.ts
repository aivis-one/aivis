// =============================================================================
// AIVIS.ONE Frontend -- Countries
// =============================================================================
//
// Single source of truth for the country picker used at profile setup
// (OnboardingProfileView) and self-service profile editing
// (InvestorSettingsView / AgentSettingsView, TASK-38 item 3). Previously
// this list lived only as a page-local const inside OnboardingProfileView
// with no export -- extracted here so the settings editors reuse the same
// options instead of hand-copying a second (and inevitably drifting) list.
//
// Values are stored as-is in profile.country (JSONB, free string per the
// backend's _ALLOWED_PROFILE_KEYS whitelist -- no server-side enum), so
// this list is a UI convenience, not a validation contract. Labels are
// intentionally NOT translated via i18n: they are place names, shown the
// same way regardless of active UI locale (matches the original onboarding
// behaviour this was extracted from).
// =============================================================================

export interface CountryOption {
  value: string
  label: string
}

export const COUNTRIES: CountryOption[] = [
  { value: 'DE', label: 'Deutschland' },
  { value: 'CH', label: 'Schweiz' },
  { value: 'AT', label: 'Österreich' },
  { value: 'RU', label: 'Россия' },
  { value: 'OTHER', label: 'Other' },
]

/** Label for a stored country code, or the raw code if unrecognized (e.g. legacy data). */
export function getCountryLabel(code: string): string {
  return COUNTRIES.find((c) => c.value === code)?.label ?? code
}
