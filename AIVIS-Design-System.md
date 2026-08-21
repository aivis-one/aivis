# AIVIS.ONE — Design System Reference

> **GENERATED FILE — do not edit by hand.** Produced by
> `frontend/scripts/gen-design-system.mjs` from `frontend/src/components/ui/` and
> `frontend/src/styles/variables.css`. Regenerate with:
>
> ```
> npm --prefix frontend run docs:ds
> ```
>
> Any edit made here is lost on the next run. Change the SOURCE instead.

**Generated:** 2026-08-21 · **Components:** 18 · **Tokens:** 149 distinct (207 declarations, the extra ones being theme overrides)

**Audience: an agent working in this repository.** It answers three questions that otherwise cost a
full read of `components/ui/`: what exists, what each thing accepts, and **what does not exist at all**.

---

## 1. Components

| Component | Used by | Props | Variants |
|---|---:|---|---|
| `AivisLogo` | 9 | 2 | — |
| `CAppControls` | 8 | — | — |
| `CAvatar` | 5 | 1 | `c-avatar--initials` |
| `CBackLink` | 11 | 1 | — |
| `CBadge` | 12 | 2 | `c-badge--accent` `c-badge--danger` `c-badge--neutral` `c-badge--primary` `c-badge--success` `c-badge--warning` |
| `CBottomSheet` | 5 | 3 | — |
| `CButton` | 48 | 5 | `c-btn--accent` `c-btn--danger` `c-btn--inline` `c-btn--link` `c-btn--outline` `c-btn--primary` `c-btn--secondary` `c-btn--sm` `c-btn--telegram` |
| `CCheckbox` | 3 | 1 | — |
| `CEmptyState` | 44 | 1 | — |
| `CIconBox` | 1 | 1 | `c-icon-box--accent` `c-icon-box--danger` `c-icon-box--neutral` `c-icon-box--primary` `c-icon-box--success` `c-icon-box--warning` |
| `CInput` | 14 | 7 | `c-input--compact` `c-input--error` `c-input--reveal` |
| `CLoader` | 49 | 1 | — |
| `CModal` | 11 | 3 | — |
| `CProgressBar` | 1 | 1 | — |
| `CSelect` | 5 | 5 | `c-select--error` |
| `CStatCard` | 4 | 5 | `c-stat--interactive` |
| `CTextarea` | 5 | 7 | `c-textarea--compact` `c-textarea--error` `c-textarea--mono` |
| `CToast` | 5 | — | `c-toast--error` `c-toast--info` `c-toast--show` `c-toast--success` `c-toast--warning` |

**Every component has at least one caller.**

### `AivisLogo`

`frontend/src/components/ui/AivisLogo.vue`
> AIVIS.ONE logo — the real brand mark + the vector wordmark, configurable height.

| Prop | Type | Required | Default |
|---|---|---|---|
| `height` | `number` | no | `28` |
| `showText` | `boolean` | no | `true` |

**Used by 9 file(s)**

### `CAppControls`

`frontend/src/components/ui/CAppControls.vue`
> Language + theme control, for surfaces a signed-out visitor reaches.

**Props:** none.

**Used by 8 file(s)**: `components/layout/CHeader.vue`, `views/auth/LoginView.vue`, `views/auth/OnboardingDocsView.vue`, `views/auth/OnboardingKYCView.vue`, `views/auth/OnboardingProfileView.vue`, `views/auth/OnboardingRoleView.vue`, `views/auth/RegisterView.vue`, `views/auth/VerifyEmailView.vue`

### `CAvatar`

`frontend/src/components/ui/CAvatar.vue`
> Avatar — shows photo if url provided, otherwise initials from name.

| Prop | Type | Required | Default |
|---|---|---|---|
| `name` | `string; url?: string; size?: number` | no | — |

