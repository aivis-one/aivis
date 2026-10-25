# =============================================================================
# AIVIS.ONE Backend tests -- a stateful fake comms for the support suites (H40)
# =============================================================================
#
# One stand-in behind every seam support reaches comms through -- the
# service, the translation module, the spam bin, the operator mutes and the
# bell (notifications/service.py) -- replacing `comms_request` itself, the
# way test_support_translation.py has since H39. It keeps the state the
# product leans on and refuses what comms refuses, in comms' classes:
#
#   threads    -- created fresh per `ticket` call; the Idempotency-Key
#                 replays the same answer, and the same key with another
#                 body is a 409 conflict (comms deploy/INTEGRATION.md
#                 section 5);
#   messages   -- posted by the thread's client or ASSIGNEE only (403
#                 forbidden otherwise -- can_post_message); a client's
#                 message reopens a resolved/closed thread; read newest
#                 first with an offset cursor;
#   claim      -- "is it yours now": the holder again is a success, anyone
#                 else a 409 conflict; off the roster a 403;
#   assign     -- the assignee must be on the roster (422 validation);
#   release    -- back to nobody;
#   status     -- comms 3.11's manual matrix (section 14):
#                 open -> resolved|closed, resolved -> open|closed,
#                 closed -> open; the same status is a no-op; else 422;
#   DELETE     -- 204 (None) for a thread there or not (idempotent);
#   read       -- per participant; unread-counts for the client's threads;
#   recipients -- known by id (the address book); preferences of an
#                 unknown one are a 404 not_found; PATCH merges categories
#                 and refuses an unknown one (422);
#   inbox      -- deliveries made by `deliver()` under comms' MUTE RULE: a
#                 type whose category the recipient turned off creates no
#                 delivery. The rule is comms'; what the tests check with
#                 it is the product's side -- that the mute was set.
#
# A call to a path the fake does not know is an AssertionError: a plausible
# default would let a test pass against a service this one is not.
# =============================================================================

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.core.comms import CommsRejectedError, CommsUnavailableError

SEAMS = (
    "app.modules.support.service.comms_request",
    "app.modules.support.translation.comms_request",
    "app.modules.support.purge.comms_request",
    "app.modules.support.mute.comms_request",
    "app.modules.notifications.service.comms_request",
)

SECTION_ID = "5ec7a000-0000-4000-8000-0000000000a1"

# The categories the profile declares (comms-profile/types.yaml).
CATEGORIES = (
    "agent_applications",
    "commissions",
    "deposits",
    "installments",
    "kyc",
    "payments",
    "purchases",
    "staff_messages",
    "support_messages",
)

# The manual status matrix of comms 3.11 (INTEGRATION.md section 14).
_ALLOWED: dict[str, set[str]] = {
    "open": {"resolved", "closed"},
    "resolved": {"open", "closed"},
    "closed": {"open"},
}


def refuse(status: int, error_class: str) -> CommsRejectedError:
    return CommsRejectedError(status_code=status, error_class=error_class)


