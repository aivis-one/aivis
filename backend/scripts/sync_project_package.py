#!/usr/bin/env python3
# =============================================================================
# AIVIS.ONE Backend -- put a project's package into the seed, and prove it
# =============================================================================
#
# USAGE:
#   python scripts/sync_project_package.py PACKAGE_DIR [--owner FIRST LAST COUNTRY]
#   python scripts/sync_project_package.py PACKAGE_DIR --check
#
# A project's package is a folder with `company.json` (one entry in the form of
# the seed profile's `companies[]`) and `template/` (the pictures and documents
# it names, by paths relative to `template/`). This script is the one way a
# package reaches the seed:
#
#   copy:  template/ -> scripts/templates/projects/<key>/, file by file, with
#          nothing left over in the destination that the package does not
#          hold; and company.json -> the profile's `companies[]` entry of the
#          same key (replaced where it exists, appended where it does not),
#          plus the three fields of the project's account that a package
#          carries no person for (first name, last name, country). The
#          package's `email` becomes the entry's `email_local` (its local
#          part): the product's code names no deployment address, and the
#          seed writes <local part>@<host of FRONTEND_BASE_URL> anyway.
#   check: compares the template files byte for byte and the profile entry as parsed JSON (the owner's three fields excluded) and exits 1 on any
#          difference, naming each; writes nothing.
#
# WHY A COPY AND A CHECK. The package is the master. A project whose pictures
# arrive later (the package grows `logo` and a file under template/media/)
# is brought up by running this again; the seed then uploads each picture
# only into a slot that is still empty, so a re-run of the seed adds them
# and touches nothing else.
#
# The owner's three fields are given once with --owner and are kept from the
# profile's existing entry on every later run. Standard library only: it runs
# anywhere, without the database.
# =============================================================================

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PROFILES_DIR = SCRIPTS_DIR / "seed_profiles"
PROJECTS_DIR = SCRIPTS_DIR / "templates" / "projects"

OWNER_FIELDS = ("first_name", "last_name", "country")


class SyncError(Exception):
    """The package or the profile cannot be taken as it is."""


def read_package(package: Path) -> dict[str, Any]:
    """The package's entry, or a refusal naming what is wrong."""
    data_file = package / "company.json"
    if not data_file.is_file():
        raise SyncError(f"{data_file} does not exist")
    entry = json.loads(data_file.read_text(encoding="utf-8"))
    if not isinstance(entry, dict) or not isinstance(entry.get("key"), str) or not entry["key"]:
        raise SyncError(f"{data_file} must be one object with a `key`")
    if not (package / "template").is_dir():
        raise SyncError(f"{package / 'template'} does not exist")
    return entry


def tree_files(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by its path relative to it (forward slashes)."""
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)).replace("\\", "/"): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def diff_tree(package_template: Path, destination: Path) -> list[str]:
    """What differs between the package's template/ and the seed's folder."""
    want = tree_files(package_template)
    have = tree_files(destination)
    problems = []
    for name in sorted(want):
        if name not in have:
            problems.append(f"missing in the seed folder: {name}")
        elif want[name] != have[name]:
            problems.append(f"differs from the package: {name}")
    for name in sorted(set(have) - set(want)):
        problems.append(f"not in the package: {name}")
    return problems


def copy_tree(package_template: Path, destination: Path) -> None:
    """Make `destination` hold exactly the package's files."""
    want = tree_files(package_template)
    for name in sorted(set(tree_files(destination)) - set(want)):
        (destination / name).unlink()
    for name in want:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package_template / name, target)
    # Folders the package no longer fills are not kept empty.
    if destination.is_dir():
        for folder in sorted(destination.rglob("*"), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()


def profile_form(package_entry: dict[str, Any]) -> dict[str, Any]:
    """The package's entry as the profile holds it: `email` replaced, in its
    place, by `email_local`, the part before the `@`."""
    entry: dict[str, Any] = {}
    for key, value in package_entry.items():
        if key == "email" and isinstance(value, str):
            entry["email_local"] = value.split("@", 1)[0]
        else:
            entry[key] = value
    return entry


def entry_for(
    package_entry: dict[str, Any], current: dict[str, Any] | None, owner: tuple[str, str, str] | None
) -> dict[str, Any]:
    """The profile's entry: the package's, then the owner's three fields."""
    entry = profile_form(package_entry)
    if owner is not None:
        fields = dict(zip(OWNER_FIELDS, owner, strict=True))
    elif current is not None and all(f in current for f in OWNER_FIELDS):
        fields = {f: current[f] for f in OWNER_FIELDS}
    else:
        raise SyncError(
            f"project {package_entry['key']!r} has no owner names yet: "
            f"give --owner FIRST LAST COUNTRY"
        )
    entry.update(fields)
    return entry


def package_part(profile_entry: dict[str, Any]) -> dict[str, Any]:
    """A profile entry without the owner's three fields -- what the package holds."""
    return {k: v for k, v in profile_entry.items() if k not in OWNER_FIELDS}


def load_profile(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_profile(profile: dict[str, Any]) -> str:
    return json.dumps(profile, ensure_ascii=False, indent=2) + "\n"


def sync(
    package: Path,
    *,
    profile_path: Path,
    projects_dir: Path,
    owner: tuple[str, str, str] | None,
    check: bool,
) -> list[str]:
    """Copy (or, with `check`, compare). Returns the problems found; empty
    after a copy and when a check passes."""
    package_entry = read_package(package)
    key = package_entry["key"]
    profile = load_profile(profile_path)
    companies = profile.setdefault("companies", [])
    index = next((i for i, c in enumerate(companies) if c.get("key") == key), None)
    current = companies[index] if index is not None else None

    problems: list[str] = []
    if check:
        if current is None:
            problems.append(f"profile has no entry for {key!r}")
        elif package_part(current) != profile_form(package_entry):
            problems.append(f"profile entry {key!r} differs from company.json")
        problems += diff_tree(package / "template", projects_dir / key)
        return problems

    entry = entry_for(package_entry, current, owner)
    if index is None:
        companies.append(entry)
    else:
        companies[index] = entry
    copy_tree(package / "template", projects_dir / key)
    profile_path.write_text(dump_profile(profile), encoding="utf-8", newline="\n")
    return diff_tree(package / "template", projects_dir / key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy a project package into the seed, or check the copy.")
    parser.add_argument("package", type=Path, help="the package folder (company.json and template/)")
    parser.add_argument("--profile", default="default", help="profile name (default: default)")
    parser.add_argument("--owner", nargs=3, metavar=("FIRST", "LAST", "COUNTRY"))
    parser.add_argument("--check", action="store_true", help="compare (files byte for byte, the entry as parsed JSON), write nothing")
    args = parser.parse_args(argv)
    try:
        problems = sync(
            args.package,
            profile_path=PROFILES_DIR / f"{args.profile}.json",
            projects_dir=PROJECTS_DIR,
            owner=tuple(args.owner) if args.owner else None,
            check=args.check,
        )
    except SyncError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("equal" if args.check else "copied and equal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
