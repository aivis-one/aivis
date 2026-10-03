#!/usr/bin/env python3
"""landing-studio v10.0.0 -- scripts/migrate-review.py

One-shot migration from the deprecated v8 inline `[review:{lang}]` marker
format to the v9 out-of-band `_review` channel (section 2, decision Q1).

For every `content/*.json` file that looks like a locale content file (has a
top-level `t` object):
  - strips every `[review:xx]` marker from every string value in `t`,
    INCLUDING every item of a list value, and from `meta.title` /
    `meta.description` if present;
  - unions the dot-keys of every value that had a marker stripped into
    `_review` (also unioning any `_review` list already present), sorted
    and de-duplicated;
  - writes the file back with a non-clobbering backup: `<file>.bak`, then
    `<file>.bak.2`, `<file>.bak.3`, ... -- a second run can never destroy the
    only copy of the true original (same rule as scripts/sanitize.py,
    finding C13).

A file with no top-level `t` (e.g. a `site.json` that happens to sit in the
same directory) is left untouched and reported as skipped -- this script
only ever touches locale content files.

`--dry-run` prints the same per-file summary without writing anything (no
backup is created in dry-run mode either).

After migration, `python3 scripts/i18n-check.py` should report zero in-value
`[review:]` markers for the migrated locale(s).

Usage:
  python3 scripts/migrate-review.py --content-dir content [--dry-run]
"""
import argparse
import json
import sys
from pathlib import Path

import re

REVIEW_RE = re.compile(r"\s*\[review:[a-z-]{2,12}\]")


def backup_path(path):
    """Never clobber an existing backup (finding C13's rule, reused here):
    <file>.bak, then .bak.2, .bak.3, ..."""
    candidate = Path(str(path) + ".bak")
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = Path(str(path) + f".bak.{n}")
        if not candidate.exists():
            return candidate
        n += 1


def strip_value(v):
    """Strip inline markers from a string, or from every item of a list.
    Returns (new_value, occurrences_removed)."""
    if isinstance(v, str):
        new, n = REVIEW_RE.subn("", v)
        return new, n
    if isinstance(v, list):
        out = []
        total = 0
        for item in v:
            if isinstance(item, str):
                new, n = REVIEW_RE.subn("", item)
                out.append(new)
                total += n
            else:
                out.append(item)
        return out, total
    return v, 0


def migrate_file(path):
    """Returns a dict describing what would/did change, and the new document
    (unwritten). Never writes -- callers decide whether to persist."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)

    if not isinstance(data.get("t"), dict):
        return {"skipped": True, "reason": "no top-level 't' object -- not a locale content file"}

    affected = set(data.get("_review", []) or [])
    stripped_total = 0
    changed_keys = []

    t = data["t"]
    for k, v in list(t.items()):
        new_v, n = strip_value(v)
        if n:
            t[k] = new_v
            affected.add(k)
            changed_keys.append(k)
            stripped_total += n

    meta = data.get("meta", {})
    if isinstance(meta, dict):
        for mk in ("title", "description"):
            if mk in meta:
                new_v, n = strip_value(meta[mk])
                if n:
                    meta[mk] = new_v
                    affected.add(f"meta.{mk}")
                    changed_keys.append(f"meta.{mk}")
                    stripped_total += n

    new_review = sorted(affected)
    review_changed = new_review != (data.get("_review") or [])
    data["_review"] = new_review

    changed_any = stripped_total > 0 or review_changed

    return {
        "skipped": False,
        "changed": changed_any,
        "stripped_total": stripped_total,
        "changed_keys": sorted(changed_keys),
        "review_list": new_review,
        "data": data,
        "raw_had_trailing_newline": raw.endswith("\n"),
    }


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--content-dir", required=True, type=Path)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv[1:])

    if not args.content_dir.is_dir():
        print(f"FAIL: content dir not found: {args.content_dir}", file=sys.stderr)
        return 2

    files = sorted(args.content_dir.glob("*.json"))
    if not files:
        print(f"FAIL: no *.json files found under {args.content_dir}", file=sys.stderr)
        return 2

    print("=== migrate-review ===")
    any_error = False
    for f in files:
        try:
            result = migrate_file(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"FAIL: {f}: cannot read/parse ({e})", file=sys.stderr)
            any_error = True
            continue

        if result["skipped"]:
            print(f"SKIP  {f}: {result['reason']}")
            continue

        if not result["changed"]:
            print(f"OK    {f}: no inline markers found; _review already up to date "
                  f"({len(result['review_list'])} key(s))")
            continue

        if args.dry_run:
            print(f"DRY   {f}: would strip {result['stripped_total']} marker(s) across "
                  f"{len(result['changed_keys'])} key(s) {result['changed_keys']}; "
                  f"_review would become {len(result['review_list'])} key(s) "
                  f"{result['review_list']}")
            continue

        bak = backup_path(f)
        f.rename(bak)  # move original aside intact
        text = json.dumps(result["data"], ensure_ascii=False, indent=2)
        if result["raw_had_trailing_newline"]:
            text += "\n"
        f.write_text(text, encoding="utf-8")
        print(f"DONE  {f}: stripped {result['stripped_total']} marker(s) across "
              f"{len(result['changed_keys'])} key(s) {result['changed_keys']}; "
              f"_review now has {len(result['review_list'])} key(s) "
              f"{result['review_list']} (backup: {bak})")

    if any_error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
