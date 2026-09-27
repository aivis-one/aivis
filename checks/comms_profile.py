"""A type the comms profile routes to email carries no category.

WHY THIS EXISTS. In comms a `category` is the mute gate: a person can switch
a category off in their notification settings, and every type in it goes
silent for them. A type WITHOUT a category bypasses that gate. So a category
written on a type that carries a login code, a password reset or a signed
document would be valid for comms -- its loader accepts it -- and would let a
person switch off the mail they need to get into their own account. Nothing
else guards this: comms cannot know which of our types must not be mutable,
and the product's test suite runs from an image built out of ./backend, where
comms-profile/ does not exist. This is our requirement of comms, written in
the H23 handover.

The types it stands on today (comms-profile/types.yaml, H23): the ones whose
`channels` include email -- auth.verification_code, auth.password_reset,
purchase.agreement, ownership.certificate. The rule is stated on the
PROPERTY (routed to email), not on that list, so a new email type is held to
it without editing this file.

WHAT IT DOES NOT CHECK, on purpose: the document's shape (version, types
under `types:`) and which types route where. The comms loader refuses to
start on a malformed profile -- loudly, on the first `aivis update` -- and a
second copy of its schema here would drift from it. Which types go to email
is data, not a property.

STANDARD LIBRARY ONLY, like every check here, so no YAML parser. The reader
understands exactly the block form this file is written in -- a type key at
two spaces under `types:`, its fields at four -- and treats ANY other line
inside `types:` as a failure, never as something to skip. A flow mapping or
a reindented record fails loudly instead of slipping past.
"""
from __future__ import annotations

import os
import re

PROFILE = os.path.join("comms-profile", "types.yaml")

TYPE_LINE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
FIELD_LINE = re.compile(r"^    ([A-Za-z0-9_-]+):\s*(.*?)\s*$")
FLOW_LIST = re.compile(r"^\[(.*)\]$")


def parse(text: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """-> ({type_key: {field: raw value}}, [lines it could not read])."""
    types: dict[str, dict[str, str]] = {}
    unread: list[str] = []
    inside = False
    current: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" "):
            inside = line.rstrip() == "types:"
            current = None
            continue
        if not inside:
            continue
        match = TYPE_LINE.match(line)
        if match:
            current = match.group(1)
            types[current] = {}
            continue
        match = FIELD_LINE.match(line)
        if match and current is not None:
            types[current][match.group(1)] = match.group(2)
            continue
        unread.append("line %d: %s" % (number, line.rstrip()))
    return types, unread


def channels_of(raw: str) -> list[str]:
    match = FLOW_LIST.match(raw)
    if match is None:
        return [raw.strip()] if raw.strip() else []
    return [part.strip() for part in match.group(1).split(",") if part.strip()]


def violations(types: dict[str, dict[str, str]]) -> tuple[list[str], list[str]]:
    """-> (email types, email types that carry a category)."""
    email = sorted(
        key for key, fields in types.items()
        if "email" in channels_of(fields.get("channels", ""))
    )
    bad = [key for key in email if "category" in types[key]]
    return email, bad


def run(root: str) -> tuple[bool, list[str]]:
    with open(os.path.join(root, PROFILE), encoding="utf-8") as handle:
        types, unread = parse(handle.read())
    email, bad = violations(types)
    lines = [
        "types read under `types:`                     : %d" % len(types),
        "types routed to email                         : %d (%s)"
        % (len(email), ", ".join(email) or "none"),
    ]
    ok = True
    if unread:
        ok = False
        lines.append("lines inside `types:` this check cannot read -- refusing to guess:")
        lines += ["  " + item for item in unread]
    if not types or not email:
        # The pair of "no email type has a category": there are email types
        # to look at. An empty read would make the rule true of nothing.
        ok = False
        lines.append("no types, or no type routed to email, were read -- nothing was checked")
    if bad:
        ok = False
        lines.append("email types that carry a category (a person could mute them):")
        lines += ["  " + key for key in bad]
    elif ok:
        lines.append("no type routed to email carries a category")
    return ok, lines


def _run_on(text: str) -> bool:
    """run() against a throwaway root holding only this profile."""
    import tempfile

    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "comms-profile"))
    with open(os.path.join(root, PROFILE), "w", encoding="utf-8") as handle:
        handle.write(text)
    ok, _ = run(root)
    return ok


def selftest(root: str) -> list[str]:
    out = []
    with open(os.path.join(root, PROFILE), encoding="utf-8") as handle:
        real = handle.read()
    anchor = "    channels: [email]\n"
    assert anchor in real, "the real profile has no `channels: [email]` line to plant on"

    assert _run_on(real), "a copy of the real profile does not pass"
    out.append("  a copy of the real profile passes")

    planted = real.replace(anchor, anchor + "    category: security\n", 1)
    assert not _run_on(planted), "an email type with a category was not refused"
    out.append("  refuses a category planted on a type routed to email")

    flow = real.replace(anchor, "    {channels: [email]}\n", 1)
    assert not _run_on(flow), "a record in a form the reader cannot read was skipped"
    out.append("  refuses a record written in a form it cannot read")

    no_email = real.replace("email]", "in_app]").replace(", email", "")
    assert not _run_on(no_email), "a profile with no email type passed -- nothing was checked"
    out.append("  refuses a read that finds no type routed to email (the pair)")

    ok, _ = run(root)
    assert ok, "the real tree does not pass its own comms profile check"
    out.append("  the real tree passes")
    return out
