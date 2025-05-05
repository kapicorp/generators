import logging

logger = logging.getLogger(__name__)

from enum import StrEnum
from typing import Any, Dict, List, Optional

from .common import (
    KubernetesResource,
    KubernetesResourceSpec,
    NetworkPolicySpec,
    ServiceConfigSpec,
    kgenlib,
)


class IngressConfigSpec(KubernetesResourceSpec):
    host: Optional[str] = None
    paths: List[Dict[str, Any]] = []
    rules: List[Dict[str, Any]] = []
    tls: Optional[List[Dict[str, Any]]] = None
    default_backend: Optional[Dict[str, Any]] = None


class Ingress(KubernetesResource):
    kind: str = "Ingress"
    api_version: str = "networking.k8s.io/v1"
    config: IngressConfigSpec

    def body(self):
        super().body()
        config = self.config

        if config.default_backend:
            self.root.spec.defaultBackend.service.name = config.default_backend.get("name")
            self.root.spec.defaultBackend.service.port = config.default_backend.get("port", 80)
        if config.paths:
            host = config.host
            paths = config.paths
            self.root.spec.setdefault("rules", []).extend(
                [{"host": host, "http": {"paths": paths}}]
            )
        self.root.spec.setdefault("rules", []).extend(config.rules)
        if config.tls:
            self.root.spec.tls = config.tls


class GoogleManagedCertificate(KubernetesResource):
    kind: str = "ManagedCertificate"
    api_version: str = "networking.gke.io/v1"

    def body(self):
        super().body()
        config = self.config
        self.root.spec.domains = config.domains


class NetworkPolicy(KubernetesResource):
    kind: str = "NetworkPolicy"
    api_version: str = "networking.k8s.io/v1"
    config: NetworkPolicySpec

    def body(self):
        super().body()
        policy = self.config
        workload = self.workload
        self.root.spec.podSelector.matchLabels = workload.root.metadata.labels
        self.root.spec.ingress = policy.ingress
        self.root.spec.egress = policy.egress
        if self.root.spec.ingress:
            self.root.spec.setdefault("policyTypes", []).append("Ingress")

        if self.root.spec.egress:
            self.root.spec.setdefault("policyTypes", []).append("Egress")


class HealthCheckPolicy(KubernetesResource):
    kind: str = "HealthCheckPolicy"
    api_version: str = "networking.gke.io/v1"

    def body(self):
        # Defaults from https://cloud.google.com/kubernetes-engine/docs/how-to/configure-gateway-resources#configure_health_check
        super().body()
        config = self.config

        self.root.spec.default.logConfig.enabled = config.healthcheck.get("log", False)

        default_spec = self.root.spec.default

        default_spec.checkIntervalSec = config.healthcheck.get("check_interval_sec", 5)
        default_spec.timeoutSec = config.healthcheck.get(
            "timeout_sec", default_spec.checkIntervalSec
        )
        default_spec.healthyThreshold = config.healthcheck.get("healthy_threshold", 2)
        default_spec.unhealthyThreshold = config.healthcheck.get(
            "unhealthy_threshold", 2
        )

        config_spec = default_spec.config
        container_port = config.healthcheck.get("container_port", self.name)

        config_spec.type = config.healthcheck.get("type", "HTTP").upper()
        if config_spec.type == "HTTP":
            config_spec.httpHealthCheck.portSpecification = "USE_FIXED_PORT"
            config_spec.httpHealthCheck.port = container_port
            config_spec.httpHealthCheck.requestPath = config.healthcheck.get(
                "path", config.path or "/"
            )

        self.root.spec.targetRef = {
            "group": "",
            "kind": "Service",
            "name": config.service,
        }


class GatewaySupportedTypes(StrEnum):
    GKE_L7_GLOBAL_EXTERNAL_MANAGED = "gke-l7-global-external-managed"
    GKE_L7_GLOBAL_EXTERNAL_MANAGED_MC = "gke-l7-global-external-managed-mc"
    GKE_L7_REGIONAL_EXTERNAL_MANAGED = "gke-l7-regional-external-managed"
    GKE_L7_REGIONAL_EXTERNAL_MANAGED_MC = "gke-l7-regional-external-managed-mc"
    GKE_L7_RILB = "gke-l7-rilb"
    GKE_L7_RILB_MC = "gke-l7-rilb-mc"
    GKE_L7_GXLB = "gke-l7-gxlb"
    GKE_L7_GXLB_MC = "gke-l7-gxlb-mc"


