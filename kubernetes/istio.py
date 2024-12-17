import logging

logger = logging.getLogger(__name__)

from .common import KubernetesResource, kgenlib


class IstioPolicy(KubernetesResource):
    kind: str = "IstioPolicy"
    api_version: str = "authentication.istio.io/v1alpha1"

    def body(self):
        super().body()
        config = self.config
        name = self.name
        self.root.spec.origins = config.istio_policy.policies.origins
        self.root.spec.principalBinding = "USE_ORIGIN"
        self.root.spec.targets = [{"name": name}]


@kgenlib.register_generator(path="generators.istio.gateway")
class IstioGatewayGenerator(kgenlib.BaseStore):
    def body(self):
        self.add(IstioGateway(name=self.id, config=self.config))


class IstioGateway(KubernetesResource):
    kind: str = "Gateway"
    api_version: str = "networking.istio.io/v1"

    def body(self):
        super().body()
        self.root.spec = self.config.spec
