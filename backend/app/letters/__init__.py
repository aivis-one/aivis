# =============================================================================
# AIVIS.ONE Backend -- the e-mail letter builder
# =============================================================================
#
# AIVIS writes its letters; comms only delivers them (owner ruling, H43). A
# request for a type routed to e-mail carries the finished letter in its
# `email` block -- {subject, text, html} -- and comms sends exactly that:
# no profile template, no title/body, no locale of its own (comms >= 3.12.0
# with the block; an older comms refuses the whole request at intake, so
# comms goes onto the box first).
#
# WHERE THE WORDS ARE. copy.yaml beside this file: per type, the layout and
# the words of its slots in each language, plus the subject and, for a type
# that also lands in the cabinet's bell, the bell's title and body. The five
# layouts (layouts/<layout>.html) carry no words of their own -- the footer
# and the digest's fixed words are copy.yaml's `common` -- so a layout serves
# both languages.
#
# ONE SET OF WORDS FOR BOTH PARTS. The html part is the layout with the
# words written into its slots; the text part is the same slots in the
# layout's plain shape (_TEXT below). Each paragraph of the text is one line
# -- a mail client wraps it -- and paragraphs are separated by an empty line;
# a block of rows ("Label: value") keeps one row per line.
#
# TWO PASSES. First the words go into the slots (HTML-escaped for the html
# part); a word may name data variables, {name}. Then the data fills every
# variable left: in the html part each value is HTML-escaped, in the text
# part and the subject it goes as it is. The second pass is one
# str.format_map, so a value carrying "{x}" is printed, never read as a
# variable.
#
# WHAT REFUSES. The loader refuses copy.yaml at import on a missing or extra
# slot, a missing language, a blank word, a duplicate key, a NUL, or a
# layout that lost one of its slots -- so a broken file stops the
# application and the test suite, not a letter. At build time a variable
# whose value is missing or None raises LetterError and the caller's
# transaction rolls back with it: the data an emitter sends is fixed by its
# code, and every type is built in both languages by the tests
# (tests/test_letters.py). An empty string is a value and is printed.
#
# NUL. comms refuses a whole request that carries U+0000 in any field, and
# Postgres refuses it in the outbox's JSONB before that. A value from the
# database cannot carry one (Postgres stores no NUL); the values that do not
# come from it -- a Telegram display name, a staff member's typed reason,
# the generated code and link -- are cleared of NUL here, every value
# alike, before anything is built.
#
# LENGTHS. comms refuses a subject or a title over 500 characters (and
# the whole request with it); the assembled subject and bell title are cut
# to MAX_LINE_CHARS, an ellipsis inside. Every other value is bounded where
# it is written: a company and a product name at 500 (their columns), a
# person's names at 100 (users/schemas.py profile_name_problem), a
# rejection reason at 2000 -- far inside the 64 000 of the text part and
# the 256 000 of the html part.
#
# THE LANGUAGE. letter_language() maps a person's users.language onto the
# languages the letters exist in: "ru", "RU", "ru-RU" -> ru; anything else,
# blank included, -> en. recipient_language() reads it from the person's row
# at the moment the letter is built.
# =============================================================================

from __future__ import annotations

import html
import re
import string
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from app.core.email_vars import letter_vars

_HERE = Path(__file__).resolve().parent

LANGUAGES = ("en", "ru")
BASE_LANGUAGE = "en"

# The slots of each layout: what copy.yaml fills, per type.
LAYOUT_SLOTS: dict[str, frozenset[str]] = {
    "code": frozenset({"heading", "lead", "valid_note", "ignore_note"}),
    "action": frozenset(
        {"heading", "lead", "highlight", "button_text", "button_url", "note"}
    ),
    "document": frozenset(
        {"heading", "lead", "note", "button_text", "button_url"}
        | {f"row{i}_{k}" for i in range(1, 6) for k in ("label", "value")}
    ),
    "notice": frozenset(
        {
            "heading", "lead", "note", "button_text", "button_url",
            "detail_label", "detail_value", "status_label", "status_text",
            "status_color",
        }
    ),
    "digest": frozenset({"heading", "lead"}),
}

# copy.yaml `common`: the footer of every layout, and the digest's words.
FOOTER_SLOTS = frozenset({"footer_company", "footer_support", "footer_bot"})
DIGEST_SLOTS = frozenset({"read_more", "digest_reason", "unsubscribe"})
COMMON_SLOTS = FOOTER_SLOTS | DIGEST_SLOTS

# Per type and language, beside the layout's slots.
SUBJECT = "subject"
BELL = frozenset({"bell_title", "bell_body"})

_FOOTER_TEXT = (
    "{footer_company}\n"
    "{footer_support} {footer_bot} {support_url} · {support_email}"
)

