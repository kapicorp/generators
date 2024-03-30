import logging

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional

from pydantic import Field

from .common import (
    KubernetesResource,
    KubernetesResourceSpec,
    RoleBindingConfig,
    WorkloadConfigSpec,
    ServiceAccountComponentConfigSpec,
    kgenlib,
)


class Role(KubernetesResource):
    kind: str = "Role"
    api_version: str = "rbac.authorization.k8s.io/v1"

    def body(self):
        super().body()
        config = self.config
        self.root.rules = config.role["rules"]


class RoleBinding(KubernetesResource):
    kind: str = "RoleBinding"
    api_version: str = "rbac.authorization.k8s.io/v1"
    config: RoleBindingConfig

    def body(self):
        super().body()
        config = self.config
        sa = self.sa
        name = config.name or self.name
        default_role_ref = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": name,
        }
        default_subject = [
            {
                "kind": "ServiceAccount",
                "name": sa.name,
                "namespace": sa.namespace,
            }
        ]
        self.root.roleRef = config.roleRef or default_role_ref
        self.root.subjects = config.subject or default_subject


class ClusterRole(KubernetesResource):
    kind: str = "ClusterRole"
    api_version: str = "rbac.authorization.k8s.io/v1"

    def new(self):
        super().new()

    def body(self):
        super().body()
        config = self.config
        self.root.rules = config.cluster_role.rules


class ClusterRoleBinding(KubernetesResource):
    kind: str = "ClusterRoleBinding"
    api_version: str = "rbac.authorization.k8s.io/v1"

    def body(self):
        super().body()
        config = self.config
        sa = self.sa
        default_role_ref = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": config.name,
        }
        default_subject = [
            {
                "kind": "ServiceAccount",
                "name": sa.name,
                "namespace": sa.namespace,
            }
        ]
        self.root.roleRef = config.get("roleRef", default_role_ref)
        self.root.subjects = config.get("subject", default_subject)


class ServiceAccountConfigSpec(KubernetesResourceSpec):
    annotations: dict = {}
    labels: dict = {}
    namespace: Optional[str] = None
    rendered_name: Optional[str] = None
    name: Optional[str] = None
    roles: Optional[List[Dict[str, Any]]] = None


@kgenlib.register_generator(path="generators.kubernetes.service_accounts")
class ServiceAccountGenerator(kgenlib.BaseStore):
    name: str
    config: ServiceAccountConfigSpec

    def body(self):
        config = self.config
        name = config.name or self.name
        sa = ServiceAccount(name=name, config=config)
        namespace = config.namespace

        roles = config.roles
        objs = [sa]
        if roles is not None:
            role_cfg = {"role": {"rules": roles}}
            r = Role(name=f"{name}-role", namespace=namespace, config=role_cfg)
            rb_cfg = {"name": r.name}
            rb = RoleBinding(
                name=f"{name}-role-binding", namespace=namespace, config=rb_cfg, sa=sa
            )

            objs += [r, rb]

        self.add_list(objs)


class ServiceAccount(KubernetesResource):
    kind: str = "ServiceAccount"
    api_version: str = "v1"
    config: Optional[ServiceAccountConfigSpec | WorkloadConfigSpec] = None
    spec: Optional[ServiceAccountComponentConfigSpec] = None

    def body(self):
        super().body()
        config = self.config

        try:
            self.add_annotations(config.annotations)
        except:
            logging.info(f"ServiceAccount body {config}")
            raise
