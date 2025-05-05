import logging

from kapitan.inputs.kadet import BaseModel, CompileError

from .autoscaling import (
    HorizontalPodAutoscaler,
    KedaScaledObject,
    PodDisruptionBudget,
    VerticalPodAutoscaler,
)
from .base import MutatingWebhookConfiguration
from .common import (
    CloudRunServiceConfigSpec,
    ContainerProbes,
    ContainerSpec,
    CronJobConfigSpec,
    DaemonSetConfigSpec,
    DeploymentConfigSpec,
    InitContainerSpec,
    JobConfigSpec,
    KubernetesResource,
    StatefulSetConfigSpec,
    WorkloadConfigSpec,
    WorkloadTypes,
    kgenlib,
)
from .gke import BackendConfig, FrontendConfig
from .istio import IstioPolicy
from .networking import NetworkPolicy, Service
from .prometheus import PrometheusRule, ServiceMonitor
from .rbac import ClusterRole, ClusterRoleBinding, Role, RoleBinding, ServiceAccount
from .storage import ComponentConfig, ComponentSecret

logger = logging.getLogger(__name__)


class CloudRunResource(KubernetesResource):
    def body(self):
        super().body()
        name = self.name
        config = self.config

        self.root.spec.template.metadata.annotations.update(config.pod_annotations)
        self.root.spec.template.metadata.labels.update(config.pod_labels)

        if config.service_account.enabled:
            self.root.spec.template.spec.serviceAccountName = (
                config.service_account.name or name
            )

        container = Container(name=name, config=config)
        additional_containers = [
            Container(name=name, config=_config)
            for name, _config in config.additional_containers.items()
            if _config is not None
        ]
        self.add_containers([container])
        self.add_containers(additional_containers)
        self.root.spec.template.spec.imagePullSecrets = config.image_pull_secrets
        self.add_volumes(config.volumes)

    def add_volumes(self, volumes):
        for key, value in volumes.items():
            kgenlib.merge({"name": key}, value)
            self.root.spec.template.spec.setdefault("volumes", []).append(value)

    def add_containers(self, containers):
        self.root.spec.template.spec.setdefault("containers", []).extend(
            [container.root for container in containers]
        )


