"""Tests for AKS Kubernetes version parsing (Azure ARM response shapes)."""

from app.aks_versions import (
    is_minor_version_supported,
    normalize_k8s_minor,
    parse_kubernetes_versions_response,
    supported_minor_versions,
)

SAMPLE_ARM_RESPONSE = {
    "values": [
        {
            "version": "1.29",
            "isDefault": False,
            "patchVersions": {"1.29.7": {"upgrades": ["1.30.0"]}},
        },
        {
            "version": "1.30",
            "isDefault": True,
            "patchVersions": {"1.30.2": {"upgrades": ["1.31.0"]}},
        },
        {
            "version": "1.31",
            "isPreview": True,
            "patchVersions": {"1.31.0": {"upgrades": []}},
        },
    ]
}


def test_normalize_k8s_minor():
    assert normalize_k8s_minor("1.29.7") == "1.29"
    assert normalize_k8s_minor("1.30") == "1.30"
    assert normalize_k8s_minor("") == ""


def test_parse_kubernetes_versions_response():
    parsed = parse_kubernetes_versions_response(SAMPLE_ARM_RESPONSE)
    assert len(parsed) == 3
    assert parsed[1].is_default is True
    assert parsed[2].is_preview is True


def test_supported_minor_versions_includes_preview_by_default():
    parsed = parse_kubernetes_versions_response(SAMPLE_ARM_RESPONSE)
    assert supported_minor_versions(parsed) == {"1.29", "1.30", "1.31"}


def test_supported_minor_versions_excludes_preview_when_requested():
    parsed = parse_kubernetes_versions_response(SAMPLE_ARM_RESPONSE)
    assert supported_minor_versions(parsed, include_preview=False) == {"1.29", "1.30"}


def test_is_minor_version_supported():
    supported = {"1.29", "1.30"}
    assert is_minor_version_supported("1.29.7", supported) is True
    assert is_minor_version_supported("1.28.3", supported) is False
    assert is_minor_version_supported("1.28.3", set()) is None
