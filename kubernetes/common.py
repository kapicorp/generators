import logging

logger = logging.getLogger(__name__)
from enum import StrEnum, auto
from typing import Annotated, Any, Dict, List, Optional, Union

from kapitan.inputs.kadet import BaseObj, load_from_search_paths
from pydantic import ConfigDict, DirectoryPath, Field, FilePath, model_validator
from pydantic.alias_generators import to_camel

kgenlib = load_from_search_paths("kgenlib")


class GeneratorValidationError(Exception):
    # Raised when a generator fails to validate
    pass


class KubernetesResourceSpec(kgenlib.BaseModel):
    namespace: Optional[str] = None
    rendered_name: Optional[str] = None
    labels: Optional[Dict[str, str]] = {}
    annotations: Optional[Dict[str, str]] = {}
    spec: Optional[dict] = None


class KubernetesBaseResource(kgenlib.BaseContent):
    name: str
    api_version: str
    kind: str
    config: KubernetesResourceSpec = KubernetesResourceSpec()
    rendered_name: str = None

    def new(self):
        if self.config:
            if not self.rendered_name:
                self.rendered_name = self.config.rendered_name or self.name

    def __eq__(self, other):
        return (
            self.root.metadata.name == other.root.metadata.name
            and self.root.kind == other.root.kind
            and self.root.apiVersion == other.root.apiVersion
        )

    @classmethod
    def from_baseobj(cls, baseobj: BaseObj):
        """Return a BaseContent initialised with baseobj."""

        kind = baseobj.root.kind
        api_version = baseobj.root.apiVersion
        name = baseobj.root.metadata.name

        resource = cls(
            name=name,
            api_version=api_version,
            kind=kind,
            config=KubernetesResourceSpec(),
        )
        resource.root = baseobj.root
        return resource

    @property
    def component_name(self):
        return self.get_label("app.kapicorp.dev/component") or self.name

    def body(self):
        self.root.apiVersion = self.api_version
        self.root.kind = self.kind

        self.root.metadata.name = self.rendered_name or self.name
        self.root.metadata.labels
        self.root.metadata.annotations
        self.add_label("name", self.name)
        if self.config:
            self.add_labels(self.config.labels)
            self.add_annotations(self.config.annotations)

    def add_label(self, key: str, value: str):
        self.root.metadata.labels[key] = value

    def add_labels(self, labels: dict):
        if labels:
            for key, value in labels.items():
                self.add_label(key, value)

    def get_label(self, key: str):
        return self.root.metadata.labels.get(key, None)

    def add_annotation(self, key: str, value: str):
        self.root.metadata.annotations[key] = value

    def get_annotation(self, key: str):
        return self.root.metadata.annotations.get(key, None)

    def add_annotations(self, annotations: dict):
        if annotations:
            for key, value in annotations.items():
                self.add_annotation(key, value)

    def set_labels(self, labels: dict):
        self.root.metadata.labels = labels

    def set_annotations(self, annotations: dict):
        self.root.metadata.annotations = annotations

    def setup_global_defaults(self, inventory):
        try:
            globals = (
                inventory.parameters.generators.manifest.default_config.globals.get(
                    self.id, {}
                )
            )
            self.add_annotations(globals.get("annotations", {}))
            self.add_labels(globals.get("labels", {}))
        except AttributeError:
            pass


class KubernetesResource(KubernetesBaseResource):
    name: str
    api_version: str
    kind: str
    namespace: Optional[str] = None
    rendered_name: str = None

    def new(self):
        super().new()
        if self.config:
            self.namespace = self.config.namespace or self.namespace

    def __eq__(self, other):
        return (
            self.root.metadata.name == other.root.metadata.name
            and self.root.kind == other.root.kind
            and self.root.apiVersion == other.root.apiVersion
            and self.root.metadata.namespace == other.root.metadata.namespace
        )

    def body(self):
        super().body()
        self.root.metadata.namespace = self.namespace

    def set_namespace(self, namespace: str):
        self.root.metadata.namespace = namespace

    def remove_namespace(self):
        self.root.metadata.pop("namespace")


class WorkloadTypes(StrEnum):
    DEPLOYMENT = auto()
    STATEFULSET = auto()
    DAEMONSET = auto()
    JOB = auto()
    CRONJOB = auto()
    CLOUD_RUN_SERVICE = auto()


class RestartPolicy(StrEnum):
    ALWAYS = "Always"
    ON_FAILURE = "OnFailure"
    NEVER = "Never"


