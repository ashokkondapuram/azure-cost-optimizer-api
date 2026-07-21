"""Tests for canonical resource API path registry."""

from app.resource_api_paths import (
    API_PATH_TO_CANONICAL,
    CANONICAL_TO_API_PATH,
    canonical_api_path,
    canonical_from_api_path,
    canonical_types_for_api_path,
)


def test_canonical_api_path_uses_canonical_type():
    assert canonical_api_path("compute/disk") == "/resources/compute/disk"
    assert canonical_api_path("containers/aks") == "/resources/containers/aks"


def test_legacy_and_canonical_paths_resolve_same_type():
    assert canonical_from_api_path("/resources/disks") == "compute/disk"
    assert canonical_from_api_path("/resources/compute/disk") == "compute/disk"
    assert canonical_types_for_api_path("/resources/compute/vm") == ["compute/vm"]


def test_canonical_to_api_path_covers_core_types():
    assert CANONICAL_TO_API_PATH["compute/vm"] == "/resources/compute/vm"
    assert API_PATH_TO_CANONICAL["/resources/vms"] == "compute/vm"
    assert API_PATH_TO_CANONICAL["/resources/compute/vm"] == "compute/vm"
