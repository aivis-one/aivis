# =============================================================================
# AIVIS.ONE Backend -- Storage Filename Sanitiser Tests (TASK-22, 2026-08-17)
# =============================================================================
#
# WHY THIS FILE EXISTS, and it is not "more coverage":
#   `_sanitize_storage_filename` is the whole of TASK-6 4.2 -- the storage-key
#   traversal fix shipped at `0fdc7c7`. It went out with NO test. The suite
#   went green afterwards, which proved that nothing REGRESSED and said
#   nothing at all about whether the new behaviour WORKS. That gap is the
#   named subject of TASK-22.
#
# WHY IT IS A SEPARATE FILE FROM test_storage.py:
#   That file has an autouse fixture that wipes a real MinIO bucket, so every
#   test in it is an integration test by construction. The sanitiser is a
#   pure function over a string. Putting it there would put a pure unit test
#   behind a running MinIO for no reason -- and this file runs anywhere,
#   which is exactly what makes it useful when the box has no docker.
#
# THE CONTRACT UNDER TEST (service.py:1412-1440), in the function's own terms:
#   allow-list, not deny-list; dot runs collapsed AFTER the character strip,
#   never before; leading/trailing " .-" trimmed; a name that cleans to
#   nothing becomes "untitled" rather than an empty path segment; 200 chars.
# =============================================================================

import pytest

from app.modules.companies.service import (
    _MAX_STORAGE_FILENAME_LENGTH,
    _sanitize_storage_filename,
    build_storage_key,
)


# ---------------------------------------------------------------------------
# The thing it was written for: no result can carry a path separator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "a/b/c.pdf",
        "....//....//secret.txt",
        "%2e%2e%2fpasswd",
        "dir/../../../root/.ssh/id_rsa",
    ],
)
def test_sanitiser_never_emits_a_path_separator(hostile: str) -> None:
    """No input may produce a `/` or `\\` in the output.

    This is the property the fix exists for, stated as a property rather
    than as seven expected strings: a key segment that cannot contain a
    separator cannot add or remove a path segment, whatever the input was.
    """
    out = _sanitize_storage_filename(hostile)
    assert "/" not in out
    assert "\\" not in out


def test_sanitiser_collapses_dot_runs_after_stripping_not_before() -> None:
    """`../` must not survive as a bare `..` once the slash is dropped.

    The docstring calls the ordering out explicitly, so it gets its own
    assertion: strip characters first, then collapse dot runs. Doing it the
    other way leaves `..` behind, which is the traversal token itself.
    """
    assert ".." not in _sanitize_storage_filename("../../etc/passwd")
    assert ".." not in _sanitize_storage_filename("....//....//x.txt")


def test_sanitiser_trims_leading_dot_and_hyphen() -> None:
    """A leading dot is a hidden file; a leading hyphen reads as a flag."""
    assert not _sanitize_storage_filename(".hidden").startswith(".")
    assert not _sanitize_storage_filename("-rf").startswith("-")
    assert not _sanitize_storage_filename("  .-spaced.-  ").startswith((" ", ".", "-"))
    assert not _sanitize_storage_filename("  .-spaced.-  ").endswith((" ", ".", "-"))


@pytest.mark.parametrize("empties", ["", "...", "..", "///", "!!!", "   ", ".-.-.-"])
def test_sanitiser_never_returns_an_empty_segment(empties: str) -> None:
    """A name that cleans to nothing falls back to a literal.

    An empty segment would leave the built key ending in `/` -- directory-
    shaped, not file-shaped -- which is a different bug from traversal and
    is why the fallback exists.
    """
    assert _sanitize_storage_filename(empties) == "untitled"


def test_sanitiser_caps_length() -> None:
    """200 characters, so an uploader cannot push the key past any limit."""
    out = _sanitize_storage_filename("a" * 5000)
    assert len(out) == _MAX_STORAGE_FILENAME_LENGTH


# ---------------------------------------------------------------------------
# MUST-FIRE CONTROL -- the tests above are all about what is REMOVED, so
# every one of them would still pass if the function returned "untitled" for
# everything. This is the case that proves it does not.
# ---------------------------------------------------------------------------


def test_sanitiser_keeps_an_ordinary_filename_intact() -> None:
    """The control: a legitimate name must survive unchanged.

    Without this, a function that threw away its input entirely would pass
    every other test in this file. Allowed set per the source: ASCII
    letters, digits, spaces, dots, hyphens, underscores.
    """
    assert _sanitize_storage_filename("Annual Report 2026-v2.pdf") == (
        "Annual Report 2026-v2.pdf"
    )
    assert _sanitize_storage_filename("invoice_001.PDF") == "invoice_001.PDF"


# ---------------------------------------------------------------------------
# The caller, because the sanitiser being right is worth nothing if the key
# builder does not use it -- the whole point of TASK-6 4.2 was moving the
# call INTO the shared helper rather than leaving it at each call site.
# ---------------------------------------------------------------------------


def test_build_storage_key_sanitises_its_filename() -> None:
    """The shared helper must sanitise, not merely interpolate.

    Both the router and reconcile_attachments.py go through this function;
    a traversal that survived here would survive for both.
    """
    from uuid import uuid4

    company_id, attachment_id = uuid4(), uuid4()
    key = build_storage_key(company_id, attachment_id, "../../etc/passwd")

    assert ".." not in key
    # Exactly the three segments the convention defines -- the hostile
    # filename added none.
    assert key.count("/") == build_storage_key(
        company_id, attachment_id, "clean.pdf"
    ).count("/")
