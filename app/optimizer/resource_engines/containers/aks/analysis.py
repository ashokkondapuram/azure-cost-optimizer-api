"""Compatibility shim — implementation: it_services.containers_aks.engine.analysis"""

from importlib import import_module

_impl = import_module("it_services.containers_aks.engine.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
