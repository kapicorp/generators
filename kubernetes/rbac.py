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
        if self.config:
            config = self.config
            if isinstance(config, WorkloadConfigSpec):
                self.name = config.service_account.name or self.name
            else:
                self.name = config.name or self.name
        super().body()
        # Force the name again after super().body()
        # This is needed for when we are setting service_account.name.
        # Wihthout this, only labels.name is set correctly
        self.root.metadata.name = self.name
        if self.spec:
            self.add_annotations(self.spec.annotations)


class RoleConfigSpec(KubernetesResourceSpec):
    rules: list[dict[str, list[str]]] | dict[str, list[str] | dict[str, list[str]]] = []


class Role(KubernetesResource):
    kind: str = "Role"
    api_version: str = "rbac.authorization.k8s.io/v1"
    spec: Optional[RoleConfigSpec] = None

    def body(self):
        super().body()
        if self.spec:
            rules = self.spec.rules
            resolved_rules = []
            if isinstance(rules, list):
                resolved_rules = rules
            elif isinstance(rules, dict):
                for rule_names, rule_config in rules.items():
                    api_groups = set()
                    resources = set()
                    for rule_name in rule_names.split(","):
                        rule_name = rule_name.strip()

                        # by default if apiGroups and resources are not defined
                        # they're going to be inferred from the rule name
                        if "/" in rule_name:
                            api_group, *resource_bits = rule_name.split("/")
                            resource = "/".join(resource_bits)
                        else:
                            api_group = ""
                            resource = rule_name
                        api_groups.add(api_group)
                        resources.add(resource)

                    # if rule has form {name: [...]}
                    # then the list is treated as role verbs
                    if isinstance(rule_config, list):
                        rule_config = {"verbs": rule_config}
                    resolved_rules.append(
                        {
                            **{
                                "apiGroups": sorted(api_groups),
                                "resources": sorted(resources),
                            },
                            **rule_config,
                        }
                    )
            else:
                raise TypeError(
                    f"rules are wrong type. expected list or dict, found: {type(rules)}"
                )
            self.root.rules = resolved_rules


class RoleBinding(KubernetesResource):
    kind: str = "RoleBinding"
    api_version: str = "rbac.authorization.k8s.io/v1"
    role: Optional[Role] = None
    sa: Optional[ServiceAccount] = None
    spec: Optional[RoleBindingConfigSpec] = RoleBindingConfigSpec()

    def body(self):
        super().body()
        if self.role and self.sa:
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
            self.root.roleRef = default_role_ref
            self.root.subjects = default_subject
        elif self.spec:
            self.root.roleRef = self.spec.roleRef
            self.root.subjects = self.spec.subjects


class ClusterRoleBindingConfigSpec(KubernetesResourceSpec):
    roleRef: Optional[Dict[str, Any]] = None
    subject: Optional[List[Dict[str, Any]]] = None


class ClusterRoleConfigSpec(KubernetesResourceSpec):
    rules: List[Dict[str, Any]] = []
    binding: Optional[ClusterRoleBindingConfigSpec] = None


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
    sa: Optional[ServiceAccount] = None
    role: Optional[ClusterRole] = None
    spec: Optional[ClusterRoleBindingConfigSpec] = ClusterRoleBindingConfigSpec()

    def body(self):
        super().body()
        if self.role and self.sa:
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
            self.root.roleRef = default_role_ref
            self.root.subjects = default_subject
        elif self.spec:
            self.root.roleRef = self.spec.roleRef
            self.root.subjects = self.spec.subjects


@kgenlib.register_generator(path="generators.kubernetes.cluster_rolebinding")
class ClusterRoleBindingGenerator(kgenlib.BaseStore):
    name: str

    def body(self):
        config = self.config
        name = config.name or self.name
        subjects = config.get("subjects") or []
        processed_subjects = [
            self._ensure_subject_format(subject) for subject in subjects
        ]
        config.subjects = processed_subjects

        cluster_rolebinding = ClusterRoleBinding(name=name, spec=config)
        self.add(cluster_rolebinding)

    @staticmethod
    def _ensure_subject_format(subject: Any) -> dict[str, str]:
        # @TODO merge with RoleBindingGenerator logic
        if isinstance(subject, dict):
            return subject

        if not isinstance(subject, str):
            raise TypeError(f"subject has to be str or dict, not {type(subject)!r}")

        try:
            prefix, identity = subject.split(":")
        except ValueError:
            raise ValueError(f"could not parse {subject!r} into prefix:suffix")

        match prefix:
            case "user":
                kind = "User"
            case "group":
                kind = "Group"
            case "serviceAccount":
                kind = "User"
            case _:
                raise ValueError(f"unrecognized identity prefix: {prefix!r}")

        return {"kind": kind, "name": identity}


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


@kgenlib.register_generator(path="generators.kubernetes.role")
class RoleGenerator(kgenlib.BaseStore):
    name: str

    def body(self):
        config = self.config
        name = config.name or self.name
        namespace = config.namespace
        spec = {"rules": config.rules}
        role = Role(name=name, namespace=namespace, spec=spec)
        self.add(role)


@kgenlib.register_generator(path="generators.kubernetes.cluster_role")
class ClusterRoleGenerator(kgenlib.BaseStore):
    name: str

    def body(self):
        config = self.config
        name = config.name or self.name
        spec = ClusterRoleConfigSpec(rules=config.rules)
        role = ClusterRole(name=name, spec=spec)
        self.add(role)


@kgenlib.register_generator(path="generators.kubernetes.rolebinding")
class RoleBindingGenerator(kgenlib.BaseStore):
    name: str

    def body(self):
        config = self.config
        name = config.name or self.name
        namespace = config.namespace

        subjects = config.get("subjects") or []
        processed_subjects = [
            self._ensure_subject_format(subject) for subject in subjects
        ]
        config.subjects = processed_subjects

        role_binding = RoleBinding(name=name, namespace=namespace, spec=config)
        self.add(role_binding)

    @staticmethod
    def _ensure_subject_format(subject: Any) -> dict[str, str]:
        if isinstance(subject, dict):
            return subject

        if not isinstance(subject, str):
            raise TypeError(f"subject has to be str or dict, not {type(subject)!r}")

        # user:bamax@google.com
        # group:eng-team@google.com
        try:
            prefix, identity = subject.split(":")
        except ValueError:
            raise ValueError(f"could not parse {subject!r} into prefix:suffix")

        match prefix:
            case "user":
                kind = "User"
            case "group":
                kind = "Group"
            case "serviceAccount":
                kind = "User"
            case _:
                raise ValueError(f"unrecognized identity prefix: {prefix!r}")

        return {"kind": kind, "name": identity}
