"""AKS cluster discovery, connection validation, and utilization-agent deployment."""
from __future__ import annotations

import base64
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.auth import build_credential, resolve_auth_config
from app.models import K8sClusterConnection
from app.services.system_settings import get_effective_config

log = structlog.get_logger(__name__)

_AGENT_NAMESPACE = "finops-agent"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_DIR = _REPO_ROOT / "k8s"
_DEPLOY_DIR = _REPO_ROOT / "deploy" / "k8s-metrics-agent"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resource_group_from_arm_id(arm_id: str) -> str:
    parts = (arm_id or "").split("/")
    try:
        idx = parts.index("resourceGroups")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


def _aks_client(subscription_id: str, db: Session):
    from azure.mgmt.containerservice import ContainerServiceClient

    cred = build_credential(resolve_auth_config(db))
    return ContainerServiceClient(cred, subscription_id)


def _k8s_modules():
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes.client.rest import ApiException
    return k8s_client, k8s_config, ApiException


def _cluster_row_dict(row: K8sClusterConnection) -> dict[str, Any]:
    return {
        "id": row.id,
        "subscription_id": row.subscription_id,
        "resource_group": row.resource_group,
        "cluster_name": row.cluster_name,
        "arm_id": row.arm_id,
        "location": row.location,
        "kubernetes_version": row.kubernetes_version,
        "agent_deployed": bool(row.agent_deployed),
        "agent_status": row.agent_status or "not_deployed",
        "agent_deployed_at": str(row.agent_deployed_at) if row.agent_deployed_at else None,
        "last_validated_at": str(row.last_validated_at) if row.last_validated_at else None,
        "last_error": row.last_error,
        "created_at": str(row.created_at) if row.created_at else None,
    }


def list_connected_clusters(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(K8sClusterConnection)
        .order_by(K8sClusterConnection.cluster_name.asc())
        .all()
    )
    return [_cluster_row_dict(row) for row in rows]


def discover_aks_clusters(db: Session, subscription_id: str) -> list[dict[str, Any]]:
    client = _aks_client(subscription_id, db)
    out: list[dict[str, Any]] = []
    for cluster in client.managed_clusters.list():
        pools = cluster.agent_pool_profiles or []
        out.append({
            "name": cluster.name,
            "resource_group": resource_group_from_arm_id(cluster.id or ""),
            "subscription_id": subscription_id,
            "location": cluster.location,
            "kubernetes_version": cluster.kubernetes_version,
            "arm_id": cluster.id,
            "node_count": sum((p.count or 0) for p in pools),
            "pool_count": len(pools),
        })
    out.sort(key=lambda item: (item.get("name") or "").lower())
    return out


def _kubeconfig_for_cluster(
    db: Session,
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
) -> str:
    client = _aks_client(subscription_id, db)
    creds = client.managed_clusters.list_cluster_user_credentials(resource_group, cluster_name)
    if not creds.kubeconfigs:
        raise ValueError("AKS did not return cluster user credentials")
    return base64.b64decode(creds.kubeconfigs[0].value).decode("utf-8")


def _api_client_from_kubeconfig(kubeconfig: str):
    k8s_client, k8s_config, _ = _k8s_modules()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fh:
        fh.write(kubeconfig)
        path = fh.name
    try:
        k8s_config.load_kube_config(config_file=path)
        return k8s_client.ApiClient()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def validate_cluster_access(
    db: Session,
    *,
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
) -> dict[str, Any]:
    client = _aks_client(subscription_id, db)
    cluster = client.managed_clusters.get(resource_group, cluster_name)
    kubeconfig = _kubeconfig_for_cluster(db, subscription_id, resource_group, cluster_name)
    api = _api_client_from_kubeconfig(kubeconfig)
    k8s_client, _, ApiException = _k8s_modules()
    core = k8s_client.CoreV1Api(api)
    nodes = core.list_node()
    metrics_ok = False
    metrics_api = k8s_client.CustomObjectsApi(api)
    try:
        metrics_api.list_cluster_custom_object(
            group="metrics.k8s.io", version="v1beta1", plural="nodes", limit=1,
        )
        metrics_ok = True
    except ApiException as exc:
        api.close()
        raise ValueError(
            "metrics-server is not available in this cluster. "
            "Install metrics-server before deploying the utilization agent."
        ) from exc
    api.close()

    pools = cluster.agent_pool_profiles or []
    return {
        "ok": True,
        "cluster_name": cluster.name,
        "resource_group": resource_group,
        "subscription_id": subscription_id,
        "arm_id": cluster.id,
        "location": cluster.location,
        "kubernetes_version": cluster.kubernetes_version,
        "node_count": len(nodes.items),
        "pool_count": len(pools),
        "metrics_server_available": metrics_ok,
    }


