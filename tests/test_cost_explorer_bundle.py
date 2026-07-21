"""Tests for batched Cost Explorer API."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.cost_explorer_bundle import _empty_summary_for_range, _fetch_period
from app.cost_resolve import live_range_kw, resolve_cost_db_only, resolve_cost_db_then_live, resolve_cost_live_then_db
from app.database import SessionLocal, init_db
from app.integration_app import app
from app.models import AppUser, ResourceSnapshot
from app.user_auth import ROLE_ADMIN, create_access_token, hash_password

SUB = "00000000-0000-0000-0000-000000000001"
RANGE_KW = {"timeframe": "MonthToDate"}


def _batched_live(*, daily=True, by_service=True, summary=True):
    payload = {"source": "azure"}
    if daily:
        payload["daily"] = {
            "properties": {"rows": [[10.0, 8.0, "", "2026-06-01", "CAD"]]},
            "source": "azure",
        }
    if by_service:
        payload["by_service"] = {
            "properties": {"rows": [["Virtual Machines", 10.0, 8.0, "CAD"]]},
            "billing_currency": "CAD",
            "source": "azure",
        }
    if summary:
        payload["summary"] = {
            "pretax_total": 10.0,
            "cost_usd_total": 8.0,
            "billing_currency": "CAD",
            "source": "azure",
        }
    return payload


def test_fetch_period_prefer_live_complete_live_response():
    batched = _batched_live()
    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=batched) as live_mock:
        with patch("app.cost_explorer_bundle.daily_cost_response_from_db") as db_daily:
            source, daily, summary, by_service = _fetch_period(
                None,
                subscription_id=SUB,
                timeframe="MonthToDate",
                range_kw=RANGE_KW,
                prefer_live=True,
                token="tok",
            )
    live_mock.assert_called_once()
    db_daily.assert_not_called()
    assert source == "azure"
    assert daily is not None
    assert summary is not None
    assert by_service is not None


def test_fetch_period_prefer_live_partial_live_response_fills_from_db():
    batched = _batched_live(by_service=False, summary=False)
    db_by_service = {
        "properties": {"rows": [["Storage", 5.0, 4.0, "CAD"]]},
        "source": "database",
    }
    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=batched) as live_mock:
        with patch("app.cost_explorer_bundle.cost_by_service_from_db", return_value=db_by_service):
            with patch("app.cost_explorer_bundle.cost_summary_from_db", return_value=None):
                with patch("app.cost_explorer_bundle.daily_cost_response_from_db", return_value=None):
                    source, daily, summary, by_service = _fetch_period(
                        None,
                        subscription_id=SUB,
                        timeframe="MonthToDate",
                        range_kw=RANGE_KW,
                        prefer_live=True,
                        token="tok",
                    )
    live_mock.assert_called_once()
    assert source == "azure"
    assert daily is not None
    assert by_service == db_by_service
    assert summary is not None
    assert summary.get("pretax_total") == 10.0


def test_fetch_period_prefer_live_none_live_response_single_call_db_fallback():
    db_daily = {"properties": {"rows": [[3.0, 2.0, "", "2026-06-02", "CAD"]]}, "source": "database"}
    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=None) as live_mock:
        with patch("app.cost_explorer_bundle.daily_cost_response_from_db", return_value=db_daily):
            with patch("app.cost_explorer_bundle.cost_summary_from_db", return_value=None):
                with patch("app.cost_explorer_bundle.cost_by_service_from_db", return_value=None):
                    source, daily, summary, by_service = _fetch_period(
                        None,
                        subscription_id=SUB,
                        timeframe="MonthToDate",
                        range_kw=RANGE_KW,
                        prefer_live=True,
                        token="tok",
                    )
    live_mock.assert_called_once()
    assert source == "database"
    assert daily == db_daily
    assert summary is not None
    assert summary.get("pretax_total") == 3.0
    assert by_service is None


def test_fetch_period_db_only_skips_live():
    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live") as live_mock:
        with patch("app.cost_explorer_bundle._resolve_period_from_db", return_value=(None, None, None)):
            source, daily, summary, by_service = _fetch_period(
                None,
                subscription_id=SUB,
                timeframe="MonthToDate",
                range_kw=RANGE_KW,
                prefer_live=False,
                token="tok",
                db_only=True,
            )
    live_mock.assert_not_called()
    assert source == "database"
    assert daily is None
    assert summary is None
    assert by_service is None


def test_fetch_period_live_fallback_when_db_empty():
    batched = _batched_live()
    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=batched) as live_mock:
        with patch("app.cost_explorer_bundle._resolve_period_from_db", return_value=(None, None, None)):
            source, daily, summary, by_service = _fetch_period(
                None,
                subscription_id=SUB,
                timeframe="MonthToDate",
                range_kw=RANGE_KW,
                prefer_live=False,
                token="tok",
            )
    live_mock.assert_called_once()
    assert source == "azure"
    assert daily is not None
    assert summary is not None
    assert by_service is not None


def test_fetch_period_prefer_live_batched_receives_live_range_kw_only():
    captured = []

    def _capture(*_args, **kwargs):
        captured.append(kwargs)
        return _batched_live()

    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live", side_effect=_capture):
        with patch(
            "app.cost_explorer_bundle._resolve_period_from_db",
            return_value=(None, None, None),
        ):
            _fetch_period(
                None,
                subscription_id=SUB,
                timeframe="MonthToDate",
                range_kw={"timeframe": "MonthToDate", "resource_types": ["compute/vm"]},
                prefer_live=True,
                token="tok",
            )
    assert captured == []

    with patch("app.cost_explorer_bundle.query_cost_explorer_period_live", side_effect=_capture):
        _fetch_period(
            None,
            subscription_id=SUB,
            timeframe="MonthToDate",
            range_kw={"timeframe": "MonthToDate", "from_date": "2026-06-01"},
            prefer_live=True,
            token="tok",
        )
    assert captured
    assert captured[0]["timeframe"] == "MonthToDate"
    assert captured[0]["from_date"] == "2026-06-01"
    assert "resource_types" not in captured[0]


def test_live_range_kw_excludes_resource_types():
    kw = live_range_kw({
        "timeframe": "MonthToDate",
        "from_date": "2026-06-01",
        "to_date": "2026-06-15",
        "resource_types": ["compute/vm"],
    })
    assert kw == {
        "timeframe": "MonthToDate",
        "from_date": "2026-06-01",
        "to_date": "2026-06-15",
    }


def test_resolve_cost_db_only_skips_live():
    live_calls = []

    def live_call():
        live_calls.append(1)
        return {"live": True}

    result, source = resolve_cost_db_only(
        db_call=lambda: None,
    )
    assert result is None
    assert source is None
    assert live_calls == []


def test_resolve_cost_db_then_live_falls_back_to_live_when_db_empty():
    live_calls = []

    def live_call():
        live_calls.append(1)
        return {"live": True}

    result, source = resolve_cost_db_then_live(
        db_call=lambda: None,
        live_call=live_call,
    )
    assert result == {"live": True}
    assert source == "azure"
    assert live_calls == [1]


def test_resolve_cost_db_then_live_db_first_when_rows_exist():
    live_calls = []

    def live_call():
        live_calls.append(1)
        return {"live": True}

    result, source = resolve_cost_db_then_live(
        db_call=lambda: {"db": True},
        live_call=live_call,
    )
    assert result == {"db": True}
    assert source == "database"
    assert live_calls == []


def test_resolve_cost_live_then_db_prefers_live_when_requested():
    live_calls = []

    def live_call():
        live_calls.append(1)
        return {"live": True}

    result, source = resolve_cost_live_then_db(
        db_call=lambda: None,
        live_call=live_call,
    )
    assert result == {"live": True}
    assert source == "azure"
    assert live_calls == [1]


def test_empty_summary_for_range_ignores_resource_types():
    empty = _empty_summary_for_range({
        "timeframe": "MonthToDate",
        "resource_types": ["compute/vm"],
    })
    assert empty["pretax_total"] == 0.0
    assert empty["sync_required"] is True


def _seed_admin(db) -> str:
    db.query(AppUser).delete()
    db.query(ResourceSnapshot).delete()
    db.commit()
    user = AppUser(
        id="admin-bundle",
        username="admin",
        display_name="Administrator",
        password_hash=hash_password("password123"),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(user)
    for sub_id in (
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ):
        db.add(ResourceSnapshot(
            id=f"snap-{sub_id}",
            subscription_id=sub_id,
            resource_id=f"/subscriptions/{sub_id}/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1",
            resource_name="vm1",
            resource_type="compute/vm",
            resource_group="rg",
            location="eastus",
            is_active=True,
        ))
    db.commit()
    return create_access_token(user_id=user.id, username=user.username, role=ROLE_ADMIN)


@patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=None)
def test_cost_explorer_bundle_returns_all_sections(_mock_live):
    init_db()
    db = SessionLocal()
    try:
        token = _seed_admin(db)
    finally:
        db.close()

    client = TestClient(app)
    sub = "00000000-0000-0000-0000-000000000001"
    resp = client.get(
        "/api/costs/explorer",
        params={"subscription_id": sub, "timeframe": "MonthToDate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "summary" in body
    assert "daily" in body
    assert "by_service" in body
    assert "changes" in body
    assert body["subscription_id"] == sub
    assert "sync_required" in body


@patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=None)
def test_cost_explorer_bundle_with_resource_types_filter(_mock_live):
    init_db()
    db = SessionLocal()
    try:
        token = _seed_admin(db)
    finally:
        db.close()

    client = TestClient(app)
    sub = "00000000-0000-0000-0000-000000000001"
    resp = client.get(
        "/api/costs/explorer",
        params={
            "subscription_id": sub,
            "timeframe": "MonthToDate",
            "resource_types": "compute/vm",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["pretax_total"] == 0.0


@patch("app.cost_explorer_bundle.query_cost_explorer_period_live", return_value=None)
def test_cost_explorer_bundle_includes_compare_when_requested(_mock_live):
    init_db()
    db = SessionLocal()
    try:
        token = _seed_admin(db)
    finally:
        db.close()

    client = TestClient(app)
    sub = "00000000-0000-0000-0000-000000000002"
    resp = client.get(
        "/api/costs/explorer",
        params={
            "subscription_id": sub,
            "timeframe": "MonthToDate",
            "compare_enabled": True,
            "compare_timeframe": "TheLastMonth",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("compare") is not None
    assert "daily" in body["compare"]
    assert "summary" in body["compare"]
