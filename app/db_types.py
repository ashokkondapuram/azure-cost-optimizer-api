"""Dialect-aware JSON column type — JSONB on PostgreSQL, Text on SQLite."""

from __future__ import annotations

import json

from sqlalchemy import Text, cast
from sqlalchemy.types import TypeDecorator


class JSONText(TypeDecorator):
    """
    Store JSON as native JSONB on PostgreSQL (GIN-indexable) and Text on SQLite.
    Application code always sees a JSON string on read for backward compatibility.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB(astext_type=Text()))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return "{}"
        if isinstance(value, (dict, list)):
            return value if dialect.name == "postgresql" else json.dumps(value)
        if isinstance(value, str):
            if dialect.name == "postgresql":
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {}
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return "{}"
        if isinstance(value, str):
            return value
        return json.dumps(value)


def json_text_like(column, pattern: str):
    """LIKE match on JSONText/JSONB columns (PostgreSQL JSONB has no native LIKE)."""
    return cast(column, Text).like(pattern)


def is_postgres_engine(engine=None) -> bool:
    if engine is None:
        from app.database import engine as default_engine

        engine = default_engine
    return engine.dialect.name == "postgresql"
