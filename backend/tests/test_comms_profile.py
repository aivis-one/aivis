# =============================================================================
# AIVIS.ONE Backend -- the comms profile is version 2 and owns the channels
#                      (H23 P-112)
# =============================================================================
#
# comms 3.0.0 starts only on a `version: 2` profile, takes the channel from
# the profile and refuses a request that names one. The loader of the
# final comms slice accepting comms-profile/types.yaml is proven by
# running it (H23 report); what is guarded HERE, on every run of this
# suite, is the half the product controls: the file's shape, the four
# channel routings, and that no emitter names a channel.
# =============================================================================

import ast
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_PROFILE = _ROOT / "comms-profile" / "types.yaml"
_APP = _ROOT / "backend" / "app"

_CHANNELS = {
    "auth.verification_code": ["email"],
    "auth.password_reset": ["email"],
    "purchase.agreement": ["in_app", "email"],
    "ownership.certificate": ["in_app", "email"],
}


def _profile() -> dict:
    return yaml.safe_load(_PROFILE.read_text())


def test_the_profile_is_version_2_with_types_under_types() -> None:
    doc = _profile()
    assert set(doc) == {"version", "types"}
    assert doc["version"] == 2
    assert len(doc["types"]) == 26


def test_exactly_four_types_carry_channels_and_they_are_the_letters() -> None:
    types = _profile()["types"]
    carried = {
        key: record["channels"]
        for key, record in types.items()
        if record and "channels" in record
    }
    assert carried == _CHANNELS


def test_the_four_email_types_still_have_no_category() -> None:
    """A category puts a type behind the mute gate; nobody may switch off
    their own login mail (the file's own header)."""
    types = _profile()["types"]
    for key in _CHANNELS:
        assert "category" not in (types[key] or {}), key
    assert sum(1 for r in types.values() if r and "category" in r) == 22


def test_no_emitter_names_a_channel() -> None:
    """Every form a channel could be written in an event's data: a dict
    literal key, a subscript assignment, a keyword. comms refuses it."""
    offenders = []
    for path in _APP.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                if "channels" in keys:
                    offenders.append(f"{path}:{node.lineno}")
            elif isinstance(node, ast.Subscript) and isinstance(
                node.slice, ast.Constant
            ) and node.slice.value == "channels" and isinstance(node.ctx, ast.Store):
                offenders.append(f"{path}:{node.lineno}")
            elif isinstance(node, ast.keyword) and node.arg == "channels":
                offenders.append(f"{path}:{getattr(node, 'lineno', '?')}")
    assert offenders == []
