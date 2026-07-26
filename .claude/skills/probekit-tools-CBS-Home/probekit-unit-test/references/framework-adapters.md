# Framework Adapters

Language and framework-specific patterns. Read the section matching the detected framework.

---

## Python — pytest

**Detection signals:** `pytest.ini`, `pyproject.toml [tool.pytest.ini_options]`, `conftest.py`,
`pytest` in `requirements*.txt` or `pyproject.toml [project.dependencies]`

**Run command:**
```
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=term-missing
pytest tests/test_specific.py::TestClass::test_method -v
```

**PowerShell note (Windows):** Use single quotes for `-k` patterns:
`pytest -k 'test_name'` — double quotes break pattern matching.

**Required packages:**
- `pytest` — core
- `pytest-cov` — coverage
- `pytest-asyncio` — async tests
- `pytest-mock` — mocker fixture (optional, `unittest.mock` works without it)

**Async test setup:**
```python
# pyproject.toml or pytest.ini
[tool.pytest.ini_options]
asyncio_mode = "auto"  # or mark each test with @pytest.mark.asyncio
```

**File structure:**
```
project/
  src/mypackage/
  tests/
    conftest.py
    unit/
      test_*.py
```

**Key assertions:**
```python
assert x == expected
assert x is None / is not None
assert x == pytest.approx(3.14)
pytest.raises(ExceptionType, match="message pattern")
```

---

## GDScript — GUT (Godot Unit Test)

**Detection signals:** `addons/gut/` directory, `.gut_editor_config` file,
`gut` in `project.godot` plugins section

**Test file naming:** `test_*.gd` — must start with `test_`
**Test location:** `res://tests/` or `res://test/` (check existing convention)
**Class prefix:** must extend `GutTest`

**GUT test structure:**
```gdscript
extends GutTest

# Setup runs before each test
func before_each():
    pass

# Teardown runs after each test
func after_each():
    pass

# Tests must start with test_
func test_player_takes_damage_reduces_health():
    # Arrange
    var player = Player.new()
    player.health = 100

    # Act
    player.take_damage(25)

    # Assert
    assert_eq(player.health, 75, "Health should be 75 after 25 damage")
```

**GUT assertions:**
```gdscript
assert_eq(actual, expected, "message")
assert_ne(actual, expected, "message")
assert_true(condition, "message")
assert_false(condition, "message")
assert_null(value, "message")
assert_not_null(value, "message")
assert_has(collection, item, "message")
assert_gt(value, min, "message")  # greater than
assert_lt(value, max, "message")  # less than
assert_between(value, min, max, "message")
```

**Mocking/doubling in GUT:**
```gdscript
func test_enemy_calls_attack_on_player():
    # Create a double (mock) of Player
    var mock_player = double(Player).new()
    stub(mock_player, "take_damage").to_return(null)

    var enemy = Enemy.new()
    enemy.attack(mock_player)

    assert_called(mock_player, "take_damage")
    assert_call_count(mock_player, "take_damage", 1)
```

**Testing signals:**
```gdscript
func test_player_emits_died_signal_at_zero_health():
    var player = Player.new()
    watch_signals(player)

    player.take_damage(player.health)  # Kill the player

    assert_signal_emitted(player, "died")
```

**Run from command line (Godot 4 + GUT 9.x):**
```
# Windows PowerShell — res:// prefix is required for -s flag
godot --headless -s res://addons/gut/gut_cmdln.gd -gdir=res://tests/ -gexit
```

**Limitations:**
- No built-in coverage tool — track coverage manually or via code inspection
- Cannot mock built-in Godot methods (push_error, etc.) — wrap them in custom methods
- Async tests require `await` and `yield_to` patterns

**Async GUT pattern:**
```gdscript
func test_async_load_completes():
    var loader = AsyncLoader.new()
    await yield_to(loader, "load_completed", 5)  # wait max 5 seconds
    assert_signal_emitted(loader, "load_completed")
```

---

## JavaScript / TypeScript — Jest

**Detection signals:** `jest.config.*`, `"jest"` in `package.json devDependencies`

**Run command:**
```
npx jest --verbose
npx jest --coverage
npx jest tests/unit/specific.test.ts --verbose
```

**Test structure:**
```typescript
describe("UserService", () => {
    let service: UserService;

    beforeEach(() => {
        service = new UserService(mockDb);
    });

    it("should return user by id", async () => {
        // Arrange
        mockDb.find.mockResolvedValue({ id: 1, name: "Alice" });

        // Act
        const user = await service.getUser(1);

        // Assert
        expect(user.name).toBe("Alice");
    });

    it("should throw when user not found", async () => {
        mockDb.find.mockResolvedValue(null);
        await expect(service.getUser(999)).rejects.toThrow("User not found");
    });
});
```

**Mocking:**
```typescript
jest.mock("../db/client");
const mockDb = jest.mocked(dbClient);
mockDb.find.mockResolvedValue(data);
```

---

## JavaScript / TypeScript — Vitest

**Detection signals:** `vitest.config.*`, `"vitest"` in `package.json`

Syntax is nearly identical to Jest. Import from `vitest` instead:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
```

Mock: `vi.mock(...)` instead of `jest.mock(...)`

---

## Go — testing package

**Detection signals:** `go.mod`, `*_test.go` files

**Run command:**
```
go test ./... -v
go test ./... -cover
go test ./pkg/specific/... -v -run TestFunctionName
```

**Test structure:**
```go
func TestCalculateDiscount_VIPCustomer_Returns20Percent(t *testing.T) {
    // Arrange
    customer := Customer{Tier: "VIP"}
    cart := Cart{Total: 100.0}

    // Act
    discount := CalculateDiscount(customer, cart)

    // Assert
    if discount != 20.0 {
        t.Errorf("expected 20.0, got %f", discount)
    }
}
```

**Table-driven tests (preferred Go pattern):**
```go
func TestValidateEmail(t *testing.T) {
    cases := []struct {
        name  string
        email string
        valid bool
    }{
        {"valid", "a@b.com", true},
        {"empty", "", false},
        {"no at sign", "notanemail", false},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            result := ValidateEmail(tc.email)
            if result != tc.valid {
                t.Errorf("ValidateEmail(%q) = %v, want %v", tc.email, result, tc.valid)
            }
        })
    }
}
```

---

## Fallback — Unknown Framework

If no framework is detected:
1. Report: "No test framework detected. Searched for: pytest.ini, package.json (jest/vitest), go.mod, addons/gut/"
2. List what was found in the project root
3. Ask: "Which test framework should I use, or should I set one up?"
4. Do not generate tests until framework is confirmed