def connect_cluster(
    db: Session,
    *,
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
) -> dict[str, Any]:
    validation = validate_cluster_access(
        db,
        subscription_id=subscription_id,
        resource_group=resource_group,
        cluster_name=cluster_name,
    )
    row = (
        db.query(K8sClusterConnection)
        .filter(
            K8sClusterConnection.subscription_id == subscription_id,
            K8sClusterConnection.resource_group == resource_group,
            K8sClusterConnection.cluster_name == cluster_name,
        )
        .first()
    )
    now = _now()
    if row is None:
        row = K8sClusterConnection(
            id=str(uuid.uuid4()),
            subscription_id=subscription_id,
            resource_group=resource_group,
            cluster_name=cluster_name,
        )
        db.add(row)

    row.arm_id = validation.get("arm_id")
    row.location = validation.get("location")
    row.kubernetes_version = validation.get("kubernetes_version")
    row.last_validated_at = now
    row.last_error = None
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _cluster_row_dict(row)


def _agent_settings(db: Session) -> dict[str, Any]:
    return get_effective_config(db, "kubernetes")


def resolve_agent_api_url(db: Session, request_base_url: str | None = None) -> str:
    cfg = _agent_settings(db)
    explicit = (cfg.get("agent_api_url") or "").strip().rstrip("/")
    if explicit:
        return explicit
    if request_base_url:
        return request_base_url.rstrip("/")
    return ""


def _read_agent_files() -> tuple[str, str]:
    agent_py = (_AGENT_DIR / "agent.py").read_text(encoding="utf-8")
    requirements = (_AGENT_DIR / "requirements.txt").read_text(encoding="utf-8")
    return agent_py, requirements


def _ensure_namespace(core) -> None:
    k8s_client, _, ApiException = _k8s_modules()
    try:
        core.read_namespace(_AGENT_NAMESPACE)
    except ApiException as exc:
        if exc.status != 404:
            raise
        body = k8s_client.V1Namespace(
            metadata=k8s_client.V1ObjectMeta(
                name=_AGENT_NAMESPACE,
                labels={"app.kubernetes.io/name": "finops-utilization-agent"},
            )
        )
        core.create_namespace(body)


def _ensure_rbac(rbac) -> None:
    k8s_client, _, _ = _k8s_modules()
    role_name = "finops-utilization-agent"
    rules = [
        k8s_client.V1PolicyRule(
            api_groups=[""],
            resources=["nodes", "pods", "namespaces"],
            verbs=["get", "list"],
        ),
        k8s_client.V1PolicyRule(
            api_groups=["metrics.k8s.io"],
            resources=["nodes", "pods"],
            verbs=["get", "list"],
        ),
    ]
    role = k8s_client.V1ClusterRole(
        metadata=k8s_client.V1ObjectMeta(name=role_name),
        rules=rules,
    )
    try:
        rbac.read_cluster_role(role_name)
    except ApiException as exc:
        if exc.status != 404:
            raise
        rbac.create_cluster_role(role)

    binding = k8s_client.V1ClusterRoleBinding(
        metadata=k8s_client.V1ObjectMeta(name=role_name),
        role_ref=k8s_client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="ClusterRole",
            name=role_name,
        ),
        subjects=[
            k8s_client.V1Subject(
                kind="ServiceAccount",
                name="utilization-agent",
                namespace=_AGENT_NAMESPACE,
            )
        ],
    )
    try:
        rbac.read_cluster_role_binding(role_name)
    except ApiException as exc:
        if exc.status != 404:
            raise
        rbac.create_cluster_role_binding(binding)


def _upsert_secret(core, api_token: str) -> None:
    k8s_client, _, ApiException = _k8s_modules()
    body = k8s_client.V1Secret(
        metadata=k8s_client.V1ObjectMeta(
            name="utilization-agent-secret",
            namespace=_AGENT_NAMESPACE,
        ),
        type="Opaque",
        string_data={"API_TOKEN": api_token or ""},
    )
    try:
        core.replace_namespaced_secret("utilization-agent-secret", _AGENT_NAMESPACE, body)
    except ApiException as exc:
        if exc.status != 404:
            raise
        core.create_namespaced_secret(_AGENT_NAMESPACE, body)


