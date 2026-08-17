# =============================================================================
# AIVIS.ONE Backend -- Background tasks that survive an error response
# =============================================================================
#
# THE DEFECT THIS EXISTS FOR (STAGE-III finding 20, 2026-08-17):
#   FastAPI attaches the BackgroundTasks collected by the dependency system
#   to the response built from the endpoint's RETURN VALUE. When the endpoint
#   RAISES instead, the response is built by an exception handler, and every
#   task queued before the raise is discarded -- silently, with no warning at
#   import time, at request time, or in any log.
#
#   That cost this project its entire failed-login audit trail. SEC-7 queued
#   `_audit_login_failure` and raised UnauthorizedError on the very next line,
#   at all three call sites. Measured on the LIVE database before the fix:
#     select count(*), max(created_at) from audit_log
#       where event = 'user.login_failed';
#     -> 0 | NULL, over the whole life of the deployment.
#   Nothing failed, nothing 500'd, the login still returned 401, and the
#   writer swallowed its own errors by design. There was no symptom to see.
#
# WHY NOT JUST AWAIT THE WRITE INSTEAD:
#   Because the scheduling is itself a security fix (TASK-6 4.1c). An audit
#   INSERT+COMMIT inside the request runs ONLY on the known-email branches,
#   which re-opens the user-enumeration timing oracle that the dummy-hash
#   equalizer on the unknown-email branch exists to close. The write has to
#   stay OFF the request path, so the mechanism is repaired rather than
#   routed around.
#
# WHY THIS SHAPE AND NOT A TYPED DEPENDENCY:
#   The obvious form -- `background_tasks: BackgroundTasks = Depends(...)` --
#   is REJECTED BY FASTAPI at import time: "Cannot specify `Depends` for type
#   BackgroundTasks". It resolves that type itself and refuses to share the
#   parameter. So this is a side-effect-only dependency that takes the same
#   instance FastAPI already built and publishes it; endpoints keep their
#   plain `background_tasks: BackgroundTasks` parameter, untouched.
#
# WHY IT IS REGISTERED APP-WIDE RATHER THAN PER ROUTE:
#   Per-route opt-in leaves the trap armed for whoever adds the next
#   background task before a raise -- and that person will pay what this cost
#   to find: a silent, symptomless hole. One app-level dependency disarms it
#   everywhere with no convention for anyone to remember. The cost is one
#   attribute assignment per request.
# =============================================================================

from fastapi import BackgroundTasks, Request


async def publish_background_tasks(
    request: Request,
    background_tasks: BackgroundTasks,
) -> None:
    """Publish this request's BackgroundTasks where an error handler can reach.

    FastAPI builds one BackgroundTasks instance per request and injects the
    SAME instance everywhere it is requested, so what an endpoint queues is
    what `aivis_error_handler` finds here.

    Success path is unchanged: FastAPI runs the tasks from the endpoint's own
    response. Exactly one response is produced per request, so nothing can
    run twice.
    """
    request.state.background_tasks = background_tasks
