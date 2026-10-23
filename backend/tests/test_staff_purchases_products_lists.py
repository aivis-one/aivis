# =============================================================================
# AIVIS.ONE Backend -- Staff purchases list, administrator gate on the gift
# grant, staff product list (DB-free)
# =============================================================================
#
# Checks the query building, the paging, the row kind, the route table and the
# administrator gate without a database. Run with:
#   pytest --noconftest tests/test_staff_purchases_products_lists.py
# =============================================================================

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import ForbiddenError
from app.modules.companies.staff_router import router as companies_router
from app.modules.products.constants import VALID_PRODUCT_STATUS_TRANSITIONS
from app.modules.purchases.schemas import (
    StaffPurchaseItem,
    StaffPurchaseListResponse,
)
from app.modules.purchases.staff_list_service import (
    build_list_statement,
    build_purchase_filters,
    buyer_name,
    page_offset,
    purchase_kind,
)
from app.modules.purchases.staff_router import router as purchases_router
from app.modules.staff import permissions as staff_permissions
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS


def _sql(statement) -> str:  # type: ignore[no-untyped-def]
    return str(statement.compile(dialect=postgresql.dialect()))


# --- the row kind ---------------------------------------------------------


def test_kind_of_each_legal_basis() -> None:
    assert purchase_kind("sale", None) == "paid"
    assert purchase_kind("installment_tranche", None) == "installment"
    assert purchase_kind("gift", None) == "gift"
    assert purchase_kind("gift", uuid4()) == "bonus"


# --- paging -----------------------------------------------------------------


def test_page_offset_is_one_based() -> None:
    assert page_offset(1, 20) == 0
    assert page_offset(2, 20) == 20
    assert page_offset(5, 100) == 400


def test_statement_carries_limit_and_offset() -> None:
    sql = _sql(build_list_statement([], page=3, per_page=25))
    assert "LIMIT" in sql and "OFFSET" in sql
    compiled = build_list_statement([], page=3, per_page=25).compile(
        dialect=postgresql.dialect()
    )
    assert 50 in compiled.params.values()
    assert 25 in compiled.params.values()


def test_statement_is_newest_first_and_joins_buyer_project_product() -> None:
    sql = _sql(build_list_statement([], page=1, per_page=20))
    assert "ORDER BY purchases.created_at DESC" in sql
    assert "JOIN users" in sql
    assert "JOIN company_profiles" in sql
    assert "JOIN products" in sql


# --- filters ----------------------------------------------------------------


def test_no_filter_adds_no_condition() -> None:
    assert build_purchase_filters() == []
    assert "WHERE" not in _sql(build_list_statement([], page=1, per_page=20))


def test_each_filter_adds_one_condition_on_its_column() -> None:
    company = uuid4()
    buyer = uuid4()
    conditions = build_purchase_filters(
        status="pending_acceptance", company_id=company, buyer_id=buyer
    )
    assert len(conditions) == 3
    sql = _sql(build_list_statement(conditions, page=1, per_page=20))
    assert "purchases.status =" in sql
    assert "purchases.company_id =" in sql
    assert "purchases.investor_id =" in sql


def test_a_single_filter_adds_only_its_condition() -> None:
    conditions = build_purchase_filters(status="active")
    assert len(conditions) == 1
    assert "company_id =" not in _sql(
        build_list_statement(conditions, page=1, per_page=20)
    )


# --- the response -----------------------------------------------------------


def test_buyer_name_from_profile() -> None:
    assert buyer_name({"first_name": "Ann", "last_name": "Lee"}) == "Ann Lee"
    assert buyer_name({"first_name": "Ann"}) == "Ann"
    assert buyer_name({}) is None
    assert buyer_name(None) is None


def test_list_response_shape() -> None:
    item = StaffPurchaseItem(
        id=uuid4(),
        created_at=datetime.now(UTC),
        buyer_id=uuid4(),
        buyer_email="a@example.com",
        buyer_name=None,
        company_id=uuid4(),
        company_name="Project",
        product_id=uuid4(),
        product_name="Package",
        units=10,
        paid_cents=0,
        kind="gift",
        legal_basis="gift",
        status="pending_acceptance",
    )
    body = StaffPurchaseListResponse(
        items=[item], total=41, page=2, per_page=20
    ).model_dump()
    assert body["total"] == 41
    assert body["page"] == 2
    assert body["items"][0]["kind"] == "gift"