# The text part of each layout: its paragraphs, in the html part's order.
_TEXT: dict[str, tuple[str, ...]] = {
    "code": ("{heading}", "{lead}", "{code}", "{valid_note}", "{ignore_note}"),
    "action": (
        "{heading}", "{lead}", "{highlight}", "{button_text}: {button_url}",
        "{note}",
    ),
    "document": (
        "{heading}",
        "{lead}",
        "\n".join(f"{{row{i}_label}}: {{row{i}_value}}" for i in range(1, 6)),
        "{button_text}: {button_url}",
        "{note}",
    ),
    "notice": (
        "{heading}",
        "{lead}",
        "{detail_label}: {detail_value}\n{status_label}: {status_text}",
        "{note}",
        "{button_text}: {button_url}",
    ),
    "digest": (
        "{heading}",
        "{lead}",
        *(
            f"{{item{i}_title}}\n{{item{i}_text}}\n{{read_more}}: {{item{i}_url}}"
            for i in range(1, 4)
        ),
        "{digest_reason} {unsubscribe}: {unsubscribe_url}",
    ),
}


class LetterError(ValueError):
    """A letter cannot be built: unknown type, or a variable without a value."""


class CopyError(ValueError):
    """copy.yaml or a layout is not what the builder needs."""


# -----------------------------------------------------------------------------
# Loading -- once, at import
# -----------------------------------------------------------------------------


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a key written twice (plain YAML keeps the
    last one silently, and a second copy of a word would be read as the
    only one)."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise CopyError(f"copy.yaml: key {key!r} written twice")
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def names(template: str) -> set[str]:
    """The {variables} a template names."""
    return {n for _, n, _, _ in string.Formatter().parse(template) if n}


def _words(where: str, raw: Any, expected: frozenset[str]) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise CopyError(f"{where}: not a mapping")
    keys = set(raw)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise CopyError(f"{where}: missing {missing}, extra {extra}")
    for key, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            raise CopyError(f"{where}.{key}: not a non-blank string")
        if "\x00" in value:
            raise CopyError(f"{where}.{key}: carries a NUL")
    return dict(raw)


def load_copy(
    text: str, layouts: dict[str, str]
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, Any]]]:
    """-> (common words per language, types) from copy.yaml's text.

    Refuses everything the module header lists. `layouts` is the html of
    each layout, checked to still carry every slot copy.yaml fills.
    """
    doc = yaml.load(text, Loader=_UniqueKeyLoader)
    if not isinstance(doc, dict) or set(doc) != {"common", "types"}:
        raise CopyError("copy.yaml: the top level is exactly `common` and `types`")

    common_raw = doc["common"]
    if not isinstance(common_raw, dict) or set(common_raw) != set(LANGUAGES):
        raise CopyError(f"copy.yaml common: exactly the languages {LANGUAGES}")
    common = {
        lang: _words(f"common.{lang}", common_raw[lang], COMMON_SLOTS)
        for lang in LANGUAGES
    }

    for layout, slots in LAYOUT_SLOTS.items():
        if layout not in layouts:
            raise CopyError(f"layouts/{layout}.html: missing")
        wanted = slots | FOOTER_SLOTS | {"lang"}
        if layout == "digest":
            wanted |= DIGEST_SLOTS
        lost = sorted(wanted - names(layouts[layout]))
        if lost:
            raise CopyError(f"layouts/{layout}.html: slots not in the layout {lost}")

    types_raw = doc["types"]
    if not isinstance(types_raw, dict) or not types_raw:
        raise CopyError("copy.yaml types: a non-empty mapping")
    types: dict[str, dict[str, Any]] = {}
    for key, entry in types_raw.items():
        where = f"types.{key}"
        if not isinstance(entry, dict):
            raise CopyError(f"{where}: not a mapping")
        extra = set(entry) - {"layout", "sent", *LANGUAGES}
        if extra:
            raise CopyError(f"{where}: unknown keys {sorted(extra)}")
        layout = entry.get("layout")
        if layout not in LAYOUT_SLOTS:
            raise CopyError(f"{where}.layout: one of {sorted(LAYOUT_SLOTS)}")
        sent = entry.get("sent", True)
        if not isinstance(sent, bool):
            raise CopyError(f"{where}.sent: true or false")
        missing_langs = [lang for lang in LANGUAGES if lang not in entry]
        if missing_langs:
            raise CopyError(f"{where}: no words in {missing_langs}")
        # The bell pair is all or nothing, and the same in every language.
        has_bell = set(entry[BASE_LANGUAGE] or {}) >= BELL
        expected = LAYOUT_SLOTS[layout] | {SUBJECT} | (BELL if has_bell else set())
        words = {
            lang: _words(f"{where}.{lang}", entry[lang], frozenset(expected))
            for lang in LANGUAGES
        }
        types[key] = {"layout": layout, "sent": sent, "bell": has_bell, **words}
    return common, types


def _read_layouts() -> dict[str, str]:
    return {
        layout: (_HERE / "layouts" / f"{layout}.html").read_text(encoding="utf-8")
        for layout in LAYOUT_SLOTS
    }


LAYOUTS = _read_layouts()
COMMON, TYPES = load_copy((_HERE / "copy.yaml").read_text(encoding="utf-8"), LAYOUTS)