class ConcurrentPolicy(StrEnum):
    ALLOW = "Allow"
    FORBID = "Forbid"
    REPLACE = "Replace"


class ImagePullPolicy(StrEnum):
    ALWAYS = "Always"
    IF_NOT_PRESENT = "IfNotPresent"
    NEVER = "Never"


class DNSPolicy(StrEnum):
    CLUSTER_FIRST = "ClusterFirst"
    CLUSTER_FIRST_WITH_HOSTNET = "ClusterFirstWithHostNet"
    DEFAULT = "Default"


class ProbeSchemeSpec(StrEnum):
    HTTP = "HTTP"
    HTTPS = "HTTPS"


class ProbeTypes(StrEnum):
    HTTP = "HTTP"
    TCP = "TCP"
    EXEC = "EXEC"


class ContainerProbeSpec(kgenlib.BaseModel):
    enabled: bool = True
    type: ProbeTypes = ProbeTypes.HTTP
    initial_delay_seconds: int = 0
    period_seconds: int = 10
    timeout_seconds: int = 1
    success_threshold: int = 1
    failure_threshold: int = 3


class ContainerTCPProbeSpec(ContainerProbeSpec):
    type: ProbeTypes = ProbeTypes.TCP
    port: Optional[int | str] = 80


class ContainerHTTPProbeSpec(ContainerProbeSpec):
    type: ProbeTypes = ProbeTypes.HTTP
    path: Optional[str] = "/healthz"
    port: Optional[int | str] = 80
    scheme: Optional[ProbeSchemeSpec] = ProbeSchemeSpec.HTTP
    httpHeaders: Optional[List[Dict[str, str]]] = None


class ContainerEXECProbeSpec(ContainerProbeSpec):
    type: ProbeTypes = ProbeTypes.EXEC
    command: str


class HealthCheckConfigSpec(kgenlib.BaseModel):
    startup: Optional[
        ContainerEXECProbeSpec | ContainerHTTPProbeSpec | ContainerTCPProbeSpec
    ] = None
    liveness: Optional[
        ContainerEXECProbeSpec | ContainerHTTPProbeSpec | ContainerTCPProbeSpec
    ] = None
    readiness: Optional[
        ContainerEXECProbeSpec | ContainerHTTPProbeSpec | ContainerTCPProbeSpec
    ] = None


class ServiceAccountComponentConfigSpec(kgenlib.BaseModel):
    enabled: Optional[bool] = False
    name: Optional[str] = None
    create: Optional[bool] = False
    annotations: dict = {}
    labels: dict = {}


class PortProtocolSpec(StrEnum):
    TCP = "TCP"
    UDP = "UDP"


class ContainerPortSpec(kgenlib.BaseModel):
    name: Optional[str] = None
    container_port: Optional[int] = None
    service_port: Optional[int] = None
    protocol: Optional[PortProtocolSpec] = PortProtocolSpec.TCP


class SecurityContextSpec(kgenlib.BaseModel):
    allow_privilege_escalation: Optional[bool] = None


class TransformTypes(StrEnum):
    NONE = auto()
    JSON = auto()
    YAML = auto()
    AUTO = auto()


class ConfigDataSpec(kgenlib.BaseModel):
    b64_encode: Optional[bool] = False
    transform: Optional[TransformTypes] = TransformTypes.NONE
    value: Optional[str | dict] = None
    template: Optional[FilePath] = None
    values: Optional[Dict] = {}
    file: Optional[FilePath] = None


class SharedConfigSpec(KubernetesResourceSpec):
    data: Optional[Dict[str, ConfigDataSpec]] = {}
    binary_data: Optional[Dict[str, ConfigDataSpec]] = {}
    mount: Optional[str] = None
    readOnly: Optional[bool] = False
    subPath: Optional[str] = None
    items: Optional[list] = []
    default_mode: Optional[int] = 420
    directory: Optional[DirectoryPath] = None
    versioned: Optional[bool] = False


class ConfigMapSpec(SharedConfigSpec):
    pass


class SecretSpec(SharedConfigSpec):
    type: Optional[str] = "Opaque"
    string_data: Optional[Dict[str, str | ConfigDataSpec]] = {}


class ServiceAccountConfigSpec(KubernetesResourceSpec):
    annotations: dict = {}
    labels: dict = {}
    namespace: Optional[str] = None
    rendered_name: Optional[str] = None
    name: Optional[str] = None
    roles: Optional[
        list[dict[str, list[str]]] | dict[str, dict[str, list[str]] | list[str]]
    ] = None


