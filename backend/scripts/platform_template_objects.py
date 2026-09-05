#!/usr/bin/env python3
"""Platform template OBJECTS: upload them, and verify they are there.

    python -m scripts.platform_template_objects upload
    python -m scripts.platform_template_objects check

WHY THIS FILE EXISTS, AND THAT IT IS A SECOND COPY.
    The box does both of these from `scripts/aivis-manage.sh` --
    restore_platform_template_objects (:697) uploads, and
    count_platform_template_objects (:730) plus
    check_platform_template_objects (:750) verify. Both are python
    heredocs run with `docker compose exec app python -`, which needs a
    running compose stand. CI has no compose stand, so it needs the same
    two operations reachable without one.

    THIS IS THEREFORE A DUPLICATE, AND IT IS MEANT TO BE MERGED. The
    intended end state is that the CLI calls this module instead of
    carrying its own heredocs, which makes the merge a one-line change
    there and no change here. Until that happens the two can drift: if
    you change the counts, the prefix, or the source directory, change
    them in aivis-manage.sh as well. Recorded as a debt in the line
    registry rather than left for someone to discover by divergence.

WHY THE SAME CODE AND NOT `mc cp`.
    Uploading with mc would let mc decide key prefixes and content
    types, and the check would then be measuring mc rather than the code
    that serves an agreement in production. upload_object and
    list_objects here are the product's own, from app.core.storage --
    the same functions the box runs, so what CI verifies is what ships.

WHICH BUCKET.
    Whatever MINIO_BUCKET points at -- for both operations, and
    deliberately the MAIN bucket rather than the test one. Only
    test_storage.py redirects storage, through a fixture local to that
    file; agreements and certificates read the main bucket even during a
    test run. Checking aivis-attachments-test here would pass exactly
    when the agreement and certificate tests are failing, which is the
    reasoning aivis-manage.sh:254 gives at greater length.

WHY `check` EXISTS SEPARATELY FROM THE SUITE.
    Failing here rather than inside pytest is the point. Without the
    objects the suite falls over anyway -- on 2026-09-01 it was
    twenty-nine failures -- and the difference is what the reader gets:
    twenty-nine StorageError tracebacks, or one line naming the count
    and the command that restores it.
"""

from __future__ import annotations

import asyncio
import mimetypes
import sys
from pathlib import Path

from app.core.storage import list_objects, upload_object

# Source of truth for the objects: 16 template directories of four files
# each. The 64 and the 16 below are derived from this tree, not chosen --
# which is what makes "one file went missing" a detectable state rather
# than a number nobody can check.
SRC = Path(__file__).resolve().parent / "templates" / "_default"
PREFIX = "_platform/templates/"

EXPECTED_TOTAL = 64
EXPECTED_HTML = 16


async def upload() -> int:
    """Upload every file under _default/ to PREFIX. Returns an exit code.

    Keys are deterministic (the path relative to SRC), so a re-run
    overwrites rather than accumulates -- a second run must still leave
    64 objects, not 128.
    """
    if not SRC.is_dir():
        print(f"source directory missing: {SRC}", file=sys.stderr)
        return 1

    uploaded = 0
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        key = PREFIX + str(path.relative_to(SRC))
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        await upload_object(key, path.read_bytes(), ctype)
        uploaded += 1

    if uploaded == 0:
        print(f"source directory is empty: {SRC}", file=sys.stderr)
        return 1

    print(f"uploaded {uploaded} template objects")
    return 0


async def check() -> int:
    """Verify 64 objects and 16 template.html under PREFIX.

    Both numbers, not just the total: 64 files of the wrong kind would
    satisfy a total-only check, and the html is the half the renderer
    actually opens.
    """
    keys = await list_objects(PREFIX)
    html = [k for k in keys if k.endswith("template.html")]

    if len(keys) != EXPECTED_TOTAL or len(html) != EXPECTED_HTML:
        print(
            f"platform template OBJECTS check failed: expected "
            f"{EXPECTED_TOTAL} objects and {EXPECTED_HTML} template.html "
            f"under {PREFIX}, found {len(keys)} objects and "
            f"{len(html)} template.html",
            file=sys.stderr,
        )
        print(
            "The DB rows can be intact while the objects are gone -- that "
            "is exactly the state this check exists to catch, and the row "
            "count cannot see it. Restore with "
            "`python -m scripts.platform_template_objects upload`, or "
            "`aivis update` on a box.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{len(keys)} platform template objects present "
        f"({len(html)} template.html)"
    )
    return 0


def main() -> int:
    commands = {"upload": upload, "check": check}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(
            f"usage: python -m scripts.platform_template_objects "
            f"{{{'|'.join(commands)}}}",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(commands[sys.argv[1]]())


if __name__ == "__main__":
    sys.exit(main())
