# AIVIS.ONE — Design System Reference

> **GENERATED FILE — do not edit by hand.** Produced by
> `frontend/scripts/gen-design-system.mjs` from `frontend/src/components/ui/` and
> `frontend/src/styles/ds/tokens.css`, `tokens-dark.css` and `variables.css`. Regenerate with:
>
> ```
> npm --prefix frontend run docs:ds
> ```
>
> Any edit made here is lost on the next run. Change the SOURCE instead.

**Generated:** 2026-10-23 · **Components:** 18 · **Tokens:** 256 distinct (378 declarations, the extra ones being theme overrides)

**Audience: an agent working in this repository.** It answers three questions that otherwise cost a
full read of `components/ui/`: what exists, what each thing accepts, and **what does not exist at all**.

---

## 1. Components

| Component | Used by | Props | Variants |
|---|---:|---|---|
| `AivisLogo` | 6 | 2 | — |
| `CAppControls` | 4 | — | — |
| `CAvatar` | 5 | 1 | `c-avatar--initials` |
| `CBackLink` | 21 | 1 | — |
| `CBadge` | 25 | 2 | — |
| `CBottomSheet` | 4 | 3 | — |
| `CButton` | 83 | 5 | — |
| `CCheckbox` | 9 | 1 | — |
| `CEmptyState` | 61 | 1 | — |
| `CIconBox` | 1 | 1 | `c-icon-box--accent` `c-icon-box--danger` `c-icon-box--neutral` `c-icon-box--primary` `c-icon-box--success` `c-icon-box--warning` |
| `CInput` | 31 | 7 | — |
| `CLoader` | 76 | 1 | — |
| `CModal` | 30 | 3 | — |
| `CProgressBar` | 0 | 1 | — |
| `CSelect` | 16 | 5 | — |
| `CStatCard` | 4 | 5 | `c-stat--interactive` |
| `CTextarea` | 13 | 7 | — |
| `CToast` | 5 | — | — |

**⚠ USED BY NOTHING: `CProgressBar`.** A component with no
callers accumulates defects unnoticed — `CCard` and `CDivider` both had, and both were deleted for it.

### `AivisLogo`

`frontend/src/components/ui/AivisLogo.vue`
> AIVIS.ONE logo — the real brand mark + the vector wordmark, configurable height.

| Prop | Type | Required | Default |
|---|---|---|---|
| `height` | `number` | no | `28` |
| `showText` | `boolean` | no | `true` |

**Used by 6 file(s)**: `components/layout/AuthShell.vue`, `components/layout/CHeader.vue`, `views/agent/AgentWelcomeView.vue`, `views/auth/LoadingView.vue`, `views/auth/RegisterView.vue`, `views/company/CompanyWelcomeView.vue`

### `CAppControls`

`frontend/src/components/ui/CAppControls.vue`
> Language + theme control, for surfaces a signed-out visitor reaches, on the

**Props:** none.

**Used by 4 file(s)**: `components/layout/AuthShell.vue`, `components/layout/CHeader.vue`, `views/agent/AgentWelcomeView.vue`, `views/company/CompanyWelcomeView.vue`

### `CAvatar`

`frontend/src/components/ui/CAvatar.vue`
> Avatar — shows photo if url provided, otherwise initials from name.

| Prop | Type | Required | Default |
|---|---|---|---|
| `name` | `string; url?: string; size?: number` | no | — |

**Variant classes:** `.c-avatar--initials`
**Used by 5 file(s)**: `components/staff/UserPicker.vue`, `views/investor/InvestorSettingsView.vue`, `views/staff/StaffAgentAppsView.vue`, `views/staff/StaffSettingsView.vue`, `views/staff/StaffUsersView.vue`

### `CBackLink`

`frontend/src/components/ui/CBackLink.vue`
> =============================================================================

| Prop | Type | Required | Default |
|---|---|---|---|
| `label` | `string` | **yes** | — |

**Used by 21 file(s)**

### `CBadge`

`frontend/src/components/ui/CBadge.vue`
> Status badge, on the design system's Badge (K08).

| Prop | Type | Required | Default |
|---|---|---|---|
| `variant` | `'success' \| 'warning' \| 'danger' \| 'primary' \| 'accent' \| 'neutral'` | no | — |
| `text` | `string` | **yes** | — |

**Used by 25 file(s)**

### `CBottomSheet`

`frontend/src/components/ui/CBottomSheet.vue`
> =============================================================================

