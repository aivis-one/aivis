# =============================================================================
# AIVIS.ONE Backend -- no emitter names a comms channel (H23 P-112)
# =============================================================================
#
# comms 3.0.0 takes a notification's channel from the profile and refuses a
# request that names one. It refuses at SEND time, and a refused event is
# buried -- there is no redelivery (P-98) -- so an emitter carrying
# `channels` would lose login codes silently. This guards the emitters.
#
# WHERE THE SOURCE IS. This suite runs on the box from the app image, built
# out of ./backend: the package is /app/app and there is no repository
# around it. The scan therefore starts from the imported package itself,
# never from a path relative to this file -- that is how the first version
# of this file scanned a directory that does not exist in the image and
# passed on nothing. It is also why the comms profile's own rule is not
# checked here but in checks/comms_profile.py: comms-profile/ is not in the
# image at all.
# =============================================================================

import ast
from pathlib import Path

import app

_APP = Path(app.__file__).resolve().parent


def _scan() -> tuple[list[Path], list[str]]:
    """-> (files scanned, "path:line" of every place a channel is named)."""
    files = sorted(_APP.rglob("*.py"))
    offenders = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                if "channels" in keys:
                    offenders.append(f"{path}:{node.lineno}")
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == "channels"
                and isinstance(node.ctx, ast.Store)
            ):
                offenders.append(f"{path}:{node.lineno}")
            elif isinstance(node, ast.keyword) and node.arg == "channels":
                offenders.append(f"{path}:{getattr(node, 'lineno', '?')}")
    return files, offenders


def test_no_emitter_names_a_channel() -> None:
    """Every form a channel could be written in an event's data: a dict
    literal key, a subscript assignment, a keyword. comms refuses it.

    The pair of "none found": the scan saw the code it is about. Without
    it an empty or misplaced tree passes -- which is exactly how this test
    first reached the box.
    """
    files, offenders = _scan()

    scanned = {path.relative_to(_APP).as_posix() for path in files}
    assert "core/comms.py" in scanned
    assert "core/events/service.py" in scanned
    assert "modules/auth/service.py" in scanned
    assert len(files) > 100, f"only {len(files)} files under {_APP}"

    assert offenders == []
