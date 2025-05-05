import logging

logger = logging.getLogger(__name__)

from .common import KubernetesResource, kgenlib
from typing import Any


class BackendConfig(KubernetesResource):
    kind: str = "BackendConfig"
    api_version: str = "cloud.google.com/v1"

    def body(self):
        super().body()
        spec = self.spec
        self.root.spec = spec


@kgenlib.register_generator(path="generators.kubernetes.backend_config")
class BackendConfigGenerator(kgenlib.BaseStore):
    name: str
    config: Any

    def body(self):
        name = self.name
        config = self.config
        spec = self.config.spec
        backend_config = BackendConfig(name=name, config=config, spec=spec)
        self.add(backend_config)


class FrontendConfig(KubernetesResource):
    kind: str = "FrontendConfig"
    api_version: str = "networking.gke.io/v1beta1"

    def body(self):
        super().body()
        spec = self.spec
        self.root.spec = spec


@kgenlib.register_generator(path="generators.kubernetes.frontend_config")
class FrontendConfigGenerator(kgenlib.BaseStore):
    name: str
    config: Any

    def body(self):
        name = self.name
        config = self.config
        spec = self.config.spec
        frontend_config = FrontendConfig(name=name, config=config, spec=spec)
        self.add(frontend_config)