**Variant classes:** `.c-avatar--initials`
**Used by 5 file(s)**: `views/agent/AgentSettingsView.vue`, `views/investor/InvestorSettingsView.vue`, `views/staff/StaffAgentAppsView.vue`, `views/staff/StaffMoreView.vue`, `views/staff/StaffUsersView.vue`

### `CBackLink`

`frontend/src/components/ui/CBackLink.vue`
> =============================================================================

| Prop | Type | Required | Default |
|---|---|---|---|
| `label` | `string` | **yes** | — |

**Used by 11 file(s)**

### `CBadge`

`frontend/src/components/ui/CBadge.vue`
> Status badge. Variants from mockups/css/components.css.

| Prop | Type | Required | Default |
|---|---|---|---|
| `variant` | `'success' \| 'warning' \| 'danger' \| 'primary' \| 'accent' \| 'neutral'` | no | — |
| `text` | `string` | **yes** | — |

**Variant classes:** `.c-badge--accent` · `.c-badge--danger` · `.c-badge--neutral` · `.c-badge--primary` · `.c-badge--success` · `.c-badge--warning`
**Used by 12 file(s)**

### `CBottomSheet`

`frontend/src/components/ui/CBottomSheet.vue`
> =============================================================================

| Prop | Type | Required | Default |
|---|---|---|---|
| `open` | `boolean` | **yes** | — |
| `closeOnOverlay` | `boolean` | no | `true` |
| `title` | `string` | no | — |

**Slots:** default, `header`
**Used by 5 file(s)**: `components/shared/AgreementSheet.vue`, `components/shared/TransactionDetailSheet.vue`, `views/agent/AgentBalanceView.vue`, `views/agent/AgentSettingsView.vue`, `views/company/CompanyBalanceView.vue`

### `CButton`

`frontend/src/components/ui/CButton.vue`
> Universal button with variant styling from mockups/css/components.css.

| Prop | Type | Required | Default |
|---|---|---|---|
| `variant` | `'primary' \| 'accent' \| 'secondary' \| 'outline' \| 'danger' \| 'telegram' \| 'link'` | no | `'primary'` |
| `size` | `'default' \| 'sm'` | no | `'default'` |
| `disabled` | `boolean` | no | `false` |
| `loading` | `boolean` | no | `false` |
| `inline` | `boolean` | no | `false` |

**Slots:** default
**Variant classes:** `.c-btn--accent` · `.c-btn--danger` · `.c-btn--inline` · `.c-btn--link` · `.c-btn--outline` · `.c-btn--primary` · `.c-btn--secondary` · `.c-btn--sm` · `.c-btn--telegram`
**Used by 48 file(s)**

### `CCheckbox`

`frontend/src/components/ui/CCheckbox.vue`
> Checkbox with label. Mockup checkbox-row pattern.

| Prop | Type | Required | Default |
|---|---|---|---|
| `modelValue` | `boolean; label?: string` | no | `false` |

**Emits:** `update:modelValue: [value: boolean]`
**Used by 3 file(s)**: `components/staff/EventEditor.vue`, `components/staff/PostListEditor.vue`, `views/staff/StaffUsersView.vue`

### `CEmptyState`

`frontend/src/components/ui/CEmptyState.vue`
> Empty state placeholder with icon slot, title, and description.

| Prop | Type | Required | Default |
|---|---|---|---|
| `title` | `string; description?: string` | no | — |

**Slots:** `icon`
**Used by 44 file(s)**

### `CIconBox`

`frontend/src/components/ui/CIconBox.vue`
> Colored icon square. Wraps a slot (Lucide icon) in a tinted background square.

| Prop | Type | Required | Default |
|---|---|---|---|
| `variant` | `'primary' \| 'accent' \| 'success' \| 'warning' \| 'danger' \| 'neutral'` | no | — |

