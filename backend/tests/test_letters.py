# =============================================================================
# AIVIS.ONE Backend -- the e-mail letter builder (app/letters, H43)
# =============================================================================
#
# The builder over copy.yaml and the five layouts: every type is built in
# both languages; the two parts say the same words; data is HTML-escaped in
# the html part and left as it is in the text part; a missing value refuses,
# an empty one does not; NUL never reaches the request; the language maps
# onto en/ru; and the loader refuses a broken copy.yaml at import.
#
# Pure: no database, no network. The emitters' side -- each of the twelve
# requests carries the block -- is tests/test_email_letters.py.
# =============================================================================

import re
import string
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import settings
from app.letters import (
    COMMON,
    LANGUAGES,
    LAYOUTS,
    TYPES,
    CopyError,
    LetterError,
    build_letter,
    letter_language,
    letter_request,
    load_copy,
)

_COPY = (Path(__file__).resolve().parents[1] / "app" / "letters" / "copy.yaml")

# One value for every variable any letter names; the strings are chosen so
# that each is findable in a letter and none is a substring of a word.
FIELDS: dict[str, Any] = {
    "code": "482915",
    "minutes": 17,
    "reset_url": "https://example.com/app/password-reset/confirm?token=t0k",
    "telegram_name": "@tg_name_x",
    "investor_name": "Investor Name X",
    "agreement_number": "3F9A12C0",
    "company": "Company X",
    "product": "Product X",
    "units": 12,
    "total_paid": "1,500.00",
    "total_units": 1000,
    "current_value": "20,000.00",
    "as_of": "As Of X",
    "documents_url": "https://example.com/app/portfolio/1?doc=x",
    "amount": "250.00",
    "reason": "Reason X",
    "tranche_number": 3,
    "due_date": "Due X",
    "digest_intro": "Intro X",
    "unsubscribe_url": "https://example.com/app/unsubscribe",
    **{f"item{i}_{k}": f"Item{i} {k} X" for i in (1, 2, 3) for k in ("title", "text")},
    **{f"item{i}_url": f"https://example.com/app/news/{i}" for i in (1, 2, 3)},
}

# Cyrillic, written as escapes so no look-alike letter hides in the source.
CYRILLIC = re.compile("[\u0430-\u044f\u0451]", re.IGNORECASE)

SENT = sorted(k for k, v in TYPES.items() if v["sent"])
ALL = sorted(TYPES)


def _fields_for(type_key: str, language: str) -> dict[str, Any]:
    """Exactly the variables this type's words name, in this language."""
    entry = TYPES[type_key]
    named: set[str] = set()
    for word in entry[language].values():
        named |= {n for _, n, _, _ in string.Formatter().parse(word) if n}
    layout = LAYOUTS[entry["layout"]]
    named |= {n for _, n, _, _ in string.Formatter().parse(layout) if n}
    return {k: v for k, v in FIELDS.items() if k in named}


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    monkeypatch.setattr(settings, "support_url", "https://t.example.com/bot")
    monkeypatch.setattr(settings, "support_email", "help@example.com")


# ---------------------------------------------------------------------------
# Every type, both languages
# ---------------------------------------------------------------------------


def test_the_twelve_sent_letters_and_the_three_unsent_are_there() -> None:
    assert len(SENT) == 12
    assert sorted(k for k in TYPES if not TYPES[k]["sent"]) == [
        "installment.reminder", "news.digest", "welcome",
    ]
    assert LANGUAGES == ("en", "ru")


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("type_key", ALL)
def test_every_type_builds_in_both_languages(type_key: str, language: str) -> None:
    request = letter_request(type_key, language, _fields_for(type_key, language))
    letter = request["email"]
    assert set(letter) == {"subject", "text", "html"}
    for part in ("subject", "text", "html"):
        assert letter[part].strip()
        # no slot and no variable is left unfilled
        assert "{" not in letter[part] and "}" not in letter[part], part
    assert request["title"].strip() and request["body"].strip()
    assert f'<html lang="{language}">' in letter["html"]
    # within comms' limits (the longest values are the report's business;
    # these are ordinary ones)
    assert len(letter["subject"]) <= 500
    assert len(letter["text"]) <= 64_000
    assert len(letter["html"]) <= 256_000