class ContainerSpec(kgenlib.BaseModel):
    args: list = []
    command: list = []
    config_maps: Optional[Dict[str, SharedConfigSpec]] = {}
    secrets: Optional[Dict[str, SharedConfigSpec]] = {}
    env: dict = {}
    healthcheck: Optional[HealthCheckConfigSpec] = None
    image: str = None
    image_pull_policy: Optional[ImagePullPolicy] = ImagePullPolicy.IF_NOT_PRESENT
    lifecycle: Optional[dict] = None
    pod_annotations: dict = {}
    pod_labels: dict = {}
    ports: Dict[str, ContainerPortSpec] = {}
    resources: dict = {}
    security: Optional[SecurityContextSpec] = None
    security_context: dict = {}
    volume_mounts: dict = {}


class InitContainerSpec(ContainerSpec):
    sidecar: Optional[bool] = None


class ServiceTypes(StrEnum):
    EXTERNAL_NAME = "ExternalName"
    CLUSTER_IP = "ClusterIP"
    NODE_PORT = "NodePort"
    LOAD_BALANCER = "LoadBalancer"


class SessionAffinity(StrEnum):
    CLIENT_IP = "ClientIP"
    NONE = "None"


class RoleBindingConfigSpec(KubernetesResourceSpec):
    roleRef: Optional[Dict[str, Any]] = None
    subjects: Optional[List[Dict[str, Any]]] = None


class ServiceConfigSpec(KubernetesResourceSpec):
    service_name: Optional[str] = None
    type: Optional[ServiceTypes] = None
    selectors: Optional[Dict[str, str]] = {}
    publish_not_ready_address: Optional[bool] = None
    headless: Optional[bool] = False
    session_affinity: Optional[SessionAffinity] = SessionAffinity.NONE
    expose_ports: Optional[List[str]] = []


class VPAConfigSpec(kgenlib.BaseModel):
    update_mode: str = "Auto"
    resource_policy: Dict[str, List[Dict]] = {}

class HPAConfigSpec(kgenlib.BaseModel):
    min_replicas: Optional[int] = None
    max_replicas: Optional[int] = None
    metrics: List[Dict[str, Any]] = []

class ServiceMonitororConfigSpec(kgenlib.BaseModel):
    endpoints: list = []


class PrometheusRuleConfigSpec(kgenlib.BaseModel):
    rules: list = []


class NetworkPolicySpec(KubernetesResourceSpec):
    ingress: Optional[List[Dict[str, Any]]] = None
    egress: Optional[List[Dict[str, Any]]] = None


class WorkloadConfigSpec(KubernetesResourceSpec, ContainerSpec):
    type: Optional[WorkloadTypes] = WorkloadTypes.DEPLOYMENT
    namespace: str | None = None
    schedule: Optional[str] = None
    additional_containers: Optional[Dict[str, Union[ContainerSpec, None]]] = {}
    additional_services: Optional[Dict[str, ServiceConfigSpec]] = {}
    annotations: dict = {}
    application: Optional[str] = None
    auto_pdb: bool = False
    backend_config: dict = {}
    frontend_config: dict = {}
    cluster_role: Optional[Dict] = None
    containers: dict = {}
    deployment_progress_deadline_seconds: int | None = None
    dns_policy: Optional[DNSPolicy] = None
    grace_period: int = 30
    host_network: Optional[bool] = None
    host_pid: Optional[bool] = None
    hpa: Optional[HPAConfigSpec] = None
    image_pull_secrets: list = []
    init_containers: Optional[Dict[str, Union[InitContainerSpec, None]]] = {}
    istio_policy: dict = {}
    keda_scaled_object: dict = {}
    labels: Dict[str, str] = {}
    min_ready_seconds: Optional[int] = None
    network_policies: Optional[Dict[str, NetworkPolicySpec]] = {}
    node_selector: dict = {}
    pdb_min_available: Optional[int] = None
    pod_security_policy: dict = {}
    prefer_pods_in_different_nodes: bool = False
    prefer_pods_in_different_zones: bool = False
    prefer_pods_in_node_with_expression: dict = {}
    prometheus_rules: Optional[PrometheusRuleConfigSpec] = None
    replicas: int = Field(1, ge=0, description="Number of replicas")
    restart_policy: Optional[RestartPolicy] = RestartPolicy.ALWAYS
    revision_history_limit: int | None = None
    role: Optional[Dict] = None
    service: Optional[ServiceConfigSpec] = None
    service_account: Optional[ServiceAccountComponentConfigSpec] = None
    service_monitors: Optional[ServiceMonitororConfigSpec] = None
    tolerations: list = []
    volume_claims: dict = {}
    volumes: dict = {}
    vpa: Optional[VPAConfigSpec] = None
    webhooks: list = []
    workload_security_context: dict = {}