**Slots:** default
**Variant classes:** `.c-icon-box--accent` · `.c-icon-box--danger` · `.c-icon-box--neutral` · `.c-icon-box--primary` · `.c-icon-box--success` · `.c-icon-box--warning`
**Used by 1 file(s)**: `views/staff/StaffDashboardView.vue`

### `CInput`

`frontend/src/components/ui/CInput.vue`
> Text input with label, error state, and optional password toggle.

| Prop | Type | Required | Default |
|---|---|---|---|
| `modelValue` | `string` | no | `''` |
| `label` | `string` | no | — |
| `placeholder` | `string` | no | — |
| `error` | `string` | no | — |
| `type` | `string` | no | `'text'` |
| `autocomplete` | `string` | no | — |
| `size` | `'default' \| 'compact'` | no | `'default'` |

**Emits:** `update:modelValue: [value: string]`
**Variant classes:** `.c-input--compact` · `.c-input--error` · `.c-input--reveal`
**Used by 14 file(s)**

### `CLoader`

`frontend/src/components/ui/CLoader.vue`
> Spinner loader with configurable size.

| Prop | Type | Required | Default |
|---|---|---|---|
| `size` | `number` | no | `32` |

**Used by 49 file(s)**

### `CModal`

`frontend/src/components/ui/CModal.vue`
> Modal overlay. Closes on Escape, on overlay click (if allowed), or on the

| Prop | Type | Required | Default |
|---|---|---|---|
| `open` | `boolean` | **yes** | — |
| `closeOnOverlay` | `boolean` | no | `true` |
| `showClose` | `boolean` | no | `true` |

**Slots:** default
**Used by 11 file(s)**

### `CProgressBar`

`frontend/src/components/ui/CProgressBar.vue`
> Progress bar with configurable value, max, and color.

| Prop | Type | Required | Default |
|---|---|---|---|
| `value` | `number; max?: number; color?: string` | **yes** | — |

**Used by 1 file(s)**: `views/company/CompanyDashboardView.vue`

### `CSelect`

`frontend/src/components/ui/CSelect.vue`
> Dropdown select with label and error state. Custom arrow via CSS.

| Prop | Type | Required | Default |
|---|---|---|---|
| `modelValue` | `string` | no | `''` |
| `label` | `string` | no | — |
| `options` | `SelectOption[]` | **yes** | — |
| `placeholder` | `string` | no | — |
| `error` | `string` | no | — |

**Emits:** `update:modelValue: [value: string]`
**Variant classes:** `.c-select--error`
**Used by 5 file(s)**: `components/shared/AttachmentsSection.vue`, `components/shared/PublicAttachmentsSection.vue`, `components/staff/PostListEditor.vue`, `views/auth/OnboardingProfileView.vue`, `views/staff/platform/StaffCompanyRoadmapSection.vue`

### `CStatCard`

`frontend/src/components/ui/CStatCard.vue`
> Numeric stat card from mockup stats-grid pattern.

| Prop | Type | Required | Default |
|---|---|---|---|
| `value` | `string` | **yes** | — |
| `label` | `string` | **yes** | — |
| `sub` | `string` | no | — |
| `change` | `string` | no | — |
| `changeDir` | `'up' \| 'down'` | no | — |

**Slots:** `icon`
**Variant classes:** `.c-stat--interactive`
**Used by 4 file(s)**: `views/company/CompanyDashboardView.vue`, `views/investor/CompanyOverviewView.vue`, `views/public/PublicCompanyOverviewView.vue`, `views/staff/StaffDashboardView.vue`

### `CTextarea`

`frontend/src/components/ui/CTextarea.vue`
> Multi-line text input with label and error state.

| Prop | Type | Required | Default |
|---|---|---|---|
| `modelValue` | `string` | no | `''` |
| `label` | `string` | no | — |
| `placeholder` | `string` | no | — |
| `error` | `string` | no | — |
| `rows` | `number` | no | `4` |
| `size` | `'default' \| 'compact'` | no | `'default'` |
| `mono` | `boolean` | no | `false` |

