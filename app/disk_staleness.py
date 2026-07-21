"""Compatibility shim — implementation: it_services.compute_disk.disk_staleness"""

from importlib import import_module

_impl = import_module("it_services.compute_disk.disk_staleness")


def __getattr__(name: str):
    return getattr(_impl, name)
