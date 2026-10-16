# Property-Based Testing Reference

PBT generates random inputs and checks that properties (invariants) hold.
Complements example-based tests — does not replace them.

## When to Use PBT

| Use PBT | Stick with examples |
|---------|-------------------|
| Pure functions with mathematical properties | Functions with complex setup/teardown |
| Serialization/deserialization roundtrips | Functions with side effects |
| Sorting, filtering, transformation | UI event handlers |
| Validation functions (should accept/reject) | Functions requiring specific mock orchestration |
| Encoding/decoding, parsing/formatting | Functions with very few valid inputs |

**Decision rule:** If you can state "for ALL valid inputs X, property P holds" — use PBT.

## Property Catalog

### Roundtrip / Inverse
`decode(encode(x)) == x`

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_json_roundtrip(s):
    import json
    assert json.loads(json.dumps(s)) == s
```

### Idempotency
`f(f(x)) == f(x)`

```python
@given(st.text())
def test_normalize_idempotent(s):
    assert normalize(normalize(s)) == normalize(s)
```

### Commutativity
`f(a, b) == f(b, a)`

```python
@given(st.integers(), st.integers())
def test_add_commutative(a, b):
    assert add(a, b) == add(b, a)
```

### Invariant Preservation
Operation preserves key data properties (length, membership, type).

```python
@given(st.lists(st.integers()))
def test_sort_preserves_elements(lst):
    result = sorted(lst)
    assert len(result) == len(lst)
    assert set(result) == set(lst)
```

### Monotonicity
`if a <= b then f(a) <= f(b)`

```python
@given(st.integers(min_value=0), st.integers(min_value=0))
def test_tax_monotonic(income_a, income_b):
    if income_a <= income_b:
        assert calculate_tax(income_a) <= calculate_tax(income_b)
```

### Oracle / Reference
Compare against known-good (slow) implementation.

```python
@given(st.lists(st.integers()))
def test_my_sort_matches_stdlib(lst):
    assert my_sort(lst) == sorted(lst)
```

## Tools

### Python — hypothesis
```python
pip install hypothesis

from hypothesis import given, strategies as st

@given(st.integers(), st.integers())
def test_addition_commutative(a, b):
    assert a + b == b + a
```

Common strategies: `st.text()`, `st.integers()`, `st.floats()`, `st.lists()`,
`st.dictionaries()`, `st.binary()`, `st.from_type()`, `st.builds(MyClass)`

### JS/TS — fast-check
```typescript
import * as fc from "fast-check";

test("sort preserves length", () => {
  fc.assert(
    fc.property(fc.array(fc.integer()), (arr) => {
      expect([...arr].sort().length).toBe(arr.length);
    })
  );
});
```

Common arbitraries: `fc.integer()`, `fc.string()`, `fc.array()`,
`fc.record()`, `fc.jsonValue()`, `fc.oneof()`

## Shrinking

When PBT finds a failing input, it automatically **shrinks** it to the minimal
reproducing case. This is one of PBT's key advantages over random fuzzing.

Example: if `test_sort_preserves_elements` fails on a list of 50 elements,
hypothesis will shrink it to the minimal list (often 1-2 elements) that still fails.

## Integration with pytest

PBT tests coexist with example-based tests in the same file:

```python
# Example-based: specific known edge cases
def test_parse_empty_string_raises():
    with pytest.raises(ValueError):
        parse_date("")

# Property-based: all valid dates roundtrip
@given(st.dates())
def test_date_roundtrip(d):
    assert parse_date(format_date(d)) == d
```

Both run with `pytest` — no special runner needed.
