# =============================================================================
# AIVIS.ONE Backend -- KYC Constants (H10, extended H12)
# =============================================================================
#
# The price of a verification session, the vocabulary the gate refuses
# with, and -- since H12 -- the vocabulary of the documents a session
# carries and of the mode that decides it. All of it is read by the
# frontend: the price to say what the deposit has to cover, the codes to
# decide which screen to show, the document rules to build the form.
#
# NO APP IMPORTS HERE, and that is load-bearing rather than tidy.
# kyc/models.py imports this module AND users/models.py (for KYCStatus,
# which owns the status vocabulary -- see the note there). An import
# back into a model from this file would close that loop and break the
# app at startup.
# =============================================================================

import enum

# THE FEE BUYS A SESSION, NOT AN ATTEMPT, and it is taken BEFORE the
# verification runs, not after. Charging on success would make a flood of
# junk photographs free; charging on start makes every attempt cost the
# same whatever it produces. A user who comes back to a session that is
# still open pays nothing extra -- only a session that reached a terminal
# decision requires a new one.
KYC_VERIFICATION_FEE_CENTS: int = 1000

# -----------------------------------------------------------------------------
# Refusal codes
# -----------------------------------------------------------------------------
# FOUR CODES ON ONE STATUS, NOT FOUR STATUSES. 402 says "this account has
# not passed verification"; which of the four screens to show is a
# product decision the frontend makes from the code, and no HTTP status
# distinguishes "pay", "wait", "you were refused" and "we took it back".
# Splitting them across 402/409/423 would have the client read a number
# that says nothing about any of those four states.
KYC_CODE_PAYMENT_REQUIRED: str = "kyc_payment_required"
KYC_CODE_PENDING: str = "kyc_pending"
KYC_CODE_REJECTED: str = "kyc_rejected"
KYC_CODE_REVOKED: str = "kyc_revoked"


# -----------------------------------------------------------------------------
# Verification mode (H12)
# -----------------------------------------------------------------------------


class VerificationMode(enum.StrEnum):
    """Who decides a verification session: staff, or the provider.

    MANUAL is the only mode that decides anything today. AUTOMATIC is
    the setting the provider pass (H13) will read; until it lands, the
    submit path does not branch on this value at all -- see the note on
    KYCApplication.decision_mode for why the column is written anyway.
    """

    MANUAL = "manual"
    AUTOMATIC = "automatic"



# -----------------------------------------------------------------------------
# Documents (H12)
# -----------------------------------------------------------------------------


class KYCDocumentType(enum.StrEnum):
    """What the person is showing us."""

    PASSPORT = "passport"
    ID_CARD = "id_card"
    DRIVING_LICENCE = "driving_licence"


class KYCDocumentKind(enum.StrEnum):
    """Which face of the submission a stored object is.

    FRONT and BACK are the two the provider endpoint takes by these
    names. SELFIE is ours: it is what lets a human say the document
    belongs to the person, rather than only that the document is real.
    """

    FRONT = "front"
    BACK = "back"
    SELFIE = "selfie"


# A passport's identity page is one page; demanding a second photograph
# of its cover would be asking for a picture of nothing. The other two
# carry half their data on the reverse, so a decision made on the front
# alone would be made on half the document.
DOCUMENT_TYPES_REQUIRING_BACK: frozenset[str] = frozenset(
    {
        KYCDocumentType.ID_CARD,
        KYCDocumentType.DRIVING_LICENCE,
    }
)

# MIME -> file extension. NOT a subset of the company-attachment
# whitelist, and deliberately much shorter than it:
#   - no SVG: it is script-capable, and this is the vector that put
#     extension-based MIME detection into companies/service.py;
#   - no PDF: the provider endpoint (H13) takes images, so a PDF here
#     would buy the next pass a conversion step nobody asked for;
#   - no WebP: whether the provider accepts it is unverified, and an
#     upload we cannot forward is an upload we should not have taken;
#   - no office formats and no video: a passport is a photograph.
# HEIC is absent on purpose and refused by name -- see the error code
# kyc_document_heic. Converting it needs a new dependency; refusing it
# silently as "unknown extension" would tell an iPhone owner nothing
# about what to do next.
KYC_ALLOWED_MIME_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
}

# Extension -> MIME, for validating what the browser sent us by the
# name it sent it under. Two spellings of JPEG reach us in practice.
KYC_EXTENSION_MIME_TYPES: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

# Extensions we recognise well enough to refuse by name rather than as
# "unknown". HEIC/HEIF is what an iPhone produces when the user picks a
# file out of the Files app instead of the camera roll.
KYC_HEIC_EXTENSIONS: frozenset[str] = frozenset({"heic", "heif"})

# Ten megabytes per file. A phone photograph of a passport is one to
# four; the attachment surface's 100 MB is sized for company decks and
# would let somebody park a hundred megabytes of anything in the
# prefix that holds identity documents forever.
KYC_MAX_DOCUMENT_BYTES: int = 10 * 1024 * 1024

# Minutes, per the storage decision: a link long enough to open and too
# short to pass around. Attachments use 900s for authenticated
# downloads; a passport is not an attachment.
KYC_PRESIGNED_URL_TTL_SECONDS: int = 300

# Identity documents live under their own top-level prefix, away from
# company attachments and document templates. An operator listing this
# prefix knows exactly what they are looking at, and a bucket policy
# written later has one thing to name.
KYC_STORAGE_PREFIX: str = "kyc/applications"