class Workload(KubernetesResource):
    def body(self):
        super().body()
        name = self.name
        config = self.config
        self.root.spec.template.spec.hostNetwork = config.host_network
        self.root.spec.template.spec.hostPID = config.host_pid

        self.root.spec.template.metadata.annotations.update(config.pod_annotations)
        self.root.spec.template.metadata.labels.update(config.pod_labels)

        self.add_volumes(config.volumes)
        self.root.spec.template.spec.securityContext = config.workload_security_context
        self.root.spec.minReadySeconds = config.min_ready_seconds
        if config.service_account.enabled:
            self.root.spec.template.spec.serviceAccountName = (
                config.service_account.name or name
            )

        container = Container(name=name, config=config)
        additional_containers = [
            Container(name=name, config=_config)
            for name, _config in config.additional_containers.items()
            if _config is not None
        ]
        self.add_containers([container])
        self.add_containers(additional_containers)
        init_containers = [
            InitContainer(name=name, config=_config)
            for name, _config in config.init_containers.items()
            if _config is not None
        ]

        self.add_init_containers(init_containers)
        self.root.spec.template.spec.imagePullSecrets = config.image_pull_secrets
        self.root.spec.template.spec.dnsPolicy = config.dns_policy

        self.root.spec.template.spec.restartPolicy = config.restart_policy
        self.root.spec.template.spec.terminationGracePeriodSeconds = config.grace_period

        self.root.spec.template.spec.nodeSelector = config.node_selector

        self.root.spec.template.spec.tolerations = config.tolerations

        affinity = self.root.spec.template.spec.affinity
        if config.prefer_pods_in_node_with_expression and not config.node_selector:
            affinity.nodeAffinity.setdefault(
                "preferredDuringSchedulingIgnoredDuringExecution", []
            )
            affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution.append(
                {
                    "preference": {
                        "matchExpressions": [config.prefer_pods_in_node_with_expression]
                    },
                    "weight": 1,
                }
            )

        if config.prefer_pods_in_different_nodes:
            affinity.podAntiAffinity.setdefault(
                "preferredDuringSchedulingIgnoredDuringExecution", []
            )
            affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution.append(
                {
                    "podAffinityTerm": {
                        "labelSelector": {
                            "matchExpressions": [
                                {"key": "name", "operator": "In", "values": [name]}
                            ]
                        },
                        "topologyKey": "kubernetes.io/hostname",
                    },
                    "weight": 1,
                }
            )

        if config.prefer_pods_in_different_zones:
            affinity.podAntiAffinity.setdefault(
                "preferredDuringSchedulingIgnoredDuringExecution", []
            )
            affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution.append(
                {
                    "podAffinityTerm": {
                        "labelSelector": {
                            "matchExpressions": [
                                {"key": "name", "operator": "In", "values": [name]}
                            ]
                        },
                        "topologyKey": "topology.kubernetes.io/zone",
                    },
                    "weight": 1,
                }
            )

        return self

    def set_replicas(self, replicas):
        self.root.spec.replicas = replicas

    def add_containers(self, containers):
        self.root.spec.template.spec.setdefault("containers", []).extend(
            [container.root for container in containers]
        )

    def add_init_containers(self, containers):
        self.root.spec.template.spec.setdefault("initContainers", []).extend(
            container.root for container in containers
        )

    def add_volumes(self, volumes):
        for key, value in volumes.items():
            kgenlib.merge({"name": key}, value)
            self.root.spec.template.spec.setdefault("volumes", []).append(value)

    def add_volume_claims(self, volume_claims):
        self.root.spec.setdefault("volumeClaimTemplates", [])
        for key, value in volume_claims.items():
            kgenlib.merge({"metadata": {"name": key, "labels": {"name": key}}}, value)
            self.root.spec.volumeClaimTemplates += [value]

    def add_volumes_for_object(self, object):
        object_name = object.object_name
        rendered_name = object.rendered_name

        if type(object) == ComponentConfig:
            key = "configMap"
            name_key = "name"
        else:
            key = "secret"
            name_key = "secretName"

        template = self.root.spec.template
        if isinstance(self, CronJob):
            template = self.root.spec.jobTemplate.spec.template

        template.spec.setdefault("volumes", []).append(
            {
                "name": object_name,
                key: {
                    "defaultMode": object.config.default_mode,
                    name_key: rendered_name,
                    "items": [
                        {"key": value, "path": value} for value in object.config.items
                    ],
                },
            }
        )


class CloudRunService(CloudRunResource):
    kind: str = "Service"
    api_version: str = "serving.knative.dev/v1"
    config: CloudRunServiceConfigSpec

    def body(self):
        super().body()


class Deployment(Workload):
    kind: str = "Deployment"
    api_version: str = "apps/v1"
    config: DeploymentConfigSpec

    def body(self):
        default_strategy = {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"},
        }
        super().body()
        config = self.config
        self.root.spec.template.metadata.setdefault("labels", {}).update(
            config.labels + self.root.metadata.labels
        )
        self.root.spec.selector.setdefault("matchLabels", {}).update(
            config.labels + self.root.metadata.labels
        )
        self.root.spec.strategy = config.update_strategy or default_strategy
        self.root.spec.revisionHistoryLimit = config.revision_history_limit
        self.root.spec.progressDeadlineSeconds = (
            config.deployment_progress_deadline_seconds
        )
        self.set_replicas(config.replicas)


