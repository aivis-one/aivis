# =============================================================================
# AIVIS.ONE Backend -- the names in a person's profile have one rule (H43)
# =============================================================================
#
# profile.first_name and profile.last_name reach documents and e-mail
# letters, and comms refuses a letter over its limits. Every writer holds
# them to users/schemas.py profile_name_problem: a string of at most 100
# characters, counted raw -- before any cleaning. Here:
# PATCH /users/me (a 422) on all three axes, the seed's refusal, and the
# Telegram login's cap at the same number.
# =============================================================================

from typing import Any

import pytest
from httpx import AsyncClient

import scripts.seed as seed
from app.modules.users.schemas import (
    PROFILE_NAME_MAX_CHARS,
    clean_profile_text,
    profile_name_problem,
)
from tests.helpers import auth_headers, register_user

ME = "/api/v1/users/me"


async def _patch(
    client: AsyncClient, token: str, profile: dict[str, Any]
) -> Any:
    return await client.patch(
        ME, json={"profile": profile}, headers=auth_headers(token)
    )


def test_the_limit_is_the_telegram_logins() -> None:
    assert PROFILE_NAME_MAX_CHARS == 100


# ---------------------------------------------------------------------------
# PATCH /users/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["first_name", "last_name"])
async def test_exactly_100_characters_is_stored(client: AsyncClient, key: str) -> None:
    data = await register_user(client)
    name = "Я" * 100
    response = await _patch(client, data["session_token"], {key: name})
    assert response.status_code == 200, response.text
    assert response.json()["profile"][key] == name


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["first_name", "last_name"])
async def test_101_characters_is_a_422_and_nothing_is_stored(
    client: AsyncClient, key: str
) -> None:
    data = await register_user(client)
    token = data["session_token"]
    assert (await _patch(client, token, {key: "Anna"})).status_code == 200
    response = await _patch(client, token, {key: "A" * 101, "country": "DE"})
    assert response.status_code == 422, response.text
    assert key in response.text
    me = await client.get(ME, headers=auth_headers(token))
    assert me.json()["profile"][key] == "Anna"
    assert me.json()["profile"].get("country") != "DE"  # the whole patch refused


@pytest.mark.asyncio
async def test_the_length_is_counted_raw(client: AsyncClient) -> None:
    """Spaces and unprintable characters count: 100 characters with
    padding inside the 100 pass; 100 letters with any padding do not."""
    data = await register_user(client)
    token = data["session_token"]
    inside = " " + "B" * 98 + "\t"
    assert (await _patch(client, token, {"first_name": inside})).status_code == 200
    padded = await _patch(client, token, {"first_name": " " + "B" * 100})
    assert padded.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "   "])
async def test_an_empty_or_blank_name_behaves_as_before(
    client: AsyncClient, blank: str
) -> None:
    """Accepted and stored as given; the onboarding step still reads it as
    no name (not changed by H43)."""
    data = await register_user(client)
    response = await _patch(client, data["session_token"], {"last_name": blank})
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["last_name"] == blank


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, 7, ["Anna"], {"x": "y"}, True])
async def test_a_name_that_is_not_a_string_is_a_422(
    client: AsyncClient, value: Any
) -> None:
    data = await register_user(client)
    response = await _patch(client, data["session_token"], {"first_name": value})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_the_other_profile_keys_are_not_held_to_it(client: AsyncClient) -> None:
    data = await register_user(client)
    response = await _patch(client, data["session_token"], {"phone": "9" * 150})
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# The rule itself, the seed, the Telegram login
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "refused"),
    [
        ("x" * 100, False),
        ("x" * 101, True),
        ("\x01" * 50 + "x" * 100, True),
        (" " * 101, True),
        ("", False),
        ("   ", False),
        (None, True),
        (1, True),
    ],
)
def test_profile_name_problem(value: Any, refused: bool) -> None:
    """The length is counted raw: measured after cleaning, 100 visible
    characters could carry an invisible tail of any length, and that tail
    would reach the e-mail letters whose length comms limits. So 100 letters
    pass, and the same 100 behind 50 unprintable characters are refused."""
    assert (profile_name_problem("first_name", value) is not None) is refused


def test_the_seed_refuses_a_long_name_naming_where() -> None:
    with pytest.raises(seed.SeedRefusedError, match=r"investors\[0\]\.last_name"):
        seed._check_names({"last_name": "L" * 101}, "investors[0]")
    with pytest.raises(seed.SeedRefusedError, match="must be a string"):
        seed._check_names({"first_name": 5}, "staff[0]")
    seed._check_names({"first_name": "F" * 100, "last_name": ""}, "staff[0]")
    seed._check_names({}, "staff[0]")


def test_the_telegram_login_keeps_at_most_the_same_number() -> None:
    assert clean_profile_text("N" * 300, PROFILE_NAME_MAX_CHARS) == "N" * 100
    assert profile_name_problem(
        "first_name", clean_profile_text("N" * 300, PROFILE_NAME_MAX_CHARS)
    ) is None
