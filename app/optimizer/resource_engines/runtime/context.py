"""Compatibility shim — implementation: app.optimizer.platform.runtime.context"""

from importlib import import_module

_impl = import_module("app.optimizer.platform.runtime.context")


def __getattr__(name: str):
    return getattr(_impl, name)
