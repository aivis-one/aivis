# =============================================================================
# CBSHOME Backend -- Notification Template Engine (Sprint 8.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Load YAML templates, render with variable substitution, language fallback.
#
# ARCHITECTURE:
#   SafeDict        -- dict subclass that returns "{key}" for missing keys
#   load_templates() -- load and cache YAML for a language
#   reload_templates() -- clear cache (called by staff endpoint)
#   render()         -- render a template with variables + language fallback
#
# TEMPLATE STRUCTURE (YAML):
#   {notification_type}.{channel}.{field}
#   e.g. transaction.telegram.body, transaction.email.subject
#
# LANGUAGE FALLBACK:
#   Requested language -> "en". If "en" also missing -> raw fallback string.
# =============================================================================

from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger()

# Directory containing language YAML files (en.yaml, ru.yaml, etc.).
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Module-level cache: {lang: {type: {channel: {field: template_str}}}}.
_cache: dict[str, dict] = {}


class SafeDict(dict):
    """Dict that returns '{key}' for missing keys instead of raising KeyError.

    Used with str.format_map() to safely render templates when some
    variables are not provided.
    """

    def __missing__(self, key: str) -> str:
        """Return the key wrapped in braces for missing values."""
        return "{" + key + "}"


def load_templates(lang: str) -> dict:
    """Load and cache templates for a language.

    Args:
        lang: Language code (e.g. "en", "ru").

    Returns:
        Nested dict {type: {channel: {field: template_str}}}.
        Empty dict if file not found.
    """
    if lang in _cache:
        return _cache[lang]

    # Sanitize lang to prevent path traversal (e.g. "../../etc/passwd").
    if not lang.isalnum():
        logger.warning("invalid_lang_code", lang=lang)
        lang = "en"

    yaml_path = _TEMPLATES_DIR / f"{lang}.yaml"
    if not yaml_path.exists():
        logger.warning("template_file_not_found", lang=lang, path=str(yaml_path))
        _cache[lang] = {}
        return _cache[lang]

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    _cache[lang] = data
    logger.info("templates_loaded", lang=lang, types=list(data.keys()))
    return data


def reload_templates() -> None:
    """Clear the template cache. Next render() call will reload from disk."""
    _cache.clear()
    logger.info("templates_cache_cleared")


def render(
    notification_type: str,
    channel: str,
    field: str,
    lang: str = "en",
    variables: dict | None = None,
) -> str:
    """Render a notification template with variable substitution.

    Lookup order:
      1. Requested language
      2. Fallback to "en"
      3. Fallback to raw string "{type}.{channel}.{field}"

    Args:
        notification_type: NotificationType value (e.g. "transaction").
        channel: DeliveryChannel value (e.g. "telegram", "email").
        field: Template field (e.g. "body", "subject").
        lang: User language code.
        variables: Dict of variables for substitution.

    Returns:
        Rendered template string.
    """
    template_str = _lookup(notification_type, channel, field, lang)

    if template_str is None and lang != "en":
        # Fallback to English.
        template_str = _lookup(notification_type, channel, field, "en")

    if template_str is None:
        # No template found -- return a raw fallback.
        logger.warning(
            "template_not_found",
            type=notification_type,
            channel=channel,
            field=field,
            lang=lang,
        )
        return f"{notification_type}.{channel}.{field}"

    safe_vars = SafeDict(variables or {})
    return str(template_str).format_map(safe_vars)


def _lookup(
    notification_type: str,
    channel: str,
    field: str,
    lang: str,
) -> str | None:
    """Look up a template string from the cache.

    Returns None if any level of the nested dict is missing.
    """
    templates = load_templates(lang)
    type_block = templates.get(notification_type)
    if not isinstance(type_block, dict):
        return None
    channel_block = type_block.get(channel)
    if not isinstance(channel_block, dict):
        return None
    value = channel_block.get(field)
    if value is None:
        return None
    return str(value)
