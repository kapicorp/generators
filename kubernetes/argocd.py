import json
import logging

logger = logging.getLogger(__name__)
from kapitan.inputs.kadet import Dict

from .base import Namespace
from .common import KubernetesResource, KubernetesResourceSpec, kgenlib


class ArgoCDApplicationConfigSpec(KubernetesResourceSpec):
    project: str = "default"
    destination: dict = None
    source: dict
    sync_policy: dict = None
    ignore_differences: list[dict] = None


class ArgoCDApplication(KubernetesResource):
    source: dict = None
    kind: str = "Application"
    api_version: str = "argoproj.io/v1alpha1"
    cluster: Dict = {}
    config: ArgoCDApplicationConfigSpec

    def body(self):
        self.root.spec.project = self.config.project
        destination = self.config.destination
        self.root.spec.destination.name = self.cluster.display_name or destination.get("name")
        self.root.spec.destination.namespace = destination.get("namespace")
        self.root.spec.source = self.config.source
        self.root.spec.syncPolicy = self.config.sync_policy

        self.root.spec.ignoreDifferences = self.config.ignore_differences

        self.namespace = (
            self.config.namespace or f"argocd-project-{self.config.project}"
        )

        super().body()


@kgenlib.register_generator(
    path="generators.argocd.applications",
    global_generator=True,
    activation_path="argocd.app_of_apps",
)
class GenArgoCDApplication(kgenlib.BaseStore):
    def body(self):
        config = self.config
        namespace = config.get("namespace", "argocd")
        name = config.get("name", self.name)
        enabled = config.get("enabled", True)
        clusters = self.inventory.parameters.get("clusters", {})
        single_cluster = config.get("single_cluster", False)
        if single_cluster:
            cluster = self.inventory.parameters.get("cluster", {})
            cluster_id = cluster.get("user", None)
            clusters = {cluster_id: cluster}

        if enabled:
            for cluster in clusters.keys():
                cluster_config = clusters[cluster]
                cluster_name = cluster_config.get("name")

                id = f"{name}-{cluster_name}"
                if len(clusters.keys()) == 1:
                    id = name

                argo_application = ArgoCDApplication(
                    name=id,
                    namespace=namespace,
                    config=config,
                    cluster=cluster_config,
                )
                self.add(argo_application)


class ArgoCDProjectConfigSpec(KubernetesResourceSpec):
    source_repos: list = []
    destinations: list = []
    cluster_resource_whitelist: list = []
    source_namespaces: list = None


class ArgoCDProject(KubernetesResource):
    kind: str = "AppProject"
    api_version: str = "argoproj.io/v1alpha1"
    config: ArgoCDProjectConfigSpec

    def body(self):
        super().body()
        self.root.spec.sourceRepos = self.config.source_repos
        self.root.spec.destinations = self.config.destinations
        self.root.spec.clusterResourceWhitelist = self.config.cluster_resource_whitelist
        self.root.spec.sourceNamespaces = self.config.source_namespaces or [
            f"argocd-project-{self.name}"
        ]


@kgenlib.register_generator(
    path="generators.argocd.projects",
    global_generator=True,
    activation_path="argocd.app_of_apps",
)
class GenArgoCDProject(kgenlib.BaseStore):
    def body(self):
        config = self.config
        namespace = config.get("namespace", "argocd")
        name = config.get("name", self.name)

        self.add(ArgoCDProject(name=name, namespace=namespace, config=config))
        self.add(Namespace(name=f"argocd-project-{name}", config=config))


@kgenlib.register_generator(
    path="clusters",
    global_generator=True,
    activation_path="argocd.clusters",
)
class GenArgoCDCluster(kgenlib.BaseStore):
    def body(self):
        config = self.config
        target = self.target
        namespace = self.global_inventory[target]["parameters"]["namespace"]
        name = config.get("name")
        cluster = ArgoCDCluster(name=name, namespace=namespace, config=config)

        self.add(cluster)


class ArgoCDClusterConfigSpec(KubernetesResourceSpec):
    display_name: str = None
    endpoint_url: str
    certificate: str


class ArgoCDCluster(KubernetesResource):
    kind: str = "Secret"
    api_version: str = "v1"
    config: ArgoCDClusterConfigSpec

    def body(self):
        super().body()
        self.add_label("argocd.argoproj.io/secret-type", "cluster")
        self.root.stringData.name = self.config.display_name or self.name
        self.root.stringData.server = self.config.endpoint_url
        self.root.stringData.config = json.dumps(
            {
                "execProviderConfig": {
                    "command": "argocd-k8s-auth",
                    "args": ["gcp"],
                    "apiVersion": "client.authentication.k8s.io/v1beta1",
                },
                "tlsClientConfig": {
                    "insecure": False,
                    "caData": self.config.certificate,
                },
            },
            indent=4,
        )
