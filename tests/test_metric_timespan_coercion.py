"""Tests for Azure Monitor timespan coercion."""

from app.validators import coerce_metric_timespan


def test_coerce_metric_timespan_from_string():
    assert coerce_metric_timespan("p7d") == "P7D"


def test_coerce_metric_timespan_from_ui_object():
    assert coerce_metric_timespan({"value": "P14D", "label": "Last 14 days"}) == "P14D"


def test_coerce_metric_timespan_falls_back_for_invalid_values():
    assert coerce_metric_timespan({"foo": "bar"}) == "P7D"
    assert coerce_metric_timespan("[object Object]") == "P7D"
    assert coerce_metric_timespan(123) == "P7D"


def test_coerce_metric_timespan_from_json_string():
    assert coerce_metric_timespan('{"value":"P30D","label":"Last 30 days"}') == "P30D"


def test_coerce_metric_timespan_from_lowercase_string():
    assert coerce_metric_timespan("p14d") == "P14D"