**Emits:** `update:modelValue: [value: string]`
**Variant classes:** `.c-textarea--compact` · `.c-textarea--error` · `.c-textarea--mono`
**Used by 5 file(s)**: `components/staff/EventEditor.vue`, `components/staff/PostListEditor.vue`, `views/agent/AgentSettingsView.vue`, `views/company/CompanyBalanceView.vue`, `views/staff/platform/StaffCompanyRoadmapSection.vue`

### `CToast`

`frontend/src/components/ui/CToast.vue`
> Global toast notification. Place once in App.vue or shell.

**Props:** none.

**Variant classes:** `.c-toast--error` · `.c-toast--info` · `.c-toast--show` · `.c-toast--success` · `.c-toast--warning`
**Used by 5 file(s)**: `components/layout/AgentShell.vue`, `components/layout/CompanyShell.vue`, `components/layout/InvestorShell.vue`, `components/layout/PublicShell.vue`, `components/layout/StaffShell.vue`

---

## 2. Tokens

Values are as declared in the **light/base** block. A token marked **±theme** is declared more than
once, meaning a dark-theme or media-query block overrides it — resolve it at runtime, do not assume
the value below applies in every theme.

### --- primitives: theme-independent by design; never redefined below ---

| Token | Value | |
|---|---|---|
| `--amber-50` | `#FCF1E4` |  |
| `--amber-100` | `#F9D0AA` |  |
| `--amber-200` | `#F5AE6D` |  |
| `--amber-300` | `#F2913A` |  |
| `--amber-400` | `#D97B2E` |  |
| `--amber-500` | `#C66A25` |  |
| `--amber-600` | `#B1581B` |  |
| `--amber-700` | `#9A4410` |  |
| `--amber-800` | `#652C0A` |  |
| `--amber-900` | `#3A1905` |  |
| `--azure-50` | `#EAF4FC` |  |
| `--azure-100` | `#ADD9F5` |  |
| `--azure-200` | `#6DBDED` |  |
| `--azure-300` | `#37A6E6` |  |
| `--azure-400` | `#2B8ECB` |  |
| `--azure-500` | `#217AB6` |  |
| `--azure-600` | `#16669F` |  |
| `--azure-700` | `#0B4F86` |  |
| `--azure-800` | `#083B64` |  |
| `--azure-900` | `#062A48` |  |
| `--emerald-50` | `#E7F8EF` |  |
| `--emerald-100` | `#AAEBC9` |  |
| `--emerald-200` | `#6ADDA0` |  |
| `--emerald-300` | `#34D17E` |  |
| `--emerald-400` | `#29B56E` |  |
| `--emerald-500` | `#21A062` |  |
| `--emerald-600` | `#188854` |  |
| `--emerald-700` | `#0E6E45` |  |
| `--emerald-800` | `#0A4D30` |  |
| `--emerald-900` | `#06321F` |  |
| `--neutral-0` | `#FFFFFF` |  |
| `--neutral-50` | `#F6F8FA` |  |
| `--neutral-100` | `#EDF1F5` |  |
| `--neutral-200` | `#DDE4EB` |  |
| `--neutral-300` | `#C5D0DA` |  |
| `--neutral-400` | `#9BA8B6` |  |
| `--neutral-500` | `#6B7785` |  |
| `--neutral-600` | `#4C5763` |  |
| `--neutral-700` | `#353E48` |  |
| `--neutral-800` | `#1F262E` |  |
| `--neutral-900` | `#11161B` |  |
| `--neutral-950` | `#070A0E` |  |
| `--red-50` | `#FCEBEA` |  |
| `--red-100` | `#F6C7C4` |  |
| `--red-200` | `#EE9893` |  |
| `--red-300` | `#E5645D` |  |
| `--red-400` | `#D63E37` |  |
| `--red-500` | `#BE2D27` |  |
| `--red-600` | `#9C231E` |  |
| `--red-700` | `#7A1A16` |  |
| `--red-800` | `#561310` |  |
| `--red-900` | `#360B09` |  |