| Prop | Type | Required | Default |
|---|---|---|---|
| `open` | `boolean` | **yes** | — |
| `closeOnOverlay` | `boolean` | no | `true` |
| `title` | `string` | no | — |

**Slots:** default, `header`
**Used by 4 file(s)**: `components/shared/AgreementSheet.vue`, `components/shared/TransactionDetailSheet.vue`, `views/agent/AgentBalanceView.vue`, `views/company/CompanyBalanceView.vue`

### `CButton`

`frontend/src/components/ui/CButton.vue`
> Universal button, on the design system's Button (K01).

| Prop | Type | Required | Default |
|---|---|---|---|
| `variant` | `'primary' \| 'accent' \| 'secondary' \| 'outline' \| 'danger' \| 'telegram' \| 'link'` | no | `'primary'` |
| `size` | `'default' \| 'sm'` | no | `'default'` |
| `disabled` | `boolean` | no | `false` |
| `loading` | `boolean` | no | `false` |
| `inline` | `boolean` | no | `false` |

**Slots:** default
**Used by 83 file(s)**

### `CCheckbox`

`frontend/src/components/ui/CCheckbox.vue`
> Checkbox with label.

| Prop | Type | Required | Default |
|---|---|---|---|
| `modelValue` | `boolean; label?: string` | no | `false` |

**Emits:** `update:modelValue: [value: boolean]`
**Used by 9 file(s)**

### `CEmptyState`

`frontend/src/components/ui/CEmptyState.vue`
> Empty state placeholder with icon slot, title, and description.

| Prop | Type | Required | Default |
|---|---|---|---|
| `title` | `string; description?: string` | no | — |

**Slots:** `icon`
**Used by 61 file(s)**

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
**Used by 31 file(s)**

### `CLoader`

`frontend/src/components/ui/CLoader.vue`
> Spinner loader, on the design system's Loader (K20). The system has two

| Prop | Type | Required | Default |
|---|---|---|---|
| `size` | `number` | no | `32` |

**Used by 76 file(s)**

### `CModal`

`frontend/src/components/ui/CModal.vue`
> Modal overlay. Closes on Escape, on overlay click (if allowed), or on the

| Prop | Type | Required | Default |
|---|---|---|---|
| `open` | `boolean` | **yes** | — |
| `closeOnOverlay` | `boolean` | no | `true` |
| `showClose` | `boolean` | no | `true` |

**Slots:** default
**Used by 30 file(s)**

### `CProgressBar`

`frontend/src/components/ui/CProgressBar.vue`
> Progress bar, on the design system's Progress (K18). The accessible name is

| Prop | Type | Required | Default |
|---|---|---|---|
| `value` | `number; max?: number; color?: string` | **yes** | — |

**Used by 0 file(s)**

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
**Used by 16 file(s)**

### `CStatCard`

`frontend/src/components/ui/CStatCard.vue`
> Numeric stat card.

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
**Used by 13 file(s)**

### `CToast`

`frontend/src/components/ui/CToast.vue`
> Global toast notification, on the design system's Toast (K16): a live region

**Props:** none.

**Used by 5 file(s)**: `components/layout/AgentShell.vue`, `components/layout/CompanyShell.vue`, `components/layout/InvestorShell.vue`, `components/layout/PublicShell.vue`, `components/layout/StaffShell.vue`

---

## 2. Tokens

Values are as declared in the **light/base** block. A token marked **±theme** is declared more than
once, meaning a dark-theme or media-query block overrides it — resolve it at runtime, do not assume
the value below applies in every theme.

### ---- Primitive ramps ----

| Token | Value | |
|---|---|---|
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

### ---- Colour roles ----

