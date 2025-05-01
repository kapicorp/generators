import logging

logger = logging.getLogger(__name__)

from .common import KubernetesResource, kgenlib


@kgenlib.register_generator(path="certmanager.issuer")
class CertManagerIssuer(KubernetesResource):
    kind: str = "Issuer"
    api_version: str = "cert-manager.io/v1"

    def body(self):
        config = self.config
        super().body()
        self.root.spec = config.spec


@kgenlib.register_generator(path="certmanager.cluster_issuer")
class CertManagerClusterIssuer(KubernetesResource):
    kind: str = "ClusterIssuer"
    api_version: str = "cert-manager.io/v1"

    def body(self):
        config = self.config
        super().body()
        self.root.spec = config.spec


@kgenlib.register_generator(path="certmanager.certificate")
class CertManagerCertificate(KubernetesResource):
    kind: str = "Certificate"
    api_version: str = "cert-manager.io/v1"

    def body(self):
        config = self.config
        super().body()
        self.root.spec = config.spec