### --- semantics: light ---

| Token | Value | |
|---|---|---|
| `--bg-page` | `var(--neutral-50)` | ±theme |
| `--bg-surface` | `var(--neutral-0)` | ±theme |
| `--bg-subtle` | `var(--neutral-100)` | ±theme |
| `--text-primary` | `var(--neutral-900)` | ±theme |
| `--text-secondary` | `var(--neutral-600)` | ±theme |
| `--text-tertiary` | `#606A77` | ±theme |
| `--border-default` | `var(--neutral-300)` | ±theme |
| `--primary` | `var(--azure-700)` | ±theme |
| `--primary-hover` | `var(--azure-800)` | ±theme |
| `--primary-active` | `var(--azure-900)` | ±theme |
| `--primary-subtle` | `var(--azure-50)` | ±theme |
| `--accent` | `var(--amber-700)` | ±theme |
| `--accent-hover` | `var(--amber-800)` | ±theme |
| `--accent-subtle` | `var(--amber-50)` | ±theme |
| `--danger` | `var(--red-600)` | ±theme |
| `--danger-subtle` | `var(--red-50)` | ±theme |
| `--success` | `var(--emerald-700)` | ±theme |
| `--success-subtle` | `var(--emerald-50)` | ±theme |
| `--warning` | `var(--amber-600)` | ±theme |
| `--warning-subtle` | `var(--amber-50)` | ±theme |
| `--on-primary` | `#FFFFFF` | ±theme |
| `--on-danger` | `#FFFFFF` | ±theme |
| `--on-accent` | `#FFFFFF` | ±theme |
| `--on-success` | `#FFFFFF` | ±theme |
| `--shadow-1` | `0 1px 2px rgba(11,79,134,.06),0 1px 3px rgba(17,22,27,.05)` | ±theme |
| `--shadow-2` | `0 4px 8px rgba(11,79,134,.06),0 8px 24px rgba(17,22,27,.07)` | ±theme |
| `--shadow-3` | `0 12px 24px rgba(11,79,134,.08),0 24px 56px rgba(17,22,27,.12)` | ±theme |
| `--shadow-deep` | `0 2px 4px rgba(11,79,134,.06), 0 8px 16px rgba(11,79,134,.10), 0 24px 48px rgba(11,79,134,.14), 0 48px 96px rgba(17,22,27,.08)` | ±theme |
| `--shadow-focus` | `0 0 0 3px rgba(55,166,230,.4)` | ±theme |
| `--radius-sm` | `8px` |  |
| `--radius-md` | `12px` |  |
| `--radius-lg` | `16px` |  |
| `--radius-pill` | `999px` |  |
| `--space-1` | `0.25rem` |  |
| `--space-2` | `0.5rem` |  |
| `--space-3` | `0.75rem` |  |
| `--space-4` | `1rem` |  |
| `--space-5` | `1.5rem` |  |
| `--space-6` | `2rem` |  |
| `--space-7` | `3rem` |  |
| `--space-8` | `4rem` |  |
| `--space-9` | `6rem` |  |
| `--space-4-lg` | `1.25rem` |  |
| `--space-5-lg` | `1.75rem` |  |
| `--space-6-lg` | `2.5rem` |  |
| `--fs-display` | `clamp(2.8rem, 5vw, 4.2rem)` |  |
| `--fs-h1` | `clamp(2.2rem, 3.5vw, 3rem)` |  |
| `--fs-h2` | `clamp(1.75rem, 2.6vw, 2.2rem)` |  |
| `--fs-h3` | `1.5rem` |  |
| `--fs-h4` | `1.125rem` |  |
| `--fs-body-lg` | `1.0625rem` |  |
| `--fs-body` | `1rem` |  |
| `--fs-sm` | `0.875rem` |  |
| `--fs-xs` | `0.75rem` |  |
| `--fs-3xs` | `0.625rem` |  |
| `--fs-lg` | `1.25rem` |  |
| `--fs-xl` | `1.375rem` |  |
| `--fs-2xl` | `1.75rem` |  |
| `--fs-3xl` | `1.875rem` |  |
| `--fs-4xl` | `2rem` |  |
| `--fs-hero` | `4.5rem` |  |
| `--maxw` | `1080px` |  |
| `--maxw-wide` | `1240px` |  |
| `--maxw-prose` | `680px` |  |
| `--maxw-form` | `360px` |  |
| `--maxw-form-wide` | `400px` |  |
| `--tap-min` | `44px` |  |
| `--size-2xs` | `20px` |  |
| `--size-xs` | `24px` |  |
| `--size-sm` | `28px` |  |
| `--size-md` | `32px` |  |
| `--size-lg` | `36px` |  |
| `--size-xl` | `40px` |  |
| `--size-2xl` | `44px` |  |
| `--size-3xl` | `48px` |  |
| `--size-4xl` | `56px` |  |
| `--center-sm` | `120px` |  |
| `--center-md` | `200px` |  |
| `--center-lg` | `320px` |  |
| `--tile-min` | `150px` |  |
| `--tile-max` | `280px` |  |
| `--font-display` | `'Plus Jakarta Sans', 'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, sans-serif` |  |
| `--font-body` | `'Manrope', 'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, sans-serif` |  |
| `--font-mono` | `'JetBrains Mono', 'Noto Sans Arabic', ui-monospace, SFMono-Regular, Menlo, monospace` |  |
| `--radius` | `var(--radius-md)` |  |
| `--surface` | `var(--bg-surface)` |  |
| `--bg-secondary` | `var(--bg-subtle)` |  |
| `--primary-tint` | `var(--primary-subtle)` |  |
| `--primary-dim` | `var(--primary-subtle)` |  |
| `--shadow-accent-focus` | `var(--shadow-focus)` |  |

