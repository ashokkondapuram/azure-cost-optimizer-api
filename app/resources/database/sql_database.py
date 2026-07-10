"""Compatibility shim — implementation: it_services.database_sql.sql_database_profile"""

from importlib import import_module

_impl = import_module("it_services.database_sql.sql_database_profile")


def __getattr__(name: str):
    return getattr(_impl, name)