class StatefulSet(Workload):
    kind: str = "StatefulSet"
    api_version: str = "apps/v1"
    config: StatefulSetConfigSpec

    def body(self):
        update_strategy = {"rollingUpdate": {"partition": 0}, "type": "RollingUpdate"}

        super().body()
        name = self.name
        config = self.config
        self.root.spec.template.metadata.setdefault("labels", {}).update(
            config.labels + self.root.metadata.labels
        )
        self.root.spec.selector.setdefault("matchLabels", {}).update(
            config.labels + self.root.metadata.labels
        )

        self.root.spec.revisionHistoryLimit = config.revision_history_limit
        self.root.spec.podManagementPolicy = config.pod_management_policy
        self.root.spec.updateStrategy = config.update_strategy or update_strategy
        if config.service:
            self.root.spec.serviceName = config.service.service_name or name
        self.set_replicas(config.replicas)
        self.add_volume_claims(config.volume_claims)


class DaemonSet(Workload):
    kind: str = "DaemonSet"
    api_version: str = "apps/v1"
    config: DaemonSetConfigSpec

    def body(self):
        super().body()
        config = self.config
        self.root.spec.template.metadata.setdefault("labels", {}).update(
            config.labels + self.root.metadata.labels
        )
        self.root.spec.selector.setdefault("matchLabels", {}).update(
            config.labels + self.root.metadata.labels
        )
        self.root.spec.revisionHistoryLimit = config.revision_history_limit
        self.root.spec.progressDeadlineSeconds = (
            config.deployment_progress_deadline_seconds
        )


class Job(Workload):
    kind: str = "Job"
    api_version: str = "batch/v1"
    config: JobConfigSpec

    def body(self):
        super().body()
        config = self.config
        self.root.spec.template.metadata.setdefault("labels", {}).update(
            config.labels + self.root.metadata.labels
        )
        self.root.spec.backoffLimit = config.backoff_limit
        self.root.spec.completions = config.completions
        self.root.spec.parallelism = config.parallelism


class CronJob(Workload):
    kind: str = "CronJob"
    api_version: str = "batch/v1"
    config: CronJobConfigSpec

    def body(self):
        super().body()
        config = self.config
        job = Job(name=self.name, config=config)
        self.root.spec.jobTemplate.spec = job.root.spec
        self.root.spec.schedule = config.schedule
        self.root.spec.concurrencyPolicy = config.concurrency_policy
        self.root.spec.template = None


class Container(BaseModel):
    config: ContainerSpec

    @staticmethod
    def find_key_in_config(key, configs):
        for name, config in configs.items():
            if key in config.data or key in config.string_data:
                return name
        raise (
            BaseException(
                "Unable to find key {} in your configs definitions".format(key)
            )
        )

    def process_envs(self, config):
        name = self.name

        for env_name, value in sorted(config.env.items()):
            if isinstance(value, dict):
                if "fieldRef" in value:
                    self.root.setdefault("env", []).append(
                        {"name": env_name, "valueFrom": value}
                    )
                elif "secretKeyRef" in value:
                    if "name" not in value["secretKeyRef"]:
                        config_name = self.find_key_in_config(
                            value["secretKeyRef"]["key"], config.secrets
                        )
                        # TODO(ademaria) I keep repeating this logic. Refactor.
                        if len(config.secrets.keys()) == 1:
                            value["secretKeyRef"]["name"] = name
                        else:
                            value["secretKeyRef"]["name"] = "{}-{}".format(
                                name, config_name
                            )

                    self.root.setdefault("env", []).append(
                        {"name": env_name, "valueFrom": value}
                    )
                if "configMapKeyRef" in value:
                    if "name" not in value["configMapKeyRef"]:
                        config_name = self.find_key_in_config(
                            value["configMapKeyRef"]["key"], config.config_maps
                        )
                        # TODO(ademaria) I keep repeating this logic. Refactor.
                        if len(config.config_maps.keys()) == 1:
                            value["configMapKeyRef"]["name"] = name
                        else:
                            value["configMapKeyRef"]["name"] = "{}-{}".format(
                                name, config_name
                            )

                    self.root.setdefault("env", []).append(
                        {"name": env_name, "valueFrom": value}
                    )
            else:
                self.root.setdefault("env", []).append(
                    {"name": env_name, "value": str(value)}
                )

    def add_volume_mounts_from_configs(self):
        name = self.name
        config = self.config
        objects = list(config.config_maps.items()) + list(config.secrets.items())
        for object_name, spec in objects:
            if spec is None:
                raise CompileError(
                    f"error with '{object_name}' for component {name}: configuration cannot be empty!"
                )

            if spec.mount:
                self.root.setdefault("volumeMounts", [])
                self.root.volumeMounts += [
                    {
                        "mountPath": spec.mount,
                        "readOnly": spec.readOnly or None,
                        "name": object_name,
                        "subPath": spec.subPath,
                    }
                ]

    def add_volume_mounts(self, volume_mounts):
        for key, value in volume_mounts.items():
            kgenlib.merge({"name": key}, value)
            self.root.setdefault("volumeMounts", []).append(value)

    def body(self):
        name = self.name
        config = self.config

        self.root.name = name
        self.root.image = config.image
        self.root.imagePullPolicy = config.image_pull_policy
        if config.lifecycle:
            self.root.lifecycle = config.lifecycle
        self.root.resources = config.resources
        self.root.args = config.args
        self.root.command = config.command
        # legacy container.security
        if config.security:
            self.root.securityContext.allowPrivilegeEscalation = (
                config.security.allow_privilege_escalation
            )
            self.root.securityContext.runAsUser = config.security.user_id
        else:
            self.root.securityContext = config.security_context
        self.add_volume_mounts_from_configs()
        self.add_volume_mounts(config.volume_mounts)

        for name, port in sorted(config.ports.items()):
            self.root.setdefault("ports", [])
            self.root.ports.append(
                {
                    "containerPort": port.container_port or port.service_port,
                    "name": name,
                    "protocol": port.protocol,
                }
            )

        if config.healthcheck:
            self.root.livenessProbe = ContainerProbes.from_spec(
                config.healthcheck.liveness
            )
            self.root.readinessProbe = ContainerProbes.from_spec(
                config.healthcheck.readiness
            )
            self.root.startupProbe = ContainerProbes.from_spec(
                config.healthcheck.startup
            )

        self.process_envs(config)


