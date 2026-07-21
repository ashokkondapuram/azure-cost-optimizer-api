"""Compatibility shim — implementation: it_services.network_appgateway.engine.optimization_rules"""

from importlib import import_module

_impl = import_module("it_services.network_appgateway.engine.optimization_rules")


def __getattr__(name: str):
    return getattr(_impl, name)
