# =============================================================================
# AIVIS.ONE Backend -- Client IP helper (TASK-6 4.1a, 2026-08-27)
# =============================================================================
#
# Pins the semantics of core.client_ip.get_client_ip, the single
# Request-layer spelling that replaced five copy-pasted _get_client_ip
# helpers plus one inline read (STAGE-III-FINDINGS.md #14). Pure unit
# tests -- no DB, no HTTP -- built on a hand-rolled ASGI scope.
#
# The empty-header case is the one that matters most: documents/router.py
# used to read `.get("X-Real-IP", <fallback>)`, whose default-arg form
# returns "" for a present-but-empty header instead of falling through to
# the peer. The consolidation unified to the truthiness form; this test
# asserts an empty header now behaves like an absent one everywhere.
# =============================================================================

from starlette.requests import Request

from app.core.client_ip import get_client_ip


def _request(headers: dict[str, str], client: tuple[str, int] | None) -> Request:
    """Build a minimal ASGI-scoped Request for the helper under test."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in headers.items()
        ],
        "client": client,
    }
    return Request(scope)


def test_prefers_x_real_ip_over_peer() -> None:
    """X-Real-IP (nginx's unspoofable header) wins over the peer."""
    req = _request({"X-Real-IP": "1.2.3.4"}, ("9.9.9.9", 5000))
    assert get_client_ip(req) == "1.2.3.4"


def test_falls_back_to_peer_when_header_absent() -> None:
    """No X-Real-IP (dev/test, no nginx) -> the ASGI peer host."""
    req = _request({}, ("9.9.9.9", 5000))
    assert get_client_ip(req) == "9.9.9.9"


def test_empty_header_falls_through_to_peer() -> None:
    """A present-but-empty X-Real-IP falls through -- the documents/router
    inconsistency this consolidation fixed."""
    req = _request({"X-Real-IP": ""}, ("9.9.9.9", 5000))
    assert get_client_ip(req) == "9.9.9.9"


def test_unknown_when_no_peer_and_no_header() -> None:
    """No header and no ASGI peer (some test transports) -> 'unknown',
    never a crash on request.client being None."""
    req = _request({}, None)
    assert get_client_ip(req) == "unknown"
