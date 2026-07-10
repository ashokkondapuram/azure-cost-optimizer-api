"""Compatibility shim — implementation: it_services.storage_account.engine.analysis"""

from importlib import import_module

_impl = import_module("it_services.storage_account.engine.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