| Token | Value | |
|---|---|---|
| `--bg-page` | `var(--neutral-50)` | ±theme |
| `--bg-surface` | `var(--neutral-0)` | ±theme |
| `--bg-subtle` | `var(--neutral-100)` | ±theme |
| `--bg-inset` | `var(--neutral-50)` | ±theme |
| `--bg-emphasis` | `var(--neutral-900)` | ±theme |
| `--text-primary` | `var(--neutral-900)` | ±theme |
| `--text-secondary` | `var(--neutral-600)` | ±theme |
| `--text-tertiary` | `var(--neutral-500)` | ±theme |
| `--text-on-brand` | `#FFFFFF` | ±theme |
| `--text-inverse` | `var(--neutral-50)` | ±theme |
| `--border-subtle` | `var(--neutral-200)` | ±theme |
| `--border-default` | `var(--neutral-300)` | ±theme |
| `--border-strong` | `var(--neutral-400)` | ±theme |
| `--border-input` | `#7F97AE` | ±theme |
| `--border-input-hover` | `#6B7785` | ±theme |
| `--primary` | `var(--azure-700)` | ±theme |
| `--primary-hover` | `var(--azure-800)` | ±theme |
| `--primary-active` | `var(--azure-900)` | ±theme |
| `--primary-subtle` | `var(--azure-50)` | ±theme |
| `--primary-subtle-text` | `var(--azure-800)` | ±theme |
| `--on-primary` | `#FFFFFF` | ±theme |
| `--success` | `var(--emerald-700)` | ±theme |
| `--success-subtle` | `var(--emerald-50)` | ±theme |
| `--success-subtle-text` | `var(--emerald-800)` | ±theme |
| `--on-success` | `#FFFFFF` | ±theme |
| `--accent` | `var(--amber-600)` | ±theme |
| `--accent-hover` | `var(--amber-700)` | ±theme |
| `--accent-subtle` | `var(--amber-50)` | ±theme |
| `--accent-subtle-text` | `var(--amber-800)` | ±theme |
| `--on-accent` | `#FFFFFF` | ±theme |
| `--info` | `var(--azure-600)` | ±theme |
| `--info-subtle` | `var(--azure-50)` | ±theme |
| `--info-subtle-text` | `var(--azure-800)` | ±theme |
| `--on-info` | `#FFFFFF` | ±theme |
| `--warning` | `var(--amber-600)` | ±theme |
| `--warning-subtle` | `var(--amber-50)` | ±theme |
| `--warning-subtle-text` | `var(--amber-800)` | ±theme |
| `--on-warning` | `var(--on-accent)` | ±theme |
| `--danger` | `var(--red-600)` | ±theme |
| `--danger-hover` | `var(--red-700)` | ±theme |
| `--danger-subtle` | `var(--red-50)` | ±theme |
| `--danger-subtle-text` | `var(--red-800)` | ±theme |
| `--on-danger` | `#FFFFFF` | ±theme |
| `--focus-ring` | `var(--azure-500)` | ±theme |
| `--toggle-track` | `var(--neutral-500)` |  |
| `--toggle-knob` | `var(--neutral-0)` |  |
| `--paper` | `var(--neutral-0)` |  |
| `--scrim` | `color-mix(in srgb, var(--neutral-950) 50%, transparent)` |  |
| `--icon-primary` | `var(--neutral-900)` | ±theme |
| `--icon-secondary` | `var(--neutral-600)` | ±theme |
| `--icon-disabled` | `var(--neutral-400)` | ±theme |
| `--icon-brand` | `var(--azure-700)` | ±theme |
| `--telegram` | `#2AABEE` |  |
| `--telegram-hover` | `#229ED9` |  |
| `--on-telegram` | `#FFFFFF` |  |

### ---- Gradients, hex edges, depth, numerals ----

| Token | Value | |
|---|---|---|
| `--grad-azure` | `linear-gradient(135deg,var(--azure-300),var(--azure-700))` |  |
| `--grad-emerald` | `linear-gradient(135deg,var(--emerald-300),var(--emerald-700))` |  |
| `--grad-amber` | `linear-gradient(135deg,var(--amber-300),var(--amber-700))` |  |
| `--grad-brand` | `linear-gradient(120deg,var(--azure-600),var(--emerald-600) 55%,var(--amber-500))` |  |
| `--hex-azure-face` | `var(--azure-300)` |  |
| `--hex-azure-edge` | `var(--azure-700)` |  |
| `--hex-emerald-face` | `var(--emerald-300)` |  |
| `--hex-emerald-edge` | `var(--emerald-700)` |  |
| `--hex-amber-face` | `var(--amber-300)` |  |
| `--hex-amber-edge` | `var(--amber-700)` |  |
| `--hex-neutral-face` | `var(--neutral-100)` | ±theme |
| `--hex-neutral-edge` | `var(--neutral-300)` | ±theme |
| `--connector-stroke` | `var(--border-default)` | ±theme |
| `--connector-width` | `1.5px` |  |
| `--numeral-display` | `clamp(2.6rem, 4.2vw, 3.8rem)` |  |
| `--numeral-mega` | `clamp(4rem, 7vw, 6rem)` |  |

