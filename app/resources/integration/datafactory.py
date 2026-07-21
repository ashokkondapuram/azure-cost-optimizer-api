"""Compatibility shim — implementation: it_services.integration_datafactory.resource_profile"""

from importlib import import_module

_impl = import_module("it_services.integration_datafactory.resource_profile")


def __getattr__(name: str):
    return getattr(_impl, name)