@pytest.mark.parametrize("type_key", ALL)
def test_the_two_languages_are_different_letters(type_key: str) -> None:
    en = build_letter(type_key, "en", _fields_for(type_key, "en"))
    ru = build_letter(type_key, "ru", _fields_for(type_key, "ru"))
    assert en["subject"] != ru["subject"]
    assert CYRILLIC.search(ru["text"])
    assert CYRILLIC.search(ru["html"])
    assert not CYRILLIC.search(en["text"])
    assert not CYRILLIC.search(en["html"])


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("type_key", ALL)
def test_the_text_part_says_every_word_of_the_html_part(
    type_key: str, language: str
) -> None:
    """One set of words for both parts: every word the html part prints --
    the type's slots and the footer -- is in the text part too (the status
    colour is a style, not a word)."""
    fields = _fields_for(type_key, language)
    letter = build_letter(type_key, language, fields)
    entry = TYPES[type_key]
    words = {k: v for k, v in entry[language].items()
             if k not in {"subject", "bell_title", "bell_body", "status_color"}}
    common = dict(COMMON[language])
    if entry["layout"] != "digest":
        for key in ("read_more", "digest_reason", "unsubscribe"):
            common.pop(key)
    for key, word in {**words, **common}.items():
        values = {k: str(v) for k, v in {**FIELDS, **_shared()}.items()}
        printed = word.format_map(values)
        assert printed in letter["text"], (key, printed)


def _shared() -> dict[str, str]:
    from app.core.email_vars import letter_vars

    return letter_vars()


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("type_key", ALL)
def test_a_paragraph_of_the_text_part_is_one_line(type_key: str, language: str) -> None:
    """A paragraph is never broken in the middle: every line of the text part
    is a whole paragraph, a whole row ("Label: value") or a whole link line.
    Every non-empty line ends where a word of copy.yaml (or a value) ends."""
    letter = build_letter(type_key, language, _fields_for(type_key, language))
    for line in letter["text"].split("\n"):
        assert line == line.strip()
    for paragraph in letter["text"].split("\n\n"):
        assert paragraph.strip()
    # the lead is one paragraph on one line, as long as it is
    lead = TYPES[type_key][language]["lead"].format_map(
        {k: str(v) for k, v in FIELDS.items()}
    )
    assert f"\n{lead}\n" in letter["text"]


# ---------------------------------------------------------------------------
# Data: escaping, missing, empty, NUL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
def test_data_is_escaped_in_html_and_as_it_is_in_text(language: str) -> None:
    hostile = '<script>alert("x")</script> & "q"'
    fields = {**_fields_for("purchase.agreement", language), "company": hostile,
              "investor_name": hostile}
    request = letter_request("purchase.agreement", language, fields)
    letter = request["email"]
    assert hostile not in letter["html"]
    assert "<script>" not in letter["html"]
    escaped = (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;q&quot;"
    )
    assert escaped in letter["html"]
    assert hostile in letter["text"]
    # the bell and the subject are text too
    assert hostile in request["body"]


def test_a_link_with_an_ampersand_is_escaped_in_its_href() -> None:
    url = "https://example.com/app/portfolio/1?doc=agreement&purchase=2"
    fields = {**_fields_for("purchase.agreement", "en"), "documents_url": url}
    letter = build_letter("purchase.agreement", "en", fields)
    href = 'href="https://example.com/app/portfolio/1?doc=agreement&amp;purchase=2"'
    assert href in letter["html"]
    assert url in letter["text"]


def test_a_value_that_looks_like_a_variable_is_printed() -> None:
    fields = {**_fields_for("auth.telegram_linked", "en"), "telegram_name": "{code}"}
    letter = build_letter("auth.telegram_linked", "en", fields)
    assert "{code}" in letter["text"]


@pytest.mark.parametrize(
    "type_key", ["purchase.agreement", "withdrawal.rejected", "auth.verification_code"]
)
def test_a_missing_variable_refuses(type_key: str) -> None:
    fields = _fields_for(type_key, "en")
    missing = sorted(fields)[0]
    del fields[missing]
    with pytest.raises(LetterError, match=repr(missing)):
        letter_request(type_key, "en", fields)


def test_a_none_value_refuses() -> None:
    fields = {**_fields_for("withdrawal.rejected", "en"), "reason": None}
    with pytest.raises(LetterError, match="'reason' is None"):
        letter_request("withdrawal.rejected", "en", fields)


def test_an_empty_value_is_printed_as_nothing() -> None:
    fields = {**_fields_for("withdrawal.rejected", "en"), "reason": ""}
    request = letter_request("withdrawal.rejected", "en", fields)
    text = request["email"]["text"]
    assert "Your withdrawal request was rejected. Reason: \n" in text