### ---- Elevation ----

| Token | Value | |
|---|---|---|
| `--shadow-1` | `0 1px 2px rgba(11,79,134,.06), 0 1px 3px rgba(17,22,27,.05)` | ±theme |
| `--shadow-2` | `0 4px 8px rgba(11,79,134,.06), 0 8px 24px rgba(17,22,27,.07)` | ±theme |
| `--shadow-3` | `0 12px 24px rgba(11,79,134,.08), 0 24px 56px rgba(17,22,27,.12)` | ±theme |
| `--shadow-deep` | `0 2px 4px rgba(11,79,134,.06), 0 8px 16px rgba(11,79,134,.10), 0 24px 48px rgba(11,79,134,.14), 0 48px 96px rgba(17,22,27,.08)` | ±theme |
| `--shadow-inset-hex` | `inset 0 1px 0 rgba(255,255,255,.18), inset 0 -2px 6px rgba(0,0,0,.08)` | ±theme |
| `--shadow-focus` | `0 0 0 3px color-mix(in srgb, var(--azure-500) 45%, transparent)` | ±theme |

### ---- Typography ----

| Token | Value | |
|---|---|---|
| `--font-display` | `'Commissioner', 'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` |  |
| `--font-body` | `'Inter', 'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` |  |
| `--font-mono` | `'JetBrains Mono', 'Noto Sans Arabic', ui-monospace, SFMono-Regular, Menlo, monospace` |  |
| `--fs-3xs` | `0.625rem` |  |
| `--fs-xs` | `0.75rem` |  |
| `--fs-sm` | `0.875rem` |  |
| `--fs-body` | `1rem` |  |
| `--fs-body-lg` | `1.0625rem` |  |
| `--fs-h4` | `1.125rem` |  |
| `--fs-lg` | `1.25rem` |  |
| `--fs-xl` | `1.375rem` |  |
| `--fs-h3` | `1.5rem` |  |
| `--fs-2xl` | `1.75rem` |  |
| `--fs-3xl` | `1.875rem` |  |
| `--fs-4xl` | `2rem` |  |
| `--fs-h2` | `clamp(1.75rem, 2.6vw, 2.2rem)` |  |
| `--fs-h1` | `clamp(2.2rem, 3.5vw, 3rem)` |  |
| `--fs-display` | `clamp(2.8rem, 5vw, 4.2rem)` |  |
| `--fs-hero` | `4.5rem` |  |
| `--lh-tight` | `1.1` |  |
| `--lh-snug` | `1.35` |  |
| `--lh-normal` | `1.6` |  |
| `--tracking-tighter` | `-0.04em` |  |
| `--tracking-tight` | `-0.02em` |  |
| `--tracking-normal` | `0em` |  |
| `--tracking-wide` | `0.04em` |  |
| `--tracking-mega` | `0.08em` |  |

### ---- Spacing ----

| Token | Value | |
|---|---|---|
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
| `--space-component-sm` | `0.5rem` |  |
| `--space-component-md` | `0.75rem` |  |
| `--space-component-lg` | `1rem` |  |
| `--space-section-sm` | `2rem` |  |
| `--space-section-md` | `3rem` |  |
| `--space-section-lg` | `4rem` |  |
| `--space-gutter-web` | `1.5rem` |  |
| `--space-gutter-mobile` | `1rem` |  |
| `--space-safe-top` | `env(safe-area-inset-top, 0px)` |  |
| `--space-safe-right` | `env(safe-area-inset-right, 0px)` |  |
| `--space-safe-bottom` | `env(safe-area-inset-bottom, 0px)` |  |
| `--space-safe-left` | `env(safe-area-inset-left, 0px)` |  |

### ---- Radius ----

| Token | Value | |
|---|---|---|
| `--radius-xs` | `4px` |  |
| `--radius-sm` | `8px` |  |
| `--radius-md` | `12px` |  |
| `--radius-lg` | `16px` |  |
| `--radius-xl` | `24px` |  |
| `--radius-pill` | `999px` |  |
| `--radius-control` | `8px` |  |
| `--radius-card` | `12px` |  |
| `--radius-modal` | `16px` |  |

### ---- Motion ----