class CloudRunServiceConfigSpec(WorkloadConfigSpec):
    type: Optional[WorkloadTypes] = WorkloadTypes.CLOUD_RUN_SERVICE


class DeploymentConfigSpec(WorkloadConfigSpec):
    type: Optional[WorkloadTypes] = WorkloadTypes.DEPLOYMENT
    update_strategy: Optional[dict] = {}
    strategy: Optional[dict] = {}


class PodManagementPolicy(StrEnum):
    ORDERED_READY = "OrderedReady"
    PARALLEL = "Parallel"


class StatefulSetConfigSpec(WorkloadConfigSpec):
    type: WorkloadTypes = WorkloadTypes.STATEFULSET
    pod_management_policy: str = PodManagementPolicy.ORDERED_READY
    update_strategy: dict = {}


class DaemonSetConfigSpec(WorkloadConfigSpec):
    type: WorkloadTypes = WorkloadTypes.DAEMONSET


class JobConfigSpec(WorkloadConfigSpec):
    type: WorkloadTypes = WorkloadTypes.JOB
    backoff_limit: int = 1
    completions: int = 1
    parallelism: int = 1
    restart_policy: RestartPolicy = RestartPolicy.NEVER


class CronJobConfigSpec(JobConfigSpec):
    type: WorkloadTypes = WorkloadTypes.CRONJOB
    schedule: str
    concurrency_policy: Optional[ConcurrentPolicy] = ConcurrentPolicy.ALLOW


ContainerProbeSpecTypes = Annotated[
    Union[ContainerEXECProbeSpec, ContainerHTTPProbeSpec, ContainerTCPProbeSpec],
    Field(discriminator="type"),
]


class ContainerProbes(kgenlib.BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="ignore",
    )
    type: ProbeTypes = Field(exclude=True)
    initial_delay_seconds: int = 0
    period_seconds: int = 10
    timeout_seconds: int = 1
    success_threshold: int = 1
    failure_threshold: int = 3

    # Define a class method for creating probes from data
    @classmethod
    def from_spec(cls, spec: ContainerProbeSpecTypes) -> Union["ContainerProbes", None]:
        probe = None
        if not spec or not spec.enabled:
            return probe
        probe_type = spec.type
        if probe_type == ProbeTypes.TCP:
            probe = TCPProbe.model_validate(spec)
        elif probe_type == ProbeTypes.HTTP:
            probe = HTTPProbe.model_validate(spec)
        elif probe_type == ProbeTypes.EXEC:
            probe = ExecProbe.model_validate(spec)
        else:
            raise ValueError(f"Invalid probe type: {probe_type}")
        return probe.model_dump(by_alias=True)


class HttpGet(kgenlib.BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
    path: str = "/"
    port: str | int = 80
    httpHeaders: Optional[List[dict]] = None
    scheme: Optional[ProbeSchemeSpec] = ProbeSchemeSpec.HTTP


class HTTPProbe(ContainerProbes):
    httpGet: Optional[HttpGet] = None
    port: str | int = Field(exclude=True)
    path: str = Field(exclude=True)
    scheme: Optional[ProbeSchemeSpec] = Field(exclude=True)
    httpHeaders: Optional[List[dict]] = Field(exclude=True)

    # Use a validator to handle the 'port' mapping
    @model_validator(mode="after")
    def map_port_to_http_config(self):
        self.httpGet = HttpGet.model_validate(self)
        return self


class TCPProbe(ContainerProbes):
    port: str | int = Field(exclude=True)
    tcpSocket: Optional[dict] = None

    # Use a validator to handle the 'port' mapping
    @model_validator(mode="after")
    def map_port_to_tcp_socket(self):
        self.tcpSocket = {"port": self.port}
        return self


class ExecProbe(ContainerProbes):
    command: List = Field(exclude=True)
    exec: Optional[dict] = None

    @model_validator(mode="after")
    def map_command_to_exec_socket(self):
        self.exec = {"command": self.command}
        return self


ContainerProbeTypes = Annotated[
    Union[HTTPProbe, TCPProbe, ExecProbe], Field(discriminator="type")
]
