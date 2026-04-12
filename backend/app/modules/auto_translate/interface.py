# =============================================================================
# CBSHOME Backend -- Auto-Translate Interface (Sprint 10.1)
# =============================================================================
#
# Stub protocol for future automatic content translation.
#
# AutoTranslateProtocol:
#   Translates text content (posts, notifications, documents)
#   into target language. Implementation deferred to Phase 2.
# =============================================================================

from typing import Protocol


class AutoTranslateProtocol(Protocol):
    """Public interface for the auto-translate module.

    Automatic translation of platform content (posts,
    notifications) into user's preferred language.
    Implementation deferred to Phase 2.
    """

    async def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> str: ...