class FromNamespace(StrEnum):
    SAME = "Same"
    ALL = "All"


class GatewayConfigSpec(KubernetesResourceSpec):
    type: GatewaySupportedTypes
    listeners: Optional[List[Dict[str, Any]]] = None
    allowed_from_namespace: Optional[FromNamespace] = FromNamespace.SAME
    certificate: Optional[str] = None
    named_addresses: Optional[List[str]]


class Gateway(KubernetesResource):
    kind: str = "Gateway"
    api_version: str = "gateway.networking.k8s.io/v1beta1"
    config: GatewayConfigSpec

    def body(self):
        super().body()
        self.root.spec.gatewayClassName = self.config.type
        default_listener = {"name": "http", "protocol": "HTTP", "port": 80}

        certificate = self.config.certificate
        if certificate:
            default_listener = {
                "name": "https",
                "protocol": "HTTPS",
                "port": 443,
                "tls": {
                    "mode": "Terminate",
                    "certificateRefs": [{"name": certificate}],
                },
            }

        listeners = self.config.listeners or [default_listener]
        allowed_routes = self.config.allowed_from_namespace or FromNamespace.SAME

        spec = {"allowedRoutes": {"namespaces": {"from": allowed_routes}}}
        for listener in listeners:
            listener.update(spec)
        self.root.spec.listeners = listeners

        for addresses in self.config.named_addresses or []:
            self.root.spec.setdefault("addresses", []).append(
                {"type": "NamedAddress", "value": addresses}
            )


class GCPGatewayConfigSpec(KubernetesResourceSpec):
    allow_global_access: bool = False
    gateway_name: Optional[str]


class GCPGatewayPolicy(KubernetesResource):
    kind: str = "GCPGatewayPolicy"
    api_version: str = "networking.gke.io/v1"
    config: GCPGatewayConfigSpec

    def body(self):
        super().body()
        gateway_name = self.config.gateway_name
        self.root.spec.default.allowGlobalAccess = self.config.allow_global_access
        self.root.spec.targetRef = {
            "group": "gateway.networking.k8s.io",
            "kind": "Gateway",
            "name": gateway_name,
        }


class GCPBackendConfigSpec(KubernetesResourceSpec):
    timeout_sec: Optional[int] = 30
    logging: Optional[Dict[str, Any]] = None
    iap: Optional[Dict[str, Any]] = None


class GCPBackendPolicy(KubernetesResource):
    kind: str = "GCPBackendPolicy"
    api_version: str = "networking.gke.io/v1"
    config: GCPBackendConfigSpec

    def body(self):
        super().body()

        self.root.spec.default.timeoutSec = self.config.timeout_sec or 30
        self.root.spec.default.logging = self.config.logging or {"enabled": False}
        self.root.spec.default.iap = self.config.iap

        self.root.spec.targetRef = {
            "group": "",
            "kind": "Service",
            "name": self.config.service,
        }


class HTTPRouteSpec(KubernetesResourceSpec):
    gateway_name: Optional[str]
    gateway_namespace: Optional[str | None]
    hostnames: Optional[List[str]]
    rules: List[Dict[str, Any]] = []
    services: Optional[Dict[str, Dict[str, Any]]] = {}


class HTTPRoute(KubernetesResource):
    kind: str = "HTTPRoute"
    api_version: str = "gateway.networking.k8s.io/v1beta1"
    config: HTTPRouteSpec

    def body(self):
        super().body()

        gateway_name = self.config.gateway_name
        gateway_namespace = self.config.gateway_namespace
        self.root.spec.setdefault("parentRefs", []).append(
            {
                "kind": "Gateway",
                "name": gateway_name,
                "namespace": gateway_namespace if gateway_namespace else None,
            }
        )

        self.root.spec.hostnames = self.config.hostnames or []

        rules = self.config.rules or []
        self.root.spec.setdefault("rules", []).extend(rules)

        services = self.config.services or {}
        for service_name, service_config in services.items():
            match = {"path": {"value": service_config.get("path", "/")}}
            rule = {
                "backendRefs": [
                    {
                        "name": service_config.get("service", service_name),
                        "port": service_config.get("port", 80),
                    }
                ],
                "matches": [match],
            }
            filters = service_config.get("filters", [])
            if filters:
                rule["filters"] = filters
            self.root.spec.setdefault("rules", []).append(rule)