| Token | Value | |
|---|---|---|
| `--dur-instant` | `80ms` |  |
| `--dur-fast` | `140ms` |  |
| `--dur-base` | `220ms` |  |
| `--dur-slow` | `360ms` |  |
| `--dur-slower` | `560ms` |  |
| `--ease-standard` | `cubic-bezier(.2,.0,.2,1)` |  |
| `--ease-entrance` | `cubic-bezier(.16,.84,.44,1)` |  |
| `--ease-exit` | `cubic-bezier(.4,.0,1,1)` |  |
| `--ease-spring` | `cubic-bezier(.34,1.56,.64,1)` |  |
| `--motion-micro` | `80ms cubic-bezier(.2,.0,.2,1)` |  |
| `--motion-quick` | `140ms cubic-bezier(.2,.0,.2,1)` |  |
| `--motion-moderate` | `220ms cubic-bezier(.16,.84,.44,1)` |  |
| `--motion-deliberate` | `360ms cubic-bezier(.16,.84,.44,1)` |  |
| `--motion-ambient` | `560ms cubic-bezier(.2,.0,.2,1)` |  |

### ---- Widths and breakpoints ----

| Token | Value | |
|---|---|---|
| `--bp-sm` | `480px` |  |
| `--bp-md` | `640px` |  |
| `--bp-lg` | `880px` |  |
| `--bp-xl` | `1120px` |  |
| `--maxw` | `1080px` |  |
| `--maxw-wide` | `1240px` |  |
| `--maxw-prose` | `680px` |  |
| `--maxw-form` | `360px` |  |
| `--maxw-form-wide` | `400px` |  |
| `--header-height` | `64px` |  |

### ---- Sizes, touch and icons ----

| Token | Value | |
|---|---|---|
| `--touch-min` | `44px` |  |
| `--touch-comfortable` | `48px` |  |
| `--tap-min` | `var(--touch-min)` |  |
| `--control-height-sm` | `32px` |  |
| `--control-height-md` | `38px` |  |
| `--control-height-lg` | `44px` |  |
| `--size-2xs` | `20px` |  |
| `--size-xs` | `24px` |  |
| `--size-sm` | `28px` |  |
| `--size-md` | `32px` |  |
| `--size-lg` | `36px` |  |
| `--size-xl` | `40px` |  |
| `--size-2xl` | `44px` |  |
| `--size-3xl` | `48px` |  |
| `--size-4xl` | `56px` |  |
| `--tile-min` | `150px` |  |
| `--tile-max` | `280px` |  |
| `--center-sm` | `120px` |  |
| `--center-md` | `200px` |  |
| `--center-lg` | `320px` |  |
| `--icon-size-sm` | `16px` |  |
| `--icon-size-md` | `24px` |  |
| `--icon-size-lg` | `32px` |  |
| `--icon-size-xl` | `48px` |  |

### ---- Focus and input border ----

| Token | Value | |
|---|---|---|
| `--focus-width` | `2px` |  |
| `--focus-offset` | `2px` |  |
| `--border-input-width` | `1px` |  |

### ---- Decoration ----

| Token | Value | |
|---|---|---|
| `--deco-ink` | `var(--neutral-500)` | ±theme |
| `--deco-opacity` | `0.33` | ±theme |
| `--deco-line-width` | `1px` | ±theme |
| `--deco-mark-line-width` | `1.09px` | ±theme |
| `--deco-divider-width` | `1px` |  |
| `--tick-length` | `88px` |  |
| `--tick-thickness` | `3px` |  |
| `--tick-cut` | `5.2px` |  |
| `--tick-azure-start` | `var(--azure-300)` |  |
| `--tick-azure-end` | `var(--azure-700)` |  |
| `--tick-emerald-start` | `var(--emerald-300)` |  |
| `--tick-emerald-end` | `var(--emerald-700)` |  |
| `--tick-amber-start` | `var(--amber-300)` |  |
| `--tick-amber-end` | `var(--amber-700)` |  |

### ---- Colour roles ----

