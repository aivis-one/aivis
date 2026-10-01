# =============================================================================
# AIVIS.ONE Backend -- document emails link to the document itself (H27 P-106)
# =============================================================================
#
# WHAT THIS GUARDS. Both document emails -- per-purchase agreement and
# per-company ownership certificate -- carry ONE link, built by
# purchases/document_utils.py::documents_link. Until P-106 that link was the
# investor portfolio LIST for every letter and every reader, agents included.
# Now it names the document: the company always, the purchase for an
# agreement, and a role-neutral path the frontend resolves after sign-in.
#
# WHY THE EMITTERS ARE CALLED DIRECTLY WITH STAND-INS. The assertion is about
# the text the emitter hands to emit_event, nothing about the outbox row or
# the HTTP layer (test_agreement_endpoints / test_ownership_endpoints cover
# the routes, and patch these very emitters out). comms_configured and
# emit_event are patched as the service module sees them, the pattern
# test_auth_password_reset uses; the data carriers are plain namespaces with
# exactly the attributes the emitters read, so no database is needed and none
# is touched.
# =============================================================================

from __future__ import annotations

from datetime import datetime, UTC
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.modules.purchases import agreement_service, ownership_certificate_service
from app.modules.purchases.document_utils import documents_link

BASE = "https://app.example.test"


@pytest.fixture(autouse=True)
def _base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", BASE)


def _capture(monkeypatch: pytest.MonkeyPatch, module) -> list[dict]:  # type: ignore[no-untyped-def]
    captured: list[dict] = []

    async def _fake_emit(_session, _event_type, data):  # type: ignore[no-untyped-def]
        captured.append(data)

    monkeypatch.setattr(module, "comms_configured", lambda: True)
    monkeypatch.setattr(module, "emit_event", _fake_emit)
    return captured


def _link_line(body: str) -> str:
    """The one line of the body that carries the link -- exactly one."""
    lines = [ln for ln in body.splitlines() if BASE in ln]
    assert len(lines) == 1, f"expected one link line, found {len(lines)}: {lines}"
    return lines[0]


# ---------------------------------------------------------------------------
# documents_link -- the address itself
# ---------------------------------------------------------------------------


def test_agreement_link_names_company_and_purchase() -> None:
    company, purchase = uuid4(), uuid4()
    link = documents_link(company, purchase)
    assert link == f"{BASE}/portfolio/{company}?doc=agreement&purchase={purchase}"


def test_certificate_link_names_company_and_no_purchase() -> None:
    """EMPTINESS AXIS: no purchase -> the certificate, and no `purchase` key
    at all (an empty `purchase=` would be a malformed agreement link)."""
    company = uuid4()
    link = documents_link(company)
    assert link == f"{BASE}/portfolio/{company}?doc=ownership"
    assert "purchase" not in link


def test_links_are_role_neutral_and_carry_no_token() -> None:
    """The pair: the old destination is gone AND the new one is there with a
    non-empty id. Neither shell is chosen here, and nothing secret travels."""
    company, purchase = uuid4(), uuid4()
    for link in (documents_link(company, purchase), documents_link(company)):
        assert "/investor/" not in link and "/agent/" not in link
        segment = link.split("/portfolio/", 1)[1].split("?", 1)[0]
        assert segment == str(company) and segment != ""
        assert "token" not in link


def test_repeated_calls_give_one_address_per_document() -> None:
    """REPETITION AXIS: the same document always gets the same address, and
    two purchases of one company never share one."""
    company, p1, p2 = uuid4(), uuid4(), uuid4()
    assert documents_link(company, p1) == documents_link(company, p1)
    assert documents_link(company, p1) != documents_link(company, p2)


# ---------------------------------------------------------------------------
# The two emitters put that address into the letter
# ---------------------------------------------------------------------------


async def test_agreement_email_links_to_this_purchase(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture(monkeypatch, agreement_service)
    company_id = uuid4()
    purchase_id = UUID("1a2b3c4d-0000-4000-8000-000000000001")
    data = SimpleNamespace(
        investor_email="buyer@example.test",
        investor_name="Buyer",
        company=SimpleNamespace(id=company_id, name="Acme"),
        product=SimpleNamespace(name="Unit"),
        purchase=SimpleNamespace(
            id=purchase_id, user_id=uuid4(), units=3, paid_cents=150000
        ),
    )

    await agreement_service.request_agreement_email(data, None)  # type: ignore[arg-type]

    assert len(captured) == 1
    line = _link_line(captured[0]["body"])
    assert line.endswith(documents_link(company_id, purchase_id))


async def test_ownership_email_links_to_this_company(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture(monkeypatch, ownership_certificate_service)
    company_id = uuid4()
    data = SimpleNamespace(
        investor_email="holder@example.test",
        investor_name="Holder",
        investor_id=uuid4(),
        company=SimpleNamespace(id=company_id, name="Acme"),
        total_units=7,
        current_value_cents=250000,
        as_of_date=datetime.now(UTC),
    )

    await ownership_certificate_service.request_ownership_email(data, None)  # type: ignore[arg-type]

    assert len(captured) == 1
    line = _link_line(captured[0]["body"])
    assert line.endswith(documents_link(company_id))
    assert "purchase" not in line
