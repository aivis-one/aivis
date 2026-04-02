# Design: CBS HOME — Auth Flow

## Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| --primary | #1A6B6A | Main actions, links, teal brand |
| --primary-dark | #0E3D42 | Hover states, deep sections |
| --primary-light | #2A9B9A | Light teal accents |
| --accent | #E8651A | CTAs, badges, orange brand |
| --accent-dark | #D45A16 | Accent hover |
| --bg | #FFFFFF | Main background |
| --bg-subtle | #F5F5F5 | Subtle sections |
| --bg-elevated | #EEFAFA | Teal-tinted card bg |
| --text | #1A1A1A | Main text |
| --text-secondary | #525252 | Secondary text |
| --text-tertiary | #A3A3A3 | Hints, placeholders |
| --border | #D4D4D4 | Borders, dividers |
| --success | #22c55e | Approved, confirmed |
| --success-dim | rgba(34,197,94,0.15) | Success bg |
| --warning | #f59e0b | Pending states |
| --warning-dim | rgba(245,158,11,0.15) | Warning bg |
| --danger | #ef4444 | Rejected, errors |
| --danger-dim | rgba(239,68,68,0.1) | Error bg |

## Typography

| Element | Size | Weight | Font |
|---------|------|--------|------|
| H1 | 32px | 800 (Extrabold) | Montserrat |
| H2 | 24px | 700 (Bold) | Montserrat |
| H3 | 18px | 600 (Semibold) | Montserrat |
| Body | 16px | 400 (Regular) | Montserrat |
| Small | 14px | 500 (Medium) | Montserrat |
| Caption | 12px | 400 (Regular) | Montserrat |

Font stack: `'Montserrat', -apple-system, BlinkMacSystemFont, sans-serif`

## Spacing & Radius

| Token | Value |
|-------|-------|
| --spacing-xs | 4px |
| --spacing-sm | 8px |
| --spacing-md | 16px |
| --spacing-lg | 24px |
| --spacing-xl | 32px |
| --spacing-2xl | 48px |
| --radius-sm | 4px |
| --radius-md | 8px |
| --radius-lg | 12px |
| --radius-xl | 24px |

## Shadows

| Token | Value |
|-------|-------|
| --shadow-sm | 0 1px 3px rgba(0,0,0,0.08) |
| --shadow-md | 0 4px 12px rgba(0,0,0,0.10) |
| --shadow-lg | 0 8px 24px rgba(0,0,0,0.12) |
| --shadow-focus | 0 0 0 3px rgba(26,107,106,0.3) |
| --shadow-accent-focus | 0 0 0 3px rgba(232,101,26,0.4) |

## Interaction Map

| Screen | Element | Trigger | Action | Feedback |
|--------|---------|---------|--------|----------|
| Login | Email input | Focus | Border teal + shadow | Focus ring |
| Login | Password input | Focus | Border teal + shadow | Focus ring |
| Login | "Войти" btn | Click | Navigate → Role Selection | Toast "Вход выполнен" (success) |
| Login | "Создать аккаунт" link | Click | Navigate → Register | Screen transition |
| Login | "Telegram" btn | Click | Endpoint | Toast "📌 Telegram WebApp — внешний сервис" |
| Register | Form fields | Focus | Border teal | Focus ring |
| Register | "Создать аккаунт" btn | Click | Navigate → Email Verify | Toast "Аккаунт создан" (success) |
| Register | "Уже есть аккаунт?" link | Click | Navigate → Login | Screen transition |
| Email Verify | Code input | Focus | Border teal | Focus ring |
| Email Verify | "Подтвердить" btn | Click | Navigate → Profile | Toast "Email подтверждён" (success) |
| Email Verify | "Отправить повторно" link | Click | Stay | Toast "Код отправлен повторно" (info) |
| Profile | Form fields | Focus | Border teal | Focus ring |
| Profile | Country select | Click | Dropdown | — |
| Profile | "Продолжить" btn | Click | Navigate → Role Selection | Toast "Профиль сохранён" (success) |
| Role Selection | Role card | Click | Highlight card (selected state) | Card lift + border accent |
| Role Selection | Role card | Hover | Card lift + shadow | — |
| Role Selection | "Продолжить" btn | Click | Navigate → KYC | Toast "Роль выбрана: {role}" (success) |
| KYC | "Начать верификацию" btn | Click | Endpoint | Toast "📌 SumSub — внешний сервис верификации" |
| KYC | "Продолжить" btn (approved) | Click | Navigate → Docs | — |
| Docs | Checkbox | Click | Toggle check | — |
| Docs | "Подписать" btn | Click | Endpoint | Toast "Документы подписаны" (success) → Toast "📌 Onboarding завершён" |

## Components Used

| Component | Variants | Where |
|-----------|----------|-------|
| Button | primary (accent orange), secondary (outline teal), link | All screens |
| Form Input | text, email, password, code | Login, Register, Profile, Email Verify |
| Form Select | country, language | Profile |
| Card | role selection (icon + title + features) | Role Selection |
| Header | minimal (logo only, no nav) | All screens |
| Checkbox | document consent | Document Signing |
| Status Badge | pending (yellow), approved (green), rejected (red) | KYC |
| Toast | success, error, info, endpoint | All screens |
| Progress Steps | step indicator (1-7) | Top of auth flow |

## Brand Elements

- **Logo:** "CBS HOME" text with U-icon (orange square with white U)
- **Primary CTA:** Orange background (#E8651A), white text
- **Secondary CTA:** Teal outline (#1A6B6A)
- **Form accent:** Teal focus rings
- **Cards:** Clean borders, minimal radius (4-8px), rectangular feel
- **Progress bar:** Teal fill on gray track