| Token | Value | |
|---|---|---|
| `--bg-page` | `var(--neutral-950)` | ±theme |
| `--bg-surface` | `#10161D` | ±theme |
| `--bg-subtle` | `#161D26` | ±theme |
| `--bg-inset` | `#0C1218` | ±theme |
| `--bg-emphasis` | `var(--neutral-50)` | ±theme |
| `--text-primary` | `var(--neutral-50)` | ±theme |
| `--text-secondary` | `#A7B4C2` | ±theme |
| `--text-tertiary` | `#7C8A99` | ±theme |
| `--text-on-brand` | `var(--on-primary)` | ±theme |
| `--text-inverse` | `var(--neutral-900)` | ±theme |
| `--border-subtle` | `#222B35` | ±theme |
| `--border-default` | `#2E3A46` | ±theme |
| `--border-strong` | `#41505E` | ±theme |
| `--border-input` | `#506579` | ±theme |
| `--border-input-hover` | `#9BA8B6` | ±theme |
| `--primary` | `var(--azure-300)` | ±theme |
| `--primary-hover` | `var(--azure-200)` | ±theme |
| `--primary-active` | `var(--azure-100)` | ±theme |
| `--primary-subtle` | `rgba(55,166,230,.14)` | ±theme |
| `--primary-subtle-text` | `var(--azure-200)` | ±theme |
| `--on-primary` | `#04243E` | ±theme |
| `--success` | `var(--emerald-300)` | ±theme |
| `--success-subtle` | `rgba(52,209,126,.14)` | ±theme |
| `--success-subtle-text` | `var(--emerald-200)` | ±theme |
| `--on-success` | `#06321F` | ±theme |
| `--accent` | `var(--amber-300)` | ±theme |
| `--accent-hover` | `var(--amber-200)` | ±theme |
| `--accent-subtle` | `rgba(242,145,58,.16)` | ±theme |
| `--accent-subtle-text` | `var(--amber-200)` | ±theme |
| `--on-accent` | `#3A1905` | ±theme |
| `--info` | `var(--azure-300)` | ±theme |
| `--info-subtle` | `rgba(55,166,230,.14)` | ±theme |
| `--info-subtle-text` | `var(--azure-200)` | ±theme |
| `--on-info` | `#04243E` | ±theme |
| `--warning` | `var(--amber-300)` | ±theme |
| `--warning-subtle` | `rgba(242,145,58,.16)` | ±theme |
| `--warning-subtle-text` | `var(--amber-200)` | ±theme |
| `--on-warning` | `var(--on-accent)` | ±theme |
| `--danger` | `var(--red-300)` | ±theme |
| `--danger-hover` | `var(--red-200)` | ±theme |
| `--danger-subtle` | `rgba(214,62,55,.16)` | ±theme |
| `--danger-subtle-text` | `var(--red-200)` | ±theme |
| `--on-danger` | `#360B09` | ±theme |
| `--focus-ring` | `var(--azure-300)` | ±theme |
| `--icon-primary` | `var(--neutral-50)` | ±theme |
| `--icon-secondary` | `var(--text-secondary)` | ±theme |
| `--icon-disabled` | `var(--border-strong)` | ±theme |
| `--icon-brand` | `var(--azure-300)` | ±theme |

### ---- Gradients, hex edges, depth, numerals ----

| Token | Value | |
|---|---|---|
| `--hex-neutral-face` | `var(--neutral-800)` | ±theme |
| `--hex-neutral-edge` | `var(--neutral-900)` | ±theme |
| `--connector-stroke` | `var(--border-default)` | ±theme |

### ---- Elevation ----

| Token | Value | |
|---|---|---|
| `--shadow-1` | `0 1px 2px rgba(0,0,0,.4)` | ±theme |
| `--shadow-2` | `0 6px 18px rgba(0,0,0,.45)` | ±theme |
| `--shadow-3` | `0 16px 40px rgba(0,0,0,.55)` | ±theme |
| `--shadow-deep` | `0 2px 4px rgba(0,0,0,.4), 0 8px 16px rgba(0,0,0,.5), 0 24px 48px rgba(0,0,0,.6), 0 48px 96px rgba(0,0,0,.3)` | ±theme |
| `--shadow-inset-hex` | `inset 0 1px 0 rgba(255,255,255,.06), inset 0 -2px 6px rgba(0,0,0,.4)` | ±theme |
| `--shadow-focus` | `0 0 0 3px rgba(55,166,230,.5)` | ±theme |

### ---- Decoration ----

| Token | Value | |
|---|---|---|
| `--deco-ink` | `var(--text-secondary)` | ±theme |
| `--deco-opacity` | `0.29` | ±theme |
| `--deco-line-width` | `1.5px` | ±theme |
| `--deco-mark-line-width` | `1.63px` | ±theme |

### ---- Colour roles ----

