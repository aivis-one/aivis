# =============================================================================
# AIVIS.ONE Backend -- Project media in our storage (H36 P-131)
# =============================================================================
#
# A project's logo, its logo for the dark theme, its cover and the cover of
# each of its products are objects in our storage. The database holds the
# object KEY (company_profiles.logo_storage_key / logo_dark_storage_key /
# cover_storage_key, products.cover_storage_key); every response that shows
# a picture carries a presigned link signed from that key at answer time,
# under the field name the API always had (logo_url, cover_url,
# company_logo_url, company_cover_url) plus logo_dark_url /
# company_logo_dark_url.
#
# WHAT LIVES HERE (the contract H37's seeding writes against):
#   CompanyMediaSlot           -- constants.py; logo / logo_dark / cover
#                                 (in a URL path: logo / logo-dark / cover)
#   company_media_key()        -- companies/<id>/media/[<lang>/]<stem><ext>
#   product_cover_key()        -- companies/<id>/products/<product_id>/[<lang>/]cover<ext>
#   roadmap_cover_key()        -- companies/<id>/roadmap/<item_id>/[<lang>/]cover<ext>
#   validate_media_upload()    -- extension, type and size of one picture
#   presign_media()            -- key -> link or None, never a 5xx
#   company_media_urls()       -- the three company links of one row
#   build_company_response() / build_public_company_response() /
#   build_product_response()   -- the ORM row plus the links, texts and
#                                 pictures in the reader's language
#   company_logo_data_uri()    -- the logo for documents, as bytes inline
#
# LANGUAGE VARIANTS (H38 P-132). Each of these pictures -- and the cover
# of a roadmap item -- may have a variant per language beside the common
# file: companies/<id>/media/<lang>/<stem><ext>, .../products/<pid>/<lang>/
# cover<ext>, .../roadmap/<iid>/<lang>/cover<ext>. Their keys live in the
# row's `media_variants` JSONB, {"ru": {"cover": "<key>"}}, next to the
# H36 columns that keep the common key. A reader is served the variant of
# their language when there is one, else the common file. `en` is never a
# variant: English is the common file. The text side of H38 -- the
# `translations` beside the English columns -- is app/core/i18n.py.
#   check_variant_language()   -- a variant's language, else 400
#   variant_key() / stored_key() / store_key()
#                              -- read / write one slot's key per language
#   company_image_variants()   -- the variant links an edit screen shows
#
# EVERY KEY IS UNDER companies/<company_id>/. H37 resets a project by
# deleting that one prefix; media outside it would be orphaned.
#
# The upload and delete services themselves are where their rows live:
# companies/service.py (set_company_media and its kin) and
# products/service.py (set_product_cover, delete_product_cover).
# =============================================================================

import base64
from typing import Any, Literal, TypeVar
from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.config import settings
from app.core.i18n import BASE_LANGUAGE, is_language_code, localized
from app.core.exceptions import BadRequestError
from app.core.storage import (
    StorageError,
    StorageNotFoundError,
    generate_presigned_url,
    get_object_bytes,
)
from app.modules.companies.constants import (
    COMPANY_LOGO_MAX_BYTES,
    ROADMAP_COVER_EXTENSION_TO_MIME,
    ROADMAP_COVER_MAX_BYTES,
    CompanyMediaSlot,
)
from app.modules.companies.schemas import (
    CompanyBaseTexts,
    CompanyResponse,
    PublicCompanyResponse,
)
from app.modules.products.schemas import ProductBaseTexts, ProductResponse

logger = structlog.get_logger()

ResponseT = TypeVar("ResponseT", bound=BaseModel)


# ---------------------------------------------------------------------------
# Slots and keys
# ---------------------------------------------------------------------------

# The CompanyProfile column that holds each slot's key.
COMPANY_MEDIA_COLUMN: dict[CompanyMediaSlot, str] = {
    CompanyMediaSlot.LOGO: "logo_storage_key",
    CompanyMediaSlot.LOGO_DARK: "logo_dark_storage_key",
    CompanyMediaSlot.COVER: "cover_storage_key",
}

# The object name of each slot inside companies/<id>/media/.
_COMPANY_MEDIA_STEM: dict[CompanyMediaSlot, str] = {
    CompanyMediaSlot.LOGO: "logo",
    CompanyMediaSlot.LOGO_DARK: "logo-dark",
    CompanyMediaSlot.COVER: "cover",
}


# The slot as it is written in a URL path: /media/{slot}. A path takes
# the hyphen; the enum value (and the audit event) the underscore.
CompanyMediaSlotPath = Literal["logo", "logo-dark", "cover"]

_SLOT_BY_PATH: dict[str, CompanyMediaSlot] = {
    "logo": CompanyMediaSlot.LOGO,
    "logo-dark": CompanyMediaSlot.LOGO_DARK,
    "cover": CompanyMediaSlot.COVER,
}


