import logging

logger = logging.getLogger(__name__)

from pydantic.functional_validators import field_validator

from .common import (
    KubernetesBaseResource,
    KubernetesResource,
    KubernetesResourceSpec,
    kgenlib,
)


class MutatingWebhookConfiguration(KubernetesResource):
    kind: str = "MutatingWebhookConfiguration"
    api_version: str = "admissionregistration.k8s.io/v1"

    def new(self):
        super().new()

    def body(self):
        super().body()
        config = self.config
        self.root.webhooks = config.webhooks


class PriorityClass(KubernetesResource):
    kind: str = "PriorityClass"
    api_version: str = "scheduling.k8s.io/v1"
    priority: int

    def body(self):
        super().body()
        config = self.config
        self.root.value = self.priority
        self.root.globalDefault = False


class ResourceQuota(KubernetesResource):
    kind: str = "ResourceQuota"
    api_version: str = "v1"
    hard: dict[str, str] = {}
    soft: dict[str, str] = {}

    @field_validator("soft", "hard", mode="before")
    def transform_dict_value_to_str(cls, _dict: dict) -> str:
        for keys in _dict:
            _dict[keys] = str(_dict[keys])
        return _dict

    def body(self):
        super().body()
        self.root.spec.hard = self.hard
        self.root.spec.soft = self.soft


class NameSpaceConfigSpec(KubernetesResourceSpec):
    enable_istio_sidecar_injection: bool = False


class Namespace(KubernetesBaseResource):
    kind: str = "Namespace"
    api_version: str = "v1"
    config: NameSpaceConfigSpec

    def body(self):
        super().body()
        if self.config.enable_istio_sidecar_injection:
            self.add_label("istio-injection", "enabled")


@kgenlib.register_generator(path="generators.kubernetes.namespace")
class NamespaceGenerator(kgenlib.BaseStore):
    def body(self):
        name = self.config.get("name", self.name)
        self.add(Namespace(name=name, config=self.config))


@kgenlib.register_generator(path="generators.kubernetes.priority_class")
class PriorityClassGenerator(kgenlib.BaseStore):
    def body(self):
        name = self.config.get("name", self.name)
        self.add(
            PriorityClass(
                name=name, priority=self.config.get("priority"), config=self.config
            )
        )


@kgenlib.register_generator(path="generators.kubernetes.resource_quotas")
class ResourceQuotaGenerator(kgenlib.BaseStore):
    def body(self):
        name = self.config.get("name", self.name)
        namespace = self.config.get("namespace", self.inventory.parameters.namespace)
        self.add(
            rq := ResourceQuota(
                name=name,
                namespace=namespace,
                hard=self.config.get("hard", {}),
                soft=self.config.get("soft", {}),
                config=self.config,
            )
        )
