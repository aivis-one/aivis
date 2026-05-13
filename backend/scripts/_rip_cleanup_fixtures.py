#!/usr/bin/env python3
# =============================================================================
# CBSHOME Backend -- One-shot Test Cleanup Ripper
#                    (iter 2.5 mini-fix #3 -- pytest isolation rewrite)
# =============================================================================
#
# WHAT THIS DOES:
#   Modifies test files in place to remove dead cleanup machinery that
#   the new per-worker ephemeral-DB conftest makes obsolete:
#
#     1. Drops `cleanup_test_users` and `cleanup_telegram_test_users`
#        from `from tests.helpers import (...)` blocks. Handles both
#        the multi-line `(...)` form and the single-line form.
#
#     2. Removes `@pytest.fixture(autouse=True) async def cleanup(...)`
#        blocks in full -- the decorator line, the def line, the body,
#        and the trailing blank line.
#
#     3. Removes local helper functions named `_cleanup_documents` and
#        `_cleanup_notifications` (defined in test_documents.py and
#        test_notification*.py only) along with the trailing blank line.
#
#     4. Drops the `AsyncGenerator[None, None]` import from
#        collections.abc when it is no longer referenced after the
#        fixture block is removed.
#
#   Files written ONLY when content changes. After running, eyeball
#   `git diff` and commit if it looks right.
#
# WHAT THIS DOES NOT DO:
#   - Touch `tests/helpers.py` itself. That file is replaced wholesale
#     by the iter 2.5 PR; you do not need this script to clean it.
#   - Touch `tests/conftest.py`. Same reason -- replaced wholesale.
#   - Touch `tests/test_seed_platform_templates.py` or
#     `tests/test_template_snapshot.py`. Those are also rewritten in the
#     same PR; their fresh versions never had a cleanup fixture in the
#     first place.
#
# HOW TO RUN:
#   cd /opt/cbshome/repo
#   python backend/scripts/_rip_cleanup_fixtures.py
#   git diff backend/tests   # eyeball
#   git add backend/tests && git commit -m "..."
#
#   After the commit you can delete this script -- it has no future use.
#
# IDEMPOTENCY:
#   Re-running on already-ripped files is safe (the script does nothing
#   if the patterns no longer match).
# =============================================================================

from __future__ import annotations

import re
import sys
from pathlib import Path


# Tests rewritten wholesale in the same PR -- skip them.
SKIP_FILES = {
    "test_seed_platform_templates.py",
    "test_template_snapshot.py",
}


# ---------------------------------------------------------------------------
# Step 1 -- prune helper imports
# ---------------------------------------------------------------------------


def _prune_helper_imports(src: str) -> str:
    """Remove cleanup_test_users / cleanup_telegram_test_users from
    `from tests.helpers import ...` statements. Handles both multi-line
    parenthesised form and single-line form.

    Multi-line form, e.g.:
        from tests.helpers import (
            auth_headers,
            cleanup_test_users,
            register_user,
        )
    -> the cleanup_test_users line is removed; the rest is preserved.

    Single-line form, e.g.:
        from tests.helpers import auth_headers, cleanup_test_users, register_user
    -> the cleanup_test_users token is removed; commas are normalised.
    """
    out = src

    # Multi-line form: pull entire `from tests.helpers import (...)` block.
    multiline_re = re.compile(
        r"from tests\.helpers import \(\n(.*?)\n\)",
        re.DOTALL,
    )

    def _strip_multiline(match: re.Match[str]) -> str:
        body = match.group(1)
        kept_lines = [
            line for line in body.splitlines()
            if line.strip().rstrip(",")
            not in {"cleanup_test_users", "cleanup_telegram_test_users"}
        ]
        return "from tests.helpers import (\n" + "\n".join(kept_lines) + "\n)"

    out = multiline_re.sub(_strip_multiline, out)

    # Single-line form: gather identifiers, drop blacklisted ones.
    singleline_re = re.compile(
        r"^from tests\.helpers import (.+)$",
        re.MULTILINE,
    )

    def _strip_singleline(match: re.Match[str]) -> str:
        raw = match.group(1)
        # Skip the `from ... import (` opening line -- multiline form
        # was already handled above.
        if raw.lstrip().startswith("("):
            return match.group(0)
        names = [n.strip() for n in raw.split(",")]
        kept = [
            n for n in names
            if n not in {"cleanup_test_users", "cleanup_telegram_test_users"}
        ]
        if not kept:
            return ""  # whole import vanishes
        return f"from tests.helpers import {', '.join(kept)}"

    out = singleline_re.sub(_strip_singleline, out)
    return out


# ---------------------------------------------------------------------------
# Step 2 -- drop autouse cleanup fixture blocks
# ---------------------------------------------------------------------------


_FIXTURE_DECORATOR_RE = re.compile(
    r"^@pytest\.fixture\(autouse=True\)\s*$",
    re.MULTILINE,
)


def _drop_autouse_cleanup_fixtures(src: str) -> str:
    """Find every `@pytest.fixture(autouse=True)` whose immediately
    following `async def` is named `cleanup` and remove the entire block.

    Block boundary detection:
      Start: the @pytest.fixture(autouse=True) line.
      End:   the first line at column 0 (no leading whitespace) AFTER
             the body has begun. Blank lines and indented lines belong
             to the block.

    This is conservative -- if the file ever has multi-decorator fixtures
    (`@pytest.fixture(autouse=True)` followed by another decorator), the
    next decorator is at column 0 and would be treated as block end. We
    do not have any such case in this codebase.
    """
    lines = src.splitlines(keepends=True)
    output: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if _FIXTURE_DECORATOR_RE.match(line):
            # Peek next non-blank line for `async def cleanup(`.
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and re.match(r"^async def cleanup\(", lines[j]):
                # Block confirmed. Find end: first column-0 non-blank line
                # AFTER the def line.
                k = j + 1
                while k < n:
                    line_k = lines[k]
                    if line_k.strip() == "":
                        k += 1
                        continue
                    if not line_k[0].isspace():
                        break
                    k += 1
                # Skip the block entirely; also swallow a single trailing
                # blank line if present (cosmetic).
                if k < n and lines[k].strip() == "":
                    k += 1
                i = k
                continue
        output.append(line)
        i += 1

    return "".join(output)


