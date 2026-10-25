# =============================================================================
# AIVIS.ONE Backend -- project data in the reader's language (H38 P-132)
# =============================================================================
#
# The cabinet's screens are bilingual through the frontend's locale files;
# the projects' DATA lives here. A translatable row keeps its English text
# in its own columns (the base and the fallback) and the other languages in
# a `translations` JSONB beside them:
#
#     {"ru": {"name": "...", "description": "..."}}
#
# A new language is a new key: no migration. English is never a key there
# -- it is the columns, and a second copy would be a second source.
#
# WHAT LIVES HERE
#   TRANSLATABLE           -- the fields (and their column limits) of each
#                             table that carries translations
#   normalize_translations -- the one validator of a written map
#   reader_language        -- FastAPI dependency: the reader's language from
#                             Accept-Language, and `Vary: Accept-Language`
#                             on the response
#   localized              -- the text of one field for a language, else the
#                             English base
#
# THE READER'S LANGUAGE is the primary subtag of the FIRST language tag of
# Accept-Language, lowercased (`ru` from `ru-RU,ru;q=0.9`). There is no
# negotiation down the list: the frontend sends one tag, the current UI
# locale. Anything that is not two letters -- no header, `*`, garbage --
# is English. A language with no translation reads English.
# =============================================================================

import re
from typing import Any

from fastapi import Request, Response

# The default language and the fallback: the base columns.
BASE_LANGUAGE = "en"

# A language key of a translations map, and a reader language.
LANGUAGE_RE = re.compile(r"^[a-z]{2}$")

# Translatable fields per table, with the length limit of their column.
TRANSLATABLE: dict[str, dict[str, int]] = {
    "company_profiles": {"name": 500, "description": 5000},
    "products": {"name": 500, "description": 5000},
    "company_roadmap_items": {"title": 500, "description": 5000},
    "posts": {"title": 500, "body": 50000},
}


def is_language_code(value: Any) -> bool:
    """A two-letter lowercase language code (`ru`), English included."""
    return isinstance(value, str) and LANGUAGE_RE.fullmatch(value) is not None


def normalize_translations(table: str, value: Any) -> dict[str, dict[str, str]]:
    """Validate a translations map for `table` and return it as stored.

    - a language key is two lowercase letters and is not `en` (English is
      the base columns);
    - inside a language, only the table's own fields, each a string within
      its column's limit;
    - an empty string or null means "no translation of that field" and is
      dropped; a language left with no field is dropped.

    Raises:
        ValueError: with the offending key, for Pydantic to report as 422.
    """
    limits = TRANSLATABLE[table]
    if not isinstance(value, dict):
        raise ValueError("translations must be an object of languages")
    result: dict[str, dict[str, str]] = {}
    for language, fields in value.items():
        if not is_language_code(language):
            raise ValueError(
                f"translations: language {language!r} is not a two-letter "
                f"lowercase code"
            )
        if language == BASE_LANGUAGE:
            raise ValueError(
                "translations: 'en' is the base text in the fields "
                "themselves, not a translation"
            )
        if not isinstance(fields, dict):
            raise ValueError(f"translations.{language} must be an object of fields")
        kept: dict[str, str] = {}
        for field, text in fields.items():
            if field not in limits:
                raise ValueError(
                    f"translations.{language}: {field!r} is not a translatable "
                    f"field here; allowed: {sorted(limits)}"
                )
            if text is None:
                continue
            if not isinstance(text, str):
                raise ValueError(f"translations.{language}.{field} must be text")
            if not text.strip():
                continue
            if len(text) > limits[field]:
                raise ValueError(
                    f"translations.{language}.{field} is longer than "
                    f"{limits[field]} characters"
                )
            kept[field] = text
        if kept:
            result[language] = kept
    return result


def parse_accept_language(header: str | None) -> str:
    """The reader's language from an Accept-Language value (see header)."""
    if not header:
        return BASE_LANGUAGE
    tags: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        quality = 1.0
        params = params.strip()
        if params.startswith("q="):
            try:
                quality = float(params[2:])
            except ValueError:
                quality = 0.0
        # The highest q wins; equal q keeps the header's order.
        tags.append((-quality, index, tag.strip()))
    if not tags:
        return BASE_LANGUAGE
    first = sorted(tags)[0][2]
    primary = re.split(r"[-_]", first, maxsplit=1)[0].lower()
    return primary if is_language_code(primary) else BASE_LANGUAGE


def reader_language(request: Request, response: Response) -> str:
    """FastAPI dependency: the reader's language, and Vary on the answer.

    Every endpoint whose answer carries a translatable text depends on it,
    so the same URL in two languages is never cached as one.
    """
    response.headers["Vary"] = "Accept-Language"
    return parse_accept_language(request.headers.get("accept-language"))


def localized(translations: dict[str, Any] | None, language: str, field: str, base: Any) -> Any:
    """The text of `field` in `language`, else the English base."""
    if language == BASE_LANGUAGE or not translations:
        return base
    text = (translations.get(language) or {}).get(field)
    return text if isinstance(text, str) and text.strip() else base


# The written shape of a translations map, before normalize_translations.
TranslationsIn = dict[str, dict[str, str | None]]


def translations_checker(table: str) -> Any:
    """A Pydantic field validator for a request's `translations`.

    Not passed (None) stays None: the update leaves the stored map alone.
    Passed, it is normalized -- and then REPLACES the stored map whole.
    """

    def check(cls: Any, value: Any) -> dict[str, dict[str, str]] | None:
        if value is None:
            return None
        return normalize_translations(table, value)

    return check
