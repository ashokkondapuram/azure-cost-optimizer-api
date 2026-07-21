"""Compatibility shim — implementation: it_services.backup_recoveryvault.resource_profile"""

from importlib import import_module

_impl = import_module("it_services.backup_recoveryvault.resource_profile")


def __getattr__(name: str):
    return getattr(_impl, name)
