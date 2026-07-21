"""Side-by-side cost period comparison helpers."""

from __future__ import annotations

from typing import Any


def _service_cost_map(payload: dict | None) -> dict[str, float]:
    if not payload:
        return {}
    props = payload.get("properties") or {}
    rows = props.get("rows") or payload.get("rows") or []
    cols = props.get("columns") or payload.get("columns") or []
    name_idx = 0
    cost_idx = 1
    for i, col in enumerate(cols):
        name = (col.get("name") if isinstance(col, dict) else str(col)).lower()
        if "service" in name:
            name_idx = i
        if "pretax" in name or "cost" in name:
            cost_idx = i
    out: dict[str, float] = {}
    for row in rows:
        if not row:
            continue
        name = str(row[name_idx] if len(row) > name_idx else row[0] or "Unknown")
        try:
            cost = float(row[cost_idx] if len(row) > cost_idx else row[1] or 0)
        except (TypeError, ValueError):
            cost = 0.0
        if cost:
            out[name] = out.get(name, 0.0) + cost
    return out


def _period_total(summary: dict | None) -> float:
    if not summary:
        return 0.0
    for key in ("pretax_total", "total_cost", "totalCost"):
        val = summary.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def build_service_deltas(current_map: dict[str, float], compare_map: dict[str, float]) -> list[dict[str, Any]]:
    names = sorted(set(current_map) | set(compare_map))
    rows: list[dict[str, Any]] = []
    for name in names:
        current_cost = round(current_map.get(name, 0.0), 2)
        compare_cost = round(compare_map.get(name, 0.0), 2)
        delta = round(current_cost - compare_cost, 2)
        pct = None
        if compare_cost > 0:
            pct = round((delta / compare_cost) * 100, 1)
        rows.append({
            "service": name,
            "current_cost": current_cost,
            "compare_cost": compare_cost,
            "delta": delta,
            "pct_change": pct,
        })
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return rows


def build_cost_comparison(
  *,
  current_summary: dict | None,
  compare_summary: dict | None,
  current_services: dict | None,
  compare_services: dict | None,
) -> dict[str, Any]:
    current_total = _period_total(current_summary)
    compare_total = _period_total(compare_summary)
    delta = round(current_total - compare_total, 2)
    pct_change = round((delta / compare_total) * 100, 1) if compare_total > 0 else None
    currency = (
        (current_summary or {}).get("billing_currency")
        or (compare_summary or {}).get("billing_currency")
        or "CAD"
    )
    return {
        "currency": currency,
        "current_total": round(current_total, 2),
        "compare_total": round(compare_total, 2),
        "delta": delta,
        "pct_change": pct_change,
        "services": build_service_deltas(
            _service_cost_map(current_services),
            _service_cost_map(compare_services),
        ),
    }