| Token | Value | |
|---|---|---|
| `--bg-page` | `var(--neutral-950)` | ±theme |
| `--bg-surface` | `#10161D` | ±theme |
| `--bg-subtle` | `#161D26` | ±theme |
| `--bg-inset` | `#0C1218` | ±theme |
| `--bg-emphasis` | `var(--neutral-50)` | ±theme |
| `--text-primary` | `var(--neutral-50)` | ±theme |
| `--text-secondary` | `#A7B4C2` | ±theme |
| `--text-tertiary` | `#7C8A99` | ±theme |
| `--text-on-brand` | `var(--on-primary)` | ±theme |
| `--text-inverse` | `var(--neutral-900)` | ±theme |
| `--border-subtle` | `#222B35` | ±theme |
| `--border-default` | `#2E3A46` | ±theme |
| `--border-strong` | `#41505E` | ±theme |
| `--border-input` | `#506579` | ±theme |
| `--border-input-hover` | `#9BA8B6` | ±theme |
| `--primary` | `var(--azure-300)` | ±theme |
| `--primary-hover` | `var(--azure-200)` | ±theme |
| `--primary-active` | `var(--azure-100)` | ±theme |
| `--primary-subtle` | `rgba(55,166,230,.14)` | ±theme |
| `--primary-subtle-text` | `var(--azure-200)` | ±theme |
| `--on-primary` | `#04243E` | ±theme |
| `--success` | `var(--emerald-300)` | ±theme |
| `--success-subtle` | `rgba(52,209,126,.14)` | ±theme |
| `--success-subtle-text` | `var(--emerald-200)` | ±theme |
| `--on-success` | `#06321F` | ±theme |
| `--accent` | `var(--amber-300)` | ±theme |
| `--accent-hover` | `var(--amber-200)` | ±theme |
| `--accent-subtle` | `rgba(242,145,58,.16)` | ±theme |
| `--accent-subtle-text` | `var(--amber-200)` | ±theme |
| `--on-accent` | `#3A1905` | ±theme |
| `--info` | `var(--azure-300)` | ±theme |
| `--info-subtle` | `rgba(55,166,230,.14)` | ±theme |
| `--info-subtle-text` | `var(--azure-200)` | ±theme |
| `--on-info` | `#04243E` | ±theme |
| `--warning` | `var(--amber-300)` | ±theme |
| `--warning-subtle` | `rgba(242,145,58,.16)` | ±theme |
| `--warning-subtle-text` | `var(--amber-200)` | ±theme |
| `--on-warning` | `var(--on-accent)` | ±theme |
| `--danger` | `var(--red-300)` | ±theme |
| `--danger-hover` | `var(--red-200)` | ±theme |
| `--danger-subtle` | `rgba(214,62,55,.16)` | ±theme |
| `--danger-subtle-text` | `var(--red-200)` | ±theme |
| `--on-danger` | `#360B09` | ±theme |
| `--focus-ring` | `var(--azure-300)` | ±theme |
| `--icon-primary` | `var(--neutral-50)` | ±theme |
| `--icon-secondary` | `var(--text-secondary)` | ±theme |
| `--icon-disabled` | `var(--border-strong)` | ±theme |
| `--icon-brand` | `var(--azure-300)` | ±theme |

### ---- Gradients, hex edges, depth, numerals ----

| Token | Value | |
|---|---|---|
| `--hex-neutral-face` | `var(--neutral-800)` | ±theme |
| `--hex-neutral-edge` | `var(--neutral-900)` | ±theme |
| `--connector-stroke` | `var(--border-default)` | ±theme |

### ---- Elevation ----

| Token | Value | |
|---|---|---|
| `--shadow-1` | `0 1px 2px rgba(0,0,0,.4)` | ±theme |
| `--shadow-2` | `0 6px 18px rgba(0,0,0,.45)` | ±theme |
| `--shadow-3` | `0 16px 40px rgba(0,0,0,.55)` | ±theme |
| `--shadow-deep` | `0 2px 4px rgba(0,0,0,.4), 0 8px 16px rgba(0,0,0,.5), 0 24px 48px rgba(0,0,0,.6), 0 48px 96px rgba(0,0,0,.3)` | ±theme |
| `--shadow-inset-hex` | `inset 0 1px 0 rgba(255,255,255,.06), inset 0 -2px 6px rgba(0,0,0,.4)` | ±theme |
| `--shadow-focus` | `0 0 0 3px rgba(55,166,230,.5)` | ±theme |

### ---- Decoration ----