def slot_from_path(path_slot: CompanyMediaSlotPath) -> CompanyMediaSlot:
    """The slot of a /media/{slot} path segment (FastAPI already refused others)."""
    return _SLOT_BY_PATH[path_slot]


def _language_dir(language: str | None) -> str:
    """The folder of a per-language variant (H38), or "" for the common file."""
    return f"{language}/" if language else ""


def company_media_key(
    company_id: UUID,
    slot: CompanyMediaSlot,
    file_extension: str,
    language: str | None = None,
) -> str:
    """Object key of one company picture. `file_extension` carries its dot.

    `language` (H38) makes it that language's variant:
    companies/<id>/media/<lang>/logo.png; None is the common file.
    """
    return (
        f"companies/{company_id}/media/{_language_dir(language)}"
        f"{_COMPANY_MEDIA_STEM[slot]}{file_extension}"
    )


def product_cover_key(
    company_id: UUID,
    product_id: UUID,
    file_extension: str,
    language: str | None = None,
) -> str:
    """Object key of a product's cover (a language's variant with `language`)."""
    return (
        f"companies/{company_id}/products/{product_id}/"
        f"{_language_dir(language)}cover{file_extension}"
    )


def roadmap_cover_key(
    company_id: UUID,
    item_id: UUID,
    file_extension: str,
    language: str | None = None,
) -> str:
    """Object key of a roadmap item's cover (a language's variant with `language`)."""
    return (
        f"companies/{company_id}/roadmap/{item_id}/"
        f"{_language_dir(language)}cover{file_extension}"
    )


def check_variant_language(language: str | None) -> None:
    """A picture variant's language: two lowercase letters, not English
    (English reads the common file). None is the common file itself.

    Raises:
        BadRequestError: the code is malformed or is "en".
    """
    if language is None:
        return
    if not is_language_code(language):
        raise BadRequestError(
            f"Picture language {language!r} is not a two-letter lowercase code"
        )
    if language == BASE_LANGUAGE:
        raise BadRequestError(
            "English reads the common picture; upload it without a language"
        )


def variant_key(
    variants: dict[str, Any] | None,
    language: str,
    slot: str,
    base_key: str | None,
) -> str | None:
    """The key to show `language`: its variant of `slot`, else the common one."""
    if language != BASE_LANGUAGE:
        key = ((variants or {}).get(language) or {}).get(slot)
        if key:
            return key
    return base_key


def with_variant(
    variants: dict[str, Any] | None, language: str, slot: str, key: str | None
) -> dict[str, dict[str, str]]:
    """A copy of a media_variants map with one slot of one language set
    (key) or removed (None); a language left empty is dropped."""
    result = {lang: dict(slots) for lang, slots in (variants or {}).items()}
    slots = result.setdefault(language, {})
    if key is None:
        slots.pop(slot, None)
    else:
        slots[slot] = key
    if not slots:
        result.pop(language)
    return result


def company_media_max_bytes(slot: CompanyMediaSlot) -> int:
    """Size limit of one slot: 1 MiB for both logos, 10 MiB for the cover.

    The logos are smaller because their bytes can be copied into every
    frozen purchase agreement (company_logo_data_uri below).
    """
    if slot is CompanyMediaSlot.COVER:
        return ROADMAP_COVER_MAX_BYTES
    return COMPANY_LOGO_MAX_BYTES


def validate_media_upload(
    *,
    content_type: str,
    file_extension: str,
    file_size_bytes: int,
    max_bytes: int,
) -> None:
    """Refuse a picture the storage must not hold.

    The routers derive (content_type, file_extension) from the filename
    with validate_roadmap_cover_mime_by_filename, so through HTTP this
    re-checks what they already checked. The services are also called
    directly (H37's seeding), and the extension becomes part of the
    object key, so they check the same set here rather than trust the
    caller.

    Raises:
        BadRequestError: the extension is not png / jpg / jpeg / webp
            (with its dot), the type does not match the extension, the
            file is empty, or it exceeds `max_bytes`.
    """
    expected_mime = ROADMAP_COVER_EXTENSION_TO_MIME.get(file_extension)
    if expected_mime is None:
        allowed = sorted(ROADMAP_COVER_EXTENSION_TO_MIME.keys())
        raise BadRequestError(
            f"Unsupported image extension: '{file_extension}'. Allowed: {allowed}"
        )
    if content_type != expected_mime:
        raise BadRequestError(
            f"Image type '{content_type}' does not match extension "
            f"'{file_extension}' ({expected_mime})"
        )
    if file_size_bytes <= 0:
        raise BadRequestError("Image file is empty")
    if file_size_bytes > max_bytes:
        raise BadRequestError(
            f"Image exceeds {max_bytes} bytes ({file_size_bytes} given)"
        )


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


