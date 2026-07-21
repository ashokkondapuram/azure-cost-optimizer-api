"""Compatibility shim — implementation: app.optimizer.platform.runtime.envelope"""

from importlib import import_module

_impl = import_module("app.optimizer.platform.runtime.envelope")


def __getattr__(name: str):
    return getattr(_impl, name)
