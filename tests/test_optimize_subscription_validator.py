"""Regression tests for subscription validation imports in optimize routes."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base

SUB = str(uuid.uuid4()).lower()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_optimize_module_exports_subscription_validator():
    from app.routers import optimize

    assert callable(optimize.ensure_subscription_known)


def test_batch_analysis_calls_ensure_subscription_known(db, monkeypatch):
    from app.routers.optimize import AnalyzeRequest, start_batch_analysis

    called: list[str] = []

    def _ensure(_db, sub):
        called.append(sub)
        return sub.lower()

    monkeypatch.setattr("app.routers.optimize.ensure_subscription_known", _ensure)
    monkeypatch.setattr(
        "app.routers.optimize.require_admin_user",
        lambda _request: {"role": "admin"},
    )
    job = MagicMock(id="job-123")
    monkeypatch.setattr(
        "app.routers.optimize.create_analysis_job",
        lambda *_args, **_kwargs: job,
    )
    monkeypatch.setattr(
        "app.routers.optimize.serialize_job",
        lambda _job: {"job_id": _job.id, "status": "queued"},
    )
    monkeypatch.setattr(
        "app.routers.optimize.execute_batch_job",
        lambda _job_id: None,
    )

    req = AnalyzeRequest(
        subscription_id=SUB,
        data_source="db",
        profile="default",
        engine_version="extended",
    )
    result = start_batch_analysis(req, MagicMock(), MagicMock(), db)

    assert called == [SUB]
    assert result["job_id"] == "job-123"
