# =============================================================================
# AIVIS.ONE Backend -- support change of a user's email (H28 P-105)
# =============================================================================
#
# PATCH /api/v1/staff/users/{id}/email -- the only way an address changes:
# a staff ADMIN sets it, with a reason, after establishing the person's
# identity. The user has no self-service path (owner's decision).
#
# Every refusal is paired with "nothing was written": the target keeps its
# address and no user.email_changed audit row exists. The success test is
# the other half of the pair: the new address logs in, the old one does
# not, and the audit row records both with the reason.
#
# Axes:
#   REPEAT    -- the current address in another case; another account's
#                address in another case
#   EMPTINESS -- empty / blank / missing reason; empty address; a user
#                with no email at all (Telegram-only)
#   SHORTAGE  -- an address without "@", without a domain, with a space
# =============================================================================

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_platform_user_id
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    login_telegram,
    register_user,
)

_REASON = "Identity checked by support against the passport on file."
_PASSWORD = "Password123!"


async def _user(session: AsyncSession, user_id: str | UUID) -> User:
    session.expire_all()
    result = await session.execute(select(User).where(User.id == UUID(str(user_id))))
    return result.scalar_one()


async def _audit_rows(
    session: AsyncSession, user_id: str | UUID
) -> list[dict[str, Any]]:
    rows = await session.execute(
        text(
            "SELECT data FROM audit_log WHERE event = 'user.email_changed' "
            "AND target_id = :uid ORDER BY created_at"
        ),
        {"uid": str(user_id)},
    )
    return [row[0] for row in rows]


async def _change(
    client: AsyncClient, token: str, user_id: str | UUID, body: dict[str, Any]
):
    return await client.patch(
        f"/api/v1/staff/users/{user_id}/email",
        json=body,
        headers=auth_headers(token),
    )


def _new_address() -> str:
    return f"moved_{uuid4().hex[:12]}@example.com"


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_changes_the_address(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The new address is stored lower-cased and verified, logs in with the
    old password; the old address no longer logs in; the audit row carries
    both addresses and the reason."""
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)
    user_id = data["user"]["id"]
    old_email = data["email"]
    new_email = _new_address()

    response = await _change(
        client, admin_token, user_id,
        {"email": f"  {new_email.upper()}  ".strip(), "reason": _REASON},
    )
    assert response.status_code == 204, response.text

    user = await _user(db_session, user_id)
    assert user.email == new_email
    assert user.credentials["email"]["verified"] is True
    assert user.credentials["email"]["verified_at"]
    # The password survives the change -- only the address moved.
    assert user.credentials["email"]["password_hash"]

    new_login = await client.post(
        "/api/v1/auth/email/login",
        json={"email": new_email, "password": _PASSWORD},
    )
    assert new_login.status_code == 200, new_login.text
    old_login = await client.post(
        "/api/v1/auth/email/login",
        json={"email": old_email, "password": _PASSWORD},
    )
    assert old_login.status_code == 401

    rows = await _audit_rows(db_session, user_id)
    assert rows == [
        {"old_email": old_email, "new_email": new_email, "reason": _REASON}
    ]


@pytest.mark.asyncio
async def test_a_pending_verification_code_is_removed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Registration leaves a verification code that was sent to the OLD
    address; the change removes it with that address, and leaves nothing
    else of onboarding behind under those keys."""
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)
    user_id = data["user"]["id"]

    before = (await _user(db_session, user_id)).credentials.get("onboarding") or {}
    assert before.get("email_token")  # the pair: there IS a code to remove

    response = await _change(
        client, admin_token, user_id, {"email": _new_address(), "reason": _REASON}
    )
    assert response.status_code == 204, response.text

    after = (await _user(db_session, user_id)).credentials.get("onboarding") or {}
    for key in ("email_token", "email_token_expires_at", "email_verification_attempts"):
        assert key not in after


