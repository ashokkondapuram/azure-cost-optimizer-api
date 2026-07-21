"""Legacy analysis job scopes must not break optimization overview."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_legacy_vmss_scope_does_not_raise():
    from app.analysis_cooldown import is_scoped_analysis, job_is_full_analysis
    from app.models import AnalysisJob

    assert is_scoped_analysis(["Virtual Machine Scale Sets"], None) is False

    job = AnalysisJob(
        id="job-legacy-vmss",
        subscription_id="sub-1",
        status="completed",
        components_json=json.dumps([
            {"component": "Virtual Machine Scale Sets"},
        ]),
    )
    # Legacy labels must not raise; unknown-only scopes are treated as non-scoped.
    job_is_full_analysis(job)


def test_known_scoped_components_still_detected():
    from app.analysis_cooldown import is_scoped_analysis

    assert is_scoped_analysis(["Virtual Machines"], None) is True
    assert is_scoped_analysis(None, ["compute/vm"]) is True
