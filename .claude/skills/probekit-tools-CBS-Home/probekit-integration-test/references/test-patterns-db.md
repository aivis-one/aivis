---
name: test-patterns-db
description: "Database-related integration test patterns: SQLite/DB layer tests, DB constraint and integrity tests, and DB-specific anti-patterns."
---

# Database Integration Test Patterns

Reference patterns for generating database-layer integration tests.
Pick the correct pattern for each layer. Combine as needed.

---

## Pattern 1 — SQLite / DB Layer Test (Python / pytest)

Use when: testing repository functions, raw SQL queries, ORM models against real SQLite.

```python
# conftest.py
import pytest
import sqlite3
from pathlib import Path

@pytest.fixture(scope="function")
def db_conn(tmp_path):
    """Fresh in-memory SQLite DB per test. Schema applied from production DDL."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Apply schema — read from actual schema file or inline DDL
    schema_sql = Path("schema.sql").read_text()  # adapt path as needed
    conn.executescript(schema_sql)
    yield conn
    conn.close()

@pytest.fixture(scope="function")
def db_with_data(db_conn):
    """DB with seed data for read tests. Yields so teardown is guaranteed."""
    db_conn.execute("INSERT INTO users (id, name, email) VALUES (1, 'Alice', 'alice@test.com')")
    db_conn.commit()
    yield db_conn
    # db_conn teardown (conn.close) runs automatically after this fixture completes
```

Key rules:
- `scope="function"` — fresh DB per test, prevents data leakage between tests
- `PRAGMA foreign_keys = ON` — always enable, SQLite disables FK checks by default
- Use `tmp_path` for file-based DB (not :memory:) when testing file path behaviour
- Always `yield`, not `return` — ensures cleanup runs even on test failure; applies to ALL fixtures
- Rollback or drop in teardown (after yield)

---

## Pattern 5 — DB Constraint and Integrity Test

Use when: verifying that DB layer enforces schema constraints correctly.

```python
import pytest

def test_unique_constraint_email(db_conn):
    db_conn.execute("INSERT INTO users (name, email) VALUES ('Alice', 'a@test.com')")
    db_conn.commit()
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        db_conn.execute("INSERT INTO users (name, email) VALUES ('Bob', 'a@test.com')")
        db_conn.commit()

def test_foreign_key_constraint(db_conn):
    with pytest.raises(Exception):  # FK violation
        db_conn.execute("INSERT INTO orders (user_id, total) VALUES (99999, 100)")
        db_conn.commit()

def test_not_null_constraint(db_conn):
    with pytest.raises(Exception):
        db_conn.execute("INSERT INTO users (name) VALUES ('Alice')")  # email is NOT NULL
        db_conn.commit()
```

---

## DB-Specific Anti-Patterns to Avoid

Never generate tests that:
- Share mutable DB state between tests (no module-scoped DB with mutations)
- Use production DB path or production config
- Depend on test execution order (each test must be independent)
- Assert on exact timestamps — use approximate comparison or mock the clock
