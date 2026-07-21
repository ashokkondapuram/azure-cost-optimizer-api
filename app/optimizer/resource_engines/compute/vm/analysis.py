"""Compatibility shim — implementation: it_services.compute_vm.engine.analysis"""

from importlib import import_module

_impl = import_module("it_services.compute_vm.engine.analysis")


def __getattr__(name: str):
    return getattr(_impl, name)
