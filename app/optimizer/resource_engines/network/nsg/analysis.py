"""Compatibility shim — implementation: it_services.network_nsg.engine.analysis"""

from importlib import import_module

_impl = import_module("it_services.network_nsg.engine.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
