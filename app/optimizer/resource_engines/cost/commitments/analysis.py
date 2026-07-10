"""Compatibility shim — implementation: app.optimizer.platform.cost.commitments.analysis"""

from importlib import import_module

_impl = import_module("app.optimizer.platform.cost.commitments.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
