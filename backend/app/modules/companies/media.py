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
#   company_media_key()        -- companies/<id>/media/<stem><ext>
#   product_cover_key()        -- companies/<id>/products/<product_id>/cover<ext>
#   validate_media_upload()    -- extension, type and size of one picture
#   presign_media()            -- key -> link or None, never a 5xx
#   company_media_urls()       -- the three company links of one row
#   build_company_response() / build_public_company_response() /
#   build_product_response()   -- the ORM row plus the links
#   company_logo_data_uri()    -- the logo for documents, as bytes inline
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
from app.modules.companies.schemas import CompanyResponse, PublicCompanyResponse
from app.modules.products.schemas import ProductResponse

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


def company_media_key(
    company_id: UUID, slot: CompanyMediaSlot, file_extension: str
) -> str:
    """Object key of one company picture. `file_extension` carries its dot."""
    return f"companies/{company_id}/media/{_COMPANY_MEDIA_STEM[slot]}{file_extension}"


def product_cover_key(company_id: UUID, product_id: UUID, file_extension: str) -> str:
    """Object key of a product's cover. `file_extension` carries its dot."""
    return f"companies/{company_id}/products/{product_id}/cover{file_extension}"


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


async def company_media_urls(
    company_id: UUID,
    *,
    logo_storage_key: str | None,
    logo_dark_storage_key: str | None,
    cover_storage_key: str | None,
) -> dict[str, str | None]:
    """The three company links, keyed by their response field names.

    Takes the keys rather than a CompanyProfile so the aggregate SELECTs
    of dashboard and portfolio, which read columns and not rows, can use
    it too.
    """
    ctx = {"company_id": str(company_id)}
    return {
        "logo_url": await presign_media(
            logo_storage_key, event="company_media_presign_failed", slot="logo", **ctx
        ),
        "logo_dark_url": await presign_media(
            logo_dark_storage_key,
            event="company_media_presign_failed",
            slot="logo_dark",
            **ctx,
        ),
        "cover_url": await presign_media(
            cover_storage_key, event="company_media_presign_failed", slot="cover", **ctx
        ),
    }


async def profile_media_urls(profile: Any) -> dict[str, str | None]:
    """company_media_urls() of one CompanyProfile row."""
    return await company_media_urls(
        profile.id,
        logo_storage_key=profile.logo_storage_key,
        logo_dark_storage_key=profile.logo_dark_storage_key,
        cover_storage_key=profile.cover_storage_key,
    )


async def product_cover_url(product: Any) -> str | None:
    """Presigned link to a product's cover, or None."""
    return await presign_media(
        product.cover_storage_key,
        event="product_cover_presign_failed",
        product_id=str(product.id),
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

_COMPANY_LINK_FIELDS = frozenset({"logo_url", "logo_dark_url", "cover_url"})


def _row_fields(response_cls: type[BaseModel], row: Any, links: frozenset[str]) -> dict[str, Any]:
    """Every field of `response_cls` read off the ORM row, except the links."""
    return {
        name: getattr(row, name)
        for name in response_cls.model_fields
        if name not in links
    }


async def build_company_response(profile: Any) -> CompanyResponse:
    """CompanyResponse of one row, with the links signed now."""
    return CompanyResponse(
        **_row_fields(CompanyResponse, profile, _COMPANY_LINK_FIELDS),
        **await profile_media_urls(profile),
    )


async def build_public_company_response(profile: Any) -> PublicCompanyResponse:
    """PublicCompanyResponse of one row, with the links signed now."""
    return PublicCompanyResponse(
        **_row_fields(PublicCompanyResponse, profile, _COMPANY_LINK_FIELDS),
        **await profile_media_urls(profile),
    )


async def build_product_response(product: Any) -> ProductResponse:
    """ProductResponse of one row, with the cover link signed now."""
    return ProductResponse(
        **_row_fields(ProductResponse, product, frozenset({"cover_url"})),
        cover_url=await product_cover_url(product),
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
