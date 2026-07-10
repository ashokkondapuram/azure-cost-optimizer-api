"""Compatibility shim — implementation: it_services.backup_recoveryvault.engine.analysis"""

from importlib import import_module

_impl = import_module("it_services.backup_recoveryvault.engine.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
