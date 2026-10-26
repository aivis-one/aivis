# =============================================================================
# AIVIS.ONE Backend -- unit tests for scripts/sync_project_package.py
# =============================================================================
#
# The copy of a project's package into the seed, and its byte-for-byte check,
# on throw-away folders. Standard library only; no database.
# =============================================================================

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.seed as seed
import scripts.sync_project_package as sync

_PNG = b"\x89PNG\r\n\x1a\nfake"


def _package(root: Path, *, with_logo: bool) -> Path:
    package = root / "package"
    (package / "template" / "media").mkdir(parents=True)
    entry = {"key": "demo-key", "email": "demo@example.com", "name": {"en": "D", "ru": "Д"}}
    if with_logo:
        entry["logo"] = "media/logo.png"
        (package / "template" / "media" / "logo.png").write_bytes(_PNG)
    (package / "company.json").write_text(json.dumps(entry), encoding="utf-8")
    return package


def _profile(root: Path) -> Path:
    path = root / "profile.json"
    path.write_text(json.dumps({"marker": "m", "companies": []}), encoding="utf-8")
    return path


def _run(package: Path, root: Path, **kw):
    return sync.sync(
        package,
        profile_path=root / "profile.json",
        projects_dir=root / "projects",
        owner=kw.get("owner", ("Demo", "Team", "GE")),
        check=kw.get("check", False),
    )


def test_a_copy_makes_the_seed_folder_and_the_entry_equal_to_the_package(tmp_path: Path) -> None:
    _profile(tmp_path)
    package = _package(tmp_path, with_logo=True)
    assert _run(package, tmp_path) == []
    assert (tmp_path / "projects" / "demo-key" / "media" / "logo.png").read_bytes() == _PNG
    (entry,) = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))["companies"]
    assert (entry["first_name"], entry["last_name"], entry["country"]) == ("Demo", "Team", "GE")
    assert "email" not in entry and entry["email_local"] == "demo"
    assert sync.package_part(entry) == sync.profile_form(
        json.loads((package / "company.json").read_text(encoding="utf-8"))
    )
    assert _run(package, tmp_path, check=True) == []


def test_a_check_names_every_difference_and_writes_nothing(tmp_path: Path) -> None:
    _profile(tmp_path)
    package = _package(tmp_path, with_logo=True)
    _run(package, tmp_path)
    folder = tmp_path / "projects" / "demo-key"
    (folder / "media" / "logo.png").write_bytes(_PNG + b"x")
    (folder / "media" / "stray.png").write_bytes(_PNG)
    (package / "template" / "media" / "cover.png").write_bytes(_PNG)
    problems = _run(package, tmp_path, check=True)
    assert "differs from the package: media/logo.png" in problems
    assert "not in the package: media/stray.png" in problems
    assert "missing in the seed folder: media/cover.png" in problems
    assert (folder / "media" / "stray.png").exists(), "a check writes nothing"


def test_a_picture_that_arrives_later_is_brought_by_a_second_copy(tmp_path: Path) -> None:
    _profile(tmp_path)
    package = _package(tmp_path, with_logo=False)
    assert _run(package, tmp_path) == []
    assert not any((tmp_path / "projects" / "demo-key").rglob("*.png"))

    entry = json.loads((package / "company.json").read_text(encoding="utf-8"))
    entry["logo"] = "media/logo.png"
    (package / "company.json").write_text(json.dumps(entry), encoding="utf-8")
    (package / "template" / "media" / "logo.png").write_bytes(_PNG)
    assert _run(package, tmp_path, check=True) != [], "the copy is stale until it is run"
    # no --owner the second time: the profile's own three fields are kept
    assert _run(package, tmp_path, owner=None) == []
    assert (tmp_path / "projects" / "demo-key" / "media" / "logo.png").read_bytes() == _PNG
    (after,) = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))["companies"]
    assert after["logo"] == "media/logo.png" and after["first_name"] == "Demo"


def test_a_new_project_needs_its_owner_names(tmp_path: Path) -> None:
    _profile(tmp_path)
    package = _package(tmp_path, with_logo=False)
    with pytest.raises(sync.SyncError, match="--owner"):
        _run(package, tmp_path, owner=None)


def test_a_file_the_package_dropped_leaves_the_seed_folder(tmp_path: Path) -> None:
    _profile(tmp_path)
    package = _package(tmp_path, with_logo=True)
    _run(package, tmp_path)
    (package / "template" / "media" / "logo.png").unlink()
    assert _run(package, tmp_path, owner=None) == []
    assert not (tmp_path / "projects" / "demo-key" / "media").exists()


def test_a_second_project_is_appended_and_the_first_is_untouched(tmp_path: Path) -> None:
    _profile(tmp_path)
    first = _package(tmp_path, with_logo=False)
    _run(first, tmp_path)
    other = tmp_path / "other"
    (other / "template").mkdir(parents=True)
    (other / "company.json").write_text(json.dumps({"key": "k2", "email": "k2@example.com"}), encoding="utf-8")
    _run(other, tmp_path)
    keys = [c["key"] for c in json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))["companies"]]
    assert keys == ["demo-key", "k2"]


def test_the_shipped_entries_are_whole_and_their_folders_are_files() -> None:
    """The shipped entries carry the owner fields and a local part, and every
    file in their folders is a file. The byte-for-byte check against the
    package itself is the script's `--check`, run where the package is."""
    for entry in seed.load_profile("default")["companies"]:
        folder = seed.PROJECTS_DIR / entry["key"]
        for name in sync.tree_files(folder):
            assert (folder / name).is_file()
        assert set(sync.OWNER_FIELDS) <= set(entry)
        assert "email_local" in entry and "email" not in entry
