import logging

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional

from pydantic import Field

from .common import (
    KubernetesResource,
    KubernetesResourceSpec,
    RoleBindingConfigSpec,
    ServiceAccountComponentConfigSpec,
    ServiceAccountConfigSpec,
    WorkloadConfigSpec,
    kgenlib,
)


class ServiceAccount(KubernetesResource):
    kind: str = "ServiceAccount"
    api_version: str = "v1"
    config: Optional[ServiceAccountConfigSpec | WorkloadConfigSpec] = None
    spec: Optional[ServiceAccountComponentConfigSpec] = None

    def body(self):
        super().body()
        if self.spec:
            self.add_annotations(self.spec.annotations)


class RoleConfigSpec(KubernetesResourceSpec):
    rules: List[Dict[str, Any]] = []


class Role(KubernetesResource):
    kind: str = "Role"
    api_version: str = "rbac.authorization.k8s.io/v1"
    spec: Optional[RoleConfigSpec] = None

    def body(self):
        super().body()
        if self.spec:
            self.root.rules = self.spec.rules


class RoleBinding(KubernetesResource):
    kind: str = "RoleBinding"
    api_version: str = "rbac.authorization.k8s.io/v1"
    role: Role
    sa: ServiceAccount
    spec: Optional[RoleBindingConfigSpec] = RoleBindingConfigSpec()

    def body(self):
        super().body()
        default_role_ref = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": self.role.name,
        }
        default_subject = [
            {
                "kind": "ServiceAccount",
                "name": self.sa.name,
                "namespace": self.sa.namespace,
            }
        ]
        self.root.roleRef = self.spec.roleRef or default_role_ref
        self.root.subjects = self.spec.subject or default_subject


class ClusterRoleBindingConfigSpec(KubernetesResourceSpec):
    roleRef: Optional[Dict[str, Any]] = None
    subject: Optional[List[Dict[str, Any]]] = None


class ClusterRoleConfigSpec(KubernetesResourceSpec):
    rules: List[Dict[str, Any]] = []
    binding: Optional[ClusterRoleBindingConfigSpec]


class ClusterRole(KubernetesResource):
    kind: str = "ClusterRole"
    api_version: str = "rbac.authorization.k8s.io/v1"
    spec: ClusterRoleConfigSpec

    def body(self):
        super().body()
        self.root.rules = self.spec.rules


class ClusterRoleBinding(KubernetesResource):
    kind: str = "ClusterRoleBinding"
    api_version: str = "rbac.authorization.k8s.io/v1"
    sa: ServiceAccount
    role: ClusterRole
    spec: ClusterRoleConfigSpec

    def body(self):
        super().body()
        default_role_ref = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": self.role.name,
        }
        default_subject = [
            {
                "kind": "ServiceAccount",
                "name": self.sa.name,
                "namespace": self.sa.namespace,
            }
        ]
        self.root.roleRef = self.spec.binding.roleRef or default_role_ref
        self.root.subjects = self.spec.binding.subject or default_subject


@kgenlib.register_generator(path="generators.kubernetes.service_accounts")
class ServiceAccountGenerator(kgenlib.BaseStore):
    name: str
    config: ServiceAccountConfigSpec

    def body(self):
        config = self.config
        name = config.name or self.name
        sa = ServiceAccount(name=name, config=config)
        namespace = config.namespace

        self.add(sa)
        rules = config.roles

        if rules:
            spec = {"rules": rules}
            r = Role(name=f"{name}-role", namespace=namespace, spec=spec)
            self.add(r)

            rb = RoleBinding(
                name=f"{name}-role-binding",
                namespace=namespace,
                role=r,
                sa=sa,
                spec=spec,
            )
            self.add(rb)
