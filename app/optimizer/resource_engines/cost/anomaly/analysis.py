"""Compatibility shim — implementation: app.optimizer.platform.cost.anomaly.analysis"""

from importlib import import_module

_impl = import_module("app.optimizer.platform.cost.anomaly.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