### PRODUCT-OWNED, and the design system is deliberately silent on all four

| Token | Value | |
|---|---|---|
| `--tab-bar-height` | `56px` |  |
| `--cta-bar-height` | `56px` |  |

### Telegram's own brand colours. Not ours to restyle.

| Token | Value | |
|---|---|---|
| `--telegram` | `#2AABEE` |  |
| `--telegram-dark` | `#229ED9` |  |
| `--on-telegram` | `#FFFFFF` |  |
| `--toggle-track` | `var(--neutral-500)` |  |
| `--toggle-knob` | `var(--neutral-0)` |  |
| `--bg-page` | `var(--neutral-950)` | ±theme |
| `--bg-surface` | `#10161D` | ±theme |
| `--bg-subtle` | `#161D26` | ±theme |
| `--text-primary` | `var(--neutral-50)` | ±theme |
| `--text-secondary` | `#A7B4C2` | ±theme |
| `--text-tertiary` | `#7C8A99` | ±theme |
| `--border-default` | `#2E3A46` | ±theme |
| `--primary` | `var(--azure-300)` | ±theme |
| `--primary-hover` | `var(--azure-200)` | ±theme |
| `--primary-active` | `var(--azure-100)` | ±theme |
| `--primary-subtle` | `rgba(55,166,230,.14)` | ±theme |
| `--accent` | `var(--amber-300)` | ±theme |
| `--accent-hover` | `var(--amber-200)` | ±theme |
| `--accent-subtle` | `rgba(242,145,58,.16)` | ±theme |
| `--danger` | `var(--red-300)` | ±theme |
| `--danger-subtle` | `rgba(214,62,55,.16)` | ±theme |
| `--success` | `var(--emerald-300)` | ±theme |
| `--success-subtle` | `rgba(52,209,126,.14)` | ±theme |
| `--warning` | `var(--amber-300)` | ±theme |
| `--warning-subtle` | `rgba(242,145,58,.16)` | ±theme |
| `--on-primary` | `#04243E` | ±theme |
| `--on-danger` | `#360B09` | ±theme |
| `--on-accent` | `#3A1905` | ±theme |
| `--on-success` | `#06321F` | ±theme |
| `--shadow-1` | `0 1px 2px rgba(0,0,0,.4)` | ±theme |
| `--shadow-2` | `0 6px 18px rgba(0,0,0,.45)` | ±theme |
| `--shadow-3` | `0 16px 40px rgba(0,0,0,.55)` | ±theme |
| `--shadow-deep` | `0 2px 4px rgba(0,0,0,.4), 0 8px 16px rgba(0,0,0,.5), 0 24px 48px rgba(0,0,0,.6), 0 48px 96px rgba(0,0,0,.3)` | ±theme |
| `--shadow-focus` | `0 0 0 3px rgba(55,166,230,.5)` | ±theme |

