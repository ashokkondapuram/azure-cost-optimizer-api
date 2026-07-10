"""Compatibility shim — implementation: it_services.appservice_webapp.engine.sub_engine"""

from importlib import import_module

_impl = import_module("it_services.appservice_webapp.engine.sub_engine")


def __getattr__(name: str):
    return getattr(_impl, name)