@kgenlib.register_generator(path="generators.kubernetes.routes")
class RouteGenerator(kgenlib.BaseStore):
    config: HTTPRouteSpec

    def body(self):
        config = self.config
        name = self.name

        route = HTTPRoute(name=name, config=config)
        self.add(route)


@kgenlib.register_generator(path="generators.kubernetes.gateway")
class GatewayGenerator(kgenlib.BaseStore):
    def body(self):
        gateway = Gateway(name=self.name, config=self.config)
        self.add(gateway)

        policy = GCPGatewayPolicy(
            name=self.name,
            config=dict(
                self.config,
                gateway_name=gateway.name,
                gateway_namespace=gateway.namespace,
            ),
        )
        self.add(policy)

        for route_id, route_config in self.config.get("routes", {}).items():
            route_name = f"{self.name}-{route_id}"
            route = HTTPRoute(
                name=route_name,
                config=dict(
                    route_config,
                    gateway_name=gateway.name,
                    gateway_namespace=gateway.namespace,
                    namespace=route_config.get("namespace") or gateway.namespace,
                ),
            )
            self.add(route)

            for service_id, service_config in route_config.get("services", {}).items():
                healthcheck = HealthCheckPolicy(
                    name=f"{service_id}",
                    config=dict(
                        service_config,
                        namespace=service_config.get("namespace") or gateway.namespace,
                    ),
                )
                self.add(healthcheck)

                backend_policy = GCPBackendPolicy(
                    name=f"{service_id}",
                    config=GCPBackendConfigSpec(
                        **dict(
                            service_config,
                            namespace=route_config.get("namespace")
                            or gateway.namespace,
                        )
                    ),
                )

                self.add(backend_policy)


class Service(KubernetesResource):
    kind: str = "Service"
    api_version: str = "v1"
    workload: KubernetesResource
    spec: ServiceConfigSpec

    def body(self):
        super().body()
        config = self.config
        workload = self.workload.root
        spec = self.spec

        self.name = spec.service_name or self.name

        self.add_labels(config.labels)
        self.add_annotations(spec.annotations)
        self.root.spec.setdefault("selector", {}).update(
            workload.spec.template.metadata.labels
        )
        self.root.spec.setdefault("selector", {}).update(spec.selectors)
        self.root.spec.type = spec.type
        self.root.spec.publishNotReadyAddresses = spec.publish_not_ready_address
        if spec.headless:
            self.root.spec.clusterIP = "None"
        self.root.spec.sessionAffinity = spec.session_affinity
        additional_containers = [
            _config
            for _config in config.additional_containers.values()
            if _config is not None
        ]
        all_ports = [config.ports] + [
            container.ports for container in additional_containers
        ]

        self.exposed_ports = {}

        for port in all_ports:
            for port_name in port.keys():
                if not spec.expose_ports or port_name in spec.expose_ports:
                    self.exposed_ports.update(port)

        for port_name in sorted(self.exposed_ports):
            self.root.spec.setdefault("ports", [])
            port_spec = self.exposed_ports[port_name]
            service_port = port_spec.service_port
            if service_port:
                self.root.spec.setdefault("ports", []).append(
                    {
                        "name": port_name,
                        "port": service_port,
                        "targetPort": port_name,
                        "protocol": port_spec.protocol,
                    }
                )


@kgenlib.register_generator(path="ingresses")
class IngressComponent(kgenlib.BaseStore):
    name: str
    config: Any

    def body(self):
        name = self.name
        config = self.config
        ingress = Ingress(name=name, config=config)
        self.add(ingress)

        if "managed_certificate" in config:
            certificate_name = config.managed_certificate
            additional_domains = config.get("additional_domains", [])
            domains = [certificate_name] + additional_domains
            ingress.add_annotations(
                {"networking.gke.io/managed-certificates": certificate_name}
            )
            self.add(
                GoogleManagedCertificate(
                    name=certificate_name, namespace=self.config.namespace,
                    config={"domains": domains}
                )
            )
