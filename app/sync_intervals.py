"""Scheduled sync interval and startup-delay helpers (minutes-first, hours fallback)."""

from __future__ import annotations

import os


def _parse_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def interval_minutes(
    *,
    minutes_env: str,
    hours_envs: tuple[str, ...] = (),
    default_minutes: float,
    minimum_minutes: float = 1.0,
) -> float:
    """Resolve a sync interval in minutes from env (minutes var wins over hours vars)."""
    raw_minutes = os.getenv(minutes_env)
    if raw_minutes is not None and str(raw_minutes).strip():
        return max(minimum_minutes, _parse_float(minutes_env, default_minutes))

    for hours_env in hours_envs:
        raw_hours = os.getenv(hours_env)
        if raw_hours is not None and str(raw_hours).strip():
            hours = _parse_float(hours_env, default_minutes / 60.0)
            return max(minimum_minutes, hours * 60.0)

    return max(minimum_minutes, default_minutes)


def startup_delay_seconds(
    env_name: str,
    *,
    legacy_envs: tuple[str, ...] = (),
    default: float = 0.0,
) -> float:
    """Resolve staggered worker startup delay in seconds."""
    for name in (env_name, *legacy_envs):
        raw = os.getenv(name)
        if raw is not None and str(raw).strip():
            return max(0.0, _parse_float(name, default))
    return max(0.0, default)


def cost_sync_interval_minutes() -> float:
    return interval_minutes(
        minutes_env="COST_SYNC_INTERVAL_MINUTES",
        hours_envs=("COST_REFRESH_HOURS", "COST_EXPORT_REFRESH_HOURS"),
        default_minutes=60.0,
    )


def cost_sync_startup_delay_seconds() -> float:
    return startup_delay_seconds(
        "COST_SYNC_STARTUP_DELAY_SEC",
        legacy_envs=("COST_REFRESH_STARTUP_DELAY_SEC",),
        default=0.0,
    )


def metrics_sync_interval_minutes() -> float:
    return interval_minutes(
        minutes_env="METRICS_SYNC_INTERVAL_MINUTES",
        hours_envs=("METRICS_SYNC_INTERVAL_HOURS",),
        default_minutes=30.0,
    )


def metrics_sync_startup_delay_seconds() -> float:
    return startup_delay_seconds(
        "METRICS_SYNC_STARTUP_DELAY_SEC",
        default=120.0,
    )


def inventory_sync_interval_minutes() -> float:
    return interval_minutes(
        minutes_env="INVENTORY_SYNC_INTERVAL_MINUTES",
        hours_envs=("RESOURCE_DISCOVERY_HOURS", "COST_REFRESH_HOURS"),
        default_minutes=15.0,
    )


def inventory_sync_startup_delay_seconds() -> float:
    return startup_delay_seconds(
        "INVENTORY_SYNC_STARTUP_DELAY_SEC",
        legacy_envs=("RESOURCE_DISCOVERY_STARTUP_DELAY_SEC",),
        default=60.0,
    )


def analysis_sync_interval_minutes() -> float:
    return interval_minutes(
        minutes_env="ANALYSIS_SYNC_INTERVAL_MINUTES",
        hours_envs=("SCHEDULED_ANALYSIS_HOURS",),
        default_minutes=10.0,
    )


def analysis_sync_startup_delay_seconds() -> float:
    return startup_delay_seconds(
        "ANALYSIS_SYNC_STARTUP_DELAY_SEC",
        legacy_envs=("SCHEDULED_STARTUP_DELAY_SECONDS",),
        default=180.0,
    )