@pytest.mark.asyncio
async def test_admin_changes_another_staff_members_address(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Another staff account is an allowed target -- only one's own is not."""
    _admin, admin_token = await create_admin_user(client, db_session)
    colleague, _token = await create_staff_user(client, db_session)
    new_email = _new_address()

    response = await _change(
        client, admin_token, colleague.id, {"email": new_email, "reason": _REASON}
    )
    assert response.status_code == 204, response.text
    assert (await _user(db_session, colleague.id)).email == new_email


# ---------------------------------------------------------------------------
# Refusals -- each with "nothing was written"
# ---------------------------------------------------------------------------


async def _assert_untouched(
    session: AsyncSession, user_id: str | UUID, email: str | None
) -> None:
    assert (await _user(session, user_id)).email == email
    assert await _audit_rows(session, user_id) == []


@pytest.mark.asyncio
async def test_non_admin_staff_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff with the default permissions is not an admin -> 403."""
    _staff, staff_token = await create_staff_user(client, db_session)
    data = await register_user(client)

    response = await _change(
        client, staff_token, data["user"]["id"],
        {"email": _new_address(), "reason": _REASON},
    )
    assert response.status_code == 403
    await _assert_untouched(db_session, data["user"]["id"], data["email"])


@pytest.mark.asyncio
async def test_non_staff_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An ordinary user cannot reach the endpoint at all -> 403."""
    caller = await register_user(client)
    data = await register_user(client)

    response = await _change(
        client, caller["session_token"], data["user"]["id"],
        {"email": _new_address(), "reason": _REASON},
    )
    assert response.status_code == 403
    await _assert_untouched(db_session, data["user"]["id"], data["email"])


@pytest.mark.asyncio
async def test_own_address_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An admin changing their own address is the self-service path the
    product removed -> 400."""
    admin, admin_token = await create_admin_user(client, db_session)
    old_email = admin.email

    response = await _change(
        client, admin_token, admin.id, {"email": _new_address(), "reason": _REASON}
    )
    assert response.status_code == 400
    await _assert_untouched(db_session, admin.id, old_email)


@pytest.mark.asyncio
async def test_unknown_user_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _admin, admin_token = await create_admin_user(client, db_session)
    response = await _change(
        client, admin_token, uuid4(), {"email": _new_address(), "reason": _REASON}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_platform_user_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _admin, admin_token = await create_admin_user(client, db_session)
    platform_id = await get_platform_user_id(db_session)
    before = (await _user(db_session, platform_id)).email

    response = await _change(
        client, admin_token, platform_id, {"email": _new_address(), "reason": _REASON}
    )
    assert response.status_code == 400
    await _assert_untouched(db_session, platform_id, before)


@pytest.mark.asyncio
async def test_telegram_only_user_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No address to change: giving one would ADD a login method -> 400."""
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await login_telegram(client, telegram_id=int(uuid4().int % 10**9) + 10**9)
    user_id = data["user"]["id"]

    response = await _change(
        client, admin_token, user_id, {"email": _new_address(), "reason": _REASON}
    )
    assert response.status_code == 400
    await _assert_untouched(db_session, user_id, None)


@pytest.mark.asyncio
async def test_the_current_address_in_another_case_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nothing to change -> 400, and no empty audit row."""
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)

    response = await _change(
        client, admin_token, data["user"]["id"],
        {"email": data["email"].upper(), "reason": _REASON},
    )
    assert response.status_code == 400
    await _assert_untouched(db_session, data["user"]["id"], data["email"])


@pytest.mark.asyncio
async def test_an_address_of_another_account_is_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Taken by another account, in any case -> 409; both accounts keep
    their own address."""
    _admin, admin_token = await create_admin_user(client, db_session)
    target = await register_user(client)
    other = await register_user(client)

    response = await _change(
        client, admin_token, target["user"]["id"],
        {"email": other["email"].upper(), "reason": _REASON},
    )
    assert response.status_code == 409
    await _assert_untouched(db_session, target["user"]["id"], target["email"])
    assert (await _user(db_session, other["user"]["id"])).email == other["email"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email", ["", "no-at-sign", "user@", "@example.com", "two words@example.com"]
)
async def test_a_malformed_address_is_422(
    client: AsyncClient, db_session: AsyncSession, email: str
) -> None:
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)

    response = await _change(
        client, admin_token, data["user"]["id"], {"email": email, "reason": _REASON}
    )
    assert response.status_code == 422
    await _assert_untouched(db_session, data["user"]["id"], data["email"])


@pytest.mark.asyncio
@pytest.mark.parametrize("body_reason", ["", "   ", None])
async def test_a_missing_or_blank_reason_is_422(
    client: AsyncClient, db_session: AsyncSession, body_reason: str | None
) -> None:
    _admin, admin_token = await create_admin_user(client, db_session)
    data = await register_user(client)
    body: dict[str, Any] = {"email": _new_address()}
    if body_reason is not None:
        body["reason"] = body_reason

    response = await _change(client, admin_token, data["user"]["id"], body)
    assert response.status_code == 422
    await _assert_untouched(db_session, data["user"]["id"], data["email"])
