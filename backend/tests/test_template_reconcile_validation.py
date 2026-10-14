# =============================================================================
# AIVIS.ONE Backend -- Template reconcile: compile check (H34 P-128)
# =============================================================================
#
# Tests cover:
#   1: a template naming a filter or test that does not exist is refused
#      by reconcile, with the reason and the line -- in every position
#      Jinja2 treats differently: a plain expression (a compile error),
#      and an {% if %} condition or inline `a if b else c` (deferred by
#      Jinja2 to render time, so compiling alone lets them through)
#   2: the pair -- a template using real filters and tests, and the
#      asset_data_uri global, is accepted; a syntax error is still
#      refused as a parse error
#   3: reconcile and the renderers are held to the same environment
#
# Pure: _validate_html_against_kind takes the HTML as a string, so
# nothing here touches storage or the database.
# =============================================================================

import pytest
from jinja2 import StrictUndefined

from app.modules.companies.constants import DocumentTemplateKind
from app.modules.purchases.document_utils import build_document_environment
from scripts._template_reconcile_core import _validate_html_against_kind

_KIND = DocumentTemplateKind.PURCHASE_AGREEMENT


@pytest.mark.parametrize(
    "html, reason",
    [
        pytest.param(
            "<p>{{ investor_name|no_such_filter }}</p>",
            "jinja2 compile error: No filter named 'no_such_filter'. (line 1)",
            id="filter-in-expression",
        ),
        pytest.param(
            "<p>\n{% if investor_name|no_such_filter %}x{% endif %}</p>",
            "jinja2 compile error: No filter named 'no_such_filter'. (line 2)",
            id="filter-in-if-condition",
        ),
        pytest.param(
            "<p>{{ 1 if investor_name|no_such_filter else 2 }}</p>",
            "jinja2 compile error: No filter named 'no_such_filter'. (line 1)",
            id="filter-in-inline-if",
        ),
        pytest.param(
            "<p>{{ investor_name is no_such_test }}</p>",
            "jinja2 compile error: No test named 'no_such_test'. (line 1)",
            id="test-in-expression",
        ),
        pytest.param(
            "<p>{% if investor_name is no_such_test %}x{% endif %}</p>",
            "jinja2 compile error: No test named 'no_such_test'. (line 1)",
            id="test-in-if-condition",
        ),
    ],
)
def test_an_unknown_filter_or_test_is_refused(html: str, reason: str) -> None:
    """Before H34 reconcile only PARSED the body, with a bare
    Environment(): every one of these was accepted, and every render of
    it then failed -- the agreement snapshot worker wedged on the first
    such row (P-122). The if-condition and inline-if forms are not even
    compile errors: Jinja2 defers them to render time, which is why
    reconcile also checks every filter and test by name."""
    assert _validate_html_against_kind(html, _KIND, set()) == (set(), reason)


def test_a_valid_template_is_accepted() -> None:
    """The pair of the refusals: real filters, real tests, an if around
    them and the asset_data_uri global all pass, and the referenced asset
    is reported."""
    html = (
        "<p>{{ investor_name|upper }} {{ units|default(0) }}</p>\n"
        "{% if company_logo_url is defined and company_logo_url %}"
        "<img src=\"{{ asset_data_uri('logo.png') }}\">{% endif %}\n"
        "{% if units is number and investor_name|length > 0 %}ok{% endif %}"
    )
    assert _validate_html_against_kind(html, _KIND, {"logo.png"}) == (
        {"logo.png"},
        None,
    )


def test_a_syntax_error_is_still_a_parse_error() -> None:
    """What reconcile refused before H34 it still refuses, the same way."""
    referenced, error = _validate_html_against_kind(
        "<p>{% if %}</p>", _KIND, set()
    )
    assert referenced == set()
    assert error is not None
    assert error.startswith("jinja2 parse error: ")


def test_reconcile_and_render_share_one_environment() -> None:
    """The factory both sides call carries the render hardening, and the
    global only when a renderer passes one: reconcile compiles without it
    (globals are looked up at render time, not at compile time)."""
    def uri(name: str) -> str:
        return f"data:{name}"

    for env in (build_document_environment(None), build_document_environment(uri)):
        assert env.autoescape is True
        assert env.undefined is StrictUndefined
    assert "asset_data_uri" not in build_document_environment(None).globals
    assert build_document_environment(uri).globals["asset_data_uri"] is uri
