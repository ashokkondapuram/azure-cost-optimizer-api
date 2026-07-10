"""Compatibility shim — implementation: it_services.database_postgresql.engine.sub_engine"""

from importlib import import_module

_impl = import_module("it_services.database_postgresql.engine.sub_engine")


def __getattr__(name: str):
    return getattr(_impl, name)