def test_a_field_may_not_shadow_a_shared_address() -> None:
    fields = {**_fields_for("withdrawal.processing", "en"), "cabinet_url": "https://evil.example"}
    with pytest.raises(LetterError, match="shadow"):
        letter_request("withdrawal.processing", "en", fields)


def test_an_unknown_type_refuses() -> None:
    with pytest.raises(LetterError, match="no letter"):
        letter_request("kyc.approved", "en", {})


def test_a_language_outside_the_letters_refuses_at_build() -> None:
    with pytest.raises(LetterError, match="letter_language"):
        letter_request("withdrawal.processing", "de", {"amount": "1.00"})


@pytest.mark.parametrize("type_key", ["auth.telegram_link_code", "withdrawal.rejected"])
def test_nul_never_reaches_the_request(type_key: str) -> None:
    """comms refuses a whole request carrying U+0000 in any field."""
    fields = {k: (f"a\x00b{v}" if isinstance(v, str) else v)
              for k, v in _fields_for(type_key, "ru").items()}
    request = letter_request(type_key, "ru", fields)
    flat = [request["title"], request["body"], *request["email"].values()]
    assert all("\x00" not in part for part in flat)
    assert any("ab" in part for part in flat)


# ---------------------------------------------------------------------------
# The bell, and title/body of an e-mail-only type
# ---------------------------------------------------------------------------


BELL_TYPES = sorted(k for k, v in TYPES.items() if v["bell"])


def test_the_eight_cabinet_types_have_bell_words() -> None:
    assert sorted([
        "purchase.agreement", "ownership.certificate",
        "withdrawal.processing", "withdrawal.completed", "withdrawal.rejected",
        "withdrawal.failed", "installment.tranche_overdue",
        "installment.plan_defaulted",
    ]) == BELL_TYPES


@pytest.mark.parametrize("type_key", BELL_TYPES)
def test_the_bell_speaks_the_persons_language(type_key: str) -> None:
    en = letter_request(type_key, "en", _fields_for(type_key, "en"))
    ru = letter_request(type_key, "ru", _fields_for(type_key, "ru"))
    assert CYRILLIC.search(ru["title"] + ru["body"])
    assert not CYRILLIC.search(en["title"] + en["body"])


@pytest.mark.parametrize(
    "type_key",
    ["auth.verification_code", "auth.password_reset", "auth.telegram_link_code",
     "auth.telegram_linked"],
)
def test_an_email_only_type_sends_its_subject_and_heading(type_key: str) -> None:
    request = letter_request(type_key, "ru", _fields_for(type_key, "ru"))
    assert request["title"] == request["email"]["subject"]
    heading = TYPES[type_key]["ru"]["heading"]
    assert request["body"] == heading
    # neither carries the code or the link
    assert "482915" not in request["title"] + request["body"]
    assert "t0k" not in request["title"] + request["body"]


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"), ("ru", "ru"), ("RU", "ru"), ("ru-RU", "ru"), ("ru_RU", "ru"),
        (" ru ", "ru"), ("de", "en"), ("", "en"), ("   ", "en"), ("russian", "en"),
        (None, "en"), (7, "en"),
    ],
)
def test_letter_language(value: Any, expected: str) -> None:
    assert letter_language(value) == expected


def test_ru_is_a_russian_letter_and_de_an_english_one() -> None:
    fields = _fields_for("auth.verification_code", "en")
    assert "Код подтверждения" in build_letter(
        "auth.verification_code", letter_language("ru"), fields)["text"]
    assert "Verification code" in build_letter(
        "auth.verification_code", letter_language("de"), fields)["text"]
    assert "Verification code" in build_letter(
        "auth.verification_code", letter_language(""), fields)["text"]


# ---------------------------------------------------------------------------
# The loader refuses a broken copy.yaml
# ---------------------------------------------------------------------------


def _doc() -> dict[str, Any]:
    return yaml.safe_load(_COPY.read_text(encoding="utf-8"))


def _load(doc: dict[str, Any]) -> None:
    load_copy(yaml.safe_dump(doc, allow_unicode=True), LAYOUTS)


def test_the_real_copy_loads() -> None:
    common, types = load_copy(_COPY.read_text(encoding="utf-8"), LAYOUTS)
    assert set(types) == set(TYPES)
    assert set(common) == set(LANGUAGES)