class InitContainer(Container):
    config: InitContainerSpec

    def body(self):
        config = self.config
        super().body()
        if config.sidecar:
            self.root.restartPolicy = "Always"


class PodSecurityPolicy(KubernetesResource):
    kind: str = "PodSecurityPolicy"
    api_version: str = "policy/v1beta1"
    workload: Workload

    def new(self):
        super().new()

    def body(self):
        super().body()
        config = self.config
        self.root.spec = config.pod_security_policy.spec
        # Merge Dicts into PSP Annotations
        self.root.metadata.annotations = {
            **config.get("annotations", {}),
            **config.pod_security_policy.get("annotations", {}),
        }
        # Merge Dicts into PSP Labels
        self.root.metadata.labels = {
            **config.get("labels", {}),
            **config.pod_security_policy.get("labels", {}),
        }


@kgenlib.register_generator(
    path="components",
    apply_patches=[
        "generators.manifest.default_config",
        'applications."{application}".component_defaults',
        'generators.manifest.resource_defaults.{type}'
    ],
)
class Components(kgenlib.BaseStore):
    config: WorkloadConfigSpec

    def _add_component(
        self,
        component_class,
        config_attr=None,
        name=None,
        workload=None,
        spec=None,
        **kwargs,
    ):
        if config_attr and getattr(self.config, config_attr):
            spec = spec or getattr(self.config, config_attr, {})
            name = name or self.name

            component = component_class(
                name=name, config=self.config, spec=spec, workload=workload, **kwargs
            )
            self.add(component)
            logger.debug(f"Added component {component.root.metadata} for {self.name}.")
            return component


    def _generate_and_add_multiple_objects(
        self, generating_class, config_attr, workload
    ):
        objects_configs = getattr(self.config, config_attr, {})

        for object_name, object_config in objects_configs.items():
            logger.debug(
                f"Generating object {object_name} of type {generating_class.__name__} for {self.name}."
            )

            if object_config is None:
                raise CompileError(
                    f"error with '{object_name}' for component {self.name}: configuration cannot be empty!"
                )

            if len(objects_configs) == 1:
                name = self.name
            else:
                name = f"{self.name}-{object_name}"

            namespace = object_config.namespace or self.config.namespace or None
            generated_object = generating_class(
                name=name,
                object_name=object_name,
                namespace=namespace,
                config=object_config.model_dump(),
                component=self.config,
                workload=workload,
            )

            self.add(generated_object)

    def body(self):
        name = self.name
        config = self.config
        logger.debug(f"Generating components for {name} from {config}")
        namespace = config.namespace

        if config.type == WorkloadTypes.DEPLOYMENT:
            workload = Deployment(name=name, config=config.model_dump())
        elif config.type == WorkloadTypes.STATEFULSET:
            workload = StatefulSet(name=name, config=config.model_dump())
        elif config.type == WorkloadTypes.DAEMONSET:
            workload = DaemonSet(name=name, config=config.model_dump())
        elif config.type == WorkloadTypes.JOB:
            if config.schedule:
                workload = CronJob(name=name, config=config.model_dump())
            else:
                workload = Job(name=name, config=config.model_dump())
        elif config.type == WorkloadTypes.CLOUD_RUN_SERVICE:
            workload = CloudRunService(name=name, config=config.model_dump())
        else:
            raise ValueError(f"Unknown workload type: {config.type}")

        self._generate_and_add_multiple_objects(
            ComponentConfig, "config_maps", workload=workload
        )
        self._generate_and_add_multiple_objects(
            ComponentSecret, "secrets", workload=workload
        )

        self._add_component(PodDisruptionBudget, "pdb_min_available", workload=workload)
        self._add_component(HorizontalPodAutoscaler, "hpa", workload=workload)
        self._add_component(VerticalPodAutoscaler, "vpa", workload=workload)
        self._add_component(KedaScaledObject, "keda_scaled_object", workload=workload)
        self._add_component(IstioPolicy, "istio_policy", workload=workload)
        self._add_component(PodSecurityPolicy, "pod_security_policy", workload=workload)
        self._add_component(
            Service, "service", workload=workload, spec=self.config.service
        )

        for service_name, spec in config.additional_services.items():
            logger.debug(f"Adding additional service {service_name} for {name}.")
            self._add_component(
                Service,
                "additional_services",
                workload=workload,
                name=service_name,
                spec=spec,
            )

        self._generate_and_add_multiple_objects(
            NetworkPolicy, "network_policies", workload=workload
        )
        self._add_component(MutatingWebhookConfiguration, "webhooks")
        self._add_component(ServiceMonitor, "service_monitors", workload=workload)
        self._add_component(PrometheusRule, "prometheus_rules")

        if self.config.service_account.create:
            sa = self._add_component(ServiceAccount, "service_account")

            if self.config.role:
                role = self._add_component(Role, "role")
                if role:
                    self._add_component(RoleBinding, "role", sa=sa, role=role)

            if self.config.cluster_role:
                role = self._add_component(ClusterRole, "cluster_role")
                if role:
                    self._add_component(
                        ClusterRoleBinding, "cluster_role", role=role, sa=sa
                    )
        self._add_component(BackendConfig, "backend_config", spec=self.config.backend_config)
        self._add_component(FrontendConfig, "frontend_config", spec=self.config.frontend_config)


        # Handling a special case where pdb_min_available or auto_pdb is set, but config.type isn't "job"
        if self.config.type != "job" and (
            self.config.pdb_min_available or self.config.auto_pdb
        ):
            config_attr = "pdb_min_available" if self.config.pdb_min_available else "auto_pdb"
            self._add_component(PodDisruptionBudget, config_attr, workload=workload)

        self.add(workload)

        # Patch Application
        if type(workload) != CloudRunService:
            self.apply_patch(
                {"metadata": {"labels": {"app.kapicorp.dev/component": self.name}}}
            )
            logger.debug(f"Applied metadata patch for {self.name}.")

        if namespace:
            for o in self.get_content_list():
                if o.root.kind != "Namespace":
                    o.root.metadata.namespace = namespace
