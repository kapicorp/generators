import logging

logger = logging.getLogger(__name__)

from .common import KubernetesResource


class BackendConfig(KubernetesResource):
    kind: str = "BackendConfig"
    api_version: str = "cloud.google.com/v1"

    def body(self):
        super().body()
        self.root.spec = self.config.backend_config
