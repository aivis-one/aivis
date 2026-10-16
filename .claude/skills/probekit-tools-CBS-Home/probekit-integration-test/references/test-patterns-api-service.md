---
name: test-patterns-api-service
description: "API, service, contract, parametrized, GDScript, and chaos/failure integration test patterns with general anti-patterns."
---

# API & Service Integration Test Patterns

Reference patterns for generating API, service-layer, and cross-cutting integration tests.
Pick the correct pattern for each layer. Combine as needed.

---

## Pattern 2 — FastAPI / Flask API Test (Python / pytest)

Use when: testing HTTP endpoints end-to-end through the framework, including routing, validation, and response shape.

```python
# conftest.py
import pytest
from fastapi.testclient import TestClient  # or from flask import testing
from myapp.main import app
from myapp.database import get_db

@pytest.fixture(scope="function")
def test_db(tmp_path):
    """Isolated SQLite DB session for API tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from myapp.database import Base  # adapt import to project

    db_path = tmp_path / "test.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session          # yield session, not path — this is what override_get_db returns
    session.close()
    Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def client(test_db):
    """Test client with DB dependency overridden to use isolated test session."""
    def override_get_db():
        yield test_db      # yields the session object from test_db fixture
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

# test file
def test_create_user_success(client):
    response = client.post("/users", json={"name": "Alice", "email": "alice@test.com"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice"
    assert "id" in data
    assert "password_hash" not in data  # contract: internal fields not leaked

def test_create_user_duplicate_email(client):
    client.post("/users", json={"name": "Alice", "email": "alice@test.com"})
    response = client.post("/users", json={"name": "Bob", "email": "alice@test.com"})
    assert response.status_code == 409  # or 422 depending on design
    assert "error" in response.json()
```

Key rules:
- Override DB dependency — never let tests hit production DB
- Clear dependency_overrides after test
- Test response shape, not just status code
- Always test: success, validation failure, not-found, duplicate

---

## Pattern 3 — Service Layer Test with Mocked External Deps (Python / pytest)

Use when: testing service functions that call external APIs, email, payment etc.

```python
import pytest
from unittest.mock import patch
from myapp.services.payment import process_payment, PaymentError  # adapt import

@pytest.fixture
def db_with_order(db_conn):
    """Seed an order that payment tests need."""
    db_conn.execute("INSERT INTO orders (id, user_id, status, total) VALUES (1, 1, 'pending', 9900)")
    db_conn.commit()
    yield db_conn

def test_process_payment_success(db_with_order):
    with patch("myapp.services.payment.stripe_client.charge") as mock_charge:
        mock_charge.return_value = {"id": "ch_123", "status": "succeeded"}
        result = process_payment(order_id=1, amount=9900, db=db_with_order)
    assert result.status == "paid"
    # Verify DB state changed — test behaviour, not just return value
    row = db_with_order.execute("SELECT status FROM orders WHERE id=1").fetchone()
    assert row["status"] == "paid"

def test_process_payment_stripe_failure(db_with_order):
    with patch("myapp.services.payment.stripe_client.charge") as mock_charge:
        mock_charge.side_effect = Exception("Card declined")
        with pytest.raises(PaymentError):
            process_payment(order_id=1, amount=9900, db=db_with_order)
    # Verify DB NOT updated on failure — rollback must have occurred
    row = db_with_order.execute("SELECT status FROM orders WHERE id=1").fetchone()
    assert row["status"] == "pending"  # unchanged
```

Key rules:
- Mock at the boundary (the external client call), not the internal service logic
- Always verify DB state after the call, not just return value
- Test both success and failure branches
- Verify rollback on failure: DB state must be unchanged

---

## Pattern 4 — Contract Compliance Test

Use when: verifying the API response shape matches what callers expect.

```python
def test_user_response_contract(client):
    """Response must include required fields and exclude internal fields."""
    response = client.get("/users/1")
    assert response.status_code == 200
    data = response.json()
    
    # Required fields (contract: callers depend on these)
    REQUIRED_FIELDS = {"id", "name", "email", "created_at"}
    assert REQUIRED_FIELDS.issubset(data.keys()), \
        f"Missing fields: {REQUIRED_FIELDS - data.keys()}"
    
    # Forbidden fields (contract: internal fields must not leak)
    FORBIDDEN_FIELDS = {"password_hash", "db_row_id", "internal_status"}
    leaked = FORBIDDEN_FIELDS & data.keys()
    assert not leaked, f"Internal fields leaked: {leaked}"

def test_error_response_contract(client):
    """Error responses must have consistent envelope."""
    response = client.get("/users/99999")
    assert response.status_code == 404
    data = response.json()
    # Consistent error envelope
    assert "error" in data or "detail" in data, "Error response has no error field"
```

---

## Pattern 6 — Parametrized Edge Cases

Use when: covering multiple input variations efficiently.