async def presign_media(key: str | None, *, event: str, **context: Any) -> str | None:
    """Presigned link to one project picture, or None.

    ONE TTL ON EVERY SURFACE: settings.storage_presigned_ttl_public. These
    pictures are public content -- the open storefront shows the very same
    file -- so the short authenticated TTL protects nothing here. And it
    would break a real screen: the company cabinet keeps its profile in a
    long-lived store, and a 15-minute link there turns the logo in the
    header into a broken image a quarter of an hour after sign-in, which
    the external URL this replaced never did. Roadmap covers and
    attachments keep their own per-surface TTLs; this function is not
    theirs.

    A signing failure is logged under `event` and answered as "no
    picture" rather than failing the whole response, the same choice as
    roadmap_cover_presign_failed. Signing is a computation, not a request
    to the storage: a key whose object is gone still gets a link, and the
    browser gets the 404.
    """
    if not key:
        return None
    try:
        return await generate_presigned_url(key, settings.storage_presigned_ttl_public)
    except StorageError as exc:
        logger.warning(event, storage_key=key, error=str(exc), **context)
        return None


_COMPANY_URL_FIELD: dict[CompanyMediaSlot, str] = {
    CompanyMediaSlot.LOGO: "logo_url",
    CompanyMediaSlot.LOGO_DARK: "logo_dark_url",
    CompanyMediaSlot.COVER: "cover_url",
}


async def company_media_urls(
    company_id: UUID,
    *,
    logo_storage_key: str | None,
    logo_dark_storage_key: str | None,
    cover_storage_key: str | None,
    media_variants: dict[str, Any] | None,
    language: str,
) -> dict[str, str | None]:
    """The three company links for a reader, keyed by their response fields.

    Each slot shows the reader's language variant when there is one, else
    the common file (H38). Takes the columns rather than a CompanyProfile
    so the aggregate SELECTs of dashboard and portfolio can use it too.
    """
    base = {
        CompanyMediaSlot.LOGO: logo_storage_key,
        CompanyMediaSlot.LOGO_DARK: logo_dark_storage_key,
        CompanyMediaSlot.COVER: cover_storage_key,
    }
    result: dict[str, str | None] = {}
    for slot, field in _COMPANY_URL_FIELD.items():
        result[field] = await presign_media(
            variant_key(media_variants, language, slot.value, base[slot]),
            event="company_media_presign_failed",
            slot=slot.value,
            company_id=str(company_id),
        )
    return result


async def profile_media_urls(profile: Any, language: str) -> dict[str, str | None]:
    """company_media_urls() of one CompanyProfile row, for `language`."""
    return await company_media_urls(
        profile.id,
        logo_storage_key=profile.logo_storage_key,
        logo_dark_storage_key=profile.logo_dark_storage_key,
        cover_storage_key=profile.cover_storage_key,
        media_variants=profile.media_variants,
        language=language,
    )


async def company_image_variants(profile: Any) -> dict[str, dict[str, str | None]]:
    """Every picture of the company per language, as links -- for the
    editing screens: {"en": {"logo_url": ..., ...}, "ru": {...}}.

    "en" is the COMMON file -- English is the common file, never a
    variant -- so an editor shows it under its own key: the displayed
    logo_url / cover_url are the READER's, and a Russian-speaking editor
    would otherwise see the Russian variant in the common file's place.
    """
    result: dict[str, dict[str, str | None]] = {
        BASE_LANGUAGE: await profile_media_urls(profile, BASE_LANGUAGE)
    }
    for language, slots in (profile.media_variants or {}).items():
        result[language] = {
            field: await presign_media(
                slots.get(slot.value),
                event="company_media_presign_failed",
                slot=slot.value,
                company_id=str(profile.id),
                language=language,
            )
            for slot, field in _COMPANY_URL_FIELD.items()
        }
    return result


async def product_cover_url(product: Any, language: str) -> str | None:
    """Presigned link to a product's cover for `language`, or None."""
    return await presign_media(
        variant_key(product.media_variants, language, "cover", product.cover_storage_key),
        event="product_cover_presign_failed",
        product_id=str(product.id),
    )


async def cover_variants(row: Any, event: str) -> dict[str, dict[str, str | None]]:
    """A product's cover per language, as links -- for the editing screens:
    {"en": {"cover_url": <common>}, "ru": {"cover_url": <variant>}}.
    "en" is the common file (see company_image_variants)."""
    return {
        BASE_LANGUAGE: {
            "cover_url": await presign_media(
                row.cover_storage_key, event=event, row_id=str(row.id)
            )
        },
        **{
            language: {
                "cover_url": await presign_media(
                    slots.get("cover"), event=event, row_id=str(row.id), language=language
                )
            }
            for language, slots in (row.media_variants or {}).items()
        },
    }


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