**⚠ DECLARED BUT REFERENCED BY NOTHING (33):** `--amber-100`, `--amber-400`, `--amber-500`, `--amber-900`, `--azure-400`, `--azure-500`, `--azure-600`, `--emerald-100`, `--emerald-200`, `--emerald-400`, `--emerald-500`, `--emerald-600`, `--emerald-800`, `--emerald-900`, `--fs-body-lg`, `--fs-display`, `--fs-h1`, `--fs-h2`, `--neutral-200`, `--neutral-400`, `--neutral-700`, `--neutral-800`, `--primary-tint`, `--red-100`, `--red-200`, `--red-400`, `--red-500`, `--red-700`, `--red-800`, `--red-900`, `--space-8`, `--space-9`, `--tile-min`

A token nothing uses is either a gap waiting to be filled or dead weight. `--font-mono` sat in this
state while twelve raw monospace stacks lived in the views, so the answer is not automatically
"delete it" — check whether something should have been using it.

---

## 3. What does NOT exist

**The expensive discovery is not which component to use — it is that there is none.** Every raw form
control still living outside the kit is listed below, derived from the templates.

| Site | Element |
|---|---|
| `views/auth/VerifyEmailView.vue` | `<input type="(text)">` |
| `views/staff/platform/StaffCompanyRoadmapSection.vue` | `<input type="file">` |

**WHY each one is still raw is NOT derivable from source and is therefore not asserted here.**
It is recorded in `BATCH-PLAN.md`. As of the last audit: a 6-box OTP control and a `display:none`
file picker, neither of which the kit has a component for.

**No component exists for:** a chip / segmented nav row · a navigation tile (icon + title +
description + chevron) · a file input · a multi-box OTP / code entry · a date or datetime picker
(`CInput` carries the native `type` through instead) · a table.
**Confirm against section 1 before concluding one is missing — this list is written, not derived,**
and is the one part of this document that can go stale.

---

## 4. Conventions that are not visible in the props

- **Attribute pass-through.** `CInput` and `CTextarea` set `inheritAttrs: false` and bind everything
  except `class`/`style` onto the CONTROL. `disabled`, `step`, `min`, `inputmode`, `readonly`,
  `spellcheck` and listeners reach the input; `class` and `style` stay on the group wrapper, so a
  consumer can still position the field. `CSelect` does NOT do this yet.
- **Label association.** `CInput`, `CSelect` and `CTextarea` pair label and control with `useId()`.
  Pass the `label` prop rather than rendering your own `<label>` — a visible caption is not an
  accessible name unless it is associated.
- **Field spacing.** Each field group carries `margin-bottom: var(--space-4)`. Inside a container that
  supplies its own rhythm (a flex column with a `gap`), zero it with a class on the component.
- **Scoped styles reach a child root.** A class passed to a component lands on its root element and
  the parent's scoped CSS applies to it.
