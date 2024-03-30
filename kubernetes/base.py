import logging

logger = logging.getLogger(__name__)

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