def _upsert_configmaps(
    core,
    *,
    cluster_name: str,
    api_url: str,
    poll_interval: int,
    agent_image: str,
) -> None:
    k8s_client, _, ApiException = _k8s_modules()
    env_body = k8s_client.V1ConfigMap(
        metadata=k8s_client.V1ObjectMeta(
            name="utilization-agent-env",
            namespace=_AGENT_NAMESPACE,
        ),
        data={
            "API_URL": api_url,
            "BATCH_ENDPOINT": "/k8s/snapshot",
            "CLUSTER_NAME": cluster_name,
            "POLL_INTERVAL": str(poll_interval),
        },
    )
    try:
        core.replace_namespaced_config_map("utilization-agent-env", _AGENT_NAMESPACE, env_body)
    except ApiException as exc:
        if exc.status != 404:
            raise
        core.create_namespaced_config_map(_AGENT_NAMESPACE, env_body)

    if agent_image:
        return

    agent_py, requirements = _read_agent_files()
    code_body = k8s_client.V1ConfigMap(
        metadata=k8s_client.V1ObjectMeta(
            name="utilization-agent-code",
            namespace=_AGENT_NAMESPACE,
        ),
        data={"agent.py": agent_py, "requirements.txt": requirements},
    )
    try:
        core.replace_namespaced_config_map("utilization-agent-code", _AGENT_NAMESPACE, code_body)
    except ApiException as exc:
        if exc.status != 404:
            raise
        core.create_namespaced_config_map(_AGENT_NAMESPACE, code_body)


def _deployment_body(*, cluster_name: str, agent_image: str):
    k8s_client, _, _ = _k8s_modules()
    labels = {"app": "utilization-agent"}
    if agent_image:
        container = k8s_client.V1Container(
            name="agent",
            image=agent_image,
            image_pull_policy="IfNotPresent",
            env_from=[k8s_client.V1EnvFromSource(
                config_map_ref=k8s_client.V1ConfigMapEnvSource(name="utilization-agent-env"),
            )],
            env=[k8s_client.V1EnvVar(
                name="API_TOKEN",
                value_from=k8s_client.V1EnvVarSource(
                    secret_key_ref=k8s_client.V1SecretKeySelector(
                        name="utilization-agent-secret",
                        key="API_TOKEN",
                        optional=True,
                    ),
                ),
            )],
            resources=k8s_client.V1ResourceRequirements(
                requests={"cpu": "25m", "memory": "64Mi"},
                limits={"cpu": "100m", "memory": "128Mi"},
            ),
            liveness_probe=k8s_client.V1Probe(
                _exec=k8s_client.V1ExecAction(
                    command=["/bin/sh", "-c", "test -f /tmp/agent-heartbeat && find /tmp/agent-heartbeat -mmin -5 | grep -q ."],
                ),
                initial_delay_seconds=90,
                period_seconds=60,
            ),
            readiness_probe=k8s_client.V1Probe(
                _exec=k8s_client.V1ExecAction(command=["/bin/sh", "-c", "test -f /tmp/agent-heartbeat"]),
                initial_delay_seconds=30,
                period_seconds=30,
            ),
        )
        pod_spec = k8s_client.V1PodSpec(
            service_account_name="utilization-agent",
            security_context=k8s_client.V1PodSecurityContext(
                run_as_non_root=True,
                run_as_user=10001,
                fs_group=10001,
            ),
            containers=[container],
        )
    else:
        init = k8s_client.V1Container(
            name="install-deps",
            image="python:3.12-alpine",
            command=["sh", "-c", "pip install --no-cache-dir -r /config/requirements.txt -t /deps"],
            volume_mounts=[
                k8s_client.V1VolumeMount(name="agent-config", mount_path="/config"),
                k8s_client.V1VolumeMount(name="deps", mount_path="/deps"),
            ],
        )
        container = k8s_client.V1Container(
            name="agent",
            image="python:3.12-alpine",
            command=["sh", "-c", "PYTHONPATH=/deps python /config/agent.py"],
            env_from=[k8s_client.V1EnvFromSource(
                config_map_ref=k8s_client.V1ConfigMapEnvSource(name="utilization-agent-env"),
            )],
            env=[k8s_client.V1EnvVar(
                name="API_TOKEN",
                value_from=k8s_client.V1EnvVarSource(
                    secret_key_ref=k8s_client.V1SecretKeySelector(
                        name="utilization-agent-secret",
                        key="API_TOKEN",
                        optional=True,
                    ),
                ),
            )],
            volume_mounts=[
                k8s_client.V1VolumeMount(name="agent-config", mount_path="/config"),
                k8s_client.V1VolumeMount(name="deps", mount_path="/deps"),
            ],
            resources=k8s_client.V1ResourceRequirements(
                requests={"cpu": "25m", "memory": "128Mi"},
                limits={"cpu": "200m", "memory": "256Mi"},
            ),
        )
        pod_spec = k8s_client.V1PodSpec(
            service_account_name="utilization-agent",
            init_containers=[init],
            containers=[container],
            volumes=[
                k8s_client.V1Volume(
                    name="agent-config",
                    config_map=k8s_client.V1ConfigMapVolumeSource(name="utilization-agent-code"),
                ),
                k8s_client.V1Volume(name="deps", empty_dir=k8s_client.V1EmptyDirVolumeSource()),
            ],
        )

    return k8s_client.V1Deployment(
        metadata=k8s_client.V1ObjectMeta(
            name="utilization-agent",
            namespace=_AGENT_NAMESPACE,
            labels=labels,
        ),
        spec=k8s_client.V1DeploymentSpec(
            replicas=1,
            selector=k8s_client.V1LabelSelector(match_labels=labels),
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels=labels),
                spec=pod_spec,
            ),
        ),
    )


