"""Tests for K8s cluster connection helpers."""
from app.services.k8s_cluster_service import resource_group_from_arm_id


def test_resource_group_from_arm_id():
    arm = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-prod/providers/Microsoft.ContainerService/managedClusters/prod-aks"
    )
    assert resource_group_from_arm_id(arm) == "rg-prod"


def test_resource_group_from_arm_id_missing():
    assert resource_group_from_arm_id("") == ""