| Token | Value | |
|---|---|---|
| `--deco-ink` | `var(--text-secondary)` | ±theme |
| `--deco-opacity` | `0.29` | ±theme |
| `--deco-line-width` | `1.5px` | ±theme |
| `--deco-mark-line-width` | `1.63px` | ±theme |
| `--tab-bar-height` | `calc(var(--size-4xl) + var(--space-2) + var(--border-input-width))` |  |
| `--cta-bar-height` | `var(--size-4xl)` |  |

**⚠ DECLARED BUT REFERENCED BY NOTHING (78):** `--accent-subtle-text`, `--amber-100`, `--amber-400`, `--amber-900`, `--azure-400`, `--bp-lg`, `--bp-md`, `--bp-sm`, `--bp-xl`, `--connector-stroke`, `--connector-width`, `--deco-divider-width`, `--deco-ink`, `--deco-line-width`, `--deco-mark-line-width`, `--deco-opacity`, `--dur-slow`, `--ease-spring`, `--emerald-100`, `--emerald-400`, `--emerald-500`, `--emerald-900`, `--fs-body-lg`, `--fs-display`, `--fs-h1`, `--fs-h2`, `--grad-amber`, `--grad-azure`, `--grad-brand`, `--grad-emerald`, `--hex-amber-edge`, `--hex-amber-face`, `--hex-azure-edge`, `--hex-azure-face`, `--hex-emerald-edge`, `--hex-emerald-face`, `--hex-neutral-edge`, `--hex-neutral-face`, `--icon-brand`, `--icon-disabled`, `--icon-primary`, `--icon-size-lg`, `--motion-ambient`, `--motion-deliberate`, `--motion-micro`, `--motion-moderate`, `--motion-quick`, `--neutral-700`, `--numeral-display`, `--numeral-mega`, `--radius-xl`, `--red-100`, `--red-400`, `--red-500`, `--red-900`, `--shadow-focus`, `--space-5-lg`, `--space-8`, `--space-9`, `--space-component-lg`, `--space-component-sm`, `--space-section-lg`, `--space-section-md`, `--space-section-sm`, `--text-on-brand`, `--tick-amber-end`, `--tick-amber-start`, `--tick-azure-end`, `--tick-azure-start`, `--tick-cut`, `--tick-emerald-end`, `--tick-emerald-start`, `--tick-length`, `--tick-thickness`, `--tile-min`, `--tracking-mega`, `--tracking-normal`, `--tracking-tighter`

A token nothing uses is either a gap waiting to be filled or dead weight. `--font-mono` sat in this
state while twelve raw monospace stacks lived in the views, so the answer is not automatically
"delete it" — check whether something should have been using it.

---

## 3. What does NOT exist

**The expensive discovery is not which component to use — it is that there is none.** Every raw form
control still living outside the kit is listed below, derived from the templates.

| Site | Element |
|---|---|
| `components/shared/NotificationPreferencesSection.vue` | `<input type="checkbox">` |
| `components/shared/PurchaseTerms.vue` | `<input type="checkbox">` |
| `components/staff/AttachmentFormModal.vue` | `<input type="file">` |
| `components/staff/AttachmentFormModal.vue` | `<input type="file">` |
| `views/auth/KYCVerificationView.vue` | `<select type="(text)">` |
| `views/auth/KYCVerificationView.vue` | `<input type="file">` |
| `views/auth/KYCVerificationView.vue` | `<input type="file">` |
| `views/auth/KYCVerificationView.vue` | `<input type="file">` |
| `views/auth/RegisterView.vue` | `<input type="checkbox">` |
| `views/auth/RegisterView.vue` | `<input type="checkbox">` |
| `views/auth/VerifyEmailView.vue` | `<input type="(text)">` |
| `views/company/CompanyAnalyticsView.vue` | `<input type="radio">` |
| `views/company/CompanyAttachmentsView.vue` | `<input type="file">` |
| `views/company/CompanyAttachmentsView.vue` | `<input type="file">` |
| `views/company/CompanyRoadmapView.vue` | `<input type="radio">` |
| `views/company/CompanyRoadmapView.vue` | `<input type="file">` |
| `views/investor/InvestorSettingsView.vue` | `<input type="radio">` |
| `views/staff/platform/StaffCompanyRoadmapSection.vue` | `<input type="radio">` |
| `views/staff/platform/StaffCompanyRoadmapSection.vue` | `<input type="file">` |
| `views/staff/platform/StaffVerificationSettingsSection.vue` | `<input type="radio">` |
| `views/staff/platform/StaffVerificationSettingsSection.vue` | `<input type="radio">` |

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