class FakeComms:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.threads: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}  # newest first
        self.read_at: dict[tuple[str, str], int] = {}  # (thread, who) -> seen
        self.roster: set[str] = set()
        self.recipients: set[str] = set()
        self.preferences: dict[str, dict[str, bool]] = {}
        self.inbox: dict[str, list[dict[str, Any]]] = {}  # newest first
        self._keys: dict[tuple[str, str, str], tuple[str, Any]] = {}
        self._clock = datetime(2026, 10, 25, 12, tzinfo=UTC)
        # Armed by a test: every call raises CommsUnavailableError.
        self.down = False
        # Armed by a test: (method, path suffix) -> the exception raised.
        self.fail: dict[tuple[str, str], Exception] = {}

    # -- what the tests read ------------------------------------------------
    def calls_to(self, method: str, suffix: str) -> list[dict[str, Any]]:
        return [
            c
            for c in self.calls
            if c["method"] == method and c["path"].endswith(suffix)
        ]

    def tick(self) -> str:
        self._clock += timedelta(seconds=1)
        return self._clock.isoformat()

    # -- what the tests do to it --------------------------------------------
    def know(self, *recipient_ids: Any) -> None:
        """Recipients comms has in its address book."""
        self.recipients.update(str(r) for r in recipient_ids)

    def serve(self, *operator_ids: Any) -> None:
        """Operators on the support section's roster."""
        self.roster.update(str(o) for o in operator_ids)
        self.know(*operator_ids)

    def add_thread(
        self,
        *,
        client: Any,
        kind: str = "dm",
        assignee: Any = None,
        status: str = "open",
    ) -> str:
        thread_id = str(uuid4())
        self.threads[thread_id] = {
            "id": thread_id,
            "client": str(client),
            "operator_kind": "section",
            "operator_value": SECTION_ID,
            "kind": kind,
            "status": status,
            "assignee": str(assignee) if assignee is not None else None,
        }
        return thread_id

    def post(self, thread_id: str, sender: Any, body: str) -> dict[str, Any]:
        """A message written straight into comms (setup, not the product)."""
        message = {
            "id": str(uuid4()),
            "thread_id": thread_id,
            "sender": str(sender),
            "body": body,
            "created_at": self.tick(),
        }
        self.messages.setdefault(thread_id, []).insert(0, message)
        return message

    def deliver(self, *, type: str, category: str | None, recipient: Any) -> bool:
        """comms delivering one in_app notification, by its mute rule: a
        category the recipient turned off creates no delivery."""
        rid = str(recipient)
        if (
            category is not None
            and self.preferences.get(rid, {}).get(category) is False
        ):
            return False
        self.inbox.setdefault(rid, []).insert(
            0,
            {
                "id": str(uuid4()),
                "type": type,
                "title": type,
                "body": type,
                "action_data": None,
                "sent_at": self.tick(),
                "read_at": None,
                "created_at": self._clock.isoformat(),
            },
        )
        return True

    # -- comms ---------------------------------------------------------------
    async def __call__(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        forward_403: bool = False,
        idempotency_key: str | None = None,
        forward_cursor_expired: bool = False,
    ) -> Any:
        params = dict(params or {})
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json,
                "key": idempotency_key,
                "forward_403": forward_403,
            }
        )
        if self.down:
            raise CommsUnavailableError()
        for (m, suffix), exc in self.fail.items():
            if m == method and path.endswith(suffix):
                raise exc
        if idempotency_key is not None:
            fingerprint = _dumps(json)
            stored = self._keys.get((method, path, idempotency_key))
            if stored is not None:
                if stored[0] != fingerprint:
                    raise refuse(409, "conflict")
                return stored[1]
            result = self._route(method, path, params, json or {}, forward_403)
            self._keys[(method, path, idempotency_key)] = (fingerprint, result)
            return result
        return self._route(method, path, params, json or {}, forward_403)

    def _route(
        self, method: str, path: str, params: dict, body: dict, forward_403: bool
    ) -> Any:
        parts = path.strip("/").split("/")
        if path == "/api/v1/sections":
            return {"id": SECTION_ID, "key": "support", "label": "Support"}

        if parts[:3] == ["api", "v1", "recipients"]:
            return self._recipient(method, parts[3:], params, body)

        if path == "/api/v1/threads" and method == "POST":
            client = str(body.get("client"))
            if client not in self.recipients:
                raise refuse(404, "not_found")
            thread_id = self.add_thread(client=client, kind=str(body.get("kind")))
            return dict(self.threads[thread_id])

        if path == "/api/v1/threads/unread-counts":
            who = str(body.get("participant"))
            return {
                "counts": {
                    tid: self._unread(tid, who)
                    for tid in body.get("thread_ids", [])
                    if tid in self.threads
                }
            }

        if parts[:3] == ["api", "v1", "threads"] and len(parts) >= 4:
            thread = self.threads.get(parts[3])
            if method == "DELETE" and len(parts) == 4:
                self.threads.pop(parts[3], None)
                self.messages.pop(parts[3], None)
                return None
            if thread is None:
                raise refuse(404, "not_found")
            verb = parts[4] if len(parts) > 4 else ""
            if verb == "messages" and len(parts) == 5 and method == "POST":
                return self._post(thread, body, forward_403)
            if verb == "messages" and len(parts) == 5 and method == "GET":
                return self._feed(thread, params)
            if verb == "read":
                who = str(body.get("participant"))
                self.read_at[(thread["id"], who)] = len(
                    self.messages.get(thread["id"], [])
                )
                return {"unread": 0}
            if verb == "claim":
                return self._claim(thread, str(body.get("operator")))
            if verb == "assign":
                return self._assign(
                    thread, str(body.get("operator")), str(body.get("assignee"))
                )
            if verb == "release":
                self._on_roster(str(body.get("operator")))
                thread["assignee"] = None
                return dict(thread)
            if verb == "status":
                return self._status(
                    thread, str(body.get("operator")), str(body.get("status"))
                )

        raise AssertionError(f"fake comms has no route for {method} {path}")

    # -- threads ---------------------------------------------------------------
    def _on_roster(self, operator: str) -> None:
        if operator not in self.roster:
            raise refuse(403, "forbidden")

    def _unread(self, thread_id: str, who: str) -> int:
        rows = self.messages.get(thread_id, [])
        seen = self.read_at.get((thread_id, who), 0)
        newer = rows[: max(len(rows) - seen, 0)]
        return sum(1 for m in newer if m["sender"] != who)

    def _post(self, thread: dict, body: dict, forward_403: bool) -> dict:
        sender = str(body.get("sender"))
        if sender not in (thread["client"], thread["assignee"]):
            raise refuse(403, "forbidden")
        if sender == thread["client"] and thread["status"] != "open":
            thread["status"] = "open"  # a client's message reopens the thread
        return self.post(thread["id"], sender, str(body.get("body")))

    def _feed(self, thread: dict, params: dict) -> dict:
        rows = self.messages.get(thread["id"], [])
        start = int(params.get("cursor") or 0)
        limit = int(params.get("limit") or 20)
        page = rows[start : start + limit]
        more = start + limit < len(rows)
        items = []
        for message in page:
            item = dict(message)
            if params.get("locale") is not None:
                item["variant_state"] = "not_needed"
                item["variant"] = None
            items.append(item)
        return {"items": items, "next_cursor": str(start + limit) if more else None}

    def _claim(self, thread: dict, operator: str) -> dict:
        self._on_roster(operator)
        if thread["assignee"] is None:
            thread["assignee"] = operator
        if thread["assignee"] != operator:
            raise refuse(409, "conflict")
        return {"claimed": True, "thread": dict(thread)}

    def _assign(self, thread: dict, operator: str, assignee: str) -> dict:
        self._on_roster(operator)
        if assignee not in self.roster:
            raise refuse(422, "validation")
        thread["assignee"] = assignee
        return dict(thread)

    def _status(self, thread: dict, operator: str, target: str) -> dict:
        self._on_roster(operator)
        if target == thread["status"]:
            return dict(thread)
        if target not in _ALLOWED[thread["status"]]:
            raise refuse(422, "validation")
        thread["status"] = target
        return dict(thread)

    # -- recipients: preferences and the inbox ----------------------------------
    def _recipient(self, method: str, rest: list[str], params: dict, body: dict) -> Any:
        rid = rest[0]
        if len(rest) == 1:  # the address book itself
            self.recipients.add(rid)
            return {}
        if rid not in self.recipients:
            raise refuse(404, "not_found")
        if rest[1] == "preferences":
            prefs = self.preferences.setdefault(rid, dict.fromkeys(CATEGORIES, True))
            if method == "PATCH":
                cats = body.get("categories") or {}
                if any(c not in CATEGORIES for c in cats):
                    raise refuse(422, "validation")
                prefs.update(cats)
            return {
                "categories": dict(sorted(prefs.items())),
                "schedule": None,
                "timezone": None,
            }
        if rest[1] == "inbox":
            rows = self.inbox.get(rid, [])
            unread = sum(1 for r in rows if r["read_at"] is None)
            if len(rest) == 2:
                limit = int(params.get("limit") or 20)
                return {"items": rows[:limit], "next_cursor": None, "unread": unread}
            if rest[2] == "unread-count":
                return {"unread": unread}
        raise AssertionError(
            f"fake comms has no route for {method} /recipients/{'/'.join(rest)}"
        )


def _dumps(body: Any) -> str:
    return json.dumps(body, sort_keys=True, default=str)


def install(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    """The fake behind every support seam, and a configured comms address
    (the emitters write outbox rows only when comms is configured). Each
    suite wraps it in its own `comms` fixture."""
    from app.core.comms import UpsertOutcome
    from app.core.config import settings
    from app.modules.support import service

    fake = FakeComms()
    for seam in SEAMS:
        monkeypatch.setattr(seam, fake)

    # Registration upserts the recipient synchronously (core/comms_sync.py).
    # Here that call joins the fake's address book and succeeds, so a test
    # never leaves a user_upserted outbox row behind for the relay suite
    # to count.
    async def _upsert(user_id: Any, snapshot: Any) -> UpsertOutcome:
        fake.recipients.add(str(user_id))
        return UpsertOutcome.STORED

    monkeypatch.setattr("app.core.comms_sync.upsert_recipient", _upsert)
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    monkeypatch.setattr(settings, "comms_service_token", "h40-token")
    monkeypatch.setattr(settings, "support_language", "en")
    monkeypatch.setattr(service, "_support_section_id", None)
    return fake
