# =============================================================================
# AIVIS.ONE Backend -- Telegram entry: the profile filled from Telegram
# =============================================================================
#
# At the Telegram entry and at the link confirmation the Telegram photo goes to
# profile.avatar_url and the Telegram names to profile.first_name and
# profile.last_name -- where those are empty, and never over a value the person
# already holds. Pure function, no database: a stand-in row records its writes.
# =============================================================================

from app.modules.auth.service import _fill_profile_from_telegram


class FakeUser:
    """The two things the function touches: the profile and set_jsonb."""

    def __init__(self, profile: dict | None) -> None:
        self.profile = profile
        self.writes = 0

    def set_jsonb(self, field: str, value: dict) -> None:
        assert field == "profile"
        self.profile = value
        self.writes += 1


TELEGRAM = {
    "id": 1,
    "first_name": "Anna",
    "last_name": "Petrova",
    "photo_url": "https://photos.example.org/anna.jpg",
}


def test_fills_empty_profile_from_telegram() -> None:
    user = FakeUser({})
    _fill_profile_from_telegram(user, TELEGRAM)  # type: ignore[arg-type]
    assert user.profile == {
        "first_name": "Anna",
        "last_name": "Petrova",
        "avatar_url": "https://photos.example.org/anna.jpg",
    }


def test_fills_a_row_with_no_profile_at_all() -> None:
    user = FakeUser(None)
    _fill_profile_from_telegram(user, TELEGRAM)  # type: ignore[arg-type]
    assert user.profile is not None
    assert user.profile["avatar_url"].endswith("anna.jpg")


def test_never_overwrites_what_is_set() -> None:
    held = {
        "first_name": "Ann",
        "last_name": "Smith",
        "avatar_url": "https://example.com/mine.png",
        "country": "GE",
    }
    user = FakeUser(dict(held))
    _fill_profile_from_telegram(user, TELEGRAM)  # type: ignore[arg-type]
    assert user.profile == held
    assert user.writes == 0


def test_fills_only_what_is_missing_and_keeps_other_keys() -> None:
    user = FakeUser({"first_name": "Ann", "country": "GE"})
    _fill_profile_from_telegram(user, TELEGRAM)  # type: ignore[arg-type]
    assert user.profile == {
        "first_name": "Ann",
        "country": "GE",
        "last_name": "Petrova",
        "avatar_url": "https://photos.example.org/anna.jpg",
    }


def test_nothing_known_in_telegram_writes_nothing() -> None:
    user = FakeUser({})
    _fill_profile_from_telegram(user, {"id": 1, "first_name": None, "photo_url": None})  # type: ignore[arg-type]
    assert user.profile == {}
    assert user.writes == 0


def test_a_photo_that_is_not_a_web_address_is_not_copied() -> None:
    user = FakeUser({})
    _fill_profile_from_telegram(
        user, {"id": 1, "photo_url": "javascript:alert(1)"}  # type: ignore[arg-type]
    )
    assert user.profile == {}


def test_names_are_trimmed_and_stripped_of_control_characters() -> None:
    user = FakeUser({})
    _fill_profile_from_telegram(
        user, {"id": 1, "first_name": "  An\x00na \n", "last_name": "   "}  # type: ignore[arg-type]
    )
    assert user.profile == {"first_name": "Anna"}
