# =============================================================================
# AIVIS.ONE Backend -- Background tasks must survive an error response
# =============================================================================
#
# STAGE-III finding 20. A background task queued before a `raise` was silently
# discarded: FastAPI attaches BackgroundTasks to the response built from the
# endpoint's RETURN, and an endpoint that raises never builds one -- the
# response comes from aivis_error_handler, which created its own with no
# background at all.
#
# It had no symptom. The request still returned its 401, nothing 500'd, and
# the discarded writer swallowed its own errors by design. It cost this
# project its entire failed-login audit trail: measured on the live database
# before the fix, `select count(*) from audit_log where event =
# 'user.login_failed'` returned 0 for the whole life of the deployment.
#
# These tests pin the MECHANISM, deliberately without a database, a running
# server or the auth path. The end-to-end proof that the audit row now
# appears lives in test_auth_email.py; this file exists so that if someone
# later removes `background=` from the handler or drops the app-level
# dependency, the failure says exactly what broke instead of surfacing as a
# missing audit row three modules away.
# =============================================================================

import pytest
from fastapi import BackgroundTasks, Request

from app.core.exceptions import NotFoundError, RateLimitError
from app.main import aivis_error_handler, app


def _request_with(background_tasks: BackgroundTasks | None) -> Request:
    """Build a bare Request, optionally carrying published background tasks."""
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/anything",
            "headers": [],
            "query_string": b"",
            "state": {},
        }
    )
    if background_tasks is not None:
        request.state.background_tasks = background_tasks
    return request


@pytest.mark.asyncio
async def test_error_response_carries_published_background_tasks() -> None:
    """The whole point: a task queued before the raise reaches the response."""
    ran: list[str] = []

    tasks = BackgroundTasks()
    tasks.add_task(ran.append, "executed")

    response = await aivis_error_handler(
        _request_with(tasks), NotFoundError("nope")
    )

    assert response.background is tasks, (
        "aivis_error_handler dropped the request's background tasks -- this "
        "is STAGE-III finding 20 reopening; see app/core/background.py"
    )

    # And they are real, runnable tasks rather than an object that merely
    # travelled: execute them the way Starlette would.
    await response.background()
    assert ran == ["executed"]


@pytest.mark.asyncio
async def test_error_response_is_fine_when_nothing_was_published() -> None:
    """CONTROL. Without this, a handler that always attached SOME object
    would pass the test above, and a route that never queued anything would
    break in a way nothing here would notice."""
    response = await aivis_error_handler(_request_with(None), NotFoundError("x"))
    assert response.background is None
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_error_response_keeps_its_other_behaviour() -> None:
    """CONTROL on the change itself: adding `background=` must not disturb
    the status code, body or the Retry-After header the handler already
    produced. Asserted because this handler is the single funnel for every
    AivisError in the application."""
    exc = RateLimitError("slow down", retry_after_seconds=42)
    response = await aivis_error_handler(_request_with(None), exc)

    assert response.status_code == exc.status_code
    assert response.headers["Retry-After"] == "42"
    assert b"slow down" in response.body


def test_every_route_publishes_its_background_tasks() -> None:
    """The app-level dependency is what makes the fix general rather than a
    per-route convention nobody will remember. If it is ever removed, the
    trap re-arms silently for whoever adds the next task-before-raise.

    Asserted over every mounted route, with the count reported, so a partial
    regression is as visible as a total one.
    """
    from fastapi.routing import APIRoute

    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    missing = [
        f"{sorted(r.methods)[0]} {r.path}"
        for r in routes
        if not any(
            getattr(d.call, "__name__", "") == "publish_background_tasks"
            for d in r.dependant.dependencies
        )
    ]

    assert routes, "no APIRoutes mounted -- the probe itself is broken"
    assert not missing, (
        f"{len(missing)} of {len(routes)} routes do not publish their "
        f"background tasks: {missing[:10]}"
    )