# ---------------------------------------------------------------------------
# Step 3 -- drop local _cleanup_documents / _cleanup_notifications defs
# ---------------------------------------------------------------------------


_LOCAL_HELPER_DEF_RE = re.compile(
    r"^async def (_cleanup_documents|_cleanup_notifications)\("
)


def _drop_local_cleanup_helpers(src: str) -> str:
    """Remove top-level async def _cleanup_documents / _cleanup_notifications
    functions. Block boundary identical to the fixture stripper.
    """
    lines = src.splitlines(keepends=True)
    output: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if _LOCAL_HELPER_DEF_RE.match(line):
            # Find end of function body.
            k = i + 1
            while k < n:
                line_k = lines[k]
                if line_k.strip() == "":
                    k += 1
                    continue
                if not line_k[0].isspace():
                    break
                k += 1
            if k < n and lines[k].strip() == "":
                k += 1
            i = k
            continue
        output.append(line)
        i += 1

    return "".join(output)


# ---------------------------------------------------------------------------
# Step 4 -- prune now-orphaned imports
# ---------------------------------------------------------------------------


def _prune_orphan_imports(src: str) -> str:
    """Once the autouse cleanup fixture is gone, several imports become
    dead in many files:
      - `AsyncGenerator` from collections.abc (return type of the fixture)
      - `delete` from sqlalchemy (used only by _cleanup_documents)
      - `Notification` from app.modules.notifications.models (used only
        by _cleanup_notifications in two files)
      - `DocumentSigning` import (used only by _cleanup_documents in
        test_documents.py)

    Conservative approach: drop an import only if the imported name no
    longer appears anywhere else in the file. Catches the common cases
    without risking a false positive.
    """
    out = src

    # Multi-import-from: `from X import (a, b, c)`
    multi_from_re = re.compile(
        r"^from ([\w\.]+) import \(\n(.*?)\n\)",
        re.DOTALL | re.MULTILINE,
    )

    def _strip_multi(match: re.Match[str]) -> str:
        module = match.group(1)
        body = match.group(2)
        kept_lines = []
        for line in body.splitlines():
            name = line.strip().rstrip(",")
            if not name:
                kept_lines.append(line)
                continue
            # Count occurrences of `name` in `out` MINUS the import line.
            # If the only occurrence is the import line itself -> drop it.
            occurrences = len(
                re.findall(rf"\b{re.escape(name)}\b", out)
            )
            # The import contributes 1. Anything > 1 means it's used elsewhere.
            if occurrences > 1:
                kept_lines.append(line)
        if not kept_lines:
            return ""  # whole block becomes empty
        return f"from {module} import (\n" + "\n".join(kept_lines) + "\n)"

    out = multi_from_re.sub(_strip_multi, out)

    # Simple `from collections.abc import AsyncGenerator` (single name).
    if (
        "AsyncGenerator" not in re.sub(
            r"^from collections\.abc import AsyncGenerator\s*$",
            "",
            out,
            flags=re.MULTILINE,
        )
    ):
        out = re.sub(
            r"^from collections\.abc import AsyncGenerator\n",
            "",
            out,
            flags=re.MULTILINE,
        )

    return out


# ---------------------------------------------------------------------------
# Step 5 -- compact triple blank lines created by removals
# ---------------------------------------------------------------------------


def _compact_blank_runs(src: str) -> str:
    """Collapse any run of 3+ consecutive blank lines down to 2."""
    return re.sub(r"\n{4,}", "\n\n\n", src)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def process_file(path: Path) -> bool:
    """Return True if the file was modified."""
    original = path.read_text()
    src = original

    src = _prune_helper_imports(src)
    src = _drop_autouse_cleanup_fixtures(src)
    src = _drop_local_cleanup_helpers(src)
    src = _prune_orphan_imports(src)
    src = _compact_blank_runs(src)

    if src == original:
        return False

    path.write_text(src)
    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    tests_dir = repo_root / "backend" / "tests"

    if not tests_dir.is_dir():
        print(f"ERROR: {tests_dir} does not exist", file=sys.stderr)
        return 1

    targets = sorted(tests_dir.glob("test_*.py"))
    if not targets:
        print(f"ERROR: no test_*.py files in {tests_dir}", file=sys.stderr)
        return 1

    changed: list[str] = []
    skipped: list[str] = []
    untouched: list[str] = []

    for path in targets:
        if path.name in SKIP_FILES:
            skipped.append(path.name)
            continue
        if process_file(path):
            changed.append(path.name)
        else:
            untouched.append(path.name)

    print(f"Changed:   {len(changed)}")
    for name in changed:
        print(f"  - {name}")
    print(f"Skipped:   {len(skipped)} (rewritten wholesale elsewhere)")
    for name in skipped:
        print(f"  - {name}")
    print(f"Untouched: {len(untouched)} (no matching patterns)")
    if len(untouched) <= 8:
        for name in untouched:
            print(f"  - {name}")
    else:
        print(f"  ({len(untouched)} files -- omitted for brevity)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