```python
import pytest

@pytest.mark.parametrize("payload,expected_status", [
    ({"name": "Alice", "email": "a@test.com"}, 201),   # valid
    ({"name": "", "email": "a@test.com"}, 422),          # empty name
    ({"name": "Alice", "email": "not-an-email"}, 422),   # bad email
    ({"email": "a@test.com"}, 422),                       # missing name
    ({}, 422),                                             # empty body
])
def test_create_user_validation(client, payload, expected_status):
    response = client.post("/users", json=payload)
    assert response.status_code == expected_status
```

---

## Pattern 7 — GDScript / GUT Test (Godot Engine)

Use when: testing Godot scenes, autoloads, or service nodes.

```gdscript
extends GutTest

var service = null

func before_each():
    service = preload("res://src/services/MyService.gd").new()
    add_child(service)

func after_each():
    service.queue_free()

func test_initial_state():
    assert_eq(service.status, "idle", "Service should start idle")

func test_process_returns_expected_value():
    var result = service.process_data({"key": "value"})
    assert_not_null(result)
    assert_true(result.has("output"))

func test_process_with_invalid_input():
    var result = service.process_data(null)
    assert_null(result, "Should return null for invalid input")
```

---

## Pattern 8 — Chaos / Failure Injection Test

Use when: testing graceful degradation under failure conditions (DB timeout, upstream 500, connection drop).

```python
import pytest
from unittest.mock import patch, MagicMock
from requests.exceptions import ConnectionError, Timeout

def test_upstream_timeout_returns_fallback(client):
    """System should degrade gracefully when upstream service times out."""
    with patch("myapp.services.external.http_client.get", side_effect=Timeout("Connection timed out")):
        response = client.get("/api/data")
    # System should NOT crash — should return cached/default/503
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        assert response.json().get("source") in ("cache", "default")

def test_db_connection_failure_returns_503(client):
    """API should return 503 when DB is unreachable, not 500 with traceback."""
    with patch("myapp.database.get_db", side_effect=ConnectionError("DB unreachable")):
        response = client.get("/api/users")
    assert response.status_code == 503
    assert "traceback" not in response.text.lower()

def test_upstream_500_does_not_crash_caller(client):
    """Upstream 500 should be handled, not propagated as unhandled exception."""
    mock_resp = MagicMock(status_code=500, json=lambda: {"error": "Internal"})
    with patch("myapp.services.external.http_client.get", return_value=mock_resp):
        response = client.get("/api/enriched-data")
    assert response.status_code in (200, 502, 503)
```

Key rules:
- Use mock-based failure injection (not Toxiproxy infrastructure) — keeps tests portable
- Test that the system degrades gracefully, not that it handles the specific exception
- Verify no internal details leaked in error responses
- Test both timeout and connection-refused scenarios

---

## Pattern 9 — Contract Compliance Test (Extended)

Use when: API has known consumers and contract changes could break them.
Extends Pattern 4 with schema validation and breaking change detection.

```python
from jsonschema import validate

USER_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "email", "created_at"],
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string", "minLength": 1},
        "email": {"type": "string", "format": "email"},
        "created_at": {"type": "string", "format": "date-time"},
    },
    "additionalProperties": False,  # strict: no extra fields
}

def test_user_endpoint_matches_schema(client):
    """Response must match published JSON schema."""
    response = client.get("/api/users/1")
    assert response.status_code == 200
    validate(instance=response.json(), schema=USER_SCHEMA)

def test_list_endpoint_pagination_contract(client):
    """List endpoints must return pagination metadata."""
    response = client.get("/api/users?page=1&size=10")
    data = response.json()
    assert "items" in data, "List must have 'items' array"
    assert "total" in data, "List must have 'total' count"
    assert "page" in data, "List must have 'page' number"

def test_error_envelope_contract(client):
    """All error responses must follow error envelope format."""
    for url in ["/api/users/99999", "/api/invalid-endpoint"]:
        response = client.get(url)
        if response.status_code >= 400:
            data = response.json()
            assert "error" in data or "detail" in data, \
                f"{url} returned {response.status_code} without error envelope"
```

Key rules:
- Use JSON Schema for machine-readable validation
- Test both success and error envelopes
- List endpoints must always test pagination contract
- Recommend Pact or Schemathesis for consumer-driven contracts (report as SUGGESTION, don't generate infrastructure)

---

## Anti-Patterns to Avoid

Never generate tests that:
- Test implementation details instead of behaviour (don't assert on private var names)
- Have no assertions (`def test_thing(): call_function()` — worthless)
- Depend on test execution order (each test must be independent)
- Sleep/wait with fixed time.sleep() — use monkeypatch for time-sensitive logic
- Have commented-out assertions ("# assert thing == expected  # TODO")
- Test the mock instead of the code (verifying mock.called without verifying actual behaviour)
