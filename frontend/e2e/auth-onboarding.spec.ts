import { test, expect } from '@playwright/test'

test.describe('Auth → Onboarding flow', () => {
  test('redirects unauthenticated user to login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/auth\/login/)
  })

  test('shows onboarding after login', async ({ page: _page }) => {
    // Implement login helper when backend is available
    test.skip()
  })

  test('onboarding wizard shows steps', async ({ page: _page }) => {
    // Implement with authenticated session
    test.skip()
  })
})