_COMPANY_LINK_FIELDS = frozenset({"logo_url", "logo_dark_url", "cover_url"})
# Fields built here, not read off the row.
_BUILT = frozenset({"base", "translations", "image_variants"})


def _row_fields(response_cls: type[BaseModel], row: Any, skip: frozenset[str]) -> dict[str, Any]:
    """Every field of `response_cls` read off the ORM row, except `skip`."""
    return {
        name: getattr(row, name)
        for name in response_cls.model_fields
        if name not in skip and name not in _BUILT
    }


def texts(row: Any, language: str, fields: tuple[str, ...]) -> dict[str, Any]:
    """The row's translatable fields in `language`, else English (H38)."""
    return {
        field: localized(row.translations, language, field, getattr(row, field))
        for field in fields
    }


_COMPANY_TEXTS = ("name", "description")
_PRODUCT_TEXTS = ("name", "description")


async def build_company_response(profile: Any, language: str) -> CompanyResponse:
    """CompanyResponse of one row for a reader, links signed now.

    Staff and the company itself edit from it, so it also carries the
    English base, the stored translations and the picture variants.
    """
    return CompanyResponse(
        **_row_fields(CompanyResponse, profile, _COMPANY_LINK_FIELDS | set(_COMPANY_TEXTS)),
        **texts(profile, language, _COMPANY_TEXTS),
        **await profile_media_urls(profile, language),
        base=CompanyBaseTexts(name=profile.name, description=profile.description),
        translations=profile.translations or {},
        image_variants=await company_image_variants(profile),
    )


async def build_public_company_response(
    profile: Any, language: str
) -> PublicCompanyResponse:
    """PublicCompanyResponse of one row for a reader, links signed now."""
    return PublicCompanyResponse(
        **_row_fields(
            PublicCompanyResponse, profile, _COMPANY_LINK_FIELDS | set(_COMPANY_TEXTS)
        ),
        **texts(profile, language, _COMPANY_TEXTS),
        **await profile_media_urls(profile, language),
    )


async def build_product_response(product: Any, language: str) -> ProductResponse:
    """ProductResponse of one row for a reader, the cover link signed now,
    plus what the staff editing screen needs (base, translations, variants)."""
    return ProductResponse(
        **_row_fields(ProductResponse, product, frozenset({"cover_url", *_PRODUCT_TEXTS})),
        **texts(product, language, _PRODUCT_TEXTS),
        cover_url=await product_cover_url(product, language),
        base=ProductBaseTexts(name=product.name, description=product.description),
        translations=product.translations or {},
        image_variants=await cover_variants(product, "product_cover_presign_failed"),
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


async def company_logo_data_uri(profile: Any) -> str | None:
    """The project's logo for a document, as a data: URI of its bytes.

    A presigned link would expire, and a purchase agreement is frozen
    into purchases.agreement_html for good -- the document has to carry
    the picture itself, the way templates already inline their own assets
    (make_asset_data_uri_func). The light logo is the one used: documents
    are printed on white.

    Returns None when the project has no logo, or when the key is set but
    its object is gone (logged): nothing would bring that object back, so
    there is nothing to wait for. Any other storage failure propagates --
    the template body comes from the same storage, and the agreement
    snapshot sweep retries a failed render.

    Callers fetch the bytes only when the template references the
    variable (document_utils.template_references), so a template without
    a logo never pays for one.
    """
    key = profile.logo_storage_key
    if not key:
        return None
    # The key was built by company_media_key from an extension
    # validate_media_upload accepted, so the lookup cannot miss.
    mime = ROADMAP_COVER_EXTENSION_TO_MIME[key[key.rfind("."):]]
    try:
        data = await get_object_bytes(key)
    except StorageNotFoundError:
        logger.warning(
            "company_logo_object_missing",
            company_id=str(profile.id),
            storage_key=key,
        )
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


# ---------------------------------------------------------------------------
# Which key a picture service reads and writes (H38)
# ---------------------------------------------------------------------------


def stored_key(row: Any, column: str, slot: str, language: str | None) -> str | None:
    """The key a picture service replaces or removes: the common file's
    column when `language` is None, else that language's variant."""
    if language is None:
        return getattr(row, column)
    return ((row.media_variants or {}).get(language) or {}).get(slot)


def store_key(
    row: Any, column: str, slot: str, language: str | None, key: str | None
) -> None:
    """Point the common column, or one language's variant, at `key`
    (None removes it). The variants map is replaced, never edited in
    place (JSONBMixin.set_jsonb)."""
    if language is None:
        setattr(row, column, key)
    else:
        row.set_jsonb("media_variants", with_variant(row.media_variants, language, slot, key))
