import logging

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional

from .common import KubernetesResource, KubernetesResourceSpec, kgenlib


@kgenlib.register_generator(
    path="generators.prometheus.gen_pod_monitoring",
    apply_patches=["generators.prometheus.defaults.gen_pod_monitoring"],
)
class PodMonitoring(KubernetesResource):
    kind: str = "PodMonitoring"
    api_version: str = "monitoring.googleapis.com/v1"

    def body(self):
        super().body()
        self.root.spec = self.config.spec


class PrometheusRule(KubernetesResource):
    kind: str = "PrometheusRule"
    api_version: str = "monitoring.coreos.com/v1"

    def body(self):
        super().body()
        name = self.name
        config = self.config
        self.root.spec.setdefault("groups", []).append(
            {"name": name, "rules": config.prometheus_rules.rules}
        )


class ServiceMonitor(KubernetesResource):
    kind: str = "ServiceMonitor"
    api_version: str = "monitoring.coreos.com/v1"

    def new(self):
        super().new()

    def body(self):
        # TODO(ademaria) This name mangling is here just to simplify diff.
        # Change it once done
        name = self.name
        workload = self.workload
        self.name = "{}-metrics".format(name)

        super().body()
        name = self.name
        config = self.config
        self.root.spec.endpoints = config.service_monitors.endpoints
        self.root.spec.jobLabel = name
        self.root.spec.namespaceSelector.matchNames = [self.namespace]
        self.root.spec.selector.matchLabels = (
            workload.root.spec.template.metadata.labels
        )