def test_a_missing_slot_refuses() -> None:
    doc = _doc()
    del doc["types"]["withdrawal.failed"]["ru"]["note"]
    with pytest.raises(CopyError, match=r"withdrawal.failed.ru: missing \['note'\]"):
        _load(doc)


def test_an_extra_slot_refuses() -> None:
    doc = _doc()
    doc["types"]["auth.verification_code"]["en"]["code"] = "{code}"
    with pytest.raises(CopyError, match=r"extra \['code'\]"):
        _load(doc)


def test_a_missing_language_refuses() -> None:
    doc = _doc()
    del doc["types"]["auth.password_reset"]["ru"]
    with pytest.raises(CopyError, match=r"no words in \['ru'\]"):
        _load(doc)


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_word_refuses(blank: str) -> None:
    doc = _doc()
    doc["types"]["purchase.agreement"]["en"]["bell_body"] = blank
    with pytest.raises(CopyError, match="bell_body: not a non-blank string"):
        _load(doc)


def test_a_bell_in_one_language_only_refuses() -> None:
    doc = _doc()
    del doc["types"]["withdrawal.completed"]["ru"]["bell_title"]
    where = r"withdrawal\.completed\.ru: missing \['bell_title'\]"
    with pytest.raises(CopyError, match=where):
        _load(doc)


def test_half_a_bell_refuses() -> None:
    doc = _doc()
    del doc["types"]["withdrawal.completed"]["en"]["bell_body"]
    with pytest.raises(CopyError, match="bell_title"):
        _load(doc)


def test_a_missing_subject_refuses() -> None:
    doc = _doc()
    del doc["types"]["installment.plan_defaulted"]["en"]["subject"]
    with pytest.raises(CopyError, match=r"missing \['subject'\]"):
        _load(doc)


def test_a_missing_footer_word_refuses() -> None:
    doc = _doc()
    del doc["common"]["ru"]["footer_bot"]
    with pytest.raises(CopyError, match=r"common.ru: missing \['footer_bot'\]"):
        _load(doc)


def test_a_nul_in_a_word_refuses() -> None:
    doc = _doc()
    doc["types"]["withdrawal.failed"]["en"]["lead"] = "a\x00b"
    with pytest.raises(CopyError, match="NUL"):
        _load(doc)


def test_a_key_written_twice_refuses() -> None:
    text = _COPY.read_text(encoding="utf-8").replace(
        '      subject: "Your withdrawal is completed"\n',
        '      subject: "Your withdrawal is completed"\n'
        '      subject: "A second subject"\n',
    )
    with pytest.raises(CopyError, match="'subject' written twice"):
        load_copy(text, LAYOUTS)


def test_a_layout_that_lost_a_slot_refuses() -> None:
    layouts = {**LAYOUTS, "notice": LAYOUTS["notice"].replace("{status_text}", "")}
    lost = r"layouts/notice\.html: slots not in the layout \['status_text'\]"
    with pytest.raises(CopyError, match=lost):
        load_copy(_COPY.read_text(encoding="utf-8"), layouts)


def test_an_unknown_layout_refuses() -> None:
    doc = _doc()
    doc["types"]["welcome"]["layout"] = "poster"
    with pytest.raises(CopyError, match=r"welcome\.layout"):
        _load(doc)


# ---------------------------------------------------------------------------
# A subject and a title stay within comms' 500 (owner ruling, H43)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("language", "assembled"), [("en", 523), ("ru", 526)])
def test_the_longest_certificate_subject_and_title_are_cut_to_500(
    language: str, assembled: int
) -> None:
    """The longest a subject gets: "Ownership certificate: " and a company
    name at its column's 500 -- 523 characters, 526 in Russian. Cut to 500,
    the ellipsis inside."""
    fields = {**_fields_for("ownership.certificate", language), "company": "C" * 500}
    subject = TYPES["ownership.certificate"][language]["subject"]
    assert len(subject.format(company="C" * 500)) == assembled
    request = letter_request("ownership.certificate", language, fields)
    for line in (request["email"]["subject"], request["title"]):
        assert len(line) == 500
        assert line.endswith("C…")
    # the body and the letter keep the whole name
    assert "C" * 500 in request["email"]["text"]


def test_a_subject_within_500_is_not_touched() -> None:
    fields = {**_fields_for("ownership.certificate", "en"), "company": "C" * 477}
    request = letter_request("ownership.certificate", "en", fields)
    assert request["email"]["subject"] == "Ownership certificate: " + "C" * 477
    assert len(request["email"]["subject"]) == 500