def deploy_utilization_agent(
    db: Session,
    cluster_id: str,
    *,
    request_base_url: str | None = None,
) -> dict[str, Any]:
    row = db.query(K8sClusterConnection).filter(K8sClusterConnection.id == cluster_id).first()
    if not row:
        raise ValueError("Cluster connection not found")

    api_url = resolve_agent_api_url(db, request_base_url)
    if not api_url:
        raise ValueError(
            "Agent API URL is not configured. Set K8S_AGENT_API_URL in Settings or "
            "kubernetes.agent_api_url before deploying."
        )

    cfg = _agent_settings(db)
    api_token = (cfg.get("agent_token") or "").strip()
    agent_image = (cfg.get("agent_image") or "").strip()
    poll_interval = int(cfg.get("poll_interval_seconds") or 60)

    row.agent_status = "deploying"
    row.last_error = None
    row.updated_at = _now()
    db.commit()

    try:
        kubeconfig = _kubeconfig_for_cluster(
            db, row.subscription_id, row.resource_group, row.cluster_name,
        )
        api = _api_client_from_kubeconfig(kubeconfig)
        k8s_client, _, ApiException = _k8s_modules()
        core = k8s_client.CoreV1Api(api)
        apps = k8s_client.AppsV1Api(api)
        rbac = k8s_client.RbacAuthorizationV1Api(api)

        _ensure_namespace(core)
        sa_body = k8s_client.V1ServiceAccount(
            metadata=k8s_client.V1ObjectMeta(
                name="utilization-agent",
                namespace=_AGENT_NAMESPACE,
            )
        )
        try:
            core.read_namespaced_service_account("utilization-agent", _AGENT_NAMESPACE)
        except ApiException as exc:
            if exc.status != 404:
                raise
            core.create_namespaced_service_account(_AGENT_NAMESPACE, sa_body)

        _ensure_rbac(rbac)
        _upsert_secret(core, api_token)
        _upsert_configmaps(
            core,
            cluster_name=row.cluster_name,
            api_url=api_url,
            poll_interval=poll_interval,
            agent_image=agent_image,
        )

        deployment = _deployment_body(cluster_name=row.cluster_name, agent_image=agent_image)
        try:
            apps.replace_namespaced_deployment("utilization-agent", _AGENT_NAMESPACE, deployment)
        except ApiException as exc:
            if exc.status != 404:
                raise
            apps.create_namespaced_deployment(_AGENT_NAMESPACE, deployment)

        api.close()

        now = _now()
        row.agent_deployed = True
        row.agent_status = "running"
        row.agent_deployed_at = now
        row.last_validated_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
        log.info(
            "k8s.agent_deployed",
            cluster=row.cluster_name,
            namespace=_AGENT_NAMESPACE,
            image=agent_image or "python:3.12-alpine",
        )
        return {
            "ok": True,
            "message": f"Utilization agent deployed to {row.cluster_name}.",
            "cluster": _cluster_row_dict(row),
            "namespace": _AGENT_NAMESPACE,
            "deployment": "utilization-agent",
        }
    except Exception as exc:
        row.agent_status = "error"
        row.last_error = str(exc)
        row.updated_at = _now()
        db.commit()
        log.warning("k8s.agent_deploy_failed", cluster=row.cluster_name, error=str(exc))
        raise


def get_cluster_connection(db: Session, cluster_id: str) -> dict[str, Any] | None:
    row = db.query(K8sClusterConnection).filter(K8sClusterConnection.id == cluster_id).first()
    return _cluster_row_dict(row) if row else None
