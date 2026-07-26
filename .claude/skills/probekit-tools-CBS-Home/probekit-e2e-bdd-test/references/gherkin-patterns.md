# Gherkin Patterns Reference

Authoritative rules for writing good Gherkin. Apply during generation and audit.

---

## Core Principle

Gherkin describes WHAT the system should do, not HOW it does it.
Scenarios survive implementation changes. Procedural scripts don't.

The test for good Gherkin: could a product manager write this scenario?
If it requires knowing CSS selectors, HTML structure, or implementation details → rewrite it.

---

## Keyword Reference

| Keyword | Purpose |
|---------|---------|
| Feature | One user-facing capability. One file per feature. |
| Scenario | One specific behavior or outcome. |
| Scenario Outline | Data-driven scenario with an Examples table. |
| Background | Steps repeated in every scenario of this feature. |
| Given | System state before the action. World setup. |
| When | The user action or system event being tested. |
| Then | Observable outcome. Must be verifiable. |
| And / But | Continuation of the previous keyword's intent. |
| @ | Tag for filtering and grouping. |

---

## Feature File Structure

```gherkin
@auth @smoke
Feature: User Authentication
  As a registered user
  I want to log in to my account
  So that I can access my personal data

  Background:
    Given the application is running
    And a registered user account exists

  Scenario: Successful login with valid credentials
    When I log in as a registered user
    Then I am on the dashboard
    And my username is displayed in the header

  Scenario: Login blocked for invalid password
    When I attempt to log in with a registered email and wrong password
    Then I see an error message about invalid credentials
    And I remain on the login page

  Scenario Outline: Login blocked for missing fields
    When I submit the login form with <field> left empty
    Then I see a validation error for <field>

    Examples:
      | field    |
      | email    |
      | password |
```

---

## Good vs Bad Gherkin

### Declarative (GOOD) vs Procedural (BAD)

BAD — procedural, UI-coupled:
```gherkin
When I click the element with id "email-input"
And I type "user@example.com"
And I click the element with id "password-input"
And I type "secret123"
And I click the button with class "btn-primary"
```

GOOD — declarative, behavior-focused:
```gherkin
When I log in as a registered user
```

---

### Parameterized (GOOD) vs Hardcoded Role (BAD)

BAD:
```gherkin
Given I am logged in
```

GOOD:
```gherkin
Given I am logged in as "admin"
Given I am logged in as an unauthenticated visitor
```

---

### Scenario Outline (GOOD) vs Copy-Paste (BAD)

BAD:
```gherkin
Scenario: Invalid email format
  When I register with email "notanemail"
  Then I see an email validation error

Scenario: Another invalid email
  When I register with email "also@notvalid"
  Then I see an email validation error
```

GOOD:
```gherkin
Scenario Outline: Invalid email format is rejected
  When I register with email "<email>"
  Then I see an email validation error

  Examples:
    | email         |
    | notanemail    |
    | @missing.com  |
    | user@         |
```

---

### Outcome-focused Then (GOOD) vs Action-focused Then (BAD)

BAD — Then describes a click, not an outcome:
```gherkin
Then I click the logout button
```

GOOD — Then describes the observable result:
```gherkin
Then I am logged out
And I am redirected to the login page
```

---

### Meaningful assertion (GOOD) vs Tautological Then (BAD)

BAD — not verifiable:
```gherkin
Then the page loads successfully
Then the request completes
```

GOOD — verifiable outcome:
```gherkin
Then I see the order confirmation with order number
Then the product count in my cart is 3
```

---

## Tag Strategy

```
@smoke        — critical path tests, run on every commit (keep under 5 minutes)
@regression   — full suite, run nightly or pre-release
@wip          — work in progress, excluded from CI until ready
@auth         — authentication/authorization scenarios
@api          — API-level scenarios (no UI)
@slow         — tests > 30s, exclude from quick feedback loops
```

Usage examples:
```
pytest -m smoke              # run smoke suite only (pytest-bdd uses -m markers)
behave --tags=regression     # run full regression
behave --tags=~wip           # exclude WIP scenarios
```

---

## File Naming Conventions

```
tests/e2e/
  features/
    auth.feature
    user_registration.feature
    product_checkout.feature
    admin_management.feature
  steps/
    auth_steps.py
    user_registration_steps.py
    product_checkout_steps.py
    admin_management_steps.py
  pages/                     ← Page Object Model
    login_page.py
    dashboard_page.py
    checkout_page.py
  conftest.py                ← shared fixtures
pytest.ini                   ← pytest-bdd config (project root, not inside tests/)
```

---

## Framework-Specific Notes

### pytest-bdd (Python)
```python
# conftest.py — shared fixtures
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()

@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()
```

```python
# Feature file link in test module
from pytest_bdd import scenarios, given, when, then
scenarios('../features/auth.feature')
```

### behave (Python)
```
features/
  auth.feature
  steps/
    auth_steps.py
  environment.py     ← before/after hooks
```

### Playwright + Cucumber (JS/TS)
```typescript
// support/world.ts
import { setWorldConstructor, World } from '@cucumber/cucumber';
import { Browser, Page } from 'playwright';

class CustomWorld extends World {
  browser!: Browser;
  page!: Page;
}
setWorldConstructor(CustomWorld);
```

### Godot / GUT (GDScript)
GUT does not use Gherkin natively.
Generate GUT test scripts with descriptive test method names that map to BDD intent:
```gdscript
# test_player_movement.gd
extends GutTest

func test_player_moves_right_when_right_key_pressed():
    # Given
    var player = Player.new()
    # When
    player._process_input(KEY_RIGHT)
    # Then
    assert_eq(player.position.x, player.SPEED * delta, "Player should move right")
```
For Godot, output .gd test files instead of .feature files.
Map Given/When/Then to comments inside GUT test methods.
