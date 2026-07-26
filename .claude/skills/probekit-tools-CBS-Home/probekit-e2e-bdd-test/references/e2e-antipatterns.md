# E2E Anti-Patterns and Flakiness Diagnosis

---

## Anti-Patterns Catalog

### AP-01 — Ice Cream Cone (CRITICAL)
Inverted test pyramid: more E2E tests than unit + integration combined.
E2E tests are slow, expensive, and flaky. They should cover user journeys only.
Every edge case in E2E should be a unit test instead.

Detection: count .feature files + test count vs unit test files.
Fix: move edge cases and validation logic to unit tests; keep E2E for full journeys only.

---

### AP-02 — Hardcoded Wait (WARNING)
```python
# BAD
time.sleep(3)
page.wait_for_timeout(3000)
asyncio.sleep(2)

# GOOD — pytest-bdd + Playwright
page.wait_for_selector('#result', state='visible')
expect(page.locator('#result')).to_be_visible()

# GOOD — behave + requests (API)
for _ in range(10):
    r = requests.get(url)
    if r.status_code == 200:
        break
    time.sleep(0.5)
else:
    raise AssertionError("Endpoint did not respond in time")
```

---

### AP-03 — Shared State Between Scenarios (WARNING)
Scenarios that depend on the order of execution or on data created by previous scenarios.
Each scenario must be independently runnable and produce the same result in isolation.

Detection: scenarios that reference "the user created in the previous test", or no cleanup after data creation.
Fix: use fixtures with proper teardown; create and destroy test data per scenario.

---

### AP-04 — UI Steps for Data Setup (WARNING)
Using the UI to seed test data (register a user through the registration form) instead of API/DB.
Doubles test duration and makes setup fragile.

```python
# BAD — setup via UI
@given("a user account exists")
def user_account_via_ui(page):
    page.goto("/register")
    page.fill("#email", "test@example.com")
    page.fill("#password", "password123")
    page.click("#submit")  # Now we wait for UI to respond

# GOOD — setup via API
@given("a user account exists")  
def user_account_via_api(api_client):
    api_client.post("/api/users", json={"email": "test@example.com", "password": "password123"})
```

---

### AP-05 — Brittle Selectors (WARNING)
Locators that break on any styling or structure change.

Fragility ranking (most to least brittle):
1. XPath absolute: `//div[2]/form/div[1]/input` — breaks on any DOM change
2. Generated CSS classes: `.css-a8f7d3` — breaks on any rebuild
3. Positional: `nth-child(3)` — breaks when element order changes
4. Static CSS class: `.btn-primary` — breaks on rename
5. Text content: `get_by_text("Submit")` — breaks on copy changes
6. Label: `get_by_label("Email")` — stable, recommended
7. ARIA role: `get_by_role("button", name="Submit")` — very stable
8. data-testid: `get_by_test_id("checkout-submit")` — most stable

Rule: prefer testid/role/label. Add data-testid attributes to key interactive elements.

---

### AP-06 — Assertions in Page Objects (WARNING)
POM methods that contain assertions break separation of concerns.
POM = interactions only. Step definitions = assertions.

```python
# BAD — assertion inside POM
class LoginPage:
    def login(self, email, password):
        self.page.fill("#email", email)
        self.page.fill("#password", password)
        self.page.click("#submit")
        assert self.page.url == "/dashboard"  # ← WRONG

# GOOD — assertion in step definition
class LoginPage:
    def login(self, email, password):
        self.page.fill("#email", email)
        self.page.fill("#password", password)
        self.page.click("#submit")

@then("I am on the dashboard")
def check_on_dashboard(page):
    expect(page).to_have_url("/dashboard")
```

---

### AP-07 — Missing Scenario Isolation (CRITICAL for parallel runs)
Module-level or global variables in step definitions used to share state between steps.

```python
# BAD — global state, breaks in parallel
current_user = None

@given("I am logged in")
def log_in():
    global current_user
    current_user = create_user()

# GOOD — pytest fixture or World object
@pytest.fixture
def logged_in_user():
    user = create_user()
    yield user
    delete_user(user.id)
```

---

### AP-08 — Testing Through the Wrong Layer (WARNING)
Business rule validation tested only through E2E.
If a business rule (email must be unique, price cannot be negative) is important enough to test,
it must be in unit tests AND optionally in E2E for the full flow.

---

### AP-09 — Tautological Gherkin (WARNING)
Steps where the step name IS the assertion, but the step definition does nothing verifiable.

```python
# BAD step definition for "Then the login succeeds"
@then("the login succeeds")
def login_succeeds():
    pass  # no actual assertion

# GOOD
@then("the login succeeds")
def login_succeeds(page):
    expect(page).to_have_url("/dashboard")
    expect(page.locator(".user-greeting")).to_be_visible()
```

---

## Flakiness Diagnosis

When a test fails intermittently, check in this order:

1. **Timing issue** — element not ready when accessed
   Symptom: passes when run slowly, fails in CI
   Fix: replace sleep with proper wait condition

2. **Shared state pollution** — previous test left dirty state
   Symptom: fails when run as part of suite, passes in isolation
   Fix: add teardown; make each scenario independent

3. **Environment dependency** — external service, network, time zone
   Symptom: fails in CI but passes locally; fails at specific times
   Fix: mock external dependencies; fix time zones in test config

4. **Race condition** — async operation not awaited
   Symptom: fails randomly at different steps
   Fix: await all async operations; use proper synchronization

5. **Test data conflict** — two parallel tests use same data
   Symptom: fails only in parallel runs
   Fix: use unique identifiers (UUID/timestamp) for test data

6. **Browser/driver state** — browser not fully reset between tests
   Symptom: first test passes, subsequent fail
   Fix: use fresh browser context per scenario (not per session)

7. **Real application bug** — the application is actually broken
   Symptom: consistent failure on a specific input or state
   Fix: document the bug; do NOT modify the test to hide it