# -----------------------------------------------------------------------------
# Language
# -----------------------------------------------------------------------------


def letter_language(value: Any) -> str:
    """users.language -> the language of a letter: one of LANGUAGES.

    The primary subtag, case-folded ("ru-RU", "RU" -> "ru"); any language the
    letters do not exist in, a blank and a non-string -> BASE_LANGUAGE.
    """
    if not isinstance(value, str):
        return BASE_LANGUAGE
    primary = re.split(r"[-_]", value.strip(), maxsplit=1)[0].lower()
    return primary if primary in LANGUAGES else BASE_LANGUAGE


async def recipient_language(session: Any, user_id: UUID) -> str:
    """The letter language of the person `user_id`, read now, in the
    caller's transaction (the letter's language is the person's at the
    moment it is built, not whatever comms holds)."""
    from sqlalchemy import select

    from app.modules.users.models import User

    language = (
        await session.execute(select(User.language).where(User.id == user_id))
    ).scalar_one()
    return letter_language(language)


# -----------------------------------------------------------------------------
# Building
# -----------------------------------------------------------------------------


class _Keep(dict):  # type: ignore[type-arg]
    """First pass: a name that is not a slot stays a {variable}."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class _Strict(dict):  # type: ignore[type-arg]
    """Second pass: every variable left must have a value."""

    def __missing__(self, key: str) -> str:
        raise LetterError(f"the letter needs the variable {key!r}")


def _values(type_key: str, fields: dict[str, Any]) -> dict[str, str]:
    shared = letter_vars()
    clash = sorted(set(shared) & set(fields))
    if clash:
        raise LetterError(f"{type_key}: fields {clash} shadow the shared ones")
    values: dict[str, str] = {}
    for key, value in {**shared, **fields}.items():
        if value is None:
            raise LetterError(f"{type_key}: the variable {key!r} is None")
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise LetterError(
                f"{type_key}: the variable {key!r} is a {type(value).__name__}"
            )
        values[key] = str(value).replace("\x00", "")
    return values


def _fill(template: str, values: dict[str, str]) -> str:
    return template.format_map(_Strict(values))


# comms' width of a letter's subject and of a notification's title (its
# MAX_TITLE_LEN): a longer one refuses the whole request at intake, and the
# letter is lost. A subject or a title is assembled from words and data --
# "Ownership certificate: " and a company name of up to 500 characters
# reach 523 (526 in Russian) -- so the assembled string is cut here, the
# ellipsis inside the limit (owner ruling, H43).
MAX_LINE_CHARS = 500
ELLIPSIS = "…"


def _cap(line: str) -> str:
    """A subject or a title within MAX_LINE_CHARS, an ellipsis where cut."""
    if len(line) <= MAX_LINE_CHARS:
        return line
    return line[: MAX_LINE_CHARS - len(ELLIPSIS)] + ELLIPSIS


def build_letter(
    type_key: str, language: str, fields: dict[str, Any]
) -> dict[str, str]:
    """-> {subject, text, html} of `type_key` in `language` (one of LANGUAGES,
    see letter_language) over the type's own `fields`; the shared addresses
    (core/email_vars.py letter_vars) are added here."""
    entry = TYPES.get(type_key)
    if entry is None:
        raise LetterError(f"no letter for the type {type_key!r}")
    if language not in LANGUAGES:
        raise LetterError(f"no letters in {language!r}; map it with letter_language")
    layout = entry["layout"]
    words = {**COMMON[language], **entry[language], "lang": language}
    values = _values(type_key, fields)

    escaped_words = _Keep({k: html.escape(v, quote=True) for k, v in words.items()})
    escaped_values = {k: html.escape(v, quote=True) for k, v in values.items()}
    html_part = LAYOUTS[layout].format_map(escaped_words)
    html_part = _fill(html_part, escaped_values)

    paragraphs = [p.format_map(_Keep(words)) for p in _TEXT[layout]]
    paragraphs.append(_FOOTER_TEXT.format_map(_Keep(words)))
    text_part = _fill("\n\n".join(paragraphs), values)

    return {
        "subject": _cap(_fill(words[SUBJECT], values)),
        "text": text_part,
        "html": html_part,
    }


def letter_request(
    type_key: str, language: str, fields: dict[str, Any]
) -> dict[str, Any]:
    """The letter fields of a notification request: title, body, email.

    `email` is the whole letter. title and body -- required by comms for a
    type delivered to people, and shown only by the cabinet's bell -- are
    the bell's words for a type that lands there, and the subject and the
    heading for one that does not (they are stored, shown nowhere).
    """
    letter = build_letter(type_key, language, fields)
    entry = TYPES[type_key]
    values = _values(type_key, fields)
    if entry["bell"]:
        title = _cap(_fill(entry[language]["bell_title"], values))
        body = _fill(entry[language]["bell_body"], values)
    else:
        title = letter["subject"]
        body = _fill(entry[language]["heading"], values)
    return {"title": title, "body": body, "email": letter}
