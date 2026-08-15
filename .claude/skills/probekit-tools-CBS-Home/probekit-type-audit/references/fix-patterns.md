# Fix Patterns — Auto-Fix Recipes

Concrete fix recipes for common TypeScript errors in Vue 3 + TS projects.
Each pattern includes detection, fix strategy, and verification.

## Pattern 1: Unknown Error Type (TS18046)

**Detection:** `catch (e)` followed by `e.message` or `e.property` without type guard
**Severity:** 🔴 CRITICAL

```ts
// BEFORE:
const error = await promise
expect(error.message).toBe('Failed')

// AFTER:
const error = await promise
expect((error as Error).message).toBe('Failed')
```

Alternative fix (preferred for production code):
```ts
// AFTER:
} catch (e: unknown) {
  if (e instanceof Error) {
    submitError.value = e.message
  }
}
```

**Rule:** In test files, `as Error` cast is acceptable. In production code, prefer `instanceof` guard.

## Pattern 2: Missing Global Type Declaration (TS2339)

**Detection:** `window.X?.Y` where Y is not in the declared interface
**Severity:** 🔴 CRITICAL

```ts
// BEFORE (telegram.ts):
interface Window {
  Telegram?: {
    WebApp: {
      ready(): void
      // initData is missing!
    }
  }
}

// AFTER:
interface Window {
  Telegram?: {
    WebApp: {
      ready(): void
      initData: string
      // ... other properties
    }
  }
}
```

**Rule:** Check Telegram WebApp SDK docs for all used properties. Add only properties actually used in code.

## Pattern 3: Template Scope Leak (TS2339 on Vue component)

**Detection:** Template uses `URL`, `window`, `document`, `console` etc. directly
**Severity:** 🔴 CRITICAL

```vue
<!-- BEFORE: -->
<img :src="URL.createObjectURL(file)" />

<!-- AFTER: -->
<img :src="createObjectURL(file)" />
```

```ts
// Add to <script setup>:
function createObjectURL(file: File): string {
  return URL.createObjectURL(file)
}
```

**Rule:** Never use browser globals directly in Vue templates. Wrap in setup functions.

## Pattern 4: Reactive Generic Constraint (TS2536)

**Detection:** `reactive<Partial<Record<keyof T, string>>>` then indexing with `keyof T`
**Severity:** 🟡 WARNING

```ts
// BEFORE:
const errors = reactive<Partial<Record<keyof T, string>>>({})
// errors[key as keyof T]  → TS2536

// AFTER:
const errors: Record<string, string> = reactive({})
// errors[key]  → works
```

**Rule:** For form error maps, `Record<string, string>` is sufficient. Over-constraining with `keyof T` creates indexing issues with `reactive()`.

## Pattern 5: Test Helper Generic Incompatibility (TS2345)

**Detection:** `mount(component, options)` where MountingOptions generic doesn't match
**Severity:** 🟡 WARNING

```ts
// BEFORE:
export function mountWithI18n<T extends Component>(
  component: T,
  options: MountingOptions<unknown> = {},
) {
  return mount(component, { ...options, global: { ... } })
}

// AFTER:
export function mountWithI18n(
  component: Component,
  options: Record<string, unknown> = {},
) {
  const global = (options.global ?? {}) as Record<string, unknown>
  const plugins = ((global.plugins ?? []) as any[])
  return mount(component as any, {
    ...options,
    global: { ...global, plugins: [...plugins, i18n] },
  } as any)
}
```

**Rule:** Test utilities can use `as any` — type safety of the test subject matters, not the test harness.

## Pattern 6: `as any` in Production Code

**Detection:** Regex `as any` in files outside `__tests__/` and `*.test.*`
**Severity:** 🟡 WARNING
**Auto-fixable:** ❌ No — requires understanding of intended type

**Guidance:** Flag for manual review. Suggest specific type alternatives when possible.

## Pattern 7: `@ts-ignore` Without Explanation

**Detection:** `@ts-ignore` or `@ts-expect-error` not followed by explanation comment
**Severity:** 🟡 WARNING
**Auto-fixable:** ❌ No — needs developer to explain why suppression is necessary

## Pattern 8: Excessive Non-Null Assertions

**Detection:** More than 5 `!.` or `![` per file
**Severity:** 🟡 WARNING
**Auto-fixable:** ❌ No — each assertion needs individual evaluation

**Guidance:** Suggest optional chaining (`?.`) or proper null checks.

## Pattern 9: Untyped API Responses

**Detection:** `api.get('/path')` or `api.post('/path', body)` without generic type parameter
**Severity:** 🟡 WARNING

```ts
// BEFORE:
const data = await api.get('/users/me')

// AFTER:
const data = await api.get<UserResponse>('/users/me')
```

**Rule:** All API calls should specify response type for compile-time safety.

## Pattern 10: Missing Vue Emit Types

**Detection:** `emit('event', payload)` where defineEmits doesn't declare the event
**Severity:** 🔴 CRITICAL

```ts
// BEFORE:
const emit = defineEmits(['update:modelValue'])

// AFTER:
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
```

**Rule:** Always use typed defineEmits with payload types.

## Fix Priority Order

1. 🔴 CRITICAL patterns first (1, 2, 3, 10)
2. 🟡 WARNING auto-fixable (4, 5)
3. 🟡 WARNING manual (6, 7, 8, 9) — report only
4. 🟢 SUGGESTION — report only, never auto-fix