# --- the routes -------------------------------------------------------------


def _route(router, method: str, path: str):  # type: ignore[no-untyped-def]
    for route in router.routes:
        if route.path == path and method in route.methods:
            return route
    raise AssertionError(f"{method} {path} is not routed")


def _guard_names(route) -> list[str]:  # type: ignore[no-untyped-def]
    return [dep.call.__name__ for dep in route.dependant.dependencies]


def test_purchases_list_is_a_get_guarded_by_financial_operations() -> None:
    route = _route(purchases_router, "GET", "/api/v1/staff/purchases")
    assert route.methods == {"GET"}
    assert "require_financial_operations" in _guard_names(route)
    query_names = {p.name for p in route.dependant.query_params}
    assert {"company_id", "buyer_id", "page", "per_page"} <= query_names
    status_param = next(p for p in route.dependant.query_params if p.name == "purchase_status")
    assert status_param.field_info.alias == "status"


def test_purchases_list_page_size_is_capped_at_100() -> None:
    route = _route(purchases_router, "GET", "/api/v1/staff/purchases")
    per_page = next(p for p in route.dependant.query_params if p.name == "per_page")
    limits = [m.__class__.__name__ for m in per_page.field_info.metadata]
    assert "Le" in limits
    assert any(getattr(m, "le", None) == 100 for m in per_page.field_info.metadata)


def test_gift_cancel_stays_on_financial_operations() -> None:
    route = _route(
        purchases_router, "POST", "/api/v1/staff/purchases/gifts/{purchase_id}/cancel"
    )
    assert "require_financial_operations" in _guard_names(route)


def test_gift_grant_is_guarded_by_financial_operations_and_admin() -> None:
    route = _route(purchases_router, "POST", "/api/v1/staff/purchases/gifts")
    assert "require_financial_operations" in _guard_names(route)
    # The administrator check runs inside the endpoint (tested below).
    import inspect

    from app.modules.purchases import staff_router

    source = inspect.getsource(staff_router.grant_gift_endpoint)
    assert "await require_admin(staff, session)" in source
    assert source.index("require_admin") < source.index("grant_gift(")


def test_company_products_list_is_a_get_guarded_by_company_manage() -> None:
    route = _route(
        companies_router, "GET", "/api/v1/staff/companies/{company_id}/products"
    )
    assert "require_company_manage" in _guard_names(route)
    query_names = {p.name for p in route.dependant.query_params}
    assert {"page", "per_page"} <= query_names


# --- the administrator gate -------------------------------------------------


def _stub_profile(monkeypatch: pytest.MonkeyPatch, permissions) -> None:  # type: ignore[no-untyped-def]
    async def fake_get_staff_profile(user_id: UUID, session):  # type: ignore[no-untyped-def]
        if permissions is None:
            return None
        return SimpleNamespace(permissions=permissions)

    monkeypatch.setattr(staff_permissions, "get_staff_profile", fake_get_staff_profile)


async def test_require_admin_refuses_a_member_with_one_permission_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_profile(monkeypatch, {})  # the defaults leave some keys False
    with pytest.raises(ForbiddenError):
        await staff_permissions.require_admin(SimpleNamespace(id=uuid4()), None)  # type: ignore[arg-type]


async def test_require_admin_refuses_a_missing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_profile(monkeypatch, None)
    with pytest.raises(ForbiddenError):
        await staff_permissions.require_admin(SimpleNamespace(id=uuid4()), None)  # type: ignore[arg-type]


async def test_require_admin_admits_every_permission_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_profile(monkeypatch, {key: True for key in DEFAULT_STAFF_PERMISSIONS})
    await staff_permissions.require_admin(SimpleNamespace(id=uuid4()), None)  # type: ignore[arg-type]


# --- product status transitions the screen offers ---------------------------


def test_product_transitions_the_screen_mirrors() -> None:
    assert VALID_PRODUCT_STATUS_TRANSITIONS["hidden"] == {"active", "archived"}
    assert VALID_PRODUCT_STATUS_TRANSITIONS["active"] == {"hidden", "archived"}
    assert VALID_PRODUCT_STATUS_TRANSITIONS["archived"] == frozenset()